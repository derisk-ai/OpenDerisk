"""EventStream——AsyncGenerator + 持久化。

每个 yield 前先持久化到 StateStore（durability before visibility）。
进程崩溃后通过 replay() 从 StateStore 重放历史事件。
"""
from __future__ import annotations
from typing import AsyncGenerator
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.state_store import StateStore


class EventStream:
    """事件流：持久化 + 重放。不直接 yield，由 run_step 的 async generator 驱动。"""

    def __init__(self, state_store: StateStore):
        self._store = state_store

    async def emit(self, event: StepEvent) -> StepEvent:
        """持久化事件后返回同一对象，供调用方 yield。"""
        await self._store.append_event(event)
        await self._store.set_step_state(
            event.step_id, event.conv_id, event.state, event.input
        )
        return event

    async def replay(
        self, conv_id: str, since_seq: int = 0
    ) -> AsyncGenerator[StepEvent, None]:
        """从 StateStore 重放历史事件。用于进程重启后续接。"""
        events = await self._store.get_events(conv_id, since_seq=since_seq)
        for event in events:
            yield event
