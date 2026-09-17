"""doc_convert 工具在 runtime 层的真实转换与产物落盘（docs/设计/25）。"""

import io

from sqlalchemy import select

from app.ai.deps import get_provider
from app.ai.tools import sync_tools
from app.main import app
from app.models import AgentTool, Tool
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "转换助手",
    "system_prompt": "",
    "model_config": {"model": "m"},
    "tags": [],
    "examples": [],
}
MD = "# 标题\n\n正文\n"


async def _bind_doc_convert(session_maker, agent_id):
    async with session_maker() as db:
        await sync_tools(db)
        tool = (await db.scalars(select(Tool).where(Tool.slug == "doc_convert"))).first()
        db.add(AgentTool(agent_id=agent_id, tool_id=tool.id))
        await db.commit()


async def _session(client, auth_headers, session_maker):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    s = (
        await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)
    ).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    await _bind_doc_convert(session_maker, agent["id"])
    return s


async def test_doc_convert_tool_creates_artifact(client, auth_headers, session_maker):
    s = await _session(client, auth_headers, session_maker)
    att = (
        await client.post(
            f"/api/v1/sessions/{s['id']}/attachments",
            files={"file": ("note.md", io.BytesIO(MD.encode()), "text/markdown")},
            headers=auth_headers,
        )
    ).json()
    assert att["kind"] == "document"

    provider = FakeProvider(
        [
            [("tool_call", {"id": "c1", "name": "doc_convert", "args": {"target": "docx"}})],
            [("token", {"delta": "已转换"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "转成 Word", "attachment_ids": [att["id"]]},
        headers=auth_headers,
    )
    assert r.status_code == 200 and "event: tool_result" in r.text

    artifacts = (
        await client.get(f"/api/v1/sessions/{s['id']}/artifacts", headers=auth_headers)
    ).json()
    assert len(artifacts) == 1
    assert artifacts[0]["source"] == "tool"
    assert artifacts[0]["filename"] == "note.docx"
    assert artifacts[0]["mime_type"].endswith("wordprocessingml.document")

    download = await client.get(f"/api/v1/artifacts/{artifacts[0]['id']}", headers=auth_headers)
    assert download.content[:2] == b"PK"


async def test_doc_convert_without_attachment_returns_error(client, auth_headers, session_maker):
    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [("tool_call", {"id": "c1", "name": "doc_convert", "args": {"target": "pdf"}})],
            [("token", {"delta": "好"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "转 pdf"}, headers=auth_headers
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    block = next(b for b in msgs[1]["blocks"] if b["type"] == "tool_result")
    assert block["status"] == "error" and "没有可转换" in block["preview"]
