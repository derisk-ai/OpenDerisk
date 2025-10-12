"""Agent Interface."""

from __future__ import annotations

import dataclasses
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union, Iterable, TypeVar, Type

from derisk.core import LLMClient, HumanMessage
from derisk.util.annotations import PublicAPI
from .action.base import ActionOutput
from .memory.agent_memory import AgentMemory
from .memory.gpts import GptsMessage
from .memory.gpts.base import GptsMessageType
from .schema import MessageMetrics
from ...core.interface.media import MediaContentType, MediaContent, MediaObject
from ...core.schema.types import ChatCompletionUserMessageParam, ChatCompletionMessageParam
from ...util.json_utils import serialize

MEDIA_PARAMS: List[str] = ["image_url", "audio_url", "input_audio", "video_url", "file_url"]

ENV_CONTEXT_KEY = "derisk_context_env"
LLM_CONTEXT_KEY = "derisk_context_llm"


class MediaMessageContent:

    def __init__(
        self,
        param_name: str,
        content_type: MediaContentType,

    ):
        self.content_type: MediaContentType = content_type
        self.param_name = param_name


class MediaMessageType(Enum):
    TEXT = MediaMessageContent("text", MediaContentType.TEXT)
    IMAGE = MediaMessageContent("image_url", MediaContentType.IMAGE)
    AUDIO = MediaMessageContent("audio_url", MediaContentType.AUDIO)
    AUDIO_INPUT = MediaMessageContent("input_audio", MediaContentType.AUDIO)
    VIDEO = MediaMessageContent("video_url", MediaContentType.VIDEO)

    @staticmethod
    def of_param(param_name: str):
        return [x for x in MediaMessageType if param_name == x.param_name][0]

    @property
    def content_type(self):
        return self._value_.content_type

    @property
    def param_name(self):
        return self._value_.param_name


