"""语音转写 MCP 服务（本地 faster-whisper）。

运行：
    python -m mcp_servers.voice_asr.server
默认 streamable-http，监听 VOICE_PORT（默认 10001）。

入参两种形态（任选其一，见 `docs/设计/23-语音转写MCP.md`）：
- `audios`: [{"name": "a.mp3", "data_base64": "..."}]  —— 与平台不同文件系统时用（默认）
- `paths`:  ["/data/uploads/x.mp3"]                    —— 与平台共享卷时用
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from fastmcp import FastMCP

from mcp_servers.voice_asr.asr_local import model_info, transcribe_source

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("voice_asr")

SERVICE_PORT = int(os.getenv("VOICE_PORT", "10001"))
# CPU 上 Whisper 很吃算力，串行+小并发，避免一次多个大音频把机器打满
_MAX_PARALLEL = int(os.getenv("VOICE_MAX_PARALLEL", "2"))

mcp = FastMCP("voice-asr")
_executor = ThreadPoolExecutor(max_workers=_MAX_PARALLEL, thread_name_prefix="asr")


def _transcribe_one(name: str, data: bytes) -> dict:
    try:
        text = transcribe_source(data, filename=name)
        logger.info("转写完成 name=%s bytes=%d chars=%d", name, len(data), len(text))
        return {"path": name, "success": True, "text": text, "error": None}
    except Exception as exc:  # noqa: BLE001 —— 单个文件失败不影响其它文件
        logger.error("转写失败 name=%s err=%s", name, exc)
        return {"path": name, "success": False, "text": "", "error": str(exc)[:300]}


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
    items: list[tuple[str, bytes]] = []
    for entry in audios or []:
        name = str(entry.get("name") or "audio.bin")
        raw = str(entry.get("data_base64") or "")
        try:
            items.append((name, base64.b64decode(raw, validate=True)))
        except (binascii.Error, ValueError) as exc:
            items.append((name, b""))
            logger.error("base64 解码失败 name=%s err=%s", name, exc)

    for path in paths or []:
        try:
            with open(path, "rb") as handle:
                items.append((path, handle.read()))
        except OSError as exc:
            items.append((path, b""))

    if not items:
        return []

    results: list[dict] = [{} for _ in items]
    futures = {
        _executor.submit(_transcribe_one, name, data): index
        for index, (name, data) in enumerate(items)
        if data
    }
    for index, (name, data) in enumerate(items):
        if not data:
            results[index] = {"path": name, "success": False, "text": "", "error": "音频内容为空或读取失败"}

    for future in futures:
        index = futures[future]
        results[index] = future.result()

    logger.info("批量转写完成 count=%d", len(results))
    return results


@mcp.tool()
def health() -> dict:
    """健康检查：返回服务与模型信息（首次调用会触发模型懒加载）。"""
    return {"status": "ok", **model_info()}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=os.getenv("HOST", "0.0.0.0"), port=SERVICE_PORT)
