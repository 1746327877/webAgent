from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.auth import UserCreateIn, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: UserCreateIn, db: Annotated[AsyncSession, Depends(get_db)]):
    if await auth_service.get_user_by_username(db, body.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    if await auth_service.get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="邮箱已被注册")
    return await auth_service.create_user(db, body)
