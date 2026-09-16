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


class _ThinkTagParser:
    """跨 chunk 解析内联 <think>…</think>：旧版 Ollama 把标签混在 content 中。"""

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    @classmethod
    def _partial_len(cls, text: str) -> int:
        """text 尾部可能是某个标签前缀的最长长度（需缓存到下一 chunk）。"""
        limit = min(len(text), max(len(cls.OPEN), len(cls.CLOSE)) - 1)
        for size in range(limit, 0, -1):
            tail = text[-size:]
            if cls.OPEN.startswith(tail) or cls.CLOSE.startswith(tail):
                return size
        return 0

    def feed(self, content: str) -> list[tuple[str, str]]:
        self._buf += content
        events: list[tuple[str, str]] = []
        while self._buf:
            if self._in_think:
                end = self._buf.find(self.CLOSE)
                if end == -1:
                    keep = self._partial_len(self._buf)
                    head = self._buf[:-keep] if keep else self._buf
                    if head:
                        events.append(("thinking", head))
                    self._buf = self._buf[-keep:] if keep else ""
                    return events
                if end > 0:
                    events.append(("thinking", self._buf[:end]))
                self._buf = self._buf[end + len(self.CLOSE):]
                self._in_think = False
                continue
            start = self._buf.find(self.OPEN)
            close = self._buf.find(self.CLOSE)
            if close != -1 and (start == -1 or close < start):
                if close > 0:  # 多余闭合标签：直接丢弃，不污染正文
                    events.append(("token", self._buf[:close]))
                self._buf = self._buf[close + len(self.CLOSE):]
                continue
            if start == -1:
                keep = self._partial_len(self._buf)
                head = self._buf[:-keep] if keep else self._buf
                if head:
                    events.append(("token", head))
                self._buf = self._buf[-keep:] if keep else ""
                return events
            if start > 0:
                events.append(("token", self._buf[:start]))
            self._buf = self._buf[start + len(self.OPEN):]
            self._in_think = True
        return events

    def flush(self) -> list[tuple[str, str]]:
        if not self._buf:
            return []
        kind = "thinking" if self._in_think else "token"
        delta, self._buf = self._buf, ""
        return [(kind, delta)]


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

        parser = _ThinkTagParser()
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
                    for kind, delta in parser.feed(content):
                        if delta:
                            yield ChatEvent(kind, {"delta": delta})
                for call in msg.get("tool_calls") or []:
                    fn = call.get("function", {})
                    yield ChatEvent(
                        "tool_call",
                        {"id": call.get("id"), "name": fn.get("name"),
                         "args": fn.get("arguments")},
                    )
                if chunk.get("done"):
                    for kind, delta in parser.flush():
                        if delta:
                            yield ChatEvent(kind, {"delta": delta})
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

    async def capabilities(self, model: str) -> list[str]:
        """Ollama /api/show 的 capabilities，例如 ["completion", "tools", "thinking"]。"""
        r = await self._client.post("/api/show", json={"model": model}, timeout=15.0)
        r.raise_for_status()
        return [str(cap) for cap in (r.json().get("capabilities") or [])]
