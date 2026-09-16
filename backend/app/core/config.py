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


settings = Settings()
