"""doc_create 工具在 runtime 层的生成与产物落盘。"""

from sqlalchemy import select

from app.ai.deps import get_provider
from app.ai.tools import sync_tools
from app.main import app
from app.models import AgentTool, Artifact, Tool
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "文档助手",
    "system_prompt": "",
    "model_config": {"model": "m"},
    "tags": [],
    "examples": [],
}
CONTENT = "# 请假条\n\n本人张三因感冒，申请请假一天。\n"


async def _bind_doc_create(session_maker, agent_id):
    async with session_maker() as db:
        await sync_tools(db)
        tool = (await db.scalars(select(Tool).where(Tool.slug == "doc_create"))).first()
        db.add(AgentTool(agent_id=agent_id, tool_id=tool.id))
        await db.commit()


async def _session(client, auth_headers, session_maker):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    s = (
        await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)
    ).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    await _bind_doc_create(session_maker, agent["id"])
    return s


async def _artifacts(session_maker, session_id):
    async with session_maker() as db:
        rows = (
            await db.scalars(select(Artifact).where(Artifact.session_id == session_id))
        ).all()
        return [(r.filename, r.source) for r in rows]


async def test_doc_create_both_generates_docx_and_pdf(client, auth_headers, session_maker):
    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [
                (
                    "tool_call",
                    {
                        "id": "c1",
                        "name": "doc_create",
                        "args": {
                            "filename": "请假条-张三",
                            "content": CONTENT,
                            "target": "both",
                        },
                    },
                )
            ],
            [("token", {"delta": "已生成"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "帮我写份请假条"},
        headers=auth_headers,
    )
    assert r.status_code == 200 and "event: tool_result" in r.text

    artifacts = (
        await client.get(f"/api/v1/sessions/{s['id']}/artifacts", headers=auth_headers)
    ).json()
    assert len(artifacts) == 2
    names = sorted(a["filename"] for a in artifacts)
    assert names == ["请假条-张三.docx", "请假条-张三.pdf"]
    assert {a["source"] for a in artifacts} == {"tool"}


async def test_doc_create_single_format(client, auth_headers, session_maker):
    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [
                (
                    "tool_call",
                    {
                        "id": "c1",
                        "name": "doc_create",
                        "args": {"filename": "证明", "content": CONTENT, "target": "pdf"},
                    },
                )
            ],
            [("token", {"delta": "好"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "生成证明"},
        headers=auth_headers,
    )
    artifacts = (
        await client.get(f"/api/v1/sessions/{s['id']}/artifacts", headers=auth_headers)
    ).json()
    assert len(artifacts) == 1 and artifacts[0]["filename"] == "证明.pdf"


async def test_doc_create_empty_content_returns_error(client, auth_headers, session_maker):
    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [("tool_call", {"id": "c1", "name": "doc_create", "args": {"filename": "x"}})],
            [("token", {"delta": "好"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "生成"},
        headers=auth_headers,
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    block = next(b for b in msgs[1]["blocks"] if b["type"] == "tool_result")
    assert block["status"] == "error" and "文档内容" in block["preview"]


async def test_doc_create_invalid_target_returns_error(client, auth_headers, session_maker):
    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [
                (
                    "tool_call",
                    {
                        "id": "c1",
                        "name": "doc_create",
                        "args": {"filename": "x", "content": CONTENT, "target": "html"},
                    },
                )
            ],
            [("token", {"delta": "好"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "生成"},
        headers=auth_headers,
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    block = next(b for b in msgs[1]["blocks"] if b["type"] == "tool_result")
    assert block["status"] == "error" and "目标格式" in block["preview"]
    artifacts = (
        await client.get(f"/api/v1/sessions/{s['id']}/artifacts", headers=auth_headers)
    ).json()
    assert artifacts == []


async def test_doc_create_too_long_content_is_rejected(client, auth_headers, session_maker):
    from app.ai.runtime import MAX_CREATE_CONTENT_CHARS

    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [
                (
                    "tool_call",
                    {
                        "id": "c1",
                        "name": "doc_create",
                        "args": {
                            "filename": "x",
                            "content": "啊" * (MAX_CREATE_CONTENT_CHARS + 1),
                            "target": "pdf",
                        },
                    },
                )
            ],
            [("token", {"delta": "好"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "生成"},
        headers=auth_headers,
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    block = next(b for b in msgs[1]["blocks"] if b["type"] == "tool_result")
    assert block["status"] == "error" and "过长" in block["preview"]


async def test_doc_create_filename_is_sanitized(client, auth_headers, session_maker):
    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [
                (
                    "tool_call",
                    {
                        "id": "c1",
                        "name": "doc_create",
                        "args": {"filename": "请假/条", "content": CONTENT, "target": "pdf"},
                    },
                )
            ],
            [("token", {"delta": "好"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "生成"},
        headers=auth_headers,
    )
    artifacts = (
        await client.get(f"/api/v1/sessions/{s['id']}/artifacts", headers=auth_headers)
    ).json()
    assert len(artifacts) == 1
    assert "/" not in artifacts[0]["filename"] and artifacts[0]["filename"].endswith(".pdf")


async def test_doc_create_partial_failure_reports_made_part(
    client, auth_headers, session_maker, monkeypatch
):
    import app.ai.convert as convert_mod
    from app.ai.convert import ConvertError

    real = convert_mod.convert_markdown

    def flaky(content, target):
        if target == "pdf":
            raise ConvertError("模拟 pdf 渲染失败")
        return real(content, target)

    monkeypatch.setattr(convert_mod, "convert_markdown", flaky)
    s = await _session(client, auth_headers, session_maker)
    provider = FakeProvider(
        [
            [
                (
                    "tool_call",
                    {
                        "id": "c1",
                        "name": "doc_create",
                        "args": {"filename": "请假条", "content": CONTENT, "target": "both"},
                    },
                )
            ],
            [("token", {"delta": "好"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "生成"},
        headers=auth_headers,
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    block = next(b for b in msgs[1]["blocks"] if b["type"] == "tool_result")
    assert block["status"] == "error" and "部分生成成功" in block["preview"]
    artifacts = (
        await client.get(f"/api/v1/sessions/{s['id']}/artifacts", headers=auth_headers)
    ).json()
    assert [a["filename"] for a in artifacts] == ["请假条.docx"]
