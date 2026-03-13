import asyncio
import logging
import warnings
from typing import Any, Dict, List, Optional
from derisk._private.pydantic import Field, PrivateAttr
from derisk.agent import (
    ActionOutput,
    Agent,
    AgentMessage,
    ProfileConfig,
    Resource,
    ResourceType,
)
from derisk.agent.core.base_agent import ContextHelper
from derisk.agent.core.role import AgentRunMode
from derisk.agent.expand.actions.agent_action import AgentStart
from derisk.agent.expand.actions.knowledge_action import KnowledgeSearch
from derisk.agent.expand.actions.tool_action import ToolAction
from derisk.agent.expand.tool_agent.function_call_parser import FunctionCallOutputParser
from derisk.agent.resource import FunctionTool, RetrieverResource, BaseTool, ToolPack
from derisk.agent.resource.agent_skills import AgentSkillResource

from derisk.agent.resource.app import AppResource
from derisk.context.event import ActionPayload, EventType
from derisk.sandbox.base import SandboxBase
from derisk.util.template_utils import render
from derisk_serve.agent.resource.tool.mcp import MCPToolPack
from .prompt_v3 import (
    REACT_SYSTEM_TEMPLATE,
    REACT_USER_TEMPLATE,
    REACT_WRITE_MEMORY_TEMPLATE,
)
from ..actions.terminate_action import Terminate
from ...core.base_team import ManagerAgent
from ...core.schema import DynamicParam, DynamicParamType

logger = logging.getLogger(__name__)

_REACT_DEFAULT_GOAL = """通用SRE问题解决专家."""

_DEPRECATION_MESSAGE = """
ReActAgent is deprecated and will be removed in a future version.
Please use ReActMasterAgent instead:

    from derisk.agent.expand.react_master_agent import ReActMasterAgent
    
    agent = ReActMasterAgent(
        enable_doom_loop_detection=True,
        enable_session_compaction=True,
        enable_history_pruning=True,
        enable_output_truncation=True,
    )

For PDCA-style task planning:
    agent = ReActMasterAgent(enable_kanban=True)
"""


