"""
TaskTool - 子Agent调用工具

参考 OpenCode 的 Task 工具设计，实现简洁的子Agent调用模式

使用方式：
1. LLM通过 tool_call 调用 task 工具
2. 指定 subagent_name 和 task
3. 可选择同步或异步执行

示例:
```python
# LLM 调用示例
{
    "name": "task",
    "arguments": {
        "subagent": "explore",
        "prompt": "搜索所有包含 'authentication' 的文件",
        "thoroughness": "quick"
    }
}
```
"""

from typing import Any, Dict, List, Optional
import logging

from .tool_base import ToolBase, ToolMetadata, ToolResult
from ..subagent_manager import (
    SubagentManager,
    SubagentInfo,
    SubagentResult,
    TaskPermission,
    subagent_manager,
)

logger = logging.getLogger(__name__)


class TaskTool(ToolBase):
    """
    Task工具 - 委派任务给子Agent
    
    这是LLM调用子Agent的主要入口。
    
    参考 OpenCode 的 Task tool:
    - subagent: 子Agent名称
    - prompt: 任务描述
    - thoroughness: 搜索彻底程度 (quick/medium/thorough)
    """
    
    def __init__(
        self,
        subagent_manager: Optional[SubagentManager] = None,
        parent_session_id: Optional[str] = None,
        on_delegate_start: Optional[callable] = None,
        on_delegate_complete: Optional[callable] = None,
    ):
        super().__init__()
        self._manager = subagent_manager
        self._parent_session_id = parent_session_id or "default"
        self._on_delegate_start = on_delegate_start
        self._on_delegate_complete = on_delegate_complete
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="task",
            description="启动一个子Agent来完成复杂任务。用于研究复杂问题、执行多步骤任务或搜索代码库。",
            parameters={},
            requires_permission=False,
            dangerous=False,
            category="agent",
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subagent": {
                    "type": "string",
                    "description": "要使用的子Agent名称。可用选项: 'general'(通用研究), 'explore'(代码探索), 'code-reviewer'(代码审查)",
                    "enum": ["general", "explore", "code-reviewer"]
                },
                "prompt": {
                    "type": "string",
                    "description": "要完成的任务描述。请提供清晰、具体的任务说明。"
                },
                "thoroughness": {
                    "type": "string",
                    "description": "执行彻底程度。quick(快速), medium(中等), thorough(彻底)",
                    "enum": ["quick", "medium", "thorough"],
                    "default": "medium"
                }
            },
            "required": ["subagent", "prompt"]
        }
    
    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """执行子Agent任务"""
        subagent_name = args.get("subagent")
        prompt = args.get("prompt")
        thoroughness = args.get("thoroughness", "medium")
        
        if not subagent_name:
            return ToolResult(
                success=False,
                output="",
                error="缺少必需参数 'subagent'"
            )
        
        if not prompt:
            return ToolResult(
                success=False,
                output="",
                error="缺少必需参数 'prompt'"
            )
        
        manager = self._manager or self._get_default_manager()
        if not manager:
            return ToolResult(
                success=False,
                output="",
                error="SubagentManager 未配置"
            )
        
        subagent_info = manager.registry.get(subagent_name)
        if not subagent_info:
            available = [a.name for a in manager.get_available_subagents()]
            return ToolResult(
                success=False,
                output="",
                error=f"子Agent '{subagent_name}' 不存在。可用: {', '.join(available)}"
            )
        
        if self._on_delegate_start:
            await self._on_delegate_start(subagent_name, prompt)
        
        logger.info(f"[TaskTool] Delegating to {subagent_name}: {prompt[:100]}...")
        
        timeout = self._get_timeout(thoroughness)
        
        result: SubagentResult = await manager.delegate(
            subagent_name=subagent_name,
            task=prompt,
            parent_session_id=self._parent_session_id,
            context=context,
            timeout=timeout,
            sync=True,
        )
        
        if self._on_delegate_complete:
            await self._on_delegate_complete(subagent_name, prompt, result)
        
        if result.success:
            output = result.to_llm_message()
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "session_id": result.session_id,
                    "subagent_name": subagent_name,
                    "tokens_used": result.tokens_used,
                    "steps_taken": result.steps_taken,
                    "execution_time_ms": result.execution_time_ms,
                }
            )
        else:
            return ToolResult(
                success=False,
                output="",
                error=result.error or "子Agent执行失败"
            )
    
    def _get_default_manager(self) -> Optional[SubagentManager]:
        """获取默认的SubagentManager"""
        return None
    
    def _get_timeout(self, thoroughness: str) -> int:
        """根据彻底程度获取超时时间"""
        timeouts = {
            "quick": 60,
            "medium": 180,
            "thorough": 600,
        }
        return timeouts.get(thoroughness, 180)
    
    def set_parent_session_id(self, session_id: str) -> "TaskTool":
        """设置父会话ID"""
        self._parent_session_id = session_id
        return self
    
    def set_callbacks(
        self,
        on_start: Optional[callable] = None,
        on_complete: Optional[callable] = None,
    ) -> "TaskTool":
        """设置回调函数"""
        self._on_delegate_start = on_start
        self._on_delegate_complete = on_complete
        return self


class TaskToolFactory:
    """
    TaskTool工厂 - 创建配置好的TaskTool实例
    
    @example
    ```python
    factory = TaskToolFactory(subagent_manager=manager)
    
    tool = factory.create(parent_session_id="session-123")
    
    # 注册到工具注册表
    registry.register(tool)
    ```
    """
    
    def __init__(
        self,
        subagent_manager: Optional[SubagentManager] = None,
    ):
        self._manager = subagent_manager
    
    def create(
        self,
        parent_session_id: Optional[str] = None,
        on_delegate_start: Optional[callable] = None,
        on_delegate_complete: Optional[callable] = None,
    ) -> TaskTool:
        """创建TaskTool实例"""
        return TaskTool(
            subagent_manager=self._manager,
            parent_session_id=parent_session_id,
            on_delegate_start=on_delegate_start,
            on_delegate_complete=on_delegate_complete,
        )
    
    def register_to(
        self,
        registry,
        parent_session_id: Optional[str] = None,
    ) -> TaskTool:
        """创建并注册到工具注册表"""
        tool = self.create(parent_session_id=parent_session_id)
        registry.register(tool)
        return tool


def create_task_tool(
    subagent_manager: Optional[SubagentManager] = None,
    parent_session_id: Optional[str] = None,
) -> TaskTool:
    """便捷函数：创建TaskTool"""
    return TaskTool(
        subagent_manager=subagent_manager,
        parent_session_id=parent_session_id,
    )


def register_task_tool(
    registry,
    subagent_manager: Optional[SubagentManager] = None,
    parent_session_id: Optional[str] = None,
) -> TaskTool:
    """便捷函数：创建并注册TaskTool"""
    tool = create_task_tool(subagent_manager, parent_session_id)
    registry.register(tool)
    return tool