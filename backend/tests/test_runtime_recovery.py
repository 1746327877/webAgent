from app.ai.runtime import recover_stale_streaming
from app.models import Message, Session
from app.models.user import User


async def test_recover_stale_streaming_marks_error(session_maker):
    async with session_maker() as db:
        user = User(username="recover", email="recover@example.com", password_hash="x")
        db.add(user)
        await db.commit()
        session = Session(user_id=user.id, title="中断的会话")
        db.add(session)
        await db.commit()
        stale = Message(session_id=session.id, role="assistant", blocks=[], status="streaming")
        done = Message(session_id=session.id, role="assistant", blocks=[], status="done")
        db.add_all([stale, done])
        await db.commit()
        stale_id, done_id = stale.id, done.id

    assert await recover_stale_streaming(session_maker) == 1

    async with session_maker() as db:
        fixed = await db.get(Message, stale_id)
        untouched = await db.get(Message, done_id)
        assert fixed is not None and fixed.status == "error"
        assert fixed.error == "生成中断"
        assert untouched is not None and untouched.status == "done"
