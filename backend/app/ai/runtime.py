import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.agent_config import EffectiveConfig, build_agent_config, resolve_effective_config
from app.ai.model_manager import ModelManager
from app.ai.providers.base import ChatRequest, ModelProvider
from app.ai.tools.registry import tools_payload
from app.models.session import Message, Session
from app.models.user import User

FLUSH_INTERVAL_S = 0.2
MAX_ERROR_LEN = 500
MAX_TOOL_ROUNDS = 5
TOOL_TIMEOUT_S = 30.0
TOOL_RESULT_MAX = 8000
TOOL_PREVIEW_LEN = 200
CANCEL_FLAGS: dict[uuid.UUID, bool] = {}

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _execute_tool(
    name: str,
    args: str | dict,
    *,
    agent_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
    assistant_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    embedder: Embedder | None = None,
) -> tuple[str, str]:
    from app.ai.tools.registry import get_tool

    item = get_tool(name)
    if item is None:
        return f"未知工具：{name}", "error"
    try:
        # Ollama function.arguments 为 JSON 对象（dict）；兼容字符串脚本与空参
        if isinstance(args, dict):
            parsed = args
        else:
            parsed = json.loads(args) if args else {}
        # kb_search 在 runtime 层拦截为真实检索（使用智能体绑定的 KB）
        if name == "kb_search" and agent_id is not None and db is not None:
            query = str(parsed.get("query", "")).strip()
            raw_top = parsed.get("top_k") or 5
            try:
                top_k = min(max(int(raw_top), 1), 50)
            except (TypeError, ValueError):
                top_k = 5
            chunks = (
                await _retrieve_for_agent(
                    db,
                    agent_id,
                    query,
                    assistant_id=assistant_id,
                    session_id=session_id,
                    top_k=top_k,
                    session_maker=session_maker,
                    embedder=embedder,
                )
                if query
                else []
            )
            if chunks:
                from app.ai.rag.retrieval import format_context

                return format_context(chunks), "ok"
            return "未绑定知识库或未检索到相关内容，请先在智能体设置中绑定知识库。", "error"
        result = await asyncio.wait_for(item.handler(**parsed), timeout=TOOL_TIMEOUT_S)
        return str(result), "ok"
    except Exception as exc:  # noqa: BLE001 —— 工具失败转为错误结果回填，不中断生成
        return f"工具执行失败：{exc}", "error"


async def _default_embedder(texts: list[str]) -> list[list[float]]:
    from app.ai.providers.ollama import OllamaProvider
    from app.core.config import settings

    provider = OllamaProvider(settings.ollama_base_url)
    try:
        return await provider.embed(texts, settings.embedding_model)
    finally:
        await provider.aclose()


def _provider_embedder(provider: ModelProvider) -> Embedder:
    """复用请求内 Provider 做查询嵌入，便于测试注入并在生产复用连接。"""

    async def embed(texts: list[str]) -> list[list[float]]:
        from app.core.config import settings

        return await provider.embed(texts, settings.embedding_model)

    return embed


async def _retrieve_for_agent(
    db: AsyncSession,
    agent_id: uuid.UUID,
    query: str,
    *,
    assistant_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    top_k: int | None = None,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    embedder: Embedder | None = None,
) -> list:
    """按智能体绑定的 KB 检索；命中返回 RetrievedChunk 列表；写 retrieval span。"""
    from app.ai.rag.retrieval import hybrid_search
    from app.models import AgentKB
    from app.observability.spans import record_span

    bindings = (await db.scalars(select(AgentKB).where(AgentKB.agent_id == agent_id))).all()
    if not bindings:
        return []
    kb_ids = [b.kb_id for b in bindings]
    limit = top_k or max((b.top_k for b in bindings), default=5)
    if session_maker is None:
        from app.core.db import SessionLocal

        session_maker = SessionLocal

    started = time.monotonic()
    try:
        chunks = await hybrid_search(
            session_maker, kb_ids, query, limit, embedder or _default_embedder
        )
        status, err = "ok", None
    except Exception as exc:  # noqa: BLE001 —— 检索失败降级为空结果，生成不中断
        chunks, status, err = [], "error", str(exc)[:300]
    await record_span(
        db,
        trace_id=assistant_id if assistant_id is not None else agent_id,
        type="retrieval",
        name="kb检索",
        session_id=session_id,
        agent_id=agent_id,
        input={"query": query, "kb_ids": [str(k) for k in kb_ids]},
        output={
            "chunks": [
                {"id": c.id, "source": c.source, "score": c.rrf_score} for c in chunks
            ]
        },
        status=status,
        error=err,
        started=started,
    )
    return chunks


def _text_of(blocks: list[dict]) -> str:
    return "".join(b.get("content", "") for b in blocks if b.get("type") == "text")


def _merge_usage(acc: dict | None, new: dict | None) -> dict | None:
    if new is None:
        return acc
    if acc is None:
        return dict(new)
    for key in ("prompt_tokens", "completion_tokens", "total_ms"):
        a, b = acc.get(key), new.get(key)
        if b is not None:
            acc[key] = (a or 0) + b
    if acc.get("first_token_ms") is None:
        acc["first_token_ms"] = new.get("first_token_ms")
    return acc


