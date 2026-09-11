from app.ai.providers.base import ModelProvider
from app.ai.providers.ollama import OllamaProvider
from app.core.config import settings

_provider: ModelProvider | None = None


def get_provider() -> ModelProvider:
    global _provider
    if _provider is None:
        _provider = OllamaProvider(settings.ollama_base_url)
    return _provider
