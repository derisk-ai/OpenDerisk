from typing import Optional, Type

from derisk._private.pydantic import BaseModel, Field, model_to_dict
from derisk.agent.core.base_parser import AgentParser, SchemaType


class TrackingInfo(BaseModel):
    """Tracking  Info model."""

    duration: int = Field(
        30,
        description="跟踪任务持续时长，如果用户没提到，默认值是30（注意他的使用时候时间单位是分钟）. ",
    )
    interval: int = Field(
        default=60,
        description="跟踪任务的执行间隔，默认60（注意他的使用时候时间单位是秒）.",
    )
    intent: str = Field(..., description="根据用户具体跟踪目标生成的使用具体代理来完成的单次任务指令(不包含调度相关信息)")
    instruction: str = Field(...,
                             description="跟踪任务的操作命令,可用选项[start, stop, update, pause, resume]. 如果当前对话记录里没提到已经有任务正在运行，这个值默认为start.")

    agent: str = Field(..., description="当前跟踪任务需要那个代理来执行，严格按照代理的能力描述和用户需求进行匹配")
    extra_info: Optional[dict] = Field(
        None,
        description="关键参数信息(结合‘代理'、‘工具’定义的需求和已知消息，搜集各种关键参数，如:目标、时间、位置等出现的有真实实际值的参数，确保后续‘agent’能结合'intent'正确运行，不包含调度相关信息)",
    )

    def to_dict(self):
        return model_to_dict(self)


class TrackingAgentParaser(AgentParser[TrackingInfo]):
    DEFAULT_SCHEMA_TYPE: SchemaType = SchemaType.JSON

    @property
    def model_type(self) -> Optional[Type[TrackingInfo]]:
        return TrackingInfo
