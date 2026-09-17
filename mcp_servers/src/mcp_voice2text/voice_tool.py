"""语音转文字工具层：批量转写、保持入参顺序、单文件失败隔离。

与 `server.py` 分开：server 只负责 MCP 注册，这里是可以直接单测的业务逻辑。
"""

from __future__ import annotations

import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.config import settings
from src.logger import get_logger
from src.mcp_voice2text.asr_local import transcribe_source

logger = get_logger("voice2text.tool")

# CPU 上 Whisper 很吃算力：小并发，避免一次多个大音频把机器打满
_executor = ThreadPoolExecutor(max_workers=settings.VOICE_MAX_PARALLEL, thread_name_prefix="asr")

# 出错的提示语：这两句是给**调用方（模型或人）**看的，必须说清"怎么改"。
# 最常见的误用是模型把附件文件名当成路径传进来（平台已自动转写，本服务读不到该文件）。
_HINT_BASE64_MISSING = (
    "缺少 data_base64。本服务与平台不共享文件系统，请改用 audios=[{\"name\":..., \"data_base64\":...}]；"
    "平台上传的音频已由平台自动转写并注入上下文，通常无需调用本工具。"
)


def _decode_items(audios: list[dict] | None) -> list[tuple[str, bytes, str | None]]:
    """base64 入参 → [(name, bytes, error)]；把"没传 data_base64"和"解码失败"分开报。"""
    items: list[tuple[str, bytes, str | None]] = []
    for entry in audios or []:
        name = str(entry.get("name") or "audio.bin")
        raw = str(entry.get("data_base64") or "").strip()
        if not raw:
            logger.error("缺少 data_base64 name=%s", name)
            items.append((name, b"", _HINT_BASE64_MISSING))
            continue
        try:
            items.append((name, base64.b64decode(raw, validate=True), None))
        except (binascii.Error, ValueError) as exc:
            logger.error("base64 解码失败 name=%s err=%s", name, exc)
            items.append((name, b"", f"data_base64 解码失败：{exc}"))
    return items


def _hint_for_path(path: str) -> str:
    """模型误用工具时最典型的入参就是"只是个文件名"，这里给针对性的提示。"""
    if _is_bare_name(path):
        return (
            f"{path} 是文件名而不是路径。本服务读不到平台的上传目录，"
            "平台上传的音频已由平台自动转写并注入上下文，**无需调用本工具**；"
            "确实要直接调用时请传本服务可访问的绝对路径，或用 audios + data_base64。"
        )
    return (
        f"读不到文件 {path}。paths 只接受本服务能访问的绝对路径（需与平台共享目录）；"
        "跨文件系统时请改用 audios + data_base64。"
    )


def _read_paths(paths: list[str] | None) -> list[tuple[str, bytes, str | None]]:
    items: list[tuple[str, bytes, str | None]] = []
    for path in paths or []:
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            logger.error("读取音频失败 path=%s err=%s", path, exc)
            items.append((path, b"", _hint_for_path(path)))
            continue
        if not data:
            items.append((path, b"", f"文件是空的：{path}"))
            continue
        items.append((path, data, None))
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
    pending: dict = {}
    for index, (name, data, error) in enumerate(items):
        if error or not data:
            results[index] = {
                "path": name,
                "success": False,
                "text": "",
                "error": error or "音频内容为空",
            }
            continue
        pending[_executor.submit(_transcribe_one, name, data)] = index

    for future, index in pending.items():
        results[index] = future.result()

    logger.info("批量转写完成 count=%d", len(results))
    return results


def _is_bare_name(source: str) -> bool:
    """判断是否只是文件名（不含目录分隔符）——这是模型误用工具时的典型入参。"""
    return "/" not in source and "\\" not in source and Path(source).name == source
