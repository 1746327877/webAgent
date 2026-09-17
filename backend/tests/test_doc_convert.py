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


def test_markdown_to_docx_keeps_list_and_code(tmp_path):
    out = convert_file(write(tmp_path, "note.md", MD_SAMPLE), "md", "docx")
    import docx

    document = docx.Document(io.BytesIO(out.data))
    assert "List Bullet" in [p.style.name for p in document.paragraphs]
    assert any("print(1)" in p.text for p in document.paragraphs)


def test_txt_to_markdown_keeps_paragraph_break(tmp_path):
    out = convert_file(write(tmp_path, "a.txt", "第一段\n\n第二段"), "txt", "md")
    assert "第一段\n\n第二段" in out.data.decode("utf-8")


def test_empty_content_is_rejected(tmp_path):
    with pytest.raises(ConvertError, match="未提取到"):
        convert_file(write(tmp_path, "empty.txt", "   \n\n"), "txt", "md")


def test_missing_file_and_unsupported_source(tmp_path):
    with pytest.raises(ConvertError, match="源文件不存在"):
        convert_file(tmp_path / "nope.md", "md", "docx")
    src = write(tmp_path, "a.rtf", "x")
    with pytest.raises(ConvertError, match="不支持的来源格式"):
        convert_file(src, "rtf", "md")


def test_nested_list_items_do_not_merge():
    from app.ai.convert.readers import read_markdown
    from app.ai.convert.writers import to_markdown

    text = to_markdown(read_markdown("- A\n    - A1\n- B\n")).decode("utf-8")
    assert "AA1" not in text
    assert "A1" in text


def test_markdown_table_cell_pipe_is_escaped():
    from app.ai.convert.ir import TableBlock
    from app.ai.convert.writers import to_markdown

    text = to_markdown([TableBlock(header=["a|b", "c"], rows=[])]).decode("utf-8")
    assert "a\\|b" in text


def test_docx_to_markdown_round_trip(tmp_path):
    docx_bytes = convert_file(write(tmp_path, "note.md", MD_SAMPLE), "md", "docx").data
    out = convert_file(write(tmp_path, "note.docx", docx_bytes), "docx", "md")
    text = out.data.decode("utf-8")
    assert "# 标题" in text
    assert "正文包含" in text
    assert "| 列1 | 列2 |" in text


def test_docx_to_html_contains_semantics(tmp_path):
    from app.ai.convert.readers import docx_to_html

    docx_bytes = convert_file(write(tmp_path, "note.md", "# 甲\n\n乙"), "md", "docx").data
    html = docx_to_html(write(tmp_path, "note.docx", docx_bytes))
    assert "<h1>" in html and "甲" in html
