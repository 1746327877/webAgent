import uuid

from sqlalchemy import select, text

from app.core.security import hash_password
from app.models import Agent, AgentKB, Chunk, Document, KnowledgeBase, Span, User


async def _user(db) -> User:
    u = User(
        id=uuid.uuid4(),
        username="alice",
        email="alice@example.com",
        password_hash=hash_password("Passw0rd!"),
    )
    db.add(u)
    await db.flush()
    return u


async def test_kb_document_chunk_roundtrip(session_maker):
    async with session_maker() as db:
        u = await _user(db)
        kb = KnowledgeBase(owner_id=u.id, name="Java 资料")
        db.add(kb)
        await db.flush()
        doc = Document(kb_id=kb.id, filename="a.md", file_type="md", size_bytes=10)
        db.add(doc)
        await db.flush()
        vec = [0.0] * 1024
        vec[0] = 1.0
        chunk = Chunk(
            document_id=doc.id,
            kb_id=kb.id,
            content="并发编程要点",
            content_tokens="并发 编程 要点",
            chunk_index=0,
            embedding=vec,
            meta={"heading_path": "Java/Multithreading"},
        )
        db.add(chunk)
        await db.commit()
        got = await db.scalar(select(Chunk).where(Chunk.id == chunk.id))
        assert got.content == "并发编程要点"
        assert len(list(got.embedding)) == 1024
        # tsv 由分词列生成：simple 配置下 "并发" 可命中
        hit = await db.scalar(
            text("SELECT id FROM chunks WHERE tsv @@ plainto_tsquery('simple', :q)"),
            {"q": "并发"},
        )
        assert hit == chunk.id


async def test_agent_kb_binding_and_span(session_maker):
    async with session_maker() as db:
        u = await _user(db)
        agent = Agent(owner_id=u.id, name="A", system_prompt="", model_config={})
        kb = KnowledgeBase(owner_id=u.id, name="KB")
        db.add_all([agent, kb])
        await db.flush()
        db.add(AgentKB(agent_id=agent.id, kb_id=kb.id, top_k=3, score_threshold=0.2))
        db.add(
            Span(
                trace_id=uuid.uuid4(),
                type="retrieval",
                name="kb检索",
                input={"query": "x"},
                output={"ids": ["c1"]},
                started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                status="ok",
            )
        )
        await db.commit()
        binding = await db.scalar(select(AgentKB).where(AgentKB.agent_id == agent.id))
        assert binding.top_k == 3
        span = await db.scalar(select(Span).where(Span.type == "retrieval"))
        assert span.output["ids"] == ["c1"]
