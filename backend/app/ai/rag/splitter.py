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
    return chunks or _hard_split(text, size, overlap)


def split_text(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    """纯文本递归切分（段落 → 行 → 句末标点 → 空格 → 硬切）。"""
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    return _recursive_split(normalized, size, overlap, SEPARATORS)
