from datetime import UTC, datetime

from app.ai.tools.registry import tool


@tool(
    "time_now",
    "当前时间",
    "获取今天的日期与星期（服务器本地时区）",
    category="system",
    is_system=True,
)
async def time_now() -> str:
    now = datetime.now(UTC).astimezone()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"{now:%Y-%m-%d} {weekdays[now.weekday()]}"


@tool(
    "kb_search",
    "知识库检索",
    "在智能体绑定的知识库中检索相关文档片段",
    category="knowledge",
    is_system=True,
)
async def kb_search(query: str, top_k: int = 5) -> str:
    return "未绑定知识库或检索不可用，请直接基于已有知识回答。"
