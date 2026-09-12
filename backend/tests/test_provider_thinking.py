import json

import httpx
import respx

from app.ai.providers.base import ChatRequest
from app.ai.providers.ollama import OllamaProvider

URL = "http://localhost:11434/api/chat"


def _ndjson(*chunks: dict) -> str:
    return "\n".join(json.dumps(chunk) for chunk in chunks)


async def _events(payload: str):
    respx.post(URL).mock(return_value=httpx.Response(200, content=payload.encode("utf-8")))
    provider = OllamaProvider("http://localhost:11434")
    events = [
        event
        async for event in provider.chat_stream(
            ChatRequest(model="m", messages=[{"role": "user", "content": "hi"}])
        )
    ]
    await provider.aclose()
    return events


@respx.mock
async def test_inline_think_tags_split_across_chunks():
    events = await _events(
        _ndjson(
            {"message": {"content": "<thi"}},
            {"message": {"content": "nk>先推理"}},
            {"message": {"content": "</thi"}},
            {"message": {"content": "nk>答案"}},
            {"message": {"content": ""}, "done": True},
        )
    )
    assert [event.type for event in events] == ["thinking", "token", "usage"]
    assert events[0].payload["delta"] == "先推理"
    assert events[1].payload["delta"] == "答案"


@respx.mock
async def test_single_chunk_with_tags_and_stray_close_tag():
    events = await _events(
        _ndjson(
            {"message": {"content": "<think>推理</think>答案</think>继续"}},
            {"message": {"content": ""}, "done": True},
        )
    )
    assert [(e.type, e.payload.get("delta")) for e in events if e.type != "usage"] == [
        ("thinking", "推理"),
        ("token", "答案"),
        ("token", "继续"),
    ]


@respx.mock
async def test_unclosed_thinking_flushed_before_usage():
    events = await _events(
        _ndjson(
            {"message": {"content": "<think>还没想完"}},
            {"message": {"content": ""}, "done": True},
        )
    )
    assert events[0].type == "thinking" and events[0].payload["delta"] == "还没想完"
    assert events[-1].type == "usage"


@respx.mock
async def test_thinking_field_still_wins_over_content():
    events = await _events(
        _ndjson(
            {"message": {"thinking": "字段思考"}},
            {"message": {"content": "正文"}},
            {"message": {"content": ""}, "done": True},
        )
    )
    assert [(e.type, e.payload.get("delta")) for e in events if e.type != "usage"] == [
        ("thinking", "字段思考"),
        ("token", "正文"),
    ]
