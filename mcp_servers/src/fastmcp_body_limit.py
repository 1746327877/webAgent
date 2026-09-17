"""放宽 FastMCP streamable-http 的请求体上限。

背景：MCP SDK 的 `DEFAULT_MAX_REQUEST_BODY_SIZE` 是 **4MB**，超过直接回 413；
而平台用 base64 传音频（体积放大 ~33%），稍长一点的录音就会撞上。
FastMCP 4.x 的 `create_streamable_http_app` / `FastMCPStreamableHTTPSessionManager`
都没有暴露这个参数（后者连 `**kwargs` 都不透传），因此这里在创建 ASGI app 之前，
把会话管理器换成"带更大上限"的子类。

这是**针对第三方库限制的显式补丁**：改动点集中在本模块的 `install()`，
FastMCP 升级后如果原生支持该参数，直接删掉本文件与调用即可。
"""

from __future__ import annotations

from typing import Any

import fastmcp.server.http as fastmcp_http
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from src.config import settings
from src.logger import get_logger

logger = get_logger("mcp.body_limit")

_Original = fastmcp_http.FastMCPStreamableHTTPSessionManager


class _LargeBodySessionManager(_Original):
    """与 FastMCP 原类行为一致，只把请求体上限调大。

    绕过 FastMCP 的 `__init__`（它不接受该参数、也不透传），直接调 SDK 基类；
    FastMCP 自身只多了一个 `event_store` 属性，子类照样继承。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._shared_event_store = None
        StreamableHTTPSessionManager.__init__(
            self, *args, max_request_body_size=_limit_bytes(), **kwargs
        )


def _limit_bytes() -> int:
    return max(1, settings.MCP_MAX_REQUEST_BODY_MB) * 1024 * 1024


def install() -> None:
    """替换 FastMCP 的会话管理器（幂等：重复调用不会叠加包装）。"""
    if fastmcp_http.FastMCPStreamableHTTPSessionManager is _LargeBodySessionManager:
        return
    fastmcp_http.FastMCPStreamableHTTPSessionManager = _LargeBodySessionManager
    logger.info(
        "已放宽 MCP 请求体上限至 %d MB（base64 音频需要；SDK 默认 4MB）",
        settings.MCP_MAX_REQUEST_BODY_MB,
    )
