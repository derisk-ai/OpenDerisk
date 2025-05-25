import json
from typing import List, cast

from jinja2 import Template

from derisk.agent import AgentMessage, AgentContext
from derisk.agent.core.reasoning import reasoning_parser
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningEngine,
    DEFAULT_REASONING_PLANNER_NAME,
    ReasoningEngineOutput,
)
from derisk.agent.resource import ResourcePack
from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
from derisk.core import ModelMessageRoleType
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
{% if history_analysis %}
### 前置分析结论（来自其他智能体）
{{history_analysis}}
{% endif %}

### 已执行动作追踪（按时间排序）
{% if history %}
{{history}}
{% else %}
无已执行动作记录
{% endif %}

{% if knowledge %}
## 参考知识库
{{knowledge}}
{% endif %}

## 输出要求
{{output_schema}}"""


class DefaultReasoningEngine(ReasoningEngine):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    async def get_all_reasoning_args(
        self,
        resource: ReasoningEngineResource,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        step_id: str,
        **kwargs,
    ) -> dict[str, str]:
        prompt_param: dict[str, str] = {}

        supplier_names: list[str] = (resource.reasoning_arg_suppliers if resource.reasoning_arg_suppliers else [])  # 用户定义的supplier优先
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
                step_id=step_id,
            )
            _visited_args.add(supplier.arg_key)

        # context也放到param中
        for k, v in agent_context.to_dict().items():
            if k not in prompt_param:
                prompt_param[k] = v

        LOGGER.info(f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]prompt_param: [{json.dumps(prompt_param, ensure_ascii=False)}]")
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
            system_prompt = Template(system_prompt_template).render(prompt_param)
            messages.append(AgentMessage(content=system_prompt, role=ModelMessageRoleType.SYSTEM))

        LOGGER.info(f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]system_prompt_template: [{system_prompt_template}]")
        LOGGER.info(f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]system_prompt: [{system_prompt}]")

        # 2. user prompt render
        user_prompt_template = resource.prompt_template or _PROMPT_TEMPLATE
        user_prompt = Template(user_prompt_template).render(prompt_param)
        messages.append(AgentMessage(
            content=user_prompt,
            role=ModelMessageRoleType.HUMAN,
        ))
        LOGGER.info(f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]user_prompt_template: [{user_prompt_template}]")
        LOGGER.info(f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]user_prompt: [{user_prompt}]")

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
            f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}], "
            f"in: received_message_id[{received_message.message_id}], current_step_message_id:[{current_step_message.message_id}]"
        )

        resource: ReasoningEngineResource = get_reasoning_resource(agent)
        prompt_param: dict[str, str] = await self.get_all_reasoning_args(
            resource=resource, agent=agent, agent_context=agent_context, received_message=received_message,
            current_step_message=current_step_message, step_id=step_id, **kwargs
        )
        messages: list[AgentMessage] = await self.render_messages(
            prompt_param=prompt_param, resource=resource, agent=agent, agent_context=agent_context,
            received_message=received_message, current_step_message=current_step_message, step_id=step_id, **kwargs
        )

        engine_output = ReasoningEngineOutput()
        engine_output.done = True
        engine_output.answer = "内部异常，未正常结束"
        with root_tracer.start_span(
            "reasoning.llm",
            metadata={},
        ) as span:
            user_messages = [message for message in messages if message.role != ModelMessageRoleType.SYSTEM]
            engine_output.user_prompt = user_messages[0].content if len(user_messages) == 1 else json.dumps([message.to_llm_message() for message in user_messages])
            engine_output.system_prompt = next((message.content for message in messages if message.role == ModelMessageRoleType.SYSTEM), None)
            engine_output.messages = messages
            res_thinking, res_content, model_name = None, None, None
            try:
                # llm invoke
                res_thinking, res_content, model_name = await agent.thinking(
                    messages, reply_message_id=current_step_message.message_id
                )
                LOGGER.info(
                    f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]res_thinking: [{res_thinking}]"
                )
                LOGGER.info(
                    f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]res_content: [{res_content}]"
                )
                LOGGER.info(
                    f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]model_name: [{model_name}]"
                )

                engine_output.model_thinking = res_thinking
                engine_output.model_content = res_content
                engine_output.model_name = model_name
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
                return engine_output
            except Exception as e:
                engine_output.done = True
                engine_output.answer = f"模型调用失败或结果解析失败\n{repr(e)}"
                LOGGER.exception(
                    f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}]模型调用或结果解析失败"
                )
                raise
            finally:
                LOGGER.info(
                    f"[{agent_context.trace_id}][{agent_context.conv_id}][ENGINE][{self.name}], "
                    f"out: model_name:[{model_name}], "
                    f"done:[{engine_output.done}], "
                    f"actions size:[{len(engine_output.actions) if engine_output.actions else 0}], "
                    f"answer:[{engine_output.answer}]"
                )


def get_reasoning_resource(agent: ReasoningAgent) -> ReasoningEngineResource:
    return (
        next((
            cast(ReasoningEngineResource, resource)
            for resource in agent.resource.sub_resources
            if isinstance(resource, ReasoningEngineResource)
        ), None, )
        if agent
           and isinstance(agent, ReasoningAgent)
           and agent.resource
           and isinstance(agent.resource, ResourcePack)
        else agent.resource if isinstance(agent.resource, ReasoningEngineResource)
        else None
    ) if agent and isinstance(agent, ReasoningAgent) else None
