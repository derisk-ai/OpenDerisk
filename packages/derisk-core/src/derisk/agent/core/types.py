from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Union, Iterable

from .schema import MessageMetrics
from .action.base import ActionOutput
from ...core import HumanMessage
from ...core.interface.media import MediaContentType, MediaContent, MediaObject
from ...core.schema.types import ChatCompletionUserMessageParam
from ...util.annotations import PublicAPI


MEDIA_PARAMS: List[str] = ["image_url", "audio_url", "input_audio", "video_url", "file_url"]

ENV_CONTEXT_KEY = "derisk_context_env"
LLM_CONTEXT_KEY = "derisk_context_llm"

ActionReportType = List[ActionOutput]
MessageContextType = Dict[str, Any]
ResourceReferType = Dict[str, Any]


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
    FILE = MediaMessageContent("file_url", MediaContentType.FILE)
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


class MessageType(str, Enum):
    AgentMessage = "agent_message"
    ActionApproval = "action_approval"  # 用户同意执行某个动作
    RouterMessage = "router_message"  # 消息路由




@dataclasses.dataclass
@PublicAPI(stability="beta")
class AgentMessage:
    """Message object for agent communication."""
    message_id: Optional[str] = None
    content: Optional[Union[str, ChatCompletionUserMessageParam]] = None
    content_types: Optional[List[str]] = None
    message_type: Optional[str] = MessageType.AgentMessage.value
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
    tool_calls: Optional[List[Dict]] = None
    """当前消息的性能指标数据(模型和action)"""

    def to_dict(self) -> Dict:
        """Return a dictionary representation of the AgentMessage."""
        result = dataclasses.asdict(self)

        if self.action_report:
            result["action_report"] = ([item.to_dict() for item in self.action_report])  # 将 action_report 转换为字典
        if self.metrics:
            result["metrics"] = self.metrics.to_dict()
        return result

    def to_llm_message(self) -> Dict[str, Any]:
        """Return a dictionary representation of the AgentMessage."""
        content = self.content
        action_report = self.action_report
        if action_report:
            for item in action_report:
                content = content + "\n" + item.content
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
        message_id: Optional[str] = None,
    ):
        return cls(
            message_id=message_id or uuid.uuid4().hex,
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
            tool_calls=self.tool_calls,
        )

    def get_dict_context(self) -> Dict[str, Any]:
        """Return the context as a dictionary."""
        if isinstance(self.context, dict):
            return self.context
        return {}
