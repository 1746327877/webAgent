import io

from app.ai.deps import get_provider
from app.ai.model_manager import ModelManager
from app.main import app
from tests.fake_provider import FakeProvider


async def test_image_upload_and_vision_switch(client, auth_headers, session_maker):
    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "VL", "system_prompt": "", "model_config": {"model": "m-text"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    await client.patch(f"/api/v1/sessions/{s['id']}", json={"title": "t"}, headers=auth_headers)

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32  # 类型白名单按扩展名/魔数校验即可
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/attachments",
        files={"file": ("pic.png", io.BytesIO(png), "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    att = r.json()

    provider = FakeProvider([("token", {"delta": "图里是一只猫"})])
    app.dependency_overrides[get_provider] = lambda: provider
    mm = ModelManager(provider, session_factory=session_maker)
    app.state.model_manager = mm
    try:
        resp = await client.post(
            f"/api/v1/sessions/{s['id']}/messages",
            json={"content": "这是什么", "attachment_ids": [att["id"]]},
            headers=auth_headers,
        )
        assert '"to": "qwen2.5vl:7b"' in resp.text  # model_switching start
        assert mm.current == "qwen2.5vl:7b"
        last = provider.requests[-1].messages[-1]
        assert last.get("images") and len(last["images"][0]) > 10
        msgs = (await client.get(f"/api/v1/sessions/{s['id']}/messages", headers=auth_headers)).json()
        assert msgs[0]["attachments"][0]["id"] == att["id"]
    finally:
        del app.state.model_manager


async def test_attachment_owner_isolation(client, auth_headers):
    from tests.test_sessions_api import make_user

    agent = (
        await client.post(
            "/api/v1/agents",
            json={"name": "VL2", "system_prompt": "", "model_config": {"model": "m"}, "tags": [], "examples": []},
            headers=auth_headers,
        )
    ).json()
    s = (await client.post("/api/v1/sessions", json={"agent_id": agent["id"]}, headers=auth_headers)).json()
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/attachments",
        files={"file": ("a.png", io.BytesIO(b"\x89PNG" + b"0" * 16), "image/png")},
        headers=auth_headers,
    )
    att_id = r.json()["id"]
    other = await make_user(client, "bob")
    assert (await client.get(f"/api/v1/attachments/{att_id}", headers=other)).status_code == 404
