import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.deps import get_provider
from app.ai.providers.base import ModelProvider
from app.ai.runtime import run_generation
from app.api.v1.deps import get_current_user
from app.core.db import get_db, get_session_factory
from app.models.session import Message, Session
from app.models.user import User
from app.schemas.session import (
    MessageOut,
    SessionCreateIn,
    SessionListOut,
    SessionOut,
    SessionPatchIn,
)
from app.services import message_service, session_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    body: SessionCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await session_service.create_session(db, user, body.title, body.agent_id)


@router.get("", response_model=SessionListOut)
async def list_sessions(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    query: Annotated[str | None, Query(max_length=64)] = None,
    archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = await session_service.list_sessions(db, user, query, archived, limit, offset)
    return SessionListOut(items=items, total=total)


@router.get("/{sid}", response_model=SessionOut)
async def get_session(
    sid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await session_service.get_owned_session(db, user, sid)


@router.patch("/{sid}", response_model=SessionOut)
async def patch_session(
    sid: uuid.UUID,
    body: Annotated[SessionPatchIn, Body(default_factory=SessionPatchIn)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await session_service.get_owned_session(db, user, sid)
    return await session_service.update_session(db, session, body.model_dump())


@router.delete("/{sid}", status_code=204)
async def delete_session(
    sid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await session_service.get_owned_session(db, user, sid)
    await session_service.delete_session(db, session)


@router.get("/{sid}/messages", response_model=list[MessageOut])
async def list_messages(
    sid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await session_service.get_owned_session(db, user, sid)
    return await session_service.list_messages(db, session)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


@router.post("/{sid}/messages")
async def post_message(
    sid: uuid.UUID,
    body: MessageIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[ModelProvider, Depends(get_provider)],
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
):
    session = await session_service.get_owned_session(db, user, sid)
    return StreamingResponse(
        run_generation(db, session, provider, user_content=body.content, session_factory=factory),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RegenerateIn(BaseModel):
    message_id: uuid.UUID


async def _owned_regenerate_target(
    sid: uuid.UUID,
    body: RegenerateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[Session, Message]:
    # 归属校验必须是独立依赖：FastAPI 会先解析全部 Depends 再执行端点体，
    # 若放在端点体内，get_provider 将先于 404 解析（测试未触发 lifespan 时直接 500）
    session = await session_service.get_owned_session(db, user, sid)
    message = await message_service.get_owned_message(db, user, body.message_id)
    if message.session_id != session.id:
        raise HTTPException(status_code=404, detail="消息不存在")
    return session, message


@router.post("/{sid}/regenerate")
async def regenerate(
    target: Annotated[tuple[Session, Message], Depends(_owned_regenerate_target)],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[ModelProvider, Depends(get_provider)],
):
    session, message = target
    keep_target = message.role == "user"
    await message_service.truncate_session(db, session, message.id, keep_target=keep_target)
    return StreamingResponse(
        run_generation(db, session, provider, user_content=None),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
