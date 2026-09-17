"""文档转换中间结构（IR）：读写两侧的唯一契约（见 docs/设计/25）。

读侧（readers）把不同来源解析成 Block 列表，写侧（writers）再渲染成目标格式；
新增来源或目标只动一侧。表格单元格用纯文本（不做逐格内联样式），因为三种目标
格式对单元格内联的支持差异大，收益低。
"""

from dataclasses import dataclass, field


@dataclass
class Span:
    """一段连续文本及其内联样式。"""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass
class Heading:
    level: int  # 1-6
    spans: list[Span] = field(default_factory=list)


@dataclass
class Paragraph:
    spans: list[Span] = field(default_factory=list)


@dataclass
class ListBlock:
    ordered: bool
    items: list[list[Span]] = field(default_factory=list)


@dataclass
class TableBlock:
    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class CodeBlock:
    text: str
    language: str = ""


@dataclass
class Quote:
    spans: list[Span] = field(default_factory=list)


@dataclass
class Rule:
    """水平分隔线（Markdown `---` / HTML `<hr>`）。"""


@dataclass
class PageBreak:
    """PDF 来源的页边界；md 渲染为分隔线，docx/pdf 渲染为分页。"""


Block = Heading | Paragraph | ListBlock | TableBlock | CodeBlock | Quote | Rule | PageBreak


def spans_text(spans: list[Span]) -> str:
    """内联片段拼回纯文本（表格单元格、PDF 等只需纯文本处使用）。"""
    return "".join(span.text for span in spans)
