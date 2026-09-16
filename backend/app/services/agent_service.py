import re
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.skills import SKILL_REGISTRY
from app.models import (
    Agent,
    AgentKB,
    AgentMcpTool,
    AgentSkill,
    AgentTool,
    AgentVersion,
    KnowledgeBase,
    McpServer,
    Message,
    Session,
    Tool,
)
from app.models.user import User

VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def extract_variables(prompt: str) -> list[str]:
    return sorted(set(VAR_RE.findall(prompt or "")))


async def get_owned_agent(db: AsyncSession, user: User, agent_id: uuid.UUID) -> Agent:
    agent = await db.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.owner_id == user.id)
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="智能体不存在")
    return agent


async def list_agents(db: AsyncSession, user: User) -> list[Agent]:
    rows = (
        await db.scalars(
            select(Agent)
            .where(Agent.owner_id == user.id)
            .order_by(Agent.updated_at.desc(), Agent.created_at.desc())
        )
    ).all()
    return list(rows)


async def create_agent(db: AsyncSession, user: User, data) -> Agent:
    agent = Agent(
        owner_id=user.id,
        name=data.name,
        emoji=data.emoji,
        description=data.description,
        tags=data.tags,
        system_prompt=data.system_prompt,
        model_config=data.model_cfg.model_dump(),
        welcome_msg=data.welcome_msg,
        examples=data.examples,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def update_agent(db: AsyncSession, agent: Agent, fields: dict) -> Agent:
    for key, value in fields.items():
        if value is None:
            continue
        if key == "model_config":
            value = value.model_dump() if hasattr(value, "model_dump") else value
        setattr(agent, key, value)
    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    used = await db.scalar(select(Message.id).where(Message.agent_id == agent.id).limit(1))
    if used is None:
        used = await db.scalar(select(Session.id).where(Session.agent_id == agent.id).limit(1))
    if used is not None:
        raise HTTPException(status_code=409, detail="该智能体已被会话使用，请改为归档")
    await db.delete(agent)
    await db.commit()


async def _tool_slugs(db: AsyncSession, agent_id) -> list[str]:
    rows = (
        await db.scalars(
            select(Tool.slug)
            .join(AgentTool, AgentTool.tool_id == Tool.id)
            .where(AgentTool.agent_id == agent_id, Tool.enabled.is_(True))
            .order_by(Tool.slug)
        )
    ).all()
    return list(rows)


async def set_tools(db: AsyncSession, agent: Agent, slugs: list[str]) -> list[str]:
    slugs = list(dict.fromkeys(slugs))
    await db.execute(delete(AgentTool).where(AgentTool.agent_id == agent.id))
    bound: list[str] = []
    for slug in slugs:
        tool = await db.scalar(select(Tool).where(Tool.slug == slug, Tool.enabled.is_(True)))
        if tool is not None:
            db.add(AgentTool(agent_id=agent.id, tool_id=tool.id))
            bound.append(slug)
    await db.commit()
    return bound


async def _skill_slugs(db: AsyncSession, agent_id) -> list[str]:
    rows = (
        await db.scalars(
            select(AgentSkill.skill_slug)
            .where(AgentSkill.agent_id == agent_id)
            .order_by(AgentSkill.skill_slug)
        )
    ).all()
    return list(rows)


async def set_skills(db: AsyncSession, agent: Agent, slugs: list[str]) -> list[str]:
    slugs = list(dict.fromkeys(slugs))
    unknown = [slug for slug in slugs if slug not in SKILL_REGISTRY]
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知的 Skill：{', '.join(unknown)}")
    await db.execute(delete(AgentSkill).where(AgentSkill.agent_id == agent.id))
    for slug in slugs:
        db.add(AgentSkill(agent_id=agent.id, skill_slug=slug))
    await db.commit()
    return sorted(slugs)


async def list_mcp_tools(db: AsyncSession, agent_id) -> list[dict]:
    rows = (
        await db.execute(
            select(AgentMcpTool.mcp_server_id, AgentMcpTool.tool_name)
            .where(AgentMcpTool.agent_id == agent_id)
            .order_by(AgentMcpTool.mcp_server_id, AgentMcpTool.tool_name)
        )
    ).all()
    return [
        {"mcp_server_id": str(row.mcp_server_id), "tool_name": row.tool_name} for row in rows
    ]


async def set_mcp_tools(db: AsyncSession, agent: Agent, user: User, bindings: list) -> list[dict]:
    """替换语义：校验 server 归属与 tool 名在缓存列表中，再整体替换。"""
    seen: list[tuple[uuid.UUID, str]] = []
    for binding in bindings:
        key = (binding.mcp_server_id, binding.tool_name)
        if key not in seen:
            seen.append(key)
    server_ids = {server_id for server_id, _ in seen}
    if server_ids:
        owned = set(
            (
                await db.scalars(
                    select(McpServer.id).where(
                        McpServer.id.in_(server_ids), McpServer.user_id == user.id
                    )
                )
            ).all()
        )
        missing = server_ids - owned
        if missing:
            raise HTTPException(status_code=404, detail="MCP 不存在")
    for server_id, tool_name in seen:
        server = await db.get(McpServer, server_id)
        cached = {str(t.get("name")) for t in (server.tools or [])}
        if tool_name not in cached:
            raise HTTPException(
                status_code=400,
                detail=f"MCP「{server.name}」没有工具 {tool_name}，请先测试连接刷新工具列表",
            )
    await db.execute(delete(AgentMcpTool).where(AgentMcpTool.agent_id == agent.id))
    for server_id, tool_name in seen:
        db.add(AgentMcpTool(agent_id=agent.id, mcp_server_id=server_id, tool_name=tool_name))
    await db.commit()
    return await list_mcp_tools(db, agent.id)


async def set_kbs(db: AsyncSession, agent: Agent, user: User, bindings: list) -> list[AgentKB]:
    """替换语义：先校验全部 KB 归属，再删除旧绑定并写入新绑定。"""
    bindings = list({b.kb_id: b for b in bindings}.values())  # 保序去重
    rows: list[AgentKB] = []
    for binding in bindings:
        kb = await db.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.id == binding.kb_id, KnowledgeBase.owner_id == user.id
            )
        )
        if kb is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        rows.append(
            AgentKB(
                agent_id=agent.id,
                kb_id=kb.id,
                top_k=binding.top_k,
                score_threshold=binding.score_threshold,
            )
        )
    await db.execute(delete(AgentKB).where(AgentKB.agent_id == agent.id))
    for row in rows:
        db.add(row)
    await db.commit()
    return rows


