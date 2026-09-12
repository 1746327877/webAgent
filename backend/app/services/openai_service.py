"""OpenAI 兼容网关：把外部 `agent:{id}` 调用映射为一次无状态智能体生成。

设计约束（见 M6 Task 7 偏离记录）：
- 只透传正文 token，thinking/tool_call 事件忽略；
- 不持久化会话/消息，外部调用不污染历史；
- 每请求写一条 llm span（独立 trace_id），使外部调用可在 /admin 统计。
"""

import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent_config import EffectiveConfig, build_agent_config
from app.ai.model_manager import ModelManager
from app.ai.providers.base import ChatRequest, ModelProvider
from app.models import Agent, Session
from app.models.user import User
from app.observability.spans import SpanBuffer


class ModelFormatError(ValueError):
    """model 字段不是合法的 agent:{uuid} 形式。"""


class AgentNotFoundError(LookupError):
    """智能体不存在，或不属于当前 API Key 用户（对外统一 404）。"""


def parse_agent_model(model: str) -> uuid.UUID:
    if not model.startswith("agent:"):
        raise ModelFormatError("model 必须形如 agent:{agent_id}")
    try:
        return uuid.UUID(model[len("agent:") :])
    except ValueError as exc:
        raise ModelFormatError("agent id 不是合法 UUID") from exc


async def prepare(
    db: AsyncSession,
    user: User,
    manager: ModelManager | None,
    *,
    model: str,
    messages: list[dict],
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> tuple[Agent, EffectiveConfig, ChatRequest]:
    """校验归属并构建请求；manager 为空（测试/无调度）时跳过模型加载。"""
    agent_id = parse_agent_model(model)
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.owner_id != user.id:
        raise AgentNotFoundError(str(agent_id))
    # 仅用于提示词模板渲染的占位会话，绝不 add 进库：外部调用无会话副作用
    stub = Session(user_id=user.id, title="OpenAI 兼容调用")
    cfg = await build_agent_config(db, agent, stub, user.username)
    if manager is not None:
        await manager.acquire(cfg.model, trigger="api")
    payload = (
        [{"role": "system", "content": cfg.system_prompt}] if cfg.system_prompt else []
    ) + messages
    req = ChatRequest(
        model=cfg.model,
        messages=payload,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        num_ctx=cfg.num_ctx,
    )
    return agent, cfg, req


def _chunk(completion_id: str, created: int, model: str, delta: dict, finish: str | None) -> dict:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


async def complete(
    db: AsyncSession,
    user: User,
    provider: ModelProvider,
    *,
    agent: Agent,
    req: ChatRequest,
    response_model: str,
) -> dict:
    """非流式：聚合正文 token 与 usage，返回 OpenAI ChatCompletion 结构。"""
    text: list[str] = []
    usage: dict | None = None
    started_at, started = datetime.now(UTC), time.monotonic()
    buffer = SpanBuffer(trace_id=uuid.uuid4(), user_id=user.id, agent_id=agent.id)
    status, error = "ok", None
    try:
        async for event in provider.chat_stream(req):
            if event.type == "token":
                text.append(event.payload["delta"])
            elif event.type == "usage":
                usage = event.payload
    except Exception as exc:  # 记录失败态后上抛，由框架转 500
        status, error = "error", str(exc)[:300]
        raise
    finally:
        buffer.add(
            type="llm",
            name=req.model,
            model=req.model,
            status=status,
            error=error,
            prompt_tokens=(usage or {}).get("prompt_tokens"),
            completion_tokens=(usage or {}).get("completion_tokens"),
            input={"messages": req.messages},
            output={"text": "".join(text)},
            started_at=started_at,
            ended_at=datetime.now(UTC),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        await buffer.flush(db)

    prompt = (usage or {}).get("prompt_tokens") or 0
    completion = (usage or {}).get("completion_tokens") or 0
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response_model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "".join(text)},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


async def stream(
    db: AsyncSession,
    user: User,
    provider: ModelProvider,
    *,
    agent: Agent,
    req: ChatRequest,
    response_model: str,
) -> AsyncIterator[str]:
    """流式：逐 token 输出 chat.completion.chunk，以 [DONE] 收尾。"""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    started_at, started = datetime.now(UTC), time.monotonic()
    buffer = SpanBuffer(trace_id=uuid.uuid4(), user_id=user.id, agent_id=agent.id)
    text: list[str] = []
    usage: dict | None = None
    status, error = "ok", None
    try:
        async for event in provider.chat_stream(req):
            if event.type == "token":
                delta = event.payload["delta"]
                text.append(delta)
                chunk = _chunk(completion_id, created, response_model, {"content": delta}, None)
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif event.type == "usage":
                usage = event.payload
            # thinking / tool_call 不透传：v1 网关只输出正文
        done = _chunk(completion_id, created, response_model, {}, "stop")
        yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:  # noqa: BLE001 —— 流中途失败以错误块收尾，不再抛出
        status, error = "error", str(exc)[:300]
        payload = {"error": {"message": "生成失败", "type": "server_error"}}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        buffer.add(
            type="llm",
            name=req.model,
            model=req.model,
            status=status,
            error=error,
            prompt_tokens=(usage or {}).get("prompt_tokens"),
            completion_tokens=(usage or {}).get("completion_tokens"),
            input={"messages": req.messages},
            output={"text": "".join(text)},
            started_at=started_at,
            ended_at=datetime.now(UTC),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        try:
            await buffer.flush(db)
        except Exception:  # noqa: BLE001, S110 —— 观测失败不影响响应
            pass
