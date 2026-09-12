import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services.attachment_service import cleanup_orphan_attachments


async def _seed(session_maker, upload_dir: Path, *, bound: bool, age_hours: int):
    from app.models import Attachment, Message, Session, User

    stored = f"{uuid.uuid4()}.png"
    path = upload_dir / stored
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
        # created_at 是 server_default，测试显式回填时间做 TTL 断言
        att.created_at = datetime.now(UTC) - timedelta(hours=age_hours)
        if bound:
            msg = Message(session_id=session.id, role="user", blocks=[])
            db.add(msg)
            await db.flush()
            att.message_id = msg.id
        await db.commit()
        return att.id, path


async def test_old_orphan_attachment_removed(session_maker, tmp_path):
    att_id, path = await _seed(session_maker, tmp_path, bound=False, age_hours=30)
    removed = await cleanup_orphan_attachments(
        session_factory=session_maker, max_age_hours=24, upload_dir=str(tmp_path)
    )
    assert removed == 1
    assert not path.exists()
    async with session_maker() as db:
        from app.models import Attachment

        assert await db.get(Attachment, att_id) is None


async def test_fresh_orphan_kept(session_maker, tmp_path):
    _att_id, path = await _seed(session_maker, tmp_path, bound=False, age_hours=1)
    removed = await cleanup_orphan_attachments(
        session_factory=session_maker, max_age_hours=24, upload_dir=str(tmp_path)
    )
    assert removed == 0
    assert path.exists()


async def test_bound_attachment_kept(session_maker, tmp_path):
    _att_id, path = await _seed(session_maker, tmp_path, bound=True, age_hours=48)
    removed = await cleanup_orphan_attachments(
        session_factory=session_maker, max_age_hours=24, upload_dir=str(tmp_path)
    )
    assert removed == 0
    assert path.exists()
