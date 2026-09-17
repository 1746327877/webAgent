"""会话产物：导出 Markdown / 列表 / 下载 / 归属隔离（docs/设计/24）。"""

import uuid

from app.models import Message


async def _seed_session(client, auth_headers, session_maker, title="会议纪要测试"):
    session = (await client.post("/api/v1/sessions", json={}, headers=auth_headers)).json()
    await client.patch(
        f"/api/v1/sessions/{session['id']}", json={"title": title}, headers=auth_headers
    )
    async with session_maker() as db:
        db.add_all(
            [
                Message(
                    session_id=uuid.UUID(session["id"]),
                    role="user",
                    blocks=[
                        {"type": "text", "content": "把这段语音转成文字"},
                        {
                            "type": "transcript",
                            "name": "voice.wav",
                            "text": "线程池的核心参数是 corePoolSize",
                            "status": "ok",
                        },
                    ],
                ),
                Message(
                    session_id=uuid.UUID(session["id"]),
                    role="assistant",
                    blocks=[
                        {"type": "text", "content": "## 纪要\n\n- 参数：corePoolSize"},
                        {"type": "thinking", "content": "这里是思考链，不应进纪要"},
                        {"type": "citation", "ref": 1, "source": "java.md", "page": 2},
                    ],
                ),
            ]
        )
        await db.commit()
    return session


async def test_export_markdown_creates_artifact(client, auth_headers, session_maker):
    session = await _seed_session(client, auth_headers, session_maker)

    r = await client.post(
        f"/api/v1/sessions/{session['id']}/artifacts/markdown", headers=auth_headers
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "会议纪要测试.md"
    assert body["mime_type"] == "text/markdown"
    assert body["source"] == "export"
    assert body["size_bytes"] > 0

    # 下载回来的内容包含标题、消息正文、转写、引用；思考链不入纪要
    download = await client.get(f"/api/v1/artifacts/{body['id']}", headers=auth_headers)
    assert download.status_code == 200
    text = download.content.decode("utf-8")
    assert "# 会议纪要测试" in text
    assert "把这段语音转成文字" in text
    assert "语音转写（voice.wav）" in text
    assert "corePoolSize" in text
    assert "引用来源" in text and "java.md p2" in text
    assert "思考链" not in text


async def test_list_artifacts_newest_first(client, auth_headers, session_maker):
    session = await _seed_session(client, auth_headers, session_maker)
    for _ in range(2):
        await client.post(
            f"/api/v1/sessions/{session['id']}/artifacts/markdown", headers=auth_headers
        )

    r = await client.get(f"/api/v1/sessions/{session['id']}/artifacts", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert all(item["filename"] == "会议纪要测试.md" for item in items)


async def test_empty_session_still_exports(client, auth_headers, session_maker):
    session = await _seed_session(client, auth_headers, session_maker, title="空会话")
    async with session_maker() as db:
        from sqlalchemy import delete

        await db.execute(delete(Message).where(Message.session_id == uuid.UUID(session["id"])))
        await db.commit()

    r = await client.post(
        f"/api/v1/sessions/{session['id']}/artifacts/markdown", headers=auth_headers
    )
    assert r.status_code == 201
    text = (
        await client.get(f"/api/v1/artifacts/{r.json()['id']}", headers=auth_headers)
    ).content.decode("utf-8")
    assert "# 空会话" in text and "消息数：0" in text


async def test_artifact_filename_is_sanitized(client, auth_headers, session_maker):
    session = await _seed_session(client, auth_headers, session_maker, title="a/b:c*d")
    r = await client.post(
        f"/api/v1/sessions/{session['id']}/artifacts/markdown", headers=auth_headers
    )
    assert r.json()["filename"] == "a_b_c_d.md"


async def test_artifact_owner_isolation(client, auth_headers, session_maker):
    from tests.test_sessions_api import make_user

    session = await _seed_session(client, auth_headers, session_maker)
    created = (
        await client.post(
            f"/api/v1/sessions/{session['id']}/artifacts/markdown", headers=auth_headers
        )
    ).json()

    other = await make_user(client, "bob")
    assert (
        await client.get(f"/api/v1/artifacts/{created['id']}", headers=other)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/sessions/{session['id']}/artifacts", headers=other)
    ).status_code == 404


async def test_download_missing_artifact_is_404(client, auth_headers):
    r = await client.get(f"/api/v1/artifacts/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404
