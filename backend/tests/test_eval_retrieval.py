"""检索评测的指标计算与黄金集加载（docs/设计/22）。"""

import json
import uuid

import pytest

from app.eval.retrieval import GoldenItem, is_hit, load_golden, score


class FakeChunk:
    """评测只依赖 source/content，因此不需要真的检索。"""

    def __init__(self, source: str, content: str) -> None:
        self.source = source
        self.content = content


def test_is_hit_requires_source_match():
    item = GoldenItem(question="q", expect_sources=["a.md"])
    assert is_hit(item, FakeChunk("a.md", "任意正文"))
    assert not is_hit(item, FakeChunk("b.md", "任意正文"))


def test_is_hit_gated_by_substrings():
    item = GoldenItem(question="q", expect_sources=["a.md"], expect_substrings=["corePoolSize"])
    assert is_hit(item, FakeChunk("a.md", "包含 corePoolSize 的正文"))
    assert not is_hit(item, FakeChunk("a.md", "来源对但内容不对"))
    assert not is_hit(item, FakeChunk("b.md", "corePoolSize"))


def test_score_recall_and_mrr():
    golden = [
        GoldenItem(question="q1", expect_sources=["a.md"]),
        GoldenItem(question="q2", expect_sources=["b.md"]),
        GoldenItem(question="q3", expect_sources=["c.md"]),
    ]
    retrieved = {
        "q1": [FakeChunk("a.md", "x")],  # 排名 1
        "q2": [FakeChunk("z.md", "x"), FakeChunk("b.md", "y")],  # 排名 2
        "q3": [FakeChunk("z.md", "x")],  # 未命中
    }

    report = score(golden, retrieved, at=(1, 2, 5))

    assert report.total == 3
    assert report.recall_at[1] == pytest.approx(1 / 3)
    assert report.recall_at[2] == pytest.approx(2 / 3)
    assert report.recall_at[5] == pytest.approx(2 / 3)
    assert report.mrr == pytest.approx((1 + 0.5) / 3)
    assert report.rank_counts == {1: 1, 2: 1, 0: 1}
    # 第 2 名进 off_rank（附"前面是谁"），完全未命中进 misses
    assert [item.question for item in report.off_rank] == ["q2"]
    assert report.off_rank[0].hit_rank == 2
    assert report.off_rank[0].above_sources == ["z.md"]
    assert [miss.question for miss in report.misses] == ["q3"]
    assert report.misses[0].above_sources == ["z.md"]
    assert "未排到第 1 名 1 条" in report.format()
    assert "完全未命中 1 条" in report.format()


def test_score_all_hit_reports_clean():
    golden = [GoldenItem(question="q", expect_sources=["a.md"])]
    report = score(golden, {"q": [FakeChunk("a.md", "x")]}, at=(1,))
    assert report.recall_at[1] == 1.0 and report.mrr == 1.0
    assert report.rank_counts == {1: 1}
    assert "第1名 1 条" in report.format()


def test_format_reports_low_rank_without_calling_it_miss():
    # 只在第 2 名命中时，recall@1 < 1，但不应被报成"完全未命中"
    golden = [GoldenItem(question="q", expect_sources=["a.md"])]
    report = score(
        golden, {"q": [FakeChunk("z.md", "x"), FakeChunk("a.md", "y")]}, at=(1, 5)
    )
    text = report.format()
    assert report.recall_at[1] == 0.0 and report.misses == []
    assert "第2名 1 条" in text and "完全未命中" not in text
    assert "实际第 2 名，前面是：z.md" in text


def test_score_rejects_empty_golden():
    with pytest.raises(ValueError):
        score([], {}, at=(1,))


def test_load_golden_reads_items(tmp_path):
    path = tmp_path / "g.json"
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "question": "问题",
                        "expect_sources": ["a.md"],
                        "expect_substrings": ["片段"],
                        "note": "备注",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    golden = load_golden(path)
    assert len(golden) == 1
    assert golden[0].question == "问题"
    assert golden[0].expect_sources == ["a.md"]
    assert golden[0].expect_substrings == ["片段"]
    assert golden[0].note == "备注"


@pytest.mark.parametrize(
    "payload",
    [
        {"items": []},  # 空集
        {"items": [{"question": "", "expect_sources": ["a.md"]}]},  # 缺 question
        {"items": [{"question": "q", "expect_sources": []}]},  # 缺 expect_sources
        "not-a-list",  # 结构非法
    ],
)
def test_load_golden_rejects_bad_shape(tmp_path, payload):
    path = tmp_path / "g.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_golden(path)


async def _seed_doc(session_maker) -> str:
    from app.models import Chunk, Document, KnowledgeBase, User

    async with session_maker() as db:
        user = User(id=uuid.uuid4(), username="eval-user", email="e@e.com", password_hash="x")
        db.add(user)
        await db.flush()
        kb = KnowledgeBase(owner_id=user.id, name="评测")
        db.add(kb)
        await db.flush()
        doc = Document(kb_id=kb.id, filename="thread-pool.md", file_type="md", size_bytes=1)
        db.add(doc)
        await db.flush()
        vector = [0.0] * 1024
        vector[0] = 1.0
        db.add(
            Chunk(
                document_id=doc.id,
                kb_id=kb.id,
                content="线程池核心参数 corePoolSize 与 maximumPoolSize",
                content_tokens="线程池 核心 参数",
                chunk_index=0,
                embedding=vector,
            )
        )
        await db.commit()
        return str(kb.id)


async def test_evaluate_end_to_end(session_maker):
    from app.eval.retrieval import evaluate

    kb_id = await _seed_doc(session_maker)

    async def embed(texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1023 for _ in texts]

    golden = [
        GoldenItem(question="线程池 参数", expect_sources=["thread-pool.md"], expect_substrings=["corePoolSize"]),
        GoldenItem(question="完全不存在的话题", expect_sources=["nope.md"]),
    ]
    report = await evaluate(
        session_maker, [uuid.UUID(kb_id)], golden, top_k=5, at=(1, 5), embedder=embed
    )
    assert report.total == 2
    assert report.recall_at[1] == pytest.approx(0.5)
    assert [miss.question for miss in report.misses] == ["完全不存在的话题"]
