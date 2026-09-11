REGISTER = {"username": "alice", "email": "alice@example.com", "password": "Passw0rd!"}


async def _register(client):
    await client.post("/api/v1/auth/register", json=REGISTER)


async def test_login_and_me(client):
    await _register(client)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "Passw0rd!"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert "refresh_token" in r.cookies

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_login_wrong_password(client):
    await _register(client)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "wrong-pass"}
    )
    assert r.status_code == 401


async def test_me_requires_token(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_refresh_rotates_and_revokes_old(client):
    await _register(client)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "Passw0rd!"}
    )
    old = r.cookies.get("refresh_token")

    r2 = await client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200
    assert r2.json()["access_token"]
    new = r2.cookies.get("refresh_token")
    assert new and new != old

    client.cookies.set("refresh_token", old, path="/api/v1/auth")
    r3 = await client.post("/api/v1/auth/refresh")
    assert r3.status_code == 401


async def test_logout_revokes(client):
    await _register(client)
    await client.post("/api/v1/auth/login", json={"username": "alice", "password": "Passw0rd!"})
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
