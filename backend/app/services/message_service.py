import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Message, Session
from app.models.user import User


async def get_owned_message(db: AsyncSession, user: User, message_id: uuid.UUID) -> Message:
    message = await db.scalar(
        select(Message)
        .join(Session, Session.id == Message.session_id)
        .where(Message.id == message_id, Session.user_id == user.id)
    )
    if message is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    return message


async def truncate_session(
    db: AsyncSession, session: Session, message_id: uuid.UUID, *, keep_target: bool
) -> None:
    ids = (
        await db.scalars(
            select(Message.id)
            .where(Message.session_id == session.id)
            .order_by(Message.seq)
        )
    ).all()
    ids = list(ids)
    if message_id not in ids:
        raise HTTPException(status_code=404, detail="消息不存在")
    idx = ids.index(message_id)
    to_delete = ids[idx:] if not keep_target else ids[idx + 1 :]
    if to_delete:
        await db.execute(delete(Message).where(Message.id.in_(to_delete)))
        await db.commit()
