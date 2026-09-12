import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, KnowledgeBase
from app.models.user import User


async def get_owned_kb(db: AsyncSession, user: User, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = await db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == user.id
        )
    )
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


async def list_kbs(db: AsyncSession, user: User) -> list[KnowledgeBase]:
    rows = (
        await db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.owner_id == user.id)
            .order_by(KnowledgeBase.created_at.desc(), KnowledgeBase.id)
        )
    ).all()
    return list(rows)


async def create_kb(db: AsyncSession, user: User, data) -> KnowledgeBase:
    kb = KnowledgeBase(owner_id=user.id, name=data.name, description=data.description)
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


async def update_kb(db: AsyncSession, kb: KnowledgeBase, fields: dict) -> KnowledgeBase:
    for key, value in fields.items():
        if value is not None:
            setattr(kb, key, value)
    await db.commit()
    await db.refresh(kb)
    return kb


async def delete_kb(db: AsyncSession, kb: KnowledgeBase) -> None:
    await db.delete(kb)
    await db.commit()


async def list_documents(db: AsyncSession, kb: KnowledgeBase) -> list[Document]:
    rows = (
        await db.scalars(
            select(Document)
            .where(Document.kb_id == kb.id)
            .order_by(Document.created_at.asc(), Document.id)
        )
    ).all()
    return list(rows)


async def get_owned_document(db: AsyncSession, user: User, document_id: uuid.UUID) -> Document:
    doc = await db.scalar(
        select(Document)
        .join(KnowledgeBase, Document.kb_id == KnowledgeBase.id)
        .where(Document.id == document_id, KnowledgeBase.owner_id == user.id)
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


async def create_document(
    db: AsyncSession,
    kb: KnowledgeBase,
    *,
    name: str,
    ext: str,
    size: int,
    user: User,
    stored_name: str,
) -> Document:
    doc = Document(
        kb_id=kb.id,
        filename=name,
        file_type=ext,
        size_bytes=size,
        status="pending",
        meta={"stored_name": stored_name},
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def reset_document(db: AsyncSession, doc: Document) -> Document:
    doc.status = "pending"
    doc.error = None
    await db.commit()
    await db.refresh(doc)
    return doc


async def delete_document(db: AsyncSession, doc: Document) -> None:
    await db.delete(doc)
    await db.commit()
