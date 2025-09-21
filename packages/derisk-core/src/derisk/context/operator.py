from abc import abstractmethod, ABC
from enum import Enum
from typing import TypeVar, Generic, Any, Union, Dict, Optional

from derisk._private.pydantic import BaseModel, Field, model_to_dict
from derisk.context.event import Event, EventType

T = TypeVar("T")


class ConfigItemType(str, Enum):
    GROUP = "group",
    BOOLEAN = "bool",
    TEXTAREA = "textarea",
    INTEGER = "int",
    FLOAT = "slider"
    PROMPT = "textarea"
    ARRAY = "array"


ConfigItemUnion = Union["ValuedConfigItem", "GroupedConfigItem"]


class ConfigItem(BaseModel, ABC):
    type: ConfigItemType = Field(..., description="字段类型")  # 需要保证全局唯一
    name: str = Field(..., description="唯一标识")
    label: str = Field(..., description="中文标题")
    description: str = Field(..., description="描述")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)

    @abstractmethod
    def get(self, name: str) -> Any:
        """获取指定name的配置值"""
        raise NotImplementedError


class ValuedConfigItem(ConfigItem, Generic[T]):
    value: Optional[T] = Field(None, description="变量值 可以给一个默认值 运行时会被配置覆盖")
    required: Optional[bool] = Field(False, description="是否必填")
    options: Optional[list[T]] = Field(None, description="下拉列表可选值")
    min: Optional[float] = Field(None, description="最小值")
    max: Optional[float] = Field(None, description="最大值")
    step: Optional[float] = Field(None, description="滑动步长")

    def get(self, name: str) -> Any:
        """获取指定name的配置值"""
        return self.value if self.name == name else None


class DynamicConditionOperatorType(str, Enum):
    EQ = "=="


class ConfigDynamicCondition(BaseModel):
    name: str = Field(..., description="eg. 哪个开关打开了，这里就是开关字段name")
    operator: DynamicConditionOperatorType = Field(..., description="eg. ==/>=/in")
    value: Any = Field(..., description="eg. true")


class ConfigDynamic(BaseModel):
    condition: ConfigDynamicCondition = Field(..., description="动态显示条件")
    fields: list[ConfigItemUnion] = Field(..., description="条件满足时才显示的字段")


class GroupedConfigItem(ConfigItem):
    type: ConfigItemType = ConfigItemType.GROUP
    title_field: Optional[str] = Field(None, description="哪个字段需要展示在group title(即使group折叠也要展示")
    fields: Optional[list[ConfigItemUnion]] = Field(None, description="分组内的字段列表")
    dynamic: Optional[list[ConfigDynamic]] = Field(None, description="动态显示的字段")

    def get(self, name: str) -> Any:
        """获取指定name的配置值"""
        if self.fields:
            for field in self.fields:
                value = field.get(name)
                if value is not None:
                    return value

        if self.dynamic:
            for dynamic in self.dynamic:
                for field in dynamic.fields:
                    value = field.get(name)
                    if value is not None:
                        return value

        return None


class Operator(ABC):
    """上下文操作算子"""

    # 配置信息 Agent运行时动态构建
    config: ConfigItem = None

    def __init__(self, **kwargs):
        pass

    @classmethod
    @property
    def name(cls) -> str:
        """算子名称"""
        return cls.__name__

    @classmethod
    @abstractmethod
    def subscribed(cls) -> list[EventType]:
        """订阅哪些事件类型"""

    @abstractmethod
    async def handle(self, event: Event, agent: "ConversableAgent" = None, **kwargs):
        """处理上下文事件"""
