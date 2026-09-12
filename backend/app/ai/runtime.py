import asyncio
import base64
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.agent_config import EffectiveConfig, build_agent_config, resolve_effective_config
from app.ai.model_manager import ModelManager
from app.ai.providers.base import ChatRequest, ModelProvider
from app.ai.tools.registry import tools_payload
from app.core.config import settings
from app.models.session import Attachment, Message, Session
from app.models.user import User

FLUSH_INTERVAL_S = 0.2
MAX_ERROR_LEN = 500
MAX_TOOL_ROUNDS = 5
TOOL_TIMEOUT_S = 30.0
TOOL_RESULT_MAX = 8000
TOOL_PREVIEW_LEN = 200
# 单个附件注入上下文上限，防止超大文档挤爆 prompt
MAX_DOCUMENT_CONTEXT_CHARS = 8000
CANCEL_FLAGS: dict[uuid.UUID, bool] = {}
CANCEL_SESSIONS: set[uuid.UUID] = set()  # 会话级停止标记，供排队中的接力回合消费

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
    span_buffer=None,
    user_id: uuid.UUID | None = None,
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
                    span_buffer=span_buffer,
                    user_id=user_id,
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
    span_buffer=None,
    user_id: uuid.UUID | None = None,
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
    started_at = datetime.now(UTC)
    try:
        chunks = await hybrid_search(
            session_maker, kb_ids, query, limit, embedder or _default_embedder
        )
        status, err = "ok", None
    except Exception as exc:  # noqa: BLE001 —— 检索失败降级为空结果，生成不中断
        chunks, status, err = [], "error", str(exc)[:300]
    output = {"chunks": [{"id": c.id, "source": c.source, "score": c.rrf_score} for c in chunks]}
    if span_buffer is not None:
        span_buffer.add(
            type="retrieval",
            name="kb检索",
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            input={"query": query, "kb_ids": [str(k) for k in kb_ids]},
            output=output,
            status=status,
            error=err,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    else:
        await record_span(
            db,
            trace_id=assistant_id if assistant_id is not None else agent_id,
            type="retrieval",
            name="kb检索",
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            input={"query": query, "kb_ids": [str(k) for k in kb_ids]},
            output=output,
            status=status,
            error=err,
            started=started,
        )
    return chunks


def _text_of(blocks: list[dict]) -> str:
    return "".join(b.get("content", "") for b in blocks if b.get("type") == "text")


def _encode_image(path: str) -> str:
    """Ollama images 字段要求无前缀的 base64。"""
    return base64.b64encode(Path(path).read_bytes()).decode()


def _extract_document_text(path: str, file_type: str) -> str:
    """复用 RAG 解析器抽取文档纯文本（同步重活，调用方放线程池）。"""
    from app.ai.rag.parsers import extract_text

    pages = extract_text(Path(path), file_type)
    return "\n".join(text for _, text in pages)


async def _document_context_notes(
    document_files: list[tuple[str, str, str]],
) -> list[str]:
    """逐个抽取文档文本并截断；任一文件失败只产出提示，不影响本轮生成。"""
    extracted = await asyncio.gather(
        *(
            asyncio.to_thread(_extract_document_text, path, ext)
            for path, ext, _ in document_files
        ),
        return_exceptions=True,
    )
    notes: list[str] = []
    for (_path, _ext, name), result in zip(document_files, extracted, strict=False):
        if isinstance(result, BaseException):
            notes.append(f"【附件：{name}】文本提取失败，已跳过该附件。")
            continue
        text = (result or "").strip()
        if not text:
            notes.append(f"【附件：{name}】未提取到文本内容。")
            continue
        truncated = text[:MAX_DOCUMENT_CONTEXT_CHARS]
        suffix = "（内容已截断）" if len(text) > MAX_DOCUMENT_CONTEXT_CHARS else ""
        notes.append(f"【附件：{name}{suffix}】\n{truncated}")
    return notes


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
    spans=None,
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
    if spans is not None:
        await spans.flush(db)


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
    model_override: str | None = None,
    image_paths: list[str] | None = None,
    document_files: list[tuple[str, str, str]] | None = None,
    attachment_ids: list[uuid.UUID] | None = None,
) -> AsyncIterator[str]:
    """user_content=None 时仅生成助手消息（重新生成/接力场景）。

    agent_override 指定被 @ 的智能体（接力回合），relay_instruction 注入接力指令。
    model_override 覆盖主回合模型（非空时生效）；有图时视觉模型优先于该覆盖。
    image_paths 非空时该轮切到视觉模型，并把图片 base64 附到最后一条 user 消息；
    document_files 为 (落盘路径, 扩展名, 原始文件名) 列表，抽取文本后以 system 上下文注入；
    attachment_ids 在用户消息落库后回填 message_id。
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
    if image_paths:
        # 有图回合按需切到视觉模型；无 agent 或未配置时回退全局设置
        from app.models import Agent as AgentModel

        vision_agent = (
            await db.get(AgentModel, agent_override or session.agent_id)
            if (agent_override or session.agent_id)
            else None
        )
        vision_model = (
            (vision_agent.model_config or {}).get("vision_model")
            if vision_agent
            else None
        )
        cfg = replace(cfg, model=vision_model or settings.vision_model)
    elif model_override:
        # 无图时用户显式选择的模型覆盖智能体默认；未知模型由 ModelManager 加载失败路径报错
        cfg = replace(cfg, model=model_override)
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
        if attachment_ids:
            await db.execute(
                update(Attachment)
                .where(Attachment.id.in_(attachment_ids))
                .values(message_id=user_msg.id)
            )
            await db.commit()

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

    from app.observability.spans import SpanBuffer

    spans = SpanBuffer(
        trace_id=assistant_id,
        session_id=session.id,
        message_id=assistant_id,
        agent_id=cfg.agent_id,
        user_id=session.user_id,
    )

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
        image_payload: list[str] = []
        if image_paths:
            image_payload = list(
                await asyncio.gather(
                    *(asyncio.to_thread(_encode_image, path) for path in image_paths)
                )
            )
        document_notes = (
            await _document_context_notes(document_files) if document_files else []
        )
        messages = (
            [{"role": "system", "content": cfg.system_prompt}] if cfg.system_prompt else []
        )
        if relay_instruction:
            messages.append({"role": "system", "content": f"[接力指令] {relay_instruction}"})
        messages += await _load_history(
            db, session.id, exclude_ids=exclude_ids, rounds=cfg.history_rounds
        )
        if document_notes:
            messages.append(
                {
                    "role": "system",
                    "content": "以下是用户本轮上传的文档内容，请结合这些资料回答：\n\n"
                    + "\n\n".join(document_notes),
                }
            )
        if user_content is not None:
            user_message: dict = {"role": "user", "content": user_content}
            if image_payload:
                user_message["images"] = image_payload
            messages.append(user_message)

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
                    span_buffer=spans,
                    user_id=session.user_id,
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
            switch_started = datetime.now(UTC)
            switch_info = await model_manager.acquire(cfg.model)
            spans.add(
                type="model_switch",
                name=cfg.model,
                model=cfg.model,
                status="ok",
                input={"from": switch_info["from"], "to": switch_info["to"]},
                output={
                    "duration_ms": switch_info["duration_ms"],
                    "switched": switch_info["switched"],
                },
                started_at=switch_started,
                ended_at=datetime.now(UTC),
                duration_ms=switch_info["duration_ms"],
            )
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
            round_started_mono = time.monotonic()
            round_started_at = datetime.now(UTC)
            round_first_token_ms: float | None = None
            round_usage: dict | None = None
            round_text: list[str] = []
            round_status, round_error = "ok", None
            round_span_id = None
            try:
                async for ev in provider.chat_stream(req):
                    now = time.monotonic()
                    if CANCEL_FLAGS.pop(assistant_id, False):
                        status = "stopped"
                        round_status = "stopped"
                        cancelled = True
                        break
                    if ev.type == "token":
                        round_text.append(ev.payload["delta"])
                        if round_first_token_ms is None:
                            round_first_token_ms = round((now - t0) * 1000, 1)
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
                            "token",
                            {"message_id": str(assistant_id), "delta": ev.payload["delta"]},
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
                            "thinking",
                            {"message_id": str(assistant_id), "delta": ev.payload["delta"]},
                        )
                    elif ev.type == "tool_call":
                        tool_calls.append(ev.payload)
                    elif ev.type == "usage":
                        round_usage = ev.payload
                        usage = _merge_usage(usage, ev.payload)

                    if now - last_flush >= FLUSH_INTERVAL_S:
                        await db.execute(
                            update(Message).where(Message.id == assistant_id).values(blocks=blocks)
                        )
                        await db.commit()
                        last_flush = now
            except (asyncio.CancelledError, GeneratorExit):
                # 断连/取消是 BaseException，不会进 except Exception：必须显式记 stopped
                round_status = "stopped"
                raise
            except Exception as exc:  # 记录 llm span 后交给外层统一转 SSE error
                round_status, round_error = "error", str(exc)[:300]
                raise
            finally:
                round_span_id = spans.add(
                    type="llm",
                    name=cfg.model,
                    model=cfg.model,
                    status=round_status,
                    error=round_error,
                    prompt_tokens=(round_usage or {}).get("prompt_tokens"),
                    completion_tokens=(round_usage or {}).get("completion_tokens"),
                    input={"messages": messages},
                    output={"text": "".join(round_text), "first_token_ms": round_first_token_ms},
                    started_at=round_started_at,
                    ended_at=datetime.now(UTC),
                    duration_ms=round((time.monotonic() - round_started_mono) * 1000),
                )
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
                tool_started_at = datetime.now(UTC)
                result, tool_status = await _execute_tool(
                    call["name"],
                    call.get("args") or "",
                    agent_id=cfg.agent_id,
                    db=db,
                    assistant_id=assistant_id,
                    session_id=session.id,
                    session_maker=session_factory,
                    embedder=embedder,
                    span_buffer=spans,
                    user_id=session.user_id,
                )
                elapsed = round((time.monotonic() - started) * 1000)
                spans.add(
                    type="tool",
                    name=call["name"],
                    status=tool_status,
                    parent_span_id=round_span_id,
                    input={"args": call.get("args")},
                    output={"result": result[:TOOL_RESULT_MAX]},
                    started_at=tool_started_at,
                    ended_at=datetime.now(UTC),
                    duration_ms=elapsed,
                )
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
        await _finalize(db, assistant_id, session.id, blocks, "stopped", usage, None, spans=spans)
        raise
    except GeneratorExit:
        await _finalize(db, assistant_id, session.id, blocks, "stopped", usage, None, spans=spans)
        raise
    except Exception as exc:  # noqa: BLE001 —— 边界处转 SSE error
        status = "error"
        error_text = str(exc)[:MAX_ERROR_LEN]
        yield sse("error", {"message_id": str(assistant_id), "message": "生成失败，请重试"})
    finally:
        if thinking_started is not None and blocks and blocks[-1]["type"] == "thinking":
            blocks[-1]["duration_ms"] = round((time.monotonic() - thinking_started) * 1000)

    await _finalize(db, assistant_id, session.id, blocks, status, usage, error_text, spans=spans)
    if (
        session_factory is not None
        and user_content is not None
        and status != "error"
        and session.title == "新对话"
        and session.id not in CANCEL_SESSIONS
    ):
        # 会话级停止待消费（接力排队空档被点停）：不再排队标题生成
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
