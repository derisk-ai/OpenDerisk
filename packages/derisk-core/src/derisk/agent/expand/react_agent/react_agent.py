import asyncio
import logging
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
from derisk.agent.expand.react_agent.react_parser import ReActOutputParser
from derisk.agent.resource import FunctionTool, RetrieverResource, BaseTool
from derisk.agent.resource.agent_skills import AgentSkillResource

from derisk.agent.resource.app import AppResource
from derisk.context.event import ActionPayload, EventType
from derisk.sandbox.base import SandboxBase
from derisk.util.template_utils import render
from derisk_ext.reasoning_arg_supplier.default.memory_history_arg_supplier import MemoryHistoryArgSupplier
from derisk_serve.agent.resource.tool.mcp import MCPToolPack
from .prompt_v3 import REACT_SYSTEM_TEMPLATE, REACT_USER_TEMPLATE, REACT_WRITE_MEMORY_TEMPLATE
from ..actions.terminate_action import Terminate
from ...core.base_team import ManagerAgent
from ...core.schema import DynamicParam, DynamicParamType

logger = logging.getLogger(__name__)

_REACT_DEFAULT_GOAL = """通用SRE问题解决专家."""


class ReActAgent(ManagerAgent):
    max_retry_count: int = 25
    run_mode: AgentRunMode = AgentRunMode.LOOP

    profile: ProfileConfig = ProfileConfig(
        name="derisk",
        role="ReActMaster",
        goal=_REACT_DEFAULT_GOAL,
        system_prompt_template=REACT_SYSTEM_TEMPLATE,
        user_prompt_template=REACT_USER_TEMPLATE,
        write_memory_template=REACT_WRITE_MEMORY_TEMPLATE,
    )
    agent_parser: ReActOutputParser = Field(default_factory=ReActOutputParser)
    function_calling: bool = True

    _ctx: ContextHelper[dict] = PrivateAttr(default_factory=lambda: ContextHelper(dict))

    available_system_tools: Dict[str, FunctionTool] = Field(default_factory=dict, description="available system tools")
    # FunctionCall函数和action的绑定
    enable_function_call: bool = False
    dynamic_variables: List[DynamicParam] = [
        DynamicParam(key=MemoryHistoryArgSupplier().arg_key, name=MemoryHistoryArgSupplier().name,
                     type=DynamicParamType.CUSTOM.value),
    ]


    def __init__(self, **kwargs):
        """Init indicator AssistantAgent."""
        super().__init__(**kwargs)
        ## 注意顺序，如果AgentStart，KnowledgeSearch， Terminate 需要在ToolAction之前 TODO待方案优化
        self._init_actions([AgentStart, KnowledgeSearch, Terminate, ToolAction, ])

    async def preload_resource(self) -> None:
        await super().preload_resource()
        # await self.sandbox_tool_injection()
        await self.system_tool_injection()

    async def load_resource(self, question: str, is_retry_chat: bool = False):
        """Load agent bind resource."""
        if self.resource:

            def _remove_tool(r: Resource):
                if r.type() == ResourceType.Tool:
                    return None
                return r

            if self.function_calling:
                # Remove all tools from the resource
                # We will handle tools separately
                new_resource = self.resource.apply(apply_func=_remove_tool)
            else:
                new_resource = self.resource
            if new_resource:
                resource_prompt, resource_reference = await new_resource.get_prompt(
                    lang=self.language, question=question
                )
                return resource_prompt, resource_reference
        return None, None

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
            explicit_keys = ['ai_message', 'resource', 'rely_action_out', 'render_protocol', 'message_id', 'sender',
                             'agent', 'received_message', 'agent_context', "memory"]

            # 创建一个新的kwargs，它不包含explicit_keys中出现的键
            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in explicit_keys}

            # 创建所有action的执行任务
            tasks = []
            for real_action in real_actions:
                task = real_action.run(
                    ai_message=message.content if message.content else "",
                    resource=self.resource,
                    resource_map=self.resource_map,
                    render_protocol=await self.memory.gpts_memory.async_vis_converter(
                        self.not_null_agent_context.conv_id),
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
            results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

            # 处理执行结果
            for (real_action, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    # 处理执行异常
                    logger.exception(f"Action execution failed: {result}")
                    # 可以选择创建一个表示失败的ActionOutput，或者跳过
                    act_outs.append(ActionOutput(content=str(result), name=real_action.name, is_exe_success=False))
                else:
                    if result:
                        act_outs.append(result)
                await self.push_context_event(
                    EventType.AfterAction,
                    ActionPayload(action_output=result),
                    await self.task_id_by_received_message(received_message)
                )

        return act_outs

    def register_variables(self):
        """子类通过重写此方法注册变量"""
        logger.info(f"register_variables {self.role}")
        super().register_variables()

        @self._vm.register('available_agents', '可用Agents资源')
        async def var_available_agents(instance):
            logger.info("注入agent资源")
            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], AppResource):
                    for item in v:
                        app_item: AppResource = item  # type:ignore
                        prompts += (
                            f"- <agent><code>{app_item.app_code}</code><name>{app_item.app_name}</name><description>{app_item.app_desc}</description>\n</agent>\n")
            return prompts

        @self._vm.register('available_knowledges', '可用知识库')
        async def var_available_knowledges(instance):
            logger.info("注入knowledges资源")

            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], RetrieverResource):
                    for item in v:
                        if hasattr(item, "knowledge_spaces") and item.knowledge_spaces:
                            for i, knowledge_space in enumerate(item.knowledge_spaces):
                                prompts += (
                                    f"- <knowledge><id>{knowledge_space.knowledge_id}</id><name>{knowledge_space.name}</name><description>{knowledge_space.desc}</description></knowledge>\n")

                        else:
                            logger.error(f"当前知识资源无法使用!{k}")
            return prompts

        @self._vm.register('available_skills', '可用技能')
        async def var_skills(instance):
            logger.info("注入技能资源")

            prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], AgentSkillResource):
                    for item in v:
                        skill_item: AgentSkillResource = item  # type:ignore
                        mode, branch = "release", "master"
                        debug_info = getattr(skill_item, 'debug_info', None)
                        if debug_info and debug_info.get('is_debug'):
                            mode, branch = "debug", debug_info.get('branch')
                        prompts += (
                            f"- <skill>"
                            f"<name>{skill_item.skill_meta(mode).name}</name>"
                            f"<description>{skill_item.skill_meta(mode).description}</description>"
                            f"<path>{skill_item.skill_meta(mode).path}</path>"
                            f"<branch>{branch}</branch>"
                            f"\n</skill>\n")
            return prompts

        @self._vm.register('system_tools', '系统工具')
        async def var_system_tools(instance):
            result = ""
            if self.available_system_tools:
                logger.info("注入系统工具")
                tool_prompts = ""
                for k, v in self.available_system_tools.items():
                    t_prompt, _ = await v.get_prompt(lang=instance.agent_context.language)
                    tool_prompts += f"- <tool>{t_prompt}</tool>\n"
                return tool_prompts

            return None

        @self._vm.register('custom_tools', '自定义工具')
        async def var_custom_tools(instance):

            logger.info("注入自定义工具")
            tool_prompts = ""
            for k, v in self.resource_map.items():
                if isinstance(v[0], BaseTool):
                    for item in v:
                        t_prompt, _ = await item.get_prompt(lang=instance.agent_context.language)
                        tool_prompts += f"- <tool>{t_prompt}</tool>\n"
                ## 临时兼容MCP 因为异步加载
                elif isinstance(v[0], MCPToolPack):
                    for mcp in v:
                        if mcp and mcp.sub_resources:
                            for item in mcp.sub_resources:
                                t_prompt, _ = await item.get_prompt(lang=instance.agent_context.language)
                                tool_prompts += f"- <tool>{t_prompt}</tool>\n"
            return tool_prompts

        @self._vm.register('sandbox', '沙箱配置')
        async def var_sandbox(instance):
            logger.info("注入沙箱配置信息，如果存在沙箱客户端即默认使用沙箱")
            if instance and instance.sandbox_manager:
                if instance.sandbox_manager.initialized == False:
                    logger.warning(
                        f"沙箱尚未准备完成!({instance.sandbox_manager.client.provider}-{instance.sandbox_manager.client.sandbox_id})")
                sandbox_client: SandboxBase = instance.sandbox_manager.client

                from derisk.agent.core.sandbox.prompt import sandbox_prompt
                from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool_dict
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
                    "prompt": render(sandbox_prompt, param)
                }
            else:
                return {
                    "enable": False,
                    "prompt": ""
                }

        logger.info(f"register_variables end {self.role}")
