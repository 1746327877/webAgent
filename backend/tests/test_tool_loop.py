from sqlalchemy import select

from app.ai.deps import get_provider
from app.ai.tools import sync_tools
from app.main import app
from app.models import AgentTool, Tool
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "工具助手",
    "system_prompt": "",
    "model_config": {"model": "m"},
    "tags": [],
    "examples": [],
}


async def _session_with_agent(client, auth_headers):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    s = (
        await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)
    ).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    return agent, s


async def test_tool_loop_executes_and_persists(client, auth_headers, session_maker):
    agent, s = await _session_with_agent(client, auth_headers)
    async with session_maker() as db:
        # 测试不走 lifespan，需手动同步内置工具（与 test_agent_versions 一致）
        await sync_tools(db)
        tool = (await db.scalars(select(Tool).where(Tool.slug == "time_now"))).first()
        db.add(AgentTool(agent_id=agent["id"], tool_id=tool.id))
        await db.commit()

    provider = FakeProvider(
        [
            [
                ("tool_call", {"id": "c1", "name": "time_now", "args": "{}"}),
                ("usage", {"prompt_tokens": 5, "completion_tokens": 2, "total_ms": 1}),
            ],
            [("token", {"delta": "现在是"}), ("usage", {"prompt_tokens": 9, "completion_tokens": 3, "total_ms": 1})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "现在几点"}, headers=auth_headers
    )
    body = r.text
    assert "event: tool_call" in body and "event: tool_result" in body and "event: done" in body
    assert len(provider.requests) == 2
    # 第二轮请求带 assistant tool_calls 与 tool 结果消息
    second = provider.requests[1].messages
    assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in second)
    assert any(m.get("role") == "tool" for m in second)

    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    blocks = msgs[1]["blocks"]
    types = [b["type"] for b in blocks]
    assert types == ["tool_call", "tool_result", "text"]
    assert blocks[0]["tool"] == "time_now"
    assert blocks[1]["status"] == "ok" and "20" in blocks[1]["preview"]
    assert blocks[2]["content"] == "现在是"


async def test_unknown_tool_becomes_error_result(client, auth_headers):
    _agent, s = await _session_with_agent(client, auth_headers)
    provider = FakeProvider(
        [
            [("tool_call", {"id": "c1", "name": "nope", "args": "{}"})],
            [("token", {"delta": "继续"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    result_block = next(b for b in msgs[1]["blocks"] if b["type"] == "tool_result")
    assert result_block["status"] == "error" and "未知工具" in result_block["preview"]


async def test_tool_loop_capped_at_five_rounds(client, auth_headers, session_maker):
    agent, s = await _session_with_agent(client, auth_headers)
    async with session_maker() as db:
        await sync_tools(db)
        tool = (await db.scalars(select(Tool).where(Tool.slug == "time_now"))).first()
        db.add(AgentTool(agent_id=agent["id"], tool_id=tool.id))
        await db.commit()

    always = [[("tool_call", {"id": "c", "name": "time_now", "args": "{}"})]]
    provider = FakeProvider(always)
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    assert "event: done" in r.text
    assert len(provider.requests) == 5  # 轮数上限
