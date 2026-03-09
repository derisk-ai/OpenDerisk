"""
Action 体系迁移适配器 - 已迁移到统一工具框架

将原有的 Action 体系适配为统一 Tool 体系：
- ActionToolAdapter: Action 到 Tool 的适配器
- action_to_tool: Action 转换工厂函数
"""

from typing import Any, Dict, List, Optional, Type, Union
import logging
import asyncio

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext
from ...registry import ToolRegistry

logger = logging.getLogger(__name__)


class ActionToolAdapter(ToolBase):
    """
    Action 到 Tool 的适配器 - 已迁移
    
    将原有 Action 体系适配为统一 ToolBase 接口
    """
    
    def __init__(
        self,
        action: Any,
        action_name: Optional[str] = None,
        action_description: Optional[str] = None,
        resource: Optional[Any] = None
    ):
        self._action = action
        self._action_name = action_name or getattr(action, "name", action.__class__.__name__)
        self._action_description = action_description or getattr(action, "__doc__", "")
        self._resource = resource
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        description = self._action_description or f"Action: {self._action_name}"
        
        return ToolMetadata(
            name=f"action_{self._action_name.lower()}",
            display_name=f"Action: {self._action_name}",
            description=description,
            category=ToolCategory.API,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.EXTENSION,
            requires_permission=False,
            tags=["action", "adapter"],
            timeout=60,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            if hasattr(self._action, "run"):
                if asyncio.iscoroutinefunction(self._action.run):
                    result = await self._action.run(**args)
                else:
                    result = self._action.run(**args)
            elif hasattr(self._action, "execute"):
                if asyncio.iscoroutinefunction(self._action.execute):
                    result = await self._action.execute(**args)
                else:
                    result = self._action.execute(**args)
            elif callable(self._action):
                result = self._action(**args)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Action 无法执行：缺少执行方法",
                    tool_name=self.name
                )
            
            if isinstance(result, ToolResult):
                return result
            
            return ToolResult(
                success=True,
                output=str(result) if result is not None else "",
                tool_name=self.name,
            )
            
        except Exception as e:
            logger.error(f"[ActionToolAdapter] 执行失败 {self._action_name}: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                tool_name=self.name
            )


def action_to_tool(
    action: Any,
    name: Optional[str] = None,
    description: Optional[str] = None,
    resource: Optional[Any] = None
) -> ActionToolAdapter:
    """
    将 Action 转换为 Tool
    
    Args:
        action: 要转换的 Action 对象
        name: 工具名称（可选）
        description: 工具描述（可选）
        resource: 资源对象（可选）
    
    Returns:
        ActionToolAdapter 实例
    """
    return ActionToolAdapter(
        action=action,
        action_name=name,
        action_description=description,
        resource=resource
    )


def register_action_tools(registry, actions: Optional[List[Any]] = None) -> None:
    """注册 Action 工具"""
    if actions:
        for action in actions:
            adapter = action_to_tool(action)
            registry.register(adapter)
    
    logger.info("[ActionTools] Action 工具注册器已初始化")


__all__ = [
    'ActionToolAdapter',
    'action_to_tool',
    'register_action_tools',
]