import asyncio

from sqlalchemy import select

from app.ai.model_manager import ModelManager
from app.models import ModelEvent
from tests.fake_provider import FakeProvider


class RecordingProvider(FakeProvider):
    """记录调用序列；可注入加载失败。"""

    def __init__(self, script=None, fail_on: set[str] | None = None):
        super().__init__(script)
        self.calls: list[tuple] = []
        self.fail_on = fail_on or set()

    async def ensure_loaded(self, model: str) -> float:
        self.calls.append(("ensure", model))
        if model in self.fail_on:
            raise RuntimeError("oom")
        return 10.0

    async def unload(self, model: str) -> None:
        self.calls.append(("unload", model))

    async def list_loaded(self):
        from app.ai.providers.base import LoadedModel

        return [LoadedModel(name="x", size_vram_mb=6000.0)] if self.calls else []


async def test_acquire_first_model_logs_load(session_maker):
    p = RecordingProvider()
    mm = ModelManager(p, session_factory=session_maker)
    info = await mm.acquire("qwen2.5:7b")
    assert info["switched"] is True and info["from"] is None
    assert ("ensure", "qwen2.5:7b") in p.calls
    async with session_maker() as db:
        rows = (await db.scalars(select(ModelEvent))).all()
    assert any(r.action == "load" and r.model == "qwen2.5:7b" for r in rows)


async def test_acquire_switch_unloads_previous(session_maker):
    p = RecordingProvider()
    mm = ModelManager(p, session_factory=session_maker)
    await mm.acquire("a")
    info = await mm.acquire("b")
    assert info["from"] == "a" and mm.current == "b"
    assert p.calls == [("ensure", "a"), ("unload", "a"), ("ensure", "b")]
    # 同模型命中：不再有调用
    await mm.acquire("b")
    assert p.calls == [("ensure", "a"), ("unload", "a"), ("ensure", "b")]


async def test_acquire_failure_logs_and_raises(session_maker):
    p = RecordingProvider(fail_on={"bad"})
    mm = ModelManager(p, session_factory=session_maker)
    import pytest

    with pytest.raises(RuntimeError):
        await mm.acquire("bad")
    assert mm.current is None
    async with session_maker() as db:
        row = (
            await db.scalars(select(ModelEvent).where(ModelEvent.action == "load_failed"))
        ).first()
    assert row is not None and row.model == "bad"


async def test_acquire_serializes_concurrent_switches(session_maker):
    p = RecordingProvider()
    mm = ModelManager(p, session_factory=session_maker)
    await asyncio.gather(mm.acquire("a"), mm.acquire("b"), mm.acquire("a"))
    ensures = [c[1] for c in p.calls if c[0] == "ensure"]
    unloads = [c[1] for c in p.calls if c[0] == "unload"]
    assert len(ensures) == 3 and len(unloads) == 2
    assert mm.current == "a"
    # 同一时刻至多一个驻留：ensure/unload 严格交替
    for prev, nxt in zip(p.calls, p.calls[1:]):
        assert not (prev[0] == "ensure" and nxt[0] == "ensure")
