from fastapi import Request

from app.ai.model_manager import ModelManager
from app.ai.providers.base import ModelProvider


def get_provider(request: Request) -> ModelProvider:
    return request.app.state.provider


def get_model_manager(request: Request) -> ModelManager | None:
    return getattr(request.app.state, "model_manager", None)
