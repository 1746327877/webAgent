import io

from app.ai.deps import get_provider
from app.ai.model_manager import ModelManager
from app.main import app
from tests.fake_provider import FakeProvider


async def test_image_upload_and_vision_switch(client, auth_headers, session_maker):
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "VL", "system_prompt": "", "model_config": {"model": "m-text"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32  # 类型白名单按扩展名/魔数校验即可
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/attachments",
        files={"file": ("pic.png", io.BytesIO(png), "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    att = r.json()

    provider = FakeProvider([("token", {"delta": "图里是一只猫"})])
    app.dependency_overrides[get_provider] = lambda: provider
    mm = ModelManager(provider, session_factory=session_maker)
    app.state.model_manager = mm
    try:
        resp = await client.post(
            f"/api/v1/sessions/{s['id']}/messages",
            json={"content": "这是什么", "attachment_ids": [att["id"]]},
            headers=auth_headers,
        )
        assert '"to": "qwen2.5vl:7b"' in resp.text  # model_switching start
        assert mm.current == "qwen2.5vl:7b"
        last = provider.requests[-1].messages[-1]
        assert last.get("images") and len(last["images"][0]) > 10
        msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
        assert msgs[0]["attachments"][0]["id"] == att["id"]
    finally:
        del app.state.model_manager


async def _make_agent(client, auth_headers, name: str, model: str = "m-text") -> str:
    agent = (
        await client.post(
            "/api/v1/agents",
            json={
                "name": name,
                "system_prompt": "",
                "model_config": {"model": model},
                "tags": [],
                "examples": [],
            },
            headers=auth_headers,
        )
    ).json()
    return agent["id"]


def _system_texts(provider: FakeProvider) -> str:
    req = provider.last_request
    assert req is not None
    return "\n".join(m["content"] for m in req.messages if m["role"] == "system")


async def test_document_upload_kind_and_extraction_injection(client, auth_headers):
    agent_id = await _make_agent(client, auth_headers, "DOC")
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent_id}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)

    body = "# 会议纪要\n决定采用 FastAPI。".encode("utf-8")
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/attachments",
        files={"file": ("notes.md", io.BytesIO(body), "text/markdown")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    att = r.json()
    assert att["kind"] == "document"
    assert att["original_name"] == "notes.md"

    provider = FakeProvider([("token", {"delta": "已总结"})])
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        resp = await client.post(
            f"/api/v1/sessions/{s['id']}/messages",
            json={"content": "总结一下", "attachment_ids": [att["id"]]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        systems = _system_texts(provider)
        assert "notes.md" in systems
        assert "决定采用 FastAPI" in systems
        # 文档轮不应触发视觉模型切换
        assert provider.last_request is not None
        assert provider.last_request.model == "m-text"
    finally:
        app.dependency_overrides.pop(get_provider, None)


async def test_document_extraction_failure_is_best_effort(client, auth_headers):
    agent_id = await _make_agent(client, auth_headers, "BADDOC")
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent_id}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)

    r = await client.post(
        f"/api/v1/sessions/{s['id']}/attachments",
        files={"file": ("broken.pdf", io.BytesIO(b"definitely-not-a-pdf"), "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    att = r.json()
    assert att["kind"] == "document"

    provider = FakeProvider([("token", {"delta": "ok"})])
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        resp = await client.post(
            f"/api/v1/sessions/{s['id']}/messages",
            json={"content": "看看", "attachment_ids": [att["id"]]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "event: done" in resp.text
        systems = _system_texts(provider)
        assert "broken.pdf" in systems
        assert "失败" in systems
    finally:
        app.dependency_overrides.pop(get_provider, None)


async def test_unsupported_attachment_type_rejected(client, auth_headers):
    agent_id = await _make_agent(client, auth_headers, "EXE")
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent_id}, headers=auth_headers)).json()
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/attachments",
        files={"file": ("evil.exe", io.BytesIO(b"MZ..."), "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 415


async def test_attachment_owner_isolation(client, auth_headers):
    from tests.test_sessions_api import make_user

    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "VL2", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/attachments",
        files={"file": ("a.png", io.BytesIO(b"\x89PNG" + b"0" * 16), "image/png")},
        headers=auth_headers,
    )
    att_id = r.json()["id"]
    other = await make_user(client, "bob")
    assert (await client.get(f"/api/v1/attachments/{att_id}", headers=other)).status_code == 404