async def list_kb_bindings(db: AsyncSession, agent_id) -> list[dict]:
    rows = (
        await db.execute(
            select(AgentKB.kb_id, KnowledgeBase.name, AgentKB.top_k, AgentKB.score_threshold)
            .join(KnowledgeBase, KnowledgeBase.id == AgentKB.kb_id)
            .where(AgentKB.agent_id == agent_id)
            .order_by(KnowledgeBase.name, AgentKB.kb_id)
        )
    ).all()
    return [
        {
            "kb_id": row.kb_id,
            "name": row.name,
            "top_k": row.top_k,
            "score_threshold": row.score_threshold,
        }
        for row in rows
    ]


def _snapshot(
    agent: Agent,
    tool_slugs: list[str],
    skill_slugs: list[str],
    mcp_tools: list[dict],
) -> dict:
    return {
        "name": agent.name,
        "emoji": agent.emoji,
        "description": agent.description,
        "tags": agent.tags,
        "system_prompt": agent.system_prompt,
        "model_config": agent.model_config,
        "welcome_msg": agent.welcome_msg,
        "examples": agent.examples,
        "tool_slugs": tool_slugs,
        "skill_slugs": skill_slugs,
        "mcp_tools": mcp_tools,
    }


async def publish_agent(db: AsyncSession, agent: Agent, user: User) -> AgentVersion:
    slugs = await _tool_slugs(db, agent.id)
    skill_slugs = await _skill_slugs(db, agent.id)
    mcp_tools = await list_mcp_tools(db, agent.id)
    max_version = await db.scalar(
        select(func.max(AgentVersion.version)).where(AgentVersion.agent_id == agent.id)
    )
    version = int(max_version or 0) + 1
    row = AgentVersion(
        agent_id=agent.id,
        version=version,
        snapshot=_snapshot(agent, slugs, skill_slugs, mcp_tools),
        published_by=user.id,
    )
    agent.current_version = version
    agent.status = "published"
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await db.refresh(agent)
    return row


async def list_versions(db: AsyncSession, agent: Agent) -> list[AgentVersion]:
    rows = (
        await db.scalars(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id)
            .order_by(AgentVersion.version.desc())
        )
    ).all()
    return list(rows)


async def rollback_agent(db: AsyncSession, agent: Agent, version: int) -> Agent:
    row = await db.scalar(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent.id, AgentVersion.version == version
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    snap = row.snapshot
    for key in (
        "name",
        "emoji",
        "description",
        "tags",
        "system_prompt",
        "model_config",
        "welcome_msg",
        "examples",
    ):
        setattr(agent, key, snap.get(key))
    # 设计 04：回滚 = 快照拷回 draft；current_version 保持最新发布号
    agent.status = "draft"
    await db.execute(delete(AgentTool).where(AgentTool.agent_id == agent.id))
    for slug in snap.get("tool_slugs", []):
        tool = await db.scalar(select(Tool).where(Tool.slug == slug, Tool.enabled.is_(True)))
        if tool is not None:
            db.add(AgentTool(agent_id=agent.id, tool_id=tool.id))
    # 扩展能力（skill / mcp）一并回滚；未知 skill 与已删除的 MCP 工具自动跳过
    await db.execute(delete(AgentSkill).where(AgentSkill.agent_id == agent.id))
    for slug in snap.get("skill_slugs", []):
        if slug in SKILL_REGISTRY:
            db.add(AgentSkill(agent_id=agent.id, skill_slug=slug))
    await db.execute(delete(AgentMcpTool).where(AgentMcpTool.agent_id == agent.id))
    for item in snap.get("mcp_tools", []):
        try:
            server_id = uuid.UUID(str(item.get("mcp_server_id")))
        except (TypeError, ValueError):
            continue
        server = await db.get(McpServer, server_id)
        if server is None or server.user_id != agent.owner_id:
            continue
        db.add(
            AgentMcpTool(
                agent_id=agent.id,
                mcp_server_id=server_id,
                tool_name=str(item.get("tool_name") or ""),
            )
        )
    await db.commit()
    await db.refresh(agent)
    return agent
