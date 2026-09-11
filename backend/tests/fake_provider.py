from collections.abc import AsyncIterator

from app.ai.providers.base import (
    ChatEvent,
    ChatRequest,
    LoadedModel,
    ModelInfo,
    ModelProvider,
    ProviderHealth,
    ProviderStreamError,
)


class FakeProvider(ModelProvider):
    def __init__(self, script: list[tuple[str, dict]] | None = None, raise_after: int | None = None):
        self.script = script or [("token", {"delta": "你好"})]
        self.raise_after = raise_after

    def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatEvent]:
        async def gen():
            for i, (etype, payload) in enumerate(self.script):
                if self.raise_after is not None and i >= self.raise_after:
                    raise ProviderStreamError("boom")
                yield ChatEvent(etype, payload)
            # raise_after=N：产出 N 个事件后抛错；脚本恰好只有 N 个事件时循环会自然结束，
            # 需要在循环后补抛，否则单 token 脚本（raise_after=1）永远模拟不出流内错误。
            if self.raise_after is not None and len(self.script) <= self.raise_after:
                raise ProviderStreamError("boom")

        return gen()

    async def embed(self, texts, model):
        return [[0.0] for _ in texts]

    async def list_available(self) -> list[ModelInfo]:
        return []

    async def list_loaded(self) -> list[LoadedModel]:
        return []

    async def ensure_loaded(self, model: str) -> float:
        return 0.0

    async def unload(self, model: str) -> None:
        return None

    async def health(self) -> ProviderHealth:
        return ProviderHealth(ok=True, base_url="fake")
