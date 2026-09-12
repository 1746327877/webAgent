import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models import Attachment

logger = logging.getLogger(__name__)


async def cleanup_orphan_attachments(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    max_age_hours: int | None = None,
    upload_dir: str | None = None,
) -> int:
    """删除超时未绑定消息的待发附件（用户上传后未发送/上传中断）。

    先删文件再删行；脏 file_path 只删行，避免越界删除。
    """
    if session_factory is None:
        from app.core.db import SessionLocal

        session_factory = SessionLocal
    hours = settings.attachment_orphan_hours if max_age_hours is None else max_age_hours
    root = Path(upload_dir or settings.upload_dir)
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    async with session_factory() as db:
        rows = (
            await db.scalars(
                select(Attachment).where(
                    Attachment.message_id.is_(None), Attachment.created_at < cutoff
                )
            )
        ).all()
        removed = 0
        for att in rows:
            if "/" not in att.file_path and "\\" not in att.file_path:
                try:
                    (root / att.file_path).unlink(missing_ok=True)
                except OSError as exc:
                    # 单文件失败（如 Windows 文件占用）不拖垮整批；保留行下轮重试
                    logger.warning(
                        "附件清理失败，保留待重试 file=%s error=%s", att.file_path, exc
                    )
                    continue
            await db.delete(att)
            removed += 1
        await db.commit()
        return removed
