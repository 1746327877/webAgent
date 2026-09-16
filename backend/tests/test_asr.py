"""语音转写 MCP 客户端、能力状态与音频附件校验（docs/设计/23）。"""

import io

import pytest

from app.ai import asr
from app.ai.mcp_slot import McpSlot
from app.core.config import settings
from app.services import mcp_service

ASR_URL = "https://asr.example.com/mcp"
TRANSCRIBE_TOOL = {
    "name": "transcribe_audio_by_storage_key_tool",
    "description": "转写音频",
    "input_schema": {"type": "object", "properties": {"paths": {"type": "array"}}},
}


def _probe_ok(tools=None):
    async def fake_probe(config):
        return mcp_service.ProbeResult(ok=True, tools=[dict(t) for t in (tools or [TRANSCRIBE_TOOL])], latency_ms=2)

    return fake_probe


@pytest.fixture(autouse=True)
def _clear_cache():
    asr.reset_cache()
    yield
    asr.reset_cache()


# ---- 客户端 ----


async def test_transcribe_degrades_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "asr_mcp_url", "")
    assert asr.is_enabled() is False
    assert await asr.binding() is None
    with pytest.raises(asr.AsrError):
        await asr.transcribe(["/data/uploads/a.mp3"])


async def test_transcribe_picks_tool_containing_transcribe(monkeypatch):
    monkeypatch.setattr(settings, "asr_mcp_url", ASR_URL)
    monkeypatch.setattr(settings, "asr_mcp_tool", "")
    monkeypatch.setattr(
        mcp_service,
        "probe",
        _probe_ok(
            [
                {"name": "health", "input_schema": {}},
                TRANSCRIBE_TOOL,
            ]
        ),
    )
    calls: dict = {}

    async def fake_call(config, name, arguments):
        calls.update({"name": name, "args": arguments})
        return ('[{"path": "/data/uploads/a.mp3", "success": true, "text": "你好"}]', "ok")

    monkeypatch.setattr(mcp_service, "call_tool", fake_call)

    result = await asr.transcribe(["/data/uploads/a.mp3"])
    assert calls["name"] == TRANSCRIBE_TOOL["name"]
    assert calls["args"] == {"paths": ["/data/uploads/a.mp3"]}
    assert result == [{"path": "/data/uploads/a.mp3", "success": True, "text": "你好", "error": None}]


async def test_transcribe_respects_configured_tool(monkeypatch):
    monkeypatch.setattr(settings, "asr_mcp_url", ASR_URL)
    monkeypatch.setattr(settings, "asr_mcp_tool", "my_tool")
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())
    seen: list[str] = []

    async def fake_call(config, name, arguments):
        seen.append(name)
        return ('[{"path": "p", "success": true, "text": "x"}]', "ok")

    monkeypatch.setattr(mcp_service, "call_tool", fake_call)
    await asr.transcribe(["p"])
    assert seen == ["my_tool"]


async def test_transcribe_errors_when_no_tool_matches(monkeypatch):
    monkeypatch.setattr(settings, "asr_mcp_url", ASR_URL)
    monkeypatch.setattr(settings, "asr_mcp_tool", "")
    monkeypatch.setattr(mcp_service, "probe", _probe_ok([{"name": "health", "input_schema": {}}]))
    with pytest.raises(asr.AsrError):
        await asr.transcribe(["p"])


async def test_transcribe_raises_on_call_failure(monkeypatch):
    monkeypatch.setattr(settings, "asr_mcp_url", ASR_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())

    async def fake_call(config, name, arguments):
        return ("连接超时", "error")

    monkeypatch.setattr(mcp_service, "call_tool", fake_call)
    with pytest.raises(asr.AsrError):
        await asr.transcribe(["p"])


def test_normalize_accepts_plain_text_and_storage_key():
    # 裸文本 → 视为单文件结果；storage_key 字段名兼容参考实现
    assert asr._normalize(" 转写出来的文字 ", ["p"]) == [
        {"path": "p", "success": True, "text": "转写出来的文字", "error": None}
    ]
    items = asr._normalize('[{"storage_key": "k", "success": true, "text": "t"}]', ["p"])
    assert items[0]["path"] == "k"


def test_normalize_empty_raises():
    with pytest.raises(asr.AsrError):
        asr._normalize("   ", ["p"])


def test_slot_server_name_is_voice_asr():
    assert asr.SERVER_NAME == "voice-asr"
    assert isinstance(asr._slot, McpSlot)


# ---- 能力状态 ----


async def test_capabilities_asr_endpoint(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "asr_mcp_url", "")
    body = (await client.get("/api/v1/capabilities/asr", headers=auth_headers)).json()
    assert body["enabled"] is False and body["healthy"] is False

    monkeypatch.setattr(settings, "asr_mcp_url", ASR_URL)
    monkeypatch.setattr(mcp_service, "probe", _probe_ok())
    body = (await client.get("/api/v1/capabilities/asr", headers=auth_headers)).json()
    assert body["enabled"] is True and body["healthy"] is True
    assert body["tools"] == [TRANSCRIBE_TOOL["name"]]


# ---- 音频附件校验 ----


async def _new_session(client, auth_headers):
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "ASR", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    return (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()


_MP3 = b"ID3\x03\x00\x00\x00" + b"0" * 64


async def test_audio_attachment_accepted_with_kind_audio(client, auth_headers):
    session = await _new_session(client, auth_headers)
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/attachments",
        files={"file": ("voice.mp3", io.BytesIO(_MP3), "audio/mpeg")},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "audio"


async def test_audio_attachment_rejects_non_audio_content(client, auth_headers):
    session = await _new_session(client, auth_headers)
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/attachments",
        files={"file": ("fake.mp3", io.BytesIO(b"this is not audio"), "audio/mpeg")},
        headers=auth_headers,
    )
    assert r.status_code == 415
    assert "不像音频" in r.json()["detail"]


async def test_audio_attachment_too_large(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "asr_max_bytes", 16)
    session = await _new_session(client, auth_headers)
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/attachments",
        files={"file": ("voice.mp3", io.BytesIO(_MP3), "audio/mpeg")},
        headers=auth_headers,
    )
    assert r.status_code == 413
    assert "音频超过" in r.json()["detail"]


def test_webm_renamed_to_mp3_still_detected_as_audio():
    from app.core.upload_rules import has_valid_audio_magic

    webm = b"\x1a\x45\xdf\xa3" + b"0" * 32
    assert has_valid_audio_magic(webm, "mp3") is True
    assert has_valid_audio_magic(b"plain text", "mp3") is False
    assert has_valid_audio_magic(webm, "txt") is False
