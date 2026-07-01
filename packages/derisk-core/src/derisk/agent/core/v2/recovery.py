# packages/derisk-core/src/derisk/agent/core/v2/recovery.py
"""RecoveryCoordinatorV2——lease 管理 + 重放恢复决策。

崩溃检测：agent 运行时持有 lease（StateStore 实现），每 N 秒续期，
进程崩溃后 lease 过期，其他进程可 scan_expired 接管。

重放恢复：读 step_event 表，找最后一个 step 的 state，
- AWAITING_* → 恢复到等待状态
- THINKING/ACTING/OBSERVING → 未完成，重做该 step
- DONE → 继续下一个 step
"""
from __future__ import annotations
from typing import List, Optional, Tuple, Dict, Any
from derisk.agent.core.v2.state_store import StateStore
from derisk.agent.core.v2.step_event import StepEvent
from derisk.agent.core.v2.step_state import StepState


_AWAITING_STATES = {
    StepState.AWAITING_USER,
    StepState.AWAITING_TOOL_PERMISSION,
    StepState.AWAITING_SUB_AGENT,
}
_INCOMPLETE_STATES = {
    StepState.THINKING,
    StepState.ACTING,
    StepState.OBSERVING,
    StepState.INIT,
}


class RecoveryCoordinatorV2:
    def __init__(
        self,
        state_store: StateStore,
        lease_ttl_seconds: int = 30,
        renew_interval_seconds: int = 10,
    ):
        self._store = state_store
        self.lease_ttl_seconds = lease_ttl_seconds
        self.renew_interval_seconds = renew_interval_seconds

    async def acquire_lease(self, conv_id: str, agent_id: str) -> bool:
        return await self._store.acquire_lease(conv_id, agent_id, self.lease_ttl_seconds)

    async def renew_lease(self, conv_id: str, agent_id: str) -> bool:
        return await self._store.renew_lease(conv_id, agent_id, self.lease_ttl_seconds)

    async def release_lease(self, conv_id: str) -> None:
        await self._store.release_lease(conv_id)

    async def scan_expired(self) -> List[str]:
        return await self._store.scan_expired_leases()

    async def get_last_step_state(
        self, conv_id: str
    ) -> Optional[Tuple[str, StepState, dict]]:
        """返回 (step_id, state, snapshot)。通过重放事件找最后一个 step。"""
        events = await self._store.get_events(conv_id)
        if not events:
            return None
        last = events[-1]
        state_result = await self._store.get_step_state(last.step_id)
        snapshot = state_result[1] if state_result else {}
        return last.step_id, last.state, snapshot

    async def replay_events(self, conv_id: str) -> List[StepEvent]:
        return await self._store.get_events(conv_id)

    async def decide_resume_action(self, conv_id: str) -> Dict[str, Any]:
        """根据最后一个 step 的 state 决定恢复动作。"""
        last = await self.get_last_step_state(conv_id)
        if last is None:
            return {"action": "continue_next", "step_id": None, "state": None}
        step_id, state, _ = last
        if state in _AWAITING_STATES:
            return {"action": "resume_awaiting", "step_id": step_id, "state": state}
        if state in _INCOMPLETE_STATES:
            return {"action": "redo_step", "step_id": step_id, "state": state}
        # DONE / FAILED
        return {"action": "continue_next", "step_id": None, "state": state}
