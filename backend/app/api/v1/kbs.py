import logging
import uuid
from pathlib import Path
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db, get_session_factory
from app.models import Document
from app.models.user import User
from app.schemas.knowledge import DocumentOut, KBCreateIn, KBOut, KBUpdateIn
from app.services import kb_service

router = APIRouter(prefix="/kbs", tags=["kbs"])
logger = logging.getLogger(__name__)

ALLOWED = {"pdf", "md", "markdown", "txt", "docx"}
MAX_BYTES = 20 * 1024 * 1024


async def enqueue_ingest(
    document_id,
    *,
    dedupe: bool = True,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """把文档解析入 ARQ 队列；入队失败时文档置 failed 并抛 503。

    dedupe=True 用固定 job_id 防止并发重复入队；重试必须 dedupe=False——
    arq 在 result key 保留期（默认 3600s）内会丢弃同名 job_id 的入队。
    session_factory 由端点注入（测试可替换为测试库），缺省时用生产 SessionLocal。
    """
    try:
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            if dedupe:
                await pool.enqueue_job(
                    "ingest_job", str(document_id), _job_id=f"ingest:{document_id}"
                )
            else:
                await pool.enqueue_job("ingest_job", str(document_id))
        finally:
            await pool.aclose()
    except Exception as exc:
        logger.exception("文档 %s 入队失败", document_id)
        if session_factory is None:
            from app.core.db import SessionLocal

            session_factory = SessionLocal
        try:
            async with session_factory() as db:
                doc = await db.get(Document, uuid.UUID(str(document_id)))
                if doc is not None:
                    doc.status = "failed"
                    doc.error = "任务排队失败，请重试"
                    await db.commit()
        except Exception:
            logger.exception("文档 %s 置 failed 失败", document_id)
        raise HTTPException(status_code=503, detail="任务排队失败，请稍后重试") from exc


def _remove_stored_file(stored_name: str | None) -> None:
    if not stored_name:
        return
    # 落盘名恒为 "{uuid}.{ext}"；含路径分隔符的脏数据一律拒绝，避免越界删除
    if "/" in stored_name or "\\" in stored_name:
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
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        raise HTTPException(status_code=415, detail="仅支持 pdf/md/markdown/txt/docx 文件")
    # multipart 解析已完成，先用 size 预检，避免把超大文件整读进内存
    if file.size is not None and file.size > MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")
    stored_name = f"{uuid.uuid4()}.{ext}"
    path = Path(settings.upload_dir) / stored_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    try:
        doc = await kb_service.create_document(
            db,
            kb,
            name=(file.filename or stored_name)[:255],
            ext=ext,
            size=len(content),
            user=user,
            stored_name=stored_name,
        )
    except Exception:
        _remove_stored_file(stored_name)  # 建行失败时清理孤儿文件
        raise
    await enqueue_ingest(doc.id, session_factory=factory)
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
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
):
    kb = await kb_service.get_owned_kb(db, user, kid)
    doc = await kb_service.get_owned_document(db, user, doc_id)
    if doc.kb_id != kb.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    doc = await kb_service.reset_document(db, doc)
    await enqueue_ingest(doc.id, dedupe=False, session_factory=factory)
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
