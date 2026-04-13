"""Base agent class for conversable agents."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    TypeVar,
    Generic,
)
from derisk._private.pydantic import ConfigDict, Field, PrivateAttr, BaseModel
from derisk.core import LLMClient, ModelMessageRoleType, PromptTemplate, HumanMessage
from derisk.core.interface.scheduler import Scheduler
from derisk.util.error_types import LLMChatError
from derisk.util.executor_utils import blocking_func_to_async
from derisk.util.logger import colored, digest
from derisk.util.tracer import SpanType, root_tracer
from derisk.sandbox.base import SandboxBase
from . import system_tool_dict
from .action.base import Action, ActionOutput
from .agent import Agent, AgentContext, AgentMessage
from .base_parser import AgentParser
from .file_system.file_tree import TreeNodeData
from .memory.agent_memory import AgentMemory
from .memory.gpts.agent_system_message import AgentSystemMessage
from .memory.gpts.agent_system_message import SystemMessageType, AgentPhase
from .memory.gpts.base import GptsMessage
from .memory.gpts.gpts_memory import GptsMemory, AgentTaskContent, AgentTaskType
from .profile.base import ProfileConfig
from .reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from .role import AgentRunMode, Role
from .sandbox_manager import SandboxManager
from .schema import (
    Status,
    DynamicParam,
    DynamicParamView,
    DynamicParamRenderType,
    DynamicParamType,
    AgentSpaceMode,
    MessageMetrics,
    ActionInferenceMetrics,
)
from .types import AgentReviewInfo, MessageType
from .variable import VariableManager
from .. import BlankAction

from ..resource.base import Resource
from ..util.ext_config import ExtConfigHolder
from ..util.llm.llm import LLMConfig, get_llm_strategy_cls
from ..util.llm.llm_client import AIWrapper, AgentLLMOut
from ...context.event import (
    ChatPayload,
    StepPayload,
    ActionPayload,
    LLMPayload,
    EventType,
    PAYLOAD_TYPE,
    Payload,
    Event,
)
from ...context.operator import ConfigItem
from ...context.window import ContextWindow
from ...util.annotations import Deprecated
from ...util.date_utils import current_ms
from ...util.json_utils import serialize
from ...util.template_utils import render

logger = logging.getLogger(__name__)

T = TypeVar("T")

from .agent_info import (
    AgentInfo,
    AgentMode,
    AgentRegistry,
    PermissionAction,
    PermissionRuleset,
)


class ContextHelper(BaseModel, Generic[T]):
    _context: contextvars.ContextVar[T] = PrivateAttr(
        default_factory=lambda: contextvars.ContextVar("context", default=None)
    )

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
    conv_round_id: Optional[str] = None
    init_uids: List[str] = []
    function_calling_context: Optional[Dict] = None


class ConversableAgent(Role, Agent):
    """ConversableAgent is an agent that can communicate with other agents."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent_context: Optional[AgentContext] = Field(None, description="Agent context")
    actions: List[Type[Action]] = Field(default_factory=list)
    resource: Optional[Resource] = Field(None, description="Resource")
    resource_map: Dict[str, List[Resource]] = Field(
        default_factory=lambda: defaultdict(list),
        description="Resource name to resource list mapping",
    )
    llm_config: Optional[LLMConfig] = None
    bind_prompt: Optional[PromptTemplate] = None
    run_mode: Optional[AgentRunMode] = Field(default=None, description="Run mode")
    max_retry_count: int = 3
    # current_retry_counter: int = 0 # deprecated: 支持并发 改为从runtime_context取
    # recovering: bool = False # deprecated: 支持并发 改为从runtime_context取
    _runtime_context: ContextHelper[RuntimeContext] = PrivateAttr(
        default_factory=lambda: ContextHelper(RuntimeContext)
    )
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

    # 上下文工程相关配置
    context_config: Optional[ConfigItem] = None
    # 扩展配置
    ext_config: Optional[Dict] = None

    # Agent解析器(如果不配置默认走Action解析)
    agent_parser: Optional[AgentParser] = None

    # FunctionCall参数信息
    enable_function_call: bool = False

    is_reasoning_agent: bool = False

    # 沙箱客户端对象，和Agent同生命周期
    sandbox_manager: Optional[SandboxManager] = None

    # ========== 新增：Permission系统和AgentInfo配置 ==========
    # 权限规则集，用于细粒度控制工具访问权限
    permission_ruleset: Optional[PermissionRuleset] = Field(
        default=None, description="Permission ruleset for tool access control"
    )
    # Agent配置信息，支持声明式配置
    agent_info: Optional[AgentInfo] = Field(
        default=None, description="Agent configuration info"
    )
    # Agent模式：primary/subagent
    agent_mode: AgentMode = Field(
        default=AgentMode.PRIMARY, description="Agent mode: primary or subagent"
    )
    # 最大执行步数（替代max_retry_count语义）
    max_steps: Optional[int] = Field(
        default=None, description="Maximum agentic iterations"
    )
    # 可用系统工具（从Role继承）
    available_system_tools: Dict[str, Any] = Field(
        default_factory=dict, description="Available system tools"
    )

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
    def conv_round_id(self) -> str:
        return self._runtime_context.context.conv_round_id

    @conv_round_id.setter
    def conv_round_id(self, value: str):
        self._runtime_context.context.conv_round_id = value

    @property
    def function_calling_context(self) -> Optional[Dict]:
        return self._runtime_context.context.function_calling_context

    @function_calling_context.setter
    def function_calling_context(self, value: Dict):
        self._runtime_context.context.function_calling_context = value

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
        logger.info(
            f"[base_agent.preload_resource] agent={self.agent_context.agent_app_code if self.agent_context else 'unknown'}, "
            f"resource_type={type(self.resource).__name__ if self.resource else 'None'}, "
            f"resource_is_pack={self.resource.is_pack if self.resource and hasattr(self.resource, 'is_pack') else 'N/A'}"
        )
        if self.resource:
            root_tracer.set_current_agent_id(self.agent_context.agent_app_code)
            await self.resource.preload_resource()
        # tidy resource
        self.resource_map = await self._tidy_resource(self.resource)
        logger.info(
            f"[base_agent.preload_resource] after _tidy_resource: "
            f"resource_map_keys={list(self.resource_map.keys()) if self.resource_map else []}"
        )

    async def build(self) -> "ConversableAgent":
        """Build the agent."""

        # Preload resources
        await self.preload_resource()
        # Check if agent is available
        self.check_available()
        _language = self.not_null_agent_context.language
        if _language:
            self.language = _language

        # Initialize LLM Server
        if self.llm_config and self.llm_config.llm_client:
            self.llm_client = AIWrapper(llm_client=self.llm_config.llm_client)

        temp_profile = self.profile
        from copy import deepcopy

        self.profile = deepcopy(temp_profile)

        return self

    async def _tidy_resource(self, resource: Resource) -> dict[str, List[Resource]]:
        """
        将资源包按分类整理为各类子资源。
        前提：is_pack 字段可信；非 pack 资源无 sub_resources。
        """

        def _merge_dicts(d1, d2):
            merged = defaultdict(list)
            for k, v in d1.items():
                merged[k].extend(v)
            for k, v in d2.items():
                merged[k].extend(v)
            return dict(merged)

        logger.debug(
            f"[base_agent._tidy_resource] resource_class={resource.__class__.__name__ if resource else 'None'}, "
            f"is_pack={resource.is_pack if resource and hasattr(resource, 'is_pack') else 'N/A'}"
        )

        if not resource:
            return {}

        resources_map = defaultdict(list)

        if resource.is_pack:
            # 只有 is_pack=True 时才访问 sub_resources
            sub_resources = resource.sub_resources
            logger.debug(
                f"[base_agent._tidy_resource] is_pack=True, sub_resources_count={len(sub_resources) if sub_resources else 0}"
            )
            if sub_resources:  # 允许为空列表
                for item in sub_resources:
                    sub_map = await self._tidy_resource(item)
                    resources_map = _merge_dicts(resources_map, sub_map)
            # 空包：返回空 dict，合理
        else:
            # is_pack=False → 必为叶子节点
            r_type = resource.type()
            # 处理 ResourceType 枚举类型
            if hasattr(r_type, "value"):
                r_type = r_type.value
            if not isinstance(r_type, str):
                raise TypeError(f"Expected resource type to be str, got {type(r_type)}")
            resources_map[r_type].append(resource)
            logger.debug(
                f"[base_agent._tidy_resource] added resource to map: "
                f"type={r_type}, resource_class={resource.__class__.__name__}"
            )

        logger.debug(
            f"[base_agent._tidy_resource] result_keys={list(resources_map.keys())}"
        )
        return dict(resources_map)

    def update_profile(self, profile: ProfileConfig):
        from copy import deepcopy

        self.profile = deepcopy(profile)
        self._inited_profile = self.profile.create_profile(
            prefer_prompt_language=self.language
        )

    def bind(self, target: Any) -> "ConversableAgent":
        """Bind the resources to the agent."""
        if target is None:
            return self
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
        elif isinstance(target, Scheduler):
            self.scheduler = target
        elif isinstance(target, ProfileConfig):
            self.update_profile(target)

        elif isinstance(target, DynamicParam):
            self.dynamic_variables.append(target)
        elif isinstance(target, list) and all(
            [
                isinstance(item, type) and issubclass(item, DynamicParam)
                for item in target
            ]
        ):
            self.dynamic_variables.extend(target)
        elif isinstance(target, PromptTemplate):
            self.bind_prompt = target
        elif isinstance(target, ConfigItem):
            self.context_config = target
        elif isinstance(target, ExtConfigHolder):
            self.ext_config = target.ext_config
        elif isinstance(target, SandboxManager):
            self.sandbox_manager = target
        return self

    async def send(
        self,
        message: AgentMessage,
        recipient: Agent,
        reviewer: Optional[Agent] = None,
        request_reply: Optional[bool] = True,
        reply_to_sender: Optional[bool] = True,  # 是否向sender发送回复消息
        request_sender_reply: Optional[
            bool
        ] = True,  # 向sender发送消息是是否仍request_reply
        is_recovery: Optional[bool] = False,
        silent: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Optional[AgentMessage]:
        """Send a message to recipient agent."""
        with root_tracer.start_span(
            "agent.send",
            metadata={
                "sender": self.name,
                "recipient": recipient.name,
                "reviewer": reviewer.name if reviewer else None,
                "message_id": message.message_id,
                "agent_message": json.dumps(
                    message.to_dict(), default=serialize, ensure_ascii=False
                ),
                "request_reply": request_reply,
                "is_recovery": is_recovery,
                "conv_uid": self.not_null_agent_context.conv_id,
            },
        ):
            return await recipient.receive(
                message=message,
                sender=self,
                reviewer=reviewer,
                request_reply=request_reply,
                reply_to_sender=reply_to_sender,
                request_sender_reply=request_sender_reply,
                is_recovery=is_recovery,
                silent=silent,
                is_retry_chat=is_retry_chat,
                last_speaker_name=last_speaker_name,
                historical_dialogues=historical_dialogues,
                rely_messages=rely_messages,
                **kwargs,
            )

    async def receive(
        self,
        message: AgentMessage,
        sender: "ConversableAgent",
        reviewer: Optional[Agent] = None,
        request_reply: Optional[bool] = None,
        reply_to_sender: Optional[bool] = True,  # 是否向sender发送回复消息
        request_sender_reply: Optional[
            bool
        ] = True,  # 向sender发送消息是是否仍request_reply
        silent: Optional[bool] = False,
        is_recovery: Optional[bool] = False,
        is_retry_chat: bool = False,
        last_speaker_name: Optional[str] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Optional[AgentMessage]:
        """Receive a message from another agent."""

        origin_current_agent_id = root_tracer.get_current_agent_id()
        try:
            root_tracer.set_current_agent_id(self.agent_context.agent_app_code)
            with root_tracer.start_span(
                "agent.receive",
                metadata={
                    "sender": sender.name,
                    "recipient": self.name,
                    "reviewer": reviewer.name if reviewer else None,
                    "agent_message": json.dumps(
                        message.to_dict(), default=serialize, ensure_ascii=False
                    ),
                    "request_reply": request_reply,
                    "silent": silent,
                    "is_recovery": is_recovery,
                    "conv_uid": self.not_null_agent_context.conv_id,
                    "is_human": self.is_human,
                },
            ):
                await ContextWindow.create(agent=self, task_id=message.message_id)
                if silent:
                    message.show_message = False

                await self._a_process_received_message(message, sender)

                if request_reply is False or request_reply is None:
                    return None

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
                            **kwargs,
                        )
                    else:
                        reply = await self.generate_reply(
                            received_message=message,
                            sender=sender,
                            reviewer=reviewer,
                            is_retry_chat=is_retry_chat,
                            historical_dialogues=historical_dialogues,
                            rely_messages=rely_messages,
                            **kwargs,
                        )

                    if reply is not None and reply_to_sender:
                        await self.send(
                            reply, sender, request_reply=request_sender_reply
                        )

                    return reply
        finally:
            root_tracer.set_current_agent_id(origin_current_agent_id)

    async def prepare_act_param(
        self,
        received_message: Optional[AgentMessage],
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Prepare the parameters for the act method."""
        return {}

    def _check_have_resource(self, resource_type: Type[Resource]) -> bool:
        for resources in self.resource_map.values():
            if not resources:  # 防御性检查，避免空列表
                continue
            first = resources[0]
            if isinstance(first, resource_type):
                # 特殊处理：仅当单元素且 is_empty 为 True 时，视为"没有"
                if len(resources) == 1 and getattr(first, "is_empty", False):
                    return False
                else:
                    return True
        return False

    def check_tool_permission(
        self, tool_name: str, command: Optional[str] = None
    ) -> PermissionAction:
        """
        检查工具权限 - 基于新的Permission系统。

        参考 opencode 的权限设计，提供细粒度控制：
        - ASK: 需要用户确认
        - ALLOW: 直接允许
        - DENY: 拒绝执行

        Args:
            tool_name: 工具名称
            command: 命令参数（可选）

        Returns:
            PermissionAction: 权限动作
        """
        # 优先使用 agent_info 中的权限配置
        if self.agent_info and self.agent_info.permission_ruleset:
            return self.agent_info.check_permission(tool_name, command)

        # 其次使用直接的 permission_ruleset
        if self.permission_ruleset:
            return self.permission_ruleset.check(tool_name, command)

        # 检查 tools 配置
        if self.agent_info and tool_name in self.agent_info.tools:
            if not self.agent_info.tools[tool_name]:
                return PermissionAction.DENY

        # 默认允许
        return PermissionAction.ALLOW

    def is_tool_allowed(self, tool_name: str, command: Optional[str] = None) -> bool:
        """检查工具是否被允许执行"""
        action = self.check_tool_permission(tool_name, command)
        return action == PermissionAction.ALLOW

    def is_tool_denied(self, tool_name: str, command: Optional[str] = None) -> bool:
        """检查工具是否被拒绝"""
        action = self.check_tool_permission(tool_name, command)
        return action == PermissionAction.DENY

    def needs_tool_approval(
        self, tool_name: str, command: Optional[str] = None
    ) -> bool:
        """检查工具是否需要用户批准"""
        action = self.check_tool_permission(tool_name, command)
        return action == PermissionAction.ASK

    def get_effective_max_steps(self) -> int:
        """获取有效的最大步骤数"""
        if self.max_steps is not None:
            return self.max_steps
        if self.agent_info and self.agent_info.max_steps:
            return self.agent_info.max_steps
        return self.max_retry_count

    async def sandbox_tool_injection(self):
        ## 如果存在沙箱，需要注入沙箱工具
        if self.sandbox_manager:
            logger.info("注入沙箱工具！")
            from derisk.agent.core.sandbox.sandbox_tool_registry import (
                sandbox_tool_dict,
            )

            self.available_system_tools.update(sandbox_tool_dict)

    async def system_tool_injection(self):
        """
        注入系统工具 - 使用统一工具管理框架

        根据 Agent 的工具绑定配置（来自编辑页面保存的 resource_tool），
        通过 tool_manager 获取已绑定的工具列表并注入。
        """
        from ..tools.registry import tool_registry, register_builtin_tools
        from ..tools.tool_manager import tool_manager
        from ..tools.base import ToolCategory

        # 确保工具已注册
        if not tool_registry._initialized:
            register_builtin_tools()
            logger.info(
                f"[system_tool_injection] Registered {len(tool_registry)} builtin tools"
            )

        # 获取 app_id 用于查询绑定配置
        app_id = None
        agent_name = self.name
        sandbox_enabled = False

        if self.agent_context:
            app_id = self.agent_context.gpts_app_code
            if hasattr(self, "sandbox_manager") and self.sandbox_manager:
                sandbox_enabled = True

        # 尝试从 tool_manager 获取绑定工具
        injected_from_config = False
        if app_id and agent_name:
            try:
                # 设置加载回调
                self._setup_tool_manager_load_callback(tool_manager)

                # 获取运行时工具
                runtime_tools = tool_manager.get_runtime_tools(
                    app_id=app_id,
                    agent_name=agent_name,
                )

                if runtime_tools:
                    for tool in runtime_tools:
                        tool_name = tool.metadata.name
                        if tool_name not in self.available_system_tools:
                            self.available_system_tools[tool_name] = tool
                    logger.info(
                        f"[system_tool_injection] Injected {len(runtime_tools)} tools from binding config"
                    )
                    injected_from_config = True

            except Exception as e:
                logger.warning(
                    f"[system_tool_injection] Failed to get tools from tool_manager: {e}"
                )

        # 无绑定配置时，注入默认工具
        if not injected_from_config:
            await self._inject_default_tools(sandbox_enabled)
            logger.info("[system_tool_injection] Using default tools")

        # 根据绑定资源注入知识和 Agent 系统工具
        await self._inject_resource_based_tools()

        logger.info(
            f"[system_tool_injection] Total tools injected: {len(self.available_system_tools)}"
        )

    def _setup_tool_manager_load_callback(self, tool_manager):
        """设置 tool_manager 的加载回调"""

        def _load_tool_bindings_from_db(app_id: str, agent_name: str):
            """从数据库 ServeEntity.resource_tool 加载工具绑定配置"""
            try:
                from derisk_serve.building.config.models.models import ServeEntity
                from derisk.storage.metadata import UnifiedDBManagerFactory
                from derisk.component import ComponentType
                from derisk._private.config import Config as DeriskConfig
                import json

                CFG = DeriskConfig()
                system_app = CFG.SYSTEM_APP
                if not system_app:
                    return None

                db_manager_factory = system_app.get_component(
                    ComponentType.UNIFIED_METADATA_DB_MANAGER_FACTORY,
                    UnifiedDBManagerFactory,
                    default_component=None,
                )
                if not db_manager_factory:
                    return None

                db_manager = db_manager_factory.create()

                with db_manager.session() as session:
                    # 优先查 temp 配置
                    entity = (
                        session.query(ServeEntity)
                        .filter(
                            ServeEntity.app_code == app_id,
                            ServeEntity.is_published == False,
                        )
                        .order_by(ServeEntity.gmt_modified.desc())
                        .first()
                    )

                    if entity and entity.resource_tool:
                        tool_ids = self._parse_resource_tool_ids(entity.resource_tool)
                        if tool_ids:
                            return tool_ids

                    # 查 published 配置
                    entity = (
                        session.query(ServeEntity)
                        .filter(
                            ServeEntity.app_code == app_id,
                            ServeEntity.is_published == True,
                        )
                        .order_by(ServeEntity.gmt_modified.desc())
                        .first()
                    )

                    if entity and entity.resource_tool:
                        return self._parse_resource_tool_ids(entity.resource_tool)

                return None
            except Exception as e:
                logger.debug(f"Failed to load tool bindings from db: {e}")
                return None

        tool_manager.set_load_callback(_load_tool_bindings_from_db)

    def _parse_resource_tool_ids(self, resource_tool_raw) -> list:
        """解析 resource_tool 字段中的工具ID列表"""
        import json

        if not resource_tool_raw:
            return None

        resource_tool = resource_tool_raw
        if isinstance(resource_tool, str):
            try:
                resource_tool = json.loads(resource_tool)
            except json.JSONDecodeError:
                return None

        if not isinstance(resource_tool, list) or len(resource_tool) == 0:
            return None

        tool_ids = []
        for item in resource_tool:
            try:
                value = item.get("value", "{}")
                if isinstance(value, str):
                    parsed = json.loads(value)
                else:
                    parsed = value
                tool_id = parsed.get("tool_id") or parsed.get("key")
                if tool_id:
                    tool_ids.append(tool_id)
            except (json.JSONDecodeError, AttributeError):
                continue

        return tool_ids if tool_ids else None

    async def _inject_default_tools(self, sandbox_enabled: bool = False):
        """注入默认工具（当无绑定配置时）"""
        from ..tools.registry import tool_registry
        from ..tools.base import ToolCategory

        # 文件系统工具
        file_tools = tool_registry.get_by_category(ToolCategory.FILE_SYSTEM)
        for tool in file_tools:
            if tool.metadata.name not in self.available_system_tools:
                self.available_system_tools[tool.metadata.name] = tool
        logger.info(
            f"[system_tool_injection] Injected {len(file_tools)} FILE_SYSTEM tools (default)"
        )

        # Shell 工具
        shell_tools = tool_registry.get_by_category(ToolCategory.SHELL)
        for tool in shell_tools:
            if tool.metadata.name not in self.available_system_tools:
                self.available_system_tools[tool.metadata.name] = tool
        logger.info(
            f"[system_tool_injection] Injected {len(shell_tools)} SHELL tools (default)"
        )

        # 网络工具
        network_tools = tool_registry.get_by_category(ToolCategory.NETWORK)
        for tool in network_tools:
            if tool.metadata.name not in self.available_system_tools:
                self.available_system_tools[tool.metadata.name] = tool
        if network_tools:
            logger.info(
                f"[system_tool_injection] Injected {len(network_tools)} NETWORK tools (default)"
            )

    async def _inject_resource_based_tools(self):
        """根据绑定资源注入知识、Agent 和数据库系统工具"""
        from ..expand.actions.knowledge_action import KnowledgeSearch
        from ..resource import RetrieverResource
        from ..resource.app import AppResource
        from ..resource.database import DBResource

        if self._check_have_resource(AppResource):
            logger.info("注入Agent工具！")
            from ..expand.actions.agent_action import AgentStart

            agent_tool = AgentStart()
            self.available_system_tools[agent_tool.name] = agent_tool
        if self._check_have_resource(RetrieverResource):
            logger.info("注入知识工具！")
            knowledge_tool = KnowledgeSearch()
            self.available_system_tools[knowledge_tool.name] = knowledge_tool
        if self._check_have_resource(DBResource):
            logger.info("注入数据库工具！")
            self._inject_database_tools()

    def _inject_database_tools(self):
        """注入数据库相关工具（get_table_spec, execute_sql, list_tables）"""
        from ..tools.registry import tool_registry

        db_tool_names = ["get_table_spec", "execute_sql", "list_tables"]

        # 尝试导入 db_tools 模块以触发 @tool 装饰器自动注册
        try:
            import derisk_serve.agent.resource.db_tools  # noqa: F401
        except ImportError:
            logger.debug(
                "[_inject_database_tools] derisk_serve.agent.resource.db_tools "
                "not available, skipping import"
            )

        # 从 registry 中获取已注册的数据库工具并注入
        injected = 0
        for name in db_tool_names:
            tool = tool_registry.get(name)
            if tool and name not in self.available_system_tools:
                self.available_system_tools[name] = tool
                injected += 1

        if injected:
            logger.info(
                f"[_inject_database_tools] Injected {injected} database tools"
            )
        else:
            logger.warning(
                "[_inject_database_tools] No database tools found in registry. "
                "Ensure db_tools module is importable."
            )

    async def agent_state(self):
        if len(self.received_message_state) > 0:
            return Status.RUNNING
        else:
            return Status.WAITING

    def function_callning_reply_messages(
        self,
        llm_out: Optional[AgentLLMOut] = None,
        action_outs: Optional[List[ActionOutput]] = None,
    ) -> List[Dict]:
        function_call_reply_messages: List[Dict] = []
        from derisk.core import ModelMessageRoleType

        ## 历史消息
        if llm_out:
            llm_content = llm_out.content or ""
            if llm_out.thinking_content:
                llm_content = (
                    f"<thinking>{llm_out.thinking_content}</thinking>{llm_content}"
                )
            ## 准备当前轮次的AImessage
            function_call_reply_messages.append(
                {
                    "role": ModelMessageRoleType.AI,
                    "content": llm_content,
                    "tool_calls": llm_out.tool_calls,
                }
            )

        if action_outs:
            ## 准备当前轮次的ToolMessage
            for action_out in action_outs:
                function_call_reply_messages.append(
                    {
                        "role": ModelMessageRoleType.TOOL,
                        "tool_call_id": action_out.action_id,
                        "content": action_out.content,
                    }
                )

        return function_call_reply_messages

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
        # logger.info(
        #     f"generate agent reply!sender={sender}, rely_messages_len={rely_messages}"
        # )
        message_metrics = MessageMetrics()
        message_metrics.start_time_ms = time.time_ns() // 1_000_000

        await self.push_context_event(
            EventType.ChatStart,
            ChatPayload(
                received_message_id=received_message.message_id,
                received_message_content=received_message.content,
            ),
            await self.task_id_by_received_message(received_message),
        )

        root_span = root_tracer.start_span(
            "agent.generate_reply",
            metadata={
                "app_code": self.agent_context.agent_app_code,
                "sender": sender.name,
                "recipient": self.name,
                "reviewer": reviewer.name if reviewer else None,
                "received_message": json.dumps(
                    received_message.to_dict(), default=serialize, ensure_ascii=False
                ),
                "conv_id": self.not_null_agent_context.conv_id,
                "rely_messages": (
                    [msg.to_dict() for msg in rely_messages] if rely_messages else None
                ),
            },
        )
        reply_message = None
        agent_system_message: Optional[AgentSystemMessage] = AgentSystemMessage.build(
            agent_context=self.agent_context,
            agent=self,
            type=SystemMessageType.STATUS,
            phase=AgentPhase.AGENT_RUN,
        )
        self.received_message_state[received_message.message_id] = Status.TODO
        try:
            self.received_message_state[received_message.message_id] = Status.RUNNING

            fail_reason = None
            self.current_retry_counter = 0
            is_success = True
            done = False
            observation = received_message.content or ""
            action_system_message: Optional[AgentSystemMessage] = None

            ## 开始当前的任务空间
            await self.memory.gpts_memory.upsert_task(
                conv_id=self.agent_context.conv_id,
                task=TreeNodeData(
                    node_id=received_message.message_id,
                    parent_id=received_message.goal_id,
                    content=AgentTaskContent(
                        agent_name=self.name,
                        task_type=AgentTaskType.AGENT.value,
                        message_id=received_message.message_id,
                    ),
                    state=self.received_message_state[
                        received_message.message_id
                    ].value,
                    name=received_message.current_goal,
                    description=received_message.content,
                ),
            )

            all_tool_messages: List[Dict] = []
            while not done and self.current_retry_counter < self.max_retry_count:
                with root_tracer.start_span(
                    "agent.generate_reply.loop",
                    metadata={
                        "app_code": self.agent_context.agent_app_code,
                        "conv_id": self.agent_context.conv_id,
                        "current_retry_counter": self.current_retry_counter,
                    },
                ):
                    # 根据收到的消息对当前恢复消息的参数进行初始化
                    rounds = received_message.rounds + 1
                    goal_id = received_message.message_id
                    current_goal = received_message.current_goal
                    observation = received_message.observation
                    if self.current_retry_counter > 0:
                        # Function Calling 模式下，必须构建 tool_messages 传递给 LLM
                        if self.enable_function_call:
                            tool_messages = self.function_callning_reply_messages(
                                agent_llm_out, act_outs
                            )
                            all_tool_messages.extend(tool_messages)

                        if self.run_mode != AgentRunMode.LOOP:
                            observation = reply_message.observation
                            rounds = reply_message.rounds + 1
                    self._update_recovering(is_retry_chat)

                    ### 0.生成当前轮次的新消息

                    reply_message = await self.init_reply_message(
                        received_message=received_message,
                        sender=sender,
                        rounds=rounds,
                        goal_id=goal_id,
                        current_goal=current_goal,
                        observation=observation,
                    )

                    ### 生成的消息先立即推送进行占位
                    await self.memory.gpts_memory.upsert_task(
                        conv_id=self.agent_context.conv_id,
                        task=TreeNodeData(
                            node_id=reply_message.message_id,
                            parent_id=reply_message.goal_id,
                            content=AgentTaskContent(
                                agent_name=self.name,
                                task_type=AgentTaskType.TASK.value,
                                message_id=reply_message.message_id,
                            ),
                            state=Status.TODO.value,
                            name=f"收到任务'{received_message.content}',开始思考...",
                            description="",
                        ),
                    )

                    await self.push_context_event(
                        EventType.StepStart,
                        StepPayload(message_id=reply_message.message_id),
                        await self.task_id_by_received_message(received_message),
                    )
                    ### 1.模型结果生成
                    reply_message, agent_llm_out = await self._generate_think_message(
                        received_message=received_message,
                        sender=sender,
                        new_reply_message=reply_message,
                        rely_messages=rely_messages,
                        historical_dialogues=historical_dialogues,
                        is_retry_chat=is_retry_chat,
                        message_metrics=message_metrics,
                        tool_messages=all_tool_messages,
                        **kwargs,
                    )

                    action_system_message: AgentSystemMessage = (
                        AgentSystemMessage.build(
                            agent_context=self.agent_context,
                            agent=self,
                            type=SystemMessageType.STATUS,
                            phase=AgentPhase.ACTION_RUN,
                            reply_message_id=reply_message.message_id,
                        )
                    )

                    # logger.info(f'after generate_think_message, reply_message:{reply_message}')
                    act_extent_param = await self.prepare_act_param(
                        received_message=received_message,
                        sender=sender,
                        rely_messages=rely_messages,
                        historical_dialogues=historical_dialogues,
                        reply_message=reply_message,
                        agent_llm_out=agent_llm_out,
                        **kwargs,
                    )

                    ### 2.模型消息处理执行
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

                        act_metrics = ActionInferenceMetrics(
                            start_time_ms=time.time_ns() // 1_000_000
                        )
                        act_outs: Optional[
                            Union[List[ActionOutput], ActionOutput]
                        ] = await self.act(
                            message=reply_message,
                            sender=sender,
                            reviewer=reviewer,
                            is_retry_chat=is_retry_chat,
                            last_speaker_name=last_speaker_name,
                            received_message=received_message,
                            agent_context=self.agent_context,
                            agent_llm_out=agent_llm_out,
                            **act_extent_param,
                        )
                        action_report = []
                        if act_outs:
                            act_reports_dict = []
                            if not isinstance(act_outs, list):
                                action_report = [act_outs]
                                act_reports_dict.extend(act_outs.to_dict())
                            else:
                                action_report = act_outs
                                act_reports_dict = [item.to_dict() for item in act_outs]
                            reply_message.action_report = action_report
                            span.metadata["action_report"] = act_reports_dict
                        await self.push_context_event(
                            EventType.AfterStepAction,
                            ActionPayload(action_output=action_report),
                            await self.task_id_by_received_message(received_message),
                        )

                    ### 3.执行结果验证
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
                            reply_message,
                            sender,
                            reviewer,
                            received_message=received_message,
                        )
                        is_success = check_pass
                        span.metadata["check_pass"] = check_pass
                        span.metadata["reason"] = reason

                    await self.push_context_event(
                        EventType.StepEnd,
                        StepPayload(
                            message_id=reply_message.message_id,
                        ),
                        await self.task_id_by_received_message(received_message),
                    )

                    question: str = received_message.content or ""
                    ai_message: str = reply_message.content

                    # Continue to run the next round
                    self.current_retry_counter += 1
                    # 发送当前轮的结果消息(fuctioncall执行结果、非LOOP模式下的异常记录、LOOP模式的上一轮消息)
                    await self.send(reply_message, recipient=self, request_reply=False)
                    # # 任务完成记录任务结论
                    await self.memory.gpts_memory.upsert_task(
                        conv_id=self.agent_context.conv_id,
                        task=TreeNodeData(
                            node_id=reply_message.message_id,
                            parent_id=reply_message.goal_id,
                            content=AgentTaskContent(
                                agent_name=self.name,
                                task_type=AgentTaskType.TASK.value,
                                message_id=reply_message.message_id,
                            ),
                            state=Status.COMPLETE.value
                            if check_pass
                            else Status.FAILED.value,
                            name=received_message.current_goal,
                            description=received_message.content,
                        ),
                    )

                    # 5.Optimize wrong answers myself
                    if not check_pass:
                        #  记录action的失败消息
                        if action_system_message:
                            action_system_message.update(
                                retry_time=self.current_retry_counter,
                                content=json.dumps(
                                    [item.to_dict() for item in act_outs],
                                    ensure_ascii=False,
                                    default=serialize,
                                ),
                                final_status=Status.FAILED,
                                type=SystemMessageType.ERROR,
                            )
                            await self.memory.gpts_memory.append_system_message(
                                action_system_message
                            )

                        if all(not item.have_retry for item in act_outs):
                            logger.warning("No retry available!")
                            break
                        fail_reason = reason

                        # 构建执行历史上下文，确保失败信息能写入记忆
                        extra_context = self._build_memory_context(
                            act_outs, fail_reason
                        )

                        await self.write_memories(
                            question=question,
                            ai_message=ai_message,
                            action_output=act_outs,
                            check_pass=check_pass,
                            check_fail_reason=fail_reason,
                            agent_id=self.not_null_agent_context.agent_app_code,
                            reply_message=reply_message,
                            terminate=any([act_out.terminate for act_out in act_outs]),
                            extra_context=extra_context,
                        )
                        ## Action明确结束的，成功后直接退出
                        if any([act_out.terminate for act_out in act_outs]):
                            break
                        ## ask_user需要跳出循环，等待用户输入后重新开启循环
                        if any([act_out.ask_user for act_out in act_outs]):
                            logger.info(f"Agent {self.name} paused for user input (ask_user)")
                            break
                    else:
                        # 记录action的成功消息
                        if action_system_message:
                            await self.memory.gpts_memory.append_system_message(
                                action_system_message
                            )

                        current_round = self.current_retry_counter + 1
                        # Successful reply
                        await self.write_memories(
                            question=question,
                            ai_message=ai_message,
                            action_output=act_outs,
                            check_pass=check_pass,
                            agent_id=self.not_null_agent_context.agent_app_code
                            or self.not_null_agent_context.gpts_app_code,
                            reply_message=reply_message,
                            terminate=any([act_out.terminate for act_out in act_outs]),
                            current_retry_counter=current_round,
                        )

                        ### 非LOOP模式以及非FunctionCall模式
                        if (
                            self.run_mode != AgentRunMode.LOOP
                            and not self.enable_function_call
                        ):
                            logger.debug(
                                f"Agent {self.name} reply success!{reply_message}"
                            )
                            break
                        ## Action明确结束的，成功后直接退出
                        if any([act_out.terminate for act_out in act_outs]):
                            break
                        ## ask_user需要跳出循环，等待用户输入后重新开启循环
                        if any([act_out.ask_user for act_out in act_outs]):
                            logger.info(f"Agent {self.name} paused for user input (ask_user)")
                            break

            reply_message.success = is_success
            # 6.final message adjustment
            await self.adjust_final_message(is_success, reply_message)

            await self.push_context_event(
                EventType.ChatEnd,
                ChatPayload(
                    received_message_id=received_message.message_id,
                    received_message_content=received_message.content,
                ),
                await self.task_id_by_received_message(received_message),
            )

            self.received_message_state[received_message.message_id] = Status.COMPLETE
            reply_message.metrics.action_metrics = [
                ActionInferenceMetrics.create_metrics(act_out.metrics or act_metrics)
                for act_out in act_outs
            ]
            reply_message.metrics.end_time_ms = time.time_ns() // 1_000_000

            return reply_message

        except Exception as e:
            logger.exception("Generate reply exception!")
            if reply_message:
                err_message = reply_message
            else:
                err_message = AgentMessage(
                    message_id=uuid.uuid4().hex,
                    goal_id=received_message.message_id,
                    content="",
                )
                err_message.rounds = 9999
            err_message.action_report = [await BlankAction().run(f"ERROR:{str(e)}")]
            err_message.success = False

            agent_system_message.update(
                1,
                content=json.dumps({self.name: str(e)}, ensure_ascii=False),
                final_status=Status.FAILED,
                type=SystemMessageType.ERROR,
            )
            self.received_message_state[received_message.message_id] = Status.FAILED

            return err_message
        finally:
            ## 更新当前的任务空间
            await self.memory.gpts_memory.upsert_task(
                conv_id=self.agent_context.conv_id,
                task=TreeNodeData(
                    node_id=received_message.message_id,
                    parent_id=received_message.goal_id,
                    state=self.received_message_state[
                        received_message.message_id
                    ].value,
                    name=received_message.current_goal,
                    description=received_message.content,
                ),
            )
            if reply_message:
                root_span.metadata["reply_message"] = reply_message.to_dict()
                if agent_system_message:
                    agent_system_message.agent_message_id = reply_message.message_id
                    await self.memory.gpts_memory.append_system_message(
                        agent_system_message
                    )
            ## 处理消息状态
            self.received_message_state.pop(received_message.message_id)
            root_span.end()

    async def listen_thinking_stream(
        self,
        llm_out: AgentLLMOut,
        reply_message_id: str,
        start_time: datetime,
        cu_thinking_incr: Optional[str] = None,
        cu_content_incr: Optional[str] = None,
        is_first_chunk: bool = False,
        is_first_content: bool = False,
        received_message: Optional[AgentMessage] = None,
        reply_message: Optional[AgentMessage] = None,
        sender: Optional[Agent] = None,
        prev_content: Optional[str] = None,
    ):
        if not self.stream_out:
            return
        if len(llm_out.content) > 0 and not self.content_stream_out:
            if is_first_content:
                cu_content_incr = "正在思考规划..."
            else:
                return
        temp_message = {
            "uid": reply_message_id,
            "type": "incr",
            "message_id": reply_message_id,
            "conv_id": self.not_null_agent_context.conv_id,
            "task_goal_id": reply_message.goal_id if reply_message else "",
            "goal_id": reply_message.goal_id if reply_message else "",
            "task_goal": reply_message.current_goal if reply_message else "",
            "conv_session_uid": self.agent_context.conv_session_id,
            "app_code": self.agent_context.gpts_app_code,
            "sender": self.name or self.role,
            "sender_name": self.name,
            "sender_role": self.role,
            "model": llm_out.llm_name,
            "llm_avatar": None,  # TODO
            "thinking": cu_thinking_incr,
            "content": cu_content_incr,
            "avatar": self.avatar,
            "observation": received_message.observation if received_message else "",
            "status": Status.RUNNING.value,
            "start_time": start_time,
            "metrics": MessageMetrics(llm_metrics=llm_out.metrics).to_dict(),
            "prev_content": prev_content,
        }
        if self.not_null_agent_context.output_process_message or self.is_final_role:
            await self.memory.gpts_memory.push_message(
                self.not_null_agent_context.conv_id,
                stream_msg=temp_message,
                is_first_chunk=is_first_chunk,
                incremental=self.not_null_agent_context.incremental,
                sender=sender,
            )

    async def reset_stream_vis(self, message_id: str, thinking: Optional[str]):
        """重置模型流式输出期间的vis显示"""
        await self.memory.gpts_memory.push_message(
            self.not_null_agent_context.conv_id,
            stream_msg={
                "uid": message_id,
                "message_id": message_id,
                "conv_id": self.not_null_agent_context.conv_id,
                "conv_session_uid": self.agent_context.conv_session_id,
                "app_code": self.agent_context.gpts_app_code,
                "sender": self.name or self.role,
                "sender_role": self.role,
                "thinking": thinking,
                "content": "",
                "avatar": self.avatar,
                "start_time": datetime.now(),
            },
            incremental=self.not_null_agent_context.incremental,
            incr_type="all",
        )

    def _update_recovering(self, is_retry_chat: bool):
        self.recovering = (
            True if self.current_retry_counter == 0 and is_retry_chat else False
        )

    async def _recovery_message(self) -> AgentMessage | None:
        # 从DB读取全量message数据
        messages: List[
            GptsMessage
        ] = await self.memory.gpts_memory.message_memory.get_by_conv_id(
            self.not_null_agent_context.conv_id
        )
        # 找到最后一条调用模型的消息
        last_speak_message: AgentMessage = next(
            (
                message.to_agent_message()
                for message in reversed(messages)
                if message.sender_name == self.name and message.model_name
            ),
            None,
        )
        if not last_speak_message:
            return None
        reply_message = await self.init_reply_message(
            received_message=last_speak_message, rounds=len(messages)
        )
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
        new_reply_message: AgentMessage,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        is_retry_chat: bool = False,
        message_metrics: Optional[MessageMetrics] = None,
        tool_messages: Optional[List[Dict]] = None,
        **kwargs,
    ) -> Tuple[AgentMessage, Optional[AgentLLMOut]]:
        ### 0.其他消息处理逻辑
        if self.recovering:
            recovering_message = await self._recovery_message()
            if recovering_message:
                recovering_message.metrics = message_metrics or MessageMetrics()
                return recovering_message, AgentLLMOut(
                    llm_name=recovering_message.model_name,
                    thinking_content=recovering_message.thinking,
                    content=recovering_message.content,
                    tool_calls=recovering_message.tool_calls,
                )

        ### 1.初始化待恢复消息
        reply_message = new_reply_message
        reply_message.metrics = message_metrics or MessageMetrics()
        # 兼容并行AgentAction rounds在会话内递增
        reply_message.rounds = await self.memory.gpts_memory.next_message_rounds(
            self.not_null_agent_context.conv_id
        )
        ### 2.加载准备模型消息
        (
            thinking_messages,
            resource_info,
            system_prompt,
            user_prompt,
        ) = await self.load_thinking_messages(
            received_message=received_message,
            sender=sender,
            rely_messages=rely_messages,
            historical_dialogues=historical_dialogues,
            context=reply_message.get_dict_context(),
            is_retry_chat=is_retry_chat,
            **kwargs,
        )
        reply_message.system_prompt = system_prompt
        reply_message.user_prompt = user_prompt
        message_metrics.context_complete = time.time_ns() // 1_000_000

        ### 3.开始进行模型推理
        with root_tracer.start_span(
            "agent.generate_reply.thinking",
            metadata={
                "app_code": self.agent_context.agent_app_code,
                "conv_uid": self.agent_context.conv_id,
                "succeed": False,
                "thinking_messages": json.dumps(
                    [msg.to_dict() for msg in thinking_messages],
                    ensure_ascii=False,
                    default=serialize,
                ),
            },
        ) as span:
            # 1.Think about how to do things
            llm_out: AgentLLMOut = await self.thinking(
                thinking_messages,
                reply_message.message_id,
                sender,
                received_message=received_message,
                tool_messages=tool_messages,
                reply_message=reply_message,
            )

            reply_message.thinking = llm_out.thinking_content
            reply_message.model_name = llm_out.llm_name
            reply_message.content = llm_out.content

            reply_message.metrics.llm_metrics = llm_out.metrics
            reply_message.resource_info = resource_info
            reply_message.tool_calls = llm_out.tool_calls
            reply_message.input_tools = llm_out.input_tools

            span.metadata["llm_reply"] = llm_out.content
            span.metadata["model_name"] = llm_out.llm_name
            span.metadata["succeed"] = True

        ### 4.模型消息审查
        with root_tracer.start_span(
            "agent.generate_reply.review",
            metadata={"llm_reply": llm_out.content, "censored": self.name},
        ) as span:
            # 2.Review whether what is being done is legal
            approve, comments = await self.review(llm_out.content, self)
            reply_message.review_info = AgentReviewInfo(
                approve=approve,
                comments=comments,
            )
            span.metadata["approve"] = approve
            span.metadata["comments"] = comments

        return reply_message, llm_out

    async def thinking(
        self,
        messages: List[AgentMessage],
        reply_message_id: str,
        sender: Optional[Agent] = None,
        prompt: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        reply_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> Optional[AgentLLMOut]:
        last_model = None
        last_err = None
        retry_count = 0
        llm_messages = [message.to_llm_message() for message in messages]
        start_time: datetime = datetime.now()

        # LLM inference automatically retries 3 times to reduce interruption
        # probability caused by speed limit and network stability
        while retry_count < 3:
            llm_model = None
            llm_context = None
            with root_tracer.start_span(
                "agent.thinking",
                metadata={
                    "app_code": self.agent_context.agent_app_code,
                    "retry_count": retry_count,
                    "llm_model": "-",
                    "succeed": False,
                    "ttft": 0,
                },
            ) as span:
                llm_system_message: AgentSystemMessage = AgentSystemMessage.build(
                    agent_context=self.agent_context,
                    agent=self,
                    type=SystemMessageType.STATUS,
                    phase=AgentPhase.LLM_CALL,
                    reply_message_id=reply_message_id,
                )
                try:
                    llm_model, llm_context = await self.select_llm_model(last_model)
                    span.metadata["llm_model"] = llm_model
                    # logger.info(f"model:{llm_model} chat begin!retry_count:{retry_count}")
                    if prompt:
                        llm_messages = _new_system_message(prompt) + llm_messages

                    ## 处理模型function call相关的参数
                    tool_messages: Optional[List[dict]] = kwargs.get("tool_messages")
                    if tool_messages:
                        llm_messages.extend(tool_messages)

                    if not self.llm_client:
                        raise ValueError("LLM client is not initialized!")

                    prev_thinking = ""
                    prev_content = ""

                    thinking_chunk_count = 0
                    content_chunk_count = 0
                    agent_llm_out = None
                    start_ms = current_ms()
                    async for output in self.llm_client.create(
                        context=llm_messages[-1].pop("context", None),
                        messages=llm_messages,
                        llm_model=llm_model,
                        mist_keys=self.mist_keys,
                        max_new_tokens=self.not_null_agent_context.max_new_tokens,
                        temperature=self.not_null_agent_context.temperature,
                        llm_context=llm_context,
                        verbose=self.not_null_agent_context.verbose,
                        trace_id=self.not_null_agent_context.trace_id,
                        rpc_id=self.not_null_agent_context.rpc_id,
                        function_calling_context=self.function_calling_context,  # 使用function call 模式下 Agent构建参数，默认为空
                        staff_no=self.not_null_agent_context.staff_no,
                    ):
                        # 处理收到的模型输出，从全量内容中分别解析出增量thinking 和 增量content， 后续恢复到模型对接层来做
                        agent_llm_out = output
                        current_thinking = output.thinking_content
                        current_content = output.content

                        if self.not_null_agent_context.incremental:
                            res_thinking = current_thinking[len(prev_thinking) :]
                            res_content = current_content[len(prev_content) :]
                            prev_thinking = current_thinking
                            temp_prev_content = current_content

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
                            temp_prev_content = res_content

                        # 输出标记检测
                        if len(prev_thinking) > 0 and len(temp_prev_content) <= 0:
                            thinking_chunk_count = thinking_chunk_count + 1
                        if len(prev_content) > 0:
                            content_chunk_count = content_chunk_count + 1
                        is_first_chunk = thinking_chunk_count == 1
                        is_first_content = content_chunk_count == 1
                        if is_first_chunk:
                            span.metadata["ttft"] = current_ms() - start_ms

                        await self.listen_thinking_stream(
                            output,
                            reply_message_id,
                            start_time=start_time,
                            cu_thinking_incr=res_thinking,
                            cu_content_incr=res_content,
                            is_first_chunk=is_first_chunk,
                            is_first_content=is_first_content,
                            received_message=received_message,
                            reply_message=reply_message,
                            sender=sender,
                            prev_content=prev_content,
                        )

                        prev_content = temp_prev_content
                    await self.reset_stream_vis(
                        reply_message_id, agent_llm_out.thinking_content
                    )
                    await self.push_context_event(
                        EventType.AfterLLMInvoke,
                        LLMPayload(
                            model_name=agent_llm_out.llm_name,
                            metrics=agent_llm_out.metrics.to_dict()
                            if agent_llm_out.metrics
                            else None,
                            messages=[message.to_dict() for message in messages],
                        ),
                        await self.task_id_by_received_message(received_message),
                    )
                    span.metadata["succeed"] = True
                    return agent_llm_out
                except LLMChatError as e:
                    logger.exception(
                        f"model:{llm_model} generate Failed!{str(e)},{e.original_exception}"
                    )

                    llm_system_message.update(
                        retry_time=retry_count + 1,
                        content=json.dumps({llm_model: str(e)}, ensure_ascii=False),
                        final_status=Status.FAILED,
                        type=SystemMessageType.ERROR,
                    )

                    if e.original_exception and e.original_exception > 0:
                        ## TODO 可以尝试发一个系统提示消息

                        ## 模型调用返回错误码大于0，可以使用其他模型兜底重试，小于0 没必要重试直接返回异常
                        retry_count += 1
                        last_model = llm_model
                        last_err = str(e)
                        await asyncio.sleep(1)
                    else:
                        raise
                except Exception as e:
                    logger.exception(f"model:{llm_model} generate Failed!{str(e)}")

                    llm_system_message.update(
                        retry_time=retry_count + 1,
                        content=json.dumps({llm_model: str(e)}, ensure_ascii=False),
                        final_status=Status.FAILED,
                        type=SystemMessageType.ERROR,
                    )
                    last_err = last_err or str(e)
                    break
                finally:
                    await self.memory.gpts_memory.append_system_message(
                        agent_system_message=llm_system_message
                    )

        if last_err:
            raise ValueError(last_err)
        else:
            raise ValueError("LLM model inference failed!")

    @Deprecated(
        reason="thinking instead.",
        version="0.1.0",
        remove_version="0.5.0",
        alternative="thinking()",
    )
    async def thinking_old(
        self,
        messages: List[AgentMessage],
        reply_message_id: str,
        sender: Optional[Agent] = None,
        prompt: Optional[str] = None,
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Think and reason about the current task goal.

        Args:
            messages(List[AgentMessage]): the messages to be reasoned
            prompt(str): the prompt to be reasoned
        """
        out = await self.thinking(
            messages, reply_message_id, sender, prompt, received_message, **kwargs
        )
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
        received_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> List[ActionOutput]:
        """Perform actions."""
        act_outs: List[ActionOutput] = []
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
                    "conv_id": self.not_null_agent_context.conv_id,
                    "action_index": i,
                    "total_action": len(self.actions),
                    "app_code": self.agent_context.agent_app_code,
                    "action": action.name,
                },
            ) as span:
                ai_message = message.content if message.content else ""
                real_action: Action = action(resource=self.resource)
                await real_action.init_action(
                    render_protocol=self.memory.gpts_memory.vis_converter(
                        self.not_null_agent_context.conv_id
                    )
                )

                logger.info(f"ai_message:{ai_message}, prepare to call tools")
                explicit_keys = [
                    "ai_message",
                    "resource",
                    "rely_action_out",
                    "render_protocol",
                    "message_id",
                    "sender",
                    "agent",
                    "current_message",
                    "received_message",
                    "agent_context",
                    "memory",
                ]

                # 创建一个新的kwargs，它不包含explicit_keys中出现的键
                filtered_kwargs = {
                    k: v for k, v in kwargs.items() if k not in explicit_keys
                }
                last_out = await real_action.run(
                    ai_message=message.content if message.content else "",
                    resource=self.resource,
                    rely_action_out=last_out,
                    render_protocol=await self.memory.gpts_memory.async_vis_converter(
                        self.not_null_agent_context.conv_id
                    ),
                    message_id=message.message_id,
                    sender=sender,
                    agent=self,
                    current_message=message,
                    received_message=received_message,
                    agent_context=self.agent_context,
                    memory=self.memory,
                    **filtered_kwargs,
                )
                if last_out:
                    act_outs.append(last_out)
                span.metadata["action_name"] = (
                    last_out.action_name if last_out else None
                )
                span.metadata["action_out"] = last_out.to_dict() if last_out else None
                await self.push_context_event(
                    EventType.AfterAction,
                    ActionPayload(action_output=last_out),
                    await self.task_id_by_received_message(received_message),
                )
        # if not act_outs:
        #     raise ValueError("Action should return value！")
        return act_outs

    def _build_memory_context(
        self,
        action_outputs: List[ActionOutput],
        fail_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建记忆上下文，把执行历史转换为模板需要的 action 和 observation 变量。

        Args:
            action_outputs: 执行结果列表
            fail_reason: 失败原因

        Returns:
            包含 action、observation 等模板变量的字典
        """
        if not action_outputs:
            return {}

        action_texts = []
        observation_texts = []
        action_input_texts = []

        for i, out in enumerate(action_outputs):
            # 构建动作描述
            action_desc = out.action if out.action else f"step_{i + 1}"
            action_texts.append(f"[{i + 1}] {action_desc}")

            # 构建执行结果（观察）
            obs_parts = []
            if not out.is_exe_success:
                obs_parts.append(
                    f"执行失败: {out.content if out.content else '未知错误'}"
                )
            elif out.observations:
                obs_parts.append(out.observations)
            elif out.content:
                # 截取过长内容
                content = (
                    out.content[:500] + "..." if len(out.content) > 500 else out.content
                )
                obs_parts.append(content)

            if obs_parts:
                observation_texts.append(f"[{i + 1}] " + "\n    ".join(obs_parts))

            # 添加动作输入
            if out.action_input:
                action_input_texts.append(f"[{i + 1}] {out.action_input}")

        extra_context = {}
        if action_texts:
            extra_context["action"] = "\n".join(action_texts)
        if observation_texts:
            extra_context["observation"] = "\n".join(observation_texts)
        if action_input_texts:
            extra_context["action_input"] = "\n".join(action_input_texts)
        if fail_reason:
            extra_context["fail_reason"] = fail_reason

        return extra_context

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
        action_outputs: Optional[List[ActionOutput]] = message.action_report
        if action_outputs:
            failed_action_outs = [
                item for item in action_outputs if not item.is_exe_success
            ]
            if failed_action_outs and len(failed_action_outs) >= 1:
                return False, "\n".join(
                    [
                        f"Action:{item.action}, failed to execute, reason: {item.content}"
                        for item in failed_action_outs
                    ]
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
        agent_message = AgentMessage.from_media_messages(
            message, None, message_rounds, context=kwargs
        )
        agent_message.goal_id = agent_message.goal_id or agent_message.message_id
        agent_message.role = "Human"
        agent_message.name = "User"

        message_type = (
            MessageType.ActionApproval.value
            if approval_message_id
            else MessageType.AgentMessage.value
        )
        agent_message.message_type = message_type
        with root_tracer.start_span(
            "agent.initiate_chat",
            span_type=SpanType.AGENT,
            metadata={
                "sender": self.name,
                "recipient": recipient.name,
                "reviewer": reviewer.name if reviewer else None,
                "agent_message": json.dumps(
                    agent_message.to_dict(),
                    ensure_ascii=False,
                    default=serialize,
                ),
                "conv_uid": self.not_null_agent_context.conv_id,
            },
        ):
            ## 开始对话的时候 在记忆中记录Agent相关数据
            await self.memory.gpts_memory.set_agents(
                self.agent_context.conv_id, recipient
            )

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
        self.actions: List[Type[Action]] = actions

    async def _a_append_message(
        self,
        message: AgentMessage,
        role=None,
        sender: Agent = None,
        receiver: Optional[Agent] = None,
        save_db: bool = True,
    ) -> bool:
        gpts_message: GptsMessage = GptsMessage.from_agent_message(
            message=message, sender=sender, role=role, receiver=receiver
        )

        await self.memory.gpts_memory.append_message(
            self.not_null_agent_context.conv_id,
            gpts_message,
            sender=sender,
            save_db=save_db,
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

        content = json.dumps(
            message.content,
            ensure_ascii=False,
            default=serialize,
        )
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
            action_report_msg = ""
            name = sender.name if sender.name else sender.role
            for item in action_report:
                action_msg = (
                    "execution succeeded" if item.is_exe_success else "execution failed"
                )
                action_report_msg = (
                    action_report_msg + f"{action_msg},\n{item.content}\n"
                )
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

    async def get_agent_llm_context_length(self) -> int:
        default_length = 64 * 1024
        model_list = self.llm_config.strategy_context
        if not model_list:
            return default_length
        if isinstance(model_list, str):
            try:
                model_list = json.loads(model_list)
            except Exception:
                return default_length

        if self.llm_client:
            try:
                llm_metadata = await self.llm_client.get_model_metadata(model_list[0])
                context_length = llm_metadata.context_length
                logger.info(
                    f"llm token limit model_name: {model_list[0]}, context_length: {context_length}"
                )
                return context_length or default_length
            except Exception as e:
                logger.warning(
                    f"Failed to get model metadata: {e}, using default context length"
                )
                return default_length

        return default_length

    def register_variables(self):
        """子类通过重写此方法注册变量"""

        # logger.info(f"register_variables {self.role}")

        @self._vm.register("out_schema", "Agent模型输出结构定义")
        def var_out_schema(instance):
            if instance and hasattr(instance, "agent_parser") and instance.agent_parser:
                return instance.agent_parser.schema()
            elif instance and instance.actions:
                return instance.actions[0]().ai_out_schema
            else:
                return None

        @self._vm.register("now", "当前日期")
        def var_now(instance):
            return datetime.now().strftime("%Y-%m-%d")

        @self._vm.register("now_time", "当前时间")
        def var_now_time(instance):
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        @self._vm.register("conv_start_time", "对话开始时间")
        def var_conv_start_time(instance, agent_context=None):
            if agent_context and getattr(agent_context, "conv_start_time", None):
                return agent_context.conv_start_time
            return None

        @self._vm.register("user_name", "用户名")
        def var_user_name(instance, agent_context=None):
            if agent_context and getattr(agent_context, "user_name", None):
                return agent_context.user_name
            return None

        @self._vm.register("user_id", "用户ID")
        def var_user_id(instance, agent_context=None):
            if agent_context and getattr(agent_context, "user_id", None):
                return agent_context.user_id
            return None

        @self._vm.register("resource_prompt", "绑定资源Prompt")
        def var_resource_info(resource_prompt: Optional[str] = None):
            if resource_prompt:
                return resource_prompt
            return None

        @self._vm.register("most_recent_memories", "对话记忆")
        async def var_most_recent_memories(instance, received_message, rely_messages):
            if not instance.agent_context:
                return ""
            # logger.info(f"对话记忆加载:{instance.agent_context.conv_id}")
            observation = received_message.content
            memories = await instance.read_memories(
                question=observation,
                conv_id=instance.agent_context.conv_session_id,
                agent_id=instance.agent_context.agent_app_code,
                llm_token_limit=await self.get_agent_llm_context_length(),
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

        @self._vm.register("question", "接收消息内容")
        def var_question(received_message):
            if received_message:
                return received_message.content
            return None

        @self._vm.register("sandbox", "沙箱配置")
        async def var_sandbox(instance):
            logger.info("注入沙箱配置信息，如果存在沙箱客户端即默认使用沙箱")
            if instance and instance.sandbox_manager:
                if instance.sandbox_manager.initialized == False:
                    logger.warning(
                        f"沙箱尚未准备完成!({instance.sandbox_manager.client.provider}-{instance.sandbox_manager.client.sandbox_id})"
                    )
                sandbox_client: SandboxBase = instance.sandbox_manager.client
                from derisk.agent.core.sandbox.sandbox_tool_registry import (
                    sandbox_tool_dict,
                )
                from derisk.agent.core.sandbox.prompt import sandbox_prompt

                sandbox_tool_prompts = []
                for k, v in sandbox_tool_dict.items():
                    prompt, _ = await v.get_prompt(lang=instance.agent_context.language)
                    sandbox_tool_prompts.append(prompt)
                param = {
                    "sandbox": {
                        "tools": "\n- ".join([item for item in sandbox_tool_prompts]),
                        "work_dir": sandbox_client.work_dir,
                        "use_agent_skill": sandbox_client.enable_skill,
                        "agent_skill_dir": sandbox_client.skill_dir,
                    }
                }

                return {
                    "enable": True if sandbox_client else False,
                    "prompt": render(sandbox_prompt, param),
                }
            else:
                return {"enable": False, "prompt": ""}

        # logger.info(f"register_variables end {self.role}")

    def init_variables(self) -> List[DynamicParam]:
        results: List[DynamicParam] = []
        ## 初始化系统参数
        system_variables = [
            {"key": "role", "value": self.role, "description": "Agent角色"},
            {"key": "name", "value": self.name, "description": "Agent名字"},
            {"key": "goal", "value": self.goal, "description": "Agent目标"},
            {
                "key": "expand_prompt",
                "value": self.expand_prompt,
                "description": "Agent扩展提示词",
            },
            {"key": "language", "value": self.language, "description": "Agent语言设定"},
            {
                "key": "constraints",
                "value": self.constraints,
                "description": "Agent默认约束设定(Prompt使用)",
            },
            {
                "key": "examples",
                "value": self.examples,
                "description": "Agent消息示例(Prompt使用)",
            },
        ]
        for item in system_variables:
            results.append(
                DynamicParam(
                    key=item["key"],
                    name=item["key"],
                    type=DynamicParamType.SYSTEM.value,
                    value=item["value"],
                    description=item["description"],
                    config=None,
                )
            )

        ## 初始化加载Agent参数
        for k, v in self._vm.get_all_variables().items():
            results.append(
                DynamicParam(
                    key=k,
                    name=k,
                    type=DynamicParamType.AGENT.value,
                    value=None,
                    description=v.get("description"),
                    config=None,
                )
            )
        return results

    async def get_all_custom_variables(self) -> List[DynamicParam]:
        from derisk.agent.core.reasoning.reasoning_arg_supplier import (
            ReasoningArgSupplier,
        )

        arg_suppliers: Dict[str, ReasoningArgSupplier] = (
            ReasoningArgSupplier.get_all_suppliers()
        )
        results: List[DynamicParam] = []
        for k, v in arg_suppliers.items():
            results.append(
                DynamicParam(
                    key=k,
                    name=v.arg_key,
                    type=DynamicParamType.CUSTOM.value,
                    value=None,
                    description=v.description,
                    config=v.params,
                )
            )
        return results

    async def variables_view(
        self, params: List[DynamicParam], **kwargs
    ) -> Dict[str, DynamicParamView]:
        logger.info(f"render_dynamic_variables: {params}")

        param_view: Dict[str, DynamicParamView] = {}
        for param in params:
            if param.type == DynamicParamType.SYSTEM.value:
                continue
            elif param.type == DynamicParamType.AGENT.value:
                view = DynamicParamView(**param.to_dict())
                view.render_mode = DynamicParamRenderType.VIS.value
                try:
                    view.render_content = await self._vm.get_value(
                        param.key, instance=self, **kwargs
                    )
                except Exception as e:
                    logger.warning(
                        f"Agent[{self.role}]内置变量[{param.name}]无法可视化！{str(e)}"
                    )
                    view.can_render = False

                param_view[param.key] = view

            else:
                arg_supplier: ReasoningArgSupplier = ReasoningArgSupplier.get_supplier(
                    param.key
                )
                view = DynamicParamView(**param.to_dict())
                try:
                    prompt_param: dict[str, str] = {}
                    await arg_supplier.supply(prompt_param, self, self.agent_context)
                    view.render_content = prompt_param[param.key]
                except Exception as e:
                    logger.warning(
                        f"Agent[{self.role}]自定义变量[{param.name}]无法可视化！{str(e)}"
                    )
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
                variable_values[k] = await self._vm.get_value(
                    k,
                    instance=self,
                    agent_context=self.not_null_agent_context,
                    received_message=received_message,
                    sender=sender,
                    rely_messages=rely_messages,
                    historical_dialogues=historical_dialogues,
                    context=context,
                    resource_info=resource_info,
                    **kwargs,
                )

        for param in self.dynamic_variables:
            if param.type == DynamicParamType.SYSTEM.value:
                continue
            elif param.type == DynamicParamType.AGENT.value:
                continue
            else:
                arg_supplier: ReasoningArgSupplier = ReasoningArgSupplier.get_supplier(
                    param.name
                )
                if arg_supplier:
                    await arg_supplier.supply(
                        variable_values,
                        agent=self,
                        agent_context=self.not_null_agent_context,
                        received_message=received_message,
                        **kwargs,
                    )
                else:
                    logger.warning(
                        f"No supplier found for dynamic variable: {param.name}"
                    )

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
            oai_messages.append(item.to_agent_message())
        return oai_messages

    async def select_llm_model(
        self, excluded_models: Optional[List[str]] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache

        # 使用全局缓存获取模型配置
        all_models = ModelConfigCache.get_all_models()

        if not all_models:
            # 回退到原有逻辑
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
                    self.not_null_llm_config.llm_param,
                )
                return await llm_strategy.next_llm(excluded_models=excluded_models)
            except Exception as e:
                logger.error(f"{self.role} get next llm failed!{str(e)}")
                raise ValueError(f"Failed to allocate model service,{str(e)}!")

        # 获取优先级列表
        strategy_context = self.llm_config.strategy_context if self.llm_config else None
        model_list = []
        if strategy_context:
            if isinstance(strategy_context, list):
                model_list = strategy_context
            elif isinstance(strategy_context, str):
                try:
                    import json

                    model_list = json.loads(strategy_context)
                except:
                    model_list = [strategy_context]

        # 如果没有优先级列表，使用配置中的所有模型
        if not model_list:
            model_list = all_models

        # 根据 excluded_models 过滤，返回第一个可用模型
        excluded = excluded_models or []
        for model_name in model_list:
            if model_name not in excluded and ModelConfigCache.has_model(model_name):
                logger.info(f"select_llm_model: using model={model_name}")
                return model_name, None

        # 如果所有模型都被排除了，返回第一个模型
        if model_list:
            logger.warning(
                f"select_llm_model: all models excluded, using first model={model_list[0]}"
            )
            return model_list[0], None

        raise ValueError("No model available!")

    @property
    def mist_keys(self) -> Optional[List[str]]:
        return (
            self.agent_context.mist_keys
            if self.agent_context.mist_keys
            else self.llm_config.mist_keys
            if self.llm_config
            else None
        )

    async def init_reply_message(
        self,
        received_message: AgentMessage,
        sender: Optional[Agent] = None,
        rounds: Optional[int] = None,
        goal_id: Optional[str] = None,
        current_goal: Optional[str] = None,
        observation: Optional[str] = None,
        **kwargs,
    ) -> AgentMessage:
        """Create a new message from the received message.

        Initialize a new message from the received message

        Args:
            received_message(AgentMessage): The received message

        Returns:
            AgentMessage: A new message
        """
        with root_tracer.start_span(
            "agent.generate_reply.init_reply_message",
        ) as span:
            new_message = AgentMessage.init_new(
                content="",
                current_goal=current_goal or received_message.current_goal,
                goal_id=goal_id or received_message.goal_id,
                context=received_message.context,
                rounds=rounds if rounds is not None else received_message.rounds + 1,
                conv_round_id=self.conv_round_id,
                name=self.name,
                role=self.role,
                show_message=self.show_message,
                observation=observation or received_message.observation,
            )
            # await self._a_append_message(new_message, None, self, save_db=False)

            span.metadata["reply_message"] = new_message.to_dict()

        return new_message

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

    async def load_thinking_messages(
        self,
        received_message: AgentMessage,
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        context: Optional[Dict[str, Any]] = None,
        is_retry_chat: bool = False,
        force_use_historical: bool = False,
        **kwargs,
    ) -> Tuple[List[AgentMessage], Optional[Dict], Optional[str], Optional[str]]:
        # logger.info(f"load_thinking_messages:{received_message.message_id}")

        observation = received_message.content
        if not observation:
            raise ValueError("The received message content is empty!")

        if context is None:
            context = {}
        if self.agent_context and self.agent_context.extra:
            context.update(self.agent_context.extra)

        try:
            resource_prompt_str, resource_references = await self.load_resource(
                observation, is_retry_chat=is_retry_chat
            )
        except Exception as e:
            logger.exception(f"Load resource error！{str(e)}")
            raise ValueError(f"Load resource error！{str(e)}")

        resource_vars = await self.generate_bind_variables(
            received_message,
            sender,
            rely_messages,
            historical_dialogues,
            context=context,
            resource_prompt=resource_prompt_str,
            resource_info=resource_references,
            **kwargs,
        )
        # logger.info(f"参数加载完成！当前可用参数:{orjson.dumps(resource_vars).decode()}")
        system_prompt = await self.build_system_prompt(
            resource_vars=resource_vars,
            context=context,
            is_retry_chat=is_retry_chat,
        )

        # 如果强制传递了历史消息，不要使用默认记忆
        if historical_dialogues and force_use_historical:
            resource_vars["most_recent_memories"] = None

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
        agent_messages.append(
            AgentMessage(
                content=user_prompt,
                context=received_message.context,
                content_types=received_message.content_types,
                role=ModelMessageRoleType.HUMAN,
            )
        )

        return agent_messages, resource_references, system_prompt, user_prompt

    async def task_id_by_received_message(self, received_message: AgentMessage) -> str:
        if not received_message:
            return ""

        if hasattr(self, "agents") and received_message.name in self.agents:
            # 小弟发的消息 说明是answer消息 需要回到父(自己)节点的上下文
            from derisk.agent.core.memory.gpts.gpts_memory import ConversationCache

            cache: ConversationCache = await self.cache()
            return cache.task_manager.get_node(received_message.goal_id).parent_id

        from .reasoning.util import is_summary_agent

        if is_summary_agent(self):
            # 兼容Report子Agent
            return received_message.goal_id

        # 上游发来的消息 message_id是新的task_id，goal_id是上游的task_id
        return received_message.message_id

    async def push_context_event(
        self, event_type: EventType, payload: Payload, task_id: str, **kwargs
    ):
        """推送上下文事件"""
        if not task_id:
            # todo @济空: 异常场景 不应该走进来 待排查
            logger.error(
                f"push_context_event task_id为空: {task_id}, {self.role}({self.name}) {event_type}, {payload}"
            )
            return

        assert event_type in PAYLOAD_TYPE and isinstance(
            payload, PAYLOAD_TYPE[event_type]
        )

        from derisk.context.utils import build_operator_config
        from derisk.context.operator import Operator, OperatorManager

        operator_clss: list[Type[Operator]] = OperatorManager.operator_clss_by_type(
            event_type
        )
        start_ms = current_ms()
        for operator_cls in operator_clss:
            succeed = True
            round_ms = current_ms()
            try:
                operator: Operator = operator_cls()
                operator.config = build_operator_config(
                    operator_cls, self.context_config
                )
                await operator.handle(
                    event=Event(
                        event_type=event_type, task_id=task_id, payload=payload
                    ),
                    agent=self,
                    **kwargs,
                )
            except Exception as e:
                succeed = False
                logger.exception("push_context_event: " + repr(e))
            finally:
                digest(
                    None,
                    "push_context_event.operate",
                    cost_ms=current_ms() - round_ms,
                    succeed=succeed,
                    event_type=event_type,
                    operator_name=operator_cls.name,
                )
        digest(
            logger,
            "push_context_event",
            cost_ms=current_ms() - start_ms,
            event_type=event_type,
            operator_size=len(operator_clss),
        )


def _new_system_message(content):
    """Return the system message."""
    return [{"content": content, "role": ModelMessageRoleType.SYSTEM}]


def _is_list_of_type(lst: List[Any], type_cls: type) -> bool:
    return all(isinstance(item, type_cls) for item in lst)
