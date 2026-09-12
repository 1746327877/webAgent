"""后台聚合：仪表盘概览（设计 08.4 / 08.6）。

口径说明：
- 除 HTTP / VRAM 外，全部指标按当前用户过滤（owner 隔离）。
- HTTP 计数与 VRAM 是进程级系统指标：HTTP 桶无用户维度（设计 08.2），
  ``model_events`` 同样无用户维度，不做用户过滤，记录在案。
- HTTP 中间件记录的是 time-to-response-start（TTFB）耗时，见 ``app.main``；
  且中间件在响应完成后才 ``record``，因此处理本请求时它不计入 pending——
  pending 只含「已完成但未落库」的请求，与 DB 小时桶合并出参。
- 所有 span 聚合走固定数量的 SQL，不在行上做 N+1 查询。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.observability.http_stats import collector as default_http_collector

_LLM_TOTALS = text("""
    SELECT count(*) AS llm_calls,
           count(*) FILTER (WHERE status = 'error') AS errors,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
           COALESCE(sum(prompt_tokens), 0) AS prompt_tokens,
           COALESCE(sum(completion_tokens), 0) AS completion_tokens,
           COALESCE(sum(duration_ms), 0) AS gpu_ms
    FROM spans
    WHERE type = 'llm' AND user_id = :uid AND started_at >= :since
""")

_LLM_HOURLY = text("""
    SELECT date_trunc('hour', started_at) AS hour,
           count(*) AS llm_calls,
           count(*) FILTER (WHERE status = 'error') AS errors,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
           COALESCE(sum(prompt_tokens), 0) AS prompt_tokens,
           COALESCE(sum(completion_tokens), 0) AS completion_tokens
    FROM spans
    WHERE type = 'llm' AND user_id = :uid AND started_at >= :since
    GROUP BY 1 ORDER BY 1
""")

_AGENTS = text("""
    SELECT s.agent_id, a.name,
           count(*) AS llm_calls,
           COALESCE(sum(COALESCE(s.prompt_tokens, 0) + COALESCE(s.completion_tokens, 0)), 0)
               AS tokens
    FROM spans s
    LEFT JOIN agents a ON a.id = s.agent_id AND a.owner_id = :uid
    WHERE s.type = 'llm' AND s.user_id = :uid AND s.started_at >= :since
      AND s.agent_id IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 3 DESC, 4 DESC
    LIMIT 10
