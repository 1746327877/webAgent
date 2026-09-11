import uuid

REGISTER = {"username": "alice", "email": "alice@example.com", "password": "Passw0rd!"}


async def make_user(client, name: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": f"{name}@example.com", "password": "Passw0rd!"},
    )
    r = await client.post("/api/v1/auth/login", json={"username": name, "password": "Passw0rd!"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_create_and_list_sessions(client, auth_headers):
    r = await client.post("/api/v1/sessions", json={}, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "新对话"
    assert data["pinned"] is False

    lst = await client.get("/api/v1/sessions", headers=auth_headers)
    assert lst.status_code == 200
    body = lst.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == data["id"]


async def test_search_and_archive_filter(client, auth_headers):
    s1 = (
        await client.post("/api/v1/sessions", json={"title": "Java 学习"}, headers=auth_headers)
    ).json()
    await client.post("/api/v1/sessions", json={"title": "Python 笔记"}, headers=auth_headers)

    found = await client.get("/api/v1/sessions?query=Java", headers=auth_headers)
    assert [s["title"] for s in found.json()["items"]] == ["Java 学习"]

    await client.patch(f"/api/v1/sessions/{s1['id']}", json={"archived": True}, headers=auth_headers)
    visible = await client.get("/api/v1/sessions", headers=auth_headers)
    assert [s["title"] for s in visible.json()["items"]] == ["Python 笔记"]
    archived = await client.get("/api/v1/sessions?archived=true", headers=auth_headers)
    assert [s["title"] for s in archived.json()["items"]] == ["Java 学习"]


async def test_patch_pin_rename_delete(client, auth_headers):
    s = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    r = await client.patch(
        f"/api/v1/sessions/{s['id']}",
        json={"title": "改名", "pinned": True},
        headers=auth_headers,
    )
    assert r.json()["title"] == "改名" and r.json()["pinned"] is True

    d = await client.delete(f"/api/v1/sessions/{s['id']}", headers=auth_headers)
    assert d.status_code == 204
    assert (await client.get("/api/v1/sessions", headers=auth_headers)).json()["total"] == 0


async def test_ownership_isolation(client, auth_headers):
    s = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    other = await make_user(client, "bob")
    for method, url in [
        ("get", f"/api/v1/sessions/{s['id']}"),
        ("patch", f"/api/v1/sessions/{s['id']}"),
        ("delete", f"/api/v1/sessions/{s['id']}"),
        ("get", f"/api/v1/sessions/{s['id']}/messages"),
    ]:
        resp = await getattr(client, method)(url, headers=other)
        assert resp.status_code == 404, (method, url)


async def test_messages_endpoint_empty_and_pagination(client, auth_headers):
    s = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    r = await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)
    assert r.status_code == 200 and r.json() == []

    for _ in range(3):
        await client.post("/api/v1/sessions", json={}, headers=auth_headers)
    page = await client.get("/api/v1/sessions?limit=2&offset=2", headers=auth_headers)
    assert page.json()["total"] == 4 and len(page.json()["items"]) == 2


async def test_get_session_and_query_bounds(client, auth_headers):
    s = (
        await client.post("/api/v1/sessions", json={"title": "Java 学习"}, headers=auth_headers)
    ).json()
    r = await client.get(f"/api/v1/sessions/{s['id']}", headers=auth_headers)
    assert r.status_code == 200 and r.json()["title"] == "Java 学习"

    missing = await client.get(f"/api/v1/sessions/{uuid.uuid4()}", headers=auth_headers)
    assert missing.status_code == 404

    noop = await client.patch(f"/api/v1/sessions/{s['id']}", headers=auth_headers)
    assert noop.status_code == 200 and noop.json()["title"] == "Java 学习"

    assert (await client.get("/api/v1/sessions?limit=0", headers=auth_headers)).status_code == 422
    assert (await client.get("/api/v1/sessions?limit=201", headers=auth_headers)).status_code == 422
