"""联网搜索合成绑定与对话级开关（docs/设计/18）。"""

import pytest

from app.ai import web_search
from app.ai.deps import get_provider
from app.core.config import settings
from app.main import app
from app.services import mcp_service
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "搜索助手",
    "system_prompt": "你是助手",
    "model_config": {"model": "m"},
    "tags": [],
    "examples": [],
}
WEB_SEARCH_URL = "https://ws.example.com/mcp"
SEARCH_TOOL = {
    "name": "search",
    "description": "网页搜索",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
}
FUNC = "mcp__web_search__search"


def _probe_ok():
    async def fake_probe(config):
        return mcp_service.ProbeResult(ok=True, tools=[dict(SEARCH_TOOL)], latency_ms=3)

    return fake_probe


@pytest.fixture(autouse=True)
def _clear_cache():
    # 模块级探测缓存跨用例残留，逐用例清空
    web_search.reset_cache()
    yield
    web_search.reset_cache()


async def test_binding_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", "")
    assert web_search.is_enabled() is False
    assert await web_search.binding() is None


async def test_binding_none_when_probe_fails(monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", WEB_SEARCH_URL)

    async def bad_probe(config):
        return mcp_service.ProbeResult(ok=False, error="boom")

    monkeypatch.setattr(mcp_service, "probe", bad_probe)
    assert await web_search.binding() is None


async def test_binding_returns_synthetic_http_binding(monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", WEB_SEARCH_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())

    binding = await web_search.binding()
    assert binding is not None
    assert binding.server_name == web_search.SERVER_NAME
    assert binding.config["transport"] == "http"
    assert binding.config["url"] == WEB_SEARCH_URL
    assert [tool["name"] for tool in binding.tools] == ["search"]


async def test_probe_result_is_cached_within_ttl(monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", WEB_SEARCH_URL)
    calls = {"n": 0}

    async def counting_probe(config):
        calls["n"] += 1
        return mcp_service.ProbeResult(ok=True, tools=[dict(SEARCH_TOOL)], latency_ms=1)

    monkeypatch.setattr(mcp_service, "probe", counting_probe)
    await web_search.binding()
    await web_search.binding()
    assert calls["n"] == 1


async def _new_session(client, auth_headers):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    session = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()
    return agent, session


def _tool_names(provider) -> list[str]:
    return [tool["function"]["name"] for tool in (provider.requests[0].tools or [])]


async def test_message_flag_exposes_and_calls_web_search(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", WEB_SEARCH_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())
    _agent, session = await _new_session(client, auth_headers)

    calls: dict = {}

    async def fake_call(config, name, args):
        calls.update({"name": name, "args": args, "url": config["url"]})
        return ("搜索结果：https://example.com/a", "ok")

    monkeypatch.setattr(mcp_service, "call_tool", fake_call)

    provider = FakeProvider(
        [
            [
                ("tool_call", {"id": "c1", "name": FUNC, "args": {"query": "并发"}}),
                ("usage", {"prompt_tokens": 5, "completion_tokens": 1}),
            ],
            [("token", {"delta": "完成"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider

    r = await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "搜一下", "web_search": True},
        headers=auth_headers,
    )
    assert "event: tool_result" in r.text
    assert FUNC in _tool_names(provider)
    assert calls == {"name": "search", "args": {"query": "并发"}, "url": WEB_SEARCH_URL}


async def test_message_without_flag_hides_web_search(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", WEB_SEARCH_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())
    _agent, session = await _new_session(client, auth_headers)

    provider = FakeProvider([[("token", {"delta": "好的"})]])
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "你好"},
        headers=auth_headers,
    )
    assert FUNC not in _tool_names(provider)


async def test_message_flag_degrades_when_unconfigured(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", "")
    _agent, session = await _new_session(client, auth_headers)

    provider = FakeProvider([[("token", {"delta": "好的"})]])
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "搜一下", "web_search": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert FUNC not in _tool_names(provider)


async def test_does_not_duplicate_already_bound_server(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", WEB_SEARCH_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    server_id = (
        await client.post(
            "/api/v1/mcp-servers",
            json={"name": web_search.SERVER_NAME, "transport": "http", "url": WEB_SEARCH_URL},
            headers=auth_headers,
        )
    ).json()["id"]
    await client.post(f"/api/v1/mcp-servers/{server_id}/test", headers=auth_headers)
    await client.put(
        f"/api/v1/agents/{agent['id']}/mcp-tools",
        json={"tools": [{"mcp_server_id": server_id, "tool_name": "search"}]},
        headers=auth_headers,
    )
    session = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()

    provider = FakeProvider([[("token", {"delta": "好的"})]])
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "搜一下", "web_search": True},
        headers=auth_headers,
    )
    names = _tool_names(provider)
    assert names.count(FUNC) == 1
    assert f"{FUNC}_1" not in names


async def test_capabilities_endpoint_reports_status(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "web_search_mcp_url", "")
    body = (
        await client.get("/api/v1/capabilities/web-search", headers=auth_headers)
    ).json()
    assert body["enabled"] is False and body["healthy"] is False

    monkeypatch.setattr(settings, "web_search_mcp_url", WEB_SEARCH_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())
    body = (
        await client.get("/api/v1/capabilities/web-search", headers=auth_headers)
    ).json()
    assert body["enabled"] is True and body["healthy"] is True
    assert body["tools"] == ["search"]
