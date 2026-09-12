import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.deps import get_model_manager, get_provider
from app.ai.model_manager import ModelManager
from app.ai.providers.base import ModelProvider
from app.ai.runtime import CANCEL_SESSIONS, run_generation, sse
from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db, get_session_factory
from app.models.agent import Agent
from app.models.session import Attachment, Message, Session
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
    mentions: list[uuid.UUID] = Field(default_factory=list, max_length=2)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=3)


async def _owned_pending_attachments(
    db: AsyncSession, session: Session, ids: list[uuid.UUID]
) -> list[Attachment]:
    """本会话下尚未绑定消息的附件（图片或文档）；顺序与请求一致；缺失或越权一律 404。"""
    if not ids:
        return []
    rows = (
        await db.scalars(
            select(Attachment).where(
                Attachment.id.in_(ids),
                Attachment.session_id == session.id,
                Attachment.message_id.is_(None),
            )
        )
    ).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(set(ids)):
        raise HTTPException(status_code=404, detail="附件不存在")
    return [by_id[aid] for aid in dict.fromkeys(ids)]


async def _relay_agent(db: AsyncSession, user: User, agent_id: uuid.UUID) -> Agent | None:
    agent = await db.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.owner_id == user.id)
    )
    if agent is None or agent.status == "archived":
        return None
    return agent


async def _relay_stream(
    db: AsyncSession,
    session: Session,
    provider: ModelProvider,
    manager: ModelManager | None,
    factory: async_sessionmaker[AsyncSession],
    agent_id: uuid.UUID,
    name: str,
):
    async for chunk in run_generation(
        db,
        session,
        provider,
        user_content=None,
        session_factory=factory,
        model_manager=manager,
        agent_override=agent_id,
        relay_instruction=f"你是{name}，用户 @ 了你，请针对上文补充你的专业意见。",
    ):
        yield chunk


@router.post("/{sid}/messages")
async def post_message(
    sid: uuid.UUID,
    body: MessageIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[ModelProvider, Depends(get_provider)],
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    manager: Annotated[ModelManager | None, Depends(get_model_manager)],
):
    session = await session_service.get_owned_session(db, user, sid)
    attachments = await _owned_pending_attachments(db, session, body.attachment_ids)
    upload_root = Path(settings.upload_dir)
    image_paths = [
        str(upload_root / att.file_path) for att in attachments if att.kind == "image"
    ]
    document_files = [
        (
            str(upload_root / att.file_path),
            Path(att.file_path).suffix.lstrip(".").lower(),
            att.original_name,
        )
        for att in attachments
        if att.kind == "document"
    ]

    async def gen():
        # 消费上一轮遗留的会话级停止标记，避免误杀本次请求的接力
        CANCEL_SESSIONS.discard(session.id)
        async for chunk in run_generation(
            db,
            session,
            provider,
            user_content=body.content,
            session_factory=factory,
            model_manager=manager,
            image_paths=image_paths or None,
            document_files=document_files or None,
            attachment_ids=[att.id for att in attachments] or None,
        ):
            yield chunk
        for mention_id in body.mentions:
            if session.id in CANCEL_SESSIONS:
                CANCEL_SESSIONS.discard(session.id)
                break  # 主回合被停止：不再启动接力
            agent = await _relay_agent(db, user, mention_id)
            if agent is None:
                yield sse("error", {"message": "无法接力：智能体不可用"})
                continue
            async for chunk in _relay_stream(
                db, session, provider, manager, factory, agent.id, agent.name
            ):
                yield chunk

    return StreamingResponse(
        gen(),
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
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    manager: Annotated[ModelManager | None, Depends(get_model_manager)],
):
    session, message = target
    keep_target = message.role == "user"
    await message_service.truncate_session(db, session, message.id, keep_target=keep_target)
    return StreamingResponse(
        run_generation(
            db,
            session,
            provider,
            user_content=None,
            session_factory=factory,
            model_manager=manager,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
