from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class DerisksMessage:
    sender: str
    receiver: str
    content: str
    action_report: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> DerisksMessage:
        return DerisksMessage(
            sender=d["sender"],
            receiver=d["receiver"],
            content=d["content"],
            model_name=d["model_name"],
            agent_name=d["agent_name"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class DerisksTaskStep:
    task_num: str
    task_content: str
    state: str
    result: str
    agent_name: str
    model_name: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> DerisksTaskStep:
        return DerisksTaskStep(
            task_num=d["task_num"],
            task_content=d["task_content"],
            state=d["state"],
            result=d["result"],
            agent_name=d["agent_name"],
            model_name=d["model_name"],
        )

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class DerisksCompletion:
    conv_id: str
    task_steps: Optional[List[DerisksTaskStep]]
    messages: Optional[List[DerisksMessage]]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> DerisksCompletion:
        return DerisksCompletion(
            conv_id=d.get("conv_id"),
            task_steps=DerisksTaskStep.from_dict(d["task_steps"]),
            messages=DerisksMessage.from_dict(d["messages"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
