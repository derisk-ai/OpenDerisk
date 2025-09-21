import json
from typing import List, cast, Optional, Dict, Any, Tuple
from derisk.agent import AgentMessage, AgentContext, Agent
from derisk.agent.core.reasoning import reasoning_parser
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningEngine,
    DEFAULT_REASONING_PLANNER_NAME,
    ReasoningEngineOutput,
)
from derisk.agent.core.reasoning.reasoning_parser import parse_actions
from derisk.agent.resource import ResourcePack
from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
from derisk.core import ModelMessageRoleType
from derisk.util.template_utils import render
from derisk.util.tracer import root_tracer
from ..agent.agents.reasoning.default.reasoning_agent import ReasoningAgent
from ..reasoning_arg_supplier.default import (
    default_history_arg_supplier,
    default_ability_arg_supplier,
    default_knowledge_arg_supplier,
    default_now_arg_supplier,
    default_output_schema_arg_supplier,
    default_query_arg_supplier,
    default_agent_name_arg_supplier,
    index_history_arg_supplier,
    index_output_schema_arg_supplier,
    memory_history_arg_supplier,
)

_NAME = DEFAULT_REASONING_PLANNER_NAME
_DESCRIPTION = """系统默认推理引擎"""
_DEFAULT_ARG_SUPPLIER_NAMES = [
    default_query_arg_supplier.DefaultQueryArgSupplier().name,
    default_ability_arg_supplier.DefaultAbilityArgSupplier().name,
    default_history_arg_supplier.DefaultHistoryArgSupplier().name,
    default_knowledge_arg_supplier.DefaultKnowledgeArgSupplier().name,
    default_output_schema_arg_supplier.DefaultOutputSchemaArgSupplier().name,
    default_now_arg_supplier.DefaultNowArgSupplier().name,
    default_agent_name_arg_supplier.DefaultAgentNameArgSupplier().name,
    index_history_arg_supplier.IndexHistoryArgSupplier().name,
    index_output_schema_arg_supplier.IndexOutputSchemaArgSupplier().name,
    memory_history_arg_supplier.MemoryHistoryArgSupplier().name,
]

_PROMPT_TEMPLATE = """请根据任务描述、可用能力和历史动作，判断任务当前状态并输出可能的下一步计划。注意避免重复操作！

## 任务概述
{{query}}


## 可用能力清单（只能选用下列工具）
{% if ability %}
{{ability}}
{% else %}
无
{% endif %}
**注意：只能使用上述工具！若无需选用工具或无匹配工具或参数不足需终止任务并说明原因**


## 历史记录分析
### 已执行动作追踪（按时间排序）
{% if memory %}
{{memory}}
{% else %}
无已执行动作记录
{% endif %}

## 输出要求
{{output_schema}}"""


