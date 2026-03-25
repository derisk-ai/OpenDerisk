"""
异步任务 Tools - LLM 可调用的异步任务管理工具

提供 4 个 Tool 让主 Agent 在 ReAct 循环中管理后台子 Agent 任务：
1. spawn_agent_task - 启动后台 Agent 任务
2. check_tasks - 查看任务状态
3. wait_tasks - 等待任务完成
4. cancel_task - 取消任务

@see docs/ASYNC_TASK_SYSTEM.md
"""

from typing import Any, Dict, Optional
import logging

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext

logger = logging.getLogger(__name__)


# ==================== Tool Prompts ====================


_SPAWN_PROMPT = """启动一个后台 Agent 任务。任务会在后台异步执行，你可以继续处理其他工作，稍后用 check_tasks 或 wait_tasks 获取结果。

使用场景：
- 需要多个独立子任务并行执行时
- 某个任务耗时较长，不想阻塞当前工作时
- 需要不同专业 Agent 分别处理不同子目标时

注意：
- 提交后立即返回 task_id，不会等待任务完成
- 可以一次提交多个任务实现并行执行
- 通过 depend_on 参数可以设置任务依赖关系"""

_CHECK_PROMPT = """查看后台任务的当前状态，不阻塞。

可以查看所有任务或指定任务的状态、进度、结果预览等信息。"""

_WAIT_PROMPT = """等待后台任务完成并获取完整结果。

两种模式：
- 指定 task_ids: 等待这些任务全部完成后返回结果
- 不指定 task_ids: 等待任意一个任务完成后返回结果

适用于需要子任务结果才能继续的场景。"""

_CANCEL_PROMPT = """取消一个正在执行或等待中的后台任务。"""


# ==================== Tool 1: spawn_agent_task ====================


