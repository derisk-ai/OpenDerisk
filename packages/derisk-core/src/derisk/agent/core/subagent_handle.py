"""SubAgentHandle: 子 Agent 句柄抽象（借鉴 V2）。

封装子 agent 的状态 + spec，供 SubagentCoordinator 管理。
序列化到 gpts_conversations.extra JSON 字段持久化，以便重启恢复。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class SubAgentMode(str, Enum):
    """子 Agent 执行模式。"""
    SYNC = "sync"    # 同步：主 agent 等待子 agent 完成，直接拿结果
    ASYNC = "async"  # 异步：主 agent 不等待，子 agent 后台跑，全完成后触发主 resume


class SubAgentStatus(str, Enum):
    """子 Agent 运行状态。"""
    PENDING = "pending"   # 已创建但未开始
    RUNNING = "running"   # 正在运行
    DONE = "done"         # 成功完成
    FAILED = "failed"     # 失败


# 子 Agent 嵌套深度上限。超过则抛 SubagentDepthExceededError，防止递归 spawn 爆栈。
MAX_SUBAGENT_DEPTH = 5


class SubagentDepthExceededError(Exception):
    """子 Agent 嵌套深度超过 MAX_SUBAGENT_DEPTH。"""

    def __init__(self, depth: int, max_depth: int = MAX_SUBAGENT_DEPTH):
        self.depth = depth
        self.max_depth = max_depth
        super().__init__(
            f"Subagent depth {depth} exceeds max {max_depth}. "
            f"Refusing to spawn further nested subagents."
        )


@dataclass
class SubAgentHandle:
    """子 Agent 句柄：封装状态 + spec，供 SubagentCoordinator 管理。"""
    sub_conv_id: str                    # 子 agent 的会话 ID
    main_conv_id: str                   # 主 agent 的会话 ID
    mode: SubAgentMode                  # sync | async
    status: SubAgentStatus = SubAgentStatus.PENDING
    result: Optional[str] = None        # 子 agent 完成时的结果
    error: Optional[str] = None         # 子 agent 失败时的错误信息
    started_at: Optional[float] = None  # 启动时间戳
    finished_at: Optional[float] = None  # 完成时间戳

    def to_dict(self) -> dict:
        """序列化为 dict（用于持久化到 gpts_conversations.extra JSON）。"""
        d = asdict(self)
        d["mode"] = self.mode.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SubAgentHandle":
        """从 dict 反序列化。"""
        return cls(
            sub_conv_id=d["sub_conv_id"],
            main_conv_id=d["main_conv_id"],
            mode=SubAgentMode(d["mode"]),
            status=SubAgentStatus(d["status"]),
            result=d.get("result"),
            error=d.get("error"),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
        )

    def is_terminal(self) -> bool:
        """是否处于终态（DONE 或 FAILED）。"""
        return self.status in (SubAgentStatus.DONE, SubAgentStatus.FAILED)
