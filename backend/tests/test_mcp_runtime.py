from types import SimpleNamespace

from app.ai.agent_config import _compose_prompt
from app.ai.deps import get_provider
from app.ai.mcp_tools import build_mcp_tools
from app.ai.skills import SKILL_REGISTRY
from app.main import app
from app.services import mcp_service
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "MCP 助手",
    "system_prompt": "你是助手",
    "model_config": {"model": "m"},
    "tags": [],
    "examples": [],
}
MCP_CONFIG = {"name": "Baidu Search", "transport": "http", "url": "https://mcp.example.com/mcp"}
FUNC = "mcp__baidu_search__web_search"


def test_compose_prompt_injects_skill_instructions():
    base = "你是助手"
    prompt = _compose_prompt(base, ["kb_qa"])
    assert base in prompt
    assert "已启用能力" in prompt
    assert SKILL_REGISTRY["kb_qa"].instructions in prompt
    # 未知 slug 静默忽略，不报错
    assert _compose_prompt(base, ["nope"]) == base


def test_build_mcp_tools_names_and_mapping():
    binding = SimpleNamespace(
        server_name="Baidu Search",
        config={"transport": "http", "url": "https://x/mcp"},
        tools=[
            {"name": "web search", "description": "搜索", "input_schema": {"type": "object"}},
            {"name": "web search", "description": "重复名", "input_schema": {}},
        ],
    )

    payload, mapping = build_mcp_tools([binding])
    names = [item["function"]["name"] for item in payload]
    assert names[0] == "mcp__baidu_search__web_search"
    assert len(set(names)) == 2  # 重名自动去重
    assert payload[0]["function"]["description"].startswith("[MCP:Baidu Search]")
    assert mapping["mcp__baidu_search__web_search"]["tool_name"] == "web search"
    assert mapping["mcp__baidu_search__web_search"]["label"] == "Baidu Search · web search"


async def _setup(client, auth_headers, monkeypatch):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    sid = (
        await client.post("/api/v1/mcp-servers", json=MCP_CONFIG, headers=auth_headers)
    ).json()["id"]

    async def fake_probe(config):
        return mcp_service.ProbeResult(
            ok=True,
            tools=[
                {
                    "name": "web_search",
                    "description": "网页搜索",
                    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
                }
            ],
            latency_ms=5,
        )

    monkeypatch.setattr(mcp_service, "probe", fake_probe)
    await client.post(f"/api/v1/mcp-servers/{sid}/test", headers=auth_headers)

    await client.put(
        f"/api/v1/agents/{agent['id']}/skills", json={"slugs": ["kb_qa"]}, headers=auth_headers
    )
    await client.put(
        f"/api/v1/agents/{agent['id']}/mcp-tools",
        json={"tools": [{"mcp_server_id": sid, "tool_name": "web_search"}]},
        headers=auth_headers,
    )
    session = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()
    await client.patch(
        f"/api/v1/sessions/{session['id']}", json={"title": "t"}, headers=auth_headers
    )
    return agent, session


async def test_mcp_tool_exposed_injected_and_called(client, auth_headers, monkeypatch):
    _agent, session = await _setup(client, auth_headers, monkeypatch)

    calls: dict = {}

    async def fake_call(config, name, args):
        calls.update({"name": name, "args": args, "url": config["url"]})
        return "搜索结果：abc", "ok"

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
        json={"content": "搜一下"},
        headers=auth_headers,
    )
    assert "event: tool_result" in r.text

    first = provider.requests[0]
    # MCP 工具已作为 function 暴露给模型
    names = [tool["function"]["name"] for tool in (first.tools or [])]
    assert FUNC in names
    # skill 指令注入 system prompt
    system_msgs = [m for m in first.messages if m.get("role") == "system"]
    assert system_msgs and "已启用能力" in system_msgs[0]["content"]
    # 调用被路由到真实 MCP 配置
    assert calls == {"name": "web_search", "args": {"query": "并发"}, "url": "https://mcp.example.com/mcp"}

    blocks = (
        await client.get(f"/api/v1/sessions/{session['id']}/messages", headers=auth_headers)
    ).json()[1]["blocks"]
    result_block = next(b for b in blocks if b["type"] == "tool_result")
    assert result_block["status"] == "ok" and "搜索结果" in result_block["preview"]
    call_block = next(b for b in blocks if b["type"] == "tool_call")
    assert call_block["tool"] == "Baidu Search · web_search"
