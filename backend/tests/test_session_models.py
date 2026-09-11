import uuid

from sqlalchemy import select

from app.models import Message, Session


async def test_session_with_message_roundtrip(session_maker):
    async with session_maker() as db:
        uid = uuid.uuid4()
        from app.core.security import hash_password
        from app.models import User

        db.add(
            User(
                id=uid,
                username="alice",
                email="alice@example.com",
                password_hash=hash_password("Passw0rd!"),
            )
        )
        await db.flush()
        s = Session(user_id=uid)
        db.add(s)
        await db.flush()
        m = Message(session_id=s.id, role="assistant", blocks=[{"type": "text", "content": "hi"}])
        db.add(m)
        await db.commit()

        got = await db.scalar(select(Message).where(Message.id == m.id))
        assert got is not None
        assert got.blocks == [{"type": "text", "content": "hi"}]
        assert got.status == "done"
        assert got.rating is None
