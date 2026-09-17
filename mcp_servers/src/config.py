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
    # streamable-http 单次请求体上限（MB）。SDK 默认 4MB，但平台用 base64 传音频
    # （体积放大 ~33%），因此放宽；要大于 ASR_MAX_BYTES * 1.34
    MCP_MAX_REQUEST_BODY_MB: int = 64
    # 额外的 CUDA 运行库目录（`;` 分隔）。ctranslate2 用普通 LoadLibrary 找依赖，
    # 只 add_dll_directory 不够、必须进 PATH；本机可直接复用 Ollama 自带的 CUDA 库，
    # 省掉 1.3GB 下载（启动脚本会自动探测并填入）
    WHISPER_CUDA_DLL_DIRS: str = ""


settings = Settings()
