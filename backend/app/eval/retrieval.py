"""检索质量评测：黄金问答集 → recall@k / MRR。

设计见 `docs/设计/22-检索评测.md`。只评"检索是否命中期望来源"，不调用生成模型，
因此可以离线、快速、可重复；回答质量（citation 准确率）属后续阶段。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DEFAULT_AT: tuple[int, ...] = (1, 5, 10)
DEFAULT_TOP_K = 10


class ChunkLike(Protocol):
    """评测只依赖这两个字段，因此可以用假对象做纯单元测试。"""

    source: str
    content: str


@dataclass(frozen=True)
class GoldenItem:
    question: str
    expect_sources: list[str]
    expect_substrings: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class ItemResult:
    question: str
    expect_sources: list[str]
    hit_rank: int | None
    top_sources: list[str]


@dataclass
class EvalReport:
    total: int
    at: tuple[int, ...]
    recall_at: dict[int, float]
    mrr: float
    misses: list[ItemResult]

    def format(self) -> str:
        """人读报告：指标摘要 + 未命中明细（直接指出该往哪调）。"""
        lines = [
            f"共 {self.total} 条",
            "recall@k: " + "  ".join(f"@{k}={self.recall_at[k]:.3f}" for k in self.at),
            f"MRR: {self.mrr:.3f}",
        ]
        if not self.misses:
            lines.append("全部命中")
            return "\n".join(lines)
        lines.append(f"未命中 {len(self.misses)} 条：")
        for miss in self.misses:
            got = "、".join(miss.top_sources) or "（无结果）"
            lines.append(
                f"  - {miss.question}\n"
                f"      期望来源：{'、'.join(miss.expect_sources)}\n"
                f"      实际 top3：{got}"
            )
        return "\n".join(lines)


def load_golden(path: Path | str) -> list[GoldenItem]:
    """读取黄金问答集；结构不合法抛 ValueError，条目不是对象抛 TypeError。

    宁可失败也不静默跑出一个"全 0"报告——那会让人以为检索坏了。
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ValueError("黄金问答集为空：需要 {'items': [...]} 或顶层数组")

    golden: list[GoldenItem] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise TypeError(f"第 {index} 条不是对象")
        question = str(item.get("question") or "").strip()
        sources = item.get("expect_sources")
        if not question:
            raise ValueError(f"第 {index} 条缺少 question")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"第 {index} 条缺少 expect_sources")
        golden.append(
            GoldenItem(
                question=question,
                expect_sources=[str(source) for source in sources],
                expect_substrings=[str(s) for s in (item.get("expect_substrings") or [])],
                note=str(item.get("note") or ""),
            )
        )
    return golden


def is_hit(item: GoldenItem, chunk: ChunkLike) -> bool:
    """命中 = 来源在期望内，且（若标了关键片段）片段全部出现在正文里。"""
    if chunk.source not in item.expect_sources:
        return False
    return all(substring in chunk.content for substring in item.expect_substrings)


def score(
    golden: list[GoldenItem],
    retrieved: dict[str, list[ChunkLike]],
    at: tuple[int, ...] = DEFAULT_AT,
) -> EvalReport:
    """纯函数：把"问题 → 检索结果"折成指标，便于不连库、不连模型单测。"""
    if not golden:
        raise ValueError("黄金问答集为空，无法评测")

    ranks: list[int | None] = []
    misses: list[ItemResult] = []
    for item in golden:
        chunks = retrieved.get(item.question, [])
        rank = next(
            (index for index, chunk in enumerate(chunks, 1) if is_hit(item, chunk)), None
        )
        ranks.append(rank)
        if rank is None:
            misses.append(
                ItemResult(
                    question=item.question,
                    expect_sources=item.expect_sources,
                    hit_rank=None,
                    top_sources=[chunk.source for chunk in chunks[:3]],
                )
            )

    total = len(golden)
    recall_at = {
        k: sum(1 for rank in ranks if rank is not None and rank <= k) / total for k in at
    }
    mrr = sum(1 / rank for rank in ranks if rank is not None) / total
    return EvalReport(total=total, at=at, recall_at=recall_at, mrr=mrr, misses=misses)


async def evaluate(
    session_maker,
    kb_ids,
    golden: list[GoldenItem],
    *,
    top_k: int = DEFAULT_TOP_K,
    at: tuple[int, ...] = DEFAULT_AT,
    embedder,
) -> EvalReport:
    """按黄金问答集逐条跑 `hybrid_search`，汇总成报告。"""
    from app.ai.rag.retrieval import hybrid_search

    retrieved: dict[str, list] = {}
    for item in golden:
        retrieved[item.question] = await hybrid_search(
            session_maker, kb_ids, item.question, top_k, embedder
        )
    return score(golden, retrieved, at=at)
