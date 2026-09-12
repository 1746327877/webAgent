from app.schemas.agent import ModelConfig


def test_model_config_rejects_empty_model():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ModelConfig(model="")
    with pytest.raises(ValidationError):
        ModelConfig(model="m", provider="openai")


async def test_usage_merges_across_rounds(client, auth_headers, session_maker):
    from app.ai.deps import get_provider
    from app.main import app
    from tests.fake_provider import FakeProvider

    agent = {
        "name": "U",
        "system_prompt": "",
        "model_config": {"model": "m"},
        "tags": [],
        "examples": [],
    }
    aid = (await client.post("/api/v1/agents", json=agent, headers=auth_headers)).json()["id"]
    s = (await client.post("/api/v1/sessions", json={"agent_id": aid}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    provider = FakeProvider(
        [
            [
                ("tool_call", {"id": "c1", "name": "time_now", "args": {}}),
                ("usage", {"prompt_tokens": 10, "completion_tokens": 1, "total_ms": 100}),
            ],
            [
                ("token", {"delta": "ok"}),
                ("usage", {"prompt_tokens": 20, "completion_tokens": 2, "total_ms": 50}),
            ],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    usage = msgs[1]["usage"]
    assert usage["prompt_tokens"] == 30 and usage["completion_tokens"] == 3
    assert usage["total_ms"] == 150


async def test_set_tools_deduplicates(client, auth_headers, session_maker):
    from app.ai.tools import sync_tools

    async with session_maker() as db:
        await sync_tools(db)
    agent = {
        "name": "D",
        "system_prompt": "",
        "model_config": {"model": "m"},
        "tags": [],
        "examples": [],
    }
    aid = (await client.post("/api/v1/agents", json=agent, headers=auth_headers)).json()["id"]
    r = await client.put(
        f"/api/v1/agents/{aid}/tools",
        json={"slugs": ["time_now", "time_now"]},
        headers=auth_headers,
    )
    assert r.status_code == 200 and r.json()["slugs"] == ["time_now"]
