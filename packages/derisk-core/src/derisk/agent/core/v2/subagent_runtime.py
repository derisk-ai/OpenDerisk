"""SubAgentRuntime — spec §8 SubAgent Runtime entry point.

Single entry: spawn(spec) -> SubAgentHandle.
- SYNC mode: await sub-agent's run_step, return handle with result
- ASYNC mode: schedule run_step in background, persist transcript, return immediately
- Depth limiting: reject spawn if depth+1 > max_depth
- Independent context: each spawn creates a new sub_conv_id

P2 wraps the existing AsyncTaskManager for ASYNC mode (lifecycle, cancel,
wait). SYNC mode just awaits run_step directly.
"""
from __future__ import annotations
import uuid
import time
import asyncio
from typing import Any, Optional, Dict, TYPE_CHECKING
from derisk._private.pydantic import BaseModel, ConfigDict
from derisk.agent.core.v2.subagent_handle import (
    SubAgentHandle, SubAgentMode, SubAgentStatus,
)
from derisk.agent.core.v2.runtime import run_step
from derisk.agent.core.v2.subagent_interaction_gateway import SubAgentInteractionGateway
from derisk.agent.core.v2.permission_gate import PermissionGate
from derisk.agent.core.v2.permission_mode import PermissionMode
from derisk.agent.core.v2.event_stream import EventStream

if TYPE_CHECKING:
    from derisk.agent.core.v2.state_store import StateStore
    from derisk.agent.util.async_task_manager import AsyncTaskManager


class SubAgentSpawnSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    agent_name: str
    task: str
    run_in_background: bool = False
    context: Dict[str, Any] = {}
    parent_step_id: str
    parent_conv_id: str
    parent_agent_id: str
    depth: int = 0
    thinking_fn: Optional[Any] = None
    acting_fn: Optional[Any] = None
    interaction_gateway: Optional[Any] = None
    ruleset: Optional[Any] = None


