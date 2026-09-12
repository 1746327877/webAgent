from sqlalchemy import select


async def test_http_middleware_counts_and_flush_persists(client, auth_headers, session_maker):
    from app.models import HttpStat
    from app.observability.http_stats import collector

    collector.clear()
    await client.get("/health")
    pending = collector.pending()
    assert sum(row["requests"] for row in pending.values()) == 1
    assert await collector.flush(session_maker) == 1
    assert collector.pending() == {}
    async with session_maker() as db:
        row = (await db.scalars(select(HttpStat))).first()
    assert row is not None and row.requests == 1 and row.duration_sum_ms >= 0


async def test_flush_failure_keeps_counters():
    from app.observability.http_stats import HttpStatsCollector

    col = HttpStatsCollector()
    col.record(200, 12.0)

    class BrokenFactory:
        def __call__(self):
            raise RuntimeError("db down")

    assert await col.flush(BrokenFactory()) == 0
    assert sum(r["requests"] for r in col.pending().values()) == 1
