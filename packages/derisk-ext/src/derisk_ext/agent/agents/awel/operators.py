import datetime
import json
import logging
import uuid
from copy import copy
from enum import Enum
from typing import Optional, List, Any

from pydantic import BaseModel

from derisk.agent import Action, ConversableAgent, ActionOutput, AgentMemory
from derisk.agent.core.agent import AgentGenerateContext, AgentMessage, AgentContext
from derisk.agent.core.memory.gpts import GptsPlan
from derisk.agent.core.reasoning.reasoning_engine import ReasoningPlan
from derisk.agent.core.reasoning.reasoning_parser import format_action
from derisk.agent.core.schema import Status
from derisk.component import ComponentType
from derisk.core import LLMClient, ModelRequest, ModelMessage, ModelOutput
from derisk.core.awel import MapOperator, DefaultTaskContext, BranchOperator, DAGContext, TaskOutput
from derisk.core.awel.flow import (
    IOField, OperatorCategory, Parameter, ViewMetadata, ui, TAGS_ORDER_HIGH, OperatorType, register_resource, ResourceCategory,
)
from derisk.core.awel.util.parameter_util import OptionValue, FunctionDynamicOptions
from derisk.model import DefaultLLMClient
from derisk.model.cluster import WorkerManagerFactory
from derisk.model.operators import MixinLLMOperator
from derisk.util.code.server import get_code_server
from derisk.util.data_util import first
from derisk.util.i18n_utils import _
from derisk.util.json_utils import find_json_objects
from derisk.util.template_utils import render
from derisk_ext.agent.agents.awel.awel_runner_agent import AwelRunnerAgent
from derisk_ext.agent.agents.reasoning.default.ability import valid_ability_types, Ability
from derisk_ext.agent.agents.reasoning.default.reasoning_agent import ReasoningAgent
from derisk_ext.agent.agents.reasoning.utils import identify_action_info
from derisk_serve.agent.agents.controller import multi_agents, CFG
from derisk_serve.prompt.models.models import ServeDao as PromptDao

_prompt_dao = PromptDao(serve_config=None)

__LLM_CLIENT: Optional[LLMClient] = None

logger: logging.Logger = logging.getLogger("awel")


def _llm_client() -> LLMClient:
    global __LLM_CLIENT

    if __LLM_CLIENT is None:
        __LLM_CLIENT = DefaultLLMClient(
            worker_manager=CFG.SYSTEM_APP.get_component(ComponentType.WORKER_MANAGER_FACTORY,
                                                        WorkerManagerFactory).create())
    return __LLM_CLIENT


class ActionContextStrategy(str, Enum):
    """填参策略"""

    UPSTREAM = "upstream"  # 直接使用上游结果
    CONTEXT = "context"  # 直接使用上下文dict
    NEAREST = "nearest"  # 使用最近的上游
    CONTEXT_TO_LLM = "context_to_llm"  # 使用LLM, 基于上下文填参
    UPSTREAM_TO_LLM = "upstream_to_llm"  # 使用LLM, 基于上一步的输出
    NEAREST_TO_LLM = "nearest_to_llm"  # 使用LLM, 基于最近的上游输出
    UPSTREAM_TO_AGENT = "upstream_to_agent"  # 上游message直接传递给下游Agent节点 (限制: 必须是AgentAction)