class DefaultReasoningEngine(ReasoningEngine):
    def __init__(self):
        self.messages = []
        self.prompt_param = {}

    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def user_prompt_template(self) -> str:
        """Return the user prompt template of the reasoning engine."""
        return _PROMPT_TEMPLATE

    async def load_thinking_messages(
        self,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        **kwargs
    )-> Tuple[List[AgentMessage], Optional[Dict], Optional[str], Optional[str]]:
        """组装模型消息 返回: 模型消息、resource_info、系统提示词、用户提示词"""
        LOGGER.info(
            f"[ENGINE][{self.name}], "
            f"in: received_message_id[{received_message.message_id}]"
        )

        resource: ReasoningEngineResource = self.get_reasoning_resource(agent)
        self.prompt_param: dict[str, str] = await self.get_all_reasoning_args(
            resource=resource,
            agent=agent,
            agent_context=agent_context,
            received_message=received_message,
            **kwargs,
        )

        resource_vars = kwargs.get("resource_vars")
        if resource_vars:
            self.prompt_param.update(resource_vars)

        self.messages: list[AgentMessage] = await self.render_messages(
            prompt_param=self.prompt_param,
            resource=resource,
            agent=agent,
            agent_context=agent_context,
            received_message=received_message,
            **kwargs,
        )

        system_prompt = next(
            (
                message.content
                for message in self.messages
                if message.role == ModelMessageRoleType.SYSTEM
            ),
            None,
        )

        user_prompt = next(
            (
                message.content
                for message in reversed(self.messages)
                if message.role != ModelMessageRoleType.SYSTEM
            ),
            None,
        )

        return self.messages, None, system_prompt, user_prompt

    def parse_output(self, agent: ReasoningAgent, reply_message: AgentMessage, **kwargs) -> ReasoningEngineOutput:
        # 解析模型结果
        engine_output: ReasoningEngineOutput = ReasoningEngineOutput()
        engine_output.done = True
        engine_output.answer = "内部异常，未正常结束"
        try:
            model_output, done, answer, actions = parse_actions(reply_message.content, agent.abilities)
            engine_output.done = done
            engine_output.answer = answer
            engine_output.actions = actions
            engine_output.action_reason = model_output.reason
            engine_output.plans_brief_description = model_output.plans_brief_description
            if self.prompt_param.get("resources"):
                engine_output.references = self.prompt_param.get("resources")
        except Exception as e:
            engine_output.done = True
            engine_output.answer = f"模型调用失败或结果解析失败\n{repr(e)}"
            LOGGER.exception(f"[ENGINE][{self.name}]模型调用或结果解析失败")

        return engine_output

    async def get_all_reasoning_args(
        self,
        resource: ReasoningEngineResource,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        **kwargs,
    ) -> dict[str, str]:
        prompt_param: dict[str, str] = {}

        supplier_names: list[str] = resource.reasoning_arg_suppliers if resource.reasoning_arg_suppliers else []  # 用户定义的supplier优先
        supplier_names.extend(_DEFAULT_ARG_SUPPLIER_NAMES)  # 系统内置supplier兜底
        _visited_args = set()
        for supplier_name in supplier_names:
            supplier = ReasoningArgSupplier.get_supplier(supplier_name)
            if (not supplier) or (supplier.arg_key in _visited_args):
                continue  # 这里如果用户supplier已经提供了ary_key，就会跳过默认的supplier
            await supplier.supply(
                prompt_param=prompt_param,
                agent=agent,
                agent_context=agent_context,
                received_message=received_message,
            )
            _visited_args.add(supplier.arg_key)

        # context也放到param中
        for k, v in agent_context.to_dict().items():
            if k not in prompt_param:
                prompt_param[k] = v

        LOGGER.info(
            f"[ENGINE][{self.name}]prompt_param: [{json.dumps(prompt_param, ensure_ascii=False)}]"
        )
        return prompt_param

    async def render_messages(
            self,
            prompt_param: dict[str, str],
            resource: ReasoningEngineResource,
            agent_context: AgentContext,
            **kwargs,
    ) -> list[AgentMessage]:
        messages: List[AgentMessage] = []

        # 1. system prompt render
        system_prompt_template = None
        system_prompt = None
        if resource and resource.system_prompt_template:
            system_prompt_template = resource.system_prompt_template
            system_prompt = render(system_prompt_template, prompt_param)
            messages.append(
                AgentMessage(content=system_prompt, role=ModelMessageRoleType.SYSTEM)
            )

        LOGGER.info(
            f"[ENGINE][{self.name}]system_prompt_template: [{system_prompt_template}]"
        )
        LOGGER.info(f"[ENGINE][{self.name}]system_prompt: [{system_prompt}]")

        # 2. user prompt render
        user_prompt_template = resource.prompt_template or self.user_prompt_template
        user_prompt = render(user_prompt_template, prompt_param)
        messages.append(
            AgentMessage(
                content=user_prompt,
                role=ModelMessageRoleType.HUMAN,
            )
        )
        LOGGER.info(
            f"[ENGINE][{self.name}]user_prompt_template: [{user_prompt_template}]"
        )
        LOGGER.info(f"[ENGINE][{self.name}]user_prompt: [{user_prompt}]")

        return messages

    async def invoke(
        self,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        current_step_message: AgentMessage,
        step_id: str,
        **kwargs,
    ) -> ReasoningEngineOutput | None:
        LOGGER.info(
            f"[ENGINE][{self.name}], "
            f"in: received_message_id[{received_message.message_id}], current_step_message_id:[{current_step_message.message_id}]"
        )

        resource: ReasoningEngineResource = self.get_reasoning_resource(agent)
        prompt_param: dict[str, str] = await self.get_all_reasoning_args(
            resource=resource,
            agent=agent,
            agent_context=agent_context,
            received_message=received_message,
            current_step_message=current_step_message,
            step_id=step_id,
            **kwargs,
        )
        messages: list[AgentMessage] = await self.render_messages(
            prompt_param=prompt_param,
            resource=resource,
            agent=agent,
            agent_context=agent_context,
            received_message=received_message,
            current_step_message=current_step_message,
            step_id=step_id,
            **kwargs,
        )

        engine_output = ReasoningEngineOutput()
        engine_output.done = True
        engine_output.answer = "内部异常，未正常结束"
        with root_tracer.start_span(
            "reasoning.llm",
            metadata={},
        ) as span:
            user_messages = [
                message
                for message in messages
                if message.role != ModelMessageRoleType.SYSTEM
            ]
            engine_output.user_prompt = (
                user_messages[-1].content
                if user_messages
                else ""
            )
            engine_output.system_prompt = next(
                (
                    message.content
                    for message in messages
                    if message.role == ModelMessageRoleType.SYSTEM
                ),
                None,
            )
            engine_output.messages = messages
            res_thinking, res_content, model_name = None, None, None
            try:
                # llm invoke
                out = await agent.thinking_inner(
                    messages, reply_message_id=current_step_message.message_id, received_message=current_step_message
                )
                res_thinking = out.thinking_content
                res_content = out.content
                model_name = out.llm_name
                LOGGER.info(f"[ENGINE][{self.name}]res_thinking: [{res_thinking}]")
                LOGGER.info(f"[ENGINE][{self.name}]res_content: [{res_content}]")
                LOGGER.info(f"[ENGINE][{self.name}]model_name: [{model_name}]")

                engine_output.model_thinking = res_thinking
                engine_output.model_content = res_content
                engine_output.model_name = model_name
                engine_output.model_metrics = out.metrics
                span.metadata["res_thinking"] = res_thinking
                span.metadata["res_content"] = res_content
                span.metadata["model_name"] = model_name
                if not res_content:
                    raise RuntimeError("llm response is empty")

                # parse result
                model_output, done, answer, actions = reasoning_parser.parse_actions(
                    text=res_content, abilities=agent.abilities
                )
                engine_output.done = done
                engine_output.answer = answer
                engine_output.actions = actions
                engine_output.action_reason = model_output.reason
                engine_output.plans_brief_description = (
                    model_output.plans_brief_description
                )
                if prompt_param.get("resources"):
                    engine_output.references = prompt_param.get("resources")
                return engine_output
            except Exception as e:
                engine_output.done = True
                engine_output.answer = f"模型调用失败或结果解析失败\n{repr(e)}"
                LOGGER.exception(f"[ENGINE][{self.name}]模型调用或结果解析失败")
                raise
            finally:
                LOGGER.info(
                    f"[ENGINE][{self.name}], "
                    f"out: model_name:[{model_name}], "
                    f"done:[{engine_output.done}], "
                    f"actions size:[{len(engine_output.actions) if engine_output.actions else 0}], "
                    f"answer:[{engine_output.answer}]"
                )

    def get_reasoning_resource(self, agent: ReasoningAgent) -> Optional[ReasoningEngineResource]:
        engine_resource = None

        # 如果 agent 的资源本身就是 ReasoningEngineResource 类型
        if isinstance(agent.resource, ReasoningEngineResource):
            engine_resource = agent.resource

        # 如果 agent 的资源是 ResourcePack 类型且有子资源
        elif (agent.resource
              and isinstance(agent.resource, ResourcePack)
              and hasattr(agent.resource, 'sub_resources')):

            # 在子资源中查找第一个 ReasoningEngineResource 类型的资源
            for resource in agent.resource.sub_resources:
                if isinstance(resource, ReasoningEngineResource):
                    engine_resource = resource

        engine_resource = engine_resource or ReasoningEngineResource(DEFAULT_REASONING_PLANNER_NAME)

        # 处理下推理引擎的兼容，如果agent绑定了外部的prompt， 优先使用
        if agent.profile.system_prompt_template:
            engine_resource.system_prompt_template = agent.profile.system_prompt_template
        if agent.profile.user_prompt_template:
            engine_resource.prompt_template = agent.profile.user_prompt_template
        return engine_resource
