"""把不同来源解析成 IR（见 docs/设计/25）。"""

from pathlib import Path

from app.ai.convert.html_reader import html_to_blocks
from app.ai.convert.ir import Block, PageBreak, Paragraph, Span


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


def docx_to_html(path: Path) -> str:
    """docx → 语义 HTML（转换与产物预览复用同一 mammoth 能力）。"""
    import mammoth

    with path.open("rb") as handle:
        return mammoth.convert_to_html(handle).value


def _read_pdf(path: Path) -> list[Block]:
    """pymupdf 逐页抽文本；页与页之间插入 PageBreak，不识别标题/表格（见设计限制）。"""
    import fitz

    blocks: list[Block] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            text = page.get_text("text").strip()
            if not text:
                continue
            if blocks:
                blocks.append(PageBreak())
            blocks.extend(text_paragraphs(text))
    return blocks


def read_source(path: Path, ext: str) -> list[Block]:
    """按扩展名读取来源文档为 IR；未知类型抛 ValueError。"""
    # errors="ignore"：容忍 GBK 等历史编码的不可解码字节，宁可丢个别字符也不让整份文档读取失败
    if ext in ("md", "markdown"):
        return read_markdown(path.read_text(encoding="utf-8", errors="ignore"))
    if ext == "docx":
        return html_to_blocks(docx_to_html(path))
    if ext == "txt":
        return text_paragraphs(path.read_text(encoding="utf-8", errors="ignore"))
    if ext == "pdf":
        return _read_pdf(path)
    raise ValueError(f"不支持的来源格式：{ext}")
