"""OpenAI 兼容端点（根路径 /v1，不带 /api/v1 前缀）。

鉴权使用 Task 6 的 sk- API Key；对外契约见 M6 Task 7 简报。
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.deps import get_model_manager, get_provider
from app.ai.model_manager import ModelManager
from app.ai.providers.base import ModelProvider
from app.api.v1.deps import get_api_key_user
from app.core.db import get_db
from app.models.user import User
from app.services import openai_service

router = APIRouter(tags=["openai-compat"])


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048


def _error(status: int, message: str, error_type: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": "model",
                "code": None,
            }
        },
    )


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    user: Annotated[User, Depends(get_api_key_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[ModelProvider, Depends(get_provider)],
    manager: Annotated[ModelManager | None, Depends(get_model_manager)],
):
    try:
        agent, _cfg, req = await openai_service.prepare(
            db,
            user,
            manager,
            model=body.model,
            messages=[message.model_dump() for message in body.messages],
            temperature=body.temperature,
            top_p=body.top_p,
            max_tokens=body.max_tokens,
        )
    except openai_service.ModelFormatError as exc:
        return _error(400, str(exc))
    except openai_service.AgentNotFoundError:
        return _error(404, "智能体不存在")

    if body.stream:
        return StreamingResponse(
            openai_service.stream(
                db, user, provider, agent=agent, req=req, response_model=body.model
            ),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
    return await openai_service.complete(
        db, user, provider, agent=agent, req=req, response_model=body.model
    )
