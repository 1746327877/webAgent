from typing import ClassVar

from arq.connections import RedisSettings

from app.core.config import settings


async def ingest_job(ctx, document_id: str) -> None:
    # 延迟导入：pipeline 由 Task 4 提供，避免 worker 启动时因模块缺失而失败
    from app.ai.rag.pipeline import run_ingest

    await run_ingest(document_id)


class WorkerSettings:
    functions: ClassVar[list] = [ingest_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
