from sqlalchemy import select

from app.ai.deps import get_provider
from app.main import app
from tests.fake_provider import FakeProvider

AGENT = {
    "name": "API 智能体",
    "system_prompt": "你是 API 助手",
    "model_config": {"model": "m-api"},
    "tags": [],
    "examples": [],
}
MESSAGES = [{"role": "user", "content": "hi"}]


async def _setup(client, auth_headers):
    agent = (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()
    key = (await client.post("/api/v1/keys", json={"name": "脚本"}, headers=auth_headers)).json()
    return agent["id"], key["key"]


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_non_stream_completion_and_span(client, auth_headers, session_maker):
    agent_id, key = await _setup(client, auth_headers)
    app.dependency_overrides[get_provider] = lambda: FakeProvider(
        [
            ("token", {"delta": "你"}),
            ("token", {"delta": "好"}),
            ("usage", {"prompt_tokens": 7, "completion_tokens": 3}),
        ]
    )
    r = await client.post(
        "/v1/chat/completions",
        json={"model": f"agent:{agent_id}", "messages": MESSAGES},
        headers=_auth(key),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == f"agent:{agent_id}"
    assert data["choices"][0]["message"] == {"role": "assistant", "content": "你好"}
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"] == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}

    from app.models import Span

    async with session_maker() as db:
        span = (await db.scalars(select(Span).where(Span.type == "llm"))).first()
    assert span is not None and span.model == "m-api" and span.prompt_tokens == 7


async def test_non_stream_provider_failure_returns_shaped_502(client, auth_headers, session_maker):
    agent_id, key = await _setup(client, auth_headers)
    app.dependency_overrides[get_provider] = lambda: FakeProvider(raise_after=0)
    r = await client.post(
        "/v1/chat/completions",
        json={"model": f"agent:{agent_id}", "messages": MESSAGES},
        headers=_auth(key),
    )
    assert r.status_code == 502
    error = r.json()["error"]
    assert error["type"] == "server_error"
    assert error["message"] == "生成失败"
    assert error["param"] is None and error["code"] is None

    from app.models import Span

    async with session_maker() as db:
        span = (await db.scalars(select(Span).where(Span.type == "llm"))).first()
    assert span is not None and span.status == "error" and span.error == "boom"


async def test_api_key_touch_failure_does_not_fail_completion(client, auth_headers, monkeypatch):
    """鉴权时 last_used_at 触达失败不得把已通过鉴权的补全请求打成 500。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    agent_id, key = await _setup(client, auth_headers)
    app.dependency_overrides[get_provider] = lambda: FakeProvider([("token", {"delta": "ok"})])

    real_commit = AsyncSession.commit
    state = {"failed": False}

    async def flaky_commit(self):
        if not state["failed"]:  # 第一次 commit 即鉴权触达；之后放行 span 落库
            state["failed"] = True
            raise RuntimeError("last_used_at 写入失败")
        await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)
    r = await client.post(
        "/v1/chat/completions",
        json={"model": f"agent:{agent_id}", "messages": MESSAGES},
        headers=_auth(key),
    )
    assert state["failed"] is True
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "ok"


async def test_stream_completion_emits_openai_chunks(client, auth_headers):
    agent_id, key = await _setup(client, auth_headers)
    app.dependency_overrides[get_provider] = lambda: FakeProvider(
        [("token", {"delta": "流"}), ("token", {"delta": "式"})]
    )
    r = await client.post(
        "/v1/chat/completions",
        json={"model": f"agent:{agent_id}", "messages": MESSAGES, "stream": True},
        headers=_auth(key),
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert '"content": "流"' in r.text
    assert '"content": "式"' in r.text
    assert r.text.rstrip().endswith("data: [DONE]")


async def test_model_format_error(client, auth_headers):
    _agent_id, key = await _setup(client, auth_headers)
    r = await client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": MESSAGES},
        headers=_auth(key),
    )
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "invalid_request_error"


async def test_foreign_agent_hidden_and_auth_required(client, auth_headers):
    from tests.test_sessions_api import make_user

    _agent_id, key = await _setup(client, auth_headers)
    bob = await make_user(client, "bob")
    bob_agent = (await client.post("/api/v1/agents", json=AGENT, headers=bob)).json()
    r = await client.post(
        "/v1/chat/completions",
        json={"model": f"agent:{bob_agent['id']}", "messages": MESSAGES},
        headers=_auth(key),
    )
    assert r.status_code == 404
    assert (
        await client.post(
            "/v1/chat/completions", json={"model": "agent:x", "messages": MESSAGES}
        )
    ).status_code == 401


async def test_revoked_key_rejected(client, auth_headers):
    agent_id, key = await _setup(client, auth_headers)
    keys = (await client.get("/api/v1/keys", headers=auth_headers)).json()
    await client.delete(f"/api/v1/keys/{keys[0]['id']}", headers=auth_headers)
    r = await client.post(
        "/v1/chat/completions",
        json={"model": f"agent:{agent_id}", "messages": MESSAGES},
        headers=_auth(key),
    )
    assert r.status_code == 401
