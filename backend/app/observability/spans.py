import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession


async def record_span(
    db: AsyncSession,
    *,
    trace_id,
    type: str,
    name: str,
    session_id=None,
    agent_id=None,
    message_id=None,
    input=None,
    output=None,
    status: str = "ok",
    error: str | None = None,
    started: float | None = None,
    ended: float | None = None,
) -> None:
    """在给定请求级会话上写一条 Span 并提交（测试可注入 session 读到记录）。"""
    from app.models import Span

    s = started if started is not None else time.monotonic()
    e = ended if ended is not None else time.monotonic()
    db.add(
        Span(
            trace_id=trace_id,
            type=type,
            name=name,
            session_id=session_id,
            agent_id=agent_id,
            message_id=message_id,
            input=input,
            output=output,
            status=status,
            error=error,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=int((e - s) * 1000),
        )
    )
    await db.commit()
