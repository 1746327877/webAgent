import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.session import Message, Session
from app.models.user import User

TOPICS = ["Java 并发", "Python 异步", "RAG 检索", "架构设计", "面试复盘", "SQL 优化"]


async def main() -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "demo"))
        if user is None:
            print("请先运行 scripts.seed 创建 demo 用户")
            return
        now = datetime.now(UTC)
        sessions = []
        for i in range(1000):
            sessions.append(
                Session(
                    user_id=user.id,
                    title=f"{random.choice(TOPICS)} #{i}",
                    pinned=i < 2,
                    last_message_at=now - timedelta(hours=i),
                    created_at=now - timedelta(hours=i + 24),
                )
            )
        db.add_all(sessions)
        await db.flush()
        demo = sessions[0]
        db.add(Message(session_id=demo.id, role="user",
                       blocks=[{"type": "text", "content": "什么是虚拟滚动？"}]))
        db.add(Message(session_id=demo.id, role="assistant",
                       blocks=[{"type": "text", "content": "只渲染可视区域节点的列表技术。"}],
                       status="done"))
        await db.commit()
        print(f"已创建 1000 个会话；demo 会话 id = {demo.id}")


if __name__ == "__main__":
    asyncio.run(main())
