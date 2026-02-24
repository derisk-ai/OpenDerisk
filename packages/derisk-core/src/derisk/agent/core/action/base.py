"""Base Action class for defining agent actions."""
import dataclasses
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
)

from ..schema import ActionInferenceMetrics, Status
from ...resource.base import Resource, ResourceType
from ...._private.pydantic import (
    BaseModel,
    field_default,
    field_description,
    model_fields,
    model_to_dict,
    model_validator,
    ValidationError
)
from ....util.json_utils import find_json_objects
from ....vis import VisProtocolConverter
from ....vis.base import Vis
from ....vis.vis_converter import DefaultVisConverter

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Union[BaseModel, List[BaseModel], None])

JsonMessageType = Union[Dict[str, Any], List[Dict[str, Any]]]

@dataclasses.dataclass
class ToolCall:
    name: str
    args: Optional[Dict] = None
    tool_call_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)
    thought: Optional[str] = None

class OutputType(Enum):
    JSON = "json"
    MARKDOWN = "markdown"
    FILE = "file"


class AskUserType(Enum):
    """向用户提问的类型"""
    NESTED_ACTION = "nested_action"  # 嵌套Action 实际的类型需要查看子Action
    NESTED_AGENT = "nested_agent"  # 嵌套Action 实际的类型需要查看子Agent
    BEFORE_ACTION = "before_action"  # 动作执行前需要用户确认
    AFTER_ACTION = "after_action"  # 动作执行后需要用户确认
    CONCLUSION_INCOMPLETE = "conclusion_incomplete"  # 不完整的结论 需要用户补充信息


