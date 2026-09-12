import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.main import app
from tests.fake_provider import FakeProvider


async def _seed_span(session_maker, user_id, **fields):
    from app.models import Span

    defaults = {
        "trace_id": uuid.uuid4(),
        "type": "llm",
        "name": fields.get("model", "m"),
        "status": "ok",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "duration_ms": 800,
        "started_at": datetime.now(UTC) - timedelta(hours=1),
        "ended_at": datetime.now(UTC),
    }
    defaults.update(fields)
    async with session_maker() as db:
        db.add(Span(user_id=user_id, **defaults))
        await db.commit()


async def _uid(client, headers):
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return uuid.UUID(me["id"])


async def test_overview_aggregates_and_isolates(client, auth_headers, session_maker):
    uid = await _uid(client, auth_headers)
    now = datetime.now(UTC)
    await _seed_span(session_maker, uid, prompt_tokens=10, completion_tokens=5, duration_ms=800,
                     started_at=now - timedelta(hours=1))
    await _seed_span(session_maker, uid, status="error", prompt_tokens=2, completion_tokens=1,
                     duration_ms=1200, started_at=now - timedelta(hours=2))
    # 他人数据不得混入
    await _seed_span(session_maker, uuid.uuid4(), prompt_tokens=9999, completion_tokens=9999)
    # 停止的 span 不计错误（也不影响 Token 断言）
    await _seed_span(
        session_maker, uid, status="stopped", prompt_tokens=0, completion_tokens=0,
        started_at=now - timedelta(hours=3),
    )

    r = await client.get("/api/v1/admin/metrics/overview?hours=24", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["cards"]["llm_calls"] == 3
    assert data["cards"]["prompt_tokens"] == 12
    assert data["cards"]["errors"] == 1
    assert data["cards"]["error_rate"] == pytest.approx(33.3, abs=0.1)
    assert data["cards"]["p95_ms"] is not None
    assert len(data["series"]) == 2 or len(data["series"]) == 3  # 小时桶数按落点


async def test_breakdown_sections(client, auth_headers, session_maker):
    uid = await _uid(client, auth_headers)
    aid = uuid.uuid4()
    now = datetime.now(UTC)
    await _seed_span(
        session_maker, uid, type="llm", model="qwen2.5:7b", agent_id=aid, prompt_tokens=10,
        completion_tokens=5, started_at=now - timedelta(hours=1),
    )
    await _seed_span(
        session_maker, uid, type="tool", name="kb_search", status="error", duration_ms=120,
        started_at=now - timedelta(hours=1),
    )
    await _seed_span(
        session_maker, uid, type="retrieval", name="kb检索", duration_ms=220,
        started_at=now - timedelta(hours=1),
    )
    await _seed_span(
        session_maker, uid, type="model_switch", model="qwen2.5:7b", duration_ms=1200,
        input={"from": "bge-m3", "to": "qwen2.5:7b"}, started_at=now - timedelta(hours=1),
    )
    r = await client.get("/api/v1/admin/metrics/overview?hours=24", headers=auth_headers)
    data = r.json()
    assert data["cards"]["tool_calls"] == 1 and data["cards"]["tool_error_rate"] == 100.0
    assert data["tools"][0] == {"tool": "kb_search", "calls": 1, "errors": 1, "avg_ms": 120.0}
    assert data["switches"][0]["to_model"] == "qwen2.5:7b" and data["switches"][0]["count"] == 1
    assert data["models"][0]["model"] == "qwen2.5:7b"
    assert data["retrieval"]["calls"] == 1 and data["retrieval"]["avg_ms"] == 220.0


async def test_http_section_merges_pending_and_db(client, auth_headers, session_maker):
    from app.observability.http_stats import collector

    collector.clear()
    await client.get("/health")
    assert await collector.flush(session_maker) == 1
    # 控制器裁定：中间件在 call_next 之后才记录，overview 请求处理期间尚未入桶。
    # 直接补记一条「已完成但未落库」的内存计数，验证 DB + pending 的合并口径。
    collector.record(200, 5.0)
    r = await client.get("/api/v1/admin/metrics/overview?hours=24", headers=auth_headers)
    data = r.json()
    assert data["http"]["requests"] == 2  # /health（已落库）+ 补记条目（内存待落）
    assert data["http"]["errors"] == 0
    assert len(data["http"]["series"]) == 1
    # overview 自身在响应返回后才被中间件计入内存桶，进一步佐证 pending 不含观测中的请求
    assert sum(row["requests"] for row in collector.pending().values()) == 2


async def test_overview_survives_ollama_down(client, auth_headers):
    from app.ai.model_manager import ModelManager

    class DownProvider(FakeProvider):
        async def list_loaded(self):
            raise RuntimeError("connection refused")

    app.state.model_manager = ModelManager(DownProvider())
    try:
        r = await client.get("/api/v1/admin/metrics/overview?hours=24", headers=auth_headers)
        assert r.status_code == 200 and "vram" in r.json()
    finally:
        del app.state.model_manager
