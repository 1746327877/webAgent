"""文档格式转换：pdf/docx/md/txt → md/docx/pdf（docs/设计/25）。"""

import io

import pytest

from app.ai.convert import ConvertError, convert_file

MD_SAMPLE = (
    "# 标题\n\n"
    "正文包含**粗体**与 `代码`。\n\n"
    "- 甲\n- 乙\n\n"
    "| 列1 | 列2 |\n| --- | --- |\n| a | b |\n\n"
    "```python\nprint(1)\n```\n"
)


def write(tmp_path, name: str, data: str | bytes):
    path = tmp_path / name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


def test_markdown_to_docx_keeps_structure(tmp_path):
    out = convert_file(write(tmp_path, "note.md", MD_SAMPLE), "md", "docx")
    assert out.ext == "docx"
    assert out.mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    import docx

    document = docx.Document(io.BytesIO(out.data))
    headings = [p for p in document.paragraphs if p.style.name == "Heading 1"]
    assert [p.text for p in headings] == ["标题"]
    assert any("正文包含" in p.text for p in document.paragraphs)
    assert len(document.tables) == 1
    assert document.tables[0].cell(0, 0).text == "列1"


def test_txt_to_markdown_splits_paragraphs(tmp_path):
    out = convert_file(write(tmp_path, "a.txt", "第一段\n\n第二段"), "txt", "md")
    text = out.data.decode("utf-8")
    assert "第一段" in text and "第二段" in text


def test_same_format_and_unknown_target_rejected(tmp_path):
    src = write(tmp_path, "note.md", "# x")
    with pytest.raises(ConvertError, match="已经是 md"):
        convert_file(src, "md", "md")
    with pytest.raises(ConvertError, match="目标格式"):
        convert_file(src, "md", "html")
