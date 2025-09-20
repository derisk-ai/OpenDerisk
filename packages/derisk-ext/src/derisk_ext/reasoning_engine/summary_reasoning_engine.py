import json

from derisk.agent import AgentMessage, AgentContext
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningEngineOutput,
)
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
    index_output_schema_arg_supplier,
    memory_history_arg_supplier,
)

SUMMARY_REPORT_ENGINE_NAME = "SUMMARY"
_NAME = SUMMARY_REPORT_ENGINE_NAME
_DESCRIPTION = """总结报告推理引擎"""
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
    index_output_schema_arg_supplier.IndexOutputSchemaArgSupplier().name,
    memory_history_arg_supplier.MemoryHistoryArgSupplier.name,
]

_PROMPT_TEMPLATE = """
根据知识库搜索结果或者搜索工具返回的结果进行结合做撰写一份全面、结构良好的且详细的总结。
**注意事项**

## 任务概述
{{query}}

## 历史记录分析

### 已执行动作追踪（按时间排序）
{% if memory %}
{{memory}}
{% else %}
无已执行动作记录
{% endif %}

## 输出要求
1.请用中文回答
2. 总结回答时请务必保留原文中的图片、引用、视频等链接内容
3. 原文中的图片、引用、视频等链接格式, 出现在原文内容中，内容后，段落中都可以认为属于原文内容，请确保在总结答案中依然输出这些内容，不要丢弃，不要修改.(参考图片链接格式：![image.png](xxx) 、普通链接格式:[xxx](xxx))
优先从给出的资源中总结用户问题答案，如果没有找到相关信息，则尝试从当前会话的历史对话记忆中找相关信息，忽略无关的信息.
5. 回答时最好按照论文格式做撰写一份全面、每一部分内容需要结构良好的且中文字数尽可能详细，尽可能涵盖上下文里面所有你认为有用的知识点，如果提供的资源信息带有图片![image.png](xxx) ，链接[xxx](xxx))或者表格,总结的时候也将图片，链接，表格按照markdown格式进行输出。
6. 注意需要并在每段总结的**中文**末尾结束标点符号前面注明内容来源的链接编号,语雀链接,语雀标题[i](https://yuque_url.com "title"),i 为引用的序号，eg:1,2,3, title是标题变量。
"""


class SummaryReasoningEngine(DefaultReasoningEngine):
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

    def parse_output(self, agent: ReasoningAgent, reply_message: AgentMessage, **kwargs) -> ReasoningEngineOutput:
        # 解析模型结果
        engine_output: ReasoningEngineOutput = ReasoningEngineOutput()
        engine_output.done = True
        engine_output.answer = reply_message.content
        engine_output.actions = []
        engine_output.action_reason = reply_message.thinking
        engine_output.plans_brief_description = ""
        if self.prompt_param.get("resources"):
            engine_output.references = self.prompt_param.get("resources")

        return engine_output

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
                engine_output.model_metrics = out.metrics
                engine_output.model_name = model_name
                span.metadata["res_thinking"] = res_thinking
                span.metadata["res_content"] = res_content
                span.metadata["model_name"] = model_name
                if not res_content:
                    raise RuntimeError("llm response is empty")

                # parse result
                # model_output, done, answer, actions = reasoning_parser.parse_actions(
                #     text=res_content, abilities=agent.abilities
                # )
                engine_output.done = True
                engine_output.answer = res_content
                engine_output.actions = []
                engine_output.action_reason = res_thinking
                engine_output.plans_brief_description = ""
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
