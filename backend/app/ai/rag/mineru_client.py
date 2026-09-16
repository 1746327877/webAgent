"""MinerU 文档解析客户端。

MinerU 以独立服务（宿主机 `mineru-api`）运行，本模块通过 HTTP 调用，
把 PDF/DOCX（含扫描件）解析成 Markdown。任何失败都抛 `MinerUError`，
由上层（document_parser）决定是否回退到内置解析。

注意：`/file_parse` 的响应结构以实测为准，这里对常见的几种形态做了兼容；
新增形态时只需扩展 `_extract_markdown`。
"""

import io
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("app.rag.mineru")

# 响应中可能承载 Markdown 的字段名（按优先级）
_MARKDOWN_KEYS = ("md_content", "md", "markdown", "content")
_MAX_ERROR_CHARS = 200


class MinerUError(RuntimeError):
    """MinerU 调用失败（未配置、网络、非 2xx、响应不可解析）。"""


def is_enabled() -> bool:
    return bool((settings.mineru_api_url or "").strip())


def _extract_markdown(payload: Any, *, allow_plain_string: bool = False) -> str:
    """从响应 JSON 里尽力取出 Markdown 文本。

    实测结构（MinerU 3.4.5）：
    - 成功：{"status": "completed", "results": {"<file>": {"md_content": "..."}}}
    - 失败：{"status": "failed", "error": "CUDA is not available."}

    注意：普通字符串只有在 Markdown 字段名下才被当作正文，避免把 task_id 之类误当正文。
    """
    if isinstance(payload, str):
        return payload if allow_plain_string else ""
    if isinstance(payload, list):
        parts = [_extract_markdown(item) for item in payload]
        return "\n\n".join(part for part in parts if part)
    if isinstance(payload, dict):
        for key in _MARKDOWN_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        # 下钻任意嵌套容器（results / data / {"<文件名>": {...}}），不把裸字符串当正文
        for value in payload.values():
            found = _extract_markdown(value)
            if found:
                return found
    return ""


def _markdown_from_zip(raw: bytes) -> str:
    """MinerU 的 zip 结果：取其中的 .md 文件按名字排序拼接。"""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = sorted(n for n in archive.namelist() if n.lower().endswith(".md"))
            parts = [archive.read(name).decode("utf-8", errors="ignore") for name in names]
    except zipfile.BadZipFile as exc:
        raise MinerUError(f"返回的不是有效 zip：{exc}") from exc
    return "\n\n".join(part for part in parts if part.strip())


def parse_markdown(path: Path | str, file_type: str) -> str:
    """调用 MinerU 解析单个文件，返回 Markdown。失败抛 MinerUError。"""
    path = Path(path)
    base = (settings.mineru_api_url or "").strip().rstrip("/")
    if not base:
        raise MinerUError("未配置 MINERU_API_URL")

    url = f"{base}/file_parse"
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise MinerUError(f"读取待解析文件失败：{exc}") from exc

    try:
        with httpx.Client(timeout=settings.mineru_timeout_s) as client:
            response = client.post(
                url,
                files={"files": (path.name, content, "application/octet-stream")},
                data={"return_md": "true", "backend": settings.mineru_backend},
            )
    except httpx.HTTPError as exc:
        raise MinerUError(f"连接 MinerU 失败：{exc}") from exc

    content_type = response.headers.get("content-type", "").lower()
    payload: Any = None
    if "application/json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            payload = None

    if response.status_code >= 400:
        raise MinerUError(_error_message(response.status_code, payload, response.text))

    # 200 也可能是 status=failed（不同版本/参数下），按 error 抛给上层回退
    if isinstance(payload, dict) and str(payload.get("status", "")).lower() == "failed":
        raise MinerUError(f"MinerU 解析失败：{payload.get('error') or '未知错误'}")

    if payload is not None:
        markdown = _extract_markdown(payload)
    elif "zip" in content_type or response.content[:2] == b"PK":
        markdown = _markdown_from_zip(response.content)
    else:
        # 少量部署会直接返回 markdown 文本
        markdown = response.text

    if not markdown.strip():
        logger.warning("MinerU 响应未包含 Markdown file=%s keys=%s", path.name, _keys_hint(response))
    return markdown


def _error_message(status: int, payload: Any, text: str) -> str:
    if isinstance(payload, dict):
        detail = payload.get("error") or payload.get("message")
        if detail:
            return f"MinerU 返回 HTTP {status}：{detail}"
    return f"MinerU 返回 HTTP {status}：{text[:_MAX_ERROR_CHARS]}"


def _keys_hint(response: httpx.Response) -> str:
    """日志辅助：失败时给出响应结构线索，便于适配新版本。"""
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return response.headers.get("content-type", "")
    if isinstance(payload, dict):
        return ",".join(list(payload.keys())[:8])
    return type(payload).__name__
