"""会话产物：导出 / 列表 / 归属校验（见 `docs/设计/24-会话产物.md`）。

当前只有一种产物来源：把整段会话导出成 Markdown。后续"工具/MCP 产出文件"复用同一张表，
把 `source` 标成 tool/mcp 即可。
"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Artifact, Message, Session, User

# 导出的是纯文本纪要，不可能这么大；纯防御，避免异常数据把盘写满
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
_UNSAFE_FILENAME = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")
# 落盘名只用白名单扩展名：filename 来自调用方，越界字符/超长后缀不能进存储名
_ALLOWED_ARTIFACT_EXTS = {"md", "docx", "pdf", "txt", "csv", "json", "html", "bin"}


def safe_filename(name: str, fallback: str = "文件") -> str:
    """展示用文件名清洗：去掉路径分隔符/控制字符，限长，空值回落 fallback。"""
    cleaned = _UNSAFE_FILENAME.sub("_", (name or "").strip()).strip(". ")
    return cleaned[:80] or fallback


def render_session_markdown(session: Session, messages: list[Message]) -> str:
    """把会话渲染成 Markdown：标题 + 元信息 + 逐条消息（含转写与引用来源）。"""
    now = datetime.now(UTC)
    lines = [
        f"# {session.title}",
        "",
        f"- 会话 ID：`{session.id}`",
        f"- 导出时间：{now:%Y-%m-%d %H:%M} UTC",
        f"- 消息数：{len(messages)}",
        "",
        "---",
        "",
    ]
    for message in messages:
        lines.append("## 我" if message.role == "user" else "## 助手")
        lines.append("")
        for block in message.blocks or []:
            kind = block.get("type")
            if kind == "text":
                lines.append(str(block.get("content") or ""))
                lines.append("")
            elif kind == "transcript":
                name = block.get("name") or "音频"
                body = block.get("text") or block.get("error") or ""
                lines.append(f"> 🎙️ 语音转写（{name}）：{body}")
                lines.append("")
            elif kind == "thinking":
                continue  # 思考链不进纪要
        citations = [b for b in (message.blocks or []) if b.get("type") == "citation"]
        if citations:
            lines.append("引用来源：")
            for block in citations:
                page = f" p{block['page']}" if block.get("page") else ""
                lines.append(f"- [{block.get('ref')}] {block.get('source')}{page}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


async def load_messages(db: AsyncSession, session: Session) -> list[Message]:
    """按 seq 取会话内全部消息（导出顺序即对话顺序）。"""
    return list(
        await db.scalars(
            select(Message).where(Message.session_id == session.id).order_by(Message.seq)
        )
    )


async def create_bytes_artifact(
    db: AsyncSession,
    session: Session,
    *,
    filename: str,
    mime_type: str,
    data: bytes,
    source: str,
) -> Artifact:
    """把字节落成会话产物；超限抛 ValueError（调用方转可读错误）。

    落盘约定与附件一致：`settings.upload_dir/{uuid}.{ext}`，扩展名取自 filename。
    """
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"产物过大（{len(data)} 字节）")
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in _ALLOWED_ARTIFACT_EXTS:
        ext = "bin"
    stored_name = f"{uuid.uuid4()}.{ext}"
    path = Path(settings.upload_dir) / stored_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

    artifact = Artifact(
        session_id=session.id,
        source=source,
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        file_path=stored_name,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def create_markdown_artifact(
    db: AsyncSession, session: Session, messages: list[Message]
) -> Artifact:
    """导出为 Markdown 并落盘；返回产物行。"""
    data = render_session_markdown(session, messages).encode("utf-8")
    return await create_bytes_artifact(
        db,
        session,
        filename=f"{safe_filename(session.title, '会话纪要')}.md",
        mime_type="text/markdown",
        data=data,
        source="export",
    )


async def list_artifacts(db: AsyncSession, session: Session) -> list[Artifact]:
    """会话产物，新的在前。"""
    return list(
        await db.scalars(
            select(Artifact)
            .where(Artifact.session_id == session.id)
            .order_by(Artifact.created_at.desc(), Artifact.id.desc())
        )
    )


async def delete_artifact(db: AsyncSession, artifact: Artifact) -> None:
    """删除产物：先删磁盘文件再删行；文件已缺失也不报错（状态以行为准）。"""
    # 与下载同一防护：file_path 含分隔符的脏数据不动盘，只删行
    if "/" not in artifact.file_path and "\\" not in artifact.file_path:
        Path(settings.upload_dir, artifact.file_path).unlink(missing_ok=True)
    await db.delete(artifact)
    await db.commit()


async def get_owned_artifact(
    db: AsyncSession, user: User, artifact_id: uuid.UUID
) -> Artifact | None:
    """按归属取产物：别人的产物返回 None（路由层转 404，不泄露存在性）。"""
    return await db.scalar(
        select(Artifact)
        .join(Session, Session.id == Artifact.session_id)
        .where(Artifact.id == artifact_id, Session.user_id == user.id)
    )
