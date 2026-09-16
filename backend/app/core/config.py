from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://webagent:webagent@localhost:5432/webagent"
    test_database_url: str = "postgresql+asyncpg://webagent:webagent@localhost:5432/webagent_test"
    jwt_secret: str = "dev-secret-change-me-0123456789abcdef"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    ollama_base_url: str = "http://localhost:11434"
    cors_origins: list[str] = ["http://localhost:5173"]
    default_model: str = "qwen2.5:7b-instruct-q4_K_M"
    history_rounds: int = 10
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: str = "./uploads"
    embedding_model: str = "bge-m3"
    vision_model: str = "qwen2.5vl:7b"
    model_keep_alive: str = "15m"
    vram_poll_seconds: int = 10
    attachment_orphan_hours: int = 24
    attachment_gc_interval_seconds: int = 3600
    log_level: str = "INFO"
    # MinerU 文档解析服务（宿主机独立进程）；为空表示不启用，回退内置解析
    mineru_api_url: str = ""
    mineru_timeout_s: float = 300.0
    # MinerU 解析后端：pipeline 支持纯 CPU；hybrid/vlm 需要 CUDA（默认 hybrid 会报 CUDA is not available）
    mineru_backend: str = "pipeline"
    # 联网搜索 MCP（compose 的 web-search 服务）；为空表示不支持联网搜索按钮
    web_search_mcp_url: str = ""
    # OCR MCP（部署方自备的 OCR 服务）；为空表示图片回合不挂 OCR 工具
    ocr_mcp_url: str = ""
    # 语音转写 MCP（外部 ASR 服务，见 docs/设计/23）；为空表示不支持音频附件转写
    asr_mcp_url: str = ""
    # 工具名覆盖；为空时自动选探测结果里名字含 "transcribe" 的第一个工具
    asr_mcp_tool: str = ""
    # 单个音频附件大小上限（默认 20MB，与文档一致）
    asr_max_bytes: int = 20 * 1024 * 1024


settings = Settings()
