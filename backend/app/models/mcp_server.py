import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class McpServer(Base):
    """用户手动接入的 MCP Server。

    http：url + headers；stdio：command + args + env。
    `tools` / `status` / `last_error` / `last_checked_at` 由测试连接写回。
    注意：headers 可能含 API Key，当前明文存储，仅返回给所有者本人。
    """

    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_mcp_servers_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    transport: Mapped[str] = mapped_column(String(16))  # http | stdio
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    headers: Mapped[dict] = mapped_column(JSONB, default=dict)
    command: Mapped[str | None] = mapped_column(String(256), nullable=True)
    args: Mapped[list] = mapped_column(JSONB, default=list)
    env: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # unknown | ok | error
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools: Mapped[list] = mapped_column(JSONB, default=list)  # [{name, description}]
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
