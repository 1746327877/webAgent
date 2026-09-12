import asyncio


async def main() -> None:
    from scripts import seed, seed_agents, seed_demo_sessions, seed_kb

    steps = (
        ("演示账号", seed),
        ("预置智能体", seed_agents),
        ("演示会话与旗舰演示", seed_demo_sessions),
        ("演示知识库（需要 Ollama + bge-m3）", seed_kb),
    )
    for label, module in steps:
        try:
            await module.main()
        except Exception as exc:  # noqa: BLE001 —— 单步失败不阻塞其余演示数据
            print(f"[seed_all] {label} 步骤失败（可稍后重试）：{exc}")


if __name__ == "__main__":
    asyncio.run(main())