""")

_MODELS = text("""
    SELECT model,
           count(*) AS llm_calls,
           COALESCE(sum(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0)
               AS tokens
    FROM spans
    WHERE type = 'llm' AND user_id = :uid AND started_at >= :since
      AND model IS NOT NULL
    GROUP BY model
    ORDER BY 2 DESC, 3 DESC
    LIMIT 10
""")

_TOOLS = text("""
    SELECT name AS tool,
           count(*) AS calls,
           count(*) FILTER (WHERE status = 'error') AS errors,
           avg(duration_ms) AS avg_ms
    FROM spans
    WHERE type = 'tool' AND user_id = :uid AND started_at >= :since
      AND name IS NOT NULL
    GROUP BY name
    ORDER BY 2 DESC, 1
    LIMIT 10
""")

_TOOL_TOTALS = text("""
    SELECT count(*) AS tool_calls,
           count(*) FILTER (WHERE status = 'error') AS errors
    FROM spans
    WHERE type = 'tool' AND user_id = :uid AND started_at >= :since
""")

_SWITCHES = text("""
    SELECT input ->> 'from' AS from_model,
           input ->> 'to' AS to_model,
           count(*) AS count,
           avg(duration_ms) AS avg_ms
    FROM spans
    WHERE type = 'model_switch' AND user_id = :uid AND started_at >= :since
      AND input IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 3 DESC, 1, 2
    LIMIT 10
""")

_SWITCH_TOTALS = text("""
    SELECT count(*) AS switches,
           COALESCE(sum(duration_ms), 0) AS switch_ms
    FROM spans
    WHERE type = 'model_switch' AND user_id = :uid AND started_at >= :since
""")

_RETRIEVAL = text("""
    SELECT count(*) AS calls,
           count(*) FILTER (WHERE status = 'error') AS errors,
           avg(duration_ms) AS avg_ms
    FROM spans
    WHERE type = 'retrieval' AND user_id = :uid AND started_at >= :since
""")

_HTTP_HOURLY = text("""
    SELECT date_trunc('hour', bucket) AS bucket,
           sum(requests) AS requests,
           sum(errors) AS errors,
           sum(duration_sum_ms) AS duration_sum_ms
    FROM http_stats
    WHERE bucket >= :since
    GROUP BY 1 ORDER BY 1
""")

_VRAM = text("""
    SELECT created_at, vram_after_mb
    FROM model_events
    WHERE created_at >= :since AND vram_after_mb IS NOT NULL
    ORDER BY created_at
""")


def _ms(value) -> float:
    """avg()/percentile_cont() 在 asyncpg 下可能返回 Decimal，统一转 float。"""
    return round(float(value or 0), 1)


def _rate(errors: int, total: int) -> float:
    return round(errors / total * 100, 1) if total else 0.0


def _merge_http(db_rows, pending: dict, since: datetime) -> tuple[list[dict], dict]:
    """DB 小时桶 + 内存 pending（分钟桶折算到小时）合并。"""
    by_hour: dict[datetime, dict] = {}
    for row in db_rows:
        by_hour[row["bucket"]] = {
            "requests": int(row["requests"] or 0),
            "errors": int(row["errors"] or 0),
            "duration_sum_ms": int(row["duration_sum_ms"] or 0),
        }
    for bucket, row in pending.items():
        if bucket < since:
            continue
        hour = bucket.replace(minute=0, second=0, microsecond=0)
        acc = by_hour.setdefault(hour, {"requests": 0, "errors": 0, "duration_sum_ms": 0})
        acc["requests"] += int(row.get("requests", 0))
        acc["errors"] += int(row.get("errors", 0))
        acc["duration_sum_ms"] += int(row.get("duration_sum_ms", 0))

    series: list[dict] = []
    totals = {"requests": 0, "errors": 0, "duration_sum_ms": 0}
    for hour in sorted(by_hour):
        acc = by_hour[hour]
        totals["requests"] += acc["requests"]
        totals["errors"] += acc["errors"]
        totals["duration_sum_ms"] += acc["duration_sum_ms"]
        series.append({
            "bucket": hour.isoformat(),
            "requests": acc["requests"],
            "errors": acc["errors"],
            "avg_ms": round(acc["duration_sum_ms"] / acc["requests"], 1)
            if acc["requests"] else 0.0,
        })
    return series, totals


async def build_overview(db, *, user_id, hours, manager=None, collector=None) -> dict:
    """聚合窗口内的 LLM / 工具 / 检索 / 切换 / HTTP / VRAM 指标。

    空数据时列表为 []、计数为 0、耗时为 0.0（前端空态依赖）。
    """
    since = datetime.now(UTC) - timedelta(hours=hours)
    params = {"uid": user_id, "since": since}

    llm_totals = (await db.execute(_LLM_TOTALS, params)).mappings().one()
    series_rows = (await db.execute(_LLM_HOURLY, params)).mappings().all()
    agent_rows = (await db.execute(_AGENTS, params)).mappings().all()
    model_rows = (await db.execute(_MODELS, params)).mappings().all()
    tool_rows = (await db.execute(_TOOLS, params)).mappings().all()
    tool_totals = (await db.execute(_TOOL_TOTALS, params)).mappings().one()
    switch_rows = (await db.execute(_SWITCHES, params)).mappings().all()
    switch_totals = (await db.execute(_SWITCH_TOTALS, params)).mappings().one()
    retrieval_row = (await db.execute(_RETRIEVAL, params)).mappings().one()
    http_rows = (await db.execute(_HTTP_HOURLY, params)).mappings().all()
    vram_rows = (await db.execute(_VRAM, params)).mappings().all()

    series = [
        {
            "hour": row["hour"].isoformat(),
            "llm_calls": int(row["llm_calls"] or 0),
            "prompt_tokens": int(row["prompt_tokens"] or 0),
            "completion_tokens": int(row["completion_tokens"] or 0),
            "p95_ms": _ms(row["p95_ms"]),
            "errors": int(row["errors"] or 0),
        }
        for row in series_rows
    ]
    agents = [
        {
            "agent_id": str(row["agent_id"]),
            "name": row["name"],
            "llm_calls": int(row["llm_calls"] or 0),
            "tokens": int(row["tokens"] or 0),
        }
        for row in agent_rows
    ]
    models = [
        {
            "model": row["model"],
            "llm_calls": int(row["llm_calls"] or 0),
            "tokens": int(row["tokens"] or 0),
        }
        for row in model_rows
    ]
    tools = [
        {
            "tool": row["tool"],
            "calls": int(row["calls"] or 0),
            "errors": int(row["errors"] or 0),
            "avg_ms": _ms(row["avg_ms"]),
        }
        for row in tool_rows
    ]
    switches = [
        {
            "from_model": row["from_model"],
            "to_model": row["to_model"],
            "count": int(row["count"] or 0),
            "avg_ms": _ms(row["avg_ms"]),
        }
        for row in switch_rows
    ]
    retrieval = {
        "calls": int(retrieval_row["calls"] or 0),
        "errors": int(retrieval_row["errors"] or 0),
        "avg_ms": _ms(retrieval_row["avg_ms"]),
    }

    pending = (collector or default_http_collector).pending()
    http_series, http_totals = _merge_http(http_rows, pending, since)
    http = {
        "requests": http_totals["requests"],
        "errors": http_totals["errors"],
        "error_rate": _rate(http_totals["errors"], http_totals["requests"]),
        "avg_ms": round(http_totals["duration_sum_ms"] / http_totals["requests"], 1)
        if http_totals["requests"] else 0.0,
        "series": http_series,
    }

    vram = [
        {"ts": row["created_at"].isoformat(), "vram_mb": int(row["vram_after_mb"])}
        for row in vram_rows
    ]
    if manager is not None:
        snapshot = getattr(manager, "last_snapshot", None) or {}
        vram_mb = snapshot.get("vram_mb")
        if vram_mb is not None:
            vram.append({
                "ts": snapshot.get("updated_at") or datetime.now(UTC).isoformat(),
                "vram_mb": int(vram_mb),
            })

    llm_calls = int(llm_totals["llm_calls"] or 0)
    errors = int(llm_totals["errors"] or 0)
    cards = {
        "llm_calls": llm_calls,
        "errors": errors,
        "error_rate": _rate(errors, llm_calls),
        "p95_ms": _ms(llm_totals["p95_ms"]),
        "prompt_tokens": int(llm_totals["prompt_tokens"] or 0),
        "completion_tokens": int(llm_totals["completion_tokens"] or 0),
        "gpu_ms": _ms(llm_totals["gpu_ms"]),
        "model_switches": int(switch_totals["switches"] or 0),
        "switch_ms": _ms(switch_totals["switch_ms"]),
        "tool_calls": int(tool_totals["tool_calls"] or 0),
        "tool_error_rate": _rate(
            int(tool_totals["errors"] or 0), int(tool_totals["tool_calls"] or 0)
        ),
        "retrieval_calls": retrieval["calls"],
        "retrieval_avg_ms": retrieval["avg_ms"],
        "http_requests": http["requests"],
        "http_error_rate": http["error_rate"],
    }

    return {
        "hours": hours,
        "cards": cards,
        "series": series,
        "agents": agents,
        "models": models,
        "tools": tools,
        "switches": switches,
        "retrieval": retrieval,
        "http": http,
        "vram": vram,
    }
