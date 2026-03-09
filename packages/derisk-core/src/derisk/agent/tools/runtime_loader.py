"""
Agent Runtime Tool Loader - Agent 运行时工具加载器

支持根据 Agent 配置加载工具，包括排除被反向解绑的内置工具
"""

from typing import Dict, Any, Optional, List
import logging

from .tool_manager import tool_manager, ToolBindingType
from .registry import tool_registry
from .base import ToolSource

logger = logging.getLogger(__name__)


class AgentRuntimeToolLoader:
    """
    Agent 运行时工具加载器

    职责：
    1. 根据 Agent 配置加载启用的工具
    2. 支持排除被解绑的工具
    3. 支持运行时动态工具切换
    """

    def __init__(
        self,
        app_id: str,
        agent_name: str,
        default_tools: Optional[List[str]] = None,
        enable_builtin_tools: bool = True,
    ):
        """
        初始化工具加载器

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            default_tools: 默认工具列表（如果没有配置）
            enable_builtin_tools: 是否启用内置工具
        """
        self.app_id = app_id
        self.agent_name = agent_name
        self.default_tools = default_tools or []
        self.enable_builtin_tools = enable_builtin_tools

        self._cached_tools: Optional[Dict[str, Any]] = None
        self._cache_valid = False

    async def load_tools(self, format_type: str = "openai") -> Dict[str, Any]:
        """
        加载工具

        Args:
            format_type: 格式类型 (openai/anthropic/raw)

        Returns:
            工具配置字典
        """
        # 使用缓存
        if self._cache_valid and self._cached_tools:
            return self._cached_tools

        # 获取运行时工具
        tools = tool_manager.get_runtime_tools(
            app_id=self.app_id, agent_name=self.agent_name
        )

        # 如果没有配置，使用默认工具
        if not tools and self.default_tools:
            tools = self._load_default_tools()

        # 转换格式
        if format_type == "openai":
            tool_schemas = [tool.to_openai_tool() for tool in tools]
        elif format_type == "anthropic":
            tool_schemas = [tool.to_anthropic_tool() for tool in tools]
        else:
            tool_schemas = [tool.metadata.model_dump() for tool in tools]

        result = {
            "tools": tools,
            "schemas": tool_schemas,
            "tool_map": {tool.metadata.name: tool for tool in tools},
            "count": len(tools),
        }

        # 缓存结果
        self._cached_tools = result
        self._cache_valid = True

        logger.info(
            f"[AgentRuntimeToolLoader] Loaded {len(tools)} tools for "
            f"{self.app_id}:{self.agent_name}"
        )

        return result

    def _load_default_tools(self) -> List[Any]:
        """加载默认工具"""
        tools = []
        for tool_id in self.default_tools:
            tool = tool_registry.get(tool_id)
            if tool:
                tools.append(tool)
        return tools

    def is_tool_enabled(self, tool_id: str) -> bool:
        """检查工具是否启用"""
        config = tool_manager.get_agent_config(
            self.app_id, self.agent_name, create_if_missing=True
        )
        if config:
            return config.is_tool_enabled(tool_id)
        return tool_id in self.default_tools

    def invalidate_cache(self):
        """使缓存失效"""
        self._cache_valid = False
        self._cached_tools = None
        logger.debug(
            f"[AgentRuntimeToolLoader] Cache invalidated for {self.app_id}:{self.agent_name}"
        )

    def get_enabled_tool_ids(self) -> List[str]:
        """获取启用的工具ID列表"""
        config = tool_manager.get_agent_config(
            self.app_id, self.agent_name, create_if_missing=True
        )
        if config:
            return config.get_enabled_tools()
        return self.default_tools


async def load_agent_tools(
    app_id: str,
    agent_name: str,
    format_type: str = "openai",
    default_tools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    加载 Agent 工具的快捷函数

    Args:
        app_id: 应用ID
        agent_name: Agent名称
        format_type: 格式类型
        default_tools: 默认工具列表

    Returns:
        工具配置字典
    """
    loader = AgentRuntimeToolLoader(
        app_id=app_id, agent_name=agent_name, default_tools=default_tools
    )
    return await loader.load_tools(format_type)


def is_tool_available_for_agent(app_id: str, agent_name: str, tool_id: str) -> bool:
    """
    检查工具是否对 Agent 可用

    Args:
        app_id: 应用ID
        agent_name: Agent名称
        tool_id: 工具ID

    Returns:
        是否可用
    """
    loader = AgentRuntimeToolLoader(app_id=app_id, agent_name=agent_name)
    return loader.is_tool_enabled(tool_id)
