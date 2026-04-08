"""
Sandbox 工具基类

提供沙箱工具的通用功能：
- 从 context 获取 SandboxClient
- 统一的错误处理
- 路径规范化
"""

from typing import Dict, Any, Optional
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolEnvironment
from ...metadata import ToolMetadata
from ...context import ToolContext
from ...result import ToolResult

logger = logging.getLogger(__name__)


class SandboxToolBase(ToolBase):
    """
    沙箱工具基类

    所有沙箱工具的父类，提供沙箱客户端获取等通用功能
    """

    def _get_sandbox_client(self, context: Optional[ToolContext]) -> Any:
        """
        从上下文获取沙箱客户端

        Args:
            context: 工具上下文（可以是 ToolContext 或普通字典）

        Returns:
            SandboxBase: 沙箱客户端实例

        Raises:
            ValueError: 如果沙箱客户端不可用
        """
        if context is None:
            return None

        # 支持普通字典类型的 context
        if isinstance(context, dict):
            sandbox_manager = context.get("sandbox_manager")
            if sandbox_manager is not None:
                if hasattr(sandbox_manager, "client"):
                    return sandbox_manager.client
                if hasattr(sandbox_manager, "get_client"):
                    return sandbox_manager.get_client()
            # 尝试直接获取 sandbox_client
            client = context.get("sandbox_client")
            if client is not None:
                return client
            # 尝试从 config 中获取
            config = context.get("config", {})
            sandbox_manager = config.get("sandbox_manager")
            if sandbox_manager is not None:
                if hasattr(sandbox_manager, "client"):
                    return sandbox_manager.client
                if hasattr(sandbox_manager, "get_client"):
                    return sandbox_manager.get_client()
            return None

        # 尝试从 context 的 config 中获取
        client = context.config.get("sandbox_client")
        if client is not None:
            return client

        # 尝试从资源中获取
        client = context.get_resource("sandbox_client")
        if client is not None:
            return client

        # 尝试从 sandbox_manager 获取
        sandbox_manager = context.config.get("sandbox_manager")
        if sandbox_manager is not None:
            if hasattr(sandbox_manager, "client"):
                return sandbox_manager.client
            if hasattr(sandbox_manager, "get_client"):
                return sandbox_manager.get_client()

        return None

    def _check_sandbox_available(self, context: Optional[ToolContext]) -> Optional[str]:
        """
        检查沙箱是否可用

        Returns:
            Optional[str]: 错误信息，None 表示可用
        """
        client = self._get_sandbox_client(context)
        if client is None:
            return f"错误: 当前任务未初始化沙箱环境，无法使用 {self.name}"
        return None

    def _get_conversation_id(self, context: Optional[ToolContext]) -> str:
        """获取会话ID"""
        if context is None:
            return "default"

        # 支持普通字典类型的 context
        if isinstance(context, dict):
            return context.get("conversation_id") or "default"

        # 支持 ToolContext 对象
        if hasattr(context, "conversation_id") and context.conversation_id:
            return context.conversation_id

        return "default"
