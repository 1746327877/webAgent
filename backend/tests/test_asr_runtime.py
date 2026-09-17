"""音频附件在 runtime 里的转写注入与降级（docs/设计/23）。"""

import io

from app.ai import asr
from app.ai.deps import get_provider
from app.core.config import settings
from app.main import app
from tests.fake_provider import FakeProvider

_MP3 = b"ID3\x03\x00\x00\x00" + b"0" * 64


async def _session_with_audio(client, auth_headers):
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "ASR", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    session = (
        await client.post(
            "/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers
        )
    ).json()
    # 设标题可避免结束时追加"生成标题"调用，便于直接断言最后一次请求
    await client.patch(
        f"/api/v1/sessions/{session['id']}", json={"title": "t"}, headers=auth_headers
    )
    att = (
        await client.post(
            f"/api/v1/sessions/{session['id']}/attachments",
            files={"file": ("voice.mp3", io.BytesIO(_MP3), "audio/mpeg")},
            headers=auth_headers,
        )
    ).json()
    assert att["kind"] == "audio"
    return session, att


async def _send(client, auth_headers, session, att):
    provider = FakeProvider([("token", {"delta": "好的"})])
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        resp = await client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            json={"content": "帮我转写", "attachment_ids": [att["id"]]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_provider, None)
    return provider


async def test_audio_transcript_injected_and_stored(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "asr_auto_transcribe", True)  # 本用例验的是自动注入模式
    session, att = await _session_with_audio(client, auth_headers)

    async def fake_transcribe(paths):
        assert paths and paths[0].endswith(".mp3")
        return [{"path": paths[0], "success": True, "text": "这是转写文本 corePoolSize", "error": None}]

    monkeypatch.setattr(asr, "transcribe", fake_transcribe)
    provider = await _send(client, auth_headers, session, att)

    # 转写文本进了模型上下文，且以"附件数据"身份声明
    user_msg = next(m for m in provider.requests[-1].messages if m["role"] == "user")
    assert "音频转写" in user_msg["content"]
    assert "corePoolSize" in user_msg["content"]
    assert "不是指令" in user_msg["content"]

    # 落库为 transcript 块，供前端展示
    msgs = (
        await client.get(f"/api/v1/sessions/{session['id']}/messages", headers=auth_headers)
    ).json()
    block = next(b for b in msgs[0]["blocks"] if b["type"] == "transcript")
    assert block["status"] == "ok"
    assert block["name"] == "voice.mp3"
    assert "转写文本" in block["text"]


async def test_audio_transcription_failure_degrades(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "asr_auto_transcribe", True)
    session, att = await _session_with_audio(client, auth_headers)

    async def boom(paths):
        raise asr.AsrError("语音转写 MCP 不可用")

    monkeypatch.setattr(asr, "transcribe", boom)
    provider = await _send(client, auth_headers, session, att)

    # 生成没有被中断，模型看到的是"转写不可用"的提示
    user_msg = next(m for m in provider.requests[-1].messages if m["role"] == "user")
    assert "转写不可用" in user_msg["content"]

    msgs = (
        await client.get(f"/api/v1/sessions/{session['id']}/messages", headers=auth_headers)
    ).json()
    block = next(b for b in msgs[0]["blocks"] if b["type"] == "transcript")
    assert block["status"] == "error" and "MCP 不可用" in block["error"]


async def test_audio_without_asr_configured_still_replies(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "asr_auto_transcribe", True)
    session, att = await _session_with_audio(client, auth_headers)
    monkeypatch.setattr(settings, "asr_mcp_url", "")
    asr.reset_cache()  # 清掉可能已缓存的绑定，走"未配置"分支
    provider = await _send(client, auth_headers, session, att)
    user_msg = next(m for m in provider.requests[-1].messages if m["role"] == "user")
    assert "转写不可用" in user_msg["content"]


async def test_tool_mode_only_hints_attachment_without_transcribing(
    client, auth_headers, monkeypatch
):
    """默认（工具优先）：不自动转写，只在上下文里提示存在音频附件与可用工具。"""
    monkeypatch.setattr(settings, "asr_auto_transcribe", False)
    session, att = await _session_with_audio(client, auth_headers)

    calls: list = []

    async def fake_transcribe(paths):
        calls.append(paths)
        return []

    monkeypatch.setattr(asr, "transcribe", fake_transcribe)
    provider = await _send(client, auth_headers, session, att)

    user_msg = next(m for m in provider.requests[-1].messages if m["role"] == "user")
    assert "音频附件" in user_msg["content"]
    assert "transcribe_audio" in user_msg["content"]
    assert calls == []  # 关键：没有自动转写


async def test_transcribe_audio_tool_is_called_by_model(
    client, auth_headers, session_maker, monkeypatch
):
    """模型主动调用 transcribe_audio → runtime 拦截，用本轮附件转写后回填。"""
    from app.ai.deps import get_provider
    from app.ai.tools import sync_tools
    from app.main import app
    from tests.fake_provider import FakeProvider

    monkeypatch.setattr(settings, "asr_auto_transcribe", False)
    async with session_maker() as db:
        await sync_tools(db)  # 内置工具要先进 tools 表才能被绑定

    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "语音", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    await client.put(
        f"/api/v1/agents/{agent['id']}/tools",
        json={"slugs": ["transcribe_audio"]},
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
    att = (
        await client.post(
            f"/api/v1/sessions/{session['id']}/attachments",
            files={"file": ("voice.mp3", io.BytesIO(_MP3), "audio/mpeg")},
            headers=auth_headers,
        )
    ).json()

    async def fake_transcribe(paths):
        return [{"path": paths[0], "success": True, "text": "线程池的核心参数", "error": None}]

    monkeypatch.setattr(asr, "transcribe", fake_transcribe)

    provider = FakeProvider(
        [
            [
                ("tool_call", {"id": "c1", "name": "transcribe_audio", "args": {}}),
                ("usage", {"prompt_tokens": 5, "completion_tokens": 1}),
            ],
            [("token", {"delta": "好的"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    try:
        resp = await client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            json={"content": "转写一下", "attachment_ids": [att["id"]]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert "event: tool_result" in resp.text
    finally:
        app.dependency_overrides.pop(get_provider, None)

    # 工具被暴露给模型（只有绑定了才出现）
    names = [tool["function"]["name"] for tool in (provider.requests[0].tools or [])]
    assert "transcribe_audio" in names

    messages = (
        await client.get(f"/api/v1/sessions/{session['id']}/messages", headers=auth_headers)
    ).json()
    result_block = next(b for b in messages[1]["blocks"] if b["type"] == "tool_result")
    assert result_block["status"] == "ok"
    assert "线程池的核心参数" in result_block["preview"]