class Agent(ABC):
    """Agent Interface."""

    @abstractmethod
    async def send(
        self,
        message: AgentMessage,
        recipient: Agent,
        reviewer: Optional[Agent] = None,
        request_reply: Optional[bool] = True,
        is_recovery: Optional[bool] = False,
        silent: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
    ) -> None:
        """Send a message to recipient agent.

        Args:
            message(AgentMessage): the message to be sent.
            recipient(Agent): the recipient agent.
            reviewer(Agent): the reviewer agent.
            request_reply(bool): whether to request a reply.
            is_recovery(bool): whether the message is a recovery message.

        Returns:
            None
        """

    @abstractmethod
    async def receive(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
        is_recovery: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
    ) -> None:
        """Receive a message from another agent.

        Args:
            message(AgentMessage): the received message.
            sender(Agent): the sender agent.
            reviewer(Agent): the reviewer agent.
            request_reply(bool): whether to request a reply.
            silent(bool): whether to be silent.
            is_recovery(bool): whether the message is a recovery message.

        Returns:
            None
        """

    @abstractmethod
    async def generate_reply(
        self,
        received_message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        **kwargs,
    ) -> AgentMessage:
        """Generate a reply based on the received messages.

        Args:
            received_message(AgentMessage): the received message.
            sender: sender of an Agent instance.
            reviewer: reviewer of an Agent instance.
            rely_messages: a list of messages received.

        Returns:
            AgentMessage: the generated reply. If None, no reply is generated.
        """

    @abstractmethod
    async def thinking(
        self,
        messages: List[AgentMessage],
        reply_message_id: str,
        sender: Optional[Agent] = None,
        prompt: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Think and reason about the current task goal.

        Based on the requirements of the current agent, reason about the current task
        goal through LLM

        Args:
            messages(List[AgentMessage]): the messages to be reasoned
            prompt(str): the prompt to be reasoned

        Returns:
            Tuple[Union[str, Dict, None], Optional[str]]: First element is the generated
                reply. If None, no reply is generated. The second element is the model
                name of current task.
        """

    @abstractmethod
    async def review(self, message: Optional[str], censored: Agent) -> Tuple[bool, Any]:
        """Review the message based on the censored message.

        Args:
            message:
            censored:

        Returns:
            bool: whether the message is censored
            Any: the censored message
        """

    @abstractmethod
    async def agent_state(self):
        """获取Agent实例的运行状态

        """

    @abstractmethod
    async def act(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        **kwargs,
    ) -> ActionOutput:
        """Act based on the LLM inference results.

        Parse the inference results for the current target and execute the inference
        results using the current agent's executor

        Args:
            message: the message to be executed
            sender: sender of an Agent instance.
            reviewer: reviewer of an Agent instance.
            **kwargs:

        Returns:
             ActionOutput: the action output of the agent.
        """

    @abstractmethod
    async def verify(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        **kwargs,
    ) -> Tuple[bool, Optional[str]]:
        """Verify whether the current execution results meet the target expectations.

        Args:
            message: the message to be verified
            sender: sender of an Agent instance.
            reviewer: reviewer of an Agent instance.
            **kwargs:

        Returns:
            Tuple[bool, Optional[str]]: whether the verification is successful and the
                verification result.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the agent."""

    @property
    @abstractmethod
    def avatar(self) -> str:
        """Return the avatar of the agent."""

    @property
    @abstractmethod
    def role(self) -> str:
        """Return the role of the agent."""

    @property
    @abstractmethod
    def desc(self) -> Optional[str]:
        """Return the description of the agent."""


@dataclasses.dataclass
class AgentContext:
    """A class to represent the context of an Agent."""

    conv_id: str
    conv_session_id: str
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    rpc_id: Optional[str] = None
    ## 当前对话的主Agent(应用)信息
    gpts_app_code: Optional[str] = None
    gpts_app_name: Optional[str] = None
    ## 当前Agent的ID(应用APP CODE, 记忆模块强依赖，如果未赋值记忆模块会错乱)
    agent_app_code: Optional[str] = None
    language: Optional[str] = None
    max_chat_round: int = 100
    max_retry_round: int = 10
    max_new_tokens: int = 0
    temperature: float = 0.5
    allow_format_str_template: Optional[bool] = False
    verbose: bool = False

    app_link_start: bool = False
    # 是否开启VIS协议消息模式，默认开启
    enable_vis_message: bool = True
    # 是否增量流式输出模型输出信息
    incremental: bool = True
    # 是否开启流式输出(默认开启，如果agent强制定义关闭，则无法开启，但是定义开启的可通过这个属性关闭)
    stream: bool = True

    output_process_message: bool = True
    extra: dict[str, Any] = None
    env_context: dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the AgentContext."""
        return dataclasses.asdict(self)


@dataclasses.dataclass
@PublicAPI(stability="beta")
class AgentGenerateContext:
    """A class to represent the input of a Agent."""

    message: Optional[AgentMessage]
    sender: Agent
    receiver: "Agent" = None
    reviewer: Optional[Agent] = None
    silent: Optional[bool] = False

    already_failed: bool = False
    last_speaker: Optional[Agent] = None

    already_started: bool = False
    begin_agent: Optional[str] = None

    rely_messages: List[AgentMessage] = dataclasses.field(default_factory=list)
    final: Optional[bool] = True

    memory: Optional[AgentMemory] = None
    agent_context: Optional[AgentContext] = None
    llm_client: Optional[LLMClient] = None

    round_index: Optional[int] = None

    def to_dict(self) -> Dict:
        """Return a dictionary representation of the AgentGenerateContext."""
        return dataclasses.asdict(self)


ActionReportType = ActionOutput
MessageContextType = Dict[str, Any]
ResourceReferType = Dict[str, Any]


@dataclasses.dataclass
@PublicAPI(stability="beta")
class AgentReviewInfo:
    """Message object for agent communication."""

    approve: bool = False
    comments: Optional[str] = None

    def copy(self) -> "AgentReviewInfo":
        """Return a copy of the current AgentReviewInfo."""
        return AgentReviewInfo(approve=self.approve, comments=self.comments)

    def to_dict(self) -> Dict:
        """Return a dictionary representation of the AgentMessage."""
        return dataclasses.asdict(self)


class ContextEngineeringKey(str, Enum):
    AVAILABLE_TOOLS = "available_tools",
    AVAILABLE_KNOWLEDGE = "available_knowledge",
    AVAILABLE_AGENTS = "available_agents",
    LAST_STEP_MESSAGE_ID = "last_step_message_id",


@dataclasses.dataclass
@PublicAPI(stability="beta")
class AgentMessage:
    """Message object for agent communication."""

    message_id: Optional[str] = None
    content: Optional[Union[str, ChatCompletionUserMessageParam]] = None
    content_types: Optional[List[str]] = None
    message_type: Optional[str] = GptsMessageType.AgentMessage.value
    thinking: Optional[str] = None
    name: Optional[str] = None
    rounds: int = 0
    round_id: Optional[str] = None
    context: Optional[MessageContextType] = None
    action_report: Optional[ActionReportType] = None
    review_info: Optional[AgentReviewInfo] = None
    current_goal: Optional[str] = None
    goal_id: Optional[str] = None
    model_name: Optional[str] = None
    role: Optional[str] = None
    success: bool = True
    resource_info: Optional[ResourceReferType] = None
    show_message: bool = True
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    gmt_create: Optional[datetime] = None

    observation: Optional[str] = None
    metrics: Optional[MessageMetrics] = None
    """当前消息的性能指标数据(模型和action)"""

    def to_dict(self) -> Dict:
        """Return a dictionary representation of the AgentMessage."""
        result = dataclasses.asdict(self)

        if self.action_report:
            result["action_report"] = (
                self.action_report.to_dict()
            )  # 将 action_report 转换为字典
        return result

    def to_llm_message(self) -> Dict[str, Any]:
        """Return a dictionary representation of the AgentMessage."""
        content = self.content
        action_report = self.action_report
        if action_report:
            content = action_report.content
        media_contents = []
        have_text_content = False
        if self.content_types:
            for content_type in self.content_types:
                media_type = MediaMessageType.of_param(content_type)
                if media_type.content_type == MediaContentType.TEXT:
                    have_text_content = True
                    media_contents.append(
                        MediaContent(type=media_type.content_type.value,
                                     object=MediaObject(format="text", data=self.content)))
                else:
                    if content_type in self.context:
                        media_contents.append(
                            MediaContent(type=media_type.content_type.value,
                                         object=MediaObject(format="url", data=self.context[content_type])))
            if not have_text_content:
                media_contents.append(MediaContent(type=MediaContentType.TEXT.value,
                                                   object=MediaObject(format="text", data=content)))
            return {
                "content": media_contents,
                "context": self.context,
                "role": self.role,
            }
        else:
            return {
                "content": content,  # use tool data as message
                "context": self.context,
                "role": self.role,
            }

    @classmethod
    def init_new(
        cls,
        content: Optional[str] = None,
        content_types: Optional[List[str]] = None,
        current_goal: Optional[str] = None,
        goal_id: Optional[str] = None,
        context: Optional[dict] = None,
        rounds: Optional[int] = None,
        name: Optional[str] = None,
        role: Optional[str] = None,
        show_message: bool = True,
        observation: Optional[str] = None,
        conv_round_id: Optional[str] = None,
    ):
        return cls(
            message_id=uuid.uuid4().hex,
            content=content,
            content_types=content_types,
            current_goal=current_goal,
            goal_id=goal_id,
            context=context,
            rounds=rounds,
            round_id=conv_round_id or uuid.uuid4().hex,
            name=name,
            role=role,
            show_message=show_message,
            gmt_create=datetime.now(),
            observation=observation,
        )

    @classmethod
    def from_dict_message(cls, message: Dict[str, Any]) -> AgentMessage:
        """Create an AgentMessage object from a dictionary."""
        return cls(
            message_id=uuid.uuid4().hex,
            content=message.get("content"),
            context=message.get("context"),
            role=message.get("role"),
            rounds=message.get("rounds", 0),
        )

    @classmethod
    def from_messages(cls, messages: List[Dict[str, Any]]) -> List[AgentMessage]:
        """Create a list of AgentMessage objects from a list of dictionaries."""
        results = []
        field_names = [f.name for f in dataclasses.fields(cls)]
        for message in messages:
            kwargs = {
                key: value for key, value in message.items() if key in field_names
            }
            kwargs["message_id"] = uuid.uuid4().hex
            results.append(cls(**kwargs))
        return results

    @classmethod
    def from_gpts_message(cls, gpts_message: GptsMessage) -> AgentMessage:
        T = TypeVar("T")

        def _str_to_type(kwargs: dict, field_name: str, cls: Type[T] = None) -> T:
            if field_name in kwargs and isinstance(kwargs.get(field_name), str):
                kwargs[field_name] = cls(**json.loads(kwargs.get(field_name)))

        field_names = [f.name for f in dataclasses.fields(cls)]
        items = gpts_message.to_dict()
        kwargs = {key: value for key, value in items.items() if key in field_names}
        _str_to_type(kwargs, "action_report", ActionOutput)
        _str_to_type(kwargs, "review_info", AgentReviewInfo)
        message: AgentMessage = cls(**kwargs)
        return message


    @classmethod
    def from_media_messages(cls, message: Union[str, HumanMessage], current_goal: Optional[str] = None,
                            rounds: int = 0, context: Optional[Any] = None) -> AgentMessage:
        """Create a  AgentMessage objects from a media message."""

        if not message:
            raise ValueError("The message is empty")

        if isinstance(message, str):
            return AgentMessage(
                message_id=uuid.uuid4().hex,
                content=message,
                context=context,
                current_goal=current_goal if current_goal else message,
                rounds=rounds,
                content_types=[MediaContentType.TEXT],
            )

        content = message.content
        if not content:
            raise ValueError(f"Failed to parse {message}, no content found")
        if not isinstance(content, Iterable):
            raise ValueError(f"Failed to parse {message}, content is not iterable")

        if isinstance(content, str):
            return AgentMessage(
                message_id=uuid.uuid4().hex,
                content=content,
                context=context,
                current_goal=current_goal if current_goal else content,
                rounds=rounds,
                content_types=[MediaContentType.TEXT],
            )

        context = context or {}
        text_content = None
        media_types = []
        for item in content:
            if isinstance(item, str):
                text_content = item
                media_types.append("text")
            elif isinstance(item, MediaContent):
                type = item.type
                if type == "text":
                    text_content = item.object.data
                    media_types.append("text")
                elif type == MediaContentType.IMAGE.value:
                    context.update({"image_url": item.object.data})
                    media_types.append("image_url")
                elif type == MediaContentType.AUDIO.value:
                    if item.object.format == "url":
                        context.update({"audio_url": item.object.data})
                        media_types.append("audio_url")
                    else:
                        context.update({"input_audio": item.object.data})
                        media_types.append("input_audio")
                elif type == MediaContentType.VIDEO.value:
                    context.update({"video_url": item.object.data})
                    media_types.append("video_url")
                elif type == MediaContentType.FILE.value:
                    context.update({"file_url": item.object.data})
                    media_types.append("file_url")
                else:
                    raise ValueError(f"Unknown message type: {item} of system message")
            else:
                raise ValueError(f"Unknown message type: {item} of system message")
        return AgentMessage(
            message_id=uuid.uuid4().hex,
            content=text_content,
            context=context,
            current_goal=current_goal if current_goal else text_content,
            rounds=rounds,
            content_types=media_types,
        )

    def copy(self) -> "AgentMessage":
        """Return a copy of the current AgentMessage."""
        copied_context: Optional[MessageContextType] = None
        if self.context:
            if isinstance(self.context, dict):
                copied_context = self.context.copy()
            else:
                copied_context = self.context

        copied_review_info = self.review_info.copy() if self.review_info else None
        return AgentMessage(
            content=self.content,
            thinking=self.thinking,
            name=self.name,
            context=copied_context,
            rounds=self.rounds,
            action_report=self.action_report,
            review_info=copied_review_info,
            current_goal=self.current_goal,
            goal_id=self.goal_id,
            model_name=self.model_name,
            role=self.role,
            success=self.success,
            resource_info=self.resource_info,
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
            gmt_create=self.gmt_create,
            message_type=self.message_type,
        )

    def get_dict_context(self) -> Dict[str, Any]:
        """Return the context as a dictionary."""
        if isinstance(self.context, dict):
            return self.context
        return {}

    def to_gpts_message(
        self,
        sender: "ConversableAgent",
        receiver: Optional["ConversableAgent"] = None,
        role: Optional[str] = None,
    ) -> GptsMessage:
        gpts_message: GptsMessage = GptsMessage(
            conv_id=sender.not_null_agent_context.conv_id,
            conv_session_id=sender.not_null_agent_context.conv_session_id,
            message_id=self.message_id if self.message_id else uuid.uuid4().hex,
            sender=sender.role,
            sender_name=sender.name,
            receiver=receiver.role if receiver else sender.role,
            receiver_name=receiver.name if receiver else sender.name,
            role=role,
            avatar=sender.avatar,
            rounds=self.rounds,
            is_success=self.success,
            app_code=sender.not_null_agent_context.agent_app_code or "",
            app_name=sender.name,
            current_goal=self.current_goal,
            goal_id=self.goal_id,
            content=self.content if self.content else "",
            thinking=self.thinking if self.thinking else "",
            context=(
                json.dumps(self.context, default=serialize, ensure_ascii=False)
                if self.context
                else None
            ),
            content_types=(
                json.dumps(self.content_types, default=serialize, ensure_ascii=False)
                if self.context
                else None
            ),
            message_type=self.message_type,
            review_info=(
                json.dumps(self.review_info.to_dict(), ensure_ascii=False)
                if self.review_info
                else None
            ),
            action_report=(
                json.dumps(self.action_report.to_dict(), default=serialize, ensure_ascii=False)
                if self.action_report
                else None
            ),
            model_name=self.model_name,
            resource_info=(
                json.dumps(self.resource_info) if self.resource_info else None
            ),
            user_prompt=self.user_prompt,
            system_prompt=self.system_prompt,
            show_message=self.show_message,
            created_at=self.gmt_create,
            observation=self.observation,
            metrics=json.dumps(self.metrics.to_dict(), default=serialize, ensure_ascii=False) if self.metrics else None,

        )
        return gpts_message
