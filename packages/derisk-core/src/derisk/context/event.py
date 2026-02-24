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

    AfterLLMInvoke = "after_llm_invoke"  # 模型调用结束
    AfterMemoryWrite = "after_memory_write"  # memory写入完成


class Payload(BaseModel):
    def to_dict(self):
        self.model_dump()


class ChatPayload(Payload):
    received_message_id: Optional[str] = None
    received_message_content: Optional[str] = None


class MemoryWritePayload(Payload):
    fragment: Optional[Any] = None  # AgentMemoryFragment 写入的memory


class StepPayload(Payload):
    message_id: Optional[str] = None  # 当前轮次message_id


class ActionPayload(Payload):
    action_output: Optional[Any] = None  # ActionOutput


class LLMPayload(Payload):
    model_name: str = None  # 模型名
    metrics: Optional[dict] = None  # AgentLLMOut.metrics.to_dict()
    messages: list[dict] = None  # 调用模型的消息 [AgentMessage.to_dict()]


class Event(BaseModel, Generic[PAYLOAD]):
    event_type: EventType = Field(..., description="事件类型")
    payload: PAYLOAD = Field(..., description="事件内容")
    task_id: str = Field(..., description="上下文ID(task_id)")


PAYLOAD_TYPE = {
    EventType.ChatStart: ChatPayload,  # Agent对话开启
    EventType.ChatEnd: ChatPayload,  # Agent对话结束
    EventType.StepStart: StepPayload,  # 对话一轮循环开始
    EventType.StepEnd: StepPayload,  # 对话一轮循环结束
    EventType.AfterStepAction: ActionPayload,  # 一轮Action结束(可能包含多个action)
    EventType.AfterAction: ActionPayload,  # 一个action结束
    EventType.AfterLLMInvoke: LLMPayload,  # LLM调用结束
    EventType.AfterMemoryWrite: MemoryWritePayload,  # Memory写入
}
