import json
from datetime import timedelta, datetime
from json import JSONDecodeError
from typing import Union, List, cast

from jinja2 import meta

from derisk.agent import AgentMessage, AgentContext, ActionOutput, MemoryFragment, AgentMemoryFragment
from derisk.agent.core.reasoning.reasoning_arg_supplier import ReasoningArgSupplier
from derisk.agent.core.reasoning.reasoning_engine import REASONING_LOGGER as LOGGER
from derisk.agent.resource.memory import MemoryParameters
from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
from derisk.context.manager import Manager, StepContextKey
from derisk.context.utils import format_ability_by_context
from derisk.core import ModelMessageRoleType
from derisk.storage.vector_store.filters import MetadataFilter, FilterOperator, MetadataFilters
from derisk.util.template_utils import TMPL_ENV, render
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import ReasoningAgent
from derisk_ext.reasoning_arg_supplier.default import default_output_schema_arg_supplier
from derisk_ext.reasoning_arg_supplier.default.default_history_arg_supplier import session_id_from_conv_id
from derisk_ext.reasoning_arg_supplier.default.memory_history_arg_supplier import get_agent_llm_context_length
from derisk_ext.reasoning_engine.default_reasoning_engine import DefaultReasoningEngine, _DEFAULT_ARG_SUPPLIER_NAMES

_NAME = "CONTEXT_REASON_ENGINE"
_DESCRIPTION = "基于上下文工程的推理引擎"


