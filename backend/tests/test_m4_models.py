async def test_model_event_roundtrip(session_maker):
    from sqlalchemy import select

    from app.models import ModelEvent

    async with session_maker() as db:
        db.add(
            ModelEvent(
                model="qwen2.5:7b",
                action="load",
                trigger="auto_switch",
                duration_ms=1234,
                vram_before_mb=0,
                vram_after_mb=6789,
            )
        )
        await db.commit()
        row = (await db.scalars(select(ModelEvent))).first()
        assert row.action == "load" and row.duration_ms == 1234
