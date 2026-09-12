import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Agent, AgentTool, Session, Tool

VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def render_prompt(template: str, *, user_name: str, session_title: str, agent_name: str) -> str:
    today = __import__("datetime").date.today().isoformat()
    resolvers = {
        "user.name": user_name,
        "session.title": session_title,
        "agent.name": agent_name,
        "today": today,
    }

    def sub(m: re.Match) -> str:
        return resolvers.get(m.group(1), m.group(0))

    return VAR_RE.sub(sub, template or "")


@dataclass
class EffectiveConfig:
    agent_id: uuid.UUID | None = None
    agent_version: int | None = None
    model: str = field(default_factory=lambda: settings.default_model)
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048
    num_ctx: int = 8192
    history_rounds: int = field(default_factory=lambda: settings.history_rounds)
    system_prompt: str = ""
    tool_slugs: list[str] = field(default_factory=list)


async def build_agent_config(
    db: AsyncSession, agent: Agent | None, session: Session, user_name: str
) -> EffectiveConfig:
    """由显式加载的智能体构建有效配置；agent 为空时回退默认配置。"""
    if agent is None:
        return EffectiveConfig()
    cfg = agent.model_config or {}
    slugs = (
        await db.scalars(
            select(Tool.slug)
            .join(AgentTool, AgentTool.tool_id == Tool.id)
            .where(AgentTool.agent_id == agent.id, Tool.enabled.is_(True))
            .order_by(Tool.slug)
        )
    ).all()
    return EffectiveConfig(
        agent_id=agent.id,
        agent_version=agent.current_version,
        model=cfg.get("model", settings.default_model),
        temperature=float(cfg.get("temperature", 0.7)),
        top_p=float(cfg.get("top_p", 0.9)),
        max_tokens=int(cfg.get("max_tokens", 2048)),
        num_ctx=int(cfg.get("num_ctx", 8192)),
        history_rounds=int(cfg.get("history_rounds", settings.history_rounds)),
        system_prompt=render_prompt(
            agent.system_prompt,
            user_name=user_name,
            session_title=session.title,
            agent_name=agent.name,
        ),
        tool_slugs=list(slugs),
    )


async def resolve_effective_config(
    db: AsyncSession, session: Session, *, user_name: str
) -> EffectiveConfig:
    if session.agent_id is None:
        return EffectiveConfig()
    agent = await db.get(Agent, session.agent_id)
    return await build_agent_config(db, agent, session, user_name)
