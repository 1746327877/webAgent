from app.ai.deps import get_provider
from app.main import app
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "代码专家",
    "emoji": "💻",
    "description": "review 代码",
    "tags": ["dev"],
    "system_prompt": "你是{{agent.name}}，今天是 {{today}}，用户 {{user.name}}",
    "model_config": {"model": "qwen2.5:7b-instruct-q4_K_M", "temperature": 0.3},
    "welcome_msg": "贴代码给我",
    "examples": ["帮我 review 这段"],
}


async def test_create_agent_and_variables(client, auth_headers):
    r = await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "代码专家" and data["status"] == "draft"
    assert data["model_config"]["model"] == "qwen2.5:7b-instruct-q4_K_M"
    assert set(data["variables"]) == {"agent.name", "today", "user.name"}


async def test_model_config_validation(client, auth_headers):
    bad = {**AGENT, "model_config": {"model": "m", "temperature": 2.5}}
    r = await client.post("/api/v1/agents", json=bad, headers=auth_headers)
    assert r.status_code == 422


async def test_list_update_archive_delete(client, auth_headers):
    aid = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()["id"]
    lst = await client.get("/api/v1/agents", headers=auth_headers)
    assert [a["id"] for a in lst.json()] == [aid]

    r = await client.patch(
        f"/api/v1/agents/{aid}", json={"name": "改名", "status": "archived"}, headers=auth_headers
    )
    assert r.json()["name"] == "改名" and r.json()["status"] == "archived"

    r2 = await client.patch(
        f"/api/v1/agents/{aid}",
        json={"model_config": {"model": "m2"}},
        headers=auth_headers,
    )
    assert r2.json()["model_config"]["model"] == "m2"

    d = await client.delete(f"/api/v1/agents/{aid}", headers=auth_headers)
    assert d.status_code == 204


async def test_themes_no_cross_user(client, auth_headers):
    from tests.test_sessions_api import make_user

    aid = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()["id"]
    other = await make_user(client, "bob")
    assert (await client.get(f"/api/v1/agents/{aid}", headers=other)).status_code == 404
    assert (await client.patch(f"/api/v1/agents/{aid}", json={}, headers=other)).status_code == 404


async def test_update_tools_and_tool_slugs(client, auth_headers, session_maker):
    from app.ai.tools import sync_tools

    async with session_maker() as db:
        await sync_tools(db)

    aid = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()["id"]
    r = await client.put(
        f"/api/v1/agents/{aid}/tools", json={"slugs": ["time_now"]}, headers=auth_headers
    )
    assert r.status_code == 200 and r.json()["slugs"] == ["time_now"]
    detail = await client.get(f"/api/v1/agents/{aid}", headers=auth_headers)
    assert detail.json()["tool_slugs"] == ["time_now"]
    # 替换语义
    r2 = await client.put(
        f"/api/v1/agents/{aid}/tools", json={"slugs": []}, headers=auth_headers
    )
    assert r2.json()["slugs"] == []


async def test_set_agent_kbs_and_kb_bindings_in_out(client, auth_headers):
    kb = (await client.post("/api/v1/kbs", json={"name": "KB1"}, headers=auth_headers)).json()
    aid = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()["id"]
    r = await client.put(
        f"/api/v1/agents/{aid}/kbs",
        json={"bindings": [{"kb_id": kb["id"], "top_k": 3}]},
        headers=auth_headers,
    )
    assert r.status_code == 200 and len(r.json()["bindings"]) == 1
    bound = r.json()["bindings"][0]
    assert bound["kb_id"] == kb["id"]
    assert bound["name"] == "KB1"
    assert bound["top_k"] == 3
    assert bound["score_threshold"] == 0.3
    detail = (await client.get(f"/api/v1/agents/{aid}", headers=auth_headers)).json()
    assert detail["kb_bindings"][0]["kb_id"] == kb["id"]
    assert detail["kb_bindings"][0]["name"] == "KB1"
    assert detail["kb_bindings"][0]["top_k"] == 3
    assert detail["kb_bindings"][0]["score_threshold"] == 0.3

    # 自定义阈值透传
    r1 = await client.put(
        f"/api/v1/agents/{aid}/kbs",
        json={"bindings": [{"kb_id": kb["id"], "top_k": 3, "score_threshold": 0.5}]},
        headers=auth_headers,
    )
    assert r1.json()["bindings"][0]["score_threshold"] == 0.5

    # 替换语义
    r2 = await client.put(f"/api/v1/agents/{aid}/kbs", json={"bindings": []}, headers=auth_headers)
    assert r2.json()["bindings"] == []

    # 他人 KB → 404：bob 拥有自己的 agent，但 kb 属于 alice，命中 KB 归属校验
    from tests.test_sessions_api import make_user

    other = await make_user(client, "bob")
    bob_aid = (await client.post("/api/v1/agents", json=AGENT, headers=other)).json()["id"]
    r3 = await client.put(
        f"/api/v1/agents/{bob_aid}/kbs",
        json={"bindings": [{"kb_id": kb["id"]}]},
        headers=other,
    )
    assert r3.status_code == 404
    assert r3.json()["detail"] == "知识库不存在"


async def test_models_endpoint(client, auth_headers):
    class P(FakeProvider):
        async def list_available(self):
            from app.ai.providers.base import ModelInfo

            return [ModelInfo(name="qwen2.5:7b-instruct-q4_K_M", size_mb=4700.0)]

    app.dependency_overrides[get_provider] = lambda: P()
    r = await client.get("/api/v1/models", headers=auth_headers)
    assert r.status_code == 200
    names = [m["name"] for m in r.json()]
    assert "qwen2.5:7b-instruct-q4_K_M" in names
