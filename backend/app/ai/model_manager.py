import asyncio
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.providers.base import ModelProvider
from app.core.config import settings
from app.models import ModelEvent


class ModelManager:
    """单活跃槽位：同一时刻至多一个 LLM 处于 LOADING/LOADED。"""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        self.provider = provider
        self._factory = session_factory
        self._lock = asyncio.Lock()
        self._current: str | None = None
        self.last_snapshot: dict = {"loaded": [], "vram_mb": 0, "updated_at": None}

    @property
    def current(self) -> str | None:
        return self._current

    async def _log(self, model: str, action: str, trigger: str | None, **extra) -> None:
        from app.core.db import SessionLocal

        factory = self._factory or SessionLocal
        async with factory() as db:
            db.add(ModelEvent(model=model, action=action, trigger=trigger, **extra))
            await db.commit()

    async def _vram_mb(self) -> int | None:
        try:
            loaded = await self.provider.list_loaded()
            return int(sum(m.size_vram_mb for m in loaded))
        except Exception:  # noqa: BLE001
            return None

    async def acquire(self, model: str, *, trigger: str = "auto_switch") -> dict:
        async with self._lock:
            if self._current == model:
                return {"switched": False, "from": model, "to": model, "duration_ms": 0}
            prev = self._current
            vram_before = await self._vram_mb()
            if prev is not None:
                await self.provider.unload(prev)
                await self._log(prev, "unload", trigger, vram_before_mb=vram_before)
                self._current = None
            t0 = time.monotonic()
            try:
                await self.provider.ensure_loaded(model)
            except Exception as exc:
                await self._log(model, "load_failed", trigger, error=str(exc)[:300])
                raise
            duration = int((time.monotonic() - t0) * 1000)
            self._current = model
            await self._log(
                model,
                "load",
                trigger,
                duration_ms=duration,
                vram_before_mb=vram_before,
                vram_after_mb=await self._vram_mb(),
            )
            return {"switched": True, "from": prev, "to": model, "duration_ms": duration}

    async def watch(self) -> None:
        while True:
            try:
                loaded = await self.provider.list_loaded()
                self.last_snapshot = {
                    "loaded": [
                        {"name": m.name, "size_vram_mb": m.size_vram_mb, "expires_at": m.expires_at}
                        for m in loaded
                    ],
                    "vram_mb": int(sum(m.size_vram_mb for m in loaded)),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            except Exception:  # noqa: BLE001, S110 —— 轮询失败保持旧快照，下轮重试
                pass
            await asyncio.sleep(settings.vram_poll_seconds)

    async def status(self) -> dict:
        loaded = await self.provider.list_loaded()
        return {
            "current": self._current,
            "loaded": [
                {"name": m.name, "size_vram_mb": m.size_vram_mb, "expires_at": m.expires_at}
                for m in loaded
            ],
            "last_snapshot": self.last_snapshot,
        }
