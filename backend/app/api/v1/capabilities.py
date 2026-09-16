import time
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends

from app.ai.skills import list_skills
from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("/skills")
async def get_skills(user: Annotated[User, Depends(get_current_user)]):
    """系统内置 Skill 清单（静态代码清单，只读）。"""
    return list_skills()


@router.get("/parser")
async def get_parser_status(user: Annotated[User, Depends(get_current_user)]):
    """MinerU 解析服务状态：当前后端、连通性与版本（未配置时回退内置解析）。"""
    base = (settings.mineru_api_url or "").strip().rstrip("/")
    status: dict = {
        "enabled": bool(base),
        "api_url": base or None,
        "backend": settings.mineru_backend,
        "healthy": False,
        "version": None,
        "latency_ms": None,
        "error": None,
    }
    if not base:
        status["error"] = "未配置 MINERU_API_URL，回退内置解析（pymupdf/docx，无 OCR）"
        return status

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base}/health")
        status["latency_ms"] = round((time.monotonic() - started) * 1000)
        if response.status_code == 200:
            status["healthy"] = True
            status["version"] = response.json().get("version")
        else:
            status["error"] = f"MinerU 返回 HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001 —— 探测失败是预期路径，前端展示即可
        status["latency_ms"] = round((time.monotonic() - started) * 1000)
        status["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return status


@router.get("/web-search")
async def get_web_search_status(user: Annotated[User, Depends(get_current_user)]):
    """联网搜索 MCP 状态：未配置或连接失败时前端禁用输入框按钮。"""
    from app.ai import web_search

    url = (settings.web_search_mcp_url or "").strip()
    status: dict = {
        "enabled": bool(url),
        "url": url or None,
        "healthy": False,
        "tools": [],
        "latency_ms": None,
        "error": None,
    }
    if not url:
        status["error"] = "未配置 WEB_SEARCH_MCP_URL，联网搜索不可用"
        return status

    started = time.monotonic()
    # binding() 内部带 TTL 缓存，轮询不会反复建连
    binding = await web_search.binding()
    status["latency_ms"] = round((time.monotonic() - started) * 1000)
    if binding is None:
        status["error"] = "联网搜索 MCP 连接失败，请确认 web-search 服务已启动"
        return status
    status["healthy"] = True
    status["tools"] = [str(tool.get("name")) for tool in binding.tools]
    return status
