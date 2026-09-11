import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models import Agent, AgentVersion, Message, Session, Tool, User


async def _user(db) -> User:
    u = User(
        id=uuid.uuid4(),
        username="alice",
        email="alice@example.com",
        password_hash=hash_password("Passw0rd!"),
    )
    db.add(u)
    await db.flush()
    return u


async def test_agent_full_fields_and_version(session_maker):
    async with session_maker() as db:
        u = await _user(db)
        agent = Agent(
            owner_id=u.id,
            name="代码专家",
            emoji="💻",
            description="review 代码",
            tags=["dev"],
            system_prompt="你是代码专家，今天是 {{today}}",
            model_config={"model": "qwen2.5:7b-instruct-q4_K_M", "temperature": 0.3},
            welcome_msg="贴代码给我",
            examples=["帮我 review 这段"],
        )
        db.add(agent)
        await db.flush()
        db.add(
            AgentVersion(
                agent_id=agent.id, version=1, snapshot={"name": "代码专家"}, published_by=u.id
            )
        )
        await db.commit()

        got = await db.scalar(select(Agent).where(Agent.id == agent.id))
        assert got.emoji == "💻" and got.tags == ["dev"] and got.examples == ["帮我 review 这段"]
        v = await db.scalar(select(AgentVersion).where(AgentVersion.agent_id == agent.id))
        assert v.version == 1 and v.snapshot["name"] == "代码专家"


async def test_tool_binding(session_maker):
    async with session_maker() as db:
        u = await _user(db)
        agent = Agent(owner_id=u.id, name="A", system_prompt="x", model_config={})
        db.add(agent)
        await db.flush()
        t = Tool(slug="time_now", name="当前时间", description="d", input_schema={}, category="system")
        db.add(t)
        await db.flush()
        from app.models import AgentTool

        db.add(AgentTool(agent_id=agent.id, tool_id=t.id, config={"timeout": 5}))
        await db.commit()
        got = await db.scalar(
            select(Tool).join(AgentTool, AgentTool.tool_id == Tool.id).where(AgentTool.agent_id == agent.id)
        )
        assert got.slug == "time_now"


async def test_messages_seq_strict_order(session_maker):
    """同一事务写入的两条消息 created_at 相同，但 seq 严格递增。"""
    async with session_maker() as db:
        u = await _user(db)
        s = Session(user_id=u.id)
        db.add(s)
        await db.flush()
        m1 = Message(session_id=s.id, role="user", blocks=[{"type": "text", "content": "一"}])
        m2 = Message(session_id=s.id, role="assistant", blocks=[{"type": "text", "content": "二"}])
        db.add_all([m1, m2])
        await db.commit()
        rows = (
            await db.scalars(select(Message).where(Message.session_id == s.id).order_by(Message.seq))
        ).all()
        assert [r.blocks[0]["content"] for r in rows] == ["一", "二"]
        assert rows[0].seq < rows[1].seq
