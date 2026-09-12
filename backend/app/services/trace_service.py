"""追踪查询：trace waterfall、span 日志筛选与 CSV 流式导出。

隔离口径：所有查询按 ``Span.user_id`` 过滤；message → session → owner
校验失败一律 404。CSV 由 ``csv.writer`` 转义，另对公式注入前缀做加固。
"""

import csv
import io
import uuid
from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Session, Span
from app.models.user import User

CSV_HEADER = (
    "started_at,type,name,status,duration_ms,model,prompt_tokens,completion_tokens,"
    "session_id,message_id,error\r\n"
)
EXPORT_BATCH = 500
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _span_view(span: Span) -> dict:
    """Span → 前端 waterfall/列表通用视图。"""
    return {
        "id": str(span.id),
        "parent_span_id": str(span.parent_span_id) if span.parent_span_id else None,
        "type": span.type,
        "name": span.name,
        "status": span.status,
        "model": span.model,
        "error": span.error,
        "prompt_tokens": span.prompt_tokens,
        "completion_tokens": span.completion_tokens,
        "duration_ms": span.duration_ms,
        "started_at": span.started_at.isoformat(),
        "ended_at": span.ended_at.isoformat() if span.ended_at else None,
        "session_id": str(span.session_id) if span.session_id else None,
        "message_id": str(span.message_id) if span.message_id else None,
        "agent_id": str(span.agent_id) if span.agent_id else None,
        "input": span.input,
        "output": span.output,
    }


def _conds(
    user_id,
    *,
    type=None,
    status=None,
    agent_id=None,
    session_id=None,
    message_id=None,
    from_dt=None,
    to_dt=None,
):
    conds = [Span.user_id == user_id]
    if type:
        conds.append(Span.type == type)
    if status:
        conds.append(Span.status == status)
    if agent_id:
        conds.append(Span.agent_id == agent_id)
    if session_id:
        conds.append(Span.session_id == session_id)
    if message_id:
        conds.append(Span.message_id == message_id)
    if from_dt:
        conds.append(Span.started_at >= from_dt)
    if to_dt:
        conds.append(Span.started_at <= to_dt)
    return conds


async def message_trace(db: AsyncSession, user: User, message_id: uuid.UUID) -> dict:
    """单条消息的 span 列表（started_at 升序），供前端渲染 waterfall。"""
    message = await db.scalar(
        select(Message)
        .join(Session, Session.id == Message.session_id)
        .where(Message.id == message_id, Session.user_id == user.id)
    )
    if message is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    spans = (
        await db.scalars(
            select(Span)
            .where(Span.message_id == message_id, Span.user_id == user.id)
            .order_by(Span.started_at)
        )
    ).all()
    return {
        "trace_id": str(message.id),
        "message": {
            "id": str(message.id),
            "model": message.model,
            "status": message.status,
            "usage": message.usage,
        },
        "spans": [_span_view(sp) for sp in spans],
    }


async def query_spans(
    db: AsyncSession,
    user_id,
    *,
    limit: int = 50,
    offset: int = 0,
    with_total: bool = True,
    **filters,
) -> tuple[list[dict], int]:
    """按筛选条件分页查询当前用户的 span，返回 (items, total)。

    ``with_total=False`` 时跳过 count（CSV 导出批量拉取用，省去每批一次计数）。
    """
    conds = _conds(user_id, **filters)
    total = 0
    if with_total:
        total = await db.scalar(select(func.count()).select_from(Span).where(*conds))
    rows = (
        await db.scalars(
            select(Span)
            .where(*conds)
            .order_by(Span.started_at.desc(), Span.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [_span_view(sp) for sp in rows], int(total or 0)


def _csv_cell(value) -> str:
    """单元格转字符串，并给公式前缀加 ``'`` 防止 Excel 公式注入。"""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


async def csv_chunks(db: AsyncSession, user_id, **filters) -> AsyncIterator[str]:
    """流式产出 CSV 分片：首片 BOM + 表头，之后按 500 行批量查询。"""
    yield "\ufeff" + CSV_HEADER
    offset = 0
    while True:
        batch, _ = await query_spans(
            db, user_id, limit=EXPORT_BATCH, offset=offset, with_total=False, **filters
        )
        if not batch:
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        for sp in batch:
            writer.writerow(
                [
                    _csv_cell(sp["started_at"]),
                    _csv_cell(sp["type"]),
                    _csv_cell(sp["name"]),
                    _csv_cell(sp["status"]),
                    _csv_cell(sp["duration_ms"]),
                    _csv_cell(sp["model"]),
                    _csv_cell(sp["prompt_tokens"]),
                    _csv_cell(sp["completion_tokens"]),
                    _csv_cell(sp["session_id"]),
                    _csv_cell(sp["message_id"]),
                    _csv_cell(sp["error"]),
                ]
            )
        yield buf.getvalue()
        offset += len(batch)
