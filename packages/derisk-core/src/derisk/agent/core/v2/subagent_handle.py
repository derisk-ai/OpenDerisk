"""SubAgentHandle — handle returned by SubAgentRuntime.spawn.

Spec §8.1. Carries the task_id, parent/sub conv ids, mode, status, and result.
SYNC mode: handle is awaited; result populated when sub-agent finishes.
ASYNC mode: handle is returned immediately; transcript persisted to
agent_transcript table; parent polls or receives notification injection.
"""
from __future__ import annotations
import time
from enum import Enum
from typing import Optional
from derisk._private.pydantic import BaseModel, ConfigDict


class SubAgentMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class SubAgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = {SubAgentStatus.DONE, SubAgentStatus.FAILED, SubAgentStatus.CANCELLED}


class SubAgentHandle(BaseModel):
    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=True)

    task_id: str
    parent_step_id: str
    parent_conv_id: str
    sub_conv_id: str
    agent_name: str
    mode: SubAgentMode
    status: SubAgentStatus
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float
    updated_at: float
    transcript_id: Optional[str] = None

    def is_done(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def to_payload(self) -> dict:
        return {
            "task_id": self.task_id,
            "parent_step_id": self.parent_step_id,
            "parent_conv_id": self.parent_conv_id,
            "sub_conv_id": self.sub_conv_id,
            "agent_name": self.agent_name,
            "mode": self.mode.value,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "transcript_id": self.transcript_id,
        }
