import time
from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.deps import get_provider
from app.ai.providers.base import ModelProvider
from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/models", tags=["models"])

# 每个模型一次 /api/show，探测有成本；加短 TTL 缓存，避免前端频繁拉取时反复询问 Ollama
_CAP_TTL_S = 60.0
_cap_cache: dict[str, tuple[float, list[str]]] = {}


async def _capabilities(provider: ModelProvider, name: str) -> list[str]:
    now = time.monotonic()
    cached = _cap_cache.get(name)
    if cached is not None and now - cached[0] < _CAP_TTL_S:
        return cached[1]
    try:
        caps = await provider.capabilities(name)
    except Exception:  # noqa: BLE001 —— 探测失败不影响模型列表，前端按"未知"处理
        caps = []
    _cap_cache[name] = (now, caps)
    return caps


@router.get("")
async def list_models(
    user: Annotated[User, Depends(get_current_user)],
    provider: Annotated[ModelProvider, Depends(get_provider)],
):
    models = await provider.list_available()
    names = {m.name for m in models}
    items: list[dict] = []
    if settings.default_model not in names:
        items.append({"name": settings.default_model, "size_mb": None})
    items.extend({"name": m.name, "size_mb": m.size_mb} for m in models)
    # capabilities 用于前端判断"该模型能否调用工具"（如 tools/thinking）
    for item in items:
        item["capabilities"] = await _capabilities(provider, item["name"])
    return items
