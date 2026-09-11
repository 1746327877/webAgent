import uuid

from app.ai.deps import get_provider
from app.ai.runtime import CANCEL_FLAGS
from app.main import app
from app.models import Message
from tests.fake_provider import FakeProvider


def _override(provider):
    app.dependency_overrides[get_provider] = lambda: provider


async def _session_with_history(client, auth_headers, session_maker):
    sid = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()["id"]
    async with session_maker() as db:
        u = Message(session_id=sid, role="user", blocks=[{"type": "text", "content": "旧问题"}])
        db.add(u)
        # 独立事务提交：使 created_at 严格递增，排序稳定（与 runtime 的修复一致）
        await db.commit()
        await db.refresh(u)
        a = Message(
            session_id=sid,
            role="assistant",
            blocks=[{"type": "text", "content": "旧回答"}],
            status="done",
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return sid, str(u.id), str(a.id)


async def test_regenerate_assistant_replaces(client, auth_headers, session_maker):
    sid, _uid, aid = await _session_with_history(client, auth_headers, session_maker)
    _override(FakeProvider([("token", {"delta": "新回答"})]))
    r = await client.post(
        f"/api/v1/sessions/{sid}/regenerate", json={"message_id": aid}, headers=auth_headers
    )
    assert r.status_code == 200 and "event: done" in r.text
    msgs = (await client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["id"] != aid
    assert msgs[1]["blocks"] == [{"type": "text", "content": "新回答"}]


async def test_edit_user_message_truncates_and_regenerates(client, auth_headers, session_maker):
    sid, uid, _aid = await _session_with_history(client, auth_headers, session_maker)
    r = await client.patch(
        f"/api/v1/messages/{uid}",
        json={"blocks": [{"type": "text", "content": "新问题"}]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    msgs = (await client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)).json()
    assert [m["id"] for m in msgs] == [uid]  # 旧助手被截断

    _override(FakeProvider([("token", {"delta": "回答2"})]))
    r2 = await client.post(
        f"/api/v1/sessions/{sid}/regenerate", json={"message_id": uid}, headers=auth_headers
    )
    assert "event: done" in r2.text
    msgs = (await client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]


async def test_stop_sets_cancel_flag(client, auth_headers, session_maker):
    _sid, _uid, aid = await _session_with_history(client, auth_headers, session_maker)
    async with session_maker() as db:
        m = await db.get(Message, aid)
        m.status = "streaming"
        await db.commit()
    r = await client.post(f"/api/v1/messages/{aid}/stop", headers=auth_headers)
    assert r.status_code == 200
    assert CANCEL_FLAGS.pop(uuid.UUID(aid), False) is True


async def test_rating_only_on_assistant(client, auth_headers, session_maker):
    _sid, uid, aid = await _session_with_history(client, auth_headers, session_maker)
    ok = await client.patch(f"/api/v1/messages/{aid}", json={"rating": 1}, headers=auth_headers)
    assert ok.status_code == 200 and ok.json()["rating"] == 1
    bad = await client.patch(f"/api/v1/messages/{uid}", json={"rating": 1}, headers=auth_headers)
    assert bad.status_code == 422


async def test_ownership_on_message_ops(client, auth_headers, session_maker):
    from tests.test_sessions_api import make_user

    sid, uid, aid = await _session_with_history(client, auth_headers, session_maker)
    other = await make_user(client, "bob")
    assert (await client.post(f"/api/v1/messages/{aid}/stop", headers=other)).status_code == 404
    assert (
        await client.patch(f"/api/v1/messages/{uid}", json={"rating": 1}, headers=other)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/sessions/{sid}/regenerate", json={"message_id": aid}, headers=other
        )
    ).status_code == 404