class ActionOperator(MapOperator[AgentGenerateContext, AgentGenerateContext]):
    """The Action operator for AWEL."""

    metadata = ViewMetadata(
        label="AWEL Action Operator",
        name="action_operator",
        category=OperatorCategory.REASONING,
        description="The Action operator.",
        parameters=[
            # Parameter.build_from(
            #     "Agent",
            #     "awel_agent",
            #     AWELAgent,
            #     description="The derisk agent.",
            # ),
            Parameter.build_from(
                "Agent App Code",
                "app_code",
                str,
                description="The derisk agent app code.",
            ),
            Parameter.build_from(
                "Intention",
                "intention",
                type=str,
                optional=True,
                default=None,
                description="Intention of the action.",
                ui=ui.UIInput(),
            ),
            Parameter.build_from(
                "Ability Type",
                "ability_type",
                type=str,
                description="Type of the ability.",
                options=[OptionValue(label=_type.__name__, name=_type.__name__, value=_type.__name__) for _type in
                         valid_ability_types()],
                ui=ui.UISelect(),
            ),
            Parameter.build_from(
                "Ability ID",
                "ability_id",
                type=str,
                description="ID of the ability.",
                ui=ui.UIInput(),
            ),
            Parameter.build_from(
                "填参策略",
                "param_fill_strategy",
                type=str,
                optional=True,
                default=ActionContextStrategy.CONTEXT_TO_LLM,
                description="使用那种填参策略.",
                options=[OptionValue(label=s, name=s, value=s) for s in ActionContextStrategy],
                ui=ui.UISelect(),
            ),
        ],
        inputs=[
            IOField.build_from(
                "Action Operator Request",
                "action_operator_request",
                AgentGenerateContext,
                "The Action Operator request.",
            )
        ],
        outputs=[
            IOField.build_from(
                "Action Operator Output",
                "action_operator_output",
                AgentGenerateContext,
                description="The Action Operator output.",
            )
        ],
    )

    def __init__(self, intention: str, app_code: str, ability_type: str, ability_id: str, param_fill_strategy: str,
                 **kwargs):
        # def __init__(self, intention: str, awel_agent: AWELAgent, ability_type: str, ability_id: str, param_fill_strategy: str, **kwargs):
        #     super().__init__(awel_agent=awel_agent, **kwargs)
        super().__init__(**kwargs)
        self.intention: str = intention
        # self.awel_agent: AWELAgent = awel_agent
        self.app_code = app_code
        self.ability_type: str = ability_type
        self.ability_id: str = ability_id
        self.param_fill_strategy = param_fill_strategy

    async def map(self, input_value: AgentGenerateContext) -> AgentGenerateContext:
        if not input_value.sender or not isinstance(input_value.sender, ConversableAgent):
            raise NotImplementedError("sender不是合法的ConversableAgent")

        context: AgentContext = input_value.agent_context
        memory: AgentMemory = input_value.memory
        action: Action = await self._get_action_with_input(input_value)
        # if not action:
        #     raise NotImplementedError("无法解析为Action")

        awel_agent: AwelRunnerAgent = input_value.receiver
        ability_agent: ConversableAgent = await multi_agents.build_agent_by_app_code(
            app_code=self.app_code,
            context=context,
            agent_memory=memory
        )

        reply_message: AgentMessage = await awel_agent.init_reply_message(
            received_message=AgentMessage(content="", context=context.to_dict()),
            sender=input_value.sender,
            rounds=await memory.gpts_memory.next_message_rounds(context.conv_id)
        )

        action.init_resource(ability_agent.resource)
        # action.init_resource(receiver.resource or ResourceManager.get_instance(CFG.SYSTEM_APP).build_resource(self.awel_agent.resources)) if action.resource_need else None
        action.init_action(
            render_protocol=input_value.memory.gpts_memory.vis_converter(input_value.agent_context.conv_id))

        # ================================↓↓↓ 总结规划记忆写入 ↓↓↓================================ #
        ### 目前只记录第一层的规划内容，内部子Agent的规划先不记录
        ### 当前Reasoning
        # ================================↓↓↓ 规划轮次计算 ↓↓↓================================ #
        plans: List[GptsPlan] = await awel_agent.memory.gpts_memory.get_plans(
            awel_agent.not_null_agent_context.conv_id)
        plan_num = 1
        if plans and len(plans) > 0:
            plan_num = plans[-1].conv_round
        # ================================↑↑↑ 规划轮次计算 ↑↑↑================================ #
        task_uid = uuid.uuid4().hex
        action_input, agent, agent_type = identify_action_info(action)
        step_plan: GptsPlan = GptsPlan(
            conv_id=awel_agent.agent_context.conv_id,
            conv_session_id=awel_agent.agent_context.conv_session_id,
            conv_round=plan_num + 1,
            conv_round_id=uuid.uuid4().hex,
            sub_task_id=task_uid,
            sub_task_num=0,
            task_uid=task_uid,
            sub_task_content=action.reason,
            sub_task_title=action.intention,
            sub_task_agent=agent,
            state=Status.RUNNING.value,
            action=agent_type,

            task_round_title=f"SOP节点[{self.intention}]",
            task_round_description=f"{self.dag.description}" or "",
            planning_agent=awel_agent.name,
            planning_model=None,
        )
        await awel_agent.memory.gpts_memory.append_plans(
            conv_id=awel_agent.agent_context.conv_id, plans=[step_plan])
        reply_message.goal_id = task_uid
        reply_message.current_goal = step_plan.sub_task_title
        # ================================↑↑↑ 总结规划记忆写入 ↑↑↑================================ #

        st = datetime.datetime.now().timestamp()
        try:
            action_output: ActionOutput = await action.run(
                agent=awel_agent,
                message_id=reply_message.message_id,
                resource=None,
                message=reply_message,
                action_id="", )
        except Exception as e:
            action_output: ActionOutput = self._format_failed_action_report(action=action, e=e)
        action_output.action_intention = self.intention
        action_output.cost_ms = int((datetime.datetime.now().timestamp() - st) * 1000)

        reply_message.action_report = action_output
        result: AgentGenerateContext = copy(input_value)
        result.message = reply_message
        result.sender = awel_agent
        result.round_index = reply_message.rounds

        # 关键信息展示
        await awel_agent.send(reply_message, recipient=awel_agent, request_reply=False)
        # ================================↓↓↓ 步骤规划记忆更新 ↓↓↓================================ #
        if step_plan:
            if reply_message.action_report.is_exe_success:
                step_plan.state = Status.COMPLETE.value
            else:
                step_plan.state = Status.FAILED.value
                step_plan.result = reply_message.action_report.content
            await awel_agent.memory.gpts_memory.update_plan(
                conv_id=awel_agent.agent_context.conv_id, plan=step_plan,
                incremental=awel_agent.agent_context.incremental)
        # ================================↑↑↑ 步骤规划记忆更新 ↑↑↑================================ #

        return result

    async def _get_action_with_input(self, context: AgentGenerateContext) -> Action:
        ability: Ability = await self._get_ability_in_app(context)
        plan = await self._format_action_plan(context, ability)
        return format_action(plan=plan, ability=ability)

    async def _get_ability_in_app(self, context: AgentGenerateContext) -> Ability:
        app_code: str = self.app_code
        # todo: 性能优化
        agent: ReasoningAgent = await multi_agents.build_agent_by_app_code(app_code=app_code,
                                                                           context=context.agent_context,
                                                                           agent_memory=context.memory)
        return next((ability for ability in agent.abilities if
                     ability.actual_type.__name__ == self.ability_type and ability.name == self.ability_id), None)

    async def _format_action_plan(self, context: AgentGenerateContext, ability: Ability) -> ReasoningPlan:
        #     if self.ability_type == FunctionTool.__name__:
        #         return await self._format_tool_action_plan(context, ability)
        #     # raise NotImplementedError("不支持的action类型")
        #     return await self._format_tool_action_plan(context, ability)
        #
        # async def _format_tool_action_plan(self, context: AgentGenerateContext, ability: Ability) -> ReasoningPlan:
        async def _format_param_by_upstream() -> dict:
            assert len(self.upstream) == 1, "当前节点存在多个上游 无法解析参数"
            return json.loads(context.message.content)

        async def _format_param_by_context() -> dict:
            return await self.current_dag_context.get_all_share_data()

        async def _format_param_by_llm_and_context() -> dict:
            def _format_prompt(out: DefaultTaskContext[AgentGenerateContext]) -> str:
                message: AgentMessage = out.task_output.output.message \
                    if out.task_output and out.task_output.output and hasattr(out.task_output.output, "message") \
                    else None
                action_report: ActionOutput = message.action_report if message else None

                action_output: str = action_report.content if action_report else ""
                action_input: str = action_report.action_input if action_report else ""
                action_intention: str = first(
                    action_report.action_intention if action_report else "",
                    message.current_goal if message else ""
                )
                return "\n".join([item for item in [
                    f"intention: {action_intention}" if action_intention else None,
                    f"input: {action_input}" if action_input else None,
                    f"output: {action_output}" if action_output else None,
                ] if item])

            outs = []
            _dup = set()
            for node_id in self.current_dag_context._finished_node_ids:
                out = self.current_dag_context._task_outputs[node_id]
                if not out:
                    continue
                prompt = _format_prompt(out)
                if not prompt:
                    continue
                if prompt in _dup:
                    continue
                _dup.add(prompt)
                outs.append(prompt)

            history: str = "" if not outs else ("<item>\n" + "\n</item>\n\n<item>\n".join(outs) + "\n</item>")
            return await _format_param_by_llm({
                "tool_schema": await ability.get_prompt(),
                "context": history,
                "intention": self.intention,
            })

        async def _format_param_by_llm_and_upstream() -> dict:
            assert len(self.upstream) == 1, "当前节点存在多个上游 无法解析参数"
            return await _format_param_by_llm({
                "tool_schema": await ability.get_prompt(),
                "context": context.message.content,
                "intention": self.intention,
            })

        async def _format_param_by_llm(params: dict[str, Any]) -> dict:
            template = _prompt_dao.get_one({"prompt_code": "awel_param_fill"})
            prompt: str = render(template.content, params)
            out: ModelOutput = await _llm_client().generate(
                request=ModelRequest(
                    model=template.model,
                    messages=[ModelMessage(role="human", content=prompt)],
                    trace_id=context.agent_context.trace_id,
                    rpc_id=context.agent_context.rpc_id,
                )
            )
            if not out or not out.content:
                return {}
            content: str = (out.content[-1] if isinstance(out.content, list) else out.content).object.data
            return find_json_objects(content)[-1]

        if self.param_fill_strategy == ActionContextStrategy.UPSTREAM_TO_AGENT:
            return ReasoningPlan(
                reason=self.intention,
                intention=context.message.content,
                id=self.ability_id,
                parameters={}
            )

        _param_formatter: dict = {
            ActionContextStrategy.UPSTREAM: _format_param_by_upstream,
            ActionContextStrategy.CONTEXT: _format_param_by_context,
            ActionContextStrategy.CONTEXT_TO_LLM: _format_param_by_llm_and_context,
            ActionContextStrategy.UPSTREAM_TO_LLM: _format_param_by_llm_and_upstream,
        }
        return ReasoningPlan(
            reason="",
            intention=self.intention,
            id=self.ability_id,
            parameters=await _param_formatter[self.param_fill_strategy]()
        )

    def _format_failed_action_report(self, action: Action, e: Exception) -> ActionOutput:
        return ActionOutput(
            is_exe_success=False,
            content=repr(e),
            view=repr(e),
            # action=None,
            action_name=action.name if action else None,
            action_input=json.dumps(action.action_input, ensure_ascii=False) if action and action.action_input else None,
        )


