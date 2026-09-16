"""联网搜索：部署级合成 MCP 绑定。

按 `docs/设计/18` 的决策，不在 `mcp_servers` 表 seed 行，而是在对话按需（输入框
「联网搜索」按钮打开）时，用 `WEB_SEARCH_MCP_URL` 合成一个临时 MCP 绑定注入本轮。
探测结果按 URL 缓存，避免每条消息都重新建连。
"""

import logging
import time
import uuid

from app.ai.agent_config import McpBinding
from app.core.config import settings
from app.services import mcp_service

logger = logging.getLogger("app.ai.web_search")

SERVER_NAME = "web-search"
# 合成绑定的固定标识：只用于分组/去重，不代表数据库行
SYNTHETIC_SERVER_ID = uuid.UUID("00000000-0000-0000-0000-00000000e5e1")
CACHE_TTL_S = 300.0

# 进程内探测缓存：(url, 抓取时刻, tools|None)。单事件循环下顺序读写；
# TTL 到期重建，探测失败也缓存 None，避免每条消息都卡在连接超时。
# 多进程/多 worker 部署时各进程各自缓存，最长 300s 不一致，可接受。
_cache: tuple[str, float, list[dict] | None] | None = None


def is_enabled() -> bool:
    """是否配置了联网搜索 MCP 地址。"""
    return bool((settings.web_search_mcp_url or "").strip())


def _config(url: str) -> dict:
    """与 `mcp_service.server_config` 同形的 http 配置（无鉴权，headers 为空）。"""
    return {
        "name": SERVER_NAME,
        "transport": "http",
        "url": url,
        "headers": {},
        "command": None,
        "args": [],
        "env": {},
    }


async def _probe_tools(url: str) -> list[dict] | None:
    """带 TTL 的探测；失败返回 None 并记 warning。"""
    global _cache
    now = time.monotonic()
    if _cache is not None:
        cached_url, fetched_at, tools = _cache
        if cached_url == url and now - fetched_at < CACHE_TTL_S:
            return tools

    result = await mcp_service.probe(_config(url))
    tools = result.tools if result.ok and result.tools else None
    if tools is None:
        logger.warning("联网搜索探测失败 url=%s error=%s", url, result.error)
    _cache = (url, now, tools)
    return tools


async def binding() -> McpBinding | None:
    """返回本轮可用的联网搜索绑定；未配置或探测失败时返回 None。"""
    url = (settings.web_search_mcp_url or "").strip()
    if not url:
        return None
    tools = await _probe_tools(url)
    if not tools:
        return None
    return McpBinding(
        server_id=SYNTHETIC_SERVER_ID,
        server_name=SERVER_NAME,
        config=_config(url),
        tools=tools,
    )


def reset_cache() -> None:
    """清空探测缓存（测试用）。"""
    global _cache
    _cache = None
