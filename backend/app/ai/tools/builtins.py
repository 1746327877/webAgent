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


@tool(
    "doc_create",
    "文档生成",
    "根据 Markdown 正文生成 md/docx/pdf 文件，生成可下载的会话产物",
    category="document",
    is_system=True,
)
async def doc_create(filename: str, content: str, target: str = "both") -> str:
    """真实生成在 runtime 层拦截（只有平台有产物落盘能力）。

    `filename`：不带后缀的文件名；`content`：完整的 Markdown 正文；
    `target`：md / docx / pdf / both（同时生成 docx 与 pdf）。
    """
    return "文档生成不可用：缺少会话上下文。"


@tool(
    "doc_convert",
    "文档转换",
    "把本轮上传的文档转换为指定格式（md/docx/pdf），生成可下载的会话产物",
    category="document",
    is_system=True,
)
async def doc_convert(target: str, name: str = "") -> str:
    """真实转换在 runtime 层拦截（只有平台拿得到本轮附件与产物落盘能力）。

    `target`：目标格式 md / docx / pdf；`name` 可选，按文件名包含匹配要转换的文档。
    """
    return "本轮没有可转换的文档附件。"
