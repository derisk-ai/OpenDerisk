"""Async resolver for Agent resource type ``tool(memory_case)`` (registered on ResourceResolver)."""

from __future__ import annotations

import json
from typing import Any


async def resolve_memory_case_resource_value(value: Any) -> Any:
    info: dict[str, Any] = {"type": "memory_case", "mcp_name": "memory_case"}
    if isinstance(value, dict):
        info.update(value)
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                info.update(parsed)
        except Exception:
            pass
    return info
