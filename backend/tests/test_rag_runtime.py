import uuid

from app.ai.deps import get_provider
from app.main import app
from tests.fake_provider import FakeProvider


async def _prepare(client, auth_headers, session_maker):
    from app.models import AgentKB, Chunk, Document, KnowledgeBase

    aid = (
        await client.post(
            "/api/v1/agents",
            json={"name": "RAG", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()["id"]
    s = (await client.post("/api/v1/sessions", json={"agent_id": aid}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    async with session_maker() as db:
        user = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
        kb = KnowledgeBase(owner_id=uuid.UUID(user["id"]), name="KB")
        db.add(kb)
        await db.flush()
        doc = Document(kb_id=kb.id, filename="java.md", file_type="md", size_bytes=1)
        db.add(doc)
        await db.flush()
        vec = [0.0] * 1024
        vec[0] = 1.0
        db.add(
            Chunk(
                document_id=doc.id,
                kb_id=kb.id,
                content="Java 并发编程的核心是线程与锁",
                content_tokens="Java 并发 编程 的 核心 是 线程 与 锁",
                chunk_index=0,
                embedding=vec,
                meta={"page": 12},
            )
        )
        db.add(AgentKB(agent_id=uuid.UUID(aid), kb_id=kb.id, top_k=3))
        await db.commit()
    return aid, s["id"]


async def test_runtime_injects_context_and_citations(client, auth_headers, session_maker):
    aid, sid = await _prepare(client, auth_headers, session_maker)

    async def emb(texts):
        vec = [0.0] * 1024
        vec[0] = 1.0
        return [vec for _ in texts]

    provider = FakeProvider([("token", {"delta": "并发与锁"})], embed_vectors=None)
    provider.embed_fn = emb  # 对应 FakeProvider 的 embed_fn 属性
    app.dependency_overrides[get_provider] = lambda: provider

    r = await client.post(
        f"/api/v1/sessions/{sid}/messages", json={"content": "Java 并发编程要点？"}, headers=auth_headers
    )
    body = r.text
    assert "event: citation" in body
    assert '"source": "java.md"' in body and '"ref": 1' in body
    req = provider.requests[0]
    sys_msg = req.messages[0]
    assert sys_msg["role"] == "system" and "[知识库检索结果]" in sys_msg["content"]
    assert "[1]" in sys_msg["content"]

    msgs = (await client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)).json()
    types = [b["type"] for b in msgs[1]["blocks"]]
    assert types[0] == "citation"

    from sqlalchemy import select

    from app.models import Span

    async with session_maker() as db:
        span = (await db.scalars(select(Span).where(Span.type == "retrieval"))).first()
        assert span is not None and span.agent_id == uuid.UUID(aid)
        assert span.status == "ok" and span.input["query"]


async def test_no_kb_no_citation(client, auth_headers):
    aid = (
        await client.post(
            "/api/v1/agents",
            json={"name": "P", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()["id"]
    s = (await client.post("/api/v1/sessions", json={"agent_id": aid}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    from app.ai.deps import get_provider as gp

    app.dependency_overrides[gp] = lambda: FakeProvider([("token", {"delta": "x"})])
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    assert "event: citation" not in r.text
