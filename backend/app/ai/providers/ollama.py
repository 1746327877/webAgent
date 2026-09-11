import json
import time
from collections.abc import AsyncIterator

import httpx

from app.ai.providers.base import (
    ChatEvent,
    ChatRequest,
    LoadedModel,
    ModelInfo,
    ModelProvider,
    ProviderHealth,
    ProviderStreamError,
)


def _strip_think_tags(content: str) -> str:
    return content.replace("<think>", "").replace("</think>", "").strip()


class OllamaProvider(ModelProvider):
    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat_stream(self, req: ChatRequest) -> AsyncIterator[ChatEvent]:
        payload: dict = {
            "model": req.model,
            "messages": req.messages,
            "stream": True,
            "options": {
                "temperature": req.temperature,
                "top_p": req.top_p,
                "num_predict": req.max_tokens,
                "num_ctx": req.num_ctx,
            },
            "keep_alive": req.keep_alive,
        }
        if req.tools:
            payload["tools"] = req.tools

        async with self._client.stream("POST", "/api/chat", json=payload, timeout=None) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if err := chunk.get("error"):
                    raise ProviderStreamError(str(err))
                msg = chunk.get("message", {})
                if thinking := msg.get("thinking"):
                    yield ChatEvent("thinking", {"delta": thinking})
                content = msg.get("content") or ""
                if content:
                    if "<think>" in content:  # 旧版 Ollama 内联标签兜底
                        if stripped := _strip_think_tags(content):
                            yield ChatEvent("thinking", {"delta": stripped})
                    else:
                        yield ChatEvent("token", {"delta": content})
                for call in msg.get("tool_calls") or []:
                    fn = call.get("function", {})
                    yield ChatEvent(
                        "tool_call",
                        {"id": call.get("id"), "name": fn.get("name"),
                         "args": fn.get("arguments")},
                    )
                if chunk.get("done"):
                    yield ChatEvent(
                        "usage",
                        {
                            "prompt_tokens": chunk.get("prompt_eval_count"),
                            "completion_tokens": chunk.get("eval_count"),
                            "total_ms": round((chunk.get("total_duration") or 0) / 1e6, 1),
                            "first_token_ms": None,
                        },
                    )

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        r = await self._client.post("/api/embed", json={"model": model, "input": texts})
        r.raise_for_status()
        return r.json()["embeddings"]

    async def list_available(self) -> list[ModelInfo]:
        r = await self._client.get("/api/tags")
        r.raise_for_status()
        return [
            ModelInfo(name=m["name"], size_mb=round(m.get("size", 0) / 1e6, 1))
            for m in r.json().get("models", [])
        ]

    async def list_loaded(self) -> list[LoadedModel]:
        r = await self._client.get("/api/ps")
        r.raise_for_status()
        return [
            LoadedModel(
                name=m["name"],
                size_vram_mb=round(m.get("size_vram", 0) / 1e6, 1),
                expires_at=m.get("expires_at"),
            )
            for m in r.json().get("models", [])
        ]

    async def ensure_loaded(self, model: str) -> float:
        t0 = time.monotonic()
        r = await self._client.post(
            "/api/generate",
            json={"model": model, "prompt": "", "keep_alive": "15m"},
            timeout=300.0,
        )
        r.raise_for_status()
        return round((time.monotonic() - t0) * 1000, 1)

    async def unload(self, model: str) -> None:
        r = await self._client.post(
            "/api/generate", json={"model": model, "keep_alive": 0}, timeout=60.0
        )
        r.raise_for_status()

    async def health(self) -> ProviderHealth:
        try:
            r = await self._client.get("/api/version", timeout=5.0)
            return ProviderHealth(ok=r.status_code == 200, base_url=self.base_url)
        except httpx.HTTPError:
            return ProviderHealth(ok=False, base_url=self.base_url)
