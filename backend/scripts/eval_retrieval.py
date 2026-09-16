"""检索评测 CLI：跑黄金问答集，打印 recall@k / MRR（docs/设计/22）。

用法（在 backend/ 下执行）：

    # 用自带语料建库并摄入（需要 Ollama + bge-m3），再评测
    uv run python -m scripts.eval_retrieval --seed-demo

    # 对已有知识库评测
    uv run python -m scripts.eval_retrieval --kb <kb_uuid> --top-k 10
"""

import argparse
import asyncio
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.eval.retrieval import DEFAULT_AT, DEFAULT_TOP_K, evaluate, load_golden

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = BACKEND_DIR / "eval" / "golden" / "demo.json"
FIXTURE_DIR = BACKEND_DIR / "eval" / "fixtures"
DEMO_KB_NAME = "评测演示语料"


def _parse_at(raw: str) -> tuple[int, ...]:
    values = tuple(int(part) for part in raw.split(",") if part.strip())
    if not values:
        raise SystemExit("--at 至少要有一个整数，例如 1,5,10")
    return values


async def seed_demo(username: str) -> uuid.UUID:
    """用 eval/fixtures 建演示知识库并摄入，返回 kb_id（已存在则复用）。"""
    from app.ai.rag.pipeline import run_ingest
    from app.models import Document, KnowledgeBase, User

    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            raise SystemExit(f"用户 {username} 不存在：先执行 python -m scripts.seed")

        kb = await db.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.owner_id == user.id, KnowledgeBase.name == DEMO_KB_NAME
            )
        )
        if kb is None:
            kb = KnowledgeBase(owner_id=user.id, name=DEMO_KB_NAME, description="检索评测演示语料")
            db.add(kb)
            await db.flush()

        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(FIXTURE_DIR.glob("*.md")):
            exists = await db.scalar(
                select(Document).where(Document.kb_id == kb.id, Document.filename == path.name)
            )
            if exists is not None:
                print(f"已存在，跳过摄入：{path.name}")
                continue
            content = path.read_text(encoding="utf-8")
            stored = f"{uuid.uuid4()}.md"
            (upload_dir / stored).write_text(content, encoding="utf-8")
            doc = Document(
                kb_id=kb.id,
                filename=path.name,
                file_type="md",
                size_bytes=len(content.encode()),
                uploaded_by=user.id,
                meta={"stored_name": stored},
            )
            db.add(doc)
            await db.commit()
            await run_ingest(str(doc.id))
            print(f"已摄入：{path.name}")
        return kb.id


async def run(args: argparse.Namespace) -> int:
    from app.ai.providers.ollama import OllamaProvider

    golden = load_golden(args.golden)
    if args.seed_demo:
        kb_id = await seed_demo(args.username)
    elif args.kb:
        kb_id = uuid.UUID(args.kb)
    else:
        raise SystemExit("需要 --kb <uuid> 或 --seed-demo")

    provider = OllamaProvider(settings.ollama_base_url)

    async def embed(texts: list[str]) -> list[list[float]]:
        return await provider.embed(texts, settings.embedding_model)

    try:
        report = await evaluate(
            SessionLocal,
            [kb_id],
            golden,
            top_k=args.top_k,
            at=_parse_at(args.at),
            embedder=embed,
        )
    finally:
        await provider.aclose()

    print(f"知识库：{kb_id}")
    print(report.format())
    if args.min_recall5 is not None and report.recall_at.get(5, 0.0) < args.min_recall5:
        print(f"recall@5 低于阈值 {args.min_recall5}，评测失败")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="检索评测：黄金问答集 → recall@k / MRR")
    parser.add_argument("--kb", help="知识库 UUID")
    parser.add_argument("--seed-demo", action="store_true", help="用 eval/fixtures 建库并摄入")
    parser.add_argument("--username", default="demo", help="--seed-demo 使用的用户名")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN, help="黄金问答集 JSON")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="每条取前 N 个结果")
    parser.add_argument("--at", default=",".join(str(k) for k in DEFAULT_AT), help="recall 的 k 列表")
    parser.add_argument("--min-recall5", type=float, default=None, help="recall@5 阈值，低于则退出码 1")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
