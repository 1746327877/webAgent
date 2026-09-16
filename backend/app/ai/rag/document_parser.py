"""文档解析入口：PDF/DOCX 优先用 MinerU，未启用或失败时回退内置解析。

对外只暴露 `extract_pages`，签名与 `parsers.extract_text` 一致，
流水线不关心用的是哪条路径（"装了更好，不装也能用"）。
"""

import logging
from pathlib import Path

from app.ai.rag import mineru_client
from app.ai.rag.mineru_client import MinerUError

logger = logging.getLogger("app.rag.parser")

# 需要 MinerU 能力（含 OCR / 表格 / 公式）的输入类型
MINERU_TYPES = {"pdf", "docx"}


def extract_pages(path: Path, file_type: str) -> list[tuple[int | None, str]]:
    """解析文档为 [(页码|None, 文本)]；PDF/DOCX 走 MinerU，其余走内置解析。"""
    if file_type in MINERU_TYPES and mineru_client.is_enabled():
        try:
            markdown = mineru_client.parse_markdown(path, file_type)
        except MinerUError as exc:
            logger.warning("MinerU 解析失败，回退内置解析 file=%s error=%s", path.name, exc)
        else:
            if markdown.strip():
                # MinerU 输出整篇 Markdown，无稳定页码 → page=None
                return [(None, markdown)]
            logger.warning("MinerU 解析结果为空，回退内置解析 file=%s", path.name)

    from app.ai.rag.parsers import extract_text

    return extract_text(path, file_type)
