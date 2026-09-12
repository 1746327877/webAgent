import asyncio
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.knowledge import DocumentOut, KBCreateIn, KBOut, KBUpdateIn
from app.services import kb_service

router = APIRouter(prefix="/kbs", tags=["kbs"])

ALLOWED = {"pdf", "md", "txt", "docx"}
MAX_BYTES = 20 * 1024 * 1024


def enqueue_ingest(document_id) -> None:
    """生产环境入 ARQ；测试 monkeypatch。"""
    from arq import create_pool
    from arq.connections import RedisSettings

    async def _run():
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await pool.enqueue_job("ingest_job", str(document_id))

    asyncio.get_running_loop().create_task(_run())


def _remove_stored_file(stored_name: str | None) -> None:
    if not stored_name:
        return
    try:
        (Path(settings.upload_dir) / stored_name).unlink(missing_ok=True)
    except OSError:
        pass


@router.post("", response_model=KBOut, status_code=201)
async def create_kb(
    body: KBCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await kb_service.create_kb(db, user, body)


@router.get("", response_model=list[KBOut])
async def list_kbs(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await kb_service.list_kbs(db, user)


@router.get("/{kid}", response_model=KBOut)
async def get_kb(
    kid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await kb_service.get_owned_kb(db, user, kid)


@router.patch("/{kid}", response_model=KBOut)
async def patch_kb(
    kid: uuid.UUID,
    body: KBUpdateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    return await kb_service.update_kb(db, kb, body.model_dump(exclude_unset=True))


@router.delete("/{kid}", status_code=204)
async def delete_kb(
    kid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    docs = await kb_service.list_documents(db, kb)
    stored_names = [(d.meta or {}).get("stored_name") for d in docs]
    await kb_service.delete_kb(db, kb)
    for stored in stored_names:
        _remove_stored_file(stored)


@router.post("/{kid}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    kid: uuid.UUID,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        raise HTTPException(status_code=415, detail="不支持的文件类型")
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")
    stored_name = f"{uuid.uuid4()}.{ext}"
    path = Path(settings.upload_dir) / stored_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    doc = await kb_service.create_document(
        db,
        kb,
        name=file.filename or stored_name,
        ext=ext,
        size=len(content),
        user=user,
        stored_name=stored_name,
    )
    enqueue_ingest(doc.id)
    return doc


@router.get("/{kid}/documents", response_model=list[DocumentOut])
async def list_documents(
    kid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    return await kb_service.list_documents(db, kb)


@router.post("/{kid}/documents/{doc_id}/retry", response_model=DocumentOut)
async def retry_document(
    kid: uuid.UUID,
    doc_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    doc = await kb_service.get_owned_document(db, user, doc_id)
    if doc.kb_id != kb.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    doc = await kb_service.reset_document(db, doc)
    enqueue_ingest(doc.id)
    return doc


@router.delete("/{kid}/documents/{doc_id}", status_code=204)
async def delete_document(
    kid: uuid.UUID,
    doc_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    doc = await kb_service.get_owned_document(db, user, doc_id)
    if doc.kb_id != kb.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    stored_name = (doc.meta or {}).get("stored_name")
    await kb_service.delete_document(db, doc)
    _remove_stored_file(stored_name)
