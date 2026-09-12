import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.model_manager import ModelManager
from app.ai.providers.ollama import OllamaProvider
from app.ai.runtime import recover_stale_streaming
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import SessionLocal
from app.observability.http_stats import collector
from app.services.attachment_service import cleanup_orphan_attachments


async def _http_stats_flush_loop() -> None:
    while True:
        await asyncio.sleep(60)
        await collector.flush()


async def _attachment_gc_loop() -> None:
    while True:
        try:
            await cleanup_orphan_attachments()
        except Exception:  # noqa: BLE001, S110 —— 清理失败下一轮重试，不得拖垮进程
            pass
        await asyncio.sleep(settings.attachment_gc_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    app.state.provider = OllamaProvider(settings.ollama_base_url)
    app.state.model_manager = ModelManager(app.state.provider)
    watch_task = asyncio.create_task(app.state.model_manager.watch())
    await recover_stale_streaming()

    from app.ai.tools import sync_tools

    async with SessionLocal() as db:
        await sync_tools(db)
    gc_task = asyncio.create_task(_attachment_gc_loop())
    flush_task = asyncio.create_task(_http_stats_flush_loop())
    try:
        yield
    finally:
        for task in (watch_task, gc_task, flush_task):
            task.cancel()
        for task in (watch_task, gc_task, flush_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await collector.flush()  # 退出前最后落一次盘（best-effort）
        await app.state.provider.aclose()


app = FastAPI(title="WebAgent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def http_metrics_middleware(request, call_next):
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        collector.record(500, (time.perf_counter() - t0) * 1000)
        raise
    collector.record(response.status_code, (time.perf_counter() - t0) * 1000)
    return response


app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
