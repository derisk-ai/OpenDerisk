"""Schema definition for the agent."""
from __future__ import annotations
import inspect

from enum import Enum
from typing import Optional, List, Dict, Any

from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict, Field


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
