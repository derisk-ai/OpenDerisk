"""Tier 3.4: 状态机形式化模型检查。

不依赖 hypothesis（避免新增依赖），用 pytest + random 实现：
1. 静态检查：所有状态可达、终态无 outgoing、非终态至少一个 outgoing
2. 随机游走：N 次 random walk，验证每次 transition 合法
3. 终态可达性：从任何非终态出发，存在路径到达终态
4. 死锁检测：从任何状态出发，不应被困在非终态循环里
5. 不变量：status 永远在 VALID_TRANSITIONS 的 key 集合里
"""
from __future__ import annotations

import random
from typing import Optional, Set

import pytest

from derisk.agent.core.schema import Status
from derisk.agent.core.step_state_guard import (
    MESSAGE_VALID_TRANSITIONS,
    SESSION_VALID_TRANSITIONS,
    Status as GuardStatus,  # noqa: F401  # 验证 import 可用
    validate_message_transition,
    validate_session_transition,
)


# ---------------- 静态结构检查 ----------------

class TestStateMachineStructure:
    def test_session_all_session_states_have_transition_table_entry(self):
        """会话级 Status（除 TODO 外）都应在 SESSION_VALID_TRANSITIONS 的 key 里。"""
        # TODO 是消息级状态，不应在会话级转换表里
        session_states = set(Status) - {Status.TODO}
        for s in session_states:
            assert s in SESSION_VALID_TRANSITIONS, (
                f"Status {s.name} missing from SESSION_VALID_TRANSITIONS"
            )

    def test_session_todo_excluded_from_session_table(self):
        """TODO 是消息级状态，不应在会话级转换表里。"""
        assert Status.TODO not in SESSION_VALID_TRANSITIONS

    def test_session_terminal_states_have_empty_outgoing(self):
        """终态（COMPLETE/FAILED）的 outgoing 应为空 set。"""
        assert SESSION_VALID_TRANSITIONS[Status.COMPLETE] == set()
        assert SESSION_VALID_TRANSITIONS[Status.FAILED] == set()

    def test_session_non_terminal_states_have_outgoing(self):
        """非终态至少有一个 outgoing transition（否则是死锁）。"""
        non_terminal = [
            Status.RUNNING, Status.WAITING, Status.RETRYING,
            Status.INTERRUPTED, Status.BLOCKED,
        ]
        for s in non_terminal:
            outgoing = SESSION_VALID_TRANSITIONS.get(s, set())
            assert len(outgoing) > 0, (
                f"Non-terminal {s.name} has no outgoing transitions → deadlock"
            )

    def test_session_no_self_loop_except_retrying(self):
        """自环（state → 同一 state）通常是 bug，RETRYING→RETRYING 不允许。"""
        for s, outs in SESSION_VALID_TRANSITIONS.items():
            if s is None:
                continue
            assert s not in outs, f"Self-loop {s.name} → {s.name} not allowed"

    def test_session_outgoing_states_all_known(self):
        """每个 outgoing 必须是已知的 Status。"""
        known = set(Status)
        for s, outs in SESSION_VALID_TRANSITIONS.items():
            for o in outs:
                assert o in known, f"Unknown status {o} in outgoing of {s}"

    def test_session_symmetric_recoverability(self):
        """INTERRUPTED → RUNNING 存在，则 RUNNING → INTERRUPTED 也应存在（取消路径对称）。"""
        # RUNNING → INTERRUPTED（用户取消）
        assert Status.INTERRUPTED in SESSION_VALID_TRANSITIONS[Status.RUNNING]
        # INTERRUPTED → RUNNING（恢复）
        assert Status.RUNNING in SESSION_VALID_TRANSITIONS[Status.INTERRUPTED]

    def test_message_all_states_have_transition_table_entry(self):
        known_message_states = {Status.TODO, Status.RUNNING, Status.COMPLETE, Status.FAILED}
        for s in known_message_states:
            assert s in MESSAGE_VALID_TRANSITIONS

    def test_message_terminal_states_have_empty_outgoing(self):
        assert MESSAGE_VALID_TRANSITIONS[Status.COMPLETE] == set()
        assert MESSAGE_VALID_TRANSITIONS[Status.FAILED] == set()


# ---------------- 随机游走（Random Walk）----------------

