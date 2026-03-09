"""
Tool Framework Integration - 工具框架集成指南

本模块实现工具框架与应用编辑的完整集成：
1. 工具注册与初始化
2. 工具资源与应用绑定
3. 运行时工具加载
4. 权限验证

使用方法:
    from derisk.agent.tools.integration import (
        initialize_tools_on_startup,
        bind_tools_to_app,
        get_app_runtime_tools,
        ToolIntegrationManager,
    )

    # 启动时初始化
    await initialize_tools_on_startup()

    # 绑定工具到应用
    await bind_tools_to_app(app_id="my_app", tool_ids=["read", "write", "bash"])

    # 获取应用运行时工具
    tools = await get_app_runtime_tools(app_id="my_app", agent_name="default")
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from derisk.agent.tools.registry import tool_registry, register_builtin_tools
from derisk.agent.tools.tool_manager import tool_manager, ToolBindingConfig, ToolBindingType
from derisk.agent.tools.resource_manager import tool_resource_manager

logger = logging.getLogger(__name__)


class ToolIntegrationManager:
    """
    工具集成管理器

    负责工具框架与应用系统的完整集成：
    - 工具初始化
    - 资源绑定
    - 运行时加载
    - 持久化管理
    """

    _instance: Optional["ToolIntegrationManager"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "ToolIntegrationManager":
        return cls()

    async def initialize(self):
        """初始化工具框架"""
        if self._initialized:
            return

        logger.info("[ToolIntegration] Initializing tool framework...")

        # 1. 注册内置工具
        register_builtin_tools()
        logger.info(f"[ToolIntegration] Registered {len(tool_registry)} built-in tools")

        # 2. 设置持久化回调
        tool_manager.set_persist_callback(self._persist_tool_config)

        self._initialized = True
        logger.info("[ToolIntegration] Tool framework initialized successfully")

    async def bind_tools_to_app(
        self,
        app_id: str,
        agent_name: str,
        tool_ids: List[str],
        binding_type: ToolBindingType = ToolBindingType.CUSTOM,
    ) -> Dict[str, Any]:
        """
        绑定工具到应用

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            tool_ids: 工具ID列表
            binding_type: 绑定类型

        Returns:
            绑定结果
        """
        results = []
        success_count = 0

        for tool_id in tool_ids:
            try:
                success = tool_manager.update_tool_binding(
                    app_id=app_id,
                    agent_name=agent_name,
                    tool_id=tool_id,
                    is_bound=True,
                )
                results.append({"tool_id": tool_id, "success": success})
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"[ToolIntegration] Failed to bind tool {tool_id}: {e}")
                results.append({"tool_id": tool_id, "success": False, "error": str(e)})

        return {
            "success": success_count == len(tool_ids),
            "results": results,
            "total": len(tool_ids),
            "success_count": success_count,
        }

    async def unbind_tools_from_app(
        self,
        app_id: str,
        agent_name: str,
        tool_ids: List[str],
    ) -> Dict[str, Any]:
        """
        从应用解绑工具

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            tool_ids: 工具ID列表

        Returns:
            解绑结果
        """
        results = []
        success_count = 0

        for tool_id in tool_ids:
            try:
                success = tool_manager.update_tool_binding(
                    app_id=app_id,
                    agent_name=agent_name,
                    tool_id=tool_id,
                    is_bound=False,
                )
                results.append({"tool_id": tool_id, "success": success})
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"[ToolIntegration] Failed to unbind tool {tool_id}: {e}")
                results.append({"tool_id": tool_id, "success": False, "error": str(e)})

        return {
            "success": success_count == len(tool_ids),
            "results": results,
            "total": len(tool_ids),
            "success_count": success_count,
        }

    async def get_app_tools(
        self,
        app_id: str,
        agent_name: str,
        include_unbound: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        获取应用的工具列表

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            include_unbound: 是否包含未绑定的工具

        Returns:
            工具列表
        """
        groups = tool_manager.get_tool_groups(app_id, agent_name)

        tools = []
        for group in groups:
            for tool in group.tools:
                if include_unbound or tool.get("is_bound", False):
                    tools.append(tool)

        return tools

    async def get_runtime_tools(
        self,
        app_id: str,
        agent_name: str,
        format_type: str = "openai",
    ) -> List[Dict[str, Any]]:
        """
        获取应用运行时工具

        Args:
            app_id: 应用ID
            agent_name: Agent名称
            format_type: 格式类型

        Returns:
            运行时工具列表
        """
        return tool_manager.get_runtime_tool_schemas(app_id, agent_name, format_type)

    def _persist_tool_config(self, config) -> bool:
        """
        持久化工具配置

        这里应该将配置保存到数据库
        目前先保存到内存缓存
        """
        try:
            # TODO: 实现数据库存储
            # from derisk_serve.agent.db.gpts_plans_db import save_tool_config
            # await save_tool_config(config)

            logger.debug(
                f"[ToolIntegration] Persisted tool config for {config.app_id}:{config.agent_name}"
            )
            return True
        except Exception as e:
            logger.error(f"[ToolIntegration] Failed to persist tool config: {e}")
            return False


# 全局实例
tool_integration_manager = ToolIntegrationManager()


async def initialize_tools_on_startup():
    """启动时初始化工具框架"""
    await tool_integration_manager.initialize()


async def bind_tools_to_app(
    app_id: str,
    agent_name: str,
    tool_ids: List[str],
) -> Dict[str, Any]:
    """绑定工具到应用"""
    return await tool_integration_manager.bind_tools_to_app(app_id, agent_name, tool_ids)


async def unbind_tools_from_app(
    app_id: str,
    agent_name: str,
    tool_ids: List[str],
) -> Dict[str, Any]:
    """从应用解绑工具"""
    return await tool_integration_manager.unbind_tools_from_app(app_id, agent_name, tool_ids)


async def get_app_runtime_tools(
    app_id: str,
    agent_name: str,
    format_type: str = "openai",
) -> List[Dict[str, Any]]:
    """获取应用运行时工具"""
    return await tool_integration_manager.get_runtime_tools(app_id, agent_name, format_type)


__all__ = [
    "ToolIntegrationManager",
    "tool_integration_manager",
    "initialize_tools_on_startup",
    "bind_tools_to_app",
    "unbind_tools_from_app",
    "get_app_runtime_tools",
]
