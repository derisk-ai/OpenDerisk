"""StepEvent——event sourcing 最小单元。

append-only：一旦写入不可修改。一个 step 产出多个 StepEvent
（thinking 阶段多个 llm_token，acting 阶段 tool_call + tool_result）。
"""
from __future__ import annotations
from typing import Any, Optional
from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict
from derisk.agent.core.v2.step_state import StepState


class StepEvent(BaseModel):
    model_config = ConfigDict(
        title="StepEvent",
        use_enum_values=False,
        arbitrary_types_allowed=True,
    )

    event_id: str
    step_id: str
    conv_id: str
    agent_id: str
    parent_step_id: Optional[str] = None
    state: StepState
    event_type: str
    input: dict = {}
    output: dict = {}
    seq: int
    timestamp: float

    def to_storage_dict(self) -> dict:
        """序列化为可存入 DB 的 dict（枚举转字符串）。"""
        d = model_to_dict(self)
        d["state"] = self.state.value
        d["input"] = __import__("json").dumps(self.input)
        d["output"] = __import__("json").dumps(self.output)
        d["parent_step_id"] = self.parent_step_id
        return d

    @staticmethod
    def from_storage_dict(d: dict) -> "StepEvent":
        """从 DB 行反序列化。"""
        import json
        return StepEvent(
            event_id=d["event_id"],
            step_id=d["step_id"],
            conv_id=d["conv_id"],
            agent_id=d["agent_id"],
            parent_step_id=d.get("parent_step_id"),
            state=StepState(d["state"]),
            event_type=d["event_type"],
            input=json.loads(d["input"]) if d.get("input") else {},
            output=json.loads(d["output"]) if d.get("output") else {},
            seq=d["seq"],
            timestamp=d["timestamp"],
        )
