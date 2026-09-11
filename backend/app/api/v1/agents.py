import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.agent import (
    AgentCreateIn,
    AgentOut,
    AgentUpdateIn,
    AgentVersionOut,
    PublishOut,
    RollbackIn,
)
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


def _to_out(agent) -> AgentOut:
    out = AgentOut.model_validate(agent)
    out.variables = agent_service.extract_variables(agent.system_prompt)
    return out


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return _to_out(await agent_service.create_agent(db, user, body))


@router.get("", response_model=list[AgentOut])
async def list_agents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [_to_out(a) for a in await agent_service.list_agents(db, user)]


@router.get("/{aid}", response_model=AgentOut)
async def get_agent(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return _to_out(await agent_service.get_owned_agent(db, user, aid))


@router.patch("/{aid}", response_model=AgentOut)
async def patch_agent(
    aid: uuid.UUID,
    body: AgentUpdateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    fields = body.model_dump(exclude_unset=True, by_alias=True)
    return _to_out(await agent_service.update_agent(db, agent, fields))


@router.delete("/{aid}", status_code=204)
async def delete_agent(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    await agent_service.delete_agent(db, agent)


@router.post("/{aid}/publish", response_model=PublishOut)
async def publish_agent(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    row = await agent_service.publish_agent(db, agent, user)
    return PublishOut(version=row.version, status=agent.status)


@router.get("/{aid}/versions", response_model=list[AgentVersionOut])
async def list_versions(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    return await agent_service.list_versions(db, agent)


@router.post("/{aid}/rollback", response_model=AgentOut)
async def rollback_agent(
    aid: uuid.UUID,
    body: RollbackIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    return _to_out(await agent_service.rollback_agent(db, agent, body.version))
