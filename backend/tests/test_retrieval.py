import uuid


async def _seed(session_maker):
    from app.models import Chunk, Document, KnowledgeBase, User

    async with session_maker() as db:
        u = User(
            id=uuid.uuid4(), username="alice", email="a@e.com", password_hash="x"
        )
        db.add(u)
        await db.flush()
        kb = KnowledgeBase(owner_id=u.id, name="K")
        db.add(kb)
        await db.flush()
        doc = Document(kb_id=kb.id, filename="java.md", file_type="md", size_bytes=1)
        db.add(doc)
        await db.flush()
        v_semantic = [0.0] * 1024
        v_semantic[0] = 1.0  # 与查询 [1,0,...] 最相似
        v_keyword = [0.0] * 1024
        v_keyword[1] = 1.0  # 与查询正交，但含关键词
        v_other = [0.0] * 1024
        v_other[2] = 1.0
        db.add_all(
            [
                Chunk(document_id=doc.id, kb_id=kb.id, content="完全语义相关", content_tokens="完全 语义 相关",
                      chunk_index=0, embedding=v_semantic),
                Chunk(document_id=doc.id, kb_id=kb.id, content="并发编程关键词命中", content_tokens="并发 编程 关键词 命中",
                      chunk_index=1, embedding=v_keyword),
                Chunk(document_id=doc.id, kb_id=kb.id, content="无关内容", content_tokens="无关 内容",
                      chunk_index=2, embedding=v_other),
            ]
        )
        await db.commit()
        return str(kb.id), str(doc.id)


async def test_hybrid_search_rrf_and_channel_hits(session_maker):
    from app.ai.rag.retrieval import hybrid_search

    kb_id, _ = await _seed(session_maker)

    async def query_embedder(texts: list[str]) -> list[list[float]]:
        vec = [0.0] * 1024
        vec[0] = 1.0
        return [vec for _ in texts]

    chunks = await hybrid_search(
        session_maker,
        [uuid.UUID(kb_id)],
        "并发 编程",
        top_k=3,
        embedder=query_embedder,
    )
    assert len(chunks) == 3
    by_content = {c.content: c for c in chunks}
    # 语义第一：向量通道 rank1；关键词条：全文通道 rank1 → 双通道命中
    assert by_content["并发编程关键词命中"].channel_hits == 2
    assert by_content["完全语义相关"].channel_hits == 1
    # 双通道命中者 RRF 分最高：必须排第一（不能只靠同文档 source 恒真断言）
    assert chunks[0].content == "并发编程关键词命中"
    assert chunks[0].rrf_score > chunks[1].rrf_score
    assert chunks[0].source == "java.md"


async def test_hybrid_search_empty_kbs(session_maker):
    from app.ai.rag.retrieval import hybrid_search

    async def emb(texts):
        return [[0.0] * 1024 for _ in texts]

    assert await hybrid_search(session_maker, [], "x", top_k=5, embedder=emb) == []


async def test_format_context_numbers_sources(session_maker):
    from app.ai.rag.retrieval import RetrievedChunk, format_context

    ctx = format_context(
        [RetrievedChunk(id="c1", content="片段", source="a.md", page=2, rrf_score=0.5, channel_hits=2)]
    )
    assert "[1]" in ctx and "a.md" in ctx and "p2" in ctx
