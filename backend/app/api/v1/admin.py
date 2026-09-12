import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.services import metrics_service, trace_service

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


@router.get("/messages/{message_id}/spans")
async def message_spans(
    message_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """单条助手消息的 trace waterfall 数据；归属校验失败返回 404。"""
    return await trace_service.message_trace(db, user, message_id)


@router.get("/spans")
async def list_spans(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    agent_id: Annotated[uuid.UUID | None, Query()] = None,
    session_id: Annotated[uuid.UUID | None, Query()] = None,
    message_id: Annotated[uuid.UUID | None, Query()] = None,
    from_dt: Annotated[datetime | None, Query(alias="from")] = None,
    to_dt: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """span 日志筛选（本人数据，started_at 倒序）。"""
    items, total = await trace_service.query_spans(
        db,
        user.id,
        limit=limit,
        offset=offset,
        type=type,
        status=status,
        agent_id=agent_id,
        session_id=session_id,
        message_id=message_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
    return {"items": items, "total": total}


@router.get("/spans/export.csv")
async def export_spans(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    agent_id: Annotated[uuid.UUID | None, Query()] = None,
    session_id: Annotated[uuid.UUID | None, Query()] = None,
    message_id: Annotated[uuid.UUID | None, Query()] = None,
    from_dt: Annotated[datetime | None, Query(alias="from")] = None,
    to_dt: Annotated[datetime | None, Query(alias="to")] = None,
):
    """按同列表筛选流式导出 CSV（UTF-8 BOM 防 Excel 中文乱码）。"""
    return StreamingResponse(
        trace_service.csv_chunks(
            db,
            user.id,
            type=type,
            status=status,
            agent_id=agent_id,
            session_id=session_id,
            message_id=message_id,
            from_dt=from_dt,
            to_dt=to_dt,
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="spans.csv"'},
    )