#
# _CONTEXT_ARG_SUPPLIER_NAMES = [
#     default_output_schema_arg_supplier.DefaultOutputSchemaArgSupplier().name,
#     context_ability_arg_supplier.ContextAbilityArgSupplier().name,
# ]


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

    async def get_all_reasoning_args(
        self,
        resource: ReasoningEngineResource,
        agent: ReasoningAgent,
        agent_context: AgentContext,
        received_message: AgentMessage,
        **kwargs,
    ) -> dict[str, str]:
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
                await supplier.supply(prompt_param=prompt_param, agent=agent, agent_context=agent_context, received_message=received_message, **kwargs)
            except Exception as e:
                LOGGER.exception(f"ContextReasoningEngine get_all_reasoning_args: {repr(e)}")

        # context也放到param中
        for k, v in agent_context.to_dict().items():
            if k not in prompt_param:
                prompt_param[k] = v

        LOGGER.info(f"[ENGINE][{self.name}]prompt_param: [{json.dumps(prompt_param, ensure_ascii=False)}]")
        return prompt_param

    async def render_messages(self, prompt_param: dict[str, str], resource: ReasoningEngineResource, agent_context: AgentContext, **kwargs) -> list[AgentMessage]:
        messages: list[AgentMessage] = []

        # 1. system message
        system_message = await self.render_system_message(
            prompt_param=prompt_param,
            resource=resource,
            agent_context=agent_context,
            **kwargs,
        )
        messages.append(system_message)

        # 2. user message
        user_messages = await self.render_user_message(agent_context=agent_context, **kwargs)
        messages += user_messages

        return messages

    async def format_system_prefix_context(self) -> str:
        ability: str = format_ability_by_context()
        output_schema: str = default_output_schema_arg_supplier.DefaultOutputSchemaArgSupplier().detail
        return "\n\n".join([
            f"<可用能力>\n{ability}",
            f"<响应格式>\n{output_schema}"
        ])
        # suppliers: dict[str, ReasoningArgSupplier] = {}
        # supplier_names: list[str] = resource.reasoning_arg_suppliers if resource.reasoning_arg_suppliers else []  # 用户定义的supplier优先
        # supplier_names.extend(_CONTEXT_ARG_SUPPLIER_NAMES)  # 系统内置supplier兜底
        # for supplier_name in supplier_names:
        #     supplier: ReasoningArgSupplier = ReasoningArgSupplier.get_supplier(supplier_name)
        #     if supplier.arg_key not in suppliers:
        #         suppliers[supplier.arg_key] = supplier
        #
        # async def _supply(arg_key: str) -> str:
        #     _supplier = suppliers.get(arg_key)
        #     param: dict[str, Any] = {}
        #     await _supplier.supply(
        #         prompt_param=param,
        #         agent=agent,
        #         agent_context=agent_context,
        #         received_message=received_message,
        #     )
        #     return param.get(arg_key)
        #
        # return "\n\n".join([f"<{v}>\n{await _supply(s)}\n</{v}>" for v, s in [
        #     ("可用能力", "ability"),
        #     ("响应格式", "output_schema"),
        # ]])

    async def render_system_message(self, prompt_param: dict[str, str], resource: ReasoningEngineResource, agent: ReasoningAgent, agent_context: AgentContext,
                                    received_message: AgentMessage, **kwargs) -> AgentMessage:
        # system_prompt在对话中应该不变 直接复用
        system_prompt: str = agent.system_prompt

        if not system_prompt:
            # 先处理参数占位符supplier
            system_prompt_template = resource.system_prompt_template
            LOGGER.info(f"[ENGINE][{self.name}]system_prompt_template: [{system_prompt_template}]")

            system_prompt = render(system_prompt_template, prompt_param) if system_prompt_template and prompt_param else ""

            # 再把Context放到system_prompt开头
            system_prompt = await self.format_system_prefix_context() + "\n\n" + system_prompt
            agent.system_prompt = system_prompt

        LOGGER.info(f"[ENGINE][{self.name}]system_prompt: [{system_prompt}]")

        return AgentMessage(content=system_prompt, role=ModelMessageRoleType.SYSTEM)

    async def render_user_message(self, agent_context: AgentContext, **kwargs) -> list[AgentMessage]:
        context: dict = Manager.current_window()
        agent: ReasoningAgent = kwargs.get("agent")
        memory = agent.memory
        preference_memory_read = True if agent.agent_context.extra and agent.agent_context.extra.get("preference_memory_read", False) else False
        memory_params: MemoryParameters = agent.get_memory_parameters()
        llm_token_limit = get_agent_llm_context_length(agent) - 8000
        received_message = kwargs.get("received_message")

        remind_message: AgentMessage = AgentMessage(content=context[StepContextKey.REMINDER], role=ModelMessageRoleType.HUMAN) \
            if context.get(StepContextKey.REMINDER, "") else None

        messages: list[AgentMessage] = []
        if preference_memory_read:
            # 读取preference中的user_memory
            date = get_time_24h_ago()
            metadata_filter = MetadataFilter(key="create_time", operator=FilterOperator.GT, value=date)
            metadata_filters = MetadataFilters(filters=[metadata_filter])
            LOGGER.info("coversation %s User Memory "
                        "search: %s, create_time >= %s", agent_context.conv_id, agent_context.user_id, date)
            memory_fragments: List[MemoryFragment] = await memory.preference_memory.search(
                observation=received_message.current_goal,
                session_id=session_id_from_conv_id(agent_context.conv_id),
                # agent_id=agent_id,
                enable_global_session=memory_params.enable_global_session,
                # retrieve_strategy=memory_params.retrieve_strategy,
                retrieve_strategy="exact",
                discard_strategy=memory_params.discard_strategy,
                condense_prompt=memory_params.message_condense_prompt,
                condense_model=memory_params.message_condense_model,
                score_threshold=memory_params.score_threshold,
                top_k=memory_params.top_k,
                llm_token_limit=llm_token_limit,
                user_id=agent_context.user_id,  # TODO 使用viewer
                metadata_filters=metadata_filters,
            )
        else:
            memory_fragments: List[MemoryFragment] = await memory.search(
                observation=received_message.current_goal,
                session_id=session_id_from_conv_id(agent_context.conv_id),
                agent_id=agent.agent_context.agent_app_code,
                enable_global_session=memory_params.enable_global_session,
                retrieve_strategy=memory_params.retrieve_strategy,
                discard_strategy=memory_params.discard_strategy,
                condense_prompt=memory_params.message_condense_prompt,
                condense_model=memory_params.message_condense_model,
                score_threshold=memory_params.score_threshold,
                top_k=memory_params.top_k,
                llm_token_limit=llm_token_limit,
            )

        if not memory_fragments:
            # 没写过任何Memory 说明是初始状态
            messages = [AgentMessage(content=received_message.content, role=ModelMessageRoleType.HUMAN)]
            if remind_message:
                messages.append(remind_message)
            return messages

        user_query: set[str] = set()
        ai_messages: set[str] = set()
        action_messages: set[str] = set()
        for fragment in memory_fragments:
            fragment = cast(AgentMemoryFragment, fragment)
            if fragment.user_input and fragment.user_input not in user_query:
                user_query.add(fragment.user_input)
                messages.append(AgentMessage(content=fragment.user_input, role=ModelMessageRoleType.HUMAN))

            if fragment.ai_message and fragment.ai_message not in ai_messages:
                ai_messages.add(fragment.ai_message)
                messages.append(AgentMessage(content=fragment.ai_message, role=ModelMessageRoleType.AI))

            if fragment.raw_observation and fragment.raw_observation not in action_messages:
                action_messages.add(fragment.raw_observation)
                messages.append(AgentMessage(content=f"Role:{fragment.role}\n{fragment.raw_observation}", role=ModelMessageRoleType.HUMAN))

        if remind_message:
            messages.append(remind_message)
        return messages

        # agent: ReasoningAgent = kwargs.get("agent")
        # gpts_messages: list[GptsMessage] = []
        # conversations = GptsConversationsDao().get_like_conv_id_asc(session_id_from_conv_id(agent_context.conv_id))
        # for idx, conversation in enumerate(conversations):
        #     conv_messages: list[GptsMessage] = await agent.memory.gpts_memory.get_messages(conv_id=conversation.conv_id)
        #     gpts_messages += conv_messages
        #
        # # todo: 这样的处理跳过了多模态逻辑 待完善
        # for gpts_message in gpts_messages:
        #     if "Human" == gpts_message.sender:
        #         messages.append(AgentMessage(content=gpts_message.content, role=ModelMessageRoleType.HUMAN))
        #     else:
        #         if gpts_message.content:
        #             messages.append(AgentMessage(content=gpts_message.content, role=ModelMessageRoleType.AI))
        #         if gpts_message.action_report:
        #             messages += messages_by_action_report(
        #                 action_report=gpts_message.action_report,
        #                 # 最终的发给Human的answer，role应该是AI。其他action执行结果，role应该是Human
        #                 role=ModelMessageRoleType.AI if gpts_message.receiver == "Human" else ModelMessageRoleType.HUMAN)
        #
        # return [message for message in messages if message and message.content]


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


def get_time_24h_ago() -> str:
    """
    返回当前时间往前推 24 小时后的时间字符串，格式为:
    "YYYY-MM-DD HH:MM:SS"
    """
    # 1. 取得当前本地时间（如果想要 UTC 可改为 datetime.utcnow()）
    now = datetime.now()
    # 2. 往前推 24 小时
    twenty_four_hours_ago = now - timedelta(hours=24)
    # 3. 按指定格式输出
    formatted = twenty_four_hours_ago.strftime("%Y-%m-%d %H:%M:%S")
    return formatted
