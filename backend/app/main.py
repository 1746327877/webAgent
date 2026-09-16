import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.model_manager import ModelManager
from app.ai.providers.ollama import OllamaProvider
from app.ai.runtime import recover_stale_streaming
from app.api.v1.openai_compat import router as openai_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging
from app.observability.http_stats import collector
from app.services.attachment_service import cleanup_orphan_attachments

logger = logging.getLogger("app")


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
    configure_logging()
    logger.info("启动中：Ollama=%s 日志级别=%s", settings.ollama_base_url, settings.log_level)
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底：未处理异常打完整堆栈到日志，返回统一 JSON。"""
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请查看后端日志"})


app.include_router(api_router)
app.include_router(openai_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
