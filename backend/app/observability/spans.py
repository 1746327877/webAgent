import json
import time
import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

MAX_SPAN_OUTPUT = 32 * 1024


def _json_snapshot(value, limit: int = MAX_SPAN_OUTPUT):
    """深拷贝 + 32KB 截断：span 记录不引用运行时可变对象。"""
    if value is None:
        return None
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) <= limit:
        return json.loads(text)
    return {"_truncated": True, "preview": text[:limit]}


class SpanBuffer:
    """批内合并：生成期间 span 只进内存，结束时一次 INSERT；观测失败不影响生成。"""

    def __init__(self, **base):
        self.base = base
        self.rows: list[dict] = []

    def add(self, **fields) -> uuid_lib.UUID:
        row_id = fields.pop("id", None) or uuid_lib.uuid4()
        try:
            row = {**self.base, **fields, "id": row_id}
            row.setdefault("started_at", datetime.now(UTC))
            row["input"] = _json_snapshot(row.get("input"))
            row["output"] = _json_snapshot(row.get("output"))
            self.rows.append(row)
        except Exception:  # noqa: BLE001, S110 —— 单条观测异常不得影响生成
            pass
        return row_id

    async def flush(self, db) -> None:
        if not self.rows:
            return
        rows, self.rows = self.rows, []
        try:
            from app.models import Span

            db.add_all([Span(**row) for row in rows])
            await db.commit()
        except Exception:  # noqa: BLE001 —— 观测写入失败只丢观测
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001, S110 —— rollback 也不可用时不得上抛
                pass


async def record_span(
    db: AsyncSession,
    *,
    trace_id,
    type: str,
    name: str,
    session_id=None,
    agent_id=None,
    message_id=None,
    user_id=None,
    parent_span_id=None,
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
            user_id=user_id,
            parent_span_id=parent_span_id,
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
