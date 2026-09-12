import asyncio

from sqlalchemy import select

from app.ai.tools import sync_tools
from app.core.db import SessionLocal
from app.models import Agent, AgentTool, AgentVersion, Tool, User

PRESETS = [
    {
        "name": "通用助手",
        "emoji": "🤖",
        "description": "日常问答与写作",
        "tags": ["通用"],
        "system_prompt": "你是一位耐心、准确的通用助手。今天是 {{today}}。",
        "welcome_msg": "你好，我是通用助手，有什么可以帮你？",
        "examples": ["帮我写一封请假邮件", "解释一下什么是 REST"],
        "tools": [],
        "model": "qwen2.5:7b-instruct-q4_K_M",
    },
    {
        "name": "代码专家",
        "emoji": "💻",
        "description": "代码审查与疑难解答",
        "tags": ["开发"],
        "system_prompt": "你是资深工程师，回答代码问题要给出可运行的示例，并指出常见坑。今天是 {{today}}。",
        "welcome_msg": "贴出你的代码或报错，我来帮你。",
        "examples": ["帮我 review 这段 Python", "解释一下这个报错"],
        "tools": [],
        "model": "qwen2.5:7b-instruct-q4_K_M",
    },
    {
        "name": "时间管家",
        "emoji": "⏰",
        "description": "可以调用工具查询当前时间",
        "tags": ["工具"],
        "system_prompt": "你是时间管家。用户问时间时，必须调用 time_now 工具再回答。",
        "welcome_msg": "问我现在几点吧。",
        "examples": ["现在几点？", "今天是星期几？"],
        "tools": ["time_now"],
        "model": "qwen2.5:7b-instruct-q4_K_M",
    },
]


async def main() -> None:
    async with SessionLocal() as db:
        await sync_tools(db)
        user = await db.scalar(select(User).where(User.username == "demo"))
        if user is None:
            print("请先运行 scripts.seed 创建 demo 用户")
            return
        created = 0
        for preset in PRESETS:
            exists = await db.scalar(
                select(Agent).where(Agent.owner_id == user.id, Agent.name == preset["name"])
            )
            if exists is not None:
                continue
            agent = Agent(
                owner_id=user.id,
                name=preset["name"],
                emoji=preset["emoji"],
                description=preset["description"],
                tags=preset["tags"],
                system_prompt=preset["system_prompt"],
                model_config={"model": preset["model"], "temperature": 0.7},
                welcome_msg=preset["welcome_msg"],
                examples=preset["examples"],
                status="published",
                current_version=1,
            )
            db.add(agent)
            await db.flush()
            for slug in preset["tools"]:
                tool = await db.scalar(select(Tool).where(Tool.slug == slug))
                if tool is not None:
                    db.add(AgentTool(agent_id=agent.id, tool_id=tool.id))
            db.add(
                AgentVersion(
                    agent_id=agent.id,
                    version=1,
                    snapshot={
                        "name": preset["name"],
                        "emoji": preset["emoji"],
                        "description": preset["description"],
                        "tags": preset["tags"],
                        "system_prompt": preset["system_prompt"],
                        "model_config": {"model": preset["model"], "temperature": 0.7},
                        "welcome_msg": preset["welcome_msg"],
                        "examples": preset["examples"],
                        "tool_slugs": preset["tools"],
                    },
                    published_by=user.id,
                )
            )
            created += 1
        await db.commit()
        print(f"已创建 {created} 个预置智能体（跳过 {len(PRESETS) - created} 个已存在）")


if __name__ == "__main__":
    asyncio.run(main())
