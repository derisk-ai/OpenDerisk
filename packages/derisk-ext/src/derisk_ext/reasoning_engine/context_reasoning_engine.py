import json
from json import JSONDecodeError
from typing import Any, Union

from jinja2 import meta

from derisk.agent import AgentMessage, AgentContext, ActionOutput
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER
from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
from derisk.core import ModelMessageRoleType
from derisk.util.template_utils import TMPL_ENV, render
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import ReasoningAgent
from derisk_ext.reasoning_arg_supplier.context import context_ability_arg_supplier
from derisk_ext.reasoning_arg_supplier.default import default_output_schema_arg_supplier
from derisk_ext.reasoning_arg_supplier.default.default_history_arg_supplier import session_id_from_conv_id
from derisk_ext.reasoning_engine.default_reasoning_engine import DefaultReasoningEngine, _DEFAULT_ARG_SUPPLIER_NAMES
from derisk_serve.agent.db import GptsConversationsDao

_NAME = "CONTEXT_REASON_ENGINE"
_DESCRIPTION = "基于上下文工程的推理引擎"

_CONTEXT_ARG_SUPPLIER_NAMES = [
    default_output_schema_arg_supplier.DefaultOutputSchemaArgSupplier().name,
    context_ability_arg_supplier.ContextAbilityArgSupplier().name,
]