class ActionOutput(BaseModel):
    """Action output model."""

    content: str
    action_id: str = uuid.uuid4().hex
    name: Optional[str] = None  # 当前结论输出的Action名字
    content_summary: Optional[str] = None  # content总结
    is_exe_success: bool = True
    start_time: Optional[datetime] = None  # 记录开始执行时间
    view: Optional[str] = None  # 给人看的信息
    simple_view: Optional[str] = None  # 最简单的给人看的消息，比如不带参数的工具结果，没有代码的执行结果
    model_view: Optional[str] = None  # 多轮聊天 给模型看的信息

    action_intention: Optional[str] = None  # 本次action对应的intention
    action_reason: Optional[str] = None  # 本次action对应的reason
    resource_type: Optional[str] = None
    resource_value: Optional[Any] = None
    action: Optional[str] = None
    action_name: Optional[str] = None
    action_input: Optional[Any] = None
    thoughts: Optional[str] = None
    observations: Optional[str] = None

    have_retry: Optional[bool] = True
    ask_user: Optional[bool] = False
    ask_type: Optional[str] = None  # 想用户询问内容的类型
    # 如果当前agent能确定下个发言者，需要在这里指定
    next_speakers: Optional[List[str]] = None
    # Terminate the conversation, it is a special action
    # If terminate is True, it means the conversation is over, it will stop the
    # conversation loop forcibly.
    terminate: Optional[bool] = None
    # Memory fragments of current conversation, we can recover the conversation at any
    # time.
    memory_fragments: Optional[Dict[str, Any]] = None
    extra: Optional[dict[str, Any]] = None
    cost_ms: Optional[float] = None
    # 输出文件列表
    output_files: Optional[List[Any]] = None
    state: Optional[str] = None

    # 当前Action的运行指标
    metrics: Optional[ActionInferenceMetrics] = None

    # 是否评测模式
    eval_mode: Optional[bool] = False
    # 评测模式下运行过程数据展示
    eval_view: Optional[dict[str, Any]] = None

    # 是否流式Action
    stream: bool = False


    @model_validator(mode="before")
    @classmethod
    def pre_fill(cls, values: Any) -> Any:
        """Pre-fill the values."""
        if not isinstance(values, dict):
            return values
        is_exe_success = values.get("is_exe_success", True)
        if not is_exe_success and "observations" not in values:
            values["observations"] = values.get("content")
        return values

    @classmethod
    def from_dict(
        cls: Type["ActionOutput"], param: Optional[Dict]
    ) -> Optional["ActionOutput"]:
        """Convert dict to ActionOutput object."""
        if not param:
            return None
        return cls.model_validate(param)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the object to a dictionary."""
        return model_to_dict(self)

    @classmethod
    def parse_action_reports(cls, raw: Union[str, bytes]) -> List["ActionOutput"]:
        """
        Parse raw string (JSON) into a list of ActionOutput objects.

        Supports:
          - Single object: '{"content": "..."}'
          - List of objects: '[{"content": "..."}, {...}]'

        Always returns a list.
        """
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode action_report as JSON: {e}")
            # Fallback: treat raw as content of a single ActionOutput
            return [ActionOutput(name=cls.name,content=str(raw))]

        if isinstance(data, dict):
            # Single object
            try:
                if "action_id" not in data or not data['action_id']:
                    data['action_id'] = uuid.uuid4().hex
                return [ActionOutput.model_validate(data)]
            except ValidationError as e:
                logger.warning(f"Validation error for single ActionOutput: {e}")
                return [ActionOutput(content=json.dumps(data, ensure_ascii=False))]

        elif isinstance(data, list):
            # List of objects
            outputs = []
            for item in data:
                if isinstance(item, dict):
                    try:
                        outputs.append(ActionOutput.model_validate(item))
                    except ValidationError as e:
                        logger.warning(f"Skip invalid ActionOutput item: {e}")
                        # Optionally fallback to raw string
                        outputs.append(ActionOutput(content=json.dumps(item, ensure_ascii=False)))
                else:
                    # Non-dict item in list → wrap as content
                    outputs.append(ActionOutput(content=str(item)))
            return outputs

        else:
            # Unexpected type (int, str, etc.)
            logger.warning(f"Unexpected action_report type: {type(data)}")
            return [ActionOutput(content=str(data))]


class Action(ABC, Generic[T]):
    """Base Action class for defining agent actions."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if 'name' not in cls.__dict__:
            _name = cls.__name__
            if _name.endswith("Action"):
                cls.name = _name[:-6]
            cls.name = _name

    def __init__(self, language: str = "en", name: Optional[str] = None, **kwargs):
        """Create an action."""
        self.resource: Optional[Resource] = kwargs.get("resource")
        self.language: str = language
        self._name = name
        self.action_input: Optional[T] = kwargs.get("action_input")
        self.init_params: Optional[Dict] = kwargs.get("init_params", {})
        self.action_view_tag: Optional[str] = None
        self.intention: Optional[str] = None
        self.reason: Optional[str] = None
        self._render: Optional[VisProtocolConverter] = kwargs.get(
            "render_protocol", DefaultVisConverter()
        )
        self._action_uid = kwargs.get("action_uid") if kwargs.get("action_uid") else uuid.uuid4().hex

    async def init_action(self, **kwargs):
        self._render: VisProtocolConverter = kwargs.get(
            "render_protocol", DefaultVisConverter()
        )

    @property
    def action_uid(self):
        return self._action_uid

    @action_uid.setter
    def action_uid(self, value):
        self._action_uid = value

    @property
    def render_protocol(self) -> Optional[Vis]:
        """Return the render protocol."""
        if self.action_view_tag:
            return self._render.vis_inst(self.action_view_tag)
        else:
            return None

    def init_resource(self, resource: Optional[Resource]):
        """Initialize the resource."""
        self.resource = resource

    @property
    def resource_need(self) -> Optional[ResourceType]:
        """Return the resource type needed for the action."""
        return None


    @classmethod
    def get_action_description(cls) -> str:
        """Return the action description."""
        return cls.__doc__ or ""

    def render_prompt(self) -> Optional[str]:
        """Return the render prompt."""
        if self.render_protocol is None:
            return None
        else:
            return self.render_protocol.render_prompt()

    def _create_example(
        self,
        model_type,
    ) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        if model_type is None:
            return None
        origin = get_origin(model_type)
        args = get_args(model_type)
        if origin is None:
            example = {}
            single_model_type = cast(Type[BaseModel], model_type)
            for field_name, field in model_fields(single_model_type).items():
                description = field_description(field)
                default_value = field_default(field)
                if description:
                    example[field_name] = description
                elif default_value:
                    example[field_name] = default_value
                else:
                    example[field_name] = ""
            return example
        elif origin is list or origin is List:
            element_type = cast(Type[BaseModel], args[0])
            if issubclass(element_type, BaseModel):
                list_example = self._create_example(element_type)
                typed_list_example = cast(Dict[str, Any], list_example)
                return [typed_list_example]
            else:
                raise TypeError("List elements must be BaseModel subclasses")
        else:
            raise ValueError(
                f"Model type {model_type} is not an instance of BaseModel."
            )

    @property
    def out_model_type(self):
        """Return the output model type."""
        return None

    @property
    def ai_out_schema_json(self) -> Optional[str]:
        """Return the AI output json schema."""
        if self.out_model_type is None:
            return None
        return json.dumps(
            self._create_example(self.out_model_type), indent=2, ensure_ascii=False
        )

    @property
    def ai_out_schema(self) -> Optional[str]:
        """Return the AI output schema."""

        json_format_data = self.ai_out_schema_json
        if json_format_data:
            return f"""Please reply strictly in the following json format:
            {json_format_data}
            Make sure the reply content only has the correct json."""  # noqa: E501
        else:
            return None

    def _ai_message_2_json(self, ai_message: str) -> JsonMessageType:
        json_objects = find_json_objects(ai_message)
        json_count = len(json_objects)
        if json_count < 1:
            raise ValueError("Unable to obtain valid output.")
        return json_objects[0]

    def _input_convert(self, ai_message: str, cls: Type[T]) -> T:
        json_result = self._ai_message_2_json(ai_message)
        if get_origin(cls) is list:
            inner_type = get_args(cls)[0]
            typed_cls = cast(Type[BaseModel], inner_type)
            return [typed_cls.model_validate(item) for item in json_result]  # type: ignore
        else:
            typed_cls = cast(Type[BaseModel], cls)
            return typed_cls.model_validate(json_result)

    @classmethod
    def parse_action(
        cls,
        tool_call: ToolCall,
        default_action: Optional["Action"] = None,
        resource: Optional[Resource] = None,
        **kwargs,
    ) -> Optional["Action"]:
        """Parse the action from the message.

        If you want skip the action, return None.
        """
        return default_action

    async def before_run(self, **kwargs):
        self._action_uid = kwargs.get("action_uid", uuid.uuid4().hex)

    async def init_out(self, view:str = None):
        return ActionOutput(
            name=self.name,
            content='执行中...',
            action='执行中...',
            action_input='执行中...',
            view=view,
            action_id=self.action_uid,
            state=Status.RUNNING.value,
        )

    @abstractmethod
    async def run(
        self,
        ai_message: str = None,
        resource: Optional[Resource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        received_message: Optional["AgentMessage"] = None,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action."""

    async def terminate(self, message_id: str):
        pass
