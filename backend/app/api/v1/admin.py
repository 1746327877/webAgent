from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.services import metrics_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics/overview")
async def metrics_overview(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: Annotated[int, Query(ge=1, le=720)] = 24,
):
    """仪表盘概览。span 指标仅统计当前用户；HTTP/VRAM 为进程级系统指标。"""
    manager = getattr(request.app.state, "model_manager", None)
    return await metrics_service.build_overview(
        db, user_id=user.id, hours=hours, manager=manager
    )
