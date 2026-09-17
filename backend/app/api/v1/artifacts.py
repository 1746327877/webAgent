"""会话产物接口：导出 Markdown / 列表 / 下载（见 `docs/设计/24-会话产物.md`）。"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.convert import DOCX_MIME
from app.ai.convert.readers import docx_to_html
from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models import Artifact, User
from app.services import artifact_service, session_service

router = APIRouter(tags=["artifacts"])


class ArtifactOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    source: str
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime


def _view(artifact: Artifact) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        session_id=artifact.session_id,
        source=artifact.source,
        filename=artifact.filename,
        mime_type=artifact.mime_type,
        size_bytes=artifact.size_bytes,
        created_at=artifact.created_at,
    )


@router.post(
    "/sessions/{sid}/artifacts/markdown", response_model=ArtifactOut, status_code=201
)
async def export_markdown(
    sid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """把当前会话导出为 Markdown 产物（标题 + 逐条消息 + 引用来源）。"""
    session = await session_service.get_owned_session(db, user, sid)
    messages = await artifact_service.load_messages(db, session)
    try:
        artifact = await artifact_service.create_markdown_artifact(db, session, messages)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return _view(artifact)


@router.get("/sessions/{sid}/artifacts", response_model=list[ArtifactOut])
async def list_session_artifacts(
    sid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """会话产物列表（新的在前）。"""
    session = await session_service.get_owned_session(db, user, sid)
    return [_view(item) for item in await artifact_service.list_artifacts(db, session)]


@router.get("/artifacts/{aid}")
async def download_artifact(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """下载产物原文（前端预览 Markdown 也走这里）。"""
    artifact = await artifact_service.get_owned_artifact(db, user, aid)
    if artifact is None:
        raise HTTPException(status_code=404, detail="产物不存在")
    # 落盘名恒为 "{uuid}.{ext}"；含路径分隔符的脏数据一律拒绝，避免越界读取
    if "/" in artifact.file_path or "\\" in artifact.file_path:
        raise HTTPException(status_code=404, detail="产物不存在")
    path = Path(settings.upload_dir) / artifact.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="产物文件不存在")
    return FileResponse(path, media_type=artifact.mime_type, filename=artifact.filename)


@router.get("/artifacts/{aid}/preview", response_class=HTMLResponse)
async def preview_artifact(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """docx 产物的 HTML 预览（浏览器不能原生预览 docx）；其它类型无需服务端预览。"""
    artifact = await artifact_service.get_owned_artifact(db, user, aid)
    if artifact is None:
        raise HTTPException(status_code=404, detail="产物不存在")
    if artifact.mime_type != DOCX_MIME:
        raise HTTPException(status_code=415, detail="该类型无需服务端预览")
    # 落盘名恒为 "{uuid}.{ext}"；含路径分隔符的脏数据一律拒绝，避免越界读取
    if "/" in artifact.file_path or "\\" in artifact.file_path:
        raise HTTPException(status_code=404, detail="产物不存在")
    path = Path(settings.upload_dir) / artifact.file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="产物文件不存在")
    try:
        html = docx_to_html(path)
    except Exception as exc:  # 预览失败返回可读错误，不阻断下载
        raise HTTPException(status_code=500, detail=f"预览生成失败：{str(exc)[:200]}") from exc
    return HTMLResponse(html)
