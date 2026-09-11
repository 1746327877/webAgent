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


settings = Settings()
