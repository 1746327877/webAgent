"""OCR：部署级合成 MCP 绑定（`docs/设计/20`）。

后端不内置 OCR 引擎：图片回合若配置了 `OCR_MCP_URL`，自动挂上该 MCP 的工具，
让模型对扫描件/截图按需取字。通用逻辑见 `app/ai/mcp_slot.py`。
"""

import uuid

from app.ai.mcp_slot import McpSlot
from app.core.config import settings

SERVER_NAME = "ocr"
# 合成绑定的固定标识：只用于分组/去重，不代表数据库行
SYNTHETIC_SERVER_ID = uuid.UUID("00000000-0000-0000-0000-00000000e5e2")

_slot = McpSlot(SERVER_NAME, lambda: settings.ocr_mcp_url, SYNTHETIC_SERVER_ID)


def is_enabled() -> bool:
    """是否配置了 OCR MCP 地址。"""
    return _slot.is_enabled()


async def binding():
    """返回本轮可用的 OCR 绑定；未配置或探测失败时返回 None。"""
    return await _slot.binding()


def reset_cache() -> None:
    """清空探测缓存（测试用）。"""
    _slot.reset_cache()
