import asyncio
import uuid

from sqlalchemy import select

from app.ai.deps import get_provider
from app.main import app
from app.models import Session
from app.services.title_service import generate_title
from tests.fake_provider import FakeProvider


async def test_generate_title_unit(client, auth_headers, session_maker):
    sid = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()["id"]
    provider = FakeProvider([("token", {"delta": "关于Java的学习"})])
    await generate_title(session_maker, provider, uuid.UUID(sid), "Java 怎么学比较好", "Java 怎么学比较好")
    async with session_maker() as db:
        s = await db.get(Session, sid)
        assert s.title == "关于Java的学习"


async def test_generate_title_fallback_on_error(client, auth_headers, session_maker):
    sid = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()["id"]
    provider = FakeProvider([("token", {"delta": "x"})], raise_after=0)
    await generate_title(session_maker, provider, uuid.UUID(sid), "这是一段很长的用户问题用来做回退标题截断", "fallback")
    async with session_maker() as db:
        s = await db.get(Session, sid)
        assert s.title == "fallback"


async def test_title_generated_after_first_message(client, auth_headers, session_maker):
    app.dependency_overrides[get_provider] = lambda: FakeProvider([("token", {"delta": "标题X"})])
    sid = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()["id"]
    await client.post(
        f"/api/v1/sessions/{sid}/messages", json={"content": "随便问"}, headers=auth_headers
    )
    title = "新对话"
    for _ in range(40):
        await asyncio.sleep(0.05)
        async with session_maker() as db:
            title = (await db.scalar(select(Session.title).where(Session.id == sid))) or title
        if title != "新对话":
            break
    assert title == "标题X"
