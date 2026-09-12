import io
import uuid

from app.api.v1 import kbs as kbs_api


async def test_kb_crud_and_ownership(client, auth_headers):
    r = await client.post("/api/v1/kbs", json={"name": "Java 资料"}, headers=auth_headers)
    assert r.status_code == 201 and r.json()["name"] == "Java 资料"
    kid = r.json()["id"]
    lst = await client.get("/api/v1/kbs", headers=auth_headers)
    assert [k["id"] for k in lst.json()] == [kid]

    from tests.test_sessions_api import make_user

    other = await make_user(client, "bob")
    assert (await client.get(f"/api/v1/kbs/{kid}", headers=other)).status_code == 404
    assert (await client.delete(f"/api/v1/kbs/{kid}", headers=other)).status_code == 404
    assert (await client.delete(f"/api/v1/kbs/{kid}", headers=auth_headers)).status_code == 204


async def test_upload_enqueues_and_lists(client, auth_headers, session_maker, monkeypatch, tmp_path):
    calls: list[str] = []
    async def fake_enqueue(doc_id, **_):
        calls.append(str(doc_id))

    monkeypatch.setattr(kbs_api, "enqueue_ingest", fake_enqueue)
    monkeypatch.setattr(kbs_api.settings, "upload_dir", str(tmp_path))

    kid = (await client.post("/api/v1/kbs", json={"name": "K"}, headers=auth_headers)).json()["id"]
    files = {"file": ("notes.md", io.BytesIO("标题\n正文".encode()), "text/markdown")}
    r = await client.post(f"/api/v1/kbs/{kid}/documents", files=files, headers=auth_headers)
    assert r.status_code == 201
    doc = r.json()
    assert doc["status"] == "pending" and doc["filename"] == "notes.md"
    assert calls == [doc["id"]]

    lst = await client.get(f"/api/v1/kbs/{kid}/documents", headers=auth_headers)
    assert [d["id"] for d in lst.json()] == [doc["id"]]


async def test_upload_rejects_bad_type_and_size(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(kbs_api.settings, "upload_dir", str(tmp_path))
    kid = (await client.post("/api/v1/kbs", json={"name": "K"}, headers=auth_headers)).json()["id"]
    bad = {"file": ("x.exe", io.BytesIO(b"x"), "application/octet-stream")}
    assert (await client.post(f"/api/v1/kbs/{kid}/documents", files=bad, headers=auth_headers)).status_code == 415


async def test_upload_rejects_oversized_file(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(kbs_api, "MAX_BYTES", 10)
    monkeypatch.setattr(kbs_api.settings, "upload_dir", str(tmp_path))
    kid = (await client.post("/api/v1/kbs", json={"name": "K"}, headers=auth_headers)).json()["id"]
    big = {"file": ("big.md", io.BytesIO(b"x" * 11), "text/markdown")}
    r = await client.post(f"/api/v1/kbs/{kid}/documents", files=big, headers=auth_headers)
    assert r.status_code == 413


async def test_delete_document_and_retry(client, auth_headers, monkeypatch, tmp_path, session_maker):
    monkeypatch.setattr(kbs_api.settings, "upload_dir", str(tmp_path))
    calls: list[str] = []
    async def fake_enqueue(doc_id, **_):
        calls.append(str(doc_id))

    monkeypatch.setattr(kbs_api, "enqueue_ingest", fake_enqueue)
    kid = (await client.post("/api/v1/kbs", json={"name": "K"}, headers=auth_headers)).json()["id"]
    files = {"file": ("a.md", io.BytesIO(b"x"), "text/markdown")}
    doc = (await client.post(f"/api/v1/kbs/{kid}/documents", files=files, headers=auth_headers)).json()

    # 伪装失败态后重试
    async with session_maker() as db:
        from app.models import Document

        row = await db.get(Document, doc["id"])
        row.status = "failed"
        row.error = "boom"
        await db.commit()
    calls.clear()
    r = await client.post(
        f"/api/v1/kbs/{kid}/documents/{doc['id']}/retry", headers=auth_headers
    )
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert calls == [doc["id"]]

    d = await client.delete(f"/api/v1/kbs/{kid}/documents/{doc['id']}", headers=auth_headers)
    assert d.status_code == 204


async def test_worker_settings_shape():
    from app.workers.settings import WorkerSettings

    assert WorkerSettings.redis_settings is not None
    assert len(WorkerSettings.functions) >= 1
    assert WorkerSettings.job_timeout == 1800


async def test_enqueue_ingest_uses_dedup_job_id(monkeypatch):
    calls: list[tuple] = []
    closed = False

    class FakePool:
        async def enqueue_job(self, name, doc_id, **kwargs):
            calls.append((name, doc_id, kwargs))

        async def aclose(self):
            nonlocal closed
            closed = True

    async def fake_create_pool(redis_settings):
        return FakePool()

    monkeypatch.setattr(kbs_api, "create_pool", fake_create_pool)
    doc_id = uuid.uuid4()
    await kbs_api.enqueue_ingest(doc_id)
    await kbs_api.enqueue_ingest(doc_id, dedupe=False)
    assert calls == [
        ("ingest_job", str(doc_id), {"_job_id": f"ingest:{doc_id}"}),
        ("ingest_job", str(doc_id), {}),
    ]
    assert closed is True


async def test_upload_enqueue_failure_marks_document_failed(
    client, auth_headers, session_maker, monkeypatch, tmp_path
):
    from sqlalchemy import select

    from app.models import Document

    monkeypatch.setattr(kbs_api.settings, "upload_dir", str(tmp_path))

    async def broken_create_pool(redis_settings):
        raise ConnectionError("redis down")

    monkeypatch.setattr(kbs_api, "create_pool", broken_create_pool)

    kid = (await client.post("/api/v1/kbs", json={"name": "K"}, headers=auth_headers)).json()["id"]
    files = {"file": ("a.md", io.BytesIO(b"x"), "text/markdown")}
    r = await client.post(f"/api/v1/kbs/{kid}/documents", files=files, headers=auth_headers)
    assert r.status_code == 503

    async with session_maker() as db:
        doc = (await db.scalars(select(Document))).one()
        assert doc.status == "failed"
        assert doc.error == "任务排队失败，请重试"
