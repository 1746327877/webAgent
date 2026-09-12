import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.session import Attachment, Message, Session
from app.models.user import User


async def create_session(
    db: AsyncSession, user: User, title: str, agent_id: uuid.UUID | None = None
) -> Session:
    if agent_id is not None:
        agent = await db.scalar(
            select(Agent).where(Agent.id == agent_id, Agent.owner_id == user.id)
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="智能体不存在")
        if agent.status == "archived":
            raise HTTPException(status_code=422, detail="该智能体已归档，无法新建会话")
    session = Session(user_id=user.id, title=title, agent_id=agent_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_owned_session(db: AsyncSession, user: User, session_id: uuid.UUID) -> Session:
    session = await db.scalar(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


async def list_sessions(
    db: AsyncSession, user: User, query: str | None, archived: bool, limit: int, offset: int
) -> tuple[list[Session], int]:
    conds = [Session.user_id == user.id, Session.archived.is_(archived)]
    if query:
        conds.append(Session.title.ilike(f"%{query}%"))
    total = await db.scalar(select(func.count()).select_from(Session).where(*conds))
    rows = (
        await db.scalars(
            select(Session)
            .where(*conds)
            .order_by(
                Session.pinned.desc(),
                Session.last_message_at.desc().nulls_last(),
                Session.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), int(total or 0)


async def update_session(db: AsyncSession, session: Session, fields: dict) -> Session:
    for key, value in fields.items():
        if value is not None:
            setattr(session, key, value)
    await db.commit()
    await db.refresh(session)
    return session


async def delete_session(db: AsyncSession, session: Session) -> None:
    await db.delete(session)
    await db.commit()


async def list_messages(db: AsyncSession, session: Session) -> list[Message]:
    rows = (
        await db.scalars(
            select(Message).where(Message.session_id == session.id).order_by(Message.seq)
        )
    ).all()
    messages = list(rows)
    # 一次批量查询按 message_id 分组，避免逐条消息查附件的 N+1
    attachments_by_message: dict[uuid.UUID, list[dict]] = {}
    if messages:
        attachments = (
            await db.scalars(
                select(Attachment)
                .where(Attachment.message_id.in_([m.id for m in messages]))
                .order_by(Attachment.created_at)
            )
        ).all()
        for attachment in attachments:
            attachments_by_message.setdefault(attachment.message_id, []).append(
                {
                    "id": str(attachment.id),
                    "original_name": attachment.original_name,
                    "kind": attachment.kind,
                    "mime_type": attachment.mime_type,
                    "size_bytes": attachment.size_bytes,
                }
            )
    for message in messages:
        message.attachments = attachments_by_message.get(message.id, [])
    return messages
