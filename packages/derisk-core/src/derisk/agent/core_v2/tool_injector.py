"""
ToolInjector - 场景工具动态注入器

实现场景工具的动态注入和清理机制
支持工具的阶段化管理

设计原则:
- 按需注入：仅在场景激活时注入场景工具
- 自动清理：场景切换或退出时清理场景工具
- 作用域隔离：不同场景的工具互不影响
"""

from typing import Dict, List, Any, Optional, Set
import logging

from .tools_v2 import ToolRegistry

logger = logging.getLogger(__name__)


class ToolInjector:
    """
    工具注入器

    管理场景工具的生命周期：
    1. 场景激活时注入场景工具
    2. 场景切换时清理旧工具、注入新工具
    3. 场景退出时清理场景工具
    """

    def __init__(self, tool_registry: ToolRegistry):
        """
        初始化工具注入器

        Args:
            tool_registry: 工具注册表
        """
        self.tool_registry = tool_registry
        self._injected_tools: Dict[
            str, Set[str]
        ] = {}  # session_id -> set of tool_names
        self._global_tools: Set[str] = set()  # 全局工具

        logger.info("[ToolInjector] Initialized")

    def register_global_tools(self, tool_names: List[str]) -> None:
        """
        注册全局工具

        Args:
            tool_names: 工具名称列表
        """
        self._global_tools.update(tool_names)
        logger.info(f"[ToolInjector] Registered global tools: {tool_names}")

    async def inject_scene_tools(
        self, session_id: str, tool_names: List[str], agent: Any = None
    ) -> int:
        """
        注入场景工具

        Args:
            session_id: 会话 ID
            tool_names: 要注入的工具名称列表
            agent: Agent 实例（可选）

        Returns:
            成功注入的工具数量
        """
        if session_id not in self._injected_tools:
            self._injected_tools[session_id] = set()

        injected_count = 0

        for tool_name in tool_names:
            # 跳过已注入的工具
            if tool_name in self._injected_tools[session_id]:
                continue

            # 跳过全局工具
            if tool_name in self._global_tools:
                continue

            try:
                # 检查工具是否存在于注册表中
                if self._check_tool_exists(tool_name):
                    self._injected_tools[session_id].add(tool_name)
                    injected_count += 1
                    logger.debug(
                        f"[ToolInjector] Injected tool: {tool_name} for session {session_id}"
                    )
                else:
                    # 工具不存在，动态注册占位工具
                    await self._register_placeholder_tool(tool_name, agent)
                    self._injected_tools[session_id].add(tool_name)
                    injected_count += 1
                    logger.info(
                        f"[ToolInjector] Registered placeholder tool: {tool_name}"
                    )
            except Exception as e:
                logger.warning(f"[ToolInjector] Failed to inject tool {tool_name}: {e}")

        logger.info(
            f"[ToolInjector] Injected {injected_count} tools for session {session_id}, "
            f"total={len(self._injected_tools[session_id])}"
        )

        return injected_count

    async def cleanup_scene_tools(
        self, session_id: str, keep_global: bool = True
    ) -> int:
        """
        清理场景工具

        Args:
            session_id: 会话 ID
            keep_global: 是否保留全局工具

        Returns:
            清理的工具数量
        """
        if session_id not in self._injected_tools:
            return 0

        # 获取要清理的工具
        tools_to_cleanup = self._injected_tools[session_id].copy()

        # 移除全局工具
        if keep_global:
            tools_to_cleanup -= self._global_tools

        # 清理工具
        cleanup_count = len(tools_to_cleanup)
        self._injected_tools[session_id] -= tools_to_cleanup

        logger.info(
            f"[ToolInjector] Cleaned up {cleanup_count} tools for session {session_id}, "
            f"remaining={len(self._injected_tools[session_id])}"
        )

        return cleanup_count

    def _check_tool_exists(self, tool_name: str) -> bool:
        """检查工具是否存在于注册表中"""
        # 在实际实现中，这里应该检查 ToolRegistry
        # 当前简化实现：假设所有基础工具都存在
        basic_tools = {
            "read",
            "write",
            "edit",
            "grep",
            "glob",
            "bash",
            "webfetch",
            "think",
            "search",
        }
        return tool_name in basic_tools

    async def _register_placeholder_tool(self, tool_name: str, agent: Any) -> None:
        """
        注册占位工具

        Args:
            tool_name: 工具名称
            agent: Agent 实例
        """

        # 创建简单的占位工具
        async def placeholder_func(**kwargs):
            return f"Tool {tool_name} is a placeholder. Not implemented yet."

        # 注册到工具注册表
        if agent and hasattr(agent, "tools"):
            agent.tools.register_function(
                name=tool_name,
                description=f"Placeholder tool: {tool_name}",
                func=placeholder_func,
                parameters={},
            )

    def get_injected_tools(self, session_id: str) -> Set[str]:
        """获取已注入的工具列表"""
        return self._injected_tools.get(session_id, set()).copy()

    def clear_session(self, session_id: str) -> None:
        """清理会话的所有工具"""
        if session_id in self._injected_tools:
            del self._injected_tools[session_id]
            logger.info(f"[ToolInjector] Cleared all tools for session {session_id}")


# ==================== 导出 ====================

__all__ = [
    "ToolInjector",
]
