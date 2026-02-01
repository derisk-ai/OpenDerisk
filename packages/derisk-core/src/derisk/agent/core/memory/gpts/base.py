"""Gpts memory define."""

from __future__ import annotations

import dataclasses
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from derisk.core.schema.types import ChatCompletionUserMessageParam
from .agent_system_message import AgentSystemMessage
from ...schema import Status, MessageMetrics
from ...types import MessageContextType, ActionReportType, AgentReviewInfo, ResourceReferType, AgentMessage, MessageType


@dataclasses.dataclass
class GptsPlan:
    """Gpts plan."""

    conv_id: str
    conv_session_id: str
    conv_round: int
    sub_task_id: str
    task_uid: str
    sub_task_num: Optional[int] = 0
    sub_task_content: Optional[str] = ""
    task_parent: Optional[str] = None
    sub_task_title: Optional[str] = None
    sub_task_agent: Optional[str] = None
    resource_name: Optional[str] = None
    agent_model: Optional[str] = None
    retry_times: int = 0
    max_retry_times: int = 5
    state: Optional[str] = Status.TODO.value
    action: Optional[str] = None
    action_input: Optional[str] = None
    result: Optional[str] = None

    conv_round_id: Optional[str] = None
    task_round_title: Optional[str] = None
    task_round_description: Optional[str] = ""
    planning_agent: Optional[str] = None

    planning_model: Optional[str] = None
    gmt_create: Optional[str] = None
    created_at: datetime = dataclasses.field(default_factory=datetime.utcnow)
    updated_at: datetime = dataclasses.field(default_factory=datetime.utcnow)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GptsPlan":
        """Create a GptsPlan object from a dictionary."""
        return GptsPlan(
            conv_id=d["conv_id"],
            conv_session_id=d["conv_session_id"],
            conv_round=d["conv_round"],
            task_uid=d["task_uid"],
            sub_task_num=d["sub_task_num"],
            sub_task_id=d["sub_task_id"],
            conv_round_id=d.get("conv_round_id"),
            task_parent=d.get("task_parent"),
            sub_task_content=d["sub_task_content"],
            sub_task_agent=d["sub_task_agent"],
            resource_name=d["resource_name"],
            agent_model=d["agent_model"],
            retry_times=d["retry_times"],
            max_retry_times=d["max_retry_times"],
            state=d["state"],
            result=d["result"],
            task_round_title=d.get("task_round_title"),
            task_round_description=d.get("task_round_description"),
            planning_agent=d.get("planning_agent"),
            planning_model=d.get("planning_model"),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the GptsPlan object."""
        return dataclasses.asdict(self)


@dataclasses.dataclass
class GptsMessage:
    """Gpts message."""

    conv_id: str
    conv_session_id: str
    sender: str
    sender_name: str
    message_id: str
    role: str
    content: Optional[Union[str, ChatCompletionUserMessageParam]] = None
    rounds: int = 0
    content_types: Optional[List[str]] = None
    message_type: Optional[str] = MessageType.AgentMessage.value
    receiver: Optional[str] = None
    receiver_name: Optional[str] = None
    is_success: bool = True
    avatar: Optional[str] = None
    thinking: Optional[str] = None
    app_code: Optional[str] = None
    app_name: Optional[str] = None
    goal_id: Optional[str] = None
    current_goal: Optional[str] = None
    context: Optional[MessageContextType] = None
    action_report: Optional[ActionReportType] = None
    review_info: Optional[AgentReviewInfo] = None
    model_name: Optional[str] = None
    resource_info: Optional[ResourceReferType] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    show_message: bool = True

    created_at: datetime = dataclasses.field(default_factory=datetime.now)
    updated_at: datetime = dataclasses.field(default_factory=datetime.now)

    observation: Optional[str] = None
    metrics: Optional[MessageMetrics] = None
    tool_calls: Optional[List[Dict]] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GptsMessage":
        """Create a GptsMessage object from a dictionary."""
        return GptsMessage(
            conv_id=d["conv_id"],
            conv_session_id=d["conv_session_id"],
            message_id=d["message_id"],
            sender=d["sender"],
            sender_name=d["sender_name"],
            receiver=d["receiver"],
            receiver_name=d["receiver_name"],
            role=d["role"],
            avatar=d.get("avatar"),
            thinking=d["thinking"],
            content=d["content"],
            message_type=d["message_type"],
            rounds=d["rounds"],
            is_success=d["is_success"],
            app_code=d["app_code"],
            app_name=d["app_name"],
            model_name=d["model_name"],
            current_goal=d["current_goal"],
            context=d["context"],
            content_types=d.get("content_types"),
            review_info=d["review_info"],
            action_report=d["action_report"],
            resource_info=d["resource_info"],
            system_prompt=d["system_prompt"],
            user_prompt=d["user_prompt"],
            show_message=d["show_message"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            observation=d.get("observation"),
            metrics=d.get("metrics"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the GptsMessage object."""
        return dataclasses.asdict(self)

    def to_agent_message(self) -> AgentMessage:
        return AgentMessage(
            message_id=self.message_id,
            content=self.content,
            content_types=self.content_types,
            message_type=self.message_type,
            thinking=self.thinking,
            name=self.sender_name,
            rounds=self.rounds,
            round_id=None,  # GptsMessage 没有 round_id，设为 None
            context=self.context,
            action_report=self.action_report,
            review_info=self.review_info,
            current_goal=self.current_goal,
            goal_id=self.goal_id,
            model_name=self.model_name,
            role=self.role,
            success=self.is_success,
            resource_info=self.resource_info,
            show_message=self.show_message,
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
            gmt_create=self.created_at,  # 或 updated_at，按需选择
            observation=self.observation,
            metrics=self.metrics,
            tool_calls=self.tool_calls,
        )

    @classmethod
    def from_agent_message(
        cls,
        message: AgentMessage,
        sender: "ConversableAgent",
        receiver: Optional["ConversableAgent"] = None,
        role: Optional[str] = None,
    ) -> GptsMessage:
        return cls(
            ## 收发信息
            conv_id=sender.not_null_agent_context.conv_id,
            conv_session_id=sender.not_null_agent_context.conv_session_id,
            sender=sender.role,
            sender_name=sender.name,
            receiver=receiver.role if receiver else sender.role,
            receiver_name=receiver.name if receiver else sender.name,
            role=role or sender.role,
            avatar=sender.avatar,
            app_code=sender.not_null_agent_context.agent_app_code or "",
            app_name=sender.name,

            ## 消息内容
            message_id=message.message_id if message.message_id else uuid.uuid4().hex,
            content=message.content,
            rounds=message.rounds,
            content_types=message.content_types,
            message_type=message.message_type,
            is_success=message.success,
            thinking=message.thinking,
            goal_id=message.goal_id,
            current_goal=message.current_goal,
            context=message.context,
            action_report=message.action_report,
            review_info=message.review_info,
            model_name=message.model_name,
            resource_info=message.resource_info,
            system_prompt=message.system_prompt,
            user_prompt=message.user_prompt,
            show_message=message.show_message,
            created_at=message.gmt_create or datetime.now(),
            updated_at=message.gmt_create or datetime.now(),
            observation=message.observation,
            metrics=message.metrics,
            tool_calls=message.tool_calls,
        )

    def view(self) -> Optional[str]:
        """最终返回给User的结论view"""

        views = [view for item in (self.action_report or []) if (
            view := item.view or item.observations or item.content
        )]

        # 有action_report view则取view 否则取content
        return "\n".join(views) or self.content

    def answer(self) -> Optional[str]:
        """最终返回给User的结论content"""

        views = [view for item in (self.action_report or []) if (
            view := item.content or item.observations or item.view
        )]

        # 有action_report view则取view 否则取content
        return "\n".join(views) or self.content


class GptsPlansMemory(ABC):
    """Gpts plans memory interface."""

    @abstractmethod
    def batch_save(self, plans: List[GptsPlan]) -> None:
        """Save plans in batch.

        Args:
            plans: panner generate plans info

        """

    @abstractmethod
    async def get_by_conv_id(self, conv_id: str) -> List[GptsPlan]:
        """Get plans by conv_id.

        Args:
            conv_id: conversation id

        Returns:
            List[GptsPlan]: List of planning steps
        """

    @abstractmethod
    def get_by_planner(self, conv_id: str, planner: str) -> List[GptsPlan]:
        """Get plans by conv_id and planner.

        Args:
            conv_id: conversation id
            planner: planner
        Returns:
            List[GptsPlan]: List of planning steps
        """

    @abstractmethod
    def get_by_planner_and_round(self, conv_id: str, planner: str, round_id: str) -> List[GptsPlan]:
        """Get plans by conv_id and planner.

        Args:
            conv_id: conversation id
            planner: planner
            round_id: round_id
        Returns:
            List[GptsPlan]: List of planning steps
        """

    @abstractmethod
    def get_by_conv_id_and_num(
        self, conv_id: str, task_ids: List[str]
    ) -> List[GptsPlan]:
        """Get plans by conv_id and task number.

        Args:
            conv_id(str): conversation id
            task_ids(List[str]): List of sequence numbers of plans in the same
                conversation

        Returns:
            List[GptsPlan]: List of planning steps
        """

    @abstractmethod
    def get_todo_plans(self, conv_id: str) -> List[GptsPlan]:
        """Get unfinished planning steps.

        Args:
            conv_id(str): Conversation id

        Returns:
            List[GptsPlan]: List of planning steps
        """

    @abstractmethod
    def get_plans_by_msg_round(self, conv_id: str, rounds_id: str) -> List[GptsPlan]:
        """Get unfinished planning steps.

        Args:
            conv_id(str): Conversation id
            rounds_id(str): rounds id
        Returns:
            List[GptsPlan]: List of planning steps
        """

    @abstractmethod
    def complete_task(self, conv_id: str, task_id: str, result: str) -> None:
        """Set the planning step to complete.

        Args:
            conv_id(str): conversation id
            task_id(str): Planning step id
            result(str): Plan step results
        """

    @abstractmethod
    def update_task(
        self,
        conv_id: str,
        task_id: str,
        state: str,
        retry_times: int,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        result: Optional[str] = None,
    ) -> None:
        """Update planning step information.

        Args:
            conv_id(str): conversation id
            task_id(str): Planning step num
            state(str): the status to update to
            retry_times(int): Latest number of retries
            agent(str): Agent's name
            model(str): Model name
            result(str): Plan step results
        """

    @abstractmethod
    def update_by_uid(
        self,
        conv_id: str,
        task_uid: str,
        state: str,
        retry_times: int,
        agent: Optional[str] = None,
        model: Optional[str] = None,
        result: Optional[str] = None,
    ) -> None:
        """Update planning step information.

        Args:
            conv_id(str): conversation id
            task_uid(str): conversation round
            state(str): the status to update to
            retry_times(int): Latest number of retries
            agent(str): Agent's name
            model(str): Model name
            result(str): Plan step results
        """

    @abstractmethod
    def remove_by_conv_id(self, conv_id: str) -> None:
        """Remove plan by conversation id.

        Args:
            conv_id(str): conversation id
        """

    @abstractmethod
    def remove_by_conv_planner(self, conv_id: str, planner: str) -> None:
        """Remove plan by conversation id and planner.

        Args:
            conv_id(str): conversation id
            planner(str): planner name
        """


class GptsMessageMemory(ABC):
    """Gpts message memory interface."""

    @abstractmethod
    def append(self, message: GptsMessage) -> None:
        """Add a message.

        Args:
            message(GptsMessage): Message object
        """

    @abstractmethod
    def update(self, message: GptsMessage) -> None:
        """Update message.

        Args:
            message:

        Returns:

        """

    @abstractmethod
    async def get_by_conv_id(self, conv_id: str) -> List[GptsMessage]:
        """Return all messages in the conversation.

        Query messages by conv id.

        Args:
            conv_id(str): Conversation id
        Returns:
            List[GptsMessage]: List of messages
        """

    @abstractmethod
    def get_by_message_id(self, message_id: str) -> Optional[GptsMessage]:
        """Return one messages by message id.

        Args:
            message_id:

        Returns:

        """

    @abstractmethod
    def get_last_message(self, conv_id: str) -> Optional[GptsMessage]:
        """Return the last message in the conversation.

        Args:
            conv_id(str): Conversation id

        Returns:
            GptsMessage: The last message in the conversation
        """

    @abstractmethod
    def delete_by_conv_id(self, conv_id: str) -> None:
        """Delete messages by conversation id.

        Args:
            conv_id(str): Conversation id
        """

    @abstractmethod
    def get_by_session_id(self, session_id: str) -> Optional[List[GptsMessage]]:
        """Return one messages by session id.

        Args:
            session_id:

        Returns:

        """


class AgentSystemMessageMemory(ABC):
    """System Agent Message memory interface."""

    @abstractmethod
    def append(self, message: AgentSystemMessage) -> None:
        """Add a message.

        Args:
            message(GptsMessage): Message object
        """

    @abstractmethod
    def update(self, message: AgentSystemMessage) -> None:
        """Update message.

        Args:
            message:

        Returns:
        """

    @abstractmethod
    def get_by_conv_id(self, conv_id: str) -> List[AgentSystemMessage]:
        """Return all messages in the conversation.

        Query messages by conv id.

        Args:
            conv_id(str): Conversation id
        Returns:
            List[GptsMessage]: List of messages
        """

    @abstractmethod
    def get_by_session_id(self, session_id: str) -> Optional[List[AgentSystemMessage]]:
        """Return one messages by session id.

        Args:
            session_id:

        Returns:
        """
