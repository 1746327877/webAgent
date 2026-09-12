import re

HEADING_RE = re.compile(r"^#{1,6}\s")


def _hard_split(block: str, size: int, overlap: int) -> list[str]:
    chunks, start = [], 0
    while start < len(block):
        chunks.append(block[start : start + size])
        start += max(1, size - overlap)
    return chunks


def split_text(text: str, size: int = 512, overlap: int = 64) -> list[str]:
    text = text.strip()
    if not text:
        return []
    blocks: list[str] = []
    current: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if HEADING_RE.match(para) and current:
            blocks.append("\n\n".join(current))
            current = [para]
        else:
            current.append(para)
        if sum(len(p) for p in current) >= size:
            blocks.append("\n\n".join(current))
            current = []
    if current:
        blocks.append("\n\n".join(current))

    chunks: list[str] = []
    for block in blocks:
        if len(block) <= size:
            chunks.append(block)
        else:
            chunks.extend(_hard_split(block, size, overlap))
    return chunks
