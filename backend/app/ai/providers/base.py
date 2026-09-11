from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


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


@dataclass
class ChatEvent:
    type: str  # token / thinking / tool_call / usage
    payload: dict = field(default_factory=dict)


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
