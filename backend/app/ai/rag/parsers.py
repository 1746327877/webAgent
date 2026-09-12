from pathlib import Path


def extract_text(path: Path, file_type: str) -> list[tuple[int | None, str]]:
    if file_type == "pdf":
        import fitz

        out = []
        with fitz.open(path) as pdf:
            for i, page in enumerate(pdf):
                out.append((i + 1, page.get_text("text")))
        return out
    if file_type == "docx":
        import docx

        d = docx.Document(str(path))
        return [(None, "\n".join(p.text for p in d.paragraphs))]
    return [(None, path.read_text(encoding="utf-8", errors="ignore"))]
