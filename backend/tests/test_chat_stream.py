from app.ai.deps import get_provider
from app.ai.providers.base import ChatEvent, ModelProvider
from app.main import app


class FakeProvider(ModelProvider):
    def chat_stream(self, req):
        async def gen():
            yield ChatEvent("token", {"delta": "你好"})
            yield ChatEvent("usage", {"prompt_tokens": 1, "completion_tokens": 1})

        return gen()

    async def embed(self, texts, model):
        return [[0.0]]

    async def list_available(self):
        return []

    async def list_loaded(self):
        return []

    async def ensure_loaded(self, model):
        return 0.0

    async def unload(self, model):
        return None

    async def health(self):
        return None


async def test_chat_stream_sse(client, auth_headers):
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    r = await client.post(
        "/api/v1/chat/stream",
        json={"model": "fake", "messages": [{"role": "user", "content": "hi"}]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "event: token" in body
    assert '"delta": "你好"' in body
    assert "event: done" in body


async def test_chat_stream_requires_auth(client):
    r = await client.post(
        "/api/v1/chat/stream",
        json={"model": "fake", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401
