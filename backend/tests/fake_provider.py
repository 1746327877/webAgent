from collections.abc import AsyncIterator
from dataclasses import replace

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
    """多轮脚本 Provider：每轮一份事件脚本，耗尽后重复最后一轮。

    构造参数可为单脚本 ``list[tuple[str, dict]]``（兼容旧用法）或多轮脚本
    ``list[list[tuple[str, dict]]]``。``raise_after`` 作用于每轮内的事件序号。
    每次 ``chat_stream`` 记录请求到 ``requests`` 与 ``last_request``。
    """

    def __init__(
        self,
        script: list[tuple[str, dict]] | list[list[tuple[str, dict]]] | None = None,
        raise_after: int | None = None,
    ):
        if not script:
            rounds: list[list[tuple[str, dict]]] = [[("token", {"delta": "你好"})]]
        elif isinstance(script[0], tuple):
            rounds = [list(script)]  # type: ignore[arg-type]
        else:
            rounds = [list(round_script) for round_script in script]  # type: ignore[arg-type]
        self.rounds = rounds
        self.script = rounds[0]
        self.raise_after = raise_after
        self.requests: list[ChatRequest] = []
        self.last_request: ChatRequest | None = None
        self._round_index = 0

    def _next_script(self) -> list[tuple[str, dict]]:
        index = min(self._round_index, len(self.rounds) - 1)
        self._round_index += 1
        return self.rounds[index]

    def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatEvent]:
        # 浅拷贝快照：runtime 会持续向 req.messages 追加回填消息，记录引用会看到最终形态
        snapshot = replace(req, messages=list(req.messages))
        self.requests.append(snapshot)
        self.last_request = snapshot
        script = self._next_script()

        async def gen():
            for i, (etype, payload) in enumerate(script):
                if self.raise_after is not None and i >= self.raise_after:
                    raise ProviderStreamError("boom")
                yield ChatEvent(etype, payload)
            # raise_after=N：产出 N 个事件后抛错；脚本恰好只有 N 个事件时循环会自然结束，
            # 需要在循环后补抛，否则单 token 脚本（raise_after=1）永远模拟不出流内错误。
            if self.raise_after is not None and len(script) <= self.raise_after:
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
