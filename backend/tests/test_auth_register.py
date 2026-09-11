async def test_register_success(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "Passw0rd!"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "alice"
    assert "password_hash" not in data


async def test_register_duplicate_username(client):
    payload = {"username": "alice", "email": "a1@example.com", "password": "Passw0rd!"}
    await client.post("/api/v1/auth/register", json=payload)
    payload["email"] = "a2@example.com"
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409


async def test_register_short_password(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "bob@example.com", "password": "short"},
    )
    assert r.status_code == 422
