"""把不同来源解析成 IR（见 docs/设计/25）。"""

from pathlib import Path

from app.ai.convert.html_reader import html_to_blocks
from app.ai.convert.ir import Block, Paragraph, Span


def read_markdown(text: str) -> list[Block]:
    """Markdown → HTML → IR：复用成熟解析库处理标题/列表/表格/代码块。"""
    import markdown

    html = markdown.markdown(text, extensions=["extra", "sane_lists"])
    return html_to_blocks(html)


def text_paragraphs(text: str) -> list[Block]:
    """纯文本按空行分段，保留段落内换行。"""
    blocks: list[Block] = []
    for chunk in text.replace("\r\n", "\n").split("\n\n"):
        chunk = chunk.strip("\n")
        if chunk.strip():
            blocks.append(Paragraph([Span(chunk)]))
    return blocks


def read_source(path: Path, ext: str) -> list[Block]:
    """按扩展名读取来源文档为 IR；未知类型抛 ValueError。"""
    if ext in ("md", "markdown"):
        return read_markdown(path.read_text(encoding="utf-8", errors="ignore"))
    if ext == "txt":
        return text_paragraphs(path.read_text(encoding="utf-8", errors="ignore"))
    raise ValueError(f"不支持的来源格式：{ext}")