# _PARAM_FILL_TEMPLATE = """
# 你是一个智能助手，请基于以下信息生成工具调用的参数。
#
# ## 约束(必须遵从!)
# * 从下面的信息中提取相关信息，可以根据“任务意图”进行必要的推理或加工，但不得编造不存在的信息。
# * 生成的工具调用参数需要符合“任务意图”的逻辑要求。
# * 必须以JSON格式输出，样例: '{"k":"v"}'
#
# ## 工具描述
# {{tool_schema}}
#
# {% if intention %}
# ## 任务意图
# {{intention}}
# {% endif %}
#
# ## 参考上下文(按照时间正序排列)
# {{context}}
# """

_FN_PYTHON_MAP = """
from copy import deepcopy


def fn_map(args: dict) -> dict:
    result: dict = deepcopy(args)
    result["share_data"]["k"] = "v"
    return result

"""


class MessageCodeMapOperator(MapOperator[AgentGenerateContext, AgentGenerateContext]):
    metadata = ViewMetadata(
        label=_("Message Code Map Operator"),
        name="message_code_map_operator",
        description=_(
            "Handle input message with code and return output message after "
            "execution."
        ),
        category=OperatorCategory.CODE,
        parameters=[
            Parameter.build_from(
                "Intention",
                "intention",
                type=str,
                optional=True,
                default=None,
                description="Intention of the operator.",
                ui=ui.UIInput(),
            ),
            Parameter.build_from(
                _("Code Editor"),
                "code",
                type=str,
                optional=True,
                default=_FN_PYTHON_MAP,
                placeholder=_("Please input your code"),
                description=_("The code to be executed."),
                ui=ui.UICodeEditor(
                    language="python",
                ),
            ),
            Parameter.build_from(
                _("Language"),
                "lang",
                type=str,
                optional=True,
                default="python",
                placeholder=_("Please select the language"),
                description=_("The language of the code."),
                options=[
                    OptionValue(label="Python", name="python", value="python"),
                    OptionValue(
                        label="JavaScript", name="javascript", value="javascript"
                    ),
                ],
                ui=ui.UISelect(),
            ),
            Parameter.build_from(
                _("Call Name"),
                "call_name",
                type=str,
                optional=True,
                default="fn_map",
                placeholder=_("Please input the call name"),
                description=_("The call name of the function."),
            ),
        ],
        inputs=[
            IOField.build_from(
                _("Input Data"),
                "input",
                type=AgentGenerateContext,
                description=_("The input dictionary."),
            )
        ],
        outputs=[
            IOField.build_from(
                _("Output Data"),
                "output",
                type=AgentGenerateContext,
                description=_("The output dictionary."),
            )
        ],
        tags={"order": TAGS_ORDER_HIGH},
    )

    def __init__(
            self,
            code: str = _FN_PYTHON_MAP,
            lang: str = "python",
            call_name: str = "fn_map",
            intention: str = None,
            **kwargs,
    ):
        super().__init__(**kwargs)
        self.code = code
        self.lang = lang
        self.call_name = call_name
        self.intention = intention

    async def map(self, input_value: AgentGenerateContext) -> AgentGenerateContext:
        serializable_share_data: dict[str, Any] = {}
        for k, v in (await self.current_dag_context.get_all_share_data()).items():
            try:
                json.dumps(v)
                serializable_share_data[k] = v
            except TypeError:
                continue

        exec_input_data = json.dumps({
            "message": input_value.message.to_dict(),
            "share_data": serializable_share_data,
        }, ensure_ascii=False)
        exec_input_data_bytes = exec_input_data.encode("utf-8")
        logger.info(f"MessageCodeMapOperator, node:{self.node_id}, intention: {self.intention}, input: {exec_input_data}")
        code_server = await get_code_server()
        result = await code_server.exec1(self.code, exec_input_data_bytes, call_name=self.call_name, lang=self.lang)
        logger.info(f"MessageCodeMapOperator node:{self.node_id}, result: {result}")

        output_value: AgentGenerateContext = copy(input_value)
        if result and result.output and "message" in result.output:
            # 踢掉以下字段
            result.output["message"].pop("message_id", None)
            output_value.message = await input_value.receiver.init_reply_message(input_value.message)
            output_value.message.__dict__.update(result.output["message"])

            # 强制刷新
            output_value.message.rounds = await input_value.memory.gpts_memory.next_message_rounds(input_value.agent_context.conv_id)
            output_value.message.show_message = False
        if result and result.output and "share_data" in result.output:
            for k, v in result.output["share_data"].items():
                await self.current_dag_context.save_to_share_data(key=k, data=v, overwrite=True)

        return output_value


