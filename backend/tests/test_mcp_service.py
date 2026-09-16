import sys

from app.services import mcp_service

# 一个最小 stdio MCP server，用官方 SDK 起真实子进程验证连接/列工具/调用
SERVER_SRC = '''
from mcp.server.mcpserver import MCPServer

server = MCPServer("demo")


@server.tool(description="Add two integers")
def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    server.run("stdio")
'''


async def test_stdio_probe_and_call(tmp_path):
    script = tmp_path / "server.py"
    script.write_text(SERVER_SRC, encoding="utf-8")
    config = {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(script)],
        "env": {},
    }

    result = await mcp_service.probe(config)
    assert result.ok, result.error
    assert [tool["name"] for tool in result.tools] == ["add"]

    text, status = await mcp_service.call_tool(config, "add", {"a": 2, "b": 3})
    assert status == "ok"
    assert text.strip() == "5"


async def test_http_probe_unreachable_returns_friendly_error():
    result = await mcp_service.probe({"transport": "http", "url": "http://127.0.0.1:9/mcp"})
    assert result.ok is False
    assert result.error
    assert result.latency_ms is not None


def test_non_ascii_header_detected():
    assert mcp_service._non_ascii_header({"Authorization": "Bearer <令牌>"}) == "Authorization"
    assert mcp_service._non_ascii_header({"Authorization": "Bearer abc123"}) is None


async def test_probe_rejects_non_ascii_header_without_network():
    result = await mcp_service.probe(
        {
            "transport": "http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer <登录后复制Token替换>"},
        }
    )
    assert result.ok is False
    assert "非 ASCII" in (result.error or "")


async def test_probe_appends_http_status_detail(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def boom(config):
        raise RuntimeError("connect failed")
        yield  # pragma: no cover

    async def fake_detail(config):
        return "HTTP 401（鉴权失败，检查请求头里的 Token 是否有效）"

    monkeypatch.setattr(mcp_service, "_connect", boom)
    monkeypatch.setattr(mcp_service, "_http_status_detail", fake_detail)

    result = await mcp_service.probe(
        {"transport": "http", "url": "https://example.com/mcp", "headers": {}}
    )
    assert result.ok is False
    assert "HTTP 401" in (result.error or "")


async def test_probe_logs_failure_without_leaking_headers(monkeypatch, caplog):
    import logging
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def boom(config):
        raise RuntimeError("connect failed")
        yield  # pragma: no cover

    async def fake_detail(config):
        return None

    monkeypatch.setattr(mcp_service, "_connect", boom)
    monkeypatch.setattr(mcp_service, "_http_status_detail", fake_detail)

    with caplog.at_level(logging.WARNING, logger="app.mcp"):
        result = await mcp_service.probe(
            {
                "name": "瑞幸咖啡",
                "transport": "http",
                "url": "https://mcp.example.com/mcp",
                "headers": {"Authorization": "Bearer SECRET_TOKEN"},
            }
        )

    assert result.ok is False
    assert any("MCP 测试连接失败" in record.message for record in caplog.records)
    assert "SECRET_TOKEN" not in caplog.text
    assert "mcp.example.com" in caplog.text


def test_configure_logging_is_idempotent():
    import logging

    from app.core.logging import _MARKER, configure_logging

    root = logging.getLogger()
    before = list(root.handlers)
    try:
        configure_logging()
        configure_logging()
        marked = [h for h in root.handlers if getattr(h, _MARKER, False)]
        assert len(marked) == 1
    finally:
        for handler in [h for h in root.handlers if h not in before]:
            root.removeHandler(handler)
