import json

import httpx
import respx

from app.ai.providers.base import ChatRequest
from app.ai.providers.ollama import OllamaProvider

NDJSON = "\n".join(  # noqa: FLY002 - JSON payload, not f-string material
    [
        '{"message":{"content":"你"}}',
        '{"message":{"content":"好"}}',
        '{"message":{"thinking":"先想一下"}}',
        (
            '{"message":{"content":""},"done":true,"prompt_eval_count":10,'
            '"eval_count":2,"total_duration":123456789}'
        ),
    ]
)


@respx.mock
async def test_chat_stream_parses_events():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, content=NDJSON.encode("utf-8"))
    )
    provider = OllamaProvider("http://localhost:11434")
    events = [
        e
        async for e in provider.chat_stream(
            ChatRequest(model="m", messages=[{"role": "user", "content": "hi"}])
        )
    ]
    assert [e.type for e in events] == ["token", "token", "thinking", "usage"]
    assert events[0].payload["delta"] == "你"
    assert events[-1].payload["prompt_tokens"] == 10
    await provider.aclose()


@respx.mock
async def test_ensure_loaded_uses_keep_alive():
    route = respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"done": True})
    )
    provider = OllamaProvider("http://localhost:11434")
    await provider.ensure_loaded("qwen2.5:7b")
    body = json.loads(route.calls[0].request.content)
    assert body == {"model": "qwen2.5:7b", "prompt": "", "keep_alive": "15m"}
    await provider.aclose()


@respx.mock
async def test_unload_uses_keep_alive_zero():
    route = respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"done": True})
    )
    provider = OllamaProvider("http://localhost:11434")
    await provider.unload("qwen2.5:7b")
    body = json.loads(route.calls[0].request.content)
    assert body["keep_alive"] == 0
    await provider.aclose()


@respx.mock
async def test_list_loaded_parses_ps():
    respx.get("http://localhost:11434/api/ps").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "qwen2.5:7b", "size_vram": 6_000_000_000,
                              "expires_at": "2026-09-11T12:00:00Z"}]},
        )
    )
    provider = OllamaProvider("http://localhost:11434")
    loaded = await provider.list_loaded()
    assert loaded[0].name == "qwen2.5:7b"
    assert loaded[0].size_vram_mb == 6000.0
    await provider.aclose()


ERROR_NDJSON = "\n".join(  # noqa: FLY002 - JSON payload, not f-string material
    [
        '{"message":{"content":"部分"}}',
        '{"error":"model requires more system memory"}',
    ]
)


@respx.mock
async def test_chat_stream_raises_on_inline_error_chunk():
    import pytest

    from app.ai.providers.base import ProviderStreamError

    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, content=ERROR_NDJSON.encode("utf-8"))
    )
    provider = OllamaProvider("http://localhost:11434")
    with pytest.raises(ProviderStreamError):
        async for _ in provider.chat_stream(
            ChatRequest(model="m", messages=[{"role": "user", "content": "hi"}])
        ):
            pass
    await provider.aclose()
