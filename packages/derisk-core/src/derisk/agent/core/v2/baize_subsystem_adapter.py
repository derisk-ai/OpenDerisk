"""BAIZESubsystemAdapter — BAIZE subsystems → StreamEvent bridge.

Spec §10.6 + §11.1. Subsystems (ContextEngine/Kanban/WorkLog/Phase/SystemEventManager)
keep their internal implementations; they call this adapter instead of
push_context_event/push_message. The adapter emits StreamEvents to the
runtime's EventStream.

P3 delivers the skeleton. Subsystem-by-subsystem migration is incremental
(P4 cleanup removes the old push_* paths once all subsystems migrated).
"""
from __future__ import annotations
from typing import Callable, Awaitable
from derisk.agent.core.v2.stream_event import StreamEvent


EmitCallback = Callable[[StreamEvent], Awaitable[None]]


class BAIZESubsystemAdapter:
    def __init__(self, emit_callback: EmitCallback):
        self._emit = emit_callback

    async def on_kanban_update(self, kanban_state: dict) -> None:
        await self._emit(StreamEvent(
            type="workspace",
            payload={"event_type": "task_created", **kanban_state},
        ))

    async def on_phase_change(self, phase: str) -> None:
        await self._emit(StreamEvent(
            type="workspace",
            payload={"event_type": "context_loaded", "phase": phase},
        ))

    async def on_worklog(self, worklog: dict) -> None:
        await self._emit(StreamEvent(
            type="content",
            payload=worklog,
        ))

    async def on_system_event(self, event_type: str, payload: dict) -> None:
        await self._emit(StreamEvent(
            type="workspace",
            payload={"event_type": event_type, **payload},
        ))
