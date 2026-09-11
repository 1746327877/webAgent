import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Message
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
    if used is not None:
        raise HTTPException(status_code=409, detail="该智能体已被会话使用，请改为归档")
    await db.delete(agent)
    await db.commit()
