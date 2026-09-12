import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ai.rag.splitter import split_text
from app.models import Chunk, Document, KnowledgeBase, User


def test_splitter_prefers_headings_and_overlaps():
    text = "# 标题一\n第一段内容。" * 1 + "\n\n" + "第二段。" * 200
    chunks = split_text(text, size=100, overlap=10)
    assert len(chunks) >= 2
    assert chunks[0].startswith("# 标题一")
    assert all(len(c) <= 130 for c in chunks)  # 允许切分余量


def test_splitter_hard_split():
    chunks = split_text("字" * 250, size=100, overlap=20)
    assert len(chunks) >= 3


def test_splitter_normalizes_crlf():
    chunks = split_text("# 标题一\r\n第一段。\r\n\r\n第二段。", size=100)
    assert chunks == ["# 标题一\n第一段。\n\n第二段。"]


async def _seed_doc(
    session_maker, upload_dir: Path, content: str = "# 标题\n内容。\n\n第二段。"
) -> tuple:
    async with session_maker() as db:
        u = User(
            id=uuid.uuid4(),
            username="alice",
            email="alice@example.com",
            password_hash="x",
        )
        db.add(u)
        await db.flush()
        kb = KnowledgeBase(owner_id=u.id, name="K")
        db.add(kb)
        await db.flush()
        path = upload_dir / f"{uuid.uuid4()}.md"
        path.write_text(content, encoding="utf-8")
        doc = Document(
            kb_id=kb.id,
            filename="a.md",
            file_type="md",
            size_bytes=len(content),
            meta={"stored_name": path.name},
        )
        db.add(doc)
        await db.commit()
        return str(doc.id), str(kb.id)


async def test_run_ingest_ready_and_chunks(session_maker, tmp_path):
    from app.ai.rag.pipeline import run_ingest

    doc_id, kb_id = await _seed_doc(session_maker, tmp_path)

    async def fake_embedder(texts: list[str]) -> list[list[float]]:
        return [[0.01 * i] * 1024 for i, _ in enumerate(texts)]

    await run_ingest(
        doc_id,
        embedder=fake_embedder,
        upload_dir=str(tmp_path),
        session_factory=session_maker,
    )
    async with session_maker() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        assert doc.status == "ready" and doc.chunk_count >= 1
        chunks = (await db.scalars(select(Chunk).where(Chunk.kb_id == uuid.UUID(kb_id)))).all()
        assert chunks and all(" " in c.content_tokens for c in chunks)
        assert all(len(list(c.embedding)) == 1024 for c in chunks)


async def test_run_ingest_rejects_path_traversal_stored_name(session_maker, tmp_path):
    from app.ai.rag.pipeline import run_ingest

    doc_id, _ = await _seed_doc(session_maker, tmp_path)
    (tmp_path.parent / "outside.md").write_text("越界内容", encoding="utf-8")
    async with session_maker() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        doc.meta = {"stored_name": "../outside.md"}
        await db.commit()

    called = False

    async def unexpected_embedder(texts: list[str]) -> list[list[float]]:
        nonlocal called
        called = True
        return []

    await run_ingest(
        doc_id,
        embedder=unexpected_embedder,
        upload_dir=str(tmp_path),
        session_factory=session_maker,
    )
    assert called is False
    async with session_maker() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        assert doc.status == "failed"
        assert "上传文件丢失" in (doc.error or "")


async def test_run_ingest_failure_sets_failed(session_maker, tmp_path):
    from app.ai.rag.pipeline import run_ingest

    doc_id, _ = await _seed_doc(session_maker, tmp_path)

    async def broken_embedder(texts):
        raise RuntimeError("embed boom")

    await run_ingest(
        doc_id,
        embedder=broken_embedder,
        upload_dir=str(tmp_path),
        session_factory=session_maker,
    )
    async with session_maker() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        assert doc.status == "failed" and "embed boom" in (doc.error or "")


async def test_run_ingest_cancelled_marks_failed_and_reraises(session_maker, tmp_path):
    from app.ai.rag.pipeline import run_ingest

    doc_id, _ = await _seed_doc(session_maker, tmp_path)

    async def cancelling_embedder(texts):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await run_ingest(
            doc_id,
            embedder=cancelling_embedder,
            upload_dir=str(tmp_path),
            session_factory=session_maker,
        )
    async with session_maker() as db:
        doc = await db.get(Document, uuid.UUID(doc_id))
        assert doc.status == "failed"
        assert doc.error == "处理超时或被取消"


async def test_run_ingest_reuses_single_provider(session_maker, tmp_path):
    from app.ai.rag.pipeline import run_ingest

    doc_id, _ = await _seed_doc(session_maker, tmp_path, content="段落一。\n\n段落二。\n\n段落三。")
    created: list[object] = []
    closed: list[int] = []

    class FakeProvider:
        def __init__(self):
            created.append(self)

        async def embed(self, texts, model):
            return [[0.0] * 1024 for _ in texts]

        async def aclose(self):
            closed.append(1)

    def factory() -> FakeProvider:
        return FakeProvider()

    await run_ingest(doc_id, provider_factory=factory, upload_dir=str(tmp_path))
    assert len(created) == 1 and closed == [1]
