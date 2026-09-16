"""统一入口：按 MCP_SERVICE 选择要启动的 MCP 服务。

    python -m src.main                                  # 用 .env 里的 MCP_SERVICE
    $env:MCP_SERVICE="mcp_voice2text"; python -m src.main

新增服务：在 SERVICES 里追加一行（模块路径 → 端口配置名），并在 config.py 加端口字段。
"""

from __future__ import annotations

import importlib

from src.config import settings
from src.logger import get_logger

logger = get_logger("main")

# 服务名 → (server 模块, 端口配置字段)。显式白名单，不做动态扫描。
SERVICES: dict[str, tuple[str, str]] = {
    "mcp_voice2text": ("src.mcp_voice2text.server", "VOICE_PORT"),
}


def main() -> None:
    name = settings.MCP_SERVICE
    entry = SERVICES.get(name)
    if entry is None:
        raise SystemExit(f"未知 MCP 服务：{name}；可选：{', '.join(sorted(SERVICES))}")

    module_path, port_field = entry
    port = getattr(settings, port_field)
    module = importlib.import_module(module_path)
    logger.info("启动 MCP 服务 %s：http://%s:%d/mcp", name, settings.HOST, port)
    module.mcp.run(transport="streamable-http", host=settings.HOST, port=port)


if __name__ == "__main__":
    main()
