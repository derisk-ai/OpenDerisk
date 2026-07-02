"""SpawnSubagentTool — LLM-facing tool wrapping SubAgentRuntime.spawn.

Spec §8.1. Replaces the dual-entry agent_start + AsyncTaskManager pattern.
LLM calls this tool with agent_name + task + run_in_background; the tool
builds a SubAgentSpawnSpec and delegates to SubAgentRuntime.
"""
from __future__ import annotations
from typing import Any, Optional, Dict
from derisk.agent.tools.base import ToolBase
from derisk.agent.tools.metadata import ToolMetadata
from derisk.agent.tools.result import ToolResult
from derisk.agent.core.v2.subagent_runtime import (
    SubAgentRuntime, SubAgentSpawnSpec,
)


class SpawnSubagentTool(ToolBase):
    def __init__(self, runtime: SubAgentRuntime):
        super().__init__()
        self._runtime = runtime

    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="spawn_subagent",
            description="Spawn a sub-agent (sync or async). Spec §8.",
        )

    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Sub-agent type (e.g. 'BAIZE')"},
                "task": {"type": "string", "description": "Task description for the sub-agent"},
                "run_in_background": {
                    "type": "boolean",
                    "default": False,
                    "description": "False=sync (block until done); True=async (return handle immediately)",
                },
                "context": {"type": "object", "default": {}},
            },
            "required": ["agent_name", "task"],
        }

    async def execute(
        self,
        args: Dict[str, Any],
        context: Optional[Any] = None,
    ) -> ToolResult:
        agent_name = args.get("agent_name")
        task = args.get("task")
        if not agent_name or not task:
            return ToolResult(
                success=False,
                error="spawn_subagent requires 'agent_name' and 'task'",
                tool_name="spawn_subagent",
            )

        # Extract parent info from context. ToolContext shape varies; use getattr.
        parent_step_id = getattr(context, "parent_step_id", None) or "step-unknown"
        parent_conv_id = getattr(context, "parent_conv_id", None) or "conv-unknown"
        parent_agent_id = getattr(context, "agent_id", None) or "agent-unknown"
        depth = getattr(context, "depth", 0)
        thinking_fn = getattr(context, "thinking_fn", None)
        acting_fn = getattr(context, "acting_fn", None)
        interaction_gateway = getattr(context, "interaction_gateway", None)

        spec = SubAgentSpawnSpec(
            agent_name=agent_name,
            task=task,
            run_in_background=args.get("run_in_background", False),
            context=args.get("context", {}),
            parent_step_id=parent_step_id,
            parent_conv_id=parent_conv_id,
            parent_agent_id=parent_agent_id,
            depth=depth,
            thinking_fn=thinking_fn,
            acting_fn=acting_fn,
            interaction_gateway=interaction_gateway,
        )

        handle = await self._runtime.spawn(spec)
        return ToolResult(
            success=True,
            output={
                "task_id": handle.task_id,
                "mode": handle.mode.value,
                "status": handle.status.value,
                "sub_conv_id": handle.sub_conv_id,
                "result": handle.result,
                "transcript_id": handle.transcript_id,
            },
            tool_name="spawn_subagent",
        )
