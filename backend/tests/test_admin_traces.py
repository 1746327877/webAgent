from app.ai.deps import get_provider
from app.main import app
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "追踪",
    "system_prompt": "",
    "model_config": {"model": "m-trace"},
    "tags": [],
    "examples": [],
}


async def _trace_session(client, auth_headers):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    s = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    provider = FakeProvider(
        [("token", {"delta": "答案"}), ("usage", {"prompt_tokens": 7, "completion_tokens": 3})]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    return s, msgs


async def test_trace_endpoint_returns_span_tree(client, auth_headers):
    _s, msgs = await _trace_session(client, auth_headers)
    mid = msgs[1]["id"]
    r = await client.get(f"/api/v1/admin/messages/{mid}/spans", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["trace_id"] == mid
    assert [sp["type"] for sp in data["spans"]] == ["llm"]
    span = data["spans"][0]
    assert span["prompt_tokens"] == 7 and span["model"] == "m-trace"
    assert span["input"]["messages"][-1]["content"] == "hi"

    from tests.test_sessions_api import make_user

    other = await make_user(client, "bob")
    assert (await client.get(f"/api/v1/admin/messages/{mid}/spans", headers=other)).status_code == 404


async def test_span_log_filters(client, auth_headers):
    _s, _msgs = await _trace_session(client, auth_headers)
    llm = (await client.get("/api/v1/admin/spans?type=llm", headers=auth_headers)).json()
    assert llm["total"] == 1 and llm["items"][0]["type"] == "llm"
    tool = (await client.get("/api/v1/admin/spans?type=tool", headers=auth_headers)).json()
    assert tool["total"] == 0
    bad = (
        await client.get("/api/v1/admin/spans?type=llm&status=error", headers=auth_headers)
    ).json()
    assert bad["total"] == 0


async def test_span_csv_export_stream(client, auth_headers):
    _s, _msgs = await _trace_session(client, auth_headers)
    r = await client.get("/api/v1/admin/spans/export.csv?type=llm", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "started_at,type,name,status" in r.text
    assert "llm" in r.text and "m-trace" in r.text
