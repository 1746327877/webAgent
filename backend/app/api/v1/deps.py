import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="未认证")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    user = await db.get(User, uuid.UUID(user_id))
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user
