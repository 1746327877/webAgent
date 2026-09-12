import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import jieba
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models import Chunk, Document

BATCH = 64

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]


async def _default_embedder(texts: list[str]) -> list[list[float]]:
    from app.ai.providers.ollama import OllamaProvider

    provider = OllamaProvider(settings.ollama_base_url)
    try:
        return await provider.embed(texts, settings.embedding_model)
    finally:
        await provider.aclose()


async def _set_status(db, doc: Document, status: str, *, error: str | None = None) -> None:
    doc.status = status
    doc.error = error
    await db.commit()


async def run_ingest(
    document_id: str,
    *,
    embedder: Embedder | None = None,
    upload_dir: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    embed = embedder or _default_embedder
    base = Path(upload_dir or settings.upload_dir)
    if session_factory is None:
        from app.core.db import SessionLocal

        session_factory = SessionLocal
    async with session_factory() as db:
        doc = await db.get(Document, uuid.UUID(document_id))
        if doc is None:
            return
        try:
            await _set_status(db, doc, "parsing")
            stored = (doc.meta or {}).get("stored_name")
            # 与 _remove_stored_file 对称：落盘名恒为 "{uuid}.{ext}"，含路径分隔符一律拒绝
            if not stored or Path(stored).name != stored:
                raise FileNotFoundError("上传文件丢失")
            path = base / stored
            if not path.exists():
                raise FileNotFoundError("上传文件丢失")
            from app.ai.rag.parsers import extract_text
            from app.ai.rag.splitter import split_text

            pages = extract_text(path, doc.file_type)
            meta_pages = doc.meta or {}
            await _set_status(db, doc, "chunking")
            pieces: list[tuple[str, dict]] = []
            for page_no, page_text in pages:
                for piece in split_text(page_text):
                    pieces.append((piece, {"page": page_no}))
            if not pieces:
                raise ValueError("解析结果为空（可能是扫描件）")

            await _set_status(db, doc, "embedding")
            await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            index = 0
            for start in range(0, len(pieces), BATCH):
                batch = pieces[start : start + BATCH]
                vectors = await embed([p[0] for p in batch])
                for (content, meta), vec in zip(batch, vectors, strict=True):
                    db.add(
                        Chunk(
                            document_id=doc.id,
                            kb_id=doc.kb_id,
                            content=content,
                            content_tokens=" ".join(jieba.lcut(content)),
                            chunk_index=index,
                            embedding=vec,
                            meta=meta,
                            token_count=len(content),
                        )
                    )
                    index += 1
                await db.flush()
            doc.chunk_count = len(pieces)
            doc.meta = {**meta_pages, "pages": len(pages)}
            await _set_status(db, doc, "ready")
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            doc = await db.get(Document, uuid.UUID(document_id))
            if doc is not None:
                await _set_status(db, doc, "failed", error=str(exc)[:500])
