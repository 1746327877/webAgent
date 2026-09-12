import uuid


async def test_create_list_revoke_key(client, auth_headers):
    created = await client.post("/api/v1/keys", json={"name": "脚本调用"}, headers=auth_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("sk-") and len(body["key"]) == 35
    assert body["key_prefix"] == body["key"][:12]
    assert body["revoked"] is False

    listed = (await client.get("/api/v1/keys", headers=auth_headers)).json()
    assert [k["id"] for k in listed] == [body["id"]]
    assert "key" not in listed[0]  # 明文只在创建响应出现一次

    deleted = await client.delete(f"/api/v1/keys/{body['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    after = (await client.get("/api/v1/keys", headers=auth_headers)).json()
    assert after[0]["revoked"] is True


async def test_keys_isolated_between_users(client, auth_headers):
    from tests.test_sessions_api import make_user

    created = (await client.post("/api/v1/keys", json={"name": "k"}, headers=auth_headers)).json()
    other = await make_user(client, "bob")
    assert (await client.get("/api/v1/keys", headers=other)).json() == []
    assert (await client.delete(f"/api/v1/keys/{created['id']}", headers=other)).status_code == 404


async def test_resolve_key_user_updates_last_used_and_revoked_fails(client, auth_headers, session_maker):
    from app.models import ApiKey
    from app.services import api_key_service

    created = (await client.post("/api/v1/keys", json={"name": "k"}, headers=auth_headers)).json()
    me = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    async with session_maker() as db:
        user = await api_key_service.resolve_key_user(db, created["key"])
        assert user is not None and str(user.id) == me["id"]
        assert await api_key_service.resolve_key_user(db, "sk-不存在的密钥") is None
        assert await api_key_service.resolve_key_user(db, "不是 sk 开头") is None
    async with session_maker() as db:
        row = await db.get(ApiKey, uuid.UUID(created["id"]))
        assert row is not None and row.last_used_at is not None

    await client.delete(f"/api/v1/keys/{created['id']}", headers=auth_headers)
    async with session_maker() as db:
        assert await api_key_service.resolve_key_user(db, created["key"]) is None
