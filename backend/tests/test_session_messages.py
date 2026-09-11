import json
import uuid

from sqlalchemy import select

from app.ai.deps import get_provider
from app.main import app
from app.models import Message, Session
from tests.fake_provider import FakeProvider


def _override(provider):
    app.dependency_overrides[get_provider] = lambda: provider


async def test_send_message_persists_and_streams(client, auth_headers, session_maker):
    session = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    _override(
        FakeProvider(
            [
                ("token", {"delta": "你"}),
                ("token", {"delta": "好"}),
                ("usage", {"prompt_tokens": 3, "completion_tokens": 2, "total_ms": 9, "first_token_ms": None}),
            ]
        )
    )
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "hi"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.text
    assert "event: message_start" in body
    assert body.count("event: token") == 2
    assert "event: done" in body
    assert '"prompt_tokens": 3' in body

    msgs = (await client.get(f"/api/v1/sessions/{session['id']}/messages", headers=auth_headers)).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["blocks"] == [{"type": "text", "content": "hi"}]
    assert msgs[1]["blocks"] == [{"type": "text", "content": "你好"}]
    assert msgs[1]["status"] == "done"
    assert msgs[1]["usage"]["prompt_tokens"] == 3

    async with session_maker() as db:
        s = await db.get(Session, session["id"])
        assert s.last_message_at is not None
        assert s.title  # 标题可能已被异步生成替换，只断言非空


async def test_thinking_block_accumulates(client, auth_headers):
    session = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    _override(
        FakeProvider(
            [
                ("thinking", {"delta": "推理"}),
                ("thinking", {"delta": "中"}),
                ("token", {"delta": "答案"}),
            ]
        )
    )
    await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "hi"},
        headers=auth_headers,
    )
    msgs = (await client.get(f"/api/v1/sessions/{session['id']}/messages", headers=auth_headers)).json()
    blocks = msgs[1]["blocks"]
    assert blocks[0]["type"] == "thinking" and blocks[0]["content"] == "推理中"
    assert blocks[0]["duration_ms"] is not None
    assert blocks[1] == {"type": "text", "content": "答案"}


async def test_provider_error_marks_message(client, auth_headers):
    session = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    _override(FakeProvider([("token", {"delta": "部分"})], raise_after=1))
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "hi"},
        headers=auth_headers,
    )
    assert "event: error" in r.text
    assert "event: done" in r.text
    msgs = (await client.get(f"/api/v1/sessions/{session['id']}/messages", headers=auth_headers)).json()
    assert msgs[1]["status"] == "error"
    assert msgs[1]["error"]


async def test_cancel_flag_stops_generation(client, auth_headers, session_maker, monkeypatch):
    from app.ai.runtime import CANCEL_FLAGS, run_generation
    from app.models.user import User
    from app.services import session_service

    session_data = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    provider = FakeProvider([("token", {"delta": str(i)}) for i in range(20)])

    async with session_maker() as db:
        user = (await db.scalars(select(User))).first()
        session = await session_service.get_owned_session(db, user, session_data["id"])
        gen = run_generation(db, session, provider, user_content="hi")
        first = await gen.__anext__()
        msg_id = json.loads(first.split("data: ", 1)[1])["message_id"]
        CANCEL_FLAGS[uuid.UUID(msg_id)] = True
        rest = [chunk async for chunk in gen]

    assert "event: message_start" in first
    assert not any("event: token" in c for c in rest)  # 取消后不再出 token
    assert any("event: done" in c for c in rest)
    async with session_maker() as db:
        m = await db.get(Message, uuid.UUID(msg_id))
        assert m.status == "stopped"


async def test_old_chat_endpoint_removed(client, auth_headers):
    r = await client.post("/api/v1/chat/stream", json={"model": "x", "messages": []}, headers=auth_headers)
    assert r.status_code == 404


async def test_send_message_requires_auth(client):
    r = await client.post(f"/api/v1/sessions/{uuid.uuid4()}/messages", json={"content": "hi"})
    assert r.status_code == 401


async def test_send_message_sse_headers(client, auth_headers):
    session = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    _override(FakeProvider([("token", {"delta": "ok"})]))
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "hi"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["x-accel-buffering"] == "no"


async def test_history_no_dup_and_order(client, auth_headers):
    session = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    # Task 7 起首条消息会触发异步标题任务并复用同一 provider；
    # 先把标题改为非默认值，标题守卫不会触发，last_request 保持在第二轮请求上
    await client.patch(
        f"/api/v1/sessions/{session['id']}", json={"title": "t"}, headers=auth_headers
    )
    provider = FakeProvider([("token", {"delta": "答"})])
    _override(provider)

    for content in ("hi", "second"):
        r = await client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            json={"content": content},
            headers=auth_headers,
        )
        assert r.status_code == 200

    assert provider.last_request is not None
    messages = provider.last_request.messages
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert [m["content"] for m in messages] == ["hi", "答", "second"]
