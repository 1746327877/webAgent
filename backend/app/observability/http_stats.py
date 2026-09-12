from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert


class HttpStatsCollector:
    """内存分钟桶：中间件零数据库开销；定时 flush 批量 upsert（设计 08.2）。"""

    def __init__(self) -> None:
        self._buckets: dict[datetime, dict] = {}

    def record(self, status_code: int, duration_ms: float) -> None:
        bucket = datetime.now(UTC).replace(second=0, microsecond=0)
        row = self._buckets.setdefault(
            bucket, {"requests": 0, "errors": 0, "duration_sum_ms": 0, "duration_max_ms": 0}
        )
        row["requests"] += 1
        if status_code >= 400:
            row["errors"] += 1
        ms = int(duration_ms)
        row["duration_sum_ms"] += ms
        row["duration_max_ms"] = max(row["duration_max_ms"], ms)

    def pending(self) -> dict[datetime, dict]:
        return dict(self._buckets)

    def clear(self) -> None:
        self._buckets.clear()

    def _merge(self, bucket: datetime, row: dict) -> None:
        target = self._buckets.setdefault(bucket, dict.fromkeys(row, 0))
        target["requests"] += row["requests"]
        target["errors"] += row["errors"]
        target["duration_sum_ms"] += row["duration_sum_ms"]
        target["duration_max_ms"] = max(target["duration_max_ms"], row["duration_max_ms"])

    async def flush(self, session_factory=None) -> int:
        if not self._buckets:
            return 0
        rows, self._buckets = self._buckets, {}
        try:
            from app.core.db import SessionLocal
            from app.models import HttpStat

            factory = session_factory or SessionLocal
            async with factory() as db:
                for bucket, row in rows.items():
                    stmt = pg_insert(HttpStat).values(bucket=bucket, **row)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[HttpStat.bucket],
                        set_={
                            "requests": HttpStat.requests + stmt.excluded.requests,
                            "errors": HttpStat.errors + stmt.excluded.errors,
                            "duration_sum_ms": HttpStat.duration_sum_ms + stmt.excluded.duration_sum_ms,
                            "duration_max_ms": func.greatest(
                                HttpStat.duration_max_ms, stmt.excluded.duration_max_ms
                            ),
                        },
                    )
                    await db.execute(stmt)
                await db.commit()
        except Exception:  # noqa: BLE001 —— 落库失败把计数放回，下一轮重试
            for bucket, row in rows.items():
                self._merge(bucket, row)
            return 0
        return len(rows)


collector = HttpStatsCollector()
