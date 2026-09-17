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


def _safe_filename(title: str) -> str:
    """会话标题可能含路径分隔符/控制字符，落到文件名前必须清洗。"""
    cleaned = _UNSAFE_FILENAME.sub("_", (title or "").strip()).strip(". ")
    return cleaned[:80] or "会话纪要"


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


async def create_markdown_artifact(
    db: AsyncSession, session: Session, messages: list[Message]
) -> Artifact:
    """导出为 Markdown 并落盘；返回产物行。"""
    data = render_session_markdown(session, messages).encode("utf-8")
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"导出内容过大（{len(data)} 字节）")

    stored_name = f"{uuid.uuid4()}.md"
    path = Path(settings.upload_dir) / stored_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

    artifact = Artifact(
        session_id=session.id,
        source="export",
        filename=f"{_safe_filename(session.title)}.md",
        mime_type="text/markdown",
        size_bytes=len(data),
        file_path=stored_name,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def list_artifacts(db: AsyncSession, session: Session) -> list[Artifact]:
    """会话产物，新的在前。"""
    return list(
        await db.scalars(
            select(Artifact)
            .where(Artifact.session_id == session.id)
            .order_by(Artifact.created_at.desc(), Artifact.id.desc())
        )
    )


async def get_owned_artifact(
    db: AsyncSession, user: User, artifact_id: uuid.UUID
) -> Artifact | None:
    """按归属取产物：别人的产物返回 None（路由层转 404，不泄露存在性）。"""
    return await db.scalar(
        select(Artifact)
        .join(Session, Session.id == Artifact.session_id)
        .where(Artifact.id == artifact_id, Session.user_id == user.id)
    )
