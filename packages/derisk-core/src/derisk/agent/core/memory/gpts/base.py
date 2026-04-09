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
from ...types import (
    MessageContextType,
    ActionReportType,
    AgentReviewInfo,
    ResourceReferType,
    AgentMessage,
    MessageType,
)


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


MESSAGE_DATA_VERSION_V2 = "v2"


@dataclasses.dataclass
class GptsMessage:
    """
    Gpts message - Agent 消息层.

    新架构 (data_version="v2"):
    - 只管理 Agent 级别的消息 (user/assistant)
    - 不存储 role="tool" 的消息 (由 WorkEntry 管理)
    - action_report 动态从 WorkEntry 构建
    - 移除冗余字段: observation (由 WorkEntry.result 管理)

    老数据兼容:
    - data_version 为 None 或不存在 = 老数据
    - 老数据可能包含 role="tool" 的消息
    - 老数据 action_report 从数据库字段解析
    """

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
    input_tools: Optional[List[Dict]] = None  # 传给模型的工具列表（输入参数）

    data_version: Optional[str] = None

    # InitVar: 接受 DB 层传入的 action_report 参数，__post_init__ 路由到内部字段
    action_report: dataclasses.InitVar[Optional[Any]] = None

    _action_report_raw: Optional[str] = dataclasses.field(default=None, repr=False)
    _action_report_cache: Optional[ActionReportType] = dataclasses.field(
        default=None, repr=False
    )
    _work_entries: Optional[List] = dataclasses.field(
        default=None, repr=False
    )

    def __post_init__(self, action_report):
        """将构造函数的 action_report 参数路由到内部字段。"""
        if action_report is not None:
            if isinstance(action_report, str):
                self._action_report_raw = action_report
            elif isinstance(action_report, list):
                self._action_report_cache = action_report

    @property
    def is_new_format(self) -> bool:
        """是否新架构数据."""
        return self.data_version == MESSAGE_DATA_VERSION_V2

    @property
    def is_legacy_tool_message(self) -> bool:
        """是否老格式的 tool 消息 (需要特殊处理)."""
        return self.role == "tool" and not self.is_new_format

    @property
    def action_report(self) -> Optional[ActionReportType]:
        """
        动态获取 action_report (兼容新旧架构).

        优先级:
        1. 内存缓存: 已解析/已设置的数据
        2. 新架构: 从 WorkEntry 动态构建
        3. 老数据: 从 _action_report_raw 解析
        4. 兜底: 从 observation 构建
        """
        if self._action_report_cache is not None:
            return self._action_report_cache

        if self.is_new_format and self._work_entries:
            action_outputs = [entry.to_action_output() for entry in self._work_entries]
            self._action_report_cache = action_outputs
            return action_outputs

        if self._action_report_raw:
            from derisk.agent.core.action.base import ActionOutput

            parsed = ActionOutput.parse_action_reports(self._action_report_raw)
            self._action_report_cache = parsed
            return parsed

        if self.observation:
            from derisk.agent.core.action.base import ActionOutput

            legacy_output = ActionOutput(
                action_id="legacy_tool",
                content=self.observation,
                is_exe_success=True,
            )
            self._action_report_cache = [legacy_output]
            return [legacy_output]

        return None

    def set_work_entries(self, entries: List) -> None:
        """设置关联的 WorkEntry (新架构: 从 WorkLog 恢复)."""
        self._work_entries = entries
        self._action_report_cache = None

    def set_action_report_raw(self, raw: Optional[str]) -> None:
        """设置原始 action_report (数据库读取时使用, 老数据兼容)."""
        self._action_report_raw = raw
        self._action_report_cache = None

    def set_action_report_cache(self, report: Optional[ActionReportType]) -> None:
        """直接设置 action_report 缓存 (from_agent_message 时使用)."""
        self._action_report_cache = report

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "GptsMessage":
        """Create a GptsMessage object from a dictionary."""
        msg = GptsMessage(
            conv_id=d["conv_id"],
            conv_session_id=d["conv_session_id"],
            message_id=d["message_id"],
            sender=d["sender"],
            sender_name=d["sender_name"],
            receiver=d["receiver"],
            receiver_name=d["receiver_name"],
            role=d["role"],
            avatar=d.get("avatar"),
            thinking=d.get("thinking"),
            content=d["content"],
            message_type=d.get("message_type"),
            rounds=d.get("rounds", 0),
            is_success=d.get("is_success", True),
            app_code=d.get("app_code"),
            app_name=d.get("app_name"),
            model_name=d.get("model_name"),
            current_goal=d.get("current_goal"),
            context=d.get("context"),
            content_types=d.get("content_types"),
            review_info=d.get("review_info"),
            resource_info=d.get("resource_info"),
            system_prompt=d.get("system_prompt"),
            user_prompt=d.get("user_prompt"),
            show_message=d.get("show_message", True),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            observation=d.get("observation"),
            metrics=d.get("metrics"),
            tool_calls=d.get("tool_calls"),
            input_tools=d.get("input_tools"),
            data_version=d.get("data_version"),
        )

        # 老数据: action_report 存在于字典中，设置为 raw 待解析
        if d.get("action_report"):
            raw_report = d["action_report"]
            if isinstance(raw_report, str):
                msg.set_action_report_raw(raw_report)
            else:
                # 已经是解析后的对象列表 (内存缓存场景)
                msg._action_report_cache = raw_report

        return msg

    def to_dict(self) -> Dict[str, Any]:
        """Return a dictionary representation of the GptsMessage object."""
        result = dataclasses.asdict(self)
        # action_report 是 property，不会被 asdict 序列化，需要手动处理
        # 对于持久化场景，老数据保留 _action_report_raw，新数据不存 action_report
        if self._action_report_raw:
            result["action_report"] = self._action_report_raw
        elif self._action_report_cache and not self.is_new_format:
            # 老格式且有缓存，需要序列化回去
            result["action_report"] = self._action_report_cache
        else:
            result["action_report"] = None
        # 清理内部字段
        result.pop("_action_report_raw", None)
        result.pop("_action_report_cache", None)
        result.pop("_work_entries", None)
        return result

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
            input_tools=self.input_tools,
        )

    @classmethod
    def from_agent_message(
        cls,
        message: AgentMessage,
        sender: "ConversableAgent",
        receiver: Optional["ConversableAgent"] = None,
        role: Optional[str] = None,
    ) -> GptsMessage:
        gpts_msg = cls(
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
            input_tools=message.input_tools,
            data_version=MESSAGE_DATA_VERSION_V2,
        )

        # 新架构: action_report 缓存到内存，不再序列化到数据库
        if message.action_report:
            gpts_msg._action_report_cache = message.action_report

        return gpts_msg

    def view(self) -> Optional[str]:
        """最终返回给User的结论view"""

        views = [
            view
            for item in (self.action_report or [])
            if (view := item.view or item.observations or item.content)
        ]

        # 有action_report view则取view 否则取content
        return "\n".join(views) or self.content

    def answer(self) -> Optional[str]:
        """最终返回给User的结论content"""

        views = [
            view
            for item in (self.action_report or [])
            if (view := item.content or item.observations or item.view)
        ]

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
    def get_by_planner_and_round(
        self, conv_id: str, planner: str, round_id: str
    ) -> List[GptsPlan]:
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
