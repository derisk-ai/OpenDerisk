"""Agent Interface."""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from derisk.core import LLMClient
from derisk.util.annotations import PublicAPI
from .action.base import ActionOutput
from .memory.agent_memory import AgentMemory
from .types import AgentMessage
from ..util.llm.llm_client import AgentLLMOut


class Agent(ABC):
    """Agent Interface."""

    @abstractmethod
    async def send(
        self,
        message: AgentMessage,
        recipient: Agent,
        reviewer: Optional[Agent] = None,
        request_reply: Optional[bool] = True,
        reply_to_sender: Optional[bool] = True,  # 是否向sender发送回复消息
        request_sender_reply: Optional[bool] = True,  # 向sender发送消息是是否仍request_reply
        is_recovery: Optional[bool] = False,
        silent: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        **kwargs
    ) ->  Optional[AgentMessage]:
        """Send a message to recipient agent.

        Args:
            message(AgentMessage): the message to be sent.
            recipient(Agent): the recipient agent.
            reviewer(Agent): the reviewer agent.
            request_reply(bool): whether to request a reply.
            reply_to_sender(bool): whether to reply to sender.
            request_sender_reply(bool): whether request a reply when response to sender
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
        reply_to_sender: Optional[bool] = True,  # 是否向sender发送回复消息
        request_sender_reply: Optional[bool] = True,  # 向sender发送消息是是否仍request_reply
        silent: Optional[bool] = False,
        is_recovery: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> None:
        """Receive a message from another agent.

        Args:
            message(AgentMessage): the received message.
            sender(Agent): the sender agent.
            reviewer(Agent): the reviewer agent.
            request_reply(bool): whether to request a reply.
            reply_to_sender(bool): whether to reply to sender.
            request_sender_reply(bool): whether request a reply when response to sender
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
    ) -> Optional[AgentLLMOut]:
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
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> List[ActionOutput]:
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
    staff_no: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    conv_start_time: Optional[str] = None
    trace_id: Optional[str] = None
    rpc_id: Optional[str] = None
    ## 当前对话的主Agent(应用)信息
    gpts_app_code: Optional[str] = None
    gpts_app_name: Optional[str] = None
    ## 当前Agent的ID(应用APP CODE, 记忆模块强依赖，如果未赋值记忆模块会错乱)
    agent_app_code: Optional[str] = None
    language: Optional[str] = "zh"
    max_chat_round: int = 100
    max_retry_round: int = 10
    max_new_tokens: int = 0
    temperature: float = 0.5
    allow_format_str_template: Optional[bool] = False
    verbose: bool = False
    # 独立分配的ai云key
    mist_keys: Optional[List[str]] = None

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





class ContextEngineeringKey(str, Enum):
    AVAILABLE_TOOLS = "available_tools",
    AVAILABLE_KNOWLEDGE = "available_knowledge",
    AVAILABLE_AGENTS = "available_agents",
    LAST_STEP_MESSAGE_ID = "last_step_message_id",
