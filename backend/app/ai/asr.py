"""语音转写：调用外部 ASR MCP（`docs/设计/23`）。

**平台确定性调用，不把该工具暴露给模型**：音频是二进制，无法经 function-call
参数传给模型；而转写的产物就是文本，模型只需要文本。因此这里只对外暴露一个
`transcribe()` 供 runtime 在生成前调用。
"""

import json
import uuid

from app.ai.mcp_slot import McpSlot
from app.core.config import settings
from app.services import mcp_service

SERVER_NAME = "voice-asr"
# 合成绑定的固定标识：只用于分组/去重，不代表数据库行
SYNTHETIC_SERVER_ID = uuid.UUID("00000000-0000-0000-0000-00000000e5e3")
# 自动挑选工具的名字线索（对齐参考实现的 transcribe_audio_by_storage_key_tool）
TOOL_NAME_HINT = "transcribe"


class AsrError(RuntimeError):
    """转写失败（未配置 / 探测失败 / 调用失败 / 返回不可解析）。"""


_slot = McpSlot(SERVER_NAME, lambda: settings.asr_mcp_url, SYNTHETIC_SERVER_ID)


def is_enabled() -> bool:
    """是否配置了语音转写 MCP 地址。"""
    return _slot.is_enabled()


async def binding():
    """返回探测到的合成绑定；未配置或探测失败返回 None（供能力状态查询）。"""
    return await _slot.binding()


def reset_cache() -> None:
    """清空探测缓存（测试用）。"""
    _slot.reset_cache()


def _pick_tool(binding) -> str:
    """工具名：显式配置优先，否则取名字含 transcribe 的第一个。"""
    configured = (settings.asr_mcp_tool or "").strip()
    if configured:
        return configured
    for tool in binding.tools:
        name = str(tool.get("name") or "")
        if TOOL_NAME_HINT in name.lower():
            return name
    raise AsrError("ASR MCP 未提供 transcribe 工具；可用 ASR_MCP_TOOL 指定工具名")


def _normalize(text: str, paths: list[str]) -> list[dict]:
    """把 MCP 返回文本规整为 [{path, success, text, error}]。

    兼容三种返回形态（见 docs/设计/23 §23.4.2）：JSON 列表、JSON 对象、裸文本。
    """
    raw = (text or "").strip()
    payload = None
    if raw.startswith(("[", "{")):
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None

    if isinstance(payload, list):
        items = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "path": str(item.get("path") or item.get("storage_key") or ""),
                    "success": bool(item.get("success", True)),
                    "text": str(item.get("text") or ""),
                    "error": item.get("error"),
                }
            )
        if items:
            return items

    first = paths[0] if paths else ""
    if isinstance(payload, dict) and payload.get("text"):
        return [{"path": first, "success": True, "text": str(payload["text"]), "error": None}]
    if raw:
        # 裸文本：视为单文件转写结果
        return [{"path": first, "success": True, "text": raw, "error": None}]
    raise AsrError("ASR MCP 返回为空")


async def transcribe(paths: list[str]) -> list[dict]:
    """转写一批音频路径；失败抛 `AsrError`，由调用方降级，不在库层吞掉。"""
    if not paths:
        return []
    binding = await _slot.binding()
    if binding is None:
        raise AsrError("语音转写 MCP 不可用（未配置 ASR_MCP_URL 或连接失败）")
    tool_name = _pick_tool(binding)
    text, status = await mcp_service.call_tool(binding.config, tool_name, {"paths": paths})
    if status != "ok":
        raise AsrError(text)
    return _normalize(text, paths)
