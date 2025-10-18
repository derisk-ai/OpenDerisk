"""Base agent class for conversable agents."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
from collections import defaultdict
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union, TypeVar, Generic

from derisk._private.pydantic import ConfigDict, Field, PrivateAttr, BaseModel
from derisk.core import LLMClient, ModelMessageRoleType, PromptTemplate, HumanMessage
from derisk.util.error_types import LLMChatError
from derisk.util.executor_utils import blocking_func_to_async
from derisk.util.logger import colored
from derisk.util.tracer import SpanType, root_tracer
from .action.base import Action, ActionOutput
from .agent import Agent, AgentContext, AgentMessage, AgentReviewInfo
from .memory.agent_memory import AgentMemory
from .memory.gpts.base import GptsMessage, GptsMessageType
from .memory.gpts.gpts_memory import GptsMemory
from .profile.base import ProfileConfig
from .reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from .role import AgentRunMode, Role
from .schema import Status, DynamicParam, DynamicParamView, DynamicParamRenderType, DynamicParamType, AgentSpaceMode, MessageMetrics, ActionInferenceMetrics
from .variable import VariableManager
from ..resource.base import Resource
from ..util.llm.llm import LLMConfig, get_llm_strategy_cls
from ..util.llm.llm_client import AIWrapper, AgentLLMOut
from ...context.event import ChatStartEvent, ChatPayload, StepStartEvent, StepPayload, AfterStepActionEvent, \
    ActionPayload, AfterActionEvent, ChatEndEvent, StepEndEvent
from ...context.manager import Manager, push_context_event
from ...util import memory_utils
from ...util.json_utils import serialize
from ...util.template_utils import render

logger = logging.getLogger(__name__)

T: TypeVar = TypeVar("T")


class ContextHelper(BaseModel, Generic[T]):
    _context: contextvars.ContextVar[T] = PrivateAttr(default_factory=lambda: contextvars.ContextVar("context", default=None))

    def __init__(self, context_cls: Type[T], /, **data: Any):
        super().__init__(**data)
        self._context_cls = context_cls

    @property
    def context(self) -> T:
        _ctx: T = self._context.get()
        if _ctx is None:
            _ctx = self._context_cls()
            self._context.set(_ctx)
        return _ctx


class RuntimeContext:
    current_retry_counter: int = 0
    recovering: bool = False


class ConversableAgent(Role, Agent):
    """ConversableAgent is an agent that can communicate with other agents."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_context: Optional[AgentContext] = Field(None, description="Agent context")
    actions: List[Action] = Field(default_factory=list)
    resource: Optional[Resource] = Field(None, description="Resource")
    llm_config: Optional[LLMConfig] = None
    bind_prompt: Optional[PromptTemplate] = None
    run_mode: Optional[AgentRunMode] = Field(default=None, description="Run mode")
    max_retry_count: int = 3
    # current_retry_counter: int = 0 # deprecated: 支持并发 改为从runtime_context取
    # recovering: bool = False # deprecated: 支持并发 改为从runtime_context取
    _runtime_context: ContextHelper[RuntimeContext] = PrivateAttr(default_factory=lambda: ContextHelper(RuntimeContext))
    llm_client: Optional[AIWrapper] = None

    # Agent可用自定义变量
    dynamic_variables: List[DynamicParam] = Field(default_factory=list)
    # Agent可用自定义变量管理器
    _vm = VariableManager()

    # 确认当前Agent是否需要进行流式输出
    stream_out: bool = True
    # 当前Agent是否对模型输出的内容区域进行流式输出(stream_out为True有效，不控制thinking区域)
    content_stream_out: bool = True

    # 消息队列管理 (初版，后续要管理整个运行时的内容)
    received_message_state: dict = defaultdict()

    # 当前Agent消息是否显示
    show_message: bool = True
    # 默认Agent的工作空间是消息模式(近对有工作空间的布局模式生效)
    agent_space: AgentSpaceMode = AgentSpaceMode.MESSAGE_SPACE

    executor: Executor = Field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=1),
        description="Executor for running tasks",
    )
    is_reasoning_agent: bool = False
    conv_round_id: str = None

    def __init__(self, **kwargs):
        """Create a new agent."""
        Role.__init__(self, **kwargs)
        Agent.__init__(self)
        self.register_variables()

    @property
    def current_retry_counter(self) -> int:
        return self._runtime_context.context.current_retry_counter

    @current_retry_counter.setter
    def current_retry_counter(self, value: int):
        self._runtime_context.context.current_retry_counter = value

    @property
    def recovering(self) -> bool:
        return self._runtime_context.context.recovering

    @recovering.setter
    def recovering(self, value: bool):
        self._runtime_context.context.recovering = value

    def check_available(self) -> None:
        """Check if the agent is available.

        Raises:
            ValueError: If the agent is not available.
        """
        self.identity_check()
        # check run context
        if self.agent_context is None:
            raise ValueError(
                f"{self.name}[{self.role}] Missing context in which agent is running!"
            )

        # action check
        if self.actions and len(self.actions) > 0:
            for action in self.actions:
                if action.resource_need and (
                    not self.resource
                    or not self.resource.get_resource_by_type(action.resource_need)
                ):
                    raise ValueError(
                        f"{self.name}[{self.role}] Missing resources"
                        f"[{action.resource_need}] required for runtime！"
                    )
        # else:
        #     if not self.is_human and not self.is_team:
        #         raise ValueError(
        #             f"This agent {self.name}[{self.role}] is missing action modules."
        #         )
        # # llm check
        # if not self.is_human and (
        #     self.llm_config is None or self.llm_config.llm_client is None
        # ):
        #     raise ValueError(
        #         f"{self.name}[{self.role}] Model configuration is missing or model "
        #         "service is unavailable！"
        #     )

    @property
    def not_null_agent_context(self) -> AgentContext:
        """Get the agent context.

        Returns:
            AgentContext: The agent context.

        Raises:
            ValueError: If the agent context is not initialized.
        """
        if not self.agent_context:
            raise ValueError("Agent context is not initialized！")
        return self.agent_context

    @property
    def not_null_llm_config(self) -> LLMConfig:
        """Get the LLM config."""
        if not self.llm_config:
            raise ValueError("LLM config is not initialized！")
        return self.llm_config

    @property
    def not_null_llm_client(self) -> LLMClient:
        """Get the LLM client."""
        llm_client = self.not_null_llm_config.llm_client
        if not llm_client:
            raise ValueError("LLM client is not initialized！")
        return llm_client

    async def blocking_func_to_async(
        self, func: Callable[..., Any], *args, **kwargs
    ) -> Any:
        """Run a potentially blocking function within an executor."""
        if not asyncio.iscoroutinefunction(func):
            return await blocking_func_to_async(self.executor, func, *args, **kwargs)
        return await func(*args, **kwargs)

    async def preload_resource(self) -> None:
        """Preload resources before agent initialization."""
        if self.resource:
            await self.blocking_func_to_async(self.resource.preload_resource)

    async def build(self) -> "ConversableAgent":
        """Build the agent."""
        # Preload resources
        await self.preload_resource()
        # Check if agent is available
        self.check_available()
        _language = self.not_null_agent_context.language
        if _language:
            self.language = _language

        # Initialize resource loader
        for action in self.actions:
            action.init_resource(self.resource)

        # Initialize LLM Server
        if self.llm_config and self.llm_config.llm_client:
            self.llm_client = AIWrapper(llm_client=self.llm_config.llm_client)
        # if not self.is_human:
        #     real_conv_id, _ = parse_conv_id(self.not_null_agent_context.conv_id)
        #     memory_session = f"{real_conv_id}_{self.role}_{self.name}"
        #     self.memory.initialize(
        #         self.name,
        #         self.llm_config.llm_client if self.llm_config and self.llm_config.llm_client else None,
        #         importance_scorer=self.memory_importance_scorer,
        #         insight_extractor=self.memory_insight_extractor,
        #         session_id=memory_session,
        #     )
        #     # Clone the memory structure
        #     self.memory = self.memory.structure_clone()
        #     action_outputs = await self.memory.gpts_memory.get_agent_history_memory(
        #         real_conv_id, self.role
        #     )
        #     await self.recovering_memory(action_outputs)

        temp_profile = self.profile
        from copy import deepcopy

        self.profile = deepcopy(temp_profile)

        for action in self.actions:
            action.init_action(
                language=self.language,
                render_protocol=self.memory.gpts_memory.vis_converter(self.not_null_agent_context.conv_id),
            )

        resource_info = '无'
        if self.resource:
            if self.resource.is_pack:
                resource_info = ';'.join(
                    [str(item.prefer_resource_parameters_class()) for item in self.resource.sub_resources])
            else:
                resource_info = self.resource.name + ":" + str(self.resource.prefer_resource_parameters_class())
        logger.info(f"Agent[{self.name}:{self.agent_context.gpts_app_code}]最终构建:"
                    f"\n资源:{resource_info}"
                    f"\n模型:{self.llm_config.strategy_context if self.llm_config else '无'}"
                    f"\n参数:{';'.join([str(item.to_dict()) for item in self.dynamic_variables]) if self.dynamic_variables else '无'}"
                    f"\n记忆:{self.memory.name if self.memory else '无'}")
        return self

    def update_profile(self, profile: ProfileConfig):
        from copy import deepcopy
        self.profile = deepcopy(profile)

        ### 构建时将自身agent对象添加到memory对象
        self.memory.gpts_memory.init_message_senders(self.not_null_agent_context.conv_id, [self])

    def bind(self, target: Any) -> "ConversableAgent":
        """Bind the resources to the agent."""
        if isinstance(target, LLMConfig):
            self.llm_config = target
        elif isinstance(target, GptsMemory):
            raise ValueError("GptsMemory is not supported!Please Use Agent Memory")
        elif isinstance(target, AgentContext):
            self.agent_context = target
        elif isinstance(target, Resource):
            self.resource = target
        elif isinstance(target, AgentMemory):
            self.memory = target
        elif isinstance(target, ProfileConfig):
            self.update_profile(target)
        elif isinstance(target, type) and issubclass(target, Action):
            self.actions.append(target())
        elif isinstance(target, DynamicParam):
            self.dynamic_variables.append(target)
        elif isinstance(target, list) and all(
            [isinstance(item, type) and issubclass(item, DynamicParam) for item in target]
        ):
            self.dynamic_variables.extend(target)
        elif isinstance(target, Action):
            self.actions.append(target)
        elif isinstance(target, list) and all(
            [isinstance(item, type) and issubclass(item, Action) for item in target]
        ):
            for action in target:
                self.actions.append(action())
        elif isinstance(target, list) and all(
            [isinstance(item, Action) for item in target]
        ):
            self.actions.extend(target)
        elif isinstance(target, PromptTemplate):
            self.bind_prompt = target
        return self

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
        """Send a message to recipient agent."""
        with root_tracer.start_span(
            "agent.send",
            metadata={
                "sender": self.name,
                "recipient": recipient.name,
                "reviewer": reviewer.name if reviewer else None,
                "agent_message": json.dumps(message.to_dict(), default=serialize, ensure_ascii=False),
                "request_reply": request_reply,
                "is_recovery": is_recovery,
                "conv_uid": self.not_null_agent_context.conv_id,
            },
        ):
            await recipient.receive(
                message=message,
                sender=self,
                reviewer=reviewer,
                request_reply=request_reply,
                is_recovery=is_recovery,
                silent=silent,
                is_retry_chat=is_retry_chat,
                last_speaker_name=last_speaker_name,
                historical_dialogues=historical_dialogues,
                rely_messages=rely_messages,
            )

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
        """Receive a message from another agent."""
        with root_tracer.start_span(
            "agent.receive",
            metadata={
                "sender": sender.name,
                "recipient": self.name,
                "reviewer": reviewer.name if reviewer else None,
                "agent_message": json.dumps(message.to_dict(), default=serialize, ensure_ascii=False),
                "request_reply": request_reply,
                "silent": silent,
                "is_recovery": is_recovery,
                "conv_uid": self.not_null_agent_context.conv_id,
                "is_human": self.is_human,
            },
        ):
            with Manager.new_window():
                if silent:
                    message.show_message = False
                await self._a_process_received_message(message, sender)
                if request_reply is False or request_reply is None:
                    return

                if not self.is_human:
                    if isinstance(sender, ConversableAgent) and sender.is_human:
                        reply = await self.generate_reply(
                            received_message=message,
                            sender=sender,
                            reviewer=reviewer,
                            is_retry_chat=is_retry_chat,
                            last_speaker_name=last_speaker_name,
                            historical_dialogues=historical_dialogues,
                            rely_messages=rely_messages,
                        )
                    else:
                        reply = await self.generate_reply(
                            received_message=message,
                            sender=sender,
                            reviewer=reviewer,
                            is_retry_chat=is_retry_chat,
                            historical_dialogues=historical_dialogues,
                            rely_messages=rely_messages,
                        )

                    if reply is not None:
                        await self.send(reply, sender)

    def prepare_act_param(
        self,
        received_message: Optional[AgentMessage],
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Prepare the parameters for the act method."""
        return {}

    async def agent_state(self):
        if len(self.received_message_state) > 0:
            return Status.RUNNING
        else:
            return Status.WAITING

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
        """Generate a reply based on the received messages."""
        logger.info(
            f"generate agent reply!sender={sender}, rely_messages_len={rely_messages}"
        )
        message_metrics = MessageMetrics()
        message_metrics.start_time_ms = time.time_ns() // 1_000_000

        await push_context_event(
            event=ChatStartEvent(payload=ChatPayload(
                received_message_id=received_message.message_id,
                received_message_content=received_message.content,
            )),
            agent=self,
        )
        root_span = root_tracer.start_span(
            "agent.generate_reply",
            metadata={
                "sender": sender.name,
                "recipient": self.name,
                "reviewer": reviewer.name if reviewer else None,
                "received_message": json.dumps(received_message.to_dict(), default=serialize, ),
                "conv_uid": self.not_null_agent_context.conv_id,
                "rely_messages": (
                    [msg.to_dict() for msg in rely_messages] if rely_messages else None
                ),
            },
        )
        reply_message = None

        try:
            self.received_message_state[received_message.message_id] = Status.RUNNING

            fail_reason = None
            self.current_retry_counter = 0
            is_success = True
            done = False
            observation = received_message.content or ""
            while not done and self.current_retry_counter < self.max_retry_count:
                await push_context_event(
                    event=StepStartEvent(payload=StepPayload(
                        step_counter=self.current_retry_counter)),
                    agent=self,
                )

                if self.current_retry_counter > 0 and self.run_mode != AgentRunMode.LOOP:
                    retry_message = AgentMessage.init_new(
                        content=fail_reason or observation,
                        current_goal=received_message.current_goal,
                        rounds=reply_message.rounds + 1,
                        conv_round_id=self.conv_round_id
                    )

                    # The current message is a self-optimized message that needs to be
                    # recorded.
                    # It is temporarily set to be initiated by the originating end to
                    # facilitate the organization of historical memory context.
                    await sender.send(
                        retry_message, self, reviewer, request_reply=False
                    )
                    received_message.rounds = retry_message.rounds + 1

                self._update_recovering(is_retry_chat)

                reply_message: AgentMessage = await self._generate_think_message(
                    received_message=received_message,
                    sender=sender,
                    rely_messages=rely_messages,
                    historical_dialogues=historical_dialogues,
                    is_retry_chat=is_retry_chat,
                    message_metrics=message_metrics,
                    **kwargs
                )
                logger.info(f'after generate_think_message, reply_message:{reply_message}')
                act_extent_param = self.prepare_act_param(
                    received_message=received_message,
                    sender=sender,
                    rely_messages=rely_messages,
                    historical_dialogues=historical_dialogues,
                    reply_message=reply_message,
                    **kwargs,
                )
                with root_tracer.start_span(
                    "agent.generate_reply.act",
                    metadata={
                        "llm_reply": reply_message.content,
                        "sender": sender.name,
                        "reviewer": reviewer.name if reviewer else None,
                        "act_extent_param": act_extent_param,
                    },
                ) as span:
                    # 3.Act based on the results of your thinking

                    act_metrics = ActionInferenceMetrics(start_time_ms=time.time_ns() // 1_000_000)
                    act_out: ActionOutput = await self.act(
                        message=reply_message,
                        sender=sender,
                        reviewer=reviewer,
                        is_retry_chat=is_retry_chat,
                        last_speaker_name=last_speaker_name,
                        **act_extent_param,
                    )
                    if act_out:
                        reply_message.action_report = act_out
                        span.metadata["action_report"] = (
                            act_out.to_dict() if act_out else None
                        )
                    await push_context_event(event=AfterStepActionEvent(
                        payload=ActionPayload(action_output=act_out)), agent=self)

                with root_tracer.start_span(
                    "agent.generate_reply.verify",
                    metadata={
                        "llm_reply": reply_message.content,
                        "sender": sender.name,
                        "reviewer": reviewer.name if reviewer else None,
                    },
                ) as span:
                    # 4.Reply information verification
                    check_pass, reason = await self.verify(
                        reply_message, sender, reviewer, received_message=received_message
                    )
                    is_success = check_pass
                    span.metadata["check_pass"] = check_pass
                    span.metadata["reason"] = reason

                await push_context_event(event=StepEndEvent(payload=StepPayload(
                    step_counter=self.current_retry_counter,
                    message_id=reply_message.message_id,
                )), agent=self)

                question: str = received_message.content or ""
                ai_message: str = reply_message.content
                # 5.Optimize wrong answers myself
                if not check_pass:
                    if not act_out.have_retry:
                        logger.warning("No retry available!")
                        break
                    fail_reason = reason
                    await self.write_memories(
                        question=question,
                        ai_message=ai_message,
                        action_output=act_out,
                        check_pass=check_pass,
                        check_fail_reason=fail_reason,
                        agent_id=self.not_null_agent_context.agent_app_code,
                        reply_message=reply_message,
                    )
                else:
                    # Successful reply
                    observation = act_out.observations
                    await self.write_memories(
                        question=question,
                        ai_message=ai_message,
                        action_output=act_out,
                        check_pass=check_pass,
                        agent_id=self.not_null_agent_context.agent_app_code or self.not_null_agent_context.gpts_app_code,
                        reply_message=reply_message,
                    )
                    if self.run_mode != AgentRunMode.LOOP or act_out.terminate:
                        logger.debug(f"Agent {self.name} reply success!{reply_message}")
                        break

                # Continue to run the next round
                self.current_retry_counter += 1
                # Send error messages and issue new problem-solving instructions
                if self.current_retry_counter < self.max_retry_count:
                    await self.send(
                        reply_message, self, reviewer, request_reply=False
                    )

            reply_message.success = is_success
            # 6.final message adjustment
            await self.adjust_final_message(is_success, reply_message)
            await push_context_event(event=ChatEndEvent(payload=ChatPayload(
                received_message_id=received_message.message_id,
                received_message_content=received_message.content,
            )), agent=self)

            ## 处理消息状态
            self.received_message_state.pop(received_message.message_id)

            reply_message.metrics.action_metrics = ActionInferenceMetrics.create_metrics(act_out.metrics or act_metrics)
            reply_message.metrics.end_time_ms = time.time_ns() // 1_000_000
            return reply_message

        except Exception as e:
            logger.exception("Generate reply exception!")
            err_message = AgentMessage(content=str(e), action_report=ActionOutput(is_exe_success=False,
                                                                                  content=f"Generate reply exception:{str(e)}"))
            err_message.rounds = 9999
            err_message.success = False
            return err_message
        finally:
            if reply_message:
                root_span.metadata["reply_message"] = reply_message.to_dict()
            root_span.end()

    async def listen_thinking_stream(self,
                                     llm_out: AgentLLMOut,
                                     reply_message_id: str,
                                     start_time: datetime,
                                     cu_thinking_incr: Optional[str] = None,
                                     cu_content_incr: Optional[str] = None,
                                     is_first_chunk: bool = False,
                                     is_first_content: bool = False,
                                     received_message: Optional[AgentMessage] = None,
                                     sender: Optional[Agent] = None):
        if not self.stream_out:
            return
        if len(llm_out.content) > 0 and not self.content_stream_out:
            if is_first_content:
                cu_content_incr = "动作执行中..."
            else:
                return
        temp_message = {
            "uid": reply_message_id,
            "type": "incr",
            "message_id": reply_message_id,
            "conv_id": self.not_null_agent_context.conv_id,
            "task_goal_id": received_message.goal_id if received_message else "",
            "task_goal": received_message.content if received_message else "",
            "conv_session_uid": self.agent_context.conv_session_id,
            "app_code": self.agent_context.gpts_app_code,
            "sender": self.name or self.role,
            "sender_role": self.role,
            "model": llm_out.llm_name,
            "thinking": cu_thinking_incr,
            "content": cu_content_incr,
            "avatar": self.avatar,
            "observation": received_message.observation if received_message else "",
            "start_time": start_time,
            "metrics": MessageMetrics(llm_metrics=llm_out.metrics).to_dict()
        }
        if not self.not_null_agent_context.output_process_message:
            if self.is_final_role:
                await self.memory.gpts_memory.push_message(
                    self.not_null_agent_context.conv_id,
                    stream_msg=temp_message,
                    is_first_chunk=is_first_chunk,
                    incremental=self.not_null_agent_context.incremental,
                    sender=sender
                )
        else:

            await self.memory.gpts_memory.push_message(
                self.not_null_agent_context.conv_id,
                stream_msg=temp_message,
                is_first_chunk=is_first_chunk,
                incremental=self.not_null_agent_context.incremental,
                sender=sender
            )

    def _update_recovering(self, is_retry_chat: bool):
        self.recovering = True if self.current_retry_counter == 0 and is_retry_chat else False

    async def _recovery_message(self) -> AgentMessage | None:
        # 从DB读取全量message数据
        messages: List[GptsMessage] = self.memory.gpts_memory.message_memory.get_by_conv_id(
            self.not_null_agent_context.conv_id)
        # 找到最后一条调用模型的消息
        last_speak_message: AgentMessage = next((AgentMessage.from_gpts_message(message)
                                                 for message in reversed(messages) if
                                                 message.sender_name == self.name and message.model_name), None)
        if not last_speak_message:
            return None
        reply_message = await self.init_reply_message(received_message=last_speak_message, rounds=len(messages))
        reply_message.thinking = last_speak_message.thinking
        reply_message.content = last_speak_message.content
        reply_message.model_name = last_speak_message.model_name
        reply_message.system_prompt = last_speak_message.system_prompt
        reply_message.user_prompt = last_speak_message.user_prompt
        reply_message.review_info = last_speak_message.review_info
        await self._a_append_message(reply_message, None, self)
        return reply_message

    async def _generate_think_message(
        self,
        received_message: AgentMessage,
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        is_retry_chat: bool = False,
        message_metrics: Optional[MessageMetrics] = None,
        **kwargs,
    ) -> AgentMessage:
        if self.recovering:
            recovering_message = await self._recovery_message()
            if recovering_message:
                return recovering_message
        if not message_metrics:
            message_metrics = MessageMetrics()
        with root_tracer.start_span(
            "agent.generate_reply.init_reply_message",
        ) as span:
            # initialize reply message
            a_reply_message: Optional[
                AgentMessage
            ] = await self._a_init_reply_message(
                received_message=received_message
            )
            if a_reply_message:
                reply_message = a_reply_message
            else:
                reply_message = await self.init_reply_message(
                    received_message=received_message, sender=sender
                )
            span.metadata["reply_message"] = reply_message.to_dict()

        (
            thinking_messages,
            resource_info,
            system_prompt,
            user_prompt,
        ) = await self._load_thinking_messages(
            received_message=received_message,
            sender=sender,
            rely_messages=rely_messages,
            historical_dialogues=historical_dialogues,
            context=reply_message.get_dict_context(),
            is_retry_chat=is_retry_chat,
            **kwargs
        )
        reply_message.system_prompt = system_prompt
        reply_message.user_prompt = user_prompt
        with root_tracer.start_span(
            "agent.generate_reply.thinking",
            metadata={
                "thinking_messages": json.dumps(
                    [msg.to_dict() for msg in thinking_messages],
                    ensure_ascii=False,
                    default=serialize,
                )
            },
        ) as span:

            message_metrics.context_complete = time.time_ns() // 1_000_000

            # 1.Think about how to do things
            llm_thinking, llm_content, llm_name = await self.thinking(
                thinking_messages, reply_message.message_id, sender, received_message=received_message,
                message_metrics=message_metrics
            )

            reply_message.thinking = llm_thinking
            reply_message.model_name = llm_name
            reply_message.content = llm_content

            reply_message.metrics = message_metrics
            reply_message.resource_info = resource_info

            span.metadata["llm_reply"] = llm_content
            span.metadata["model_name"] = llm_name

        with root_tracer.start_span(
            "agent.generate_reply.review",
            metadata={"llm_reply": llm_content, "censored": self.name},
        ) as span:
            # 2.Review whether what is being done is legal
            approve, comments = await self.review(llm_content, self)
            reply_message.review_info = AgentReviewInfo(
                approve=approve,
                comments=comments,
            )
            span.metadata["approve"] = approve
            span.metadata["comments"] = comments

        return reply_message

    async def thinking_inner(
        self,
        messages: List[AgentMessage],
        reply_message_id: str,
        sender: Optional[Agent] = None,
        prompt: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
    ) -> Optional[AgentLLMOut]:
        last_model = None
        last_err = None
        retry_count = 0
        llm_messages = [message.to_llm_message() for message in messages]
        start_time: datetime = datetime.now()
        # LLM inference automatically retries 3 times to reduce interruption
        # probability caused by speed limit and network stability
        while retry_count < 3:
            llm_model, llm_context = await self.select_llm_model(last_model)
            try:
                logger.info(f"model:{llm_model} chat begin!retry_count:{retry_count}")
                if prompt:
                    llm_messages = _new_system_message(prompt) + llm_messages

                if not self.llm_client:
                    raise ValueError("LLM client is not initialized!")

                prev_thinking = ""
                prev_content = ""

                thinking_chunk_count = 0
                content_chunk_count = 0
                agent_llm_out = None
                async for output in self.llm_client.create(
                    context=llm_messages[-1].pop("context", None),
                    messages=llm_messages,
                    llm_model=llm_model,
                    max_new_tokens=self.not_null_agent_context.max_new_tokens,
                    temperature=self.not_null_agent_context.temperature,
                    llm_context=llm_context,
                    verbose=self.not_null_agent_context.verbose,
                    trace_id=self.not_null_agent_context.trace_id,
                    rpc_id=self.not_null_agent_context.rpc_id,
                ):

                    # 处理收到的模型输出，从全量内容中分别解析出增量thinking 和 增量content， 后续恢复到模型对接层来做
                    agent_llm_out = output
                    current_thinking = output.thinking_content
                    current_content = output.content

                    if self.not_null_agent_context.incremental:
                        res_thinking = current_thinking[len(prev_thinking):]
                        res_content = current_content[len(prev_content):]
                        prev_thinking = current_thinking
                        prev_content = current_content

                    else:
                        res_thinking = (
                            current_thinking.strip().replace("\\n", "\n")
                            if current_thinking
                            else current_thinking
                        )
                        res_content = (
                            current_content.strip().replace("\\n", "\n")
                            if current_content
                            else current_content
                        )
                        prev_thinking = res_thinking
                        prev_content = res_content

                    # 输出标记检测
                    if len(prev_thinking) > 0 and len(prev_content) <= 0:
                        thinking_chunk_count = thinking_chunk_count + 1
                    if len(prev_content) > 0:
                        content_chunk_count = content_chunk_count + 1
                    is_first_chunk = thinking_chunk_count == 1
                    is_first_content = content_chunk_count == 1

                    await self.listen_thinking_stream(output, reply_message_id,
                                                      start_time=start_time,
                                                      cu_thinking_incr=res_thinking,
                                                      cu_content_incr=res_content,
                                                      is_first_chunk=is_first_chunk,
                                                      is_first_content=is_first_content,
                                                      received_message=received_message,
                                                      sender=sender)

                return agent_llm_out
            except LLMChatError as e:
                logger.exception(f"model:{llm_model} generate Failed!{str(e)}")
                if e.original_exception and e.original_exception > 0:
                    ## TODO 可以尝试发一个系统提示消息

                    ## 模型调用返回错误码大于0，可以使用其他模型兜底重试，小于0 没必要重试直接返回异常
                    retry_count += 1
                    last_model = llm_model
                    last_err = str(e)
                    await asyncio.sleep(1)
                else:
                    raise
            except Exception:
                raise

        if last_err:
            raise ValueError(last_err)
        else:
            raise ValueError("LLM model inference failed!")

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

        Args:
            messages(List[AgentMessage]): the messages to be reasoned
            prompt(str): the prompt to be reasoned
        """
        out = await self.thinking_inner(messages, reply_message_id, sender, prompt, received_message)
        message_metrics = kwargs.get("message_metrics")
        if message_metrics:
            message_metrics.llm_metrics = out.metrics
        return out.thinking_content, out.content, out.llm_name

    async def review(self, message: Optional[str], censored: Agent) -> Tuple[bool, Any]:
        """Review the message based on the censored message."""
        return True, None

    async def act(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        **kwargs,
    ) -> ActionOutput:
        """Perform actions."""
        last_out: Optional[ActionOutput] = None
        for i, action in enumerate(self.actions):
            if not message:
                raise ValueError("The message content is empty!")

            with root_tracer.start_span(
                "agent.act.run",
                metadata={
                    "message": message,
                    "sender": sender.name if sender else None,
                    "recipient": self.name,
                    "reviewer": reviewer.name if reviewer else None,
                    "rely_action_out": last_out.to_dict() if last_out else None,
                    "conv_uid": self.not_null_agent_context.conv_id,
                    "action_index": i,
                    "total_action": len(self.actions),
                },
            ) as span:
                ai_message = message.content if message.content else ""
                real_action = action.parse_action(
                    ai_message, default_action=action, **kwargs
                )
                if real_action is None:
                    continue
                logger.info(f"ai_message:{ai_message}, prepare to call tools")
                last_out = await real_action.run(
                    ai_message=message.content if message.content else "",
                    resource=None,
                    rely_action_out=last_out,
                    render_protocol=self.memory.gpts_memory.vis_converter(self.not_null_agent_context.conv_id),
                    message_id=message.message_id,
                    agent_context= self.agent_context,
                    **kwargs,
                )
                span.metadata["action_out"] = last_out.to_dict() if last_out else None
                await push_context_event(event=AfterActionEvent(payload=ActionPayload(action_output=last_out)),
                                         agent=self)
        if not last_out:
            raise ValueError("Action should return value！")
        return last_out

    async def correctness_check(
        self, message: AgentMessage, **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """Verify the correctness of the results."""
        return True, None

    async def verify(
        self,
        message: AgentMessage,
        sender: Agent,
        reviewer: Optional[Agent] = None,
        **kwargs,
    ) -> Tuple[bool, Optional[str]]:
        """Verify the current execution results."""
        # Check approval results
        if message.review_info and not message.review_info.approve:
            return False, message.review_info.comments

        # Check action run results
        action_output: Optional[ActionOutput] = message.action_report
        if action_output:
            if not action_output.is_exe_success:
                return False, action_output.content
            elif not action_output.content or len(action_output.content.strip()) < 1:
                return (
                    False,
                    "The current execution result is empty. Please rethink the "
                    "question and background and generate a new answer.. ",
                )

        # agent output correctness check
        return await self.correctness_check(message, **kwargs)

    async def initiate_chat(
        self,
        recipient: Agent,
        reviewer: Optional[Agent] = None,
        message: Optional[Union[str, HumanMessage, AgentMessage]] = None,
        request_reply: bool = True,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        message_rounds: int = 0,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        approval_message_id: Optional[str] = None,
        **kwargs,
    ):
        """Initiate a chat with another agent.

        Args:
            recipient (Agent): The recipient agent.
            reviewer (Agent): The reviewer agent.
            message (str): The message to send.
        """
        agent_message = AgentMessage.from_media_messages(message, None, message_rounds, context=kwargs)
        agent_message.role = "Human"
        agent_message.name = "User"

        message_type = GptsMessageType.ActionApproval.value \
            if approval_message_id \
            else GptsMessageType.AgentMessage.value
        agent_message.message_type = message_type

        with root_tracer.start_span(
            "agent.initiate_chat",
            span_type=SpanType.AGENT,
            metadata={
                "sender": self.name,
                "recipient": recipient.name,
                "reviewer": reviewer.name if reviewer else None,
                "agent_message": json.dumps(
                    agent_message.to_dict(), ensure_ascii=False, default=serialize,
                ),
                "conv_uid": self.not_null_agent_context.conv_id,
            },
        ):
            await self.send(
                agent_message,
                recipient,
                reviewer,
                historical_dialogues=historical_dialogues,
                rely_messages=rely_messages,
                request_reply=request_reply,
                is_retry_chat=is_retry_chat,
                last_speaker_name=last_speaker_name,
            )

    async def adjust_final_message(
        self,
        is_success: bool,
        reply_message: AgentMessage,
    ):
        """Adjust final message after agent reply."""
        return is_success, reply_message

    #######################################################################
    # Private Function Begin
    #######################################################################

    def _init_actions(self, actions: List[Type[Action]]):
        self.actions = []
        for idx, action in enumerate(actions):
            if issubclass(action, Action):
                self.actions.append(action(language=self.language))

    async def _a_append_message(
        self,
        message: AgentMessage,
        role,
        sender: Agent,
        reciver: Optional[Agent] = None,
    ) -> bool:
        gpts_message: GptsMessage = message.to_gpts_message(
            sender=sender, role=role, receiver=reciver
        )

        with root_tracer.start_span(
            "agent.save_message_to_memory",
            metadata={
                "gpts_message": gpts_message.to_dict(),
                "conv_uid": self.not_null_agent_context.conv_id,
            },
        ):
            await self.memory.gpts_memory.append_message(
                self.not_null_agent_context.conv_id, gpts_message, sender=sender
            )
            return True

    def _print_received_message(self, message: AgentMessage, sender: Agent):
        # print the message received
        print("\n", "-" * 80, flush=True, sep="")
        _print_name = self.name if self.name else self.role
        print(
            colored(
                sender.name if sender.name else sender.role,
                "yellow",
            ),
            "(to",
            f"{_print_name})-[{message.model_name or ''}]:\n",
            flush=True,
        )

        content = json.dumps(message.content, ensure_ascii=False, default=serialize, )
        if content is not None:
            print(content, flush=True)

        review_info = message.review_info
        if review_info:
            name = sender.name if sender.name else sender.role
            pass_msg = "Pass" if review_info.approve else "Reject"
            review_msg = f"{pass_msg}({review_info.comments})"
            approve_print = f">>>>>>>>{name} Review info: \n{review_msg}"
            print(colored(approve_print, "green"), flush=True)

        action_report = message.action_report
        if action_report:
            name = sender.name if sender.name else sender.role
            action_msg = (
                "execution succeeded"
                if action_report.is_exe_success
                else "execution failed"
            )
            action_report_msg = f"{action_msg},\n{action_report.content}"
            action_print = f">>>>>>>>{name} Action report: \n{action_report_msg}"
            print(colored(action_print, "blue"), flush=True)

        print("\n", "-" * 80, flush=True, sep="")

    async def _a_process_received_message(self, message: AgentMessage, sender: Agent):
        valid = await self._a_append_message(message, None, sender, self)
        if not valid:
            raise ValueError(
                "Received message can't be converted into a valid ChatCompletion"
                " message. Either content or function_call must be provided."
            )

        self._print_received_message(message, sender)

    async def load_resource(self, question: str, is_retry_chat: bool = False):
        """Load agent bind resource."""
        if self.resource:
            resource_prompt, resource_reference = await self.resource.get_prompt(
                lang=self.language, question=question
            )
            return resource_prompt, resource_reference
        return None, None

    def register_variables(self):
        """子类通过重写此方法注册变量"""
        logger.info(f"register_variables {self.role}")

        @self._vm.register('out_schema', 'Agent模型输出结构定义')
        def var_out_schema(instance):
            if instance and instance.actions:
                return instance.actions[0].ai_out_schema
            else:
                return None

        @self._vm.register('resource_prompt', '绑定资源Prompt')
        def var_resource_info(resource_prompt: Optional[str] = None):
            if resource_prompt:
                return resource_prompt
            return None

        @self._vm.register('most_recent_memories', '对话记忆')
        async def var_most_recent_memories(instance, received_message, rely_messages):
            if not instance.agent_context:
                return ""
            logger.info(f"对话记忆加载:{instance.agent_context.conv_id}")
            observation = received_message.content
            memories = await instance.read_memories(
                question=observation,
                conv_id=instance.agent_context.conv_session_id,
                agent_id=instance.agent_context.agent_app_code,
                llm_token_limit=memory_utils.get_agent_llm_context_length(
                    instance.llm_config.strategy_context
                )
            )

            reply_message_str = ""

            if rely_messages:
                copied_rely_messages = [m.copy() for m in rely_messages]
                # When directly relying on historical messages, use the execution result
                # content as a dependency
                for message in copied_rely_messages:
                    action_report: Optional[ActionOutput] = message.action_report
                    if action_report:
                        message.content = action_report.content
                    if message.name != self.name:
                        # Rely messages are not from the current agent
                        if message.role == ModelMessageRoleType.HUMAN:
                            reply_message_str += f"Question: {message.content}\n"
                        elif message.role == ModelMessageRoleType.AI:
                            reply_message_str += f"Observation: {message.content}\n"
            if reply_message_str:
                memories += "\n" + reply_message_str
            return memories

        @self._vm.register('question', '接收消息内容')
        def var_question(received_message):
            if received_message:
                return received_message.content
            return None

        logger.info(f"register_variables end {self.role}")

    def init_variables(self) -> List[DynamicParam]:
        results: List[DynamicParam] = []
        ## 初始化系统参数
        system_variables = [{
            "key": "role",
            "value": self.role,
            "description": "Agent角色"
        }, {
            "key": "name",
            "value": self.name,
            "description": "Agent名字"
        }, {
            "key": "goal",
            "value": self.goal,
            "description": "Agent目标"
        }, {
            "key": "expand_prompt",
            "value": self.expand_prompt,
            "description": "Agent扩展提示词"
        }, {
            "key": "language",
            "value": self.language,
            "description": "Agent语言设定"
        }, {
            "key": "constraints",
            "value": self.constraints,
            "description": "Agent默认约束设定(Prompt使用)"
        }, {
            "key": "examples",
            "value": self.examples,
            "description": "Agent消息示例(Prompt使用)"
        }]
        for item in system_variables:
            results.append(DynamicParam(
                key=item['key'],
                name=item['key'],
                type=DynamicParamType.SYSTEM.value,
                value=item['value'],
                description=item['description'],
                config=None
            ))

        ## 初始化加载Agent参数
        for k, v in self._vm.get_all_variables().items():
            results.append(DynamicParam(
                key=k,
                name=k,
                type=DynamicParamType.AGENT.value,
                value=None,
                description=v.get("description"),
                config=None
            ))
        return results

    async def get_all_custom_variables(self) -> List[DynamicParam]:
        from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
        arg_suppliers: Dict[str, ReasoningArgSupplier] = ReasoningArgSupplier.get_all_suppliers()
        results: List[DynamicParam] = []
        for k, v in arg_suppliers.items():
            results.append(DynamicParam(
                key=k,
                name=v.arg_key,
                type=DynamicParamType.CUSTOM.value,
                value=None,
                description=v.description,
                config=v.params
            ))
        return results

    async def variables_view(self, params: List[DynamicParam], **kwargs) -> Dict[str, DynamicParamView]:
        logger.info(f"render_dynamic_variables: {params}")

        param_view: Dict[str, DynamicParamView] = {}
        for param in params:
            if param.type == DynamicParamType.SYSTEM.value:
                continue
            elif param.type == DynamicParamType.AGENT.value:
                view = DynamicParamView(**param.to_dict())
                view.render_mode = DynamicParamRenderType.VIS.value
                try:
                    view.render_content = await self._vm.get_value(param.key, instance=self, **kwargs)
                except Exception as e:
                    logger.warning(f"Agent[{self.role}]内置变量[{param.name}]无法可视化！{str(e)}")
                    view.can_render = False

                param_view[param.key] = view

            else:
                arg_supplier: ReasoningArgSupplier = ReasoningArgSupplier.get_supplier(param.key)
                view = DynamicParamView(**param.to_dict())
                try:
                    prompt_param: dict[str, str] = {}
                    await arg_supplier.supply(prompt_param, self, self.agent_context)
                    view.render_content = prompt_param[param.key]
                except Exception as e:
                    logger.warning(f"Agent[{self.role}]自定义变量[{param.name}]无法可视化！{str(e)}")
                    view.can_render = False

                view.render_mode = DynamicParamRenderType.VIS.value

                param_view[param.key] = view

        return param_view

    async def generate_bind_variables(
        self,
        received_message: AgentMessage,
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        context: Optional[Dict[str, Any]] = None,
        resource_info: Optional[str] = None,
        resource: Optional[Resource] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate the resource variables."""
        variable_values = {}

        ## Agent参数准备

        agent_variables = self._vm.get_all_variables()
        if agent_variables:
            for k, v in agent_variables.items():
                variable_values[k] = await self._vm.get_value(k, instance=self,
                                                              agent_context=self.not_null_agent_context,
                                                              received_message=received_message,
                                                              sender=sender,
                                                              rely_messages=rely_messages,
                                                              historical_dialogues=historical_dialogues,
                                                              context=context,
                                                              resource_info=resource_info,
                                                              **kwargs)

        for param in self.dynamic_variables:
            if param.type == DynamicParamType.SYSTEM.value:
                continue
            elif param.type == DynamicParamType.AGENT.value:
                continue
                # variable_values[param.key] = await self._vm.get_value(param.key, self=self,
                #                                                       agent_context=self.not_null_agent_context,
                #                                                       received_message=received_message,
                #                                                       sender=sender,
                #                                                       rely_messages=rely_messages,
                #                                                       historical_dialogues=historical_dialogues,
                #                                                       context=context,
                #                                                       resource_info=resource_info,
                #                                                       **kwargs)


            else:
                arg_supplier: ReasoningArgSupplier = ReasoningArgSupplier.get_supplier(param.key)
                await arg_supplier.supply(variable_values, agent=self, agent_context=self.not_null_agent_context,
                                          received_message=received_message, **kwargs)

        return variable_values

    def _excluded_models(
        self,
        all_models: List[str],
        order_llms: Optional[List[str]] = None,
        excluded_models: Optional[List[str]] = None,
    ):
        if not order_llms:
            order_llms = []
        if not excluded_models:
            excluded_models = []
        can_uses = []
        if order_llms and len(order_llms) > 0:
            for llm_name in order_llms:
                if llm_name in all_models and (
                    not excluded_models or llm_name not in excluded_models
                ):
                    can_uses.append(llm_name)
        else:
            for llm_name in all_models:
                if not excluded_models or llm_name not in excluded_models:
                    can_uses.append(llm_name)

        return can_uses

    def convert_to_agent_message(
        self,
        gpts_messages: List[GptsMessage],
        is_rery_chat: bool = False,
    ) -> Optional[List[AgentMessage]]:
        """Convert gptmessage to agent message."""
        oai_messages: List[AgentMessage] = []
        # Based on the current agent, all messages received are user, and all messages
        # sent are assistant.
        if not gpts_messages:
            return None
        for item in gpts_messages:
            # Message conversion, priority is given to converting execution results,
            # and only model output results will be used if not.
            oai_messages.append(
                AgentMessage(
                    message_id=item.message_id,
                    content=item.content,
                    thinking=item.thinking,
                    context=(
                        json.loads(item.context) if item.context is not None else None
                    ),
                    action_report=(
                        ActionOutput.from_dict(json.loads(item.action_report))
                        if item.action_report
                        else None
                    ),
                    name=item.sender,
                    role=item.role,
                    goal_id=item.goal_id,
                    rounds=item.rounds,
                    model_name=item.model_name,
                    success=item.is_success,
                    show_message=item.show_message,
                    system_prompt=item.system_prompt,
                    user_prompt=item.user_prompt,
                )
            )
        return oai_messages

    async def select_llm_model(
        self, excluded_models: Optional[List[str]] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        logger.info(f"_a_select_llm_model:{excluded_models}")
        try:
            llm_strategy_cls = get_llm_strategy_cls(
                self.not_null_llm_config.llm_strategy
            )
            if not llm_strategy_cls:
                raise ValueError(
                    f"Configured model policy not found {self.not_null_llm_config.llm_strategy}!"
                )
            llm_strategy = llm_strategy_cls(
                self.not_null_llm_config.llm_client,
                self.not_null_llm_config.strategy_context,
                self.not_null_llm_config.llm_param
            )

            return await llm_strategy.next_llm(excluded_models=excluded_models)
        except Exception as e:
            logger.error(f"{self.role} get next llm failed!{str(e)}")
            raise ValueError(f"Failed to allocate model service,{str(e)}!")

    async def init_reply_message(
        self,
        received_message: AgentMessage,
        rely_messages: Optional[List[AgentMessage]] = None,
        sender: Optional[Agent] = None,
        rounds: Optional[int] = None,
    ) -> AgentMessage:
        """Create a new message from the received message.

        Initialize a new message from the received message

        Args:
            received_message(AgentMessage): The received message

        Returns:
            AgentMessage: A new message
        """
        new_message = AgentMessage.init_new(
            content="",
            current_goal=received_message.current_goal,
            goal_id=received_message.goal_id,
            context=received_message.context,
            rounds=rounds if rounds is not None else received_message.rounds + 1,
            conv_round_id=self.conv_round_id,
            name=self.name,
            role=self.role,
            show_message=self.show_message,
            observation=received_message.observation
        )
        await self._a_append_message(new_message, None, self)
        return new_message

    async def _a_init_reply_message(
        self,
        received_message: AgentMessage,
        rely_messages: Optional[List[AgentMessage]] = None,
    ) -> Optional[AgentMessage]:
        """Create a new message from the received message.

        If return not None, the `init_reply_message` method will not be called.
        """
        return None

    def _convert_to_ai_message(
        self,
        gpts_messages: List[GptsMessage],
        is_rery_chat: bool = False,
    ) -> List[AgentMessage]:
        oai_messages: List[AgentMessage] = []
        # Based on the current agent, all messages received are user, and all messages
        # sent are assistant.
        for item in gpts_messages:
            if item.role:
                role = item.role
            else:
                if item.receiver == self.role:
                    role = ModelMessageRoleType.HUMAN
                elif item.sender == self.role:
                    role = ModelMessageRoleType.AI
                else:
                    continue

            # Message conversion, priority is given to converting execution results,
            # and only model output results will be used if not.
            content = item.content
            if item.action_report:
                action_out = ActionOutput.from_dict(json.loads(item.action_report))
                if is_rery_chat:
                    if action_out is not None and action_out.content:
                        content = action_out.content
                else:
                    if (
                        action_out is not None
                        and action_out.is_exe_success
                        and action_out.content is not None
                    ):
                        content = action_out.content
            oai_messages.append(
                AgentMessage(
                    content=content,
                    role=role,
                    context=(
                        json.loads(item.context) if item.context is not None else None
                    ),
                )
            )
        return oai_messages

    async def build_system_prompt(
        self,
        resource_vars: Optional[Dict] = None,
        context: Optional[Dict[str, Any]] = None,
        is_retry_chat: bool = False,
    ):
        """Build system prompt."""
        system_prompt = None
        if self.bind_prompt:
            prompt_param = {}
            if resource_vars:
                prompt_param.update(resource_vars)
            if context:
                prompt_param.update(context)
            if self.bind_prompt.template_format == "f-string":
                system_prompt = self.bind_prompt.template.format(
                    **prompt_param,
                )
            elif self.bind_prompt.template_format == "jinja2":
                system_prompt = render(self.bind_prompt.template, prompt_param)
            else:
                logger.warning("Bind prompt template not exsit or  format not support!")
        if not system_prompt:
            param: Dict = context if context else {}
            system_prompt = await self.build_prompt(
                is_system=True,
                resource_vars=resource_vars,
                is_retry_chat=is_retry_chat,
                **param,
            )
        return system_prompt

    async def _load_thinking_messages(
        self,
        received_message: AgentMessage,
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        context: Optional[Dict[str, Any]] = None,
        is_retry_chat: bool = False,
        force_use_historical: bool = False,
        **kwargs
    ) -> Tuple[List[AgentMessage], Optional[Dict], Optional[str], Optional[str]]:
        logger.info(f"_load_thinking_messages:{received_message.message_id}")
        observation = received_message.content
        if not observation:
            raise ValueError("The received message content is empty!")

        if context is None:
            context = {}

        try:
            resource_prompt_str, resource_references = await self.load_resource(
                observation, is_retry_chat=is_retry_chat
            )
        except Exception as e:
            logger.exception(f"Load resource error！{str(e)}")
            raise ValueError(f"Load resource error！{str(e)}")

        resource_vars = await self.generate_bind_variables(received_message, sender, rely_messages,
                                                           historical_dialogues, context=context,
                                                           resource_prompt=resource_prompt_str,
                                                           resource_info=resource_references, **kwargs)
        logger.info(f"参数加载完成！当前可用参数:{json.dumps(resource_vars, ensure_ascii=False)}")
        system_prompt = await self.build_system_prompt(
            resource_vars=resource_vars,
            context=context,
            is_retry_chat=is_retry_chat,
        )

        # 如果强制传递了历史消息，不要使用默认记忆
        if historical_dialogues and force_use_historical:
            resource_vars['most_recent_memories'] = None

        user_prompt = await self.build_prompt(
            is_system=False,
            resource_vars=resource_vars,
            **context,
        )
        if not user_prompt:
            user_prompt = "Observation: "

        agent_messages = []
        if system_prompt:
            agent_messages.append(
                AgentMessage(
                    content=system_prompt,
                    role=ModelMessageRoleType.SYSTEM,
                )
            )

        if historical_dialogues and force_use_historical:
            # If we can't read the memory, we need to rely on the historical dialogue
            if historical_dialogues:
                for i in range(len(historical_dialogues)):
                    if i % 2 == 0:
                        # The even number starts, and the even number is the user
                        # information
                        message = historical_dialogues[i]
                        message.role = ModelMessageRoleType.HUMAN
                        agent_messages.append(message)
                    else:
                        # The odd number is AI information
                        message = historical_dialogues[i]
                        message.role = ModelMessageRoleType.AI
                        agent_messages.append(message)

        # Current user input information
        agent_messages.append(AgentMessage(
            content=user_prompt,
            context=received_message.context,
            content_types=received_message.content_types,
            role=ModelMessageRoleType.HUMAN,
        ))

        return agent_messages, resource_references, system_prompt, user_prompt


def _new_system_message(content):
    """Return the system message."""
    return [{"content": content, "role": ModelMessageRoleType.SYSTEM}]


def _is_list_of_type(lst: List[Any], type_cls: type) -> bool:
    return all(isinstance(item, type_cls) for item in lst)
