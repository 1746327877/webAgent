import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import ChatRequest, ModelProvider
from app.core.config import settings
from app.models.session import Message, Session

FLUSH_INTERVAL_S = 0.2
MAX_ERROR_LEN = 500
CANCEL_FLAGS: dict[uuid.UUID, bool] = {}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _text_of(blocks: list[dict]) -> str:
    return "".join(b.get("content", "") for b in blocks if b.get("type") == "text")


async def _load_history(
    db: AsyncSession, session_id: uuid.UUID, exclude_id: uuid.UUID
) -> list[dict]:
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.session_id == session_id, Message.id != exclude_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(settings.history_rounds * 2)
        )
    ).all()
    history = []
    for row in reversed(rows):
        text = _text_of(row.blocks or [])
        if text and row.status in ("done", "stopped"):
            history.append({"role": row.role, "content": text})
    return history


async def _finalize(
    db: AsyncSession,
    assistant_id: uuid.UUID,
    session_id: uuid.UUID,
    blocks: list[dict],
    status: str,
    usage: dict | None,
    error_text: str | None,
) -> None:
    CANCEL_FLAGS.pop(assistant_id, None)
    await db.execute(
        update(Message)
        .where(Message.id == assistant_id)
        .values(blocks=blocks, status=status, usage=usage, error=error_text)
    )
    await db.execute(
        update(Session).where(Session.id == session_id).values(last_message_at=func.now())
    )
    await db.commit()


async def run_generation(
    db: AsyncSession,
    session: Session,
    provider: ModelProvider,
    *,
    user_content: str | None,
) -> AsyncIterator[str]:
    """user_content=None 时仅生成助手消息（重新生成场景）。"""
    if user_content is not None:
        db.add(
            Message(
                session_id=session.id,
                role="user",
                blocks=[{"type": "text", "content": user_content}],
            )
        )
        await db.flush()

    assistant = Message(
        session_id=session.id,
        role="assistant",
        blocks=[],
        status="streaming",
        model=settings.default_model,
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    assistant_id = assistant.id

    yield sse("message_start", {"message_id": str(assistant_id), "role": "assistant"})

    blocks: list[dict] = []
    usage: dict | None = None
    status = "done"
    error_text: str | None = None
    first_token_ms: float | None = None
    thinking_started: float | None = None
    t0 = time.monotonic()
    last_flush = t0

    try:
        history = await _load_history(db, session.id, exclude_id=assistant_id)
        if user_content is not None:
            history.append({"role": "user", "content": user_content})
        req = ChatRequest(model=settings.default_model, messages=history)

        async for ev in provider.chat_stream(req):
            now = time.monotonic()
            if CANCEL_FLAGS.pop(assistant_id, False):
                status = "stopped"
                break
            if ev.type == "token":
                if blocks and blocks[-1]["type"] == "text":
                    blocks[-1]["content"] += ev.payload["delta"]
                else:
                    if thinking_started is not None and blocks and blocks[-1]["type"] == "thinking":
                        blocks[-1]["duration_ms"] = round((now - thinking_started) * 1000)
                        thinking_started = None
                    blocks.append({"type": "text", "content": ev.payload["delta"]})
                if first_token_ms is None:
                    first_token_ms = round((now - t0) * 1000, 1)
                yield sse("token", {"message_id": str(assistant_id), "delta": ev.payload["delta"]})
            elif ev.type == "thinking":
                if blocks and blocks[-1]["type"] == "thinking":
                    blocks[-1]["content"] += ev.payload["delta"]
                else:
                    blocks.append({"type": "thinking", "content": ev.payload["delta"], "duration_ms": None})
                    thinking_started = now
                yield sse("thinking", {"message_id": str(assistant_id), "delta": ev.payload["delta"]})
            elif ev.type == "usage":
                usage = ev.payload

            if now - last_flush >= FLUSH_INTERVAL_S:
                await db.execute(
                    update(Message).where(Message.id == assistant_id).values(blocks=blocks)
                )
                await db.commit()
                last_flush = now
    except asyncio.CancelledError:
        await _finalize(db, assistant_id, session.id, blocks, "stopped", usage, None)
        raise
    except GeneratorExit:
        await _finalize(db, assistant_id, session.id, blocks, "stopped", usage, None)
        raise
    except Exception as exc:  # noqa: BLE001 —— 边界处转 SSE error
        status = "error"
        error_text = str(exc)[:MAX_ERROR_LEN]
        yield sse("error", {"message_id": str(assistant_id), "message": "生成失败，请重试"})
    finally:
        if thinking_started is not None and blocks and blocks[-1]["type"] == "thinking":
            blocks[-1]["duration_ms"] = round((time.monotonic() - thinking_started) * 1000)

    await _finalize(db, assistant_id, session.id, blocks, status, usage, error_text)
    yield sse(
        "done",
        {
            "message_id": str(assistant_id),
            "usage": usage,
            "latency_ms": {
                "first_token": first_token_ms,
                "total": round((time.monotonic() - t0) * 1000),
            },
        },
    )