async def _load_history(
    db: AsyncSession, session_id: uuid.UUID, exclude_ids: set[uuid.UUID], rounds: int
) -> list[dict]:
    rows = (
        await db.scalars(
            select(Message)
            .where(Message.session_id == session_id, Message.id.not_in(exclude_ids))
            .order_by(Message.seq.desc())
            .limit(rounds * 2)
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


async def recover_stale_streaming(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> int:
    """把上次进程遗留的 streaming 消息标记为 error（进程中断的生成无法续传）。

    返回被修复的行数。启动阶段调用；默认使用生产 SessionLocal。
    """
    if session_factory is None:
        from app.core.db import SessionLocal

        session_factory = SessionLocal
    async with session_factory() as db:
        result = await db.execute(
            update(Message)
            .where(Message.status == "streaming")
            .values(status="error", error="生成中断")
        )
        await db.commit()
        return int(result.rowcount or 0)


async def run_generation(
    db: AsyncSession,
    session: Session,
    provider: ModelProvider,
    *,
    user_content: str | None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    model_manager: ModelManager | None = None,
    agent_override: uuid.UUID | None = None,
    relay_instruction: str | None = None,
) -> AsyncIterator[str]:
    """user_content=None 时仅生成助手消息（重新生成/接力场景）。

    agent_override 指定被 @ 的智能体（接力回合），relay_instruction 注入接力指令。
    """
    user = await db.get(User, session.user_id)
    user_name = user.username if user else ""
    if agent_override is not None:
        from app.models import Agent as AgentModel

        agent = await db.get(AgentModel, agent_override)
        cfg = (
            await build_agent_config(db, agent, session, user_name)
            if agent
            else EffectiveConfig()
        )
    else:
        cfg = await resolve_effective_config(db, session, user_name=user_name)
    exclude_ids: set[uuid.UUID] = set()
    if user_content is not None:
        user_msg = Message(
            session_id=session.id,
            role="user",
            agent_id=cfg.agent_id,
            blocks=[{"type": "text", "content": user_content}],
        )
        db.add(user_msg)
        # 独立事务提交：与 assistant 占位分开；历史排序以 seq 为准，不依赖 created_at
        await db.commit()
        exclude_ids.add(user_msg.id)

    assistant = Message(
        session_id=session.id,
        role="assistant",
        agent_id=cfg.agent_id,
        agent_version=cfg.agent_version,
        blocks=[],
        status="streaming",
        model=cfg.model,
    )
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    assistant_id = assistant.id
    exclude_ids.add(assistant_id)

    blocks: list[dict] = []
    usage: dict | None = None
    status = "done"
    error_text: str | None = None
    first_token_ms: float | None = None
    thinking_started: float | None = None
    t0 = time.monotonic()
    last_flush = t0

    try:
        # message_start 也放在 try 内：客户端在首个事件前断连时，GeneratorExit
        # 能命中下方分支 finalize，避免留下永远 streaming 的僵尸消息
        yield sse("message_start", {"message_id": str(assistant_id), "role": "assistant"})
        messages = (
            [{"role": "system", "content": cfg.system_prompt}] if cfg.system_prompt else []
        )
        if relay_instruction:
            messages.append({"role": "system", "content": f"[接力指令] {relay_instruction}"})
        messages += await _load_history(
            db, session.id, exclude_ids=exclude_ids, rounds=cfg.history_rounds
        )
        if user_content is not None:
            messages.append({"role": "user", "content": user_content})

        retrieval_chunks: list = []
        embedder = _provider_embedder(provider)
        if cfg.agent_id is not None:
            query_text = user_content
            if query_text is None:
                last_user = await db.scalar(
                    select(Message.blocks)
                    .where(Message.session_id == session.id, Message.role == "user")
                    .order_by(Message.seq.desc())
                    .limit(1)
                )
                query_text = _text_of(last_user or [])
            retrieval_chunks = (
                await _retrieve_for_agent(
                    db,
                    cfg.agent_id,
                    query_text,
                    assistant_id=assistant_id,
                    session_id=session.id,
                    session_maker=session_factory,
                    embedder=embedder,
                )
                if query_text
                else []
            )

        if retrieval_chunks:
            from app.ai.rag.retrieval import format_context

            context = format_context(retrieval_chunks)
            if cfg.system_prompt:
                messages[0]["content"] = cfg.system_prompt + "\n\n" + context
            else:
                messages.insert(0, {"role": "system", "content": context})
            citation_blocks = [
                {
                    "type": "citation",
                    "ref": i,
                    "chunk_id": c.id,
                    "source": c.source,
                    "page": c.page,
                    "score": round(c.rrf_score, 4),
                    "similarity": round(c.similarity, 4),
                    "snippet": c.content[:200],
                }
                for i, c in enumerate(retrieval_chunks, 1)
            ]
            blocks.extend(citation_blocks)
            for block in citation_blocks:
                yield sse(
                    "citation",
                    {
                        "message_id": str(assistant_id),
                        **{k: v for k, v in block.items() if k != "type"},
                    },
                )

        if model_manager is not None and model_manager.current != cfg.model:
            yield sse(
                "model_switching",
                {"from": model_manager.current, "to": cfg.model, "stage": "start"},
            )
            switch_info = await model_manager.acquire(cfg.model)
            yield sse(
                "model_switching",
                {
                    "from": switch_info["from"],
                    "to": switch_info["to"],
                    "stage": "done",
                    "duration_ms": switch_info["duration_ms"],
                },
            )

        cancelled = False
        for _ in range(MAX_TOOL_ROUNDS):
            req = ChatRequest(
                model=cfg.model,
                messages=messages,
                tools=tools_payload(cfg.tool_slugs) or None,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                max_tokens=cfg.max_tokens,
                num_ctx=cfg.num_ctx,
            )
            tool_calls: list[dict] = []
            async for ev in provider.chat_stream(req):
                now = time.monotonic()
                if CANCEL_FLAGS.pop(assistant_id, False):
                    status = "stopped"
                    cancelled = True
                    break
                if ev.type == "token":
                    if blocks and blocks[-1]["type"] == "text":
                        blocks[-1]["content"] += ev.payload["delta"]
                    else:
                        if (
                            thinking_started is not None
                            and blocks
                            and blocks[-1]["type"] == "thinking"
                        ):
                            blocks[-1]["duration_ms"] = round((now - thinking_started) * 1000)
                            thinking_started = None
                        blocks.append({"type": "text", "content": ev.payload["delta"]})
                    if first_token_ms is None:
                        first_token_ms = round((now - t0) * 1000, 1)
                    yield sse(
                        "token", {"message_id": str(assistant_id), "delta": ev.payload["delta"]}
                    )
                elif ev.type == "thinking":
                    if blocks and blocks[-1]["type"] == "thinking":
                        blocks[-1]["content"] += ev.payload["delta"]
                    else:
                        blocks.append(
                            {
                                "type": "thinking",
                                "content": ev.payload["delta"],
                                "duration_ms": None,
                            }
                        )
                        thinking_started = now
                    yield sse(
                        "thinking", {"message_id": str(assistant_id), "delta": ev.payload["delta"]}
                    )
                elif ev.type == "tool_call":
                    tool_calls.append(ev.payload)
                elif ev.type == "usage":
                    usage = _merge_usage(usage, ev.payload)

                if now - last_flush >= FLUSH_INTERVAL_S:
                    await db.execute(
                        update(Message).where(Message.id == assistant_id).values(blocks=blocks)
                    )
                    await db.commit()
                    last_flush = now

            if cancelled or not tool_calls:
                break

            for call in tool_calls:
                blocks.append(
                    {
                        "type": "tool_call",
                        "id": call["id"],
                        "tool": call["name"],
                        "args": call["args"],
                    }
                )
                yield sse(
                    "tool_call",
                    {
                        "message_id": str(assistant_id),
                        "id": call["id"],
                        "name": call["name"],
                        "args": call["args"],
                    },
                )
            # 协议顺序：assistant(tool_calls) 消息必须先于各条 tool 结果消息
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["name"], "arguments": call["args"]},
                        }
                        for call in tool_calls
                    ],
                }
            )
            cancelled_during_tools = False
            for call in tool_calls:
                if CANCEL_FLAGS.pop(assistant_id, False):
                    status = "stopped"
                    cancelled_during_tools = True
                    break
                started = time.monotonic()
                result, tool_status = await _execute_tool(
                    call["name"],
                    call.get("args") or "",
                    agent_id=cfg.agent_id,
                    db=db,
                    assistant_id=assistant_id,
                    session_id=session.id,
                    session_maker=session_factory,
                    embedder=embedder,
                )
                elapsed = round((time.monotonic() - started) * 1000)
                preview = result[:TOOL_PREVIEW_LEN]
                blocks.append(
                    {
                        "type": "tool_result",
                        "id": call["id"],
                        "tool": call["name"],
                        "status": tool_status,
                        "elapsed_ms": elapsed,
                        "preview": preview,
                    }
                )
                yield sse(
                    "tool_result",
                    {
                        "message_id": str(assistant_id),
                        "id": call["id"],
                        "status": tool_status,
                        "elapsed_ms": elapsed,
                        "preview": preview,
                    },
                )
                messages.append(
                    {"role": "tool", "content": result[:TOOL_RESULT_MAX], "tool_name": call["name"]}
                )
            if cancelled_during_tools:
                break
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
    if (
        session_factory is not None
        and user_content is not None
        and status != "error"
        and session.title == "新对话"
    ):
        from app.services.title_service import generate_title

        asyncio.create_task(
            generate_title(
                session_factory, provider, session.id, user_content, user_content.strip()[:16]
            )
        )
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
