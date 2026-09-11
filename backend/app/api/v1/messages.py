import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime import CANCEL_FLAGS
from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models.session import Session
from app.models.user import User
from app.schemas.session import MessageOut
from app.services import message_service

router = APIRouter(prefix="/messages", tags=["messages"])


class MessagePatchIn(BaseModel):
    blocks: list[dict] | None = None
    rating: Literal[1, -1] | None = None


@router.post("/{mid}/stop")
async def stop_message(
    mid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    message = await message_service.get_owned_message(db, user, mid)
    if message.role != "assistant":
        return {"status": "ignored"}
    if message.status == "streaming":
        CANCEL_FLAGS[message.id] = True
    return {"status": "ok"}


@router.patch("/{mid}", response_model=MessageOut)
async def patch_message(
    mid: uuid.UUID,
    body: MessagePatchIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    message = await message_service.get_owned_message(db, user, mid)
    if body.rating is not None:
        if message.role != "assistant":
            raise HTTPException(status_code=422, detail="仅助手消息可评分")
        message.rating = body.rating
    if body.blocks is not None:
        if message.role != "user":
            raise HTTPException(status_code=422, detail="仅用户消息可编辑")
        text = "".join(b.get("content", "") for b in body.blocks if b.get("type") == "text").strip()
        if not text:
            raise HTTPException(status_code=422, detail="内容不能为空")
        message.blocks = body.blocks
        await db.commit()
        session = await db.get(Session, message.session_id)
        await message_service.truncate_session(db, session, message.id, keep_target=True)
    else:
        await db.commit()
    await db.refresh(message)
    return message
