from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ChatRequest:
    model: str
    messages: list[dict]
    tools: list[dict] | None = None
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048
    num_ctx: int = 8192
    keep_alive: str = "15m"


EventType = Literal["token", "thinking", "tool_call", "usage"]


@dataclass
class ChatEvent:
    type: EventType
    payload: dict = field(default_factory=dict)


class ProviderStreamError(RuntimeError):
    """Provider 在 200 流内返回错误块（如显存不足）。"""


@dataclass
class LoadedModel:
    name: str
    size_vram_mb: float
    expires_at: str | None = None


@dataclass
class ModelInfo:
    name: str
    size_mb: float


@dataclass
class ProviderHealth:
    ok: bool
    base_url: str


class ModelProvider(ABC):
    @abstractmethod
    def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatEvent]: ...

    @abstractmethod
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...

    @abstractmethod
    async def list_available(self) -> list[ModelInfo]: ...

    @abstractmethod
    async def list_loaded(self) -> list[LoadedModel]: ...

    @abstractmethod
    async def ensure_loaded(self, model: str) -> float: ...

    @abstractmethod
    async def unload(self, model: str) -> None: ...

    @abstractmethod
    async def health(self) -> ProviderHealth: ...

    async def capabilities(self, model: str) -> list[str]:
        """模型能力（如 tools/thinking）；默认未知，子类按需实现。"""
        return []
