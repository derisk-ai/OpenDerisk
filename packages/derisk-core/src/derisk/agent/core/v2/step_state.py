"""StepState 状态机——V2 Runtime 显式状态枚举。

替代散落的 Status 枚举 + received_message_state + RuntimeContext.recovering。
每个 AWAITING_* 状态都是可持久化挂起的——进程重启后能从 StateStore 恢复。
"""
from __future__ import annotations
from enum import Enum
from typing import Dict, Tuple


class StepState(Enum):
    INIT = "init"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    AWAITING_USER = "awaiting_user"
    AWAITING_TOOL_PERMISSION = "awaiting_tool_permission"
    AWAITING_SUB_AGENT = "awaiting_sub_agent"
    DONE = "done"
    FAILED = "failed"


class IllegalTransitionError(Exception):
    """非法状态转换。"""


VALID_TRANSITIONS: Dict[StepState, Tuple[StepState, ...]] = {
    StepState.INIT: (StepState.THINKING, StepState.AWAITING_USER),
    StepState.THINKING: (
        StepState.ACTING,
        StepState.AWAITING_USER,
        StepState.AWAITING_TOOL_PERMISSION,
        StepState.AWAITING_SUB_AGENT,
        StepState.DONE,
        StepState.FAILED,
    ),
    StepState.ACTING: (
        StepState.OBSERVING,
        StepState.AWAITING_USER,
        StepState.AWAITING_TOOL_PERMISSION,
        StepState.AWAITING_SUB_AGENT,
        StepState.DONE,
        StepState.FAILED,
    ),
    StepState.OBSERVING: (StepState.THINKING, StepState.ACTING, StepState.DONE, StepState.FAILED),
    StepState.AWAITING_USER: (StepState.THINKING, StepState.FAILED),
    StepState.AWAITING_TOOL_PERMISSION: (StepState.ACTING, StepState.FAILED),
    StepState.AWAITING_SUB_AGENT: (StepState.OBSERVING, StepState.FAILED),
    StepState.DONE: (),
    StepState.FAILED: (),
}


def validate_transition(from_state: StepState, to_state: StepState) -> bool:
    """检查状态转换是否合法。"""
    return to_state in VALID_TRANSITIONS.get(from_state, ())
