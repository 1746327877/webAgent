from app.ai.rag.splitter import split_text


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
