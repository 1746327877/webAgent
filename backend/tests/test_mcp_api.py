from app.services import mcp_service

HTTP_CONFIG = {
    "name": "百度搜索",
    "transport": "http",
    "url": "https://mcp.example.com/mcp",
    "headers": {"Authorization": "Bearer sk-test"},
}
STDIO_CONFIG = {
    "name": "本地文件",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    "env": {"FOO": "bar"},
}


async def test_create_list_update_delete(client, auth_headers):
    r = await client.post("/api/v1/mcp-servers", json=HTTP_CONFIG, headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "百度搜索" and data["transport"] == "http"
    assert data["headers"]["Authorization"] == "Bearer sk-test"
    assert data["status"] == "unknown" and data["tools"] == []
    sid = data["id"]

    lst = await client.get("/api/v1/mcp-servers", headers=auth_headers)
    assert [s["id"] for s in lst.json()] == [sid]

    upd = await client.patch(
        f"/api/v1/mcp-servers/{sid}",
        json={**HTTP_CONFIG, "name": "改名"},
        headers=auth_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "改名"

    assert (await client.delete(f"/api/v1/mcp-servers/{sid}", headers=auth_headers)).status_code == 204
    assert (await client.get("/api/v1/mcp-servers", headers=auth_headers)).json() == []


async def test_stdio_config_roundtrip(client, auth_headers):
    r = await client.post("/api/v1/mcp-servers", json=STDIO_CONFIG, headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["transport"] == "stdio"
    assert data["command"] == "npx"
    assert data["args"] == STDIO_CONFIG["args"]
    assert data["env"]["FOO"] == "bar"


async def test_duplicate_name_conflict(client, auth_headers):
    await client.post("/api/v1/mcp-servers", json=HTTP_CONFIG, headers=auth_headers)
    r = await client.post("/api/v1/mcp-servers", json=HTTP_CONFIG, headers=auth_headers)
    assert r.status_code == 409


async def test_transport_field_validation(client, auth_headers):
    # http 缺 url
    r = await client.post(
        "/api/v1/mcp-servers",
        json={"name": "a", "transport": "http"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    # http url 协议不对
    r = await client.post(
        "/api/v1/mcp-servers",
        json={"name": "b", "transport": "http", "url": "ftp://x"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    # stdio 缺 command
    r = await client.post(
        "/api/v1/mcp-servers",
        json={"name": "c", "transport": "stdio"},
        headers=auth_headers,
    )
    assert r.status_code == 422


async def test_cross_user_isolation(client, auth_headers):
    from tests.test_sessions_api import make_user

    sid = (await client.post("/api/v1/mcp-servers", json=HTTP_CONFIG, headers=auth_headers)).json()[
        "id"
    ]
    other = await make_user(client, "bob")
    assert (await client.get("/api/v1/mcp-servers", headers=other)).json() == []
    assert (
        await client.patch(
            f"/api/v1/mcp-servers/{sid}", json=HTTP_CONFIG, headers=other
        )
    ).status_code == 404
    assert (await client.delete(f"/api/v1/mcp-servers/{sid}", headers=other)).status_code == 404
    assert (await client.post(f"/api/v1/mcp-servers/{sid}/test", headers=other)).status_code == 404


async def test_probe_endpoint_does_not_persist(client, auth_headers, monkeypatch):
    captured: dict = {}

    async def fake_probe(config):
        captured["config"] = config
        return mcp_service.ProbeResult(
            ok=True, tools=[{"name": "web_search", "description": "搜索"}], latency_ms=42
        )

    monkeypatch.setattr(mcp_service, "probe", fake_probe)
    r = await client.post("/api/v1/mcp-servers/test", json=HTTP_CONFIG, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["tools"][0]["name"] == "web_search"
    assert body["latency_ms"] == 42
    assert captured["config"]["url"] == "https://mcp.example.com/mcp"
    assert captured["config"]["headers"]["Authorization"] == "Bearer sk-test"
    # 未保存：列表里没有这条
    assert (await client.get("/api/v1/mcp-servers", headers=auth_headers)).json() == []


async def test_test_saved_persists_status_and_tools(client, auth_headers, monkeypatch):
    sid = (await client.post("/api/v1/mcp-servers", json=HTTP_CONFIG, headers=auth_headers)).json()[
        "id"
    ]

    async def ok_probe(config):
        return mcp_service.ProbeResult(
            ok=True, tools=[{"name": "t1", "description": "d"}], latency_ms=7
        )

    monkeypatch.setattr(mcp_service, "probe", ok_probe)
    body = (await client.post(f"/api/v1/mcp-servers/{sid}/test", headers=auth_headers)).json()
    assert body["server"]["status"] == "ok"
    assert body["server"]["last_error"] is None
    assert body["server"]["tools"][0]["name"] == "t1"
    assert body["server"]["last_checked_at"] is not None

    async def fail_probe(config):
        return mcp_service.ProbeResult(ok=False, error="连接超时", latency_ms=3)

    monkeypatch.setattr(mcp_service, "probe", fail_probe)
    body = (await client.post(f"/api/v1/mcp-servers/{sid}/test", headers=auth_headers)).json()
    assert body["server"]["status"] == "error"
    assert body["server"]["last_error"] == "连接超时"