_BRANCH_PROMPT_TEMPLATE = """
你是一个智能助手，请根据上下文参考信息给出分支判断。

## 分支条件
{{criteria}}

## 分支选项(用<branch></branch>包裹的内容)
{{branch}}

## 上下文信息
{{context}}

## 约束(必须遵守)
* 只能输出**最多一个**`分支选项`内容，不要输出<branch></branch>标签
* 不要输出额外解释等信息
"""


class ActionBranchOperator(BranchOperator[AgentGenerateContext, AgentGenerateContext]):
    metadata = ViewMetadata(
        label=_("Action Branch Operator"),
        name="action_branch_operator",
        category=OperatorCategory.REASONING,
        operator_type=OperatorType.BRANCH,
        description=_(
            "Branch the workflow based on the agent actionreport nexspeakers of the request."  # noqa
        ),
        parameters=[
            Parameter.build_from(
                "Criteria",
                "criteria",
                type=str,
                description="对分支条件的描述。如：监控数据是否大于某个阈值.",
                ui=ui.UIInput(),
            ),
        ],
        inputs=[
            IOField.build_from(
                _("Agent Request"),
                "input_value",
                AgentGenerateContext,
                description=_("The input value of the operator."),
            ),
        ],
        outputs=[
            IOField.build_from(
                _("Agent Request"),
                "output_value",
                AgentGenerateContext,
                description=_("The output value of the operator."),
            ),
        ],
    )

    def __init__(self, criteria: str, **kwargs):
        super().__init__(**kwargs)
        self.criteria = criteria

    async def _do_run(self, dag_ctx: DAGContext) -> TaskOutput[AgentGenerateContext]:
        def _format_context() -> str:
            ss: list[str] = []
            for upstream in self.upstream:
                if not upstream.node_id in dag_ctx._node_to_outputs:
                    continue

                output: AgentGenerateContext = dag_ctx._node_to_outputs[upstream.node_id].task_output.output
                if not output or not output.message or not output.message.action_report or not output.message.action_report.content:
                    continue

                ss.append(output.message.action_report.content)

            return "\n\n".join(ss)

        branch_nodes: dict[str, list[str]] = {}
        for node in self.downstream:
            if not isinstance(node, ActionBranchConditionOperator):
                continue
            nodes = branch_nodes.get(node.branch, [])
            nodes.append(node.node_name)
            branch_nodes[node.branch] = nodes

        prompt: str = render(_BRANCH_PROMPT_TEMPLATE, {
            "criteria": self.criteria,
            "branch": "<branch>" + "</branch>\n<branch>".join([branch for branch, _ in branch_nodes.items()]) + "</branch>",
            "context": _format_context()
        })

        model_out: ModelOutput = await _llm_client().generate(
            request=ModelRequest(
                model="deepseek-v3",
                messages=[ModelMessage(role="human", content=prompt)],
                trace_id="",
                rpc_id="",
            )
        )
        branch: str = (model_out.content[-1] if isinstance(model_out.content, list) else model_out.content).object.data
        skip_node_names = []
        for _branch, nodes in branch_nodes.items():
            if _branch.strip() != branch.strip():
                skip_node_names.extend(nodes)
        assert len(skip_node_names) != len(self.downstream), f"所有下游分支都不满足条件: {branch}"
        dag_ctx.current_task_context.update_metadata("skip_node_names", skip_node_names)

        return dag_ctx.current_task_context.task_input.parent_outputs[0].task_output


