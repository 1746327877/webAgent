import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.providers.base import ChatRequest, ModelProvider
from app.core.config import settings
from app.models.session import Session

TITLE_PROMPT = "为下面这段对话生成一个不超过16个字的标题，只输出标题，不要引号或标点：\n{text}"


async def generate_title(
    factory: async_sessionmaker[AsyncSession],
    provider: ModelProvider,
    session_id: uuid.UUID,
    first_user_text: str,
    fallback: str,
) -> None:
    title = ""
    try:
        async with asyncio.timeout(20):
            req = ChatRequest(
                model=settings.default_model,
                messages=[{"role": "user", "content": TITLE_PROMPT.format(text=first_user_text[:300])}],
                temperature=0.2,
                max_tokens=32,
            )
            async for ev in provider.chat_stream(req):
                if ev.type == "token":
                    title += ev.payload.get("delta", "")
    except Exception:  # noqa: BLE001 —— 标题失败不打扰主流程
        title = ""
    title = title.strip().strip('"').strip("《》").split("\n")[0].strip()[:16] or fallback[:16]
    async with factory() as db:
        session = await db.get(Session, session_id)
        if session is not None and session.title == "新对话":
            session.title = title
            await db.commit()
