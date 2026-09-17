import httpx
import respx

from app.ai.deps import get_provider
from app.core.config import settings
from app.main import app
from tests.fake_provider import FakeProvider

MINERU_HEALTH = "http://mineru.test:8001/health"


async def test_list_skills_returns_full_fields(client, auth_headers):
    r = await client.get("/api/v1/capabilities/skills", headers=auth_headers)
    assert r.status_code == 200, r.text
    skills = r.json()
    slugs = [s["slug"] for s in skills]
    assert "kb_qa" in slugs
    assert "doc_convert" in slugs
    for skill in skills:
        for field in (
            "slug",
            "name",
            "icon",
            "summary",
            "usage",
            "instructions",
            "examples",
            "recommended_tools",
        ):
            assert field in skill, field
        assert skill["summary"] and skill["usage"] and skill["instructions"]


async def test_skills_require_auth(client):
    r = await client.get("/api/v1/capabilities/skills")
    assert r.status_code == 401


async def test_tools_include_input_schema(client, auth_headers, session_maker):
    from app.ai.tools import sync_tools

    async with session_maker() as db:
        await sync_tools(db)

    r = await client.get("/api/v1/tools", headers=auth_headers)
    tools = {t["slug"]: t for t in r.json()}
    assert "kb_search" in tools
    schema = tools["kb_search"]["input_schema"]
    assert "properties" in schema
    assert "query" in schema["properties"]


async def test_doc_convert_tool_and_skill_registered(client, auth_headers, session_maker):
    from app.ai.tools import sync_tools

    async with session_maker() as db:
        await sync_tools(db)

    tools = {t["slug"]: t for t in (await client.get("/api/v1/tools", headers=auth_headers)).json()}
    assert "doc_convert" in tools
    properties = tools["doc_convert"]["input_schema"]["properties"]
    assert "target" in properties and "name" in properties

    skills = {
        s["slug"]: s
        for s in (await client.get("/api/v1/capabilities/skills", headers=auth_headers)).json()
    }
    assert skills["doc_convert"]["recommended_tools"] == ["doc_convert"]
    assert "docx" in skills["doc_convert"]["summary"]


async def test_parser_status_disabled(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "")
    body = (await client.get("/api/v1/capabilities/parser", headers=auth_headers)).json()
    assert body["enabled"] is False
    assert body["healthy"] is False
    assert "未配置" in body["error"]


@respx.mock
async def test_parser_status_healthy(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "http://mineru.test:8001")
    respx.get(MINERU_HEALTH).mock(
        return_value=httpx.Response(200, json={"status": "healthy", "version": "3.4.5"})
    )
    body = (await client.get("/api/v1/capabilities/parser", headers=auth_headers)).json()
    assert body["enabled"] is True
    assert body["healthy"] is True
    assert body["version"] == "3.4.5"
    assert body["backend"] == settings.mineru_backend
    assert body["latency_ms"] is not None


@respx.mock
async def test_parser_status_unreachable(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "http://mineru.test:8001")
    respx.get(MINERU_HEALTH).mock(side_effect=httpx.ConnectError("refused"))
    body = (await client.get("/api/v1/capabilities/parser", headers=auth_headers)).json()
    assert body["enabled"] is True
    assert body["healthy"] is False
    assert body["error"]


async def test_models_include_capabilities(client, auth_headers):
    from app.ai.providers.base import ModelInfo

    class P(FakeProvider):
        async def list_available(self):
            return [ModelInfo(name="tool-model:1b", size_mb=1000.0)]

        async def capabilities(self, model):
            return ["completion", "tools"]

    app.dependency_overrides[get_provider] = lambda: P()
    body = (await client.get("/api/v1/models", headers=auth_headers)).json()
    item = next(m for m in body if m["name"] == "tool-model:1b")
    assert "tools" in item["capabilities"]