class ActionBranchConditionOperator(MapOperator[AgentGenerateContext, AgentGenerateContext]):
    metadata = ViewMetadata(
        label=_("Action Branch Condition Operator"),
        name="action_branch_condition_operator",
        category=OperatorCategory.REASONING,
        description=_(
            "Branch condition operator to connect BranchOperator and ActionOperator."  # noqa
        ),
        parameters=[
            Parameter.build_from(
                "Branch Description",
                "branch",
                type=str,
                description="Description of the branch.",
                ui=ui.UIInput(),
            ),
        ],
        inputs=[
            IOField.build_from(
                _("Agent Request"),
                "input_value",
                AgentGenerateContext,
                description=_("The input value of the operator."),
            ),
        ],
        outputs=[
            IOField.build_from(
                _("Agent Request"),
                "output_value",
                AgentGenerateContext,
                description=_("The output value of the operator."),
            ),
        ],
    )

    def __init__(self, branch: str, **kwargs):
        super().__init__(**kwargs)
        self._branch = branch

    @property
    def branch(self) -> str:
        return self._branch

    async def map(self, input_value: AgentGenerateContext) -> AgentGenerateContext:
        return input_value


MODELS = [
]


def _load_model_names() -> List[OptionValue]:
    global MODELS
    # if not MODELS:
    #     MODELS = async_to_sync(available_llms)()[0]

    return [OptionValue(label=llm, name=llm, value=llm) for llm in MODELS]


