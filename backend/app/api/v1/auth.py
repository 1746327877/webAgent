import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import (
    create_access_token,
    new_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.auth import LoginIn, TokenOut, UserCreateIn, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: UserCreateIn, db: Annotated[AsyncSession, Depends(get_db)]):
    if await auth_service.get_user_by_username(db, body.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    if await auth_service.get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="邮箱已被注册")
    return await auth_service.create_user(db, body)


REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        httponly=True,
        samesite="lax",
        path=COOKIE_PATH,
        max_age=settings.refresh_token_days * 86400,
    )


async def _issue_refresh(db: AsyncSession, user_id) -> str:
    raw, token_hash = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    await db.commit()
    return raw


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = await auth_service.get_user_by_username(db, body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    raw = await _issue_refresh(db, user.id)
    _set_refresh_cookie(response, raw)
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="缺少刷新令牌")
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = await db.scalar(
        select(RefreshToken)
        .where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")
    row.revoked = True  # 轮换：旧令牌立即失效
    new_raw = await _issue_refresh(db, row.user_id)
    _set_refresh_cookie(response, new_raw)
    return TokenOut(access_token=create_access_token(str(row.user_id)))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if row is not None:
            row.revoked = True
            await db.commit()
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(get_current_user)]):
    return user
