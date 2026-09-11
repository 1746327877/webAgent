import re
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, AgentTool, AgentVersion, Message, Session, Tool
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
        )
    ).all()
    return list(rows)


def _snapshot(agent: Agent, tool_slugs: list[str]) -> dict:
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
    }


async def publish_agent(db: AsyncSession, agent: Agent, user: User) -> AgentVersion:
    slugs = await _tool_slugs(db, agent.id)
    max_version = await db.scalar(
        select(func.max(AgentVersion.version)).where(AgentVersion.agent_id == agent.id)
    )
    version = int(max_version or 0) + 1
    row = AgentVersion(
        agent_id=agent.id,
        version=version,
        snapshot=_snapshot(agent, slugs),
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
    await db.execute(delete(AgentTool).where(AgentTool.agent_id == agent.id))
    for slug in snap.get("tool_slugs", []):
        tool = await db.scalar(select(Tool).where(Tool.slug == slug, Tool.enabled.is_(True)))
        if tool is not None:
            db.add(AgentTool(agent_id=agent.id, tool_id=tool.id))
    await db.commit()
    await db.refresh(agent)
    return agent
