import re
from collections.abc import Sequence

# 分隔符按"结构强度"从强到弱；"" 表示降到硬切。
# 刻意不含 . , ; ——避免把 v1.2.3 / 小数 / 代码语句从中间切开。
SEPARATORS: tuple[str, ...] = ("\n\n", "\n", "。", "！", "？", "；", " ", "")


def _hard_split(block: str, size: int, overlap: int) -> list[str]:
    """按固定步长硬切，作为所有分隔符都用尽时的兜底（保证块长 <= size）。"""
    chunks, start = [], 0
    while start < len(block):
        chunks.append(block[start : start + size])
        start += max(1, size - overlap)
    return chunks


def _recursive_split(
    text: str, size: int, overlap: int, separators: Sequence[str]
) -> list[str]:
    """按分隔符优先级递归切分，尽量让每块 <= size；分隔符用尽则硬切。"""
    if len(text) <= size:
        return [text]
    if not separators or separators[0] == "":
        return _hard_split(text, size, overlap)

    sep, rest = separators[0], separators[1:]
    parts = text.split(sep)
    # 保留分隔符：除末段外每段补回 sep，保证内容不丢失
    pieces = [p + sep for p in parts[:-1]] + [parts[-1]]

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not piece:
            continue
        if len(current) + len(piece) <= size:
            current += piece
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(piece) > size:
            chunks.extend(_recursive_split(piece, size, overlap, rest))
        else:
            current = piece
    if current:
        chunks.append(current)
    # 防御网：pieces 全为空（例如文本仅由分隔符组成）时退回硬切，避免返回空列表丢掉内容
    return chunks or _hard_split(text, size, overlap)


