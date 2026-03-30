"""
V2ContextAdapter - Core V2 上下文适配器

将 SharedSessionContext 集成到 Core V2 (AgentHarness/SimpleAgent) 架构中。

核心职责：
1. 共享组件注入到 AgentHarness
2. 工具输出自动归档钩子
3. 上下文压力处理钩子
4. Todo/Kanban 工具转换为 V2 格式
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from derisk.agent.shared.context import SharedSessionContext

if TYPE_CHECKING:
    from derisk.agent.core_v2.agent_harness import AgentHarness
    from derisk.agent.core_v2.agent_base import AgentBase
    from derisk.agent.tools.base import ToolBase

logger = logging.getLogger(__name__)


class V2ContextAdapter:
    """
    Core V2 上下文适配器

    将 SharedSessionContext 集成到 Core V2 的 AgentHarness。

    使用示例：
        # 创建共享上下文
        shared_ctx = await SharedSessionContext.create(
            session_id="session_001",
            conv_id="conv_001",
        )

        # 创建适配器
        adapter = V2ContextAdapter(shared_ctx)

        # 获取增强的工具集
        tools = await adapter.get_enhanced_tools()

        # 创建 Agent 并集成
        harness = AgentHarness(...)
        await adapter.integrate_with_harness(harness)

    功能：
    - 注册上下文压力钩子
    - 注册工具输出归档钩子
    - 提供 V2 格式的 Todo/Kanban 工具
    - 与 MemoryCompaction 联动
    """

    def __init__(self, shared_context: SharedSessionContext):
        self.shared = shared_context

        self.agent_file_system = shared_context.file_system
        self.task_board = shared_context.task_board
        self.archiver = shared_context.archiver

        self._hooks_registered = False

    @property
    def session_id(self) -> str:
        return self.shared.session_id

    @property
    def conv_id(self) -> str:
        return self.shared.conv_id

    async def integrate_with_harness(
        self,
        harness: "AgentHarness",
        hooks_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._hooks_registered:
            logger.warning("[V2Adapter] Hooks already registered")
            return

        hooks_config = hooks_config or {}

        if hooks_config.get("context_pressure", True) and self.archiver:
            harness.register_hook(
                "on_context_pressure",
                self._handle_context_pressure,
            )

        if hooks_config.get("tool_output_archive", True) and self.archiver:
            harness.register_hook("after_action", self._handle_after_action)

        if hooks_config.get("skill_exit", True) and self.archiver:
            harness.register_hook("on_skill_complete", self._handle_skill_complete)

        harness._shared_context = self.shared
        harness._context_adapter = self

        self._hooks_registered = True

        logger.info(
            f"[V2Adapter] Integrated with harness: "
            f"hooks=✓, task_board={'✓' if self.task_board else '✗'}, "
            f"archiver={'✓' if self.archiver else '✗'}"
        )

    async def integrate_with_agent(
        self,
        agent: "AgentBase",
    ) -> None:
        agent._shared_context = self.shared
        agent._agent_file_system = self.agent_file_system

        if hasattr(agent, "_tools"):
            enhanced_tools = await self.get_enhanced_tools()
            agent._tools.extend(enhanced_tools)

        logger.info(f"[V2Adapter] Integrated with agent")

    async def _handle_context_pressure(
        self,
        context: Any,
        pressure_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.archiver:
            return {"action": "none", "reason": "Archiver not available"}

        pressure_info = pressure_info or {}
        current_tokens = pressure_info.get("current_tokens", 0)
        budget_tokens = pressure_info.get("budget_tokens", 100000)

        archived = await self.archiver.auto_archive_for_pressure(
            current_tokens=current_tokens,
            budget_tokens=budget_tokens,
        )

        logger.info(
            f"[V2Adapter] Context pressure handled: archived {len(archived)} items"
        )

        return {
            "action": "auto_archive",
            "archived_count": len(archived),
            "archives": archived,
        }

    async def _handle_after_action(
        self,
        step_result: Any,
    ) -> Any:
        tool_name = None
        output = None

        if hasattr(step_result, "tool_name"):
            tool_name = step_result.tool_name
        elif hasattr(step_result, "name"):
            tool_name = step_result.name

        if hasattr(step_result, "output"):
            output = step_result.output
        elif hasattr(step_result, "result"):
            output = step_result.result
        elif hasattr(step_result, "content"):
            output = step_result.content

        if not tool_name or not output:
            return step_result

        if isinstance(output, str) and len(output) < 2000:
            return step_result

        processed = await self.archiver.process_tool_output(
            tool_name=tool_name,
            output=output,
        )

        if processed.get("archived"):
            if hasattr(step_result, "output"):
                step_result.output = processed["content"]
            if hasattr(step_result, "result"):
                step_result.result = processed["content"]
            if hasattr(step_result, "content"):
                step_result.content = processed["content"]

            if hasattr(step_result, "archive_ref"):
                step_result.archive_ref = processed["archive_ref"]
            elif hasattr(step_result, "metadata"):
                if not step_result.metadata:
                    step_result.metadata = {}
                step_result.metadata["archive_ref"] = processed["archive_ref"]

            logger.info(
                f"[V2Adapter] Tool output archived: {tool_name} -> "
                f"{processed['archive_ref']['file_id']}"
            )

        return step_result

    async def _handle_skill_complete(
        self,
        skill_result: Any,
    ) -> Any:
        skill_name = None
        content = None
        summary = None
        key_results = None

        if hasattr(skill_result, "skill_name"):
            skill_name = skill_result.skill_name
        elif hasattr(skill_result, "name"):
            skill_name = skill_result.name

        if hasattr(skill_result, "content"):
            content = skill_result.content
        if hasattr(skill_result, "summary"):
            summary = skill_result.summary
        if hasattr(skill_result, "key_results"):
            key_results = skill_result.key_results

        if not skill_name or not content:
            return skill_result

        if len(str(content)) > 3000:
            archive_result = await self.archiver.archive_skill_content(
                skill_name=skill_name,
                content=str(content),
                summary=summary,
                key_results=key_results,
            )

            if hasattr(skill_result, "content"):
                skill_result.content = archive_result["content"]
            if hasattr(skill_result, "archive_ref"):
                skill_result.archive_ref = archive_result.get("archive_ref")

            logger.info(f"[V2Adapter] Skill content archived: {skill_name}")

        return skill_result

    async def get_enhanced_tools(self) -> List["ToolBase"]:
        tools = []

        if self.task_board:
            tools.extend(await self._create_task_tools())

        return tools

    async def _create_task_tools(self) -> List["ToolBase"]:
        tools = []

        try:
            from derisk.agent.tools.base import ToolBase, ToolMetadata

            class TodoTool(ToolBase):
                def __init__(self, task_board, archiver=None):
                    self._task_board = task_board
                    self._archiver = archiver

                @property
                def metadata(self) -> ToolMetadata:
                    return ToolMetadata(
                        name="todo",
                        description="创建和管理 Todo 任务列表，用于追踪简单任务进度",
                        parameters={
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["create", "update", "list", "next"],
                                    "description": "操作类型",
                                },
                                "title": {
                                    "type": "string",
                                    "description": "任务标题 (create)",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "任务描述 (create)",
                                },
                                "task_id": {
                                    "type": "string",
                                    "description": "任务ID (update)",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": [
                                        "pending",
                                        "working",
                                        "completed",
                                        "failed",
                                    ],
                                    "description": "任务状态 (update)",
                                },
                            },
                            "required": ["action"],
                        },
                    )

                async def execute(self, **kwargs) -> Dict[str, Any]:
                    from derisk.agent.shared.task_board import TaskPriority, TaskStatus

                    action = kwargs.get("action")

                    if action == "create":
                        task = await self._task_board.create_todo(
                            title=kwargs.get("title", ""),
                            description=kwargs.get("description", ""),
                            priority=TaskPriority(kwargs.get("priority", "medium")),
                        )
                        return {
                            "success": True,
                            "task_id": task.id,
                            "message": f"Created: {task.title}",
                        }

                    elif action == "update":
                        task = await self._task_board.update_todo_status(
                            task_id=kwargs.get("task_id"),
                            status=TaskStatus(kwargs.get("status", "pending")),
                        )
                        if task:
                            return {"success": True, "message": f"Updated: {task.id}"}
                        return {"success": False, "message": "Task not found"}

                    elif action == "list":
                        todos = await self._task_board.list_todos()
                        return {
                            "success": True,
                            "todos": [t.to_dict() for t in todos],
                        }

                    elif action == "next":
                        task = await self._task_board.get_next_pending_todo()
                        if task:
                            return {"success": True, "task": task.to_dict()}
                        return {"success": False, "message": "No pending tasks"}

                    return {"success": False, "message": f"Unknown action: {action}"}

            class KanbanTool(ToolBase):
                def __init__(self, task_board, archiver=None):
                    self._task_board = task_board
                    self._archiver = archiver

                @property
                def metadata(self) -> ToolMetadata:
                    return ToolMetadata(
                        name="kanban",
                        description="创建和管理 Kanban 看板，用于复杂任务的阶段化管理",
                        parameters={
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["create", "status", "submit", "current"],
                                    "description": "操作类型",
                                },
                                "mission": {
                                    "type": "string",
                                    "description": "任务使命 (create)",
                                },
                                "stages": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "stage_id": {"type": "string"},
                                            "description": {"type": "string"},
                                            "deliverable_type": {"type": "string"},
                                        },
                                    },
                                    "description": "阶段列表 (create)",
                                },
                                "stage_id": {
                                    "type": "string",
                                    "description": "阶段ID (submit)",
                                },
                                "deliverable": {
                                    "type": "object",
                                    "description": "交付物 (submit)",
                                },
                            },
                            "required": ["action"],
                        },
                    )

                async def execute(self, **kwargs) -> Dict[str, Any]:
                    action = kwargs.get("action")

                    if action == "create":
                        result = await self._task_board.create_kanban(
                            mission=kwargs.get("mission", ""),
                            stages=kwargs.get("stages", []),
                        )
                        return result

                    elif action == "status":
                        kanban = await self._task_board.get_kanban()
                        if kanban:
                            return {
                                "success": True,
                                "overview": kanban.generate_overview(),
                            }
                        return {"success": False, "message": "No kanban exists"}

                    elif action == "submit":
                        result = await self._task_board.submit_deliverable(
                            stage_id=kwargs.get("stage_id"),
                            deliverable=kwargs.get("deliverable", {}),
                        )
                        return result

                    elif action == "current":
                        stage = await self._task_board.get_current_stage()
                        if stage:
                            return {
                                "success": True,
                                "stage": {
                                    "stage_id": stage.stage_id,
                                    "description": stage.description,
                                    "status": stage.status.value,
                                },
                            }
                        return {"success": False, "message": "No current stage"}

                    return {"success": False, "message": f"Unknown action: {action}"}

            tools.append(TodoTool(self.task_board, self.archiver))
            tools.append(KanbanTool(self.task_board, self.archiver))

        except ImportError:
            logger.warning("[V2Adapter] ToolBase not available, skipping tool creation")

        return tools

    async def get_task_status_for_prompt(self) -> str:
        if self.task_board:
            return await self.task_board.get_status_report()
        return ""

    async def process_tool_output(
        self,
        tool_name: str,
        output: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.archiver:
            return await self.archiver.process_tool_output(
                tool_name=tool_name,
                output=output,
                metadata=metadata,
            )
        return {"content": str(output), "archived": False}

    async def close(self):
        await self.shared.close()


async def create_v2_adapter(
    shared_context: SharedSessionContext,
) -> V2ContextAdapter:
    return V2ContextAdapter(shared_context)


__all__ = [
    "V2ContextAdapter",
    "create_v2_adapter",
]
