import inspect
from collections.abc import AsyncIterator, Callable
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

    ``embed_vectors`` 可覆盖 embed 返回值；实例属性 ``embed_fn``（设置后优先）
    接收 texts 并返回/等待向量列表。
    """

    def __init__(
        self,
        script: list[tuple[str, dict]] | list[list[tuple[str, dict]]] | None = None,
        raise_after: int | None = None,
        embed_vectors: list[list[float]] | None = None,
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
        self.embed_vectors = embed_vectors
        self.embed_fn: Callable | None = None
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
        if self.embed_fn is not None:
            result = self.embed_fn(texts)
            if inspect.isawaitable(result):
                result = await result
            return result
        if self.embed_vectors is not None:
            return self.embed_vectors
        # 默认确定性 1024 维向量（首位随文本哈希变化，其余为 0）
        return [[float(hash(t) % 100) / 100] + [0.0] * 1023 for t in texts]

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
