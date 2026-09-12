import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select

from app.ai.rag.pipeline import run_ingest
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Agent, AgentKB, Document, KnowledgeBase, User

SAMPLE = """# Java 并发笔记

## synchronized
synchronized 是可重入的内置锁，JDK 1.6 后包含偏向锁、轻量级锁到重量级锁的升级过程。

## volatile
volatile 保证可见性与禁止指令重排，但不保证原子性。

## 线程池
线程池核心参数包括 corePoolSize、maximumPoolSize、workQueue、RejectedExecutionHandler。
"""


async def main() -> None:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == "demo"))
        if user is None:
            print("请先运行 scripts.seed 创建 demo 用户")
            return
        exists = await db.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.owner_id == user.id, KnowledgeBase.name == "Java 并发笔记"
            )
        )
        if exists is not None:
            print("演示知识库已存在，跳过")
            return
        kb = KnowledgeBase(owner_id=user.id, name="Java 并发笔记", description="M3 演示数据")
        db.add(kb)
        await db.flush()
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4()}.md"
        (upload_dir / stored).write_text(SAMPLE, encoding="utf-8")
        doc = Document(
            kb_id=kb.id,
            filename="java-concurrency.md",
            file_type="md",
            size_bytes=len(SAMPLE.encode()),
            uploaded_by=user.id,
            meta={"stored_name": stored},
        )
        db.add(doc)
        await db.commit()
        await run_ingest(str(doc.id))
        agent = await db.scalar(
            select(Agent).where(Agent.owner_id == user.id, Agent.name == "代码专家")
        )
        if agent is not None:
            db.add(AgentKB(agent_id=agent.id, kb_id=kb.id, top_k=3))
            await db.commit()
        print(f"已创建演示知识库 {kb.id}（文档 {doc.id}），并绑定到代码专家")


if __name__ == "__main__":
    asyncio.run(main())
