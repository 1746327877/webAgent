import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Artifact(Base):
    """会话产物：平台/工具生成的、可预览与下载的文件（见 `docs/设计/24-会话产物.md`）。

    与 `Attachment` 分开建模：附件是"用户传上来的"，产物是"平台/工具生成出来的"，
    且产物**不参与附件孤儿回收**（没有 message_id、不会被 GC 清掉）。
    """

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    # 产物来源：export=平台导出（当前只有这个）/ tool=内置工具产出 / mcp=MCP 产出
    source: Mapped[str] = mapped_column(String(16), default="export")
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    # 落盘名恒为 "{uuid}.{ext}"（落在 settings.upload_dir），与 Attachment 同一约定
    file_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
