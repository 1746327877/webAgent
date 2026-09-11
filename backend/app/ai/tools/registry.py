import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import create_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tool


@dataclass
class ToolDef:
    slug: str
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]
    category: str = "general"
    is_system: bool = False


TOOL_REGISTRY: dict[str, ToolDef] = {}


def schema_from_signature(fn: Callable) -> dict:
    params = inspect.signature(fn).parameters
    fields = {
        name: (
            p.annotation if p.annotation is not inspect.Parameter.empty else str,
            p.default if p.default is not inspect.Parameter.empty else ...,
        )
        for name, p in params.items()
    }
    return create_model(fn.__name__, **fields).model_json_schema()


def tool(slug: str, name: str, description: str, category: str = "general", is_system: bool = False):
    def decorator(fn: Callable) -> Callable:
        TOOL_REGISTRY[slug] = ToolDef(
            slug=slug,
            name=name,
            description=description,
            input_schema=schema_from_signature(fn),
            handler=fn,
            category=category,
            is_system=is_system,
        )
        return fn

    return decorator


def get_tool(slug: str) -> ToolDef | None:
    return TOOL_REGISTRY.get(slug)


def tools_payload(slugs: list[str]) -> list[dict]:
    payload = []
    for slug in slugs:
        item = TOOL_REGISTRY.get(slug)
        if item is not None:
            payload.append(
                {
                    "type": "function",
                    "function": {
                        "name": item.slug,
                        "description": item.description,
                        "parameters": item.input_schema,
                    },
                }
            )
    return payload


async def sync_tools(db: AsyncSession) -> None:
    for item in TOOL_REGISTRY.values():
        existing = await db.scalar(select(Tool).where(Tool.slug == item.slug))
        if existing is None:
            db.add(
                Tool(
                    slug=item.slug,
                    name=item.name,
                    description=item.description,
                    input_schema=item.input_schema,
                    category=item.category,
                    is_system=item.is_system,
                )
            )
        else:
            existing.name = item.name
            existing.description = item.description
            existing.input_schema = item.input_schema
            existing.category = item.category
            existing.is_system = item.is_system
    await db.commit()
