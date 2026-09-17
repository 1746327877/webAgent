"""HTML → IR：docx(mammoth) 与 markdown 库的输出共用这一条解析链路。"""

import re
from html.parser import HTMLParser

from app.ai.convert.ir import (
    Block,
    CodeBlock,
    Heading,
    ListBlock,
    Paragraph,
    Quote,
    Rule,
    Span,
    TableBlock,
)

_VOID_TAGS = {"br", "hr", "img", "meta", "link", "input", "col"}
_HEADING_TAGS = {f"h{level}": level for level in range(1, 7)}
_BOLD_TAGS = {"strong", "b"}
_ITALIC_TAGS = {"em", "i"}
# IR 列表是扁平单层（docs/设计/25 §25.6 已知限制）：行内收集遇到块级标签时先插入
# 换行作项边界再递归，嵌套内容允许被扁平化，但相邻文字绝不能无分隔拼在一起。
# 不含 p/div 等：松散列表的 <p> 若加分隔符会把普通段落拆出多余空行。
_INLINE_BREAK_TAGS = {"ul", "ol", "table", "pre", "blockquote", *_HEADING_TAGS}


class _Node:
    """极简 DOM 节点：元素节点与字符串子节点混排，避免引入 HTML 解析依赖。"""

    __slots__ = ("attrs", "children", "tag")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[_Node | str] = []


class _TreeBuilder(HTMLParser):
    """标准库 HTMLParser → _Node 树；只保留结构，不做合法性校验（输入可信度见设计文档）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs))
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._stack[-1].children.append(_Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        # 容忍畸形 HTML：从栈顶向下找到匹配标签后整体弹出
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data):
        self._stack[-1].children.append(data)


def html_to_blocks(html: str) -> list[Block]:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return _walk(builder.root.children)


def _walk(nodes, *, quote: bool = False) -> list[Block]:
    blocks: list[Block] = []
    for node in nodes:
        if isinstance(node, str):
            spans = _normalize_ws([Span(re.sub(r"\s+", " ", node))])
            if spans:
                blocks.append(Quote(spans) if quote else Paragraph(spans))
            continue
        tag = node.tag
        if tag in _HEADING_TAGS:
            spans = _collect_inline(node.children)
            if spans:
                blocks.append(Heading(_HEADING_TAGS[tag], spans))
        elif tag == "p":
            spans = _collect_inline(node.children)
            if spans:
                blocks.append(Quote(spans) if quote else Paragraph(spans))
        elif tag in ("ul", "ol"):
            items = [
                _collect_inline(child.children)
                for child in node.children
                if isinstance(child, _Node) and child.tag == "li"
            ]
            items = [item for item in items if item]
            if items:
                blocks.append(ListBlock(ordered=tag == "ol", items=items))
        elif tag == "table":
            table = _table(node)
            if table is not None:
                blocks.append(table)
        elif tag == "pre":
            blocks.append(
                CodeBlock(text=_text_of(node.children).rstrip("\n"), language=_code_language(node))
            )
        elif tag == "blockquote":
            blocks.extend(_walk(node.children, quote=True))
        elif tag == "hr":
            blocks.append(Rule())
        elif tag == "br":
            continue
        else:
            # div 等容器与未知标签：递归子内容，保证文本不丢
            blocks.extend(_walk(node.children, quote=quote))
    return blocks


def _collect_inline(nodes, *, bold=False, italic=False, code=False) -> list[Span]:
    spans: list[Span] = []
    for node in nodes:
        if isinstance(node, str):
            spans.append(Span(re.sub(r"\s+", " ", node), bold, italic, code))
            continue
        tag = node.tag
        if tag == "br":
            spans.append(Span("\n"))
        elif tag == "img":
            alt = node.attrs.get("alt", "")
            if alt:
                spans.append(Span(alt))
        elif tag in _BOLD_TAGS:
            spans.extend(_collect_inline(node.children, bold=True, italic=italic, code=code))
        elif tag in _ITALIC_TAGS:
            spans.extend(_collect_inline(node.children, bold=bold, italic=True, code=code))
        elif tag == "code":
            spans.extend(_collect_inline(node.children, bold=bold, italic=italic, code=True))
        elif tag in _INLINE_BREAK_TAGS:
            # 见 _INLINE_BREAK_TAGS 注释：换行作项边界，避免嵌套块的文字被拼接
            spans.append(Span("\n"))
            spans.extend(_collect_inline(node.children, bold=bold, italic=italic, code=code))
        else:
            spans.extend(_collect_inline(node.children, bold=bold, italic=italic, code=code))
    return _normalize_ws(spans)


def _normalize_ws(spans: list[Span]) -> list[Span]:
    """折叠空白：段首段尾去空格、连续空白合并；显式换行（\\n）保留。"""
    out: list[Span] = []
    for span in spans:
        text = span.text if span.text == "\n" else re.sub(r"\s+", " ", span.text)
        if text:
            out.append(Span(text, span.bold, span.italic, span.code))
    if out:
        first = out[0]
        out[0] = Span(first.text.lstrip(" "), first.bold, first.italic, first.code)
        last = out[-1]
        out[-1] = Span(last.text.rstrip(" "), last.bold, last.italic, last.code)
    return [span for span in out if span.text]


def _text_of(nodes) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
        else:
            parts.append(_text_of(node.children))
    return "".join(parts)


def _iter_nodes(nodes):
    for node in nodes:
        if isinstance(node, _Node):
            yield node
            yield from _iter_nodes(node.children)


def _code_language(pre: _Node) -> str:
    for node in _iter_nodes(pre.children):
        if node.tag == "code":
            for name in node.attrs.get("class", "").split():
                if name.startswith("language-"):
                    return name[len("language-") :]
    return ""


def _table(table: _Node) -> TableBlock | None:
    rows: list[list[str]] = []
    for node in _iter_nodes(table.children):
        if node.tag != "tr":
            continue
        cells = [
            _text_of(child.children).strip()
            for child in node.children
            if isinstance(child, _Node) and child.tag in ("td", "th")
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return None
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    # mammoth 不区分表头行，统一把首行当表头（md 管道表亦然）
    return TableBlock(header=normalized[0], rows=normalized[1:])
