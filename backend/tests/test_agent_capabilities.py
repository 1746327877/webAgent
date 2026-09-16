from app.services import mcp_service
from tests.test_agents_api import AGENT

MCP_CONFIG = {"name": "Baidu Search", "transport": "http", "url": "https://mcp.example.com/mcp"}


async def _make_agent(client, auth_headers) -> str:
    return (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()["id"]


async def _make_mcp_with_tools(client, auth_headers, monkeypatch) -> str:
    sid = (
        await client.post("/api/v1/mcp-servers", json=MCP_CONFIG, headers=auth_headers)
    ).json()["id"]

    async def fake_probe(config):
        return mcp_service.ProbeResult(
            ok=True,
            tools=[
                {
                    "name": "web_search",
                    "description": "网页搜索",
                    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                }
            ],
            latency_ms=5,
        )

    monkeypatch.setattr(mcp_service, "probe", fake_probe)
    await client.post(f"/api/v1/mcp-servers/{sid}/test", headers=auth_headers)
    return sid


async def test_set_and_get_skills(client, auth_headers):
    aid = await _make_agent(client, auth_headers)
    assert (await client.get(f"/api/v1/agents/{aid}", headers=auth_headers)).json()["skill_slugs"] == []

    r = await client.put(
        f"/api/v1/agents/{aid}/skills", json={"slugs": ["relay", "kb_qa"]}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["slugs"] == ["kb_qa", "relay"]
    body = (await client.get(f"/api/v1/agents/{aid}", headers=auth_headers)).json()
    assert body["skill_slugs"] == ["kb_qa", "relay"]


async def test_unknown_skill_rejected(client, auth_headers):
    aid = await _make_agent(client, auth_headers)
    r = await client.put(
        f"/api/v1/agents/{aid}/skills", json={"slugs": ["nope"]}, headers=auth_headers
    )
    assert r.status_code == 400


async def test_set_and_get_mcp_tools(client, auth_headers, monkeypatch):
    aid = await _make_agent(client, auth_headers)
    sid = await _make_mcp_with_tools(client, auth_headers, monkeypatch)
    r = await client.put(
        f"/api/v1/agents/{aid}/mcp-tools",
        json={"tools": [{"mcp_server_id": sid, "tool_name": "web_search"}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["tools"] == [{"mcp_server_id": sid, "tool_name": "web_search"}]
    body = (await client.get(f"/api/v1/agents/{aid}", headers=auth_headers)).json()
    assert body["mcp_tools"] == [{"mcp_server_id": sid, "tool_name": "web_search"}]


async def test_unknown_mcp_tool_rejected(client, auth_headers, monkeypatch):
    aid = await _make_agent(client, auth_headers)
    sid = await _make_mcp_with_tools(client, auth_headers, monkeypatch)
    r = await client.put(
        f"/api/v1/agents/{aid}/mcp-tools",
        json={"tools": [{"mcp_server_id": sid, "tool_name": "nope"}]},
        headers=auth_headers,
    )
    assert r.status_code == 400


async def test_mcp_tool_from_other_user_not_allowed(client, auth_headers, monkeypatch):
    from tests.test_sessions_api import make_user

    aid = await _make_agent(client, auth_headers)
    sid = await _make_mcp_with_tools(client, auth_headers, monkeypatch)
    other = await make_user(client, "bob")
    # bob 访问 alice 的 agent → 404（归属校验先于 MCP 校验）
    r = await client.put(
        f"/api/v1/agents/{aid}/mcp-tools",
        json={"tools": [{"mcp_server_id": sid, "tool_name": "web_search"}]},
        headers=other,
    )
    assert r.status_code == 404


async def test_publish_snapshot_and_rollback_include_capabilities(client, auth_headers, monkeypatch):
    aid = await _make_agent(client, auth_headers)
    sid = await _make_mcp_with_tools(client, auth_headers, monkeypatch)
    await client.put(f"/api/v1/agents/{aid}/skills", json={"slugs": ["kb_qa"]}, headers=auth_headers)
    await client.put(
        f"/api/v1/agents/{aid}/mcp-tools",
        json={"tools": [{"mcp_server_id": sid, "tool_name": "web_search"}]},
        headers=auth_headers,
    )

    version = (
        await client.post(f"/api/v1/agents/{aid}/publish", headers=auth_headers)
    ).json()["version"]

    # 清空能力后再回滚，验证快照真的带上了 skill / mcp
    await client.put(f"/api/v1/agents/{aid}/skills", json={"slugs": []}, headers=auth_headers)
    await client.put(f"/api/v1/agents/{aid}/mcp-tools", json={"tools": []}, headers=auth_headers)

    body = (
        await client.post(
            f"/api/v1/agents/{aid}/rollback", json={"version": version}, headers=auth_headers
        )
    ).json()
    assert body["skill_slugs"] == ["kb_qa"]
    assert body["mcp_tools"] == [{"mcp_server_id": sid, "tool_name": "web_search"}]
