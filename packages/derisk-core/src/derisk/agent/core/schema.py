"""Schema definition for the agent."""
from __future__ import annotations
import inspect
import time

from enum import Enum
from typing import Optional, List, Dict, Any

from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict, Field
from derisk.core import ModelInferenceMetrics


class PluginStorageType(Enum):
    """Plugin storage type."""

    Git = "git"
    Oss = "oss"


class ApiTagType(Enum):
    """API tag type."""

    API_VIEW = "derisk_view"
    API_CALL = "derisk_call"


class Status(Enum):
    """Status of a task."""

    TODO = "todo"
    RUNNING = "running"
    WAITING = "waiting"
    RETRYING = "retrying"
    FAILED = "failed"
    COMPLETE = "complete"


class DynamicParamType(Enum):
    SYSTEM = "system"
    AGENT = "agent"
    CUSTOM = "custom"


class DynamicParamRenderType(Enum):
    DEFAULT = "default"
    VIS = "vis"


class AgentSpaceMode(Enum):
    WORK_SPACE = "work_space"
    MESSAGE_SPACE = "message_space"
    BLANk_SPACE = "blank_space"


class DynamicParam(BaseModel):
    model_config = ConfigDict(title=f"DynamicParam",
                              use_enum_values=True,  # 关键配置：自动序列化枚举值为字符串
                              arbitrary_types_allowed=True,  # 如果 config 包含非基础类型可能需要
                              )

    key: str = Field(
        ...,
        description="The dynamic param key.",
    )
    name: Optional[str] = Field(
        ...,
        description="The dynamic param name.",
    ),
    type: Optional[str] = Field(
        ...,
        description="The dynamic param type.",
    )
    value: Optional[Any] = Field(
        None,
        description="The param values of dynamic param.",
    )
    default_value: Optional[List[str]] = Field(
        None,
        description="The param values of dynamic param.",
    )
    description: Optional[str] = Field(
        None,
        description="The dynamic param description.",
    )
    config: Optional[Any] = Field(
        None,
        description="The dynamic param config.",
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class DynamicParamView(DynamicParam):
    render_mode: Optional[str] = Field(
        "markdown",
        description="The dynamic param render mode, can use vis/markdown.",
    )
    render_content: Optional[str] = Field(
        None,
        description="Content after dynamic parameter rendering.",
    )
    can_render: bool = Field(
        True,
        description="The variable can be rendered as a visual component"
    )


class Variable:
    def __init__(self, name, description, value_func):
        self.name = name
        self.description = description
        self.value_func = value_func
        self.agent_inst: Optional["ConversableAgent"] = None

    def get_value(self):
        """动态判断是否需要传递self参数"""
        args = inspect.getfullargspec(self.value_func).args
        if len(args) == 0:
            return self.value_func()
        else:
            return self.value_func(self)  # 传递自身实例




class ActionInferenceMetrics(BaseModel):
    start_time_ms: Optional[int] = None
    """The timestamp (in milliseconds) when the action inference starts."""

    end_time_ms: Optional[int] = None
    """The timestamp (in milliseconds) when the action inference ends."""

    current_time_ms: Optional[int] = None
    """The current timestamp (in milliseconds) when the action inference return
    partially output(stream)."""

    first_result_time_ms: Optional[int] = None
    """The timestamp (in milliseconds) when the first action result is generated."""

    result_tokens: Optional[int] = None
    """The total number of tokens (action result)."""

    cost_seconds: Optional[int] = None
    """The total number of action cost (action cost)."""

    def to_dict(self) -> Dict:
        """Convert the model inference metrics to dict."""
        return model_to_dict(self)

    @staticmethod
    def create_metrics(
        last_metrics: Optional["ActionInferenceMetrics"] = None,
    ) -> "ActionInferenceMetrics":
        """Create metrics for model inference.

        Args:
            last_metrics(ModelInferenceMetrics): The last metrics.

        Returns:
            ModelInferenceMetrics: The metrics for model inference.
        """
        start_time_ms = last_metrics.start_time_ms if last_metrics else None
        first_result_time_ms = last_metrics.first_result_time_ms if last_metrics else None
        result_tokens = last_metrics.result_tokens if last_metrics else None

        if not start_time_ms:
            start_time_ms = time.time_ns() // 1_000_000
        current_time_ms = time.time_ns() // 1_000_000
        end_time_ms = current_time_ms

        # 计算速度
        cost_seconds = 0
        if start_time_ms and end_time_ms :
            cost_seconds = (end_time_ms - start_time_ms) // 1000

        return ActionInferenceMetrics(
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            current_time_ms=current_time_ms,
            first_result_time_ms=first_result_time_ms,
            result_tokens=result_tokens,
            cost_seconds=cost_seconds,
        )


class MessageMetrics(BaseModel):
    llm_metrics: Optional[ModelInferenceMetrics] = None
    """模型性能指标信息"""
    action_metrics: Optional[ActionInferenceMetrics] = None
    """Action性能指标信息"""
    start_time_ms:  Optional[int] = None
    """消息开始时间戳"""
    end_time_ms:  Optional[int] = None
    """消息结束时间戳"""
    retry_count: Optional[int] = None
    """本次消息答案生成重试次数"""
    context_complete: Optional[int] = None
    """上下文准备完成时间戳"""

    def to_dict(self) -> Dict:
        """Convert the model inference metrics to dict."""
        return {
            "llm_metrics": self.llm_metrics.to_dict() if self.llm_metrics else None,
            "action_metrics": self.action_metrics.to_dict() if self.action_metrics else None,
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "retry_count": self.retry_count,
            "context_complete": self.context_complete,
        }
