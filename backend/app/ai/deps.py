from fastapi import Request

from app.ai.providers.base import ModelProvider


def get_provider(request: Request) -> ModelProvider:
    return request.app.state.provider
