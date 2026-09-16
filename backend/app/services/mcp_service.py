"""MCP 客户端：探测（测试连接）与工具调用。

用官方 `mcp` SDK：
- http：`streamable_http_client`（失败回退 `sse_client`），请求头经 `create_mcp_http_client` 注入；
- stdio：`stdio_client` 拉起本地子进程。

所有异常都转成可读中文并截断，绝不向上抛，避免拖垮对话生成。
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

CONNECT_TIMEOUT_S = 15.0
ERROR_MAX_LEN = 300
FIELD_MAX_LEN = 1024

logger = logging.getLogger("app.mcp")

# http 探测失败时补一次直接请求，把笼统的 SDK 报错换成可排查的状态码
_STATUS_HINTS = {
    400: "请求被拒绝，检查 url 与协议是否匹配",
    401: "鉴权失败，检查请求头里的 Token 是否有效",
    403: "无权限，检查账号或 Token 权限",
    404: "地址不存在，检查 url 路径",
    405: "方法不被支持，确认是 streamable http 端点",
    406: "服务端不接受请求头 Accept",
    429: "请求过于频繁，稍后再试",
}


@dataclass
class ProbeResult:
    ok: bool
    tools: list[dict] = field(default_factory=list)
    error: str | None = None
    latency_ms: int | None = None


def server_config(server) -> dict:
    """把 ORM 行转成与 `probe`/`call_tool` 一致的纯配置字典。"""
    return {
        "name": server.name,
        "transport": server.transport,
        "url": server.url,
        "headers": server.headers or {},
        "command": server.command,
        "args": server.args or [],
        "env": server.env or {},
    }


def _clean_headers(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        if name:
            out[name] = str(value)
    return out


def _clean_env(raw: Any) -> dict[str, str]:
    env = get_default_environment()
    if isinstance(raw, dict):
        for key, value in raw.items():
            env[str(key)] = str(value)
    return env


def _non_ascii_header(headers: dict[str, str]) -> str | None:
    for key, value in headers.items():
        if any(ord(ch) > 127 for ch in f"{key}{value}"):
            return key
    return None


async def _http_status_detail(config: dict) -> str | None:
    """SDK 对非 2xx 只给一句笼统错误；这里直连一次拿到状态码与响应片段。"""
    url = str(config.get("url") or "").strip()
    if not url:
        return None
    headers = {
        "Accept": "application/json, text/event-stream",
        **_clean_headers(config.get("headers")),
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "webagent-probe", "version": "1.0"},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
    except Exception:  # noqa: BLE001 —— 诊断是尽力而为，失败就算了
        return None
    if response.status_code < 400:
        return None
    hint = _STATUS_HINTS.get(response.status_code, "")
    snippet = (response.text or "").strip().replace("\n", " ")[:160]
    detail = f"HTTP {response.status_code}"
    if hint:
        detail += f"（{hint}）"
    if snippet:
        detail += f" {snippet}"
    return detail


async def _describe(exc: BaseException, config: dict) -> str:
    message = _friendly(exc)
    if str(config.get("transport") or "").lower() == "http":
        detail = await _http_status_detail(config)
        if detail:
            return f"{message} —— {detail}"
    return message


@contextmanager
def _devnull():
    """给子进程 stderr 一个带 fileno 的文本流（同步打开，满足 lint）。"""
    with open(os.devnull, "w", encoding="utf-8") as handle:
        yield handle


@asynccontextmanager
async def _connect(config: dict) -> AsyncIterator[tuple[Any, Any]]:
    """按 transport 建立 MCP 会话流，产出 (read, write)。"""
    transport = str(config.get("transport") or "").lower()
    async with AsyncExitStack() as stack:
        if transport == "http":
            url = str(config.get("url") or "").strip()
            if not url:
                raise ValueError("缺少 url")
            headers = _clean_headers(config.get("headers"))
            bad_header = _non_ascii_header(headers)
            if bad_header:
                raise ValueError(
                    f"请求头「{bad_header}」含非 ASCII 字符（如中文占位符），请填入真实 Token"
                )
            auth_headers = headers or None
            client = await stack.enter_async_context(create_mcp_http_client(headers=auth_headers))
            streams = None
            first_error: BaseException | None = None
            try:
                streams = await stack.enter_async_context(
                    streamable_http_client(url, http_client=client)
                )
            except BaseException as exc:  # noqa: BLE001 —— 回退 SSE 前先留存首个错误
                first_error = exc
            if streams is None:
                try:
                    streams = await stack.enter_async_context(sse_client(url, headers=auth_headers))
                except BaseException as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"连接失败：{_friendly(first_error or exc)}"
                    ) from (first_error or exc)
            yield streams[0], streams[1]
        elif transport == "stdio":
            command = str(config.get("command") or "").strip()
            if not command:
                raise ValueError("缺少 command")
            args = [str(a) for a in (config.get("args") or [])]
            params = StdioServerParameters(
                command=command, args=args, env=_clean_env(config.get("env"))
            )
            # 子进程 stderr 需要一个带 fileno 的文本流；用 devnull 丢弃，避免默认 stderr 的编码噪声
            errlog = stack.enter_context(_devnull())
            streams = await stack.enter_async_context(stdio_client(params, errlog=errlog))
            yield streams[0], streams[1]
        else:
            raise ValueError(f"不支持的连接方式：{transport or '(空)'}")


def _target(config: dict) -> str:
    """日志用的连接目标描述（不回显请求头，避免泄漏 Token）。"""
    if str(config.get("transport") or "").lower() == "http":
        return f"http url={config.get('url')}"
    args = " ".join(str(a) for a in (config.get("args") or []))
    return f"stdio command={config.get('command')} args={args}".strip()


def _log_probe(config: dict, result: "ProbeResult") -> None:
    name = config.get("name") or "-"
    if result.ok:
        logger.info(
            "MCP 测试连接成功 name=%s %s tools=%d latency_ms=%s",
            name,
            _target(config),
            len(result.tools),
            result.latency_ms,
        )
    else:
        logger.warning(
            "MCP 测试连接失败 name=%s %s error=%s",
            name,
            _target(config),
            result.error,
        )


async def probe(config: dict) -> ProbeResult:
    """连接并列出工具，用于「测试连接」。"""
    started = time.monotonic()
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT_S):
            async with _connect(config) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
        tools = [
            {
                "name": tool.name,
                "description": (tool.description or "")[:FIELD_MAX_LEN],
                # 缓存 input_schema，运行时据此构造 function calling 的 parameters
                "input_schema": tool.input_schema or {"type": "object", "properties": {}},
            }
            for tool in listed.tools
        ]
        result = ProbeResult(ok=True, tools=tools, latency_ms=_elapsed_ms(started))
    except TimeoutError:
        result = ProbeResult(
            ok=False,
            error=f"连接超时（{int(CONNECT_TIMEOUT_S)}s）",
            latency_ms=_elapsed_ms(started),
        )
    except Exception as exc:  # noqa: BLE001 —— 探测失败是预期路径
        result = ProbeResult(
            ok=False, error=await _describe(exc, config), latency_ms=_elapsed_ms(started)
        )
    _log_probe(config, result)
    return result


async def call_tool(config: dict, name: str, arguments: dict | None = None) -> tuple[str, str]:
    """调用 MCP 工具，返回 (文本结果, status)。异常转错误结果，不抛。"""
    server = config.get("name") or "-"
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT_S):
            async with _connect(config) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments or {})
        status = "error" if getattr(result, "is_error", False) else "ok"
        text = _render_result(result)
    except TimeoutError:
        text, status = f"MCP 工具调用超时（{int(CONNECT_TIMEOUT_S)}s）", "error"
    except Exception as exc:  # noqa: BLE001
        text, status = f"MCP 工具调用失败：{await _describe(exc, config)}", "error"

    if status == "ok":
        logger.info("MCP 工具调用成功 server=%s tool=%s", server, name)
    else:
        logger.warning(
            "MCP 工具调用失败 server=%s tool=%s error=%s", server, name, text[:ERROR_MAX_LEN]
        )
    return text, status


def _render_result(result) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
            continue
        dump = None
        if hasattr(item, "model_dump"):
            try:
                dump = item.model_dump(exclude_none=True)
            except Exception:  # noqa: BLE001
                dump = None
        if dump:
            parts.append(json.dumps(dump, ensure_ascii=False)[:FIELD_MAX_LEN])
        else:
            parts.append(f"[{getattr(item, 'type', 'content')}]")
    text = "\n".join(parts).strip()
    structured = getattr(result, "structured_content", None)
    if not text and structured:
        text = json.dumps(structured, ensure_ascii=False)
    return text or "(空结果)"


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _friendly(exc: BaseException) -> str:
    """ExceptionGroup（anyio task group）会嵌套，递归取叶子消息并去重。"""
    messages: list[str] = []

    def walk(err: BaseException) -> None:
        if isinstance(err, BaseExceptionGroup):
            for sub in err.exceptions:
                walk(sub)
        else:
            detail = str(err).strip() or err.__class__.__name__
            messages.append(f"{err.__class__.__name__}: {detail}")

    walk(exc)
    text = "; ".join(dict.fromkeys(messages)) or repr(exc)
    return text[:ERROR_MAX_LEN]
