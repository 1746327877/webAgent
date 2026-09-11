from datetime import UTC

CJK_75_BYTES = "密" * 25  # 25 * 3 = 75 字节 > 72


async def test_register_rejects_password_over_72_bytes(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": CJK_75_BYTES},
    )
    assert r.status_code == 422


async def test_login_rejects_password_over_72_bytes(client):
    r = await client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": CJK_75_BYTES}
    )
    assert r.status_code == 422


async def test_register_duplicate_email(client):
    payload = {"username": "user1", "email": "dup@example.com", "password": "Passw0rd!"}
    await client.post("/api/v1/auth/register", json=payload)
    r = await client.post(
        "/api/v1/auth/register",
        json={"username": "user2", "email": "dup@example.com", "password": "Passw0rd!"},
    )
    assert r.status_code == 409


async def test_refresh_rejects_expired_token(client, auth_headers, session_maker):
    from datetime import datetime, timedelta

    from sqlalchemy import update as sa_update

    from app.models import RefreshToken

    async with session_maker() as db:
        await db.execute(
            sa_update(RefreshToken).values(
                expires_at=datetime.now(UTC) - timedelta(days=1)
            )
        )
        await db.commit()
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
