import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.ai.model_manager import ModelManager
from app.main import app
from app.observability.spans import SpanBuffer
from app.services.attachment_service import cleanup_orphan_attachments
from tests.fake_provider import FakeProvider


class FailingDb:
    """commit 与外层 rollback 都失败：观测收尾不得把异常抛回生成链路。"""

    def add_all(self, rows):
        raise RuntimeError("insert failed")

    async def rollback(self):
        raise RuntimeError("rollback failed")


async def test_span_buffer_flush_survives_failed_rollback():
    buffer = SpanBuffer(trace_id=uuid.uuid4())
    buffer.add(type="llm", name="m")
    await buffer.flush(FailingDb())  # 当前实现会因 rollback 抛错
    assert buffer.rows == []  # 观测数据被丢弃，但生成链路不受影响


async def _seed_orphan(session_maker, upload_dir, *, broken: bool):
    from app.models import Attachment, Session, User

    stored = f"{uuid.uuid4()}.png"
    path = upload_dir / stored
    if broken:
        path.mkdir()  # unlink 目录必然失败（Windows: PermissionError；POSIX: IsADirectoryError）
    else:
        path.write_bytes(b"png")
    async with session_maker() as db:
        user = User(
            username=f"u{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(user)
        await db.flush()
        session = Session(user_id=user.id, title="t")
        db.add(session)
        await db.flush()
        att = Attachment(
            session_id=session.id,
            message_id=None,
            file_path=stored,
            original_name="a.png",
            mime_type="image/png",
            size_bytes=3,
            kind="image",
        )
        db.add(att)
        await db.flush()
        att.created_at = datetime.now(UTC) - timedelta(hours=30)
        await db.commit()
        return att.id, path


async def test_gc_continues_when_single_unlink_fails(session_maker, tmp_path, caplog):
    from app.models import Attachment

    broken_id, broken_path = await _seed_orphan(session_maker, tmp_path, broken=True)
    ok_id, ok_path = await _seed_orphan(session_maker, tmp_path, broken=False)
    with caplog.at_level(logging.WARNING, logger="app.services.attachment_service"):
        removed = await cleanup_orphan_attachments(
            session_factory=session_maker, max_age_hours=24, upload_dir=str(tmp_path)
        )
    assert removed == 1  # 只统计成功删除的行
    assert not ok_path.exists()  # 单文件失败不拖垮整批
    async with session_maker() as db:
        assert await db.get(Attachment, broken_id) is not None  # 保留待下轮重试
        assert await db.get(Attachment, ok_id) is None
    assert any(broken_path.name in record.message for record in caplog.records)


async def test_manual_model_load_and_unload(client, auth_headers, session_maker):
    app.state.model_manager = ModelManager(FakeProvider(), session_factory=session_maker)
    try:
        loaded = await client.post("/api/v1/models/m-manual/load", headers=auth_headers)
        assert loaded.status_code == 200
        body = loaded.json()
        assert body["current"] == "m-manual" and body["switched"] is True

        status = (await client.get("/api/v1/models/status", headers=auth_headers)).json()
        assert status["current"] == "m-manual"

        unloaded = await client.post("/api/v1/models/m-manual/unload", headers=auth_headers)
        assert unloaded.status_code == 200 and unloaded.json()["unloaded"] is True
        assert app.state.model_manager.current is None

        again = await client.post("/api/v1/models/m-manual/unload", headers=auth_headers)
        assert again.status_code == 200 and again.json()["unloaded"] is False
    finally:
        del app.state.model_manager


async def test_manual_model_ops_require_manager(client, auth_headers):
    app.state.model_manager = None  # 显式确保无 manager，避免跨文件串扰
    assert (await client.post("/api/v1/models/m/load", headers=auth_headers)).status_code == 503
    assert (await client.post("/api/v1/models/m/unload", headers=auth_headers)).status_code == 503
