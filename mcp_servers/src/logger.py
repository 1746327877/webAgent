"""mcp_servers 公共日志。

各子服务统一走这里，避免各自 basicConfig 造成重复 handler / 格式不一致。
"""

from __future__ import annotations

import logging

from src.config import settings

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)
