import uuid

from app.ai.deps import get_provider
from app.ai.model_manager import ModelManager
from app.ai.runtime import CANCEL_FLAGS, CANCEL_SESSIONS
from app.main import app
from app.models import Message
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "停止测试",
    "system_prompt": "",
    "model_config": {"model": "m"},
    "tags": [],
    "examples": [],
}


class BrokenFactory:
    """模拟观测库不可用：session 工厂直接抛错。"""

    def __call__(self):
        raise RuntimeError("db down")


async def test_status_falls_back_to_snapshot_when_provider_down(session_maker):
    class DownProvider(FakeProvider):
        async def list_loaded(self):
            raise RuntimeError("connection refused")

    mm = ModelManager(DownProvider(), session_factory=session_maker)
    mm.last_snapshot = {
        "loaded": [{"name": "qwen2.5:7b", "size_vram_mb": 6000.0, "expires_at": None}],
        "vram_mb": 6000,
        "updated_at": "2026-09-12T00:00:00+00:00",
    }
    mm._current = "qwen2.5:7b"
    info = await mm.status()
    assert info["current"] == "qwen2.5:7b"
    assert info["loaded"][0]["name"] == "qwen2.5:7b"  # 回退快照
    assert info["degraded"] is True
    assert info["last_snapshot"]["vram_mb"] == 6000


async def test_acquire_survives_log_failure():
    mm = ModelManager(FakeProvider(), session_factory=BrokenFactory())
    first = await mm.acquire("a")
    assert first["switched"] is True and mm.current == "a"
    # unload 成功 + 记账失败：槽位必须已经清空，第二步切换才能正确驱逐
    second = await mm.acquire("b")
    assert second["from"] == "a" and mm.current == "b"


async def test_watch_once_appends_vram_history():
    class LoadedProvider(FakeProvider):
        async def list_loaded(self):
            from app.ai.providers.base import LoadedModel

            return [LoadedModel(name="a", size_vram_mb=6000.0)]

    mm = ModelManager(LoadedProvider())
    await mm.watch_once()
    assert mm.vram_history[-1]["vram_mb"] == 6000
    assert mm.last_snapshot["vram_mb"] == 6000


async def _streaming_assistant(session_maker, session_id):
    async with session_maker() as db:
        m = Message(session_id=uuid.UUID(session_id), role="assistant", status="streaming", blocks=[])
        db.add(m)
        await db.commit()
        await db.refresh(m)
    return m


async def test_stop_sets_session_cancel(client, auth_headers, session_maker):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    m = await _streaming_assistant(session_maker, s["id"])
    try:
        r = await client.post(f"/api/v1/messages/{m.id}/stop", headers=auth_headers)
        assert r.status_code == 200
        assert CANCEL_FLAGS.get(m.id) is True
        assert uuid.UUID(s["id"]) in CANCEL_SESSIONS
    finally:
        CANCEL_FLAGS.pop(m.id, None)
        CANCEL_SESSIONS.discard(uuid.UUID(s["id"]))


class CancelInjectProvider(FakeProvider):
    """首回合开始即注入会话级取消，模拟「接力排队期间用户点了停止」。"""

    def __init__(self, script, session_id):
        super().__init__(script)
        self.session_id = session_id

    def chat_stream(self, req):
        CANCEL_SESSIONS.add(self.session_id)
        return super().chat_stream(req)


async def test_queued_relay_skipped_after_session_cancel(client, auth_headers):
    a = (await client.post("/api/v1/agents", json={**AGENT, "name": "甲"}, headers=auth_headers)).json()
    b = (await client.post("/api/v1/agents", json={**AGENT, "name": "乙"}, headers=auth_headers)).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": a["id"]}, headers=auth_headers)).json()
    provider = CancelInjectProvider([("token", {"delta": "A答"})], uuid.UUID(s["id"]))
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages",
        json={"content": "问题", "mentions": [b["id"]]},
        headers=auth_headers,
    )
    assert r.text.count("event: message_start") == 1
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    assert len([m for m in msgs if m["role"] == "assistant"]) == 1
    assert uuid.UUID(s["id"]) not in CANCEL_SESSIONS  # 标记被接力检查消费
