import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai.deps import get_provider
from app.ai.providers.base import ChatRequest, ModelProvider
from app.api.v1.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatStreamIn(BaseModel):
    model: str
    messages: list[ChatMessageIn] = Field(min_length=1)
    temperature: float = 0.7
    max_tokens: int = 2048
    num_ctx: int = 8192


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(
    body: ChatStreamIn,
    user: Annotated[User, Depends(get_current_user)],
    provider: Annotated[ModelProvider, Depends(get_provider)],
):
    async def gen():
        try:
            req = ChatRequest(
                model=body.model,
                messages=[m.model_dump() for m in body.messages],
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                num_ctx=body.num_ctx,
            )
            async for ev in provider.chat_stream(req):
                yield _sse(ev.type, ev.payload)
        except Exception as exc:  # noqa: BLE001 — 边界处转为 error 事件
            yield _sse("error", {"message": str(exc)})
        finally:
            yield _sse("done", {})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
