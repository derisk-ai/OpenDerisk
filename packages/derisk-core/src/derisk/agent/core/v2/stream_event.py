"""StreamEvent — external-facing event type for SSE adapter + internal consumers.

Spec §10.2. Wraps StepEvent's rich payload into a flat type+payload format
that the SSE adapter can dispatch on. EVENT_TYPES is the closed set of
allowed type strings.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Set


EVENT_TYPES: Set[str] = {
    # === 老 SSE 兼容（前端零修改） ===
    "metadata",
    "interrupt",
    "error",
    "workspace",
    "content",
    "done",
    # === 新增细粒度 ===
    "step_start",
    "step_end",
    "llm_token",
    "tool_call",
    "tool_result",
    "interaction_request",
    "sub_agent_start",
    "sub_agent_result",
    # === §10.7 实时可观测性 ===
    "usage_metric",
}


@dataclass
class StreamEvent:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    timestamp: float = 0.0
