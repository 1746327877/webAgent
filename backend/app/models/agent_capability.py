import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentSkill(Base):
    """智能体绑定的 Skill（slug 指向代码里的静态清单，不入库内容）。"""

    __tablename__ = "agent_skills"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    skill_slug: Mapped[str] = mapped_column(String(64), primary_key=True)


class AgentMcpTool(Base):
    """智能体绑定的 MCP 工具，精确到 tool 粒度。"""

    __tablename__ = "agent_mcp_tools"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    mcp_server_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="CASCADE"), primary_key=True
    )
    tool_name: Mapped[str] = mapped_column(String(128), primary_key=True)
