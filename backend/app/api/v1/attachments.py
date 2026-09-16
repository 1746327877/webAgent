import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.upload_rules import IMAGE_EXTS, MIME_BY_EXT, has_valid_image_magic
from app.models import Attachment
from app.models.session import Session
from app.models.user import User
from app.services import session_service

router = APIRouter(tags=["attachments"])

# 文档走文本提取注入，与知识库上传的类型保持一致（额外放宽 markdown 后缀）
DOCUMENT_EXTS = {"pdf", "md", "markdown", "txt", "docx"}
ALLOWED_EXTS = IMAGE_EXTS | DOCUMENT_EXTS
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


class AttachmentOut(BaseModel):
    id: uuid.UUID
    original_name: str
    kind: str
    size_bytes: int


def stored_path(stored_name: str) -> Path:
    return Path(settings.upload_dir) / stored_name


def _too_large_detail(is_image: bool) -> str:
    return "图片超过 5MB" if is_image else "文档超过 20MB"


@router.post("/sessions/{sid}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    sid: uuid.UUID,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await session_service.get_owned_session(db, user, sid)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail="仅支持 png/jpg/jpeg/webp 图片与 pdf/md/markdown/txt/docx 文档",
        )
    is_image = ext in IMAGE_EXTS
    max_bytes = MAX_IMAGE_BYTES if is_image else MAX_DOCUMENT_BYTES
    # multipart 解析已完成，先用 size 预检；随后整读时再按实际长度二次校验
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(status_code=413, detail=_too_large_detail(is_image))
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=_too_large_detail(is_image))
    if is_image and not has_valid_image_magic(content, ext):
        raise HTTPException(status_code=415, detail="文件内容与图片类型不符")

    stored_name = f"{uuid.uuid4()}.{ext}"
    path = stored_path(stored_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    try:
        attachment = Attachment(
            session_id=session.id,
            message_id=None,
            file_path=stored_name,
            original_name=(file.filename or stored_name)[:255],
            mime_type=MIME_BY_EXT[ext],
            size_bytes=len(content),
            kind="image" if is_image else "document",
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)
    except Exception:
        path.unlink(missing_ok=True)  # 建行失败时清理孤儿文件
        raise
    return attachment


@router.get("/attachments/{aid}")
async def download_attachment(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    attachment = await db.scalar(
        select(Attachment)
        .join(Session, Session.id == Attachment.session_id)
        .where(Attachment.id == aid, Session.user_id == user.id)
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    # 落盘名恒为 "{uuid}.{ext}"；含路径分隔符的脏数据一律拒绝，避免越界读取
    if "/" in attachment.file_path or "\\" in attachment.file_path:
        raise HTTPException(status_code=404, detail="附件不存在")
    path = stored_path(attachment.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.original_name)