class ReActAgent(ManagerAgent):
    max_retry_count: int = 300
    run_mode: AgentRunMode = AgentRunMode.LOOP

    profile: ProfileConfig = ProfileConfig(
        name="derisk",
        role=" ReActMaster",
        goal=_REACT_DEFAULT_GOAL,
        system_prompt_template=REACT_SYSTEM_TEMPLATE,
        user_prompt_template=REACT_USER_TEMPLATE,
        write_memory_template=REACT_WRITE_MEMORY_TEMPLATE,
    )
    agent_parser: FunctionCallOutputParser = Field(
        default_factory=FunctionCallOutputParser
    )
    function_calling: bool = True

    _ctx: ContextHelper[dict] = PrivateAttr(default_factory=lambda: ContextHelper(dict))

    available_system_tools: Dict[str, FunctionTool] = Field(
        default_factory=dict, description="available system tools"
    )
    enable_function_call: bool = True
    dynamic_variables: List[DynamicParam] = []

    def __init__(self, **kwargs):
        """Init indicator AssistantAgent."""
        warnings.warn(_DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
        super().__init__(**kwargs)
        ## 注意顺序，如果AgentStart，KnowledgeSearch， Terminate 需要在ToolAction之前 TODO待方案优化
        self._init_actions(
            [
                AgentStart,
                KnowledgeSearch,
                Terminate,
                ToolAction,
            ]
        )

    async def preload_resource(self) -> None:
        await super().preload_resource()
        await self.system_tool_injection()

    async def load_resource(self, question: str, is_retry_chat: bool = False):
        """Load agent bind resource."""
        self.function_calling_context = await self.function_calling_params()
        return None, None

    async def function_calling_params(self):
        def _tool_to_function(tool) -> Dict:
            # 新框架 ToolBase: 使用 to_openai_tool() 方法
            if hasattr(tool, "to_openai_tool"):
                return tool.to_openai_tool()

            # 旧框架 BaseTool: 使用 args 属性
            properties = {}
            required_list = []
            for key, value in tool.args.items():
                properties[key] = {
                    "type": value.type,
                    "description": value.description,
                }
                if value.required:
                    required_list.append(key)
            parameters_dict = {
                "type": "object",
                "properties": properties,
                "required": required_list,
            }

            function = {}
            function["name"] = tool.name
            function["description"] = tool.description
            function["parameters"] = parameters_dict
            return {"type": "function", "function": function}

        functions = []
        for k, v in self.available_system_tools.items():
            functions.append(_tool_to_function(v))

        tool_packs = ToolPack.from_resource(self.resource)
        if tool_packs:
            tool_pack = tool_packs[0]
            for tool in tool_pack.sub_resources:
                tool_item: BaseTool = tool
                functions.append(_tool_to_function(tool_item))

        if functions:
            return {
                "tool_choice": "auto",
                "tools": functions,
                "parallel_tool_calls": True,
            }
        else:
            return None

    def prepare_act_param(
        self,
        received_message: Optional[AgentMessage],
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Prepare the parameters for the act method."""
        return {
            "parser": self.agent_parser,
        }

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
        if not message:
            raise ValueError("The message content is empty!")

        act_outs: List[ActionOutput] = []

        # 第一阶段：解析所有可能的action
        real_actions = self.agent_parser.parse_actions(
            llm_out=kwargs.get("agent_llm_out"), action_cls_list=self.actions, **kwargs
        )

        # 第二阶段：并行执行所有解析出的action
        if real_actions:
            explicit_keys = [
                "ai_message",
                "resource",
                "rely_action_out",
                "render_protocol",
                "message_id",
                "sender",
                "agent",
                "received_message",
                "agent_context",
                "memory",
            ]

            # 创建一个新的kwargs，它不包含explicit_keys中出现的键
            filtered_kwargs = {
                k: v for k, v in kwargs.items() if k not in explicit_keys
            }

            # 创建所有action的执行任务
            tasks = []
            for real_action in real_actions:
                task = real_action.run(
                    ai_message=message.content if message.content else "",
                    resource=self.resource,
                    resource_map=self.resource_map,
                    render_protocol=await self.memory.gpts_memory.async_vis_converter(
                        self.not_null_agent_context.conv_id
                    ),
                    message_id=message.message_id,
                    current_message=message,
                    sender=sender,
                    agent=self,
                    received_message=received_message,
                    agent_context=self.agent_context,
                    memory=self.memory,
                    **filtered_kwargs,
                )
                tasks.append((real_action, task))

            # 并行执行所有任务
            results = await asyncio.gather(
                *[task for _, task in tasks], return_exceptions=True
            )

            # 处理执行结果
            for (real_action, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    # 处理执行异常
                    logger.exception(f"Action execution failed: {result}")
                    # 可以选择创建一个表示失败的ActionOutput，或者跳过
                    act_outs.append(
                        ActionOutput(
                            content=str(result),
                            name=real_action.name,
                            is_exe_success=False,
                        )
                    )
                else:
                    if result:
                        act_outs.append(result)
                await self.push_context_event(
                    EventType.AfterAction,
                    ActionPayload(action_output=result),
                    await self.task_id_by_received_message(received_message),
                )

        return act_outs

    def register_variables(self):
        """子类通过重写此方法注册变量"""
        logger.info(f"register_variables {self.role}")
        super().register_variables()

        @self._vm.register("available_agents", "可用Agents资源")
        async def var_available_agents(instance):
            logger.info("注入agent资源")
            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], AppResource):
                    for item in v:
                        app_item: AppResource = item  # type:ignore
                        prompts += f"- <agent><code>{app_item.app_code}</code><name>{app_item.app_name}</name><description>{app_item.app_desc}</description>\n</agent>\n"
            return prompts

        @self._vm.register("available_knowledges", "可用知识库")
        async def var_available_knowledges(instance):
            logger.info("注入knowledges资源")

            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], RetrieverResource):
                    for item in v:
                        if hasattr(item, "knowledge_spaces") and item.knowledge_spaces:
                            for i, knowledge_space in enumerate(item.knowledge_spaces):
                                prompts += f"- <knowledge><id>{knowledge_space.knowledge_id}</id><name>{knowledge_space.name}</name><description>{knowledge_space.desc}</description></knowledge>\n"

                        else:
                            logger.error(f"当前知识资源无法使用!{k}")
            return prompts

        @self._vm.register("available_skills", "可用技能")
        async def var_skills(instance):
            logger.info("注入技能资源")

            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], AgentSkillResource):
                    for item in v:
                        skill_item: AgentSkillResource = item  # type:ignore
                        mode, branch = "release", "master"
                        debug_info = getattr(skill_item, "debug_info", None)
                        if debug_info and debug_info.get("is_debug"):
                            mode, branch = "debug", debug_info.get("branch")
                        prompts += (
                            f"- <skill>"
                            f"<name>{skill_item.skill_meta(mode).name}</name>"
                            f"<description>{skill_item.skill_meta(mode).description}</description>"
                            f"<path>{skill_item.skill_meta(mode).path}</path>"
                            f"<branch>{branch}</branch>"
                            f"\n</skill>\n"
                        )
            return prompts

        @self._vm.register("system_tools", "系统工具")
        async def var_system_tools(instance):
            result = ""
            if self.available_system_tools:
                logger.info("注入系统工具")
                tool_prompts = ""
                for k, v in self.available_system_tools.items():
                    t_prompt, _ = await v.get_prompt(
                        lang=instance.agent_context.language
                    )
                    tool_prompts += f"- <tool>{t_prompt}</tool>\n"
                return tool_prompts

            return None

        @self._vm.register("custom_tools", "自定义工具")
        async def var_custom_tools(instance):
            logger.info("注入自定义工具")
            tool_prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], BaseTool):
                    for item in v:
                        t_prompt, _ = await item.get_prompt(
                            lang=instance.agent_context.language
                        )
                        tool_prompts += f"- <tool>{t_prompt}</tool>\n"
                ## 临时兼容MCP 因为异步加载
                elif isinstance(v[0], MCPToolPack):
                    for mcp in v:
                        if mcp and mcp.sub_resources:
                            for item in mcp.sub_resources:
                                t_prompt, _ = await item.get_prompt(
                                    lang=instance.agent_context.language
                                )
                                tool_prompts += f"- <tool>{t_prompt}</tool>\n"
            return tool_prompts

        @self._vm.register("sandbox", "沙箱配置")
        async def var_sandbox(instance):
            logger.info("注入沙箱配置信息，如果存在沙箱客户端即默认使用沙箱")
            if instance and instance.sandbox_manager:
                if instance.sandbox_manager.initialized == False:
                    logger.warning(
                        f"沙箱尚未准备完成!({instance.sandbox_manager.client.provider}-{instance.sandbox_manager.client.sandbox_id})"
                    )
                sandbox_client: SandboxBase = instance.sandbox_manager.client

                from derisk.agent.core.sandbox.prompt import sandbox_prompt
                from derisk.agent.core.sandbox.sandbox_tool_registry import (
                    sandbox_tool_dict,
                )
                from derisk.agent.core.sandbox.tools.browser_tool import BROWSER_TOOLS

                sandbox_tool_prompts = []
                browser_tool_prompts = []
                for k, v in sandbox_tool_dict.items():
                    prompt, _ = await v.get_prompt(lang=instance.agent_context.language)
                    if k in BROWSER_TOOLS:
                        browser_tool_prompts.append(f"- <tool>{prompt}</tool>")
                    else:
                        sandbox_tool_prompts.append(f"- <tool>{prompt}</tool>")

                param = {
                    "sandbox": {
                        "work_dir": sandbox_client.work_dir,
                        "use_agent_skill": sandbox_client.enable_skill,
                        "agent_skill_dir": sandbox_client.skill_dir,
                    }
                }

                return {
                    "tools": "\n".join([item for item in sandbox_tool_prompts]),
                    "browser_tools": "\n".join([item for item in browser_tool_prompts]),
                    "enable": True if sandbox_client else False,
                    "prompt": render(sandbox_prompt, param),
                }
            else:
                return {"enable": False, "prompt": ""}

        @self._vm.register("memory", "记忆上下文")
        async def var_memory(instance, received_message=None, agent_context=None):
            """获取Layer 4压缩的历史对话记录或fallback到传统memory

            优先尝试使用Layer 4跨轮次历史压缩，如果不可用则降级到传统memory搜索
            """
            # 首先尝试Layer 4
            try:
                if hasattr(instance, "_ensure_compaction_pipeline"):
                    pipeline = await instance._ensure_compaction_pipeline()
                    if pipeline:
                        history = await pipeline.get_layer4_history_for_prompt()
                        if history:
                            logger.info(
                                f"Layer 4: Retrieved compressed history ({len(history)} chars)"
                            )
                            return history
            except Exception as e:
                logger.debug(
                    f"Layer 4 not available, falling back to traditional memory: {e}"
                )

            # 降级到传统memory搜索
            import json
            from datetime import datetime, timedelta
            from derisk.agent.resource.memory import MemoryParameters
            from derisk.storage.vector_store.filters import (
                MetadataFilter,
                MetadataFilters,
                FilterOperator,
            )

            if not instance.memory:
                return ""

            preference_memory_read: bool = False
            if (
                agent_context
                and agent_context.extra
                and "preference_memory_read" in agent_context.extra
            ):
                preference_memory_read = agent_context.extra.get(
                    "preference_memory_read"
                )

            MODEL_CONTEXT_LENGTH = {
                "deepseek-v3": 64000,
                "deepSeek-r1": 64000,
                "QwQ-32B": 64000,
            }

            def get_agent_llm_context_length() -> int:
                default_length = 32000
                if not hasattr(instance, "llm_config") or not instance.llm_config:
                    return default_length
                model_list = instance.llm_config.strategy_context
                if not model_list:
                    return default_length
                if isinstance(model_list, str):
                    try:
                        model_list = json.loads(model_list)
                    except Exception:
                        return default_length
                return MODEL_CONTEXT_LENGTH.get(model_list[0], default_length)

            def session_id_from_conv_id(conv_id: str) -> str:
                idx = conv_id.rfind("_")
                return conv_id[:idx] if idx else conv_id

            def get_time_24h_ago() -> str:
                now = datetime.now()
                twenty_four_hours_ago = now - timedelta(hours=24)
                return twenty_four_hours_ago.strftime("%Y-%m-%d %H:%M:%S")

            llm_token_limit = get_agent_llm_context_length() - 8000
            memory_params = (
                instance.get_memory_parameters()
                if hasattr(instance, "get_memory_parameters")
                else None
            )
            if not memory_params:
                return ""

            if preference_memory_read:
                date = get_time_24h_ago()
                metadata_filter = MetadataFilter(
                    key="create_time", operator=FilterOperator.GT, value=date
                )
                metadata_filters = MetadataFilters(filters=[metadata_filter])
                memory_fragments = await instance.memory.preference_memory.search(
                    observation=received_message.current_goal
                    if received_message
                    else "",
                    session_id=session_id_from_conv_id(agent_context.conv_id)
                    if agent_context
                    else "",
                    enable_global_session=memory_params.enable_global_session,
                    retrieve_strategy="exact",
                    discard_strategy="fifo",
                    condense_prompt=memory_params.message_condense_prompt,
                    condense_model=memory_params.message_condense_model,
                    score_threshold=memory_params.score_threshold,
                    top_k=memory_params.top_k,
                    llm_token_limit=llm_token_limit,
                    user_id=agent_context.user_id if agent_context else None,
                    metadata_filters=metadata_filters,
                )
            else:
                memory_fragments = await instance.memory.search(
                    observation=received_message.current_goal
                    if received_message
                    else "",
                    session_id=session_id_from_conv_id(agent_context.conv_id)
                    if agent_context
                    else "",
                    agent_id=agent_context.agent_app_code if agent_context else None,
                    enable_global_session=memory_params.enable_global_session,
                    retrieve_strategy=memory_params.retrieve_strategy,
                    discard_strategy=memory_params.discard_strategy,
                    condense_prompt=memory_params.message_condense_prompt,
                    condense_model=memory_params.message_condense_model,
                    score_threshold=memory_params.score_threshold,
                    top_k=memory_params.top_k,
                    llm_token_limit=llm_token_limit,
                )

            recent_messages = [
                f"\nRound:{m.rounds if m.rounds else m.metadata.get('rounds')}\n"
                f"Role:{m.role if m.role else m.metadata.get('role')}\n"
                f"{m.raw_observation}"
                for m in memory_fragments
            ]
            return "\n".join(recent_messages)

        logger.info(f"register_variables end {self.role}")
