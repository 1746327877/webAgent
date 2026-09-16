from app.ai.rag.splitter import split_markdown, split_text


def test_short_text_not_split():
    assert split_text("短文本。", size=100) == ["短文本。"]


def test_splits_at_sentence_boundary():
    chunks = split_text("第一句。" * 40, size=50, overlap=0)
    assert len(chunks) >= 3
    assert all(len(c) <= 50 for c in chunks)
    # 句末标点优先：所有块都以句号收尾，不会从句子中间断开
    assert all(c.endswith("。") for c in chunks)


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
    assert all(h == ["第一章"] for c, h in chunks if "甲" in c)
    assert all(h == ["第二章"] for c, h in chunks if "乙" in c)


def test_markdown_keeps_heading_line_in_body():
    chunks = split_markdown("# 标题A\n正文内容。", size=100)
    assert len(chunks) == 1
    assert chunks[0][0].startswith("# 标题A")   # 标题词必须进正文，才能进向量
    assert chunks[0][1] == ["标题A"]


def test_markdown_ignores_hash_inside_code_fence():
    text = "# 真标题\n\n```bash\n# 这是代码注释\n```\n\n正文。"
    chunks = split_markdown(text, size=100)
    assert len(chunks) == 1
    assert chunks[0][1] == ["真标题"]


def test_markdown_heading_path_is_nested():
    text = "# 第一章\n\n## 1.1 小节\n\n小节内容。"
    chunks = split_markdown(text, size=100)
    paths = [h for c, h in chunks if "小节内容" in c]
    assert paths == [["第一章", "1.1 小节"]]
