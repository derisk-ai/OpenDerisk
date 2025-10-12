from enum import Enum
from typing import TypeVar, Generic, Optional, Any

from derisk._private.pydantic import BaseModel, Field

PAYLOAD = TypeVar("PAYLOAD", bound="Payload")


class EventType(str, Enum):
    """上下文事件类型"""
    ChatStart = "chat_start"  # Agent对话开启
    ChatEnd = "chat_end"  # Agent对话结束
    StepStart = "step_start"  # 对话一轮循环开始
    StepEnd = "step_end"  # 对话一轮循环结束

    AfterStepAction = "after_step_action"  # 一轮Action结束(可能包含多个action)
    AfterAction = "after_action"  # 一个action结束

    AfterMemoryWrite = "after_memory_write"  # memory写入完成


class Payload(BaseModel):
    def to_dict(self):
        self.model_dump()


class Event(BaseModel, Generic[PAYLOAD]):
    event_type: EventType = Field(..., description="事件类型")
    payload: PAYLOAD = Field(..., description="事件内容")


class ChatPayload(Payload):
    received_message_id: Optional[str] = None
    received_message_content: Optional[str] = None


class ChatStartEvent(Event[ChatPayload]):
    """Agent对话开启"""
    event_type: EventType = EventType.ChatStart


class ChatEndEvent(Event[ChatPayload]):
    """Agent对话结束"""
    event_type: EventType = EventType.ChatEnd


class StepPayload(Payload):
    message_id: Optional[str] = None  # 当前轮次message_id
    step_counter: Optional[int] = None  # 当前第几轮循环


class StepStartEvent(Event[StepPayload]):
    """对话一轮循环开始"""
    event_type: EventType = EventType.StepStart


class StepEndEvent(Event[StepPayload]):
    """对话一轮循环结束"""
    event_type: EventType = EventType.StepEnd


class ActionPayload(Payload):
    action_output: Optional[Any] = None  # ActionOutput


class AfterStepActionEvent(Event[ActionPayload]):
    """一轮Action结束(可能包含多个action)"""
    event_type: EventType = EventType.AfterStepAction


class AfterActionEvent(Event[ActionPayload]):
    """一个action结束"""
    event_type: EventType = EventType.AfterAction


class MemoryWritePayload(Payload):
    fragment: Optional[Any] = None  # AgentMemoryFragment 写入的memory


class AfterMemoryWriteEvent(Event[MemoryWritePayload]):
    event_type: EventType = EventType.AfterMemoryWrite
