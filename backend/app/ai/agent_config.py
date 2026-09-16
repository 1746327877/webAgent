import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.skills import SKILL_REGISTRY
from app.core.config import settings
from app.models import Agent, AgentMcpTool, AgentSkill, AgentTool, McpServer, Session, Tool
from app.services.mcp_service import server_config

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
class McpBinding:
    server_id: uuid.UUID
    server_name: str
    config: dict
    tools: list[dict] = field(default_factory=list)


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
    skill_slugs: list[str] = field(default_factory=list)
    mcp_bindings: list[McpBinding] = field(default_factory=list)


def _compose_prompt(base: str, skill_slugs: list[str]) -> str:
    skills = [SKILL_REGISTRY[slug] for slug in skill_slugs if slug in SKILL_REGISTRY]
    if not skills:
        return base
    sections = "\n\n".join(f"### {skill.name}\n{skill.instructions}" for skill in skills)
    return f"{base}\n\n## 已启用能力\n{sections}".strip()


async def _load_mcp_bindings(db: AsyncSession, agent_id) -> list[McpBinding]:
    rows = (
        await db.execute(
            select(AgentMcpTool.mcp_server_id, AgentMcpTool.tool_name, McpServer)
            .join(McpServer, McpServer.id == AgentMcpTool.mcp_server_id)
            .where(AgentMcpTool.agent_id == agent_id, McpServer.enabled.is_(True))
            .order_by(AgentMcpTool.mcp_server_id, AgentMcpTool.tool_name)
        )
    ).all()

    servers: dict[uuid.UUID, McpServer] = {}
    grouped: dict[uuid.UUID, list[str]] = {}
    for server_id, tool_name, server in rows:
        servers[server_id] = server
        grouped.setdefault(server_id, []).append(tool_name)

    bindings: list[McpBinding] = []
    for server_id, tool_names in grouped.items():
        server = servers[server_id]
        cached = {str(t.get("name")): t for t in (server.tools or [])}
        tools = []
        for name in tool_names:
            entry = cached.get(name) or {}
            tools.append(
                {
                    "name": name,
                    "description": entry.get("description", ""),
                    "input_schema": entry.get("input_schema")
                    or {"type": "object", "properties": {}},
                }
            )
        bindings.append(
            McpBinding(
                server_id=server_id,
                server_name=server.name,
                config=server_config(server),
                tools=tools,
            )
        )
    return bindings


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
    skill_slugs = list(
        (
            await db.scalars(
                select(AgentSkill.skill_slug)
                .where(AgentSkill.agent_id == agent.id)
                .order_by(AgentSkill.skill_slug)
            )
        ).all()
    )
    prompt = render_prompt(
        agent.system_prompt,
        user_name=user_name,
        session_title=session.title,
        agent_name=agent.name,
    )
    return EffectiveConfig(
        agent_id=agent.id,
        agent_version=agent.current_version,
        model=cfg.get("model", settings.default_model),
        temperature=float(cfg.get("temperature", 0.7)),
        top_p=float(cfg.get("top_p", 0.9)),
        max_tokens=int(cfg.get("max_tokens", 2048)),
        num_ctx=int(cfg.get("num_ctx", 8192)),
        history_rounds=int(cfg.get("history_rounds", settings.history_rounds)),
        system_prompt=_compose_prompt(prompt, skill_slugs),
        tool_slugs=list(slugs),
        skill_slugs=skill_slugs,
        mcp_bindings=await _load_mcp_bindings(db, agent.id),
    )


async def resolve_effective_config(
    db: AsyncSession, session: Session, *, user_name: str
) -> EffectiveConfig:
    if session.agent_id is None:
        return EffectiveConfig()
    agent = await db.get(Agent, session.agent_id)
    return await build_agent_config(db, agent, session, user_name)
