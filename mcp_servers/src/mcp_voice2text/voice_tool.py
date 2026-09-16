"""语音转文字工具层：批量转写、保持入参顺序、单文件失败隔离。

与 `server.py` 分开：server 只负责 MCP 注册，这里是可以直接单测的业务逻辑。
"""

from __future__ import annotations

import base64
import binascii
from concurrent.futures import ThreadPoolExecutor

from src.config import settings
from src.logger import get_logger
from src.mcp_voice2text.asr_local import transcribe_source

logger = get_logger("voice2text.tool")

# CPU 上 Whisper 很吃算力：小并发，避免一次多个大音频把机器打满
_executor = ThreadPoolExecutor(max_workers=settings.VOICE_MAX_PARALLEL, thread_name_prefix="asr")


def _decode_items(audios: list[dict] | None) -> list[tuple[str, bytes]]:
    """base64 入参 → [(name, bytes)]；解码失败保留条目以便按序回填错误。"""
    items: list[tuple[str, bytes]] = []
    for entry in audios or []:
        name = str(entry.get("name") or "audio.bin")
        try:
            items.append((name, base64.b64decode(str(entry.get("data_base64") or ""), validate=True)))
        except (binascii.Error, ValueError) as exc:
            logger.error("base64 解码失败 name=%s err=%s", name, exc)
            items.append((name, b""))
    return items


def _read_paths(paths: list[str] | None) -> list[tuple[str, bytes]]:
    items: list[tuple[str, bytes]] = []
    for path in paths or []:
        try:
            with open(path, "rb") as handle:
                items.append((path, handle.read()))
        except OSError as exc:
            logger.error("读取音频失败 path=%s err=%s", path, exc)
            items.append((path, b""))
    return items


def _transcribe_one(name: str, data: bytes) -> dict:
    try:
        text = transcribe_source(data, filename=name)
        logger.info("转写完成 name=%s bytes=%d chars=%d", name, len(data), len(text))
        return {"path": name, "success": True, "text": text, "error": None}
    except Exception as exc:  # noqa: BLE001 —— 单文件失败不影响其它文件
        logger.error("转写失败 name=%s err=%s", name, exc)
        return {"path": name, "success": False, "text": "", "error": str(exc)[:300]}


def transcribe_items(
    audios: list[dict] | None = None,
    paths: list[str] | None = None,
) -> list[dict]:
    """批量转写，返回与入参顺序一致的 `[{path, success, text, error}]`。"""
    items = _decode_items(audios) + _read_paths(paths)
    if not items:
        return []

    results: list[dict] = [{} for _ in items]
    for index, (name, data) in enumerate(items):
        if not data:
            results[index] = {"path": name, "success": False, "text": "", "error": "音频内容为空或读取失败"}

    futures = {
        _executor.submit(_transcribe_one, name, data): index
        for index, (name, data) in enumerate(items)
        if data
    }
    for future, index in futures.items():
        results[index] = future.result()

    logger.info("批量转写完成 count=%d", len(results))
    return results
