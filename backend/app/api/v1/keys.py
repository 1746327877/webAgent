import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models import ApiKey
from app.models.user import User
from app.services import api_key_service

router = APIRouter(prefix="/keys", tags=["keys"])


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


def _view(key: ApiKey) -> dict:
    return {
        "id": str(key.id),
        "name": key.name,
        "key_prefix": key.key_prefix,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "revoked": key.revoked,
        "created_at": key.created_at.isoformat() if key.created_at else None,
    }


@router.post("", status_code=201)
async def create_key(
    body: KeyCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    key, plaintext = await api_key_service.create_key(db, user, body.name)
    return {**_view(key), "key": plaintext}


@router.get("")
async def list_keys(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [_view(key) for key in await api_key_service.list_keys(db, user)]


@router.delete("/{key_id}", status_code=204)
async def delete_key(
    key_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    if not await api_key_service.revoke_key(db, user, key_id):
        raise HTTPException(status_code=404, detail="密钥不存在")
    return Response(status_code=204)