def split_text(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    """纯文本递归切分：段落 → 行 → 句末标点（。！？；）→ 空格 → 硬切。

    每块长度 <= size；overlap 仅在降到硬切时生效（按分隔符断开的块不重叠）。
    """
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    return _recursive_split(normalized, size, overlap, SEPARATORS)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# 表格识别：管道表（GFM）与 HTML 表。分隔行必须自身含 "|"，避免把 setext 标题/水平线误判成表。
_TABLE_CELL_DELIM_RE = re.compile(r"^:?-{1,}:?$")
_HTML_TABLE_START_RE = re.compile(r"<table\b", re.IGNORECASE)
_HTML_TABLE_END_RE = re.compile(r"</table\s*>", re.IGNORECASE)
# 表格块内无法按行组切分时的兜底分隔符：只按行断，避免在单元格内部（句号/空格）切开
_LINE_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", "")


def _is_pipe_delimiter(line: str) -> bool:
    """GFM 表格分隔行，如 `| --- | :--: |`。"""
    stripped = line.strip()
    if "|" not in stripped or "-" not in stripped:
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(_TABLE_CELL_DELIM_RE.match(cell) for cell in cells)


def _header_cells(header_line: str) -> list[str]:
    """表头行 → 单元格文本列表（去掉首尾管道与空白）。"""
    return [cell.strip() for cell in header_line.strip().strip("|").split("|")]


def _pipe_rows(text: str) -> list[str] | None:
    """返回管道表的行列表；不是管道表则返回 None。"""
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 2 or not _is_pipe_delimiter(lines[1]):
        return None
    return lines


def _iter_blocks(body: str) -> list[tuple[str, str]]:
    """把一节正文切成有序块：("table", 表格原文) 与 ("text", 其余文本)。

    代码围栏内的 `|` 与 `<table>` 不算表格；表格块整块交给 `_split_table`。
    """
    lines = body.split("\n")
    blocks: list[tuple[str, str]] = []
    buf: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            blocks.append(("text", text))
        buf.clear()

    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buf.append(line)
            index += 1
            continue
        if in_fence:
            buf.append(line)
            index += 1
            continue
        if _HTML_TABLE_START_RE.search(line):
            flush()
            collected = [line]
            while not _HTML_TABLE_END_RE.search(collected[-1]) and index + 1 < total:
                index += 1
                collected.append(lines[index])
            blocks.append(("table", "\n".join(collected).strip()))
            index += 1
            continue
        if "|" in line and index + 1 < total and _is_pipe_delimiter(lines[index + 1]):
            flush()
            collected = [line, lines[index + 1]]
            index += 2
            while index < total and "|" in lines[index] and lines[index].strip():
                collected.append(lines[index])
                index += 1
            blocks.append(("table", "\n".join(collected).strip()))
            continue
        buf.append(line)
        index += 1
    flush()
    return blocks


def _render_table_chunk(prefix: str, header_lines: list[str], rows: list[str]) -> str:
    """渲染一个表格块：可选语义前缀 + 表头/分隔行 + 数据行。"""
    body = "\n".join([*header_lines, *rows])
    return f"{prefix}\n{body}" if prefix else body


def _split_oversized_table(
    text: str, size: int, overlap: int, base_meta: dict
) -> list[tuple[str, dict]]:
    """无法按行组切分的表格（HTML 表 / 畸形表）：按行级递归，不保证重复表头。"""
    return [
        (piece, dict(base_meta))
        for piece in _recursive_split(text, size, overlap, _LINE_SEPARATORS)
    ]


def _split_table(
    text: str, size: int, overlap: int, table_index: int
) -> list[tuple[str, dict]]:
    """表格块：管道表整块优先、超长按行组切并重复表头；HTML 表整块保留。

    元数据见 docs/设计/21 §21.3.3。表头完整性优先于长度上限：单行超长时块会超过 size。
    """
    rows = _pipe_rows(text)
    if rows is None:
        # HTML 表不解析行结构：header 固定为空列表，保证 meta 契约统一（消费方不用判 KeyError）
        base_meta = {"kind": "table", "header": [], "table_index": table_index}
        if len(text) <= size:
            return [(text, base_meta)]
        return _split_oversized_table(text, size, overlap, base_meta)

    header_cells = _header_cells(rows[0])
    header_lines = rows[:2]  # 表头行 + 分隔行
    data_rows = rows[2:]
    prefix = f"【表格 · 列：{'、'.join(header_cells)}】" if header_cells else ""
    base_meta = {"kind": "table", "header": header_cells, "table_index": table_index}

    rendered = _render_table_chunk(prefix, header_lines, data_rows)
    if len(rendered) <= size:
        return [(rendered, {**base_meta, "row_range": [0, len(data_rows)]})]
    if not data_rows:
        return _split_oversized_table(text, size, overlap, base_meta)

    chunks: list[tuple[str, dict]] = []
    current: list[str] = []
    start = 0
    for offset, row in enumerate(data_rows):
        if current and len(_render_table_chunk(prefix, header_lines, [*current, row])) > size:
            chunks.append(
                (
                    _render_table_chunk(prefix, header_lines, current),
                    {**base_meta, "row_range": [start, start + len(current)]},
                )
            )
            start = offset
            current = []
        current.append(row)
    if current:
        chunks.append(
            (
                _render_table_chunk(prefix, header_lines, current),
                {**base_meta, "row_range": [start, start + len(current)]},
            )
        )
    return chunks


def _split_markdown_sections(text: str) -> list[tuple[list[str], str]]:
    """按 Markdown 标题分节，返回 [(heading_path, 小节正文)]。

    规则：标题行并入其小节正文；代码围栏内的 # 不算标题；首个标题前的内容 heading_path=[]。
    """
    sections: list[tuple[list[str], str]] = []
    stack: list[tuple[int, str]] = []
    headings: list[str] = []
    buf: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((list(headings), body))
        buf.clear()

    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buf.append(line)
            continue
        match = None if in_fence else _HEADING_RE.match(line)
        if match is None:
            buf.append(line)
            continue
        flush()
        level = len(match.group(1))
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, match.group(2).strip()))
        headings = [title for _, title in stack]
        buf.append(line)
    flush()
    return sections


def split_markdown(
    text: str, size: int = 512, overlap: int = 64
) -> list[tuple[str, dict]]:
    """Markdown 递归切分：先按标题分节，再把每节切成文本块/表格块。

    返回 [(chunk, extra_meta)]；extra_meta 至少含 `headings`，表格块另含
    `kind` / `header` / `row_range` / `table_index`（见 docs/设计/21）。片段不跨章节。
    """
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    out: list[tuple[str, dict]] = []
    table_index = 0
    for headings, section in _split_markdown_sections(normalized):
        for kind, block in _iter_blocks(section):
            if kind == "text":
                for piece in _recursive_split(block, size, overlap, SEPARATORS):
                    out.append((piece, {"headings": list(headings)}))
                continue
            for piece, extra in _split_table(block, size, overlap, table_index):
                out.append((piece, {"headings": list(headings), **extra}))
            table_index += 1
    return out
