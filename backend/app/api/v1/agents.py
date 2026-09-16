import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.upload_rules import IMAGE_EXTS, MIME_BY_EXT, has_valid_image_magic
from app.models.user import User
from app.schemas.agent import (
    AgentCreateIn,
    AgentOut,
    AgentUpdateIn,
    AgentVersionOut,
    KbsIn,
    McpToolsIn,
    PublishOut,
    RollbackIn,
    SkillsIn,
    ToolsIn,
)
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])

logger = logging.getLogger("app.agents")

# 头像：仅图片、单张 ≤ 2MB
AVATAR_MAX_BYTES = 2 * 1024 * 1024


def _avatar_file(stored: str) -> Path:
    """落盘名恒为 "{uuid}.{ext}"；含路径分隔符的脏数据一律拒绝，避免越界读取。"""
    if "/" in stored or "\\" in stored:
        raise HTTPException(status_code=404, detail="头像不存在")
    return Path(settings.upload_dir) / stored


def _remove_avatar_file(stored: str | None) -> None:
    if not stored:
        return
    try:
        _avatar_file(stored).unlink(missing_ok=True)
    except (OSError, HTTPException):
        logger.warning("头像文件删除失败 file=%s", stored)


async def _to_out(db: AsyncSession, agent) -> AgentOut:
    out = AgentOut.model_validate(agent)
    out.variables = agent_service.extract_variables(agent.system_prompt)
    out.tool_slugs = await agent_service._tool_slugs(db, agent.id)
    out.skill_slugs = await agent_service._skill_slugs(db, agent.id)
    out.mcp_tools = await agent_service.list_mcp_tools(db, agent.id)
    out.kb_bindings = await agent_service.list_kb_bindings(db, agent.id)
    out.has_avatar = bool(agent.avatar_path)
    return out


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _to_out(db, await agent_service.create_agent(db, user, body))


@router.get("", response_model=list[AgentOut])
async def list_agents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return [await _to_out(db, a) for a in await agent_service.list_agents(db, user)]


@router.get("/{aid}", response_model=AgentOut)
async def get_agent(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _to_out(db, await agent_service.get_owned_agent(db, user, aid))


@router.patch("/{aid}", response_model=AgentOut)
async def patch_agent(
    aid: uuid.UUID,
    body: AgentUpdateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    fields = body.model_dump(exclude_unset=True, by_alias=True)
    return await _to_out(db, await agent_service.update_agent(db, agent, fields))


@router.put("/{aid}/tools")
async def set_tools(
    aid: uuid.UUID,
    body: ToolsIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    bound = await agent_service.set_tools(db, agent, body.slugs)
    return {"slugs": bound}


@router.post("/{aid}/avatar", response_model=AgentOut)
async def upload_avatar(
    aid: uuid.UUID,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """上传/替换智能体头像（图片 ≤ 2MB，替换时删除旧文件）。"""
    agent = await agent_service.get_owned_agent(db, user, aid)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=415, detail="头像仅支持 png/jpg/jpeg/webp 图片")
    content = await file.read()
    if len(content) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="头像超过 2MB")
    if not has_valid_image_magic(content, ext):
        raise HTTPException(status_code=415, detail="文件内容与图片类型不符")

    stored = f"{uuid.uuid4()}.{ext}"
    path = _avatar_file(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    previous = agent.avatar_path
    agent.avatar_path = stored
    await db.commit()
    await db.refresh(agent)
    if previous and previous != stored:
        _remove_avatar_file(previous)
    logger.info("上传头像 agent=%s file=%s", agent.id, stored)
    return await _to_out(db, agent)


@router.delete("/{aid}/avatar", status_code=204)
async def delete_avatar(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """移除头像（前端随即回退到"名字首字"）。"""
    agent = await agent_service.get_owned_agent(db, user, aid)
    previous = agent.avatar_path
    if previous:
        agent.avatar_path = None
        await db.commit()
        _remove_avatar_file(previous)
        logger.info("移除头像 agent=%s", agent.id)
    return Response(status_code=204)


@router.get("/{aid}/avatar")
async def get_avatar(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """返回头像图片（鉴权 + 归属校验；<img> 不能带 Bearer，前端以 blob 方式取）。"""
    agent = await agent_service.get_owned_agent(db, user, aid)
    if not agent.avatar_path:
        raise HTTPException(status_code=404, detail="头像不存在")
    path = _avatar_file(agent.avatar_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="头像文件不存在")
    ext = agent.avatar_path.rsplit(".", 1)[-1].lower()
    return FileResponse(path, media_type=MIME_BY_EXT.get(ext, "application/octet-stream"))


@router.put("/{aid}/skills")
async def set_skills(
    aid: uuid.UUID,
    body: SkillsIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    bound = await agent_service.set_skills(db, agent, body.slugs)
    return {"slugs": bound}


@router.put("/{aid}/mcp-tools")
async def set_mcp_tools(
    aid: uuid.UUID,
    body: McpToolsIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    bound = await agent_service.set_mcp_tools(db, agent, user, body.tools)
    return {"tools": bound}


@router.put("/{aid}/kbs")
async def set_kbs(
    aid: uuid.UUID,
    body: KbsIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    await agent_service.set_kbs(db, agent, user, body.bindings)
    return {"bindings": await agent_service.list_kb_bindings(db, agent.id)}


@router.delete("/{aid}", status_code=204)
async def delete_agent(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    await agent_service.delete_agent(db, agent)


@router.post("/{aid}/publish", response_model=PublishOut)
async def publish_agent(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    row = await agent_service.publish_agent(db, agent, user)
    return PublishOut(version=row.version, status=agent.status)


@router.get("/{aid}/versions", response_model=list[AgentVersionOut])
async def list_versions(
    aid: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    return await agent_service.list_versions(db, agent)


@router.post("/{aid}/rollback", response_model=AgentOut)
async def rollback_agent(
    aid: uuid.UUID,
    body: RollbackIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    agent = await agent_service.get_owned_agent(db, user, aid)
    return await _to_out(db, await agent_service.rollback_agent(db, agent, body.version))
