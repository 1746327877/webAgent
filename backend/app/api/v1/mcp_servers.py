import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.models import McpServer
from app.models.user import User
from app.services import mcp_service

router = APIRouter(prefix="/mcp-servers", tags=["mcp"])


class McpConfigBase(BaseModel):
    transport: Literal["http", "stdio"]
    url: str | None = Field(default=None, max_length=512)
    headers: dict[str, str] = Field(default_factory=dict)
    command: str | None = Field(default=None, max_length=256)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def _check_transport_fields(self):
        if self.transport == "http":
            url = (self.url or "").strip()
            if not url:
                raise ValueError("http 需要填写 url")
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError("url 需以 http:// 或 https:// 开头")
            self.url = url
        else:
            command = (self.command or "").strip()
            if not command:
                raise ValueError("stdio 需要填写 command")
            self.command = command
        return self


class McpCreate(McpConfigBase):
    name: str = Field(min_length=1, max_length=64)


class McpUpdate(McpCreate):
    """编辑按整份配置替换（前端表单总是全量提交）。"""


class McpProbe(McpConfigBase):
    name: str | None = Field(default=None, max_length=64)


def _view(server: McpServer) -> dict:
    return {
        "id": str(server.id),
        "name": server.name,
        "transport": server.transport,
        "url": server.url,
        "headers": server.headers or {},
        "command": server.command,
        "args": server.args or [],
        "env": server.env or {},
        "enabled": server.enabled,
        "status": server.status,
        "last_error": server.last_error,
        "tools": server.tools or [],
        "last_checked_at": server.last_checked_at.isoformat() if server.last_checked_at else None,
        "created_at": server.created_at.isoformat() if server.created_at else None,
        "updated_at": server.updated_at.isoformat() if server.updated_at else None,
    }


def _config(body: McpConfigBase, name: str | None = None) -> dict:
    return {
        "name": name,
        "transport": body.transport,
        "url": body.url,
        "headers": body.headers,
        "command": body.command,
        "args": body.args,
        "env": body.env,
    }


def _probe_result_payload(result: mcp_service.ProbeResult) -> dict:
    return {
        "ok": result.ok,
        "tools": result.tools,
        "error": result.error,
        "latency_ms": result.latency_ms,
    }


async def _get_owned(db: AsyncSession, user: User, server_id: uuid.UUID) -> McpServer:
    server = await db.scalar(
        select(McpServer).where(McpServer.id == server_id, McpServer.user_id == user.id)
    )
    if server is None:
        raise HTTPException(status_code=404, detail="MCP 不存在")
    return server


async def _ensure_name_free(
    db: AsyncSession, user: User, name: str, *, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(McpServer.id).where(McpServer.user_id == user.id, McpServer.name == name)
    if exclude is not None:
        stmt = stmt.where(McpServer.id != exclude)
    if await db.scalar(stmt.limit(1)) is not None:
        raise HTTPException(status_code=409, detail="同名 MCP 已存在")


@router.get("")
async def list_mcp_servers(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rows = (
        await db.scalars(
            select(McpServer)
            .where(McpServer.user_id == user.id)
            .order_by(McpServer.created_at.desc())
        )
    ).all()
    return [_view(row) for row in rows]


@router.post("", status_code=201)
async def create_mcp_server(
    body: McpCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _ensure_name_free(db, user, body.name)
    server = McpServer(
        user_id=user.id,
        name=body.name,
        transport=body.transport,
        url=body.url,
        headers=body.headers,
        command=body.command,
        args=body.args,
        env=body.env,
        enabled=body.enabled,
    )
    db.add(server)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="同名 MCP 已存在") from None
    await db.refresh(server)
    return _view(server)


@router.patch("/{server_id}")
async def update_mcp_server(
    server_id: uuid.UUID,
    body: McpUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    server = await _get_owned(db, user, server_id)
    await _ensure_name_free(db, user, body.name, exclude=server.id)
    server.name = body.name
    server.transport = body.transport
    server.url = body.url
    server.headers = body.headers
    server.command = body.command
    server.args = body.args
    server.env = body.env
    server.enabled = body.enabled
    # 配置已变，旧探测结果不再可信
    server.status = "unknown"
    server.last_error = None
    server.tools = []
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="同名 MCP 已存在") from None
    await db.refresh(server)
    return _view(server)


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    server = await _get_owned(db, user, server_id)
    await db.delete(server)
    await db.commit()
    return Response(status_code=204)


@router.post("/test")
async def test_config(
    body: McpProbe,
    user: Annotated[User, Depends(get_current_user)],
):
    """用表单里的配置探测，不落库。"""
    result = await mcp_service.probe(_config(body, body.name))
    return _probe_result_payload(result)


@router.post("/{server_id}/test")
async def test_saved_server(
    server_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    server = await _get_owned(db, user, server_id)
    result = await mcp_service.probe(mcp_service.server_config(server))
    server.status = "ok" if result.ok else "error"
    server.last_error = result.error
    server.tools = result.tools
    server.last_checked_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(server)
    return {**_probe_result_payload(result), "server": _view(server)}
