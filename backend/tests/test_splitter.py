from app.ai.rag.splitter import split_markdown, split_text


def test_short_text_not_split():
    assert split_text("短文本。", size=100) == ["短文本。"]


def test_splits_at_sentence_boundary():
    chunks = split_text("第一句。" * 40, size=50, overlap=0)
    assert len(chunks) >= 3
    assert all(len(c) <= 50 for c in chunks)
    # 句末标点优先：所有块都以句号收尾，不会从句子中间断开
    assert all(c.endswith("。") for c in chunks)


def test_delimiter_path_preserves_all_content():
    # 数据丢失是最高危失败模式：走分隔符（非硬切兜底）路径时，递归必须原样保留分隔符与正文
    text = "第一句。" * 40
    chunks = split_text(text, size=50, overlap=0)
    assert len(chunks) >= 3
    assert "".join(chunks) == text


def test_falls_back_to_hard_split():
    chunks = split_text("字" * 250, size=100, overlap=20)
    assert len(chunks) >= 3
    assert all(len(c) <= 100 for c in chunks)


def test_hard_split_honors_overlap():
    # overlap 只在硬切路径生效（有分隔符时按分隔符断，不用 overlap）
    # 输入必须非周期：周期串（如 "1234567890" 循环）在 80 是周期倍数时自洽，
    # 会让下面的窗口断言在 overlap=0 时照样成立，等于没验证
    text = "".join(f"{i:03d}" for i in range(100))
    chunks = split_text(text, size=100, overlap=20)
    # 步长 = size - overlap = 80 → 起点 0/80/160/240，最后一块自然收短
    assert [len(c) for c in chunks] == [100, 100, 100, 60]
    assert chunks[0] == text[:100] and chunks[1] == text[80:180]
    # 相邻块共享 20 字重叠
    assert chunks[0][-20:] == chunks[1][:20]
    assert chunks[1][-20:] == chunks[2][:20]
    assert chunks[2][-20:] == chunks[3][:20]
    # 自证非退化：overlap=0 时窗口必须不同，否则本用例的输入又变成了周期串
    assert split_text(text, size=100, overlap=0)[1] != chunks[1]


def test_markdown_does_not_cross_sections():
    text = "# 第一章\n" + "甲" * 300 + "\n\n# 第二章\n" + "乙" * 300
    chunks = split_markdown(text, size=100, overlap=0)
    first = [c for c, _ in chunks if "甲" in c]
    second = [c for c, _ in chunks if "乙" in c]
    assert first and second
    assert all("乙" not in c for c in first)
    assert all("甲" not in c for c in second)
    assert all(e["headings"] == ["第一章"] for c, e in chunks if "甲" in c)
    assert all(e["headings"] == ["第二章"] for c, e in chunks if "乙" in c)


def test_markdown_keeps_heading_line_in_body():
    chunks = split_markdown("# 标题A\n正文内容。", size=100)
    assert len(chunks) == 1
    assert chunks[0][0].startswith("# 标题A")  # 标题词必须进正文，才能进向量
    assert chunks[0][1]["headings"] == ["标题A"]


def test_markdown_ignores_hash_inside_code_fence():
    text = "# 真标题\n\n```bash\n# 这是代码注释\n```\n\n正文。"
    chunks = split_markdown(text, size=100)
    assert len(chunks) == 1
    assert chunks[0][1]["headings"] == ["真标题"]


def test_markdown_heading_path_is_nested():
    text = "# 第一章\n\n## 1.1 小节\n\n小节内容。"
    chunks = split_markdown(text, size=100)
    paths = [e["headings"] for c, e in chunks if "小节内容" in c]
    assert paths == [["第一章", "1.1 小节"]]


# ---- 表格切分（docs/设计/21）----

TABLE = (
    "| 参数 | 值 | 说明 |\n"
    "| --- | --- | --- |\n"
    "| 精度 | ±1% | 直流 |\n"
    "| 范围 | 0-100Ω | 电阻 |\n"
)


def test_short_table_kept_whole_with_meta():
    chunks = split_markdown("# 规格\n\n" + TABLE, size=500)
    table_chunks = [(c, e) for c, e in chunks if e.get("kind") == "table"]
    assert len(table_chunks) == 1
    body, extra = table_chunks[0]
    # 前缀带上所属小节（标题行落在前面的文本块里，表格切片自己只有表头与数据）
    assert body.startswith("规格\n| 参数 | 值 | 说明 |")
    assert "| 精度 | ±1% | 直流 |" in body
    assert extra["header"] == ["参数", "值", "说明"]
    assert extra["row_range"] == [0, 2]
    assert extra["headings"] == ["规格"]
    assert extra["table_index"] == 0


def test_table_prefix_carries_section_path():
    # 小节标题的措辞要能出现在表格切片里，否则"核心参数有哪些"这类问题会被散文切片抢走
    text = "# 线程池参数速查\n\n## 核心参数\n\n| 参数 | 含义 |\n| --- | --- |\n| corePoolSize | 核心线程数 |"
    chunks = split_markdown(text, size=500)
    table_body = next(c for c, e in chunks if e.get("kind") == "table")
    assert "线程池参数速查 › 核心参数" in table_body
    assert "corePoolSize" in table_body


def test_long_table_split_with_header_repeated():
    rows = "\n".join(f"| 行{i} | 数值{i} | 说明{i} |" for i in range(30))
    text = "| 参数 | 值 | 说明 |\n| --- | --- | --- |\n" + rows
    chunks = split_markdown(text, size=200)
    assert len(chunks) > 1
    for body, extra in chunks:
        # 每块都必须重复表头，否则数据行没有列含义
        assert "| 参数 | 值 | 说明 |" in body
        assert "| --- | --- | --- |" in body
        assert extra["kind"] == "table"
        assert extra["header"] == ["参数", "值", "说明"]
    # row_range 连续且完整覆盖 30 行数据
    ranges = [extra["row_range"] for _, extra in chunks]
    assert ranges[0][0] == 0
    assert all(ranges[i][1] == ranges[i + 1][0] for i in range(len(ranges) - 1))
    assert ranges[-1][1] == 30


def test_table_stays_within_its_section():
    text = "# A\n\n" + TABLE + "\n\n# B\n\n正文B。"
    chunks = split_markdown(text, size=500)
    table_chunks = [(c, e) for c, e in chunks if e.get("kind") == "table"]
    assert len(table_chunks) == 1
    assert table_chunks[0][1]["headings"] == ["A"]
    assert all("正文B" not in c for c, _ in table_chunks)


def test_html_table_kept_whole():
    html = "<table>\n<tr><td>a</td><td>b</td></tr>\n</table>"
    chunks = split_markdown("# T\n\n" + html, size=500)
    table_chunks = [(c, e) for c, e in chunks if e.get("kind") == "table"]
    assert len(table_chunks) == 1
    body, extra = table_chunks[0]
    assert "<table>" in body and "</table>" in body
    assert extra["header"] == []


def test_pipe_table_inside_code_fence_is_not_table():
    text = "```\n| a | b |\n| --- | --- |\n| c | d |\n```"
    chunks = split_markdown(text, size=500)
    assert len(chunks) == 1
    assert chunks[0][1].get("kind") is None
