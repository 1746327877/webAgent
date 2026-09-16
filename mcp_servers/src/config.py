"""mcp_servers 公共配置（各 MCP 子服务共用）。

对齐 `mcp_new/src/config.py` 的风格：pydantic-settings 从环境变量 / `.env` 读取，
密钥与端口不写死在代码里。新增服务时**只在这里加字段**，不要另建配置文件。
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 工程根目录：src/config.py -> mcp_servers/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 公共 ----
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # 统一入口默认启动哪个服务（`python -m src.main`）
    MCP_SERVICE: str = "mcp_voice2text"

    # ---- mcp_voice2text（本地 faster-whisper，见 docs/设计/23）----
    VOICE_PORT: int = 10001
    WHISPER_MODEL: str = "Systran/faster-whisper-large-v3"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "zh"
    WHISPER_BEAM_SIZE: int = 5
    # CPU 上 Whisper 很吃算力：默认只允许 2 个并发转写
    VOICE_MAX_PARALLEL: int = 2


settings = Settings()