class SubAgentRuntime:
    def __init__(
        self,
        state_store: "StateStore",
        max_depth: int = 5,
        async_task_manager: Optional["AsyncTaskManager"] = None,
    ):
        self._store = state_store
        self._max_depth = max_depth
        self._async_mgr = async_task_manager
        self._handles: Dict[str, SubAgentHandle] = {}
        self._async_tasks: Dict[str, asyncio.Task] = {}

    async def spawn(self, spec: SubAgentSpawnSpec) -> SubAgentHandle:
        if spec.depth + 1 > self._max_depth:
            raise ValueError(
                f"spawn depth limit exceeded: depth={spec.depth}, max_depth={self._max_depth}"
            )

        task_id = f"task-{uuid.uuid4().hex[:8]}"
        sub_conv_id = f"conv-{uuid.uuid4().hex[:8]}"
        now = time.time()
        mode = SubAgentMode.ASYNC if spec.run_in_background else SubAgentMode.SYNC
        handle = SubAgentHandle(
            task_id=task_id,
            parent_step_id=spec.parent_step_id,
            parent_conv_id=spec.parent_conv_id,
            sub_conv_id=sub_conv_id,
            agent_name=spec.agent_name,
            mode=mode,
            status=SubAgentStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        if mode is SubAgentMode.SYNC:
            await self._run_subagent(handle, spec)
        else:
            # ASYNC: schedule in background, persist transcript
            transcript_id = f"t-{uuid.uuid4().hex[:8]}"
            handle.transcript_id = transcript_id
            handle.status = SubAgentStatus.RUNNING
            self._handles[task_id] = handle
            self._async_tasks[task_id] = asyncio.create_task(
                self._run_subagent_async(handle, spec, transcript_id)
            )

        return handle

    async def _make_permission_gate(
        self, handle: SubAgentHandle, spec: SubAgentSpawnSpec
    ):
        """Build a PermissionGate wired to the parent's gateway (if any)."""
        if spec.interaction_gateway is None:
            return None
        sub_gateway = SubAgentInteractionGateway(
            parent_gateway=spec.interaction_gateway,
            sync=not spec.run_in_background,
        )
        return PermissionGate(
            state_store=self._store,
            event_stream=EventStream(self._store),
            interaction_adapter=sub_gateway,
            mode=PermissionMode.DEFAULT,
            ruleset=spec.ruleset,
            step_id=None,  # bound by run_step
            conv_id=handle.sub_conv_id,
            agent_id=f"subagent-{handle.task_id}",
        )

    async def _run_subagent(self, handle: SubAgentHandle, spec: SubAgentSpawnSpec) -> None:
        """Sync mode: run sub-agent to completion before returning."""
        handle.status = SubAgentStatus.RUNNING
        self._handles[handle.task_id] = handle
        input_ = {"prompt": spec.task, **spec.context}
        permission_gate = await self._make_permission_gate(handle, spec)
        try:
            result = {"events": []}
            async for event in run_step(
                agent_id=f"subagent-{handle.task_id}",
                conv_id=handle.sub_conv_id,
                input_=input_,
                state_store=self._store,
                thinking_fn=spec.thinking_fn,
                acting_fn=spec.acting_fn,
                parent_step_id=handle.parent_step_id,
                permission_gate=permission_gate,
            ):
                result["events"].append({
                    "seq": event.seq,
                    "state": event.state.value,
                    "event_type": event.event_type,
                })
            handle.result = {"status": "done", "events_count": len(result["events"])}
            handle.status = SubAgentStatus.DONE
        except Exception as e:
            handle.error = str(e)
            handle.status = SubAgentStatus.FAILED
        handle.updated_at = time.time()

    async def _run_subagent_async(
        self, handle: SubAgentHandle, spec: SubAgentSpawnSpec, transcript_id: str,
    ) -> None:
        """Async mode: run in background, update transcript periodically."""
        input_ = {"prompt": spec.task, **spec.context}
        permission_gate = await self._make_permission_gate(handle, spec)
        try:
            latest_seq = 0
            async for event in run_step(
                agent_id=f"subagent-{handle.task_id}",
                conv_id=handle.sub_conv_id,
                input_=input_,
                state_store=self._store,
                thinking_fn=spec.thinking_fn,
                acting_fn=spec.acting_fn,
                parent_step_id=handle.parent_step_id,
                permission_gate=permission_gate,
            ):
                latest_seq = max(latest_seq, event.seq)
                # Persist transcript snapshot every few events
                await self._store.save_transcript(
                    transcript_id=transcript_id,
                    task_id=handle.task_id,
                    sub_conv_id=handle.sub_conv_id,
                    parent_step_id=handle.parent_step_id,
                    parent_conv_id=handle.parent_conv_id,
                    agent_name=handle.agent_name,
                    status="running",
                    latest_event_seq=latest_seq,
                    payload={"last_event_state": event.state.value},
                )
            handle.result = {"status": "done", "latest_seq": latest_seq}
            handle.status = SubAgentStatus.DONE
            await self._store.save_transcript(
                transcript_id=transcript_id,
                task_id=handle.task_id,
                sub_conv_id=handle.sub_conv_id,
                parent_step_id=handle.parent_step_id,
                parent_conv_id=handle.parent_conv_id,
                agent_name=handle.agent_name,
                status="done",
                latest_event_seq=latest_seq,
                payload={"result": handle.result},
            )
        except asyncio.CancelledError:
            handle.status = SubAgentStatus.CANCELLED
            await self._store.save_transcript(
                transcript_id=transcript_id,
                task_id=handle.task_id,
                sub_conv_id=handle.sub_conv_id,
                parent_step_id=handle.parent_step_id,
                parent_conv_id=handle.parent_conv_id,
                agent_name=handle.agent_name,
                status="cancelled",
                latest_event_seq=0,
                payload={"error": "cancelled"},
            )
            raise
        except Exception as e:
            handle.error = str(e)
            handle.status = SubAgentStatus.FAILED
            await self._store.save_transcript(
                transcript_id=transcript_id,
                task_id=handle.task_id,
                sub_conv_id=handle.sub_conv_id,
                parent_step_id=handle.parent_step_id,
                parent_conv_id=handle.parent_conv_id,
                agent_name=handle.agent_name,
                status="failed",
                latest_event_seq=0,
                payload={"error": str(e)},
            )
        finally:
            handle.updated_at = time.time()

    async def wait(self, handle: SubAgentHandle, timeout: Optional[float] = None) -> SubAgentHandle:
        if handle.mode is SubAgentMode.SYNC:
            return handle  # sync already done
        task = self._async_tasks.get(handle.task_id)
        if task is None:
            return handle
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return self._handles.get(handle.task_id, handle)

    async def get_status(self, task_id: str) -> Optional[SubAgentHandle]:
        return self._handles.get(task_id)

    async def cancel(self, task_id: str) -> bool:
        task = self._async_tasks.get(task_id)
        if task is None:
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # If the task was cancelled before it started, the coroutine body never
        # ran and didn't get a chance to update the handle status.
        handle = self._handles.get(task_id)
        if handle is not None and not handle.is_done():
            handle.status = SubAgentStatus.CANCELLED
            handle.updated_at = time.time()
        return True

    async def resume(self, task_id: str) -> Optional[SubAgentHandle]:
        """Re-attach to an async sub-agent. Returns current handle."""
        return self._handles.get(task_id)
