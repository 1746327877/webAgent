"""把 IR 渲染成目标格式（md / docx / pdf）。"""

import io

from app.ai.convert.ir import (
    Block,
    CodeBlock,
    Heading,
    ListBlock,
    PageBreak,
    Paragraph,
    Quote,
    Rule,
    Span,
    TableBlock,
    spans_text,
)

# ---------- 公共 ----------


def _table_rows(block: TableBlock) -> list[list[str]]:
    """补齐每行列数到等宽，返回 [表头, *数据行]；空表返回 []。"""
    width = max([len(block.header), *(len(row) for row in block.rows)], default=0)
    if width == 0:
        return []
    header = list(block.header) + [""] * (width - len(block.header))
    rows = [list(row) + [""] * (width - len(row)) for row in block.rows]
    return [header, *rows]


# ---------- Markdown ----------


def _md_span(span: Span) -> str:
    if span.code:
        return f"`{span.text}`"
    if span.bold and span.italic:
        return f"***{span.text}***"
    if span.bold:
        return f"**{span.text}**"
    if span.italic:
        return f"*{span.text}*"
    return span.text


def _md_spans(spans: list[Span]) -> str:
    return "".join(_md_span(span) for span in spans)


def _md_cell(text: str) -> str:
    """仅转义 markdown 管道表的单元格：竖线会切断列、换行会切断行、反斜杠是转义符。
    只用于 md 渲染路径，docx/pdf 共用 _table_rows 的原文，不能在此处转义。"""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def to_markdown(blocks: list[Block]) -> bytes:
    lines: list[str] = []
    for block in blocks:
        if isinstance(block, Heading):
            lines += ["#" * min(max(block.level, 1), 6) + " " + _md_spans(block.spans), ""]
        elif isinstance(block, Paragraph):
            lines += [_md_spans(block.spans), ""]
        elif isinstance(block, ListBlock):
            for index, item in enumerate(block.items, 1):
                marker = f"{index}." if block.ordered else "-"
                lines.append(f"{marker} {_md_spans(item)}")
            lines.append("")
        elif isinstance(block, CodeBlock):
            fence = f"```{block.language}" if block.language else "```"
            lines += [fence, block.text, "```", ""]
        elif isinstance(block, Quote):
            lines += [f"> {_md_spans(block.spans)}", ""]
        elif isinstance(block, TableBlock):
            rows = _table_rows(block)
            if rows:
                lines.append("| " + " | ".join(_md_cell(cell) for cell in rows[0]) + " |")
                lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
                lines.extend(
                    "| " + " | ".join(_md_cell(cell) for cell in row) + " |" for row in rows[1:]
                )
                lines.append("")
        elif isinstance(block, (PageBreak, Rule)):
            lines += ["---", ""]
    text = "\n".join(lines).strip()
    return (text + "\n").encode("utf-8") if text else b"\n"


# ---------- DOCX ----------


def _fill_runs(paragraph, spans: list[Span]) -> None:
    for span in spans:
        run = paragraph.add_run(span.text)
        run.bold = span.bold
        run.italic = span.italic
        if span.code:
            run.font.name = "Consolas"


def to_docx(blocks: list[Block]) -> bytes:
    import docx
    from docx.shared import Pt

    document = docx.Document()
    for block in blocks:
        if isinstance(block, Heading):
            document.add_heading(spans_text(block.spans), level=min(max(block.level, 1), 6))
        elif isinstance(block, Paragraph):
            _fill_runs(document.add_paragraph(), block.spans)
        elif isinstance(block, ListBlock):
            style = "List Number" if block.ordered else "List Bullet"
            for item in block.items:
                _fill_runs(document.add_paragraph(style=style), item)
        elif isinstance(block, CodeBlock):
            run = document.add_paragraph().add_run(block.text)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        elif isinstance(block, Quote):
            _fill_runs(document.add_paragraph(style="Quote"), block.spans)
        elif isinstance(block, TableBlock):
            rows = _table_rows(block)
            if rows:
                table = document.add_table(rows=1, cols=len(rows[0]))
                table.style = "Table Grid"
                for cell, text in zip(table.rows[0].cells, rows[0], strict=False):
                    cell.text = text
                for row in rows[1:]:
                    for cell, text in zip(table.add_row().cells, row, strict=False):
                        cell.text = text
        elif isinstance(block, PageBreak):
            document.add_page_break()
        elif isinstance(block, Rule):
            document.add_paragraph("―" * 10)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
