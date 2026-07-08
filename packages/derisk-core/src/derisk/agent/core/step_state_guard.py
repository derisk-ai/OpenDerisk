"""状态机守卫：校验 Status 转换是否合法。

V1 的 Status 枚举有 8 值但无转换表，状态变更散落 1000+ 行 if-else。
本模块提供 VALID_TRANSITIONS 表 + 守卫函数，让非法转换抛错（先 WARN_ONLY 灰度）。

用法：
    from derisk.agent.core.step_state_guard import validate_session_transition
    validate_session_transition(old_state, new_state)  # WARN_ONLY=True 时只 log warning
"""
from __future__ import annotations

import logging
from typing import Optional, Set

from derisk.agent.core.schema import Status

logger = logging.getLogger(__name__)


class IllegalTransitionError(Exception):
    """非法状态转换。"""


# 会话级（gpts_conversations.state）
SESSION_VALID_TRANSITIONS: dict[Optional[Status], Set[Status]] = {
    None: {Status.RUNNING},
    Status.RUNNING: {
        Status.WAITING,
        Status.COMPLETE,
        Status.INTERRUPTED,
        Status.FAILED,
        Status.RETRYING,
    },
    Status.WAITING: {Status.RUNNING, Status.INTERRUPTED, Status.FAILED},
    Status.RETRYING: {Status.RUNNING, Status.FAILED},
    Status.COMPLETE: set(),  # 终态
    Status.FAILED: set(),  # 终态
    Status.INTERRUPTED: {Status.RUNNING},  # 可恢复
    Status.BLOCKED: {Status.RUNNING, Status.FAILED},
}

# 消息级（received_message_state）
MESSAGE_VALID_TRANSITIONS: dict[Optional[Status], Set[Status]] = {
    None: {Status.TODO},
    Status.TODO: {Status.RUNNING},
    Status.RUNNING: {Status.COMPLETE, Status.FAILED},
    Status.COMPLETE: set(),
    Status.FAILED: set(),
}

# 灰度开关：True 时只 log warning 不抛错；False 时抛 IllegalTransitionError
WARN_ONLY = True


def _state_name(s: Optional[Status]) -> str:
    return "None" if s is None else s.name


def _validate(
    old: Optional[Status],
    new: Status,
    table: dict,
    label: str,
) -> bool:
    """通用校验：返回 True 合法，False 非法。"""
    allowed = table.get(old)
    if allowed is None:
        # old 不在表里（如 BLOCKED 在 MESSAGE 表里没有）——保守起见放行
        return True
    if new in allowed:
        return True
    return False


def validate_session_transition(old: Optional[Status], new: Status) -> None:
    """校验会话级状态转换。非法时 WARN_ONLY=True log warning，False 抛错。"""
    if _validate(old, new, SESSION_VALID_TRANSITIONS, "session"):
        return
    msg = (
        f"[state-guard] illegal session transition: "
        f"{_state_name(old)} -> {_state_name(new)}"
    )
    if WARN_ONLY:
        logger.warning(msg)
    else:
        raise IllegalTransitionError(msg)


def validate_message_transition(old: Optional[Status], new: Status) -> None:
    """校验消息级状态转换。非法时 WARN_ONLY=True log warning，False 抛错。"""
    if _validate(old, new, MESSAGE_VALID_TRANSITIONS, "message"):
        return
    msg = (
        f"[state-guard] illegal message transition: "
        f"{_state_name(old)} -> {_state_name(new)}"
    )
    if WARN_ONLY:
        logger.warning(msg)
    else:
        raise IllegalTransitionError(msg)
