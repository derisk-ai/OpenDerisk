"""适配 BAIZE 工具（str-returning / FunctionTool）到 V2 接口（V2ToolResult-returning async）。"""
from typing import Any, Optional

from derisk.agent.core.v2.tool_call_types import V2ToolResult
from derisk.agent.tools.context import ToolContext


class UnifiedToolAdapter:
    """包一个 BAIZE 工具，使其可被 default_acting_fn 调用。

    支持的工具形态：
    - ToolBase 子类：async execute(args, context) -> ToolResult（V2 兼容，直接透传）
    - ToolBase 子类：sync execute(*args, **kwargs) -> str（如 KnowledgeSearch）
    - FunctionTool（@tool 装饰）：async_execute(*args, **kwargs) -> str
    """

    def __init__(self, tool: Any):
        self._tool = tool
        self.name = getattr(tool, "name", "unknown")

    async def execute(self, args: dict, context: Optional[ToolContext] = None) -> V2ToolResult:
        tool = self._tool
        tool_name = self.name

        raw = await _call_tool(tool, args, context)
        return _to_v2_result(raw, tool_name)


async def _call_tool(tool: Any, args: dict, context: Optional[ToolContext]) -> Any:
    import inspect

    # Path 1: async execute with (args, context) signature
    execute_fn = getattr(tool, "execute", None)
    if execute_fn is not None and callable(execute_fn):
        if inspect.iscoroutinefunction(execute_fn):
            try:
                return await execute_fn(args, context=context)
            except TypeError:
                return await execute_fn(**(args or {}))
        else:
            try:
                return execute_fn(args, context=context)
            except TypeError:
                return execute_fn(**(args or {}))

    # Path 2: async_execute (FunctionTool / @tool decorated async fn)
    async_exec = getattr(tool, "async_execute", None)
    if async_exec is not None and callable(async_exec):
        try:
            return await async_exec(args, context=context)
        except TypeError:
            return await async_exec(**(args or {}))

    return None


def _to_v2_result(raw: Any, tool_name: str) -> V2ToolResult:
    """把任意 raw 输出转为 V2ToolResult。"""
    # 已经是 ToolResult / V2ToolResult
    if hasattr(raw, "success") and hasattr(raw, "output") and hasattr(raw, "tool_name"):
        if not raw.tool_name:
            raw.tool_name = tool_name
        return raw
    # 异常 / None
    if raw is None:
        return V2ToolResult.ok(output="", tool_name=tool_name)
    # 字符串 / dict / 其他
    return V2ToolResult.ok(output=raw, tool_name=tool_name)