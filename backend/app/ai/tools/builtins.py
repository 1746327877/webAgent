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


@tool(
    "transcribe_audio",
    "语音转写",
    "把用户上传的音频附件转写成文字（平台负责读取附件并调用 ASR 服务）",
    category="media",
    is_system=True,
)
async def transcribe_audio(name: str = "") -> str:
    """真实的转写在 runtime 层拦截（只有平台拿得到本轮附件）。

    `name` 可选：只转写文件名包含它的那个音频；留空转写本轮全部音频。
    """
    return "本轮没有可转写的音频附件。"
