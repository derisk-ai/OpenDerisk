from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from derisk.agent.core.schema import Status


@dataclasses.dataclass
class AgentSystemMessage:
    conv_id: str
    conv_session_id: str
    agent: str
    type: str
    phase: str
    agent_message_id: str
    message_id: str
    content: Optional[str] = None
    content_extra: Optional[str] = None
    retry_time: int = 0
    final_status: Optional[str] = None
    plan_round_id: Optional[str] = None
    gmt_create: datetime = dataclasses.field(default_factory=datetime.now)
    gmt_modified: datetime = dataclasses.field(default_factory=datetime.now)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "AgentSystemMessage":
        """Create a SystemMessage object from a dictionary."""
        return AgentSystemMessage(
            conv_id=d["conv_id"],
            conv_session_id=d["conv_session_id"],
            agent=d["agent"],
            type=d["type"],
            phase=d["phase"],
            agent_message_id=d["agent_message_id"],
            message_id=d["message_id"],
            content=d.get('content'),
            content_extra=d.get('content_extra'),
            retry_time=d.get('retry_time'),
            final_status=d.get('final_status'),
            gmt_create=d.get('gmt_create'),
            gmt_modified=d.get('gmt_modified'),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the SystenMessage object."""
        return dataclasses.asdict(self)

    @classmethod
    def build(cls, agent_context: "AgentContext", agent: "ConversableAgent", type: SystemMessageType, phase: AgentPhase,
              reply_message_id: Optional[str] = None, plan_round_id: Optional[str] = None,
              retry_time: Optional[int] = None, content: Optional[str] = None, final_status: Optional[Status] = None):
        return cls(
            conv_id=agent_context.conv_id,
            conv_session_id=agent_context.conv_session_id,
            plan_round_id=plan_round_id or agent.conv_round_id,
            agent=agent.name,
            type=type.value,
            phase=phase.value,
            agent_message_id=reply_message_id,
            message_id=uuid.uuid4().hex,
            content=content,
            retry_time=retry_time if retry_time else 0,
            final_status=Status.COMPLETE.value if not final_status else final_status.value,
        )

    def update(self, retry_time: int, content: str, final_status: Status, type: Optional[SystemMessageType] = None):
        self.retry_time = retry_time
        self.content = content
        self.final_status = final_status.value
        if type:
            self.type = type.ERROR.value


class AgentPhase(Enum):
    IN_CONTEXT = "in_context"
    AGENT_RUN = "agent_run"
    LLM_CALL = "llm_call"
    ACTION_RUN = "action_run"
    MESSAGE_OUT = "message_out"


class SystemMessageType(Enum):
    SYSTEM = "system"
    ERROR = "error"
    STATUS = "status"
