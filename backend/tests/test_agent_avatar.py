from pathlib import Path

from app.core.config import settings
from tests.test_agents_api import AGENT

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 16


async def _agent(client, auth_headers) -> str:
    return (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()["id"]


async def test_upload_get_replace_delete_avatar(client, auth_headers, tmp_path, monkeypatch):
    # 头像落盘到临时目录，避免污染仓库 uploads/
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    aid = await _agent(client, auth_headers)
    created = (await client.get(f"/api/v1/agents/{aid}", headers=auth_headers)).json()
    assert created["has_avatar"] is False

    r = await client.post(
        f"/api/v1/agents/{aid}/avatar",
        files={"file": ("a.png", PNG, "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_avatar"] is True
    assert len(list(Path(tmp_path).glob("*.png"))) == 1

    img = await client.get(f"/api/v1/agents/{aid}/avatar", headers=auth_headers)
    assert img.status_code == 200
    assert img.content.startswith(b"\x89PNG")

    # 替换头像：旧文件必须删掉，不留孤儿
    r2 = await client.post(
        f"/api/v1/agents/{aid}/avatar",
        files={"file": ("b.png", PNG, "image/png")},
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert len(list(Path(tmp_path).glob("*.png"))) == 1

    d = await client.delete(f"/api/v1/agents/{aid}/avatar", headers=auth_headers)
    assert d.status_code == 204
    assert list(Path(tmp_path).glob("*.png")) == []
    assert (await client.get(f"/api/v1/agents/{aid}", headers=auth_headers)).json()["has_avatar"] is False
    assert (await client.get(f"/api/v1/agents/{aid}/avatar", headers=auth_headers)).status_code == 404


async def test_avatar_rejects_type_size_and_magic(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    aid = await _agent(client, auth_headers)

    bad_ext = await client.post(
        f"/api/v1/agents/{aid}/avatar",
        files={"file": ("a.gif", b"GIF89a", "image/gif")},
        headers=auth_headers,
    )
    assert bad_ext.status_code == 415

    too_big = await client.post(
        f"/api/v1/agents/{aid}/avatar",
        files={"file": ("big.png", b"\x89PNG" + b"x" * (2 * 1024 * 1024), "image/png")},
        headers=auth_headers,
    )
    assert too_big.status_code == 413

    bad_magic = await client.post(
        f"/api/v1/agents/{aid}/avatar",
        files={"file": ("fake.png", b"not-an-image", "image/png")},
        headers=auth_headers,
    )
    assert bad_magic.status_code == 415
    assert list(Path(tmp_path).glob("*")) == []


async def test_avatar_is_owner_only(client, auth_headers, tmp_path, monkeypatch):
    from tests.test_sessions_api import make_user

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    aid = await _agent(client, auth_headers)
    await client.post(
        f"/api/v1/agents/{aid}/avatar",
        files={"file": ("a.png", PNG, "image/png")},
        headers=auth_headers,
    )
    other = await make_user(client, "bob")
    assert (await client.get(f"/api/v1/agents/{aid}/avatar", headers=other)).status_code == 404
    assert (await client.delete(f"/api/v1/agents/{aid}/avatar", headers=other)).status_code == 404


async def test_upload_without_avatar_returns_404(client, auth_headers):
    aid = await _agent(client, auth_headers)
    assert (await client.get(f"/api/v1/agents/{aid}/avatar", headers=auth_headers)).status_code == 404
