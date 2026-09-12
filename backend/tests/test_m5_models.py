from datetime import UTC, datetime

from sqlalchemy import select


async def test_http_stat_roundtrip(session_maker):
    from app.models import HttpStat

    async with session_maker() as db:
        db.add(
            HttpStat(
                bucket=datetime.now(UTC).replace(second=0, microsecond=0),
                requests=3,
                errors=1,
                duration_sum_ms=45,
                duration_max_ms=30,
            )
        )
        await db.commit()
        row = (await db.scalars(select(HttpStat))).first()
    assert row is not None and row.requests == 3 and row.errors == 1


async def test_alert_rule_and_event_roundtrip(session_maker):
    from app.models import AlertEvent, AlertRule, User

    async with session_maker() as db:
        user = User(
            username="alert_u", email="alert@example.com", password_hash="x"
        )
        db.add(user)
        await db.flush()
        rule = AlertRule(
            owner_id=user.id,
            metric="p95_latency",
            operator="gt",
            threshold=3000,
            window_minutes=5,
        )
        db.add(rule)
        await db.flush()
        db.add(AlertEvent(rule_id=rule.id, metric_value=4200.0, message="p95_latency 超阈值"))
        await db.commit()
        event = (await db.scalars(select(AlertEvent))).first()
        assert event is not None and event.rule_id == rule.id
        assert event.acknowledged is False
