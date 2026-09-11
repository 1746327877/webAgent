from app.ai.deps import get_provider
from app.main import app
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "辅导员",
    "system_prompt": "你是{{agent.name}}，今天是 {{today}}",
    "model_config": {"model": "qwen2.5:7b-instruct-q4_K_M", "temperature": 0.3, "history_rounds": 3},
    "tags": [],
    "examples": [],
}


async def test_session_with_agent_uses_config(client, auth_headers):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    s = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()
    assert s["agent_id"] == agent["id"]

    provider = FakeProvider([("token", {"delta": "好"})])
    app.dependency_overrides[get_provider] = lambda: provider
    # 关闭标题任务干扰
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    assert "event: done" in r.text

    req = provider.last_request
    assert req.model == "qwen2.5:7b-instruct-q4_K_M"
    assert req.temperature == 0.3
    assert req.messages[0]["role"] == "system"
    assert "辅导员" in req.messages[0]["content"]

    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    assert msgs[1]["agent_id"] == agent["id"]
    assert msgs[1]["agent_version"] == 1


async def test_session_without_agent_has_no_system_message(client, auth_headers):
    s = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    provider = FakeProvider([("token", {"delta": "x"})])
    app.dependency_overrides[get_provider] = lambda: provider
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    assert provider.last_request.messages[0]["role"] == "user"


async def test_session_agent_validation(client, auth_headers):
    from tests.test_sessions_api import make_user

    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    other = await make_user(client, "bob")
    r = await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=other)
    assert r.status_code == 404

    await client.patch(
        f"/api/v1/agents/{agent['id']}", json={"status": "archived"}, headers=auth_headers
    )
    r2 = await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)
    assert r2.status_code == 422
