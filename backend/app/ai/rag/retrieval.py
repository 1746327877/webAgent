import uuid
from dataclasses import dataclass, field

import jieba
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

TOP_CHANNEL = 40
RRF_K = 60
# 引用来源标签的层级分隔符，format_context 与前端展示保持一致
HEADING_SEPARATOR = " › "


@dataclass
class RetrievedChunk:
    id: str
    content: str
    source: str
    page: int | None
    rrf_score: float
    channel_hits: int
    similarity: float = 0.0
    # 章节路径（如 ["第3章", "3.1 核心参数"]）；历史数据无 meta.headings，
    # 用 default_factory 避免共享可变默认值并回落为空列表
    headings: list[str] = field(default_factory=list)


def jieba_tokens(query: str) -> str:
    return " ".join(jieba.lcut(query))


def _vec_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in vector) + "]"


async def hybrid_search(
    session_maker: async_sessionmaker[AsyncSession],
    kb_ids: list[uuid.UUID],
    query: str,
    top_k: int,
    embedder,
):
    if not kb_ids:
        return []
    vectors = await embedder([query])
    qvec = _vec_literal(vectors[0])
    tokens = jieba_tokens(query)

    sql = text(
        """
        WITH semantic AS (
            SELECT id, 1 - (embedding <=> CAST(:qvec AS vector)) AS sim,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:qvec AS vector)) AS r
            FROM chunks WHERE kb_id = ANY(:kb_ids)
            ORDER BY embedding <=> CAST(:qvec AS vector) LIMIT :chan
        ),
        fulltext AS (
            SELECT c.id, ROW_NUMBER() OVER (ORDER BY ts_rank(c.tsv, q) DESC) AS r
            FROM chunks c, plainto_tsquery('simple', :tokens) q
            WHERE c.kb_id = ANY(:kb_ids) AND c.tsv @@ q
            ORDER BY ts_rank(c.tsv, q) DESC LIMIT :chan
        ),
        fused AS (
            SELECT id, SUM(1.0 / (:rrf + r)) AS rrf_score, count(*) AS channel_hits,
                   MAX(sim) AS similarity
            FROM (
                SELECT id, r, sim FROM semantic
                UNION ALL
                SELECT id, r, NULL AS sim FROM fulltext
            ) t
            GROUP BY id
        )
        SELECT c.id, c.content, c.meta, d.filename, f.rrf_score, f.channel_hits, f.similarity
        FROM fused f JOIN chunks c ON c.id = f.id JOIN documents d ON d.id = c.document_id
        ORDER BY f.rrf_score DESC, c.id LIMIT :top_k
        """
    )
    async with session_maker() as db:
        rows = (
            await db.execute(
                sql,
                {
                    "qvec": qvec,
                    "kb_ids": kb_ids,
                    "tokens": tokens,
                    "chan": TOP_CHANNEL,
                    "rrf": RRF_K,
                    "top_k": top_k,
                },
            )
        ).all()
    out = []
    for row in rows:
        meta = row.meta or {}
        out.append(
            RetrievedChunk(
                id=str(row.id),
                content=row.content,
                source=row.filename,
                page=meta.get("page"),
                rrf_score=float(row.rrf_score),
                channel_hits=int(row.channel_hits),
                similarity=float(row.similarity or 0.0),
                headings=list(meta.get("headings") or []),
            )
        )
    return out


def _source_label(chunk: RetrievedChunk) -> str:
    """来源标签：文件名 [p页码] [› 章节 › 子节]，缺失项自动省略。"""
    label = chunk.source
    if chunk.page:
        label += f" p{chunk.page}"
    if chunk.headings:
        label += HEADING_SEPARATOR + HEADING_SEPARATOR.join(chunk.headings)
    return label


def format_context(chunks: list[RetrievedChunk]) -> str:
    lines = ["[知识库检索结果]"]
    for i, c in enumerate(chunks, 1):
        snippet = c.content[:300].replace("\n", " ")
        lines.append(f"[{i}] (来源: {_source_label(c)}) {snippet}")
    lines.append("回答时请用 [1][2] 形式标注引用；检索结果未覆盖时明确说明。")
    return "\n".join(lines)