class TestRandomWalks:
    """从 None 出发，随机走 N 步，每步都必须合法。"""

    @pytest.mark.parametrize("seed", range(20))
    def test_session_random_walk_always_legal(self, seed):
        """20 次随机游走，每次 50 步，每步都应被 validate 接受。"""
        rng = random.Random(seed)
        current: Optional[Status] = None
        for _ in range(50):
            outs = SESSION_VALID_TRANSITIONS.get(current, set())
            if not outs:
                # 终态：游走结束
                break
            nxt = rng.choice(list(outs))
            # 这一步应被 validate 接受（不抛异常）
            validate_session_transition(current, nxt)
            current = nxt

    @pytest.mark.parametrize("seed", range(20))
    def test_message_random_walk_always_legal(self, seed):
        rng = random.Random(seed)
        current: Optional[Status] = None
        for _ in range(50):
            outs = MESSAGE_VALID_TRANSITIONS.get(current, set())
            if not outs:
                break
            nxt = rng.choice(list(outs))
            validate_message_transition(current, nxt)
            current = nxt

    def test_session_invalid_transition_rejected(self):
        """显式构造非法转换 → WARN_ONLY=True 时只 log，不抛；False 时抛 IllegalTransitionError。"""
        from derisk.agent.core.step_state_guard import (
            IllegalTransitionError,
            WARN_ONLY,
        )
        # COMPLETE → 任何状态都非法
        if WARN_ONLY:
            # WARN_ONLY=True 时不抛异常，只 log warning
            validate_session_transition(Status.COMPLETE, Status.RUNNING)
        else:
            with pytest.raises(IllegalTransitionError):
                validate_session_transition(Status.COMPLETE, Status.RUNNING)


# ---------------- 终态可达性（从任何状态都能走到终态）----------------

class TestTerminalReachability:
    def _can_reach_terminal(
        self,
        start: Status,
        table: dict,
        terminals: Set[Status],
        max_depth: int = 20,
    ) -> bool:
        """BFS：从 start 出发，能否在 max_depth 步内到达任一终态。"""
        if start in terminals:
            return True
        visited = {start}
        queue = [(start, 0)]
        while queue:
            state, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            outs = table.get(state, set())
            for o in outs:
                if o in terminals:
                    return True
                if o not in visited:
                    visited.add(o)
                    queue.append((o, depth + 1))
        return False

    def test_session_all_non_terminal_can_reach_terminal(self):
        """每个非终态都应能到达 COMPLETE 或 FAILED。"""
        terminals = {Status.COMPLETE, Status.FAILED}
        non_terminal = [
            Status.RUNNING, Status.WAITING, Status.RETRYING,
            Status.INTERRUPTED, Status.BLOCKED,
        ]
        for s in non_terminal:
            assert self._can_reach_terminal(
                s, SESSION_VALID_TRANSITIONS, terminals
            ), f"{s.name} cannot reach any terminal state → livelock risk"

    def test_message_all_non_terminal_can_reach_terminal(self):
        terminals = {Status.COMPLETE, Status.FAILED}
        for s in [Status.TODO, Status.RUNNING]:
            assert self._can_reach_terminal(
                s, MESSAGE_VALID_TRANSITIONS, terminals
            ), f"{s.name} cannot reach any terminal state"


# ---------------- 死锁检测（无 outgoing 的非终态）----------------

class TestNoDeadlock:
    def test_session_no_non_terminal_state_has_empty_outgoing(self):
        """非终态的 outgoing 不能为空（否则是死锁）。"""
        terminals = {Status.COMPLETE, Status.FAILED}
        for s, outs in SESSION_VALID_TRANSITIONS.items():
            if s is None or s in terminals:
                continue
            assert len(outs) > 0, (
                f"Non-terminal state {s.name} has empty outgoing → deadlock"
            )

    def test_message_no_non_terminal_state_has_empty_outgoing(self):
        terminals = {Status.COMPLETE, Status.FAILED}
        for s, outs in MESSAGE_VALID_TRANSITIONS.items():
            if s is None or s in terminals:
                continue
            assert len(outs) > 0, (
                f"Non-terminal message state {s.name} has empty outgoing → deadlock"
            )


# ---------------- 不变量（invariants）----------------

class TestInvariants:
    def test_session_recovering_states_can_reach_running(self):
        """RETRYING/INTERRUPTED/BLOCKED 都应能恢复到 RUNNING（否则无法继续）。"""
        recoverable = [Status.RETRYING, Status.INTERRUPTED, Status.BLOCKED]
        for s in recoverable:
            assert Status.RUNNING in SESSION_VALID_TRANSITIONS.get(s, set()), (
                f"{s.name} cannot return to RUNNING → unrecoverable"
            )

    def test_session_running_can_reach_all_terminals(self):
        """RUNNING 应能直接或间接到达所有终态（COMPLETE + FAILED）。"""
        outs = SESSION_VALID_TRANSITIONS[Status.RUNNING]
        # RUNNING 可以直接到 FAILED（异常）
        assert Status.FAILED in outs
        # RUNNING 可以直接到 COMPLETE（正常结束）
        assert Status.COMPLETE in outs
