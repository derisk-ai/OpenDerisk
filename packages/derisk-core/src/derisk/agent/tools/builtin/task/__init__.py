"""
TaskTool - 子Agent调用工具 - 已迁移到统一工具框架

参考 OpenCode 的 Task 工具设计，实现简洁的子Agent调用模式

使用方式：
1. LLM通过 tool_call 调用 task 工具
2. 指定 subagent_name 和 task
3. 可选择同步或异步执行
"""

from typing import Any, Dict, List, Optional
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


class TaskTool(ToolBase):
    """
    Task工具 - 委派任务给子Agent - 已迁移

    这是LLM调用子Agent的主要入口。

    参考 OpenCode 的 Task tool:
    - subagent: 子Agent名称
    - prompt: 任务描述
    - thoroughness: 搜索彻底程度 (quick/medium/thorough)
    """

    def __init__(
        self,
        subagent_manager: Optional[Any] = None,
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
            display_name="Delegate Task",
            description=(
                "启动一个子Agent来完成复杂任务。"
                "用于研究复杂问题、执行多步骤任务或搜索代码库。"
            ),
            category=ToolCategory.API,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            tags=["agent", "task", "delegate", "subagent"],
            timeout=300,
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subagent": {
                    "type": "string",
                    "description": "要使用的子Agent名称",
                    "enum": [
                        "general",
                        "explore",
                        "code-reviewer",
                        "librarian",
                        "oracle",
                    ],
                },
                "prompt": {
                    "type": "string",
                    "description": "要完成的任务描述。请提供清晰、具体的任务说明。",
                },
                "thoroughness": {
                    "type": "string",
                    "description": "执行彻底程度",
                    "enum": ["quick", "medium", "thorough"],
                    "default": "medium",
                },
            },
            "required": ["subagent", "prompt"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        subagent_name = args.get("subagent", "general")
        prompt = args.get("prompt", "")
        thoroughness = args.get("thoroughness", "medium")

        if not prompt:
            return ToolResult(
                success=False, output="", error="任务描述不能为空", tool_name=self.name
            )

        try:
            if self._on_delegate_start:
                self._on_delegate_start(subagent_name, prompt)

            if self._manager:
                result = await self._manager.delegate(
                    subagent_name=subagent_name,
                    prompt=prompt,
                    parent_session_id=self._parent_session_id,
                    thoroughness=thoroughness,
                )

                if self._on_delegate_complete:
                    self._on_delegate_complete(subagent_name, result)

                return ToolResult(
                    success=True,
                    output=result.get("output", ""),
                    tool_name=self.name,
                    metadata={
                        "subagent": subagent_name,
                        "thoroughness": thoroughness,
                    },
                )
            else:
                result = f"[Task Delegation]\nSubagent: {subagent_name}\nPrompt: {prompt}\nThoroughness: {thoroughness}"

                if self._on_delegate_complete:
                    self._on_delegate_complete(subagent_name, {"output": result})

                return ToolResult(
                    success=True,
                    output=result,
                    tool_name=self.name,
                    metadata={
                        "subagent": subagent_name,
                        "thoroughness": thoroughness,
                    },
                )

        except Exception as e:
            logger.error(f"[TaskTool] 任务委派失败: {e}")
            return ToolResult(
                success=False, output="", error=str(e), tool_name=self.name
            )


def register_task_tools(registry, subagent_manager: Optional[Any] = None) -> None:
    """注册 Task 工具"""
    registry.register(TaskTool(subagent_manager=subagent_manager))
    logger.info("[TaskTools] Task 工具已注册到统一框架")


__all__ = [
    "TaskTool",
    "register_task_tools",
]
