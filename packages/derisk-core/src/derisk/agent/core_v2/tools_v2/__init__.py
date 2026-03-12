"""
工具系统 V2 - 兼容层重定向

此模块已迁移到统一工具框架 `derisk.agent.tools`。

旧的导入路径:
    from derisk.agent.core_v2.tools_v2 import ToolBase, ReadTool, ...

新的导入路径 (推荐):
    from derisk.agent.tools import ToolBase, tool_registry, ...
    from derisk.agent.tools.builtin import ReadTool, WriteTool, ...

此文件仅作为向后兼容层存在，新代码请使用统一框架。
"""

import warnings

warnings.warn(
    "derisk.agent.core_v2.tools_v2 已迁移到 derisk.agent.tools，"
    "此兼容层将在未来版本移除",
    DeprecationWarning,
    stacklevel=2,
)

# 从统一框架重新导出核心类
from derisk.agent.tools.base import (
    ToolBase,
    ToolCategory,
    ToolRiskLevel,
    ToolSource,
)

from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import ToolResult
from derisk.agent.tools.registry import (
    ToolRegistry,
    tool_registry,
    register_builtin_tools,
)

from derisk.agent.tools.decorators import tool

# 从内置工具模块导入具体工具
from derisk.agent.tools.builtin.file_system.read import ReadTool
from derisk.agent.tools.builtin.file_system.write import WriteTool
from derisk.agent.tools.builtin.file_system.edit import EditTool
from derisk.agent.tools.builtin.file_system.glob import GlobTool
from derisk.agent.tools.builtin.file_system.grep import GrepTool
from derisk.agent.tools.builtin.file_system.list_files import ListFilesTool
from derisk.agent.tools.builtin.file_system.search import SearchTool
from derisk.agent.tools.builtin.shell.bash import BashTool
from derisk.agent.tools.builtin.network import WebFetchTool, WebSearchTool
from derisk.agent.tools.builtin.interaction import (
    QuestionTool,
    ConfirmTool,
    NotifyTool,
    ProgressTool,
    FileSelectTool,
    register_interaction_tools,
)
from derisk.agent.tools.builtin.reasoning import ThinkTool
from derisk.agent.tools.builtin.analysis import (
    AnalyzeDataTool,
    AnalyzeLogTool,
    AnalyzeCodeTool,
    ShowChartTool,
    ShowTableTool,
    ShowMarkdownTool,
    GenerateReportTool,
    register_analysis_tools,
)
from derisk.agent.tools.builtin.mcp import (
    MCPToolAdapter,
    MCPToolRegistry,
    register_mcp_tools,
)
from derisk.agent.tools.builtin.action import (
    ActionToolAdapter,
    action_to_tool,
    register_action_tools,
)
from derisk.agent.tools.builtin.task import (
    TaskTool,
    register_task_tools,
)

# 兼容旧版名称
APICallTool = WebFetchTool  # 别名
GraphQLTool = WebFetchTool  # 别名
register_network_tools = register_builtin_tools  # 别名


# 兼容旧版 Action 相关
class ActionToolRegistry:
    """兼容旧版 ActionToolRegistry"""

    pass


class ActionTypeMapper:
    """兼容旧版 ActionTypeMapper"""

    pass


class MCPConnectionManager:
    """兼容旧版 MCPConnectionManager"""

    pass


default_action_mapper = type(
    "default_action_mapper",
    (),
    {"list_actions": lambda: [], "get_action_class": lambda x: None},
)()


def adapt_mcp_tool(*args, **kwargs):
    """兼容旧版 adapt_mcp_tool"""
    return None


def register_actions_from_module(*args, **kwargs):
    """兼容旧版 register_actions_from_module"""
    pass


def create_action_tools_from_resources(*args, **kwargs):
    """兼容旧版 create_action_tools_from_resources"""
    return []


def TaskToolFactory(*args, **kwargs):
    """兼容旧版 TaskToolFactory"""
    return TaskTool(*args, **kwargs)


def create_task_tool(*args, **kwargs):
    """兼容旧版 create_task_tool"""
    return TaskTool(*args, **kwargs)


def register_task_tool(*args, **kwargs):
    """兼容旧版 register_task_tool"""
    return register_task_tools(*args, **kwargs)


mcp_connection_manager = None  # 兼容旧版


def register_all_tools(
    registry=None,
    interaction_manager=None,
    progress_broadcaster=None,
    http_client=None,
    search_config=None,
):
    """注册所有工具到注册表"""
    if registry is None:
        registry = tool_registry

    register_builtin_tools(registry)
    register_interaction_tools(registry)
    register_analysis_tools(registry)

    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"[Tools] 已注册所有工具，共 {len(registry.list_names())} 个")

    return registry


def create_default_tool_registry():
    """创建带有所有默认工具的注册表"""
    return register_all_tools()


__all__ = [
    "ToolMetadata",
    "ToolResult",
    "ToolBase",
    "ToolRegistry",
    "tool",
    "BashTool",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
    "SearchTool",
    "ListFilesTool",
    "ThinkTool",
    "register_builtin_tools",
    "QuestionTool",
    "ConfirmTool",
    "NotifyTool",
    "ProgressTool",
    "FileSelectTool",
    "register_interaction_tools",
    "WebFetchTool",
    "WebSearchTool",
    "APICallTool",
    "GraphQLTool",
    "register_network_tools",
    "MCPToolAdapter",
    "MCPToolRegistry",
    "MCPConnectionManager",
    "adapt_mcp_tool",
    "register_mcp_tools",
    "mcp_connection_manager",
    "ActionToolAdapter",
    "ActionToolRegistry",
    "action_to_tool",
    "register_actions_from_module",
    "create_action_tools_from_resources",
    "ActionTypeMapper",
    "default_action_mapper",
    "AnalyzeDataTool",
    "AnalyzeLogTool",
    "AnalyzeCodeTool",
    "ShowChartTool",
    "ShowTableTool",
    "ShowMarkdownTool",
    "GenerateReportTool",
    "register_analysis_tools",
    "register_all_tools",
    "create_default_tool_registry",
    "TaskTool",
    "TaskToolFactory",
    "create_task_tool",
    "register_task_tool",
]