class SpawnAgentTaskTool(ToolBase):
    """启动后台 Agent 异步任务"""

    def __init__(self, async_task_manager: Optional[Any] = None):
        self._manager = async_task_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="spawn_agent_task",
            display_name="Spawn Agent Task",
            description=_SPAWN_PROMPT,
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=30,
            tags=["agent", "async", "task", "parallel", "background"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "目标子 Agent 的名称，必须为系统中已注册的 Agent。",
                },
                "task": {
                    "type": "string",
                    "description": "需要完成的任务描述。请提供清晰、具体的任务说明。",
                },
                "context": {
                    "type": "object",
                    "description": "传递给子 Agent 的额外上下文信息（可选）。",
                    "default": {},
                },
                "timeout": {
                    "type": "integer",
                    "description": "任务超时秒数（可选，默认 300 秒）。",
                    "default": 300,
                    "minimum": 10,
                    "maximum": 3600,
                },
                "depend_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "依赖的 task_id 列表。这些任务完成后才会开始执行当前任务（可选）。",
                    "default": [],
                },
            },
            "required": ["agent_name", "task"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        agent_name = args.get("agent_name", "")
        task = args.get("task", "")

        if not agent_name:
            return ToolResult.fail(
                error="agent_name 不能为空",
                tool_name=self.name,
            )
        if not task:
            return ToolResult.fail(
                error="task 描述不能为空",
                tool_name=self.name,
            )

        # 获取 AsyncTaskManager
        manager = self._manager
        if not manager and context:
            manager = (
                context.get_resource("async_task_manager")
                if hasattr(context, "get_resource")
                else None
            )

        if not manager:
            return ToolResult.fail(
                error="异步任务管理器不可用。当前环境未启用异步任务功能。",
                tool_name=self.name,
            )

        try:
            from ....core_v2.async_task_manager import AsyncTaskSpec

            spec = AsyncTaskSpec(
                agent_name=agent_name,
                task_description=task,
                context=args.get("context", {}),
                timeout=args.get("timeout", 300),
                depend_on=args.get("depend_on", []),
            )

            task_id = await manager.spawn(spec)

            deps_info = ""
            if spec.depend_on:
                deps_info = f"\n依赖: {', '.join(spec.depend_on)}（等待依赖完成后自动开始）"

            output = (
                f"任务已提交到后台执行。\n"
                f"- Task ID: {task_id}\n"
                f"- Agent: {agent_name}\n"
                f"- 描述: {task[:100]}\n"
                f"- 超时: {spec.timeout}s"
                f"{deps_info}\n\n"
                f"你可以继续其他工作，稍后用 check_tasks 查看状态或 wait_tasks 获取结果。"
            )

            return ToolResult.ok(
                output=output,
                tool_name=self.name,
                metadata={"task_id": task_id, "agent_name": agent_name},
            )

        except Exception as e:
            logger.error(f"[SpawnAgentTaskTool] 提交任务失败: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)


# ==================== Tool 2: check_tasks ====================


class CheckTasksTool(ToolBase):
    """查看后台任务状态"""

    def __init__(self, async_task_manager: Optional[Any] = None):
        self._manager = async_task_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="check_tasks",
            display_name="Check Tasks",
            description=_CHECK_PROMPT,
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.SAFE,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=10,
            tags=["agent", "async", "task", "status"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要查询的 task_id 列表。为空则查询所有任务。",
                    "default": [],
                },
            },
            "required": [],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        manager = self._manager
        if not manager and context:
            manager = (
                context.get_resource("async_task_manager")
                if hasattr(context, "get_resource")
                else None
            )

        if not manager:
            return ToolResult.fail(
                error="异步任务管理器不可用",
                tool_name=self.name,
            )

        try:
            task_ids = args.get("task_ids", []) or None
            output = manager.format_status_table(task_ids)
            return ToolResult.ok(output=output, tool_name=self.name)

        except Exception as e:
            logger.error(f"[CheckTasksTool] 查询失败: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)


# ==================== Tool 3: wait_tasks ====================


class WaitTasksTool(ToolBase):
    """等待后台任务完成"""

    def __init__(self, async_task_manager: Optional[Any] = None):
        self._manager = async_task_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="wait_tasks",
            display_name="Wait Tasks",
            description=_WAIT_PROMPT,
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=600,
            tags=["agent", "async", "task", "wait", "blocking"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "等待的 task_id 列表。为空则等待任意一个任务完成。",
                    "default": [],
                },
                "timeout": {
                    "type": "integer",
                    "description": "最大等待秒数（默认 60）。",
                    "default": 60,
                    "minimum": 5,
                    "maximum": 600,
                },
            },
            "required": [],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        manager = self._manager
        if not manager and context:
            manager = (
                context.get_resource("async_task_manager")
                if hasattr(context, "get_resource")
                else None
            )

        if not manager:
            return ToolResult.fail(
                error="异步任务管理器不可用",
                tool_name=self.name,
            )

        try:
            task_ids = args.get("task_ids", [])
            timeout = args.get("timeout", 60)

            if task_ids:
                results = await manager.wait_all(task_ids, timeout=timeout)
            else:
                results = await manager.wait_any(timeout=timeout)

            if not results:
                return ToolResult.ok(
                    output="等待超时，暂无任务完成。你可以继续其他工作后再检查。",
                    tool_name=self.name,
                )

            output = manager.format_results(results)
            return ToolResult.ok(
                output=output,
                tool_name=self.name,
                metadata={
                    "completed_task_ids": [s.spec.task_id for s in results],
                    "total_results": len(results),
                },
            )

        except Exception as e:
            logger.error(f"[WaitTasksTool] 等待失败: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)


# ==================== Tool 4: cancel_task ====================


class CancelTaskTool(ToolBase):
    """取消后台任务"""

    def __init__(self, async_task_manager: Optional[Any] = None):
        self._manager = async_task_manager
        super().__init__()

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="cancel_task",
            display_name="Cancel Task",
            description=_CANCEL_PROMPT,
            category=ToolCategory.UTILITY,
            risk_level=ToolRiskLevel.LOW,
            source=ToolSource.SYSTEM,
            requires_permission=False,
            timeout=10,
            tags=["agent", "async", "task", "cancel"],
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "要取消的任务 ID。",
                },
            },
            "required": ["task_id"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        task_id = args.get("task_id", "")
        if not task_id:
            return ToolResult.fail(
                error="task_id 不能为空",
                tool_name=self.name,
            )

        manager = self._manager
        if not manager and context:
            manager = (
                context.get_resource("async_task_manager")
                if hasattr(context, "get_resource")
                else None
            )

        if not manager:
            return ToolResult.fail(
                error="异步任务管理器不可用",
                tool_name=self.name,
            )

        try:
            success = await manager.cancel(task_id)
            if success:
                return ToolResult.ok(
                    output=f"任务 {task_id} 已取消。",
                    tool_name=self.name,
                )
            else:
                return ToolResult.ok(
                    output=f"无法取消任务 {task_id}（任务可能已完成或不存在）。",
                    tool_name=self.name,
                )

        except Exception as e:
            logger.error(f"[CancelTaskTool] 取消失败: {e}")
            return ToolResult.fail(error=str(e), tool_name=self.name)


__all__ = [
    "SpawnAgentTaskTool",
    "CheckTasksTool",
    "WaitTasksTool",
    "CancelTaskTool",
]
