import json

from sqlalchemy import func, select

from app.models.session import Message, Session
from app.models.user import User


def test_flagship_messages_cover_all_demo_blocks():
    from scripts.seed_demo_sessions import build_flagship_messages

    messages = build_flagship_messages()
    assert messages[0]["role"] == "user"
    assert [m["role"] for m in messages].count("assistant") >= 2  # 主回答 + 接力回答
    types = [block["type"] for message in messages for block in message["blocks"]]
    for expected in ("thinking", "tool_call", "tool_result", "citation", "text"):
        assert expected in types


def test_flagship_thinking_duration_and_json_roundtrip():
    from scripts.seed_demo_sessions import build_flagship_messages

    messages = build_flagship_messages()
    thinking = [
        block for message in messages for block in message["blocks"] if block["type"] == "thinking"
    ]
    assert thinking and all(block["duration_ms"] > 0 for block in thinking)
    dumped = json.dumps(messages, ensure_ascii=False)
    assert "线程池" in dumped  # 直接写入 JSONB：可序列化且中文不转义


async def test_seed_demo_sessions_main_is_idempotent(session_maker, monkeypatch):
    from scripts import seed_demo_sessions

    monkeypatch.setattr(seed_demo_sessions, "SessionLocal", session_maker)

    async with session_maker() as db:
        db.add(User(username="demo", email="demo@example.com", password_hash="x", role="admin"))
        await db.commit()

    await seed_demo_sessions.main()

    async with session_maker() as db:
        sessions_first = await db.scalar(select(func.count()).select_from(Session))
        messages_first = await db.scalar(select(func.count()).select_from(Message))

    assert sessions_first == 1001  # 1000 条压力会话 + 1 条旗舰会话
    assert messages_first == 5  # 压力 demo 会话 2 条 + 旗舰会话 3 条

    await seed_demo_sessions.main()

    async with session_maker() as db:
        sessions_second = await db.scalar(select(func.count()).select_from(Session))
        messages_second = await db.scalar(select(func.count()).select_from(Message))
        flagship_count = await db.scalar(
            select(func.count())
            .select_from(Session)
            .where(Session.title == "旗舰演示：Java 并发与 RAG")
        )
        flagship = await db.scalar(
            select(Session).where(Session.title == "旗舰演示：Java 并发与 RAG")
        )
        assert flagship is not None
        flagship_messages = await db.scalar(
            select(func.count()).select_from(Message).where(Message.session_id == flagship.id)
        )

    assert sessions_second == sessions_first  # 重跑不追加会话
    assert messages_second == messages_first  # 重跑不追加消息
    assert flagship_count == 1
    assert flagship_messages == 3
