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


async def test_bulk_delete_removes_selected_and_ignores_other_users(client, auth_headers):
    ids = [
        (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()["id"]
        for _ in range(3)
    ]
    bob = await make_user(client, "bob")
    theirs = (await client.post("/api/v1/sessions", json={}, headers=bob)).json()["id"]

    r = await client.post(
        "/api/v1/sessions/bulk-delete",
        json={"ids": [ids[0], ids[1], theirs]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    # 他人的 id 被忽略，只删掉自己的两条
    assert r.json()["deleted"] == 2

    mine = (await client.get("/api/v1/sessions", headers=auth_headers)).json()
    assert [s["id"] for s in mine["items"]] == [ids[2]]
    bob_list = (await client.get("/api/v1/sessions", headers=bob)).json()
    assert [s["id"] for s in bob_list["items"]] == [theirs]


async def test_bulk_delete_cascades_messages(client, auth_headers):
    sid = (
        await client.post("/api/v1/sessions", json={"title": "待删"}, headers=auth_headers)
    ).json()["id"]
    r = await client.post(
        "/api/v1/sessions/bulk-delete", json={"ids": [sid]}, headers=auth_headers
    )
    assert r.json()["deleted"] == 1
    assert (await client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)).status_code == 404


async def test_bulk_delete_empty_ids_rejected(client, auth_headers):
    r = await client.post(
        "/api/v1/sessions/bulk-delete", json={"ids": []}, headers=auth_headers
    )
    assert r.status_code == 422


async def test_bulk_delete_up_to_1000_ids_allowed(client, auth_headers):
    # 不存在的 id 一律忽略：用随机 id 验证"恰好到上限"能通过，避免逐条建会话拖慢用例
    ids = [str(uuid.uuid4()) for _ in range(1000)]
    r = await client.post(
        "/api/v1/sessions/bulk-delete", json={"ids": ids}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 0


async def test_bulk_delete_over_limit_returns_422_and_logs(client, auth_headers, caplog):
    import logging

    ids = [str(uuid.uuid4()) for _ in range(1001)]
    with caplog.at_level(logging.WARNING, logger="app"):
        r = await client.post(
            "/api/v1/sessions/bulk-delete", json={"ids": ids}, headers=auth_headers
        )
    assert r.status_code == 422
    # 校验失败要留下可排障的日志（含路径与错误细节）
    assert any("请求校验失败" in record.message for record in caplog.records)
    assert any("/api/v1/sessions/bulk-delete" in record.message for record in caplog.records)
    assert any("too_long" in record.message for record in caplog.records)
    # 但不得回显请求体（上千 id 会刷屏，且可能把敏感字段写进日志）
    assert not any(ids[0] in record.message for record in caplog.records)
