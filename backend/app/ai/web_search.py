"""联网搜索：部署级合成 MCP 绑定。

按 `docs/设计/18` 的决策，不在 `mcp_servers` 表 seed 行，而是在对话按需（输入框
「联网搜索」按钮打开）时，用 `WEB_SEARCH_MCP_URL` 合成一个临时 MCP 绑定注入本轮。
通用逻辑见 `app/ai/mcp_slot.py`。
"""

import uuid

from app.ai.mcp_slot import McpSlot
from app.core.config import settings

SERVER_NAME = "web-search"
# 合成绑定的固定标识：只用于分组/去重，不代表数据库行
SYNTHETIC_SERVER_ID = uuid.UUID("00000000-0000-0000-0000-00000000e5e1")

_slot = McpSlot(SERVER_NAME, lambda: settings.web_search_mcp_url, SYNTHETIC_SERVER_ID)


def is_enabled() -> bool:
    """是否配置了联网搜索 MCP 地址。"""
    return _slot.is_enabled()


async def binding():
    """返回本轮可用的联网搜索绑定；未配置或探测失败时返回 None。"""
    return await _slot.binding()


def reset_cache() -> None:
    """清空探测缓存（测试用）。"""
    _slot.reset_cache()
