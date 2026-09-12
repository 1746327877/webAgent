from app.ai.deps import get_provider
from app.ai.model_manager import ModelManager
from app.main import app
from tests.fake_provider import FakeProvider


async def test_switching_events_emitted(client, auth_headers, session_maker):
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "SW", "system_prompt": "", "model_config": {"model": "m-switch"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    provider = FakeProvider([("token", {"delta": "x"})])
    app.dependency_overrides[get_provider] = lambda: provider
    app.state.model_manager = ModelManager(provider, session_factory=session_maker)
    try:
        r = await client.post(
            f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
        )
        body = r.text
        assert "event: model_switching" in body
        assert '"stage": "start"' in body and '"stage": "done"' in body
        assert '"to": "m-switch"' in body
        assert app.state.model_manager.current == "m-switch"
        # 事件顺序：message_start → model_switching → token
        assert body.index("message_start") < body.index("model_switching") < body.index("event: token")
    finally:
        del app.state.model_manager


async def test_same_model_no_switching_event(client, auth_headers, session_maker):
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "SW2", "system_prompt": "", "model_config": {"model": "m-stay"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    provider = FakeProvider([("token", {"delta": "x"})])
    app.dependency_overrides[get_provider] = lambda: provider
    mm = ModelManager(provider, session_factory=session_maker)
    mm._current = "m-stay"
    app.state.model_manager = mm
    try:
        r = await client.post(
            f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
        )
        assert "event: model_switching" not in r.text
    finally:
        del app.state.model_manager
