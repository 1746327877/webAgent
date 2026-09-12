import uuid

from sqlalchemy import select

from app.ai.deps import get_provider
from app.ai.model_manager import ModelManager
from app.ai.tools import sync_tools
from app.main import app
from app.models import AgentTool, Span, Tool
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "埋点",
    "system_prompt": "",
    "model_config": {"model": "m-span"},
    "tags": [],
    "examples": [],
}


async def _agent_session(client, auth_headers, model="m-span"):
    agent = (
        await client.post("/api/v1/agents", json={**AGENT, "model_config": {"model": model}}, headers=auth_headers)
    ).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    return agent, s


async def test_llm_and_tool_spans_with_parent(client, auth_headers, session_maker):
    agent, s = await _agent_session(client, auth_headers)
    async with session_maker() as db:
        await sync_tools(db)
        tool = (await db.scalars(select(Tool).where(Tool.slug == "time_now"))).first()
        db.add(AgentTool(agent_id=uuid.UUID(agent["id"]), tool_id=tool.id))
        await db.commit()

    provider = FakeProvider(
        [
            [
                ("tool_call", {"id": "c1", "name": "time_now", "args": {}}),
                ("usage", {"prompt_tokens": 5, "completion_tokens": 2}),
            ],
            [("token", {"delta": "好"}), ("usage", {"prompt_tokens": 9, "completion_tokens": 3})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "现在几点"}, headers=auth_headers
    )
    assert "event: done" in r.text

    async with session_maker() as db:
        spans = (await db.scalars(select(Span).order_by(Span.started_at))).all()
    llm_spans = [x for x in spans if x.type == "llm"]
    tool_spans = [x for x in spans if x.type == "tool"]
    assert len(llm_spans) == 2 and len(tool_spans) == 1
    assert llm_spans[0].model == "m-span" and llm_spans[0].user_id is not None
    assert llm_spans[0].prompt_tokens == 5 and llm_spans[1].completion_tokens == 3
    assert tool_spans[0].name == "time_now" and tool_spans[0].status == "ok"
    assert tool_spans[0].parent_span_id == llm_spans[0].id
    assert tool_spans[0].message_id is not None


async def test_model_switch_span(client, auth_headers, session_maker):
    _agent, s = await _agent_session(client, auth_headers, model="m-switch")
    provider = FakeProvider([("token", {"delta": "x"})])
    app.dependency_overrides[get_provider] = lambda: provider
    app.state.model_manager = ModelManager(provider, session_factory=session_maker)
    try:
        await client.post(
            f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
        )
    finally:
        del app.state.model_manager
    async with session_maker() as db:
        row = (await db.scalars(select(Span).where(Span.type == "model_switch"))).first()
    assert row is not None and row.model == "m-switch" and row.status == "ok"
    assert row.input["to"] == "m-switch"


async def test_large_span_output_truncated(client, auth_headers, session_maker):
    _agent, s = await _agent_session(client, auth_headers)
    provider = FakeProvider([("token", {"delta": "x" * 40000})])
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    async with session_maker() as db:
        row = (await db.scalars(select(Span).where(Span.type == "llm"))).first()
    assert row.output.get("_truncated") is True
