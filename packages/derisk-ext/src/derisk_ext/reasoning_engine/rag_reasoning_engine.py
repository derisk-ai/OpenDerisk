import json
from typing import cast


from derisk.agent import AgentMessage, AgentContext
from derisk.agent.core.reasoning import reasoning_parser
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningEngineOutput,
)
from derisk.agent.resource import ResourcePack
from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
from derisk.core import ModelMessageRoleType
from derisk.util.tracer import root_tracer
from .default_reasoning_engine import DefaultReasoningEngine
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
    index_output_schema_arg_supplier, memory_history_arg_supplier,
)

_NAME = "RAG_REASON_ENGINE"
_DESCRIPTION = """通用搜索推理引擎"""
_DEFAULT_ARG_SUPPLIER_NAMES = [
    default_query_arg_supplier.DefaultQueryArgSupplier().name,
    default_ability_arg_supplier.DefaultAbilityArgSupplier().name,
    default_history_arg_supplier.DefaultHistoryArgSupplier().name,
    memory_history_arg_supplier.MemoryHistoryArgSupplier().name,
    default_knowledge_arg_supplier.DefaultKnowledgeArgSupplier().name,
    default_output_schema_arg_supplier.DefaultOutputSchemaArgSupplier().name,
    default_now_arg_supplier.DefaultNowArgSupplier().name,
    default_agent_name_arg_supplier.DefaultAgentNameArgSupplier().name,
    index_history_arg_supplier.IndexHistoryArgSupplier().name,
    index_output_schema_arg_supplier.IndexOutputSchemaArgSupplier().name,
    memory_history_arg_supplier.MemoryHistoryArgSupplier.name,
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


class RAGReasoningEngine(DefaultReasoningEngine):
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
                user_messages[0].content
                if len(user_messages) == 1
                else json.dumps([message.to_llm_message() for message in user_messages])
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
                if get_current_reason_step(step_id) > 0:
                    engine_output.done = True
                    engine_output.answer = "done"
                    engine_output.actions = []
                    engine_output.action_reason = ""
                    engine_output.plans_brief_description = ""
                    engine_output.references = prompt_param.get("resources")
                    return engine_output

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
                engine_output.model_metrics= out.metrics
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


def get_current_reason_step(step_id: str):
    """Extracts the current reason step from the step_id."""
    last_dash_index = step_id.rfind('-')

    if last_dash_index != -1:
        last_part = step_id[last_dash_index + 1:]

        try:
            return int(last_part)
        except ValueError:
            return last_part
    else:
        return step_id

