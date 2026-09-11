from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.deps import get_provider
from app.ai.providers.base import ModelProvider
from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_models(
    user: Annotated[User, Depends(get_current_user)],
    provider: Annotated[ModelProvider, Depends(get_provider)],
):
    models = await provider.list_available()
    names = {m.name for m in models}
    items = [{"name": m.name, "size_mb": m.size_mb} for m in models]
    if settings.default_model not in names:
        items.insert(0, {"name": settings.default_model, "size_mb": None})
    return items
