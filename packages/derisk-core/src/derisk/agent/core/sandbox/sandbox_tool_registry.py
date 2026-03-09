"""
Sandbox 工具注册表 - 兼容层

这是一个向后兼容的模块，将旧的 sandbox_tool 注册机制适配到统一工具框架。

新的代码应该使用:
    from derisk.agent.tools import tool_registry
    from derisk.agent.tools.decorators import sandbox_tool

旧的代码可以继续使用:
    from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool, sandbox_tool_dict
"""

import logging
from typing import Dict, Any, Optional, Callable

# 向后兼容：导入统一框架
from derisk.agent.tools.decorators import sandbox_tool as _unified_sandbox_tool
from derisk.agent.tools.registry import tool_registry

logger = logging.getLogger(__name__)

DERISK_TOOL_IDENTIFIER = 'sandbox_tool'

# 向后兼容：保留全局字典，但实际从统一注册表同步
sandbox_tool_dict: Dict[str, Any] = {}


def sandbox_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    owner: Optional[str] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    ask_user: bool = False,
    stream: bool = False,
    concurrency: str = "parallel",
) -> Callable[..., Any]:
    """
    沙箱工具装饰器 - 向后兼容层
    
    将旧版 @sandbox_tool 装饰器适配到统一工具框架。
    
    使用方式（与旧版完全兼容）:
        @sandbox_tool(name="my_tool", description="My tool")
        async def my_tool(client, arg1: str) -> str:
            ...
    """
    # 使用统一框架的 sandbox_tool 装饰器
    return _unified_sandbox_tool(
        name=name,
        description=description,
        input_schema=input_schema,
    )


def _sync_from_unified_registry():
    """从统一注册表同步 sandbox 工具到旧的全局字典"""
    global sandbox_tool_dict
    from derisk.agent.tools.base import ToolCategory
    
    # 获取所有 SANDBOX 类别的工具
    sandbox_tools = tool_registry.get_by_category(ToolCategory.SANDBOX)
    
    for tool in sandbox_tools:
        tool_name = tool.name
        if tool_name not in sandbox_tool_dict:
            sandbox_tool_dict[tool_name] = tool
            logger.debug(f"[兼容层] 已同步 sandbox 工具: {tool_name}")


def get_sandbox_tool(tool_name: str):
    """
    获取沙箱工具
    
    优先从统一注册表获取，如果不存在则从旧字典获取。
    """
    # 先尝试从统一注册表获取
    tool = tool_registry.get(tool_name)
    if tool:
        return tool
    
    # 回退到旧字典
    return sandbox_tool_dict.get(tool_name)


def register_sandbox_tools_to_unified():
    """将旧的 sandbox 工具注册到统一框架"""
    from derisk.agent.tools.builtin.sandbox import register_sandbox_tools
    register_sandbox_tools(tool_registry)
    _sync_from_unified_registry()
    logger.info(f"[兼容层] 已注册 {len(sandbox_tool_dict)} 个 sandbox 工具")


# 初始化时同步
def _init():
    """初始化兼容层"""
    try:
        _sync_from_unified_registry()
    except Exception as e:
        logger.debug(f"[兼容层] 初始化同步失败（可能统一注册表尚未初始化）: {e}")


_init()


__all__ = [
    "sandbox_tool",
    "sandbox_tool_dict",
    "DERISK_TOOL_IDENTIFIER",
    "get_sandbox_tool",
    "register_sandbox_tools_to_unified",
]