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
