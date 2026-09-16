"""语音转文字 MCP 服务（本地 faster-whisper）。

单独启动：
    python -m src.mcp_voice2text.server
统一入口启动：
    python -m src.main          # 由 MCP_SERVICE / VOICE_PORT 决定

入参两种形态（任选其一，见 `docs/设计/23-语音转写MCP.md`）：
- `audios`: [{"name": "a.mp3", "data_base64": "..."}]  —— 与平台不同文件系统时用（默认）
- `paths`:  ["/data/uploads/x.mp3"]                    —— 与平台共享卷时用
"""

from __future__ import annotations

from fastmcp import FastMCP

from src.config import settings
from src.mcp_voice2text.asr_local import model_info
from src.mcp_voice2text.voice_tool import transcribe_items

mcp = FastMCP("voice-asr")


@mcp.tool()
def transcribe(
    audios: list[dict] | None = None,
    paths: list[str] | None = None,
) -> list[dict]:
    """把音频转写成简体中文文本，支持批量。

    Args:
        audios: 形如 [{"name": "a.mp3", "data_base64": "<base64 音频字节>"}]。
        paths: 音频文件路径列表（需本服务能读到该路径）。

    Returns:
        [{path, success, text, error}]，顺序与入参一致；path 为文件名或原始路径。
    """
    return transcribe_items(audios=audios, paths=paths)


@mcp.tool()
def health() -> dict:
    """健康检查：返回服务与模型信息（首次调用会触发模型懒加载）。"""
    return {"status": "ok", **model_info()}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=settings.HOST, port=settings.VOICE_PORT)
