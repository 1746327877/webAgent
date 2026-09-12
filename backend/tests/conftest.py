import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.db import get_db, get_session_factory
from app.main import app
from app.models import Base
from tests.fake_provider import FakeProvider


def _plain(dsn: str) -> str:
    return dsn.replace("+asyncpg", "")


@pytest_asyncio.fixture(scope="session")
async def engine():
    dsn = _plain(settings.test_database_url)
    admin_dsn = dsn.rsplit("/", 1)[0] + "/postgres"
    conn = await asyncpg.connect(admin_dsn)
    exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname='webagent_test'")
    if not exists:
        await conn.execute("CREATE DATABASE webagent_test")
    await conn.close()

    eng = create_async_engine(settings.test_database_url, poolclass=NullPool)
    async with eng.begin() as c:
        await c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await c.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(engine):
    from app.observability.http_stats import collector

    collector.clear()
    yield
    collector.clear()
    async with engine.begin() as c:
        await c.execute(
            text(
                "TRUNCATE chunks, documents, knowledge_bases, agent_kbs, spans, http_stats,"
                " alert_events, alert_rules, api_keys, attachments, messages, sessions, refresh_tokens,"
                " users, agents, agent_versions, agent_tools, tools, model_events CASCADE"
            )
        )


@pytest_asyncio.fixture
async def client(session_maker):
    async def override_get_db():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_maker
    # 测试不走 lifespan：预置哑 provider，使「依赖解析早于请求体校验」的
    # 失败路径（如 mentions 超限 422）不因 app.state.provider 缺失而 500。
    app.state.provider = FakeProvider()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "Passw0rd!"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "Passw0rd!"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
