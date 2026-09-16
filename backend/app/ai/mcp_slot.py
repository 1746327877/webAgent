"""部署级 MCP 槽位：把"平台能力 → 外部 MCP 服务"的接线收在一处。

`docs/设计/18`（联网搜索）与 `docs/设计/20`（OCR）是同一模式：部署方配一个 URL，
运行时按需把外部 MCP 合成为 `McpBinding` 注入本轮，**不写 `mcp_servers` 表**。
探测结果按 URL 缓存，避免每条消息都重新建连。

每个 `McpSlot` 实例自带缓存（实例即缓存作用域）：进程内单事件循环下顺序读写；
TTL 到期或 URL 变更时重建，探测失败也缓存 None 以免反复卡在连接超时。
多 worker 部署时各进程独立缓存，最长 TTL 内不一致，可接受。
"""

import logging
import time
import uuid
from collections.abc import Callable

from app.ai.agent_config import McpBinding
from app.services import mcp_service

logger = logging.getLogger("app.ai.mcp_slot")

CACHE_TTL_S = 300.0


class McpSlot:
    """一个部署级 MCP 槽位；`url_provider` 每次读取当前配置（便于测试与热改）。"""

    def __init__(
        self,
        server_name: str,
        url_provider: Callable[[], str],
        server_id: uuid.UUID,
        ttl_s: float = CACHE_TTL_S,
    ) -> None:
        self.server_name = server_name
        self._url_provider = url_provider
        self._server_id = server_id
        self._ttl_s = ttl_s
        self._cache: tuple[str, float, list[dict] | None] | None = None

    def is_enabled(self) -> bool:
        return bool(self._url())

    def reset_cache(self) -> None:
        """清空探测缓存（测试用）。"""
        self._cache = None

    def _url(self) -> str:
        return (self._url_provider() or "").strip()

    def _config(self, url: str) -> dict:
        """与 `mcp_service.server_config` 同形的 http 配置（槽位服务默认无鉴权）。"""
        return {
            "name": self.server_name,
            "transport": "http",
            "url": url,
            "headers": {},
            "command": None,
            "args": [],
            "env": {},
        }

    async def _probe_tools(self, url: str) -> list[dict] | None:
        now = time.monotonic()
        if self._cache is not None:
            cached_url, fetched_at, tools = self._cache
            if cached_url == url and now - fetched_at < self._ttl_s:
                return tools

        result = await mcp_service.probe(self._config(url))
        tools = result.tools if result.ok and result.tools else None
        if tools is None:
            logger.warning("MCP 槽位探测失败 server=%s url=%s error=%s", self.server_name, url, result.error)
        self._cache = (url, now, tools)
        return tools

    async def binding(self) -> McpBinding | None:
        """返回本轮可用的合成绑定；未配置或探测失败时返回 None。"""
        url = self._url()
        if not url:
            return None
        tools = await self._probe_tools(url)
        if not tools:
            return None
        return McpBinding(
            server_id=self._server_id,
            server_name=self.server_name,
            config=self._config(url),
            tools=tools,
        )
