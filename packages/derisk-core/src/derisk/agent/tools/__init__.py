"""
DeRisk Agent Tools - 统一工具体系

提供完整的工具框架：
- ToolBase: 统一工具基类
- ToolRegistry: 全局注册表
- ToolMetadata: 元数据定义
- ToolContext: 执行上下文
- ToolResult: 执行结果
- ToolResourceManager: 资源管理器（供前端关联）
- AgentToolAdapter: Agent集成适配器
- LocalToolMigrator: LocalTool迁移器

使用方式：
    from derisk.agent.tools import (
        ToolBase, ToolRegistry, tool,
        ToolCategory, ToolRiskLevel, ToolSource,
        tool_resource_manager, AgentToolAdapter
    )

    # 定义工具
    class MyTool(ToolBase):
        def _define_metadata(self) -> ToolMetadata:
            return ToolMetadata(name="my_tool", ...)

        def _define_parameters(self) -> Dict[str, Any]:
            return {"type": "object", "properties": {...}}

        async def execute(self, args, context) -> ToolResult:
            ...

    # 注册工具
    registry = ToolRegistry()
    registry.register(MyTool())

    # 前端获取工具列表（分类展示）
    groups = tool_resource_manager.get_tools_by_category()

    # Agent集成
    adapter = AgentToolAdapter(agent)
    result = await adapter.execute_tool("read", {"path": "/tmp/file"})
"""

from .base import (
    ToolBase,
    ToolCategory,
    ToolRiskLevel,
    ToolSource,
    ToolEnvironment,
    tool,
    register_tool,
)

from .metadata import (
    ToolMetadata,
    ToolExample,
    ToolDependency,
)

from .context import (
    ToolContext,
    SandboxConfig,
)

from .result import (
    ToolResult,
    Artifact,
    Visualization,
)

from .registry import (
    ToolRegistry,
    ToolFilter,
    tool_registry,
    get_tool,
    register_builtin_tools,
)

from .config import (
    ToolConfig,
    GlobalToolConfig,
    AgentToolConfig,
    UserToolConfig,
)

from .exceptions import (
    ToolError,
    ToolNotFoundError,
    ToolExecutionError,
    ToolValidationError,
    ToolPermissionError,
    ToolTimeoutError,
)

from .resource_manager import (
    ToolResource,
    ToolCategoryGroup,
    ToolResourceManager,
    ToolVisibility,
    ToolStatus,
    tool_resource_manager,
    get_tool_resource_manager,
)

from .agent_adapter import (
    AgentToolAdapter,
    CoreToolAdapter,
    CoreV2ToolAdapter,
    create_tool_adapter_for_agent,
    get_tools_for_agent,
)

from .migration import (
    LocalToolWrapper,
    LocalToolMigrator,
    migrate_local_tools,
    local_tool_migrator,
)

__all__ = [
    # 基类与枚举
    "ToolBase",
    "ToolCategory",
    "ToolRiskLevel",
    "ToolSource",
    "ToolEnvironment",
    # 元数据
    "ToolMetadata",
    "ToolExample",
    "ToolDependency",
    # 上下文
    "ToolContext",
    "SandboxConfig",
    # 结果
    "ToolResult",
    "Artifact",
    "Visualization",
    # 注册表
    "ToolRegistry",
    "ToolFilter",
    "tool_registry",
    "get_tool",
    "register_builtin_tools",
    # 配置
    "ToolConfig",
    "GlobalToolConfig",
    "AgentToolConfig",
    "UserToolConfig",
    # 装饰器
    "tool",
    "register_tool",
    # 异常
    "ToolError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolValidationError",
    "ToolPermissionError",
    "ToolTimeoutError",
    # 资源管理（供前端使用）
    "ToolResource",
    "ToolCategoryGroup",
    "ToolResourceManager",
    "ToolVisibility",
    "ToolStatus",
    "tool_resource_manager",
    "get_tool_resource_manager",
    # Agent集成
    "AgentToolAdapter",
    "CoreToolAdapter",
    "CoreV2ToolAdapter",
    "create_tool_adapter_for_agent",
    "get_tools_for_agent",
    # 迁移
    "LocalToolWrapper",
    "LocalToolMigrator",
    "migrate_local_tools",
    "local_tool_migrator",
]