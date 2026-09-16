"""OCR 部署级 MCP 槽位与图片回合自动挂载（docs/设计/20）。"""

import io

import pytest

from app.ai import ocr
from app.ai.deps import get_provider
from app.ai.model_manager import ModelManager
from app.core.config import settings
from app.main import app
from app.services import mcp_service
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "OCR 助手",
    "system_prompt": "你是助手",
    "model_config": {"model": "m-text"},
    "tags": [],
    "examples": [],
}
OCR_URL = "https://ocr.example.com/mcp"
OCR_TOOL = {
    "name": "ocr",
    "description": "识别图片文字",
    "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}},
}
FUNC = "mcp__ocr__ocr"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _probe_ok():
    async def fake_probe(config):
        return mcp_service.ProbeResult(ok=True, tools=[dict(OCR_TOOL)], latency_ms=2)

    return fake_probe


@pytest.fixture(autouse=True)
def _clear_cache():
    ocr.reset_cache()
    yield
    ocr.reset_cache()


async def test_binding_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "ocr_mcp_url", "")
    assert ocr.is_enabled() is False
    assert await ocr.binding() is None


async def test_binding_returns_synthetic_http_binding(monkeypatch):
    monkeypatch.setattr(settings, "ocr_mcp_url", OCR_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())

    binding = await ocr.binding()
    assert binding is not None
    assert binding.server_name == ocr.SERVER_NAME
    assert binding.config["url"] == OCR_URL
    assert [tool["name"] for tool in binding.tools] == ["ocr"]


async def test_binding_none_when_probe_fails(monkeypatch):
    monkeypatch.setattr(settings, "ocr_mcp_url", OCR_URL)

    async def bad_probe(config):
        return mcp_service.ProbeResult(ok=False, error="down")

    monkeypatch.setattr(mcp_service, "probe", bad_probe)
    assert await ocr.binding() is None


async def test_image_turn_auto_attaches_ocr_tool(client, auth_headers, session_maker, monkeypatch):
    monkeypatch.setattr(settings, "ocr_mcp_url", OCR_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())

    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    session = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()
    att = (
        await client.post(
            f"/api/v1/sessions/{session['id']}/attachments",
            files={"file": ("pic.png", io.BytesIO(PNG), "image/png")},
            headers=auth_headers,
        )
    ).json()
    assert att["kind"] == "image"
    assert await ocr.binding() is not None

    provider = FakeProvider([("token", {"delta": "识别结果"})])
    app.dependency_overrides[get_provider] = lambda: provider
    app.state.model_manager = ModelManager(provider, session_factory=session_maker)
    try:
        resp = await client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            json={"content": "读出图里的文字", "attachment_ids": [att["id"]]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.state.model_manager = None

    # 会话未设标题时会追加一次"生成标题"调用，不能直接取 requests[-1]；按"含图片"定位视觉回合
    vision_requests = [
        req for req in provider.requests if req.messages and req.messages[-1].get("images")
    ]
    assert vision_requests, "未找到视觉回合请求"
    names = [tool["function"]["name"] for tool in (vision_requests[0].tools or [])]
    assert FUNC in names


async def test_text_turn_does_not_attach_ocr(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "ocr_mcp_url", OCR_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())

    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    session = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()

    provider = FakeProvider([("token", {"delta": "好的"})])
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "你好"},
        headers=auth_headers,
    )
    names = [tool["function"]["name"] for tool in (provider.requests[0].tools or [])]
    assert FUNC not in names


async def test_ocr_capabilities_endpoint(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "ocr_mcp_url", "")
    body = (await client.get("/api/v1/capabilities/ocr", headers=auth_headers)).json()
    assert body["enabled"] is False and body["healthy"] is False

    monkeypatch.setattr(settings, "ocr_mcp_url", OCR_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())
    body = (await client.get("/api/v1/capabilities/ocr", headers=auth_headers)).json()
    assert body["enabled"] is True and body["healthy"] is True
    assert body["tools"] == ["ocr"]
