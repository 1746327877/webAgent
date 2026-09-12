import uuid

from app.ai.deps import get_provider
from app.main import app
from tests.fake_provider import FakeProvider


async def _rag_session(client, auth_headers, session_maker):
    from app.models import AgentKB, Chunk, Document, KnowledgeBase

    aid = (
        await client.post(
            "/api/v1/agents",
            json={"name": "R2", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()["id"]
    s = (await client.post("/api/v1/sessions", json={"agent_id": aid}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    me = (await client.get("/api/v1/auth/me", headers=auth_headers)).json()
    async with session_maker() as db:
        kb = KnowledgeBase(owner_id=uuid.UUID(me["id"]), name="KB")
        db.add(kb)
        await db.flush()
        doc = Document(kb_id=kb.id, filename="j.md", file_type="md", size_bytes=1)
        db.add(doc)
        await db.flush()
        vec = [0.0] * 1024
        vec[0] = 1.0
        db.add(
            Chunk(
                document_id=doc.id,
                kb_id=kb.id,
                content="线程池参数包括 corePoolSize",
                content_tokens="线程池 参数 包括 corePoolSize",
                chunk_index=0,
                embedding=vec,
            )
        )
        db.add(AgentKB(agent_id=uuid.UUID(aid), kb_id=kb.id, top_k=3))
        await db.commit()
    return aid, s["id"]


def _embed():
    async def emb(texts):
        vec = [0.0] * 1024
        vec[0] = 1.0
        return [vec for _ in texts]

    return emb


async def test_citation_includes_similarity(client, auth_headers, session_maker):
    _aid, sid = await _rag_session(client, auth_headers, session_maker)
    provider = FakeProvider([("token", {"delta": "ok"})])
    provider.embed_fn = _embed()
    app.dependency_overrides[get_provider] = lambda: provider
    r = await client.post(
        f"/api/v1/sessions/{sid}/messages", json={"content": "线程池参数"}, headers=auth_headers
    )
    assert '"similarity": 1.0' in r.text or '"similarity":1.0' in r.text
    msgs = (await client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)).json()
    assert msgs[1]["blocks"][0].get("similarity") is not None


async def test_regenerate_keeps_retrieval(client, auth_headers, session_maker):
    _aid, sid = await _rag_session(client, auth_headers, session_maker)
    provider = FakeProvider([("token", {"delta": "答"})])
    provider.embed_fn = _embed()
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{sid}/messages", json={"content": "线程池参数"}, headers=auth_headers
    )
    msgs = (await client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)).json()
    aid_msg = msgs[1]["id"]
    r2 = await client.post(
        f"/api/v1/sessions/{sid}/regenerate", json={"message_id": aid_msg}, headers=auth_headers
    )
    assert "event: citation" in r2.text
    msgs2 = (await client.get(f"/api/v1/sessions/{sid}/messages", headers=auth_headers)).json()
    assert msgs2[1]["blocks"][0]["type"] == "citation"


async def test_kb_search_no_binding_is_error(client, auth_headers, session_maker):
    # 无绑定智能体上直接跑工具循环脚本调用 kb_search
    aid = (
        await client.post(
            "/api/v1/agents",
            json={"name": "NB", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()["id"]
    s = (await client.post("/api/v1/sessions", json={"agent_id": aid}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)
    provider = FakeProvider(
        [
            [("tool_call", {"id": "c1", "name": "kb_search", "args": {"query": "x", "top_k": 9999}})],
            [("token", {"delta": "done"})],
        ]
    )
    app.dependency_overrides[get_provider] = lambda: provider
    await client.post(
        f"/api/v1/sessions/{s['id']}/messages", json={"content": "hi"}, headers=auth_headers
    )
    msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
    result_block = next(b for b in msgs[1]["blocks"] if b["type"] == "tool_result")
    assert result_block["status"] == "error"
    assert "未绑定知识库" in result_block["preview"]


async def test_set_kbs_deduplicates(client, auth_headers):
    kb = (await client.post("/api/v1/kbs", json={"name": "K"}, headers=auth_headers)).json()
    aid = (
        await client.post(
            "/api/v1/agents",
            json={"name": "KD", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()["id"]
    r = await client.put(
        f"/api/v1/agents/{aid}/kbs",
        json={"bindings": [{"kb_id": kb["id"]}, {"kb_id": kb["id"]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200 and len(r.json()["bindings"]) == 1
