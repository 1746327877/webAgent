import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.session import Message, Session
from app.models.user import User

TOPICS = ["Java 并发", "Python 异步", "RAG 检索", "架构设计", "面试复盘", "SQL 优化"]


def build_flagship_messages() -> list[dict]:
    """旗舰演示会话：思考链 / 工具卡片 / 引用 / 接力一屏俱全，开箱即可演示。"""
    return [
        {
            "role": "user",
            "blocks": [{"type": "text", "content": "线程池的核心参数有哪些？@深度思考"}],
        },
        {
            "role": "assistant",
            "status": "done",
            "blocks": [
                {"type": "thinking", "content": "先检索知识库，再组织线程池参数的讲解顺序…", "duration_ms": 2100},
                {
                    "type": "tool_call",
                    "id": "seed-c1",
                    "tool": "kb_search",
                    "args": {"query": "线程池 核心参数"},
                },
                {
                    "type": "tool_result",
                    "id": "seed-c1",
                    "tool": "kb_search",
                    "status": "ok",
                    "elapsed_ms": 120,
                    "preview": "线程池核心参数包括 corePoolSize、maximumPoolSize、workQueue…",
                },
                {
                    "type": "citation",
                    "ref": 1,
                    "chunk_id": "seed-chunk",
                    "source": "java-concurrency.md",
                    "page": None,
                    "score": 0.87,
                    "snippet": "线程池核心参数包括 corePoolSize、maximumPoolSize、workQueue、RejectedExecutionHandler。",
                },
                {
                    "type": "text",
                    "content": "线程池核心参数包括 corePoolSize、maximumPoolSize、workQueue 与拒绝策略 [1]。",
                },
            ],
        },
        {
            "role": "assistant",
            "status": "done",
            "blocks": [
                {"type": "thinking", "content": "补充一个工程取舍：队列类型决定拒绝时机…", "duration_ms": 3200},
                {"type": "text", "content": "补充：使用有界队列 + CallerRunsPolicy 是常见的稳健组合。"},
            ],
        },
    ]


FILLER_TITLE_MARKER = " #0"  # 压力会话固定从 #0 起编，作为「已生成」的稳定信号


async def main() -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "demo"))
        if user is None:
            print("请先运行 scripts.seed 创建 demo 用户")
            return
        now = datetime.now(UTC)
        filler_exists = await db.scalar(
            select(Session.id).where(
                Session.user_id == user.id,
                Session.title.like(f"%{FILLER_TITLE_MARKER}"),
            )
        )
        if filler_exists is not None:
            print("演示压力会话已存在，跳过")
        else:
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

        flagship_title = "旗舰演示：Java 并发与 RAG"
        exists = await db.scalar(
            select(Session).where(Session.user_id == user.id, Session.title == flagship_title)
        )
        if exists is None:
            flagship = Session(user_id=user.id, title=flagship_title, pinned=True, last_message_at=now)
            db.add(flagship)
            await db.flush()
            for item in build_flagship_messages():
                db.add(
                    Message(
                        session_id=flagship.id,
                        role=item["role"],
                        blocks=item["blocks"],
                        status=item.get("status", "done"),
                    )
                )
            await db.commit()
            print(f"已创建旗舰演示会话：{flagship_title}")


if __name__ == "__main__":
    asyncio.run(main())