@register_resource(
    label="AgentContextLLMParameter",
    name="agent_context_llm_parameter",
    description="The Parameter to build the AgentContextLLMOperator.",
    category=ResourceCategory.PROMPT,
    parameters=[
        Parameter.build_from(
            label=_("Model Name"),
            name="model_name",
            type=str,
            description=_("The model name."),
            options=FunctionDynamicOptions(func=_load_model_names)
        ),
        Parameter.build_from(
            label=_("Prompt Template"),
            name="prompt_template",
            type=str,
            optional=True,
            default="{{query}}",
            description=_("The user message."),
            ui=ui.DefaultUITextArea(),
        ),
    ],
)
class AgentContextLLMParameter(BaseModel):
    model_name: str = ""
    prompt_template: str = ""


class AgentContextLLMOperator(MixinLLMOperator, MapOperator[AgentGenerateContext, AgentGenerateContext]):
    metadata = ViewMetadata(
        label=_("LLM Operator"),
        name="agent_context_llm_operator",
        category=OperatorCategory.LLM,
        description=_("The LLM operator with context."),
        parameters=[
            Parameter.build_from(
                _("LLM Parameter"),
                "parameter",
                AgentContextLLMParameter,
                description=_("The LLM Parameter."),
            ),

        ],
        inputs=[
            IOField.build_from(
                _("Model Request"),
                "model_request",
                AgentGenerateContext,
                _("The model request."),
            )
        ],
        outputs=[
            IOField.build_from(
                _("Model Output"),
                "model_output",
                AgentGenerateContext,
                description=_("The model output."),
            )
        ],
    )

    def __init__(self, parameter: AgentContextLLMParameter, **kwargs):
        MixinLLMOperator.__init__(self)
        MapOperator.__init__(self, **kwargs)
        # super().__init__(**kwargs)
        self._parameter: AgentContextLLMParameter = parameter

    async def map(self, input_value: AgentGenerateContext) -> AgentGenerateContext:
        await self.current_dag_context.save_to_share_data(self.SHARE_DATA_KEY_MODEL_NAME, self._parameter.model_name)

        awel_agent: AwelRunnerAgent = input_value.receiver
        context: AgentContext = input_value.agent_context
        reply_message: AgentMessage = await awel_agent.init_reply_message(
            received_message=AgentMessage(content="", context=input_value.agent_context.to_dict()),
            sender=input_value.sender,
            rounds=await awel_agent.memory.gpts_memory.next_message_rounds(context.conv_id)
        )

        prompt_param: dict[str, Any] = await self._prompt_param(input_value)
        content: str = render(self._parameter.prompt_template, prompt_param)
        model_output: ModelOutput = await self.llm_client.generate(ModelRequest(
            model=self._parameter.model_name,
            messages=[ModelMessage.build_human_message(content)],
        ))
        await self.save_model_output(self.current_dag_context, model_output)
        reply_message.content = model_output.text
        reply_message.thinking = model_output.thinking_text
        reply_message.model_name = self._parameter.model_name
        result: AgentGenerateContext = copy(input_value)
        result.message = reply_message
        return result

    async def _prompt_param(self, input_value: AgentGenerateContext) -> dict[str, Any]:
        prompt_param: dict[str, Any] = {
            "last_query": input_value.message.content if input_value.message else None,
            "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        # 注意顺序优先级
        for kvs in [
            await self.current_dag_context.get_all_share_data(),
            input_value.message.context if input_value.message else None,
            input_value.agent_context.to_dict() if input_value.agent_context else None,
            input_value.agent_context.extra if input_value.agent_context else None,
        ]:
            if not kvs:
                continue
            for k, v in kvs.items():
                if k not in prompt_param:
                    prompt_param[k] = v

        return prompt_param
