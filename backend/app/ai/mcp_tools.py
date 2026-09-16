"""把智能体绑定的 MCP 工具转成 function calling 载荷。

模型看到的是形如 `mcp__{server}__{tool}` 的函数名；执行时用返回的映射还原到
真实 MCP server 配置与 tool 名（见 `runtime._execute_tool`）。
"""

import re
from typing import Any

FUNC_NAME_MAX = 64
_NON_WORD = re.compile(r"[^a-zA-Z0-9_]+")


def _slug(text: str) -> str:
    slug = _NON_WORD.sub("_", text).strip("_").lower()
    return slug or "s"


def build_mcp_tools(bindings: list[Any]) -> tuple[list[dict], dict[str, dict]]:
    """bindings 为带 server_name/config/tools 的对象列表。

    返回 (function 载荷列表, {函数名: {config, tool_name, label}})。
    """
    payload: list[dict] = []
    mapping: dict[str, dict] = {}
    used: set[str] = set()

    for binding in bindings:
        server_slug = _slug(binding.server_name)
        for tool in binding.tools:
            tool_name = str(tool.get("name") or "").strip()
            if not tool_name:
                continue
            base = f"mcp__{server_slug}__{_slug(tool_name)}"[:FUNC_NAME_MAX]
            fn_name = base
            index = 1
            while fn_name in used:
                suffix = f"_{index}"
                fn_name = base[: FUNC_NAME_MAX - len(suffix)] + suffix
                index += 1
            used.add(fn_name)

            description = str(tool.get("description") or tool_name)
            payload.append(
                {
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "description": f"[MCP:{binding.server_name}] {description}"[:1024],
                        "parameters": tool.get("input_schema")
                        or {"type": "object", "properties": {}},
                    },
                }
            )
            mapping[fn_name] = {
                "config": binding.config,
                "tool_name": tool_name,
                "label": f"{binding.server_name} · {tool_name}",
            }

    return payload, mapping
