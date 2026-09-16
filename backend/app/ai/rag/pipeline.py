import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import jieba
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models import Chunk, Document, KnowledgeBase

BATCH = 64

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...

    async def aclose(self) -> None: ...


ProviderFactory = Callable[[], EmbeddingProvider]


def _provider_embedder(provider: EmbeddingProvider) -> Embedder:
    async def embed(texts: list[str]) -> list[list[float]]:
        return await provider.embed(texts, settings.embedding_model)

    return embed


async def _set_status(db, doc: Document, status: str, *, error: str | None = None) -> None:
    doc.status = status
    doc.error = error
    await db.commit()


async def run_ingest(
    document_id: str,
    *,
    embedder: Embedder | None = None,
    provider_factory: ProviderFactory | None = None,
    upload_dir: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    provider: EmbeddingProvider | None = None
    embed: Embedder | None = embedder

    base = Path(upload_dir or settings.upload_dir)
    if session_factory is None:
        from app.core.db import SessionLocal

        session_factory = SessionLocal
    try:
        async with session_factory() as db:
            doc = await db.get(Document, uuid.UUID(document_id))
            if doc is None:
                return
            try:
                if embed is None:
                    from app.ai.providers.ollama import OllamaProvider

                    # 单次 ingest 复用一个 provider：各批次嵌入共享连接池，结束统一关闭
                    provider = (
                        provider_factory()
                        if provider_factory is not None
                        else OllamaProvider(settings.ollama_base_url)
                    )
                    embed = _provider_embedder(provider)
                await _set_status(db, doc, "parsing")
                stored = (doc.meta or {}).get("stored_name")
                # 与 _remove_stored_file 对称：落盘名恒为 "{uuid}.{ext}"，含路径分隔符一律拒绝
                if not stored or Path(stored).name != stored:
                    raise FileNotFoundError("上传文件丢失")
                path = base / stored
                if not path.exists():
                    raise FileNotFoundError("上传文件丢失")
                from app.ai.rag.document_parser import KIND_MARKDOWN, extract_document
                from app.ai.rag.splitter import split_markdown, split_text

                # 解析/切片/jieba 都是同步重活，挪到线程池避免阻塞事件循环
                # PDF/DOCX 优先走 MinerU（含 OCR），失败自动回退内置解析；
                # parsed.kind 决定下游按 Markdown 还是纯文本切分
                parsed = await asyncio.to_thread(extract_document, path, doc.file_type)
                meta_pages = doc.meta or {}
                await _set_status(db, doc, "chunking")

                # KB 的 chunk_size/chunk_overlap 真正生效；KB 缺失时回落默认值
                kb = await db.get(KnowledgeBase, doc.kb_id)
                chunk_size = kb.chunk_size if kb is not None else 512
                chunk_overlap = kb.chunk_overlap if kb is not None else 64

                def _split_pages() -> list[tuple[str, dict]]:
                    out: list[tuple[str, dict]] = []
                    for page_no, page_text in parsed.pages:
                        if parsed.kind == KIND_MARKDOWN:
                            for piece, headings in split_markdown(
                                page_text, chunk_size, chunk_overlap
                            ):
                                out.append((piece, {"page": page_no, "headings": headings}))
                        else:
                            for piece in split_text(page_text, chunk_size, chunk_overlap):
                                out.append((piece, {"page": page_no}))
                    return out

                pieces = await asyncio.to_thread(_split_pages)
                if not pieces:
                    raise ValueError("解析结果为空（可能是扫描件）")

                await _set_status(db, doc, "embedding")
                await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
                tokens = await asyncio.to_thread(
                    lambda: [" ".join(jieba.lcut(content)) for content, _ in pieces]
                )
                index = 0
                for start in range(0, len(pieces), BATCH):
                    batch = pieces[start : start + BATCH]
                    vectors = await embed([p[0] for p in batch])
                    for (content, meta), vec, content_tokens in zip(
                        batch, vectors, tokens[start : start + BATCH], strict=True
                    ):
                        db.add(
                            Chunk(
                                document_id=doc.id,
                                kb_id=doc.kb_id,
                                content=content,
                                content_tokens=content_tokens,
                                chunk_index=index,
                                embedding=vec,
                                meta=meta,
                                token_count=len(content),
                            )
                        )
                        index += 1
                    await db.flush()
                doc.chunk_count = len(pieces)
                doc.meta = {**meta_pages, "pages": len(parsed.pages)}
                await _set_status(db, doc, "ready")
            except asyncio.CancelledError:
                # arq 超时/取消抛 BaseException，逃逸会让文档永久停在非终态（前端无限轮询）
                await db.rollback()
                doc = await db.get(Document, uuid.UUID(document_id))
                if doc is not None and doc.status not in ("ready", "failed"):
                    await _set_status(db, doc, "failed", error="处理超时或被取消")
                raise
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                doc = await db.get(Document, uuid.UUID(document_id))
                if doc is not None:
                    await _set_status(db, doc, "failed", error=str(exc)[:500])
    finally:
        if provider is not None:
            await provider.aclose()
