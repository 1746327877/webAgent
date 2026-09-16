"""文档解析入口：PDF/DOCX 优先用 MinerU，未启用或失败时回退内置解析。

对外只暴露 `extract_document`：返回 `ParsedDoc(kind, pages)`，让下游切分层
知道拿到的是 Markdown 还是纯文本，从而选择对应的分块策略。
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.ai.rag import mineru_client
from app.ai.rag.mineru_client import MinerUError

logger = logging.getLogger("app.rag.parser")

# 需要 MinerU 能力（含 OCR / 表格 / 公式）的输入类型
MINERU_TYPES = {"pdf", "docx"}

# 本身就是 Markdown 的类型：内置解析只读取原文、不改结构，产物仍带 Markdown 结构
MARKDOWN_TYPES = {"md", "markdown"}

# 解析产物格式：MinerU 产物与 .md/.markdown 原文均为 Markdown，其余为纯文本
KIND_MARKDOWN = "markdown"
KIND_TEXT = "text"


@dataclass
class ParsedDoc:
    kind: str  # KIND_MARKDOWN | KIND_TEXT
    pages: list[tuple[int | None, str]]


def extract_document(path: Path, file_type: str) -> ParsedDoc:
    """解析文档为 ParsedDoc：MinerU 成功或 `.md`/`.markdown` 上传 → markdown，其余 → text。"""
    if file_type in MINERU_TYPES and mineru_client.is_enabled():
        try:
            markdown = mineru_client.parse_markdown(path, file_type)
        except MinerUError as exc:
            logger.warning("MinerU 解析失败，回退内置解析 file=%s error=%s", path.name, exc)
        else:
            if markdown.strip():
                # MinerU 输出整篇 Markdown，无稳定页码 → page=None
                return ParsedDoc(kind=KIND_MARKDOWN, pages=[(None, markdown)])
            logger.warning("MinerU 解析结果为空，回退内置解析 file=%s", path.name)

    from app.ai.rag.parsers import extract_text

    kind = KIND_MARKDOWN if file_type in MARKDOWN_TYPES else KIND_TEXT
    return ParsedDoc(kind=kind, pages=extract_text(path, file_type))
