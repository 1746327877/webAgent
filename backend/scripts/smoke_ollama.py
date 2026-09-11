import asyncio
import sys

from app.ai.providers.base import ChatRequest
from app.ai.providers.ollama import OllamaProvider


async def main() -> None:
    provider = OllamaProvider("http://localhost:11434")
    health = await provider.health()
    print("health:", health)
    if not health.ok:
        sys.exit(1)
    print("已加载模型:", await provider.list_loaded())
    async for ev in provider.chat_stream(
        ChatRequest(
            model="qwen2.5:7b-instruct-q4_K_M",
            messages=[{"role": "user", "content": "用一句话介绍你自己"}],
            max_tokens=64,
        )
    ):
        print(ev.type, ev.payload)
    await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
