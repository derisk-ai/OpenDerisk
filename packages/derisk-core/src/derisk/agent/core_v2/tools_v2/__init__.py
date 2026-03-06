"""
工具系统 V2

提供Agent可调用的工具框架

模块结构:
- tool_base: 基础类和注册系统
- builtin_tools: 内置工具 (bash, read, write, search, list_files, think)
- interaction_tools: 用户交互工具 (question, confirm, notify, progress, ask_human, file_select)
- network_tools: 网络工具 (webfetch, web_search, api_call, graphql)
- mcp_tools: MCP协议工具适配器
- action_tools: Action体系迁移适配器
- analysis_tools: 分析可视化工具 (analyze_data, analyze_log, analyze_code, show_chart, show_table, show_markdown, generate_report)
"""

from .tool_base import (
    ToolMetadata,
    ToolResult,
    ToolBase,
    ToolRegistry,
    tool,
)

from .builtin_tools import (
    BashTool,
    ReadTool,
    WriteTool,
    SearchTool,
    ListFilesTool,
    ThinkTool,
    register_builtin_tools,
)

from .interaction_tools import (
    QuestionTool,
    ConfirmTool,
    NotifyTool,
    ProgressTool,
    AskHumanTool,
    FileSelectTool,
    register_interaction_tools,
)

from .network_tools import (
    WebFetchTool,
    WebSearchTool,
    APICallTool,
    GraphQLTool,
    register_network_tools,
)

from .mcp_tools import (
    MCPToolAdapter,
    MCPToolRegistry,
    MCPConnectionManager,
    adapt_mcp_tool,
    register_mcp_tools,
    mcp_connection_manager,
)

from .action_tools import (
    ActionToolAdapter,
    ActionToolRegistry,
    action_to_tool,
    register_actions_from_module,
    create_action_tools_from_resources,
    ActionTypeMapper,
    default_action_mapper,
)

from .analysis_tools import (
    AnalyzeDataTool,
    AnalyzeLogTool,
    AnalyzeCodeTool,
    ShowChartTool,
    ShowTableTool,
    ShowMarkdownTool,
    GenerateReportTool,
    register_analysis_tools,
)

from .task_tools import (
    TaskTool,
    TaskToolFactory,
    create_task_tool,
    register_task_tool,
)


def register_all_tools(
    registry: ToolRegistry = None,
    interaction_manager: any = None,
    progress_broadcaster: any = None,
    http_client: any = None,
    search_config: dict = None,
) -> ToolRegistry:
    """
    注册所有工具到注册表
    
    Args:
        registry: 工具注册表（可选，默认创建新的）
        interaction_manager: 用户交互管理器
        progress_broadcaster: 进度广播器
        http_client: HTTP客户端
        search_config: 搜索配置
        
    Returns:
        ToolRegistry: 工具注册表
    """
    if registry is None:
        registry = ToolRegistry()
    
    register_builtin_tools(registry)
    
    register_interaction_tools(
        registry,
        interaction_manager=interaction_manager,
        progress_broadcaster=progress_broadcaster
    )
    
    register_network_tools(
        registry,
        http_client=http_client,
        search_config=search_config
    )
    
    register_analysis_tools(registry)
    
    from .action_tools import default_action_mapper
    for action_name in default_action_mapper.list_actions():
        action_class = default_action_mapper.get_action_class(action_name)
        if action_class:
            adapter = action_to_tool(action_class, name=action_name)
            registry.register(adapter)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[Tools] 已注册所有工具，共 {len(registry.list_names())} 个")
    
    return registry


def create_default_tool_registry() -> ToolRegistry:
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
    "SearchTool",
    "ListFilesTool",
    "ThinkTool",
    "register_builtin_tools",
    "QuestionTool",
    "ConfirmTool",
    "NotifyTool",
    "ProgressTool",
    "AskHumanTool",
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
    # Task Tool - Subagent Delegation
    "TaskTool",
    "TaskToolFactory",
    "create_task_tool",
    "register_task_tool",
]