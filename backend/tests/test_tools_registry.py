from datetime import UTC, datetime

from sqlalchemy import select

from app.ai.tools import builtins  # noqa: F401  触发注册
from app.ai.tools.registry import (
    TOOL_REGISTRY,
    get_tool,
    schema_from_signature,
    sync_tools,
    tools_payload,
)
from app.models import Tool


async def test_schema_from_signature():
    async def sample(query: str, top_k: int = 5) -> str:
        return ""

    schema = schema_from_signature(sample)
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["top_k"]["default"] == 5


async def test_registry_has_builtins():
    assert "time_now" in TOOL_REGISTRY and "kb_search" in TOOL_REGISTRY
    payload = tools_payload(["time_now"])
    assert payload[0]["function"]["name"] == "time_now"
    assert payload[0]["type"] == "function"


async def test_time_now_executes():
    result = await get_tool("time_now").handler()
    assert str(datetime.now(UTC).astimezone().year) in result


async def test_kb_search_is_placeholder():
    result = await get_tool("kb_search").handler("任意查询")
    assert "知识库" in result


async def test_sync_tools_upserts(session_maker):
    async with session_maker() as db:
        await sync_tools(db)
        rows = (await db.scalars(select(Tool))).all()
        assert {r.slug for r in rows} >= {"time_now", "kb_search"}
        await sync_tools(db)  # 幂等
        rows2 = (await db.scalars(select(Tool).where(Tool.slug == "time_now"))).all()
        assert len(rows2) == 1
