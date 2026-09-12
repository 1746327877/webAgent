import uuid

from app.ai.deps import get_provider
from app.main import app
from tests.fake_provider import FakeProvider


async def _two_agents(client, auth_headers):
    a = (await client.post("/api/v1/agents", json={"name": "甲", "system_prompt": "", "model_config": {"model": "ma"}, "tags": [], "examples": []}, headers=auth_headers)).json()
    b = (await client.post("/api/v1/agents", json={"name": "乙", "system_prompt": "", "model_config": {"model": "mb"}, "tags": [], "examples": []}, headers=auth_headers)).json()
    return a, b


async def test_relay_creates_second_assistant(client, auth_headers, session_maker):
    a, b = await _two_agents(client, auth_headers)
    s = (await client.post("/api/v1/sessions", json={"agent_id": a["id"]}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    provider = FakeProvider([[("token", {"delta": "A答"})], [("token", {"delta": "B答"})]])
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "问题", "mentions": [b["id"]]},
        headers=auth_headers,
    )
    body = r.text
    assert body.count("event: message_start") == 2
    assert "A答" in body and "B答" in body
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    assistants = [m for m in msgs if m["role"] == "assistant"]
    assert [m["agent_id"] for m in assistants] == [a["id"], b["id"]]
    # 第二回合请求带接力指令与上下文
    second = provider.requests[-1].messages
    assert any("接力" in m.get("content", "") or "补充" in m.get("content", "") for m in second if m["role"] == "system")
    assert any("A答" in m.get("content", "") for m in second if m["role"] == "assistant")


async def test_relay_invalid_mention_emits_error(client, auth_headers):
    a, _ = await _two_agents(client, auth_headers)
    s = (await client.post("/api/v1/sessions", json={"agent_id": a["id"]}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    app.dependency_overrides[get_provider] = lambda: FakeProvider([("token", {"delta": "A"})])
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "hi", "mentions": [str(uuid.uuid4())]},
        headers=auth_headers,
    )
    assert "event: error" in r.text and "无法接力" in r.text
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    assert len([m for m in msgs if m["role"] == "assistant"]) == 1


async def test_mentions_max_two(client, auth_headers):
    a, b = await _two_agents(client, auth_headers)
    s = (await client.post("/api/v1/sessions", json={"agent_id": a["id"]}, headers=auth_headers)).json()
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "hi", "mentions": [a["id"], b["id"], a["id"]]},
        headers=auth_headers,
    )
    assert r.status_code == 422