class ContextReasoningEngine(DefaultReasoningEngine):
    @property
    def name(self) -> str:
        return _NAME

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def system_prompt_template(self) -> str:
        return '''你是一个{#InputSlot placeholder="智能体人设"#}{#/InputSlot#}，请通帮助解决用户问题。'''

    async def get_all_reasoning_args(self, resource: ReasoningEngineResource, agent: ReasoningAgent, agent_context: AgentContext, received_message: AgentMessage, step_id: str,
                                     **kwargs) -> dict[str, str]:
        prompt_param: dict[str, str] = {}

        # 解析模板中的占位符参数
        system_prompt: str = resource.system_prompt_template
        system_variables = meta.find_undeclared_variables(TMPL_ENV.parse(system_prompt)) if system_prompt else set()

        user_prompt: str = resource.prompt_template
        user_variables = meta.find_undeclared_variables(TMPL_ENV.parse(user_prompt)) if user_prompt else set()

        variables = system_variables.union(user_variables)

        # 参数引擎supplier处理
        supplier_names: list[str] = resource.reasoning_arg_suppliers if resource.reasoning_arg_suppliers else []  # 用户定义的supplier优先
        supplier_names.extend(_DEFAULT_ARG_SUPPLIER_NAMES)  # 系统内置supplier兜底
        for supplier_name in supplier_names:
            supplier = ReasoningArgSupplier.get_supplier(supplier_name)
            if (not supplier) or (supplier.arg_key not in variables) or (supplier.arg_key in prompt_param):
                continue  # 这里如果用户supplier已经提供了ary_key，就会跳过默认的supplier

            try:
                await supplier.supply(prompt_param=prompt_param, agent=agent, agent_context=agent_context, received_message=received_message, step_id=step_id)
            except Exception as e:
                LOGGER.exception(f"ContextReasoningEngine get_all_reasoning_args: {repr(e)}")

        # context也放到param中
        for k, v in agent_context.to_dict().items():
            if k not in prompt_param:
                prompt_param[k] = v

        LOGGER.info(f"[ENGINE][{self.name}]prompt_param: [{json.dumps(prompt_param, ensure_ascii=False)}]")
        return prompt_param

    async def render_messages(self, prompt_param: dict[str, str], resource: ReasoningEngineResource, agent_context: AgentContext, **kwargs) -> list[AgentMessage]:
        agent: ReasoningAgent = kwargs.get("agent")
        received_message = kwargs.get("received_message")
        current_step_message = kwargs.get("current_step_message")
        step_id = kwargs.get("step_id")
        messages: list[AgentMessage] = []

        # 1. system message
        system_message = await self.render_system_message(
            prompt_param=prompt_param,
            resource=resource,
            agent=agent,
            agent_context=agent_context,
            received_message=received_message,
            current_step_message=current_step_message,
            step_id=step_id,
        )
        messages.append(system_message)

        # 2. user message
        user_messages = await self.render_user_message(prompt_param=prompt_param, resource=resource, agent_context=agent_context, **kwargs)
        messages += user_messages

        return messages

    async def format_system_prefix_context(self, resource: ReasoningEngineResource, agent: ReasoningAgent, agent_context: AgentContext, received_message: AgentMessage,
                                           current_step_message: AgentMessage, step_id: str) -> str:
        suppliers: dict[str, ReasoningArgSupplier] = {}
        supplier_names: list[str] = resource.reasoning_arg_suppliers if resource.reasoning_arg_suppliers else []  # 用户定义的supplier优先
        supplier_names.extend(_CONTEXT_ARG_SUPPLIER_NAMES)  # 系统内置supplier兜底
        for supplier_name in supplier_names:
            supplier: ReasoningArgSupplier = ReasoningArgSupplier.get_supplier(supplier_name)
            if supplier.arg_key not in suppliers:
                suppliers[supplier.arg_key] = supplier

        async def _supply(arg_key: str) -> str:
            _supplier = suppliers.get(arg_key)
            param: dict[str, Any] = {}
            await _supplier.supply(
                prompt_param=param,
                agent=agent,
                agent_context=agent_context,
                received_message=received_message,
                current_step_message=current_step_message,
                step_id=step_id,
            )
            return param.get(arg_key)

        return "\n\n".join([f"<{v}>\n{await _supply(s)}\n</{v}>" for v, s in [
            ("可用能力", "ability"),
            ("响应格式", "output_schema"),
        ]])

    async def render_system_message(self, prompt_param: dict[str, str], resource: ReasoningEngineResource, agent: ReasoningAgent, agent_context: AgentContext,
                                    received_message: AgentMessage, current_step_message: AgentMessage, step_id: str) -> AgentMessage:
        # 先处理参数占位符supplier
        system_prompt_template = resource.system_prompt_template
        system_prompt = render(system_prompt_template, prompt_param) if system_prompt_template and prompt_param else ""

        # 再把Context放到system_prompt开头
        system_prompt = await self.format_system_prefix_context(
            resource=resource,
            agent=agent,
            agent_context=agent_context,
            received_message=received_message,
            current_step_message=current_step_message,
            step_id=step_id,
        ) + "\n\n" + system_prompt

        LOGGER.info(f"[ENGINE][{self.name}]system_prompt_template: [{system_prompt_template}]")
        LOGGER.info(f"[ENGINE][{self.name}]system_prompt: [{system_prompt}]")

        return AgentMessage(content=system_prompt, role=ModelMessageRoleType.SYSTEM)

    async def render_user_message(self, prompt_param: dict[str, str], resource: ReasoningEngineResource, agent_context: AgentContext, **kwargs) -> list[AgentMessage]:
        messages: list[AgentMessage] = []
        user_prompt_template = resource.prompt_template
        LOGGER.info(f"[ENGINE][{self.name}]user_prompt_template: [{user_prompt_template}]")
        if user_prompt_template:
            # 如果用户配了user_prompt 则以用户配置为准
            user_prompt = render(user_prompt_template, prompt_param)
            LOGGER.info(f"[ENGINE][{self.name}]user_prompt: [{user_prompt}]")
            messages.append(AgentMessage(content=user_prompt, role=ModelMessageRoleType.HUMAN))
        else:
            # 没有配置user_prompt 则直接取gpts_message
            agent: ReasoningAgent = kwargs.get("agent")
            gpts_messages: list[GptsMessage] = []
            conversations = GptsConversationsDao().get_like_conv_id_asc(session_id_from_conv_id(agent_context.conv_id))
            for idx, conversation in enumerate(conversations):
                conv_messages: list[GptsMessage] = await agent.memory.gpts_memory.get_messages(conv_id=conversation.conv_id)
                gpts_messages += conv_messages

            # todo: 这样的处理跳过了多模态逻辑 待完善
            for gpts_message in gpts_messages:
                if "Human" == gpts_message.sender:
                    messages.append(AgentMessage(content=gpts_message.content, role=ModelMessageRoleType.HUMAN))
                else:
                    if gpts_message.content:
                        messages.append(AgentMessage(content=gpts_message.content, role=ModelMessageRoleType.AI))
                    if gpts_message.action_report:
                        messages += messages_by_action_report(
                            action_report=gpts_message.action_report,
                            # 最终的发给Human的answer，role应该是AI。其他action执行结果，role应该是Human
                            role=ModelMessageRoleType.AI if gpts_message.receiver == "Human" else ModelMessageRoleType.HUMAN)

        return [message for message in messages if message and message.content]


def messages_by_action_report(action_report: Union[str, ActionOutput], role: str) -> list[AgentMessage]:
    if action_report and isinstance(action_report, str):
        action_report = ActionOutput.from_dict(json.loads(action_report))

    if not action_report or not action_report.content:
        return []

    def _format_message_content_by_action_report(_action_report: ActionOutput) -> AgentMessage:
        return AgentMessage(content=action_report.model_view or action_report.content, role=role)

    try:
        sub_action_reports: list[dict] = json.loads(action_report.content)
        messages: list[AgentMessage] = []
        for sub in sub_action_reports:
            sub_messages = messages_by_action_report(ActionOutput.from_dict(sub), role=role)
            messages += sub_messages
        return messages
    except JSONDecodeError:
        return [_format_message_content_by_action_report(action_report)]
    except Exception as e:
        return [_format_message_content_by_action_report(action_report)]
