"""Plugin Assistant Agent."""

import json
import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Any, Dict, Tuple, TypeVar, Type

from derisk.agent import (
    AgentMessage,
    Agent,
    ActionOutput,
    Resource,
    ResourceType,
    Action, BlankAction, )
from derisk.agent.core.agent import ContextEngineeringKey
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.memory.gpts import GptsPlan, GptsMessage
from derisk.agent.core.profile import DynConfig, ProfileConfig
from derisk.agent.core.reasoning.reasoning_action import (
    AgentAction,
    KnowledgeRetrieveAction,
)
from derisk.agent.core.reasoning.reasoning_engine import (
    REASONING_LOGGER as LOGGER,
    ReasoningEngineOutput, )
from derisk.agent.core.reasoning.reasoning_engine import (
    ReasoningEngine,
    DEFAULT_REASONING_PLANNER_NAME,
)
from derisk.agent.core.reasoning.reasoning_parser import parse_action_reports
from derisk.agent.core.role import AgentRunMode
from derisk.agent.core.schema import Status
from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
from derisk.agent.expand.actions.tool_action import ToolAction, ToolInput
from derisk.agent.resource import ResourcePack, ToolPack, BaseTool
from derisk.agent.resource.memory import MemoryResource
from derisk.agent.resource.reasoning_engine import ReasoningEngineResource
from derisk.context.event import ActionPayload, AfterActionEvent
from derisk.context.manager import push_context_event
from derisk.util.chat_util import run_async_tasks
from derisk.util.json_utils import serialize
from derisk.vis import SystemVisTag, Vis
from derisk.vis.schema import (
    VisTextContent,
    VisTaskContent,
    StepInfo,
    VisPlansContent,
    VisStepContent, VisConfirm,
)
from derisk_ext.agent.agents.reasoning.default.ability import Ability
from derisk_ext.agent.agents.reasoning.utils import ActionCounter, identify_action_info

_ABILITY_RESOURCE_TYPES = [ResourceType.Tool, ResourceType.KnowledgePack]
_OUTPUT_BY_MAX_STEP: ReasoningEngineOutput = ReasoningEngineOutput()
_OUTPUT_BY_MAX_STEP.done = True
_OUTPUT_BY_MAX_STEP.answer = "动作执行达到最大次数，强制结束任务"
REASONING_AGENT_NAME = "ReasoningPlanner"

T = TypeVar("T")


class CtxKey(str, Enum):
    """运行时上下文Key"""
    REASONING_OUTPUT = "REASONING_OUTPUT"  # 推理模型输出解析结果
    REPLY_MESSAGE = "REPLY_MESSAGE"  # 本轮消息 用于回复

    ACTIONS = "ACTIONS"  # 本轮Actions
    ACTION_REPORTS = "ACTION_REPORTS"  # 本轮ActionReports

    CONV_ROUND_ID = "CONV_ROUND_ID"  # 本轮Plan的conv_round_id
    TASK_UID = "TASK_UID"  # 本轮Plan的task uid
    ACTION_PLAN = "ACTION_PLAN"  # 本轮Plan信息
    REPORT_PLAN = "REPORT_PLAN"  # 本轮总结Plan

    REASON_VIEW = "REASON_VIEW"  # 将本轮模型输出的原因描述转为vis

    ACTION_START_MS = "ACTION_START_MS"  # 所有Action开始执行前的时间
    ACTION_END_MS = "ACTION_END_MS"  # 所有Action执行完毕的时间


class ReasoningAgent(ManagerAgent):
    """Reasoning Agent."""

    profile: ProfileConfig = ProfileConfig(
        name=DynConfig(
            "ReasoningPlanner",
            category="agent",
            key="derisk_agent_expand_reasoning_assistant_agent_name",
        ),
        role=DynConfig(
            "ReasoningPlanner",
            category="agent",
            key="derisk_agent_expand_reasoning_assistant_agent_role",
        ),
        goal=DynConfig(
            "推理Agent：根据绑定的技能(工具, MCP/Local Tool)、子Agent、知识库，"
            "动态规划执行计划，直至任务完成。关键词: ReAct、PromptEngineering。",
            category="agent",
            key="derisk_agent_expand_reasoning_assistant_agent_role",
        ),
        system_prompt_template="",
        user_prompt_template="",
    )
    run_mode: AgentRunMode = AgentRunMode.LOOP
    max_retry_count: int = 100
    content_stream_out: bool = False

    action_counter: ActionCounter = None
    received_message: AgentMessage = None
    sender: Agent = None
    approved_action_reports: List[ActionOutput] = []
    is_retry_chat: bool = False
    is_reasoning_agent: bool = True
    system_prompt: str = None  # Context推理引擎缓存系统提示词 理论上系统提示词在对话过程中应该是不变的

    def __init__(self, **kwargs):
        """Create a new instance of ReasoningAgent."""
        super().__init__(**kwargs)
        self._init_actions([BlankAction])
        self.action_counter: ActionCounter = ActionCounter()

    def _set(self, key: str, value: Any):
        step_ctx: dict = self._ctx.get(self.current_retry_counter, {})
        step_ctx[key] = value
        self._ctx[self.current_retry_counter] = step_ctx
        LOGGER.info(f"set context, round=[{self.current_retry_counter}], key=[{key}]")

    def _get(self, key: str, cls: Type[T] = None) -> T:
        return self._ctx.get(self.current_retry_counter, {}).get(key)

    async def generate_reply(
        self,
        received_message: AgentMessage,
        sender: Agent,
        **kwargs,
    ) -> AgentMessage:
        self.received_message = received_message
        self.sender = sender
        self.approved_action_reports: List[ActionOutput] = await self._parse_approved_action_report()
        self.is_retry_chat = kwargs.get("is_retry_chat", False)

        await self._init_runtime_context()

        # 上下文初始化后调用基类的generate_reply
        return await super().generate_reply(
            received_message=received_message,
            sender=sender,
            **kwargs)

    async def _init_runtime_context(self):
        """初始化用于generate_reply中所需的上下文信息"""
        self._ctx = {}

    async def _load_thinking_messages(
        self,
        received_message: AgentMessage,
        sender: Agent,
        rely_messages: Optional[List[AgentMessage]] = None,
        historical_dialogues: Optional[List[AgentMessage]] = None,
        context: Optional[Dict[str, Any]] = None,
        is_retry_chat: bool = False,
        force_use_historical: bool = False,
        **kwargs
    ) -> Tuple[List[AgentMessage], Optional[Dict], Optional[str], Optional[str]]:
        """组装模型消息 返回: 模型消息、resource_info、系统提示词、用户提示词"""

        LOGGER.info(
            f"[AGENT][推理流程:开始] --------> [{self.name}]"
            f"received_message_id=[{self.received_message.message_id}], "
            f"sender=[{self.sender.role}][{self.sender.name}], "
            f"app_code[{self.agent_context.gpts_app_code}], "
            f"content=[{self.received_message.content}]"
        )
        resource_vars = await self.generate_bind_variables(received_message, sender, rely_messages,
                                                           historical_dialogues, context=context)
        return await self.reasoning_engine.load_thinking_messages(
            agent=self,
            received_message=received_message,
            agent_context=self.agent_context,
            resource_vars=resource_vars,
            context=context,
            rely_messages=rely_messages,
            historical_dialogues=historical_dialogues,
            force_use_historical=force_use_historical,
            sender=sender,
            **kwargs
        )

    def prepare_act_param(
        self,
        received_message: Optional[AgentMessage],
        sender: Agent,
        reply_message: Optional[AgentMessage] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        engine_output: ReasoningEngineOutput = ReasoningEngineOutput()
        engine_output.done = True
        engine_output.answer = "内部异常，未正常结束"
        try:
            # 解析模型结果
            engine_output: ReasoningEngineOutput = self.reasoning_engine.parse_output(
                agent=self,
                reply_message=reply_message,
                sender=sender,
                **kwargs
            )
        except Exception as e:
            engine_output.done = True
            engine_output.answer = f"模型调用失败或结果解析失败\n{repr(e)}"
            LOGGER.exception(f"[ENGINE][{self.name}]模型调用或结果解析失败")

        self._set(CtxKey.REASONING_OUTPUT, engine_output)
        self._set(CtxKey.REPLY_MESSAGE, reply_message)

        return {}

    async def act(self, **kwargs) -> ActionOutput:
        if not self._get(CtxKey.REASONING_OUTPUT):
            pass

        # 执行动作前 先准备相关信息
        await self._before_act()

        # 若有结论 则不再执行动作
        if await self._process_summary():
            return self._get(CtxKey.REPLY_MESSAGE, AgentMessage).action_report

        # 依次执行Action
        output = self._get(CtxKey.REASONING_OUTPUT, ReasoningEngineOutput)
        LOGGER.info(f"[AGENT]actions size:{len(output.actions)}")
        action_tasks = []
        for idx, action_uid in enumerate([action_uid for action in output.actions if (action_uid := action.action_uid)]):
            action_tasks.append(self._run_action(action_uid, idx=idx))
        await run_async_tasks(action_tasks)

        # Action执行完毕
        await self._after_act()

        return self._get(CtxKey.REPLY_MESSAGE, AgentMessage).action_report

    async def _process_summary(self) -> bool:
        output: ReasoningEngineOutput = self._get(CtxKey.REASONING_OUTPUT)
        if (not output.answer) and (not output.done):
            # 没有结论 不处理
            return False

        reply_message = self._get(CtxKey.REPLY_MESSAGE, AgentMessage)

        summary_agent = self._find_summary_agent()
        await self._init_report_plan(summary_agent)

        if summary_agent:
            LOGGER.info(f"[AGENT]找到summary_agent:[{summary_agent.name}]")
            ## Reasoning Agent 的总结Agent强制开启 内容区域流式输出
            summary_agent.content_stream_out = True

            # 总结规划记忆更新
            await self._update_report_plan(Status.RUNNING)

            report_message = reply_message.copy()
            report_message.goal_id = self._get(CtxKey.TASK_UID)
            report_message.content = self.received_message.current_goal
            await self.send(report_message, recipient=summary_agent, request_reply=False)
            report_out_message = await summary_agent.generate_reply(
                received_message=report_message,
                sender=self,
                current_step_message=reply_message,
                output=output,
            )
            await summary_agent.send(report_out_message, recipient=self, request_reply=False)

            # 总结规划记忆更新
            await self._update_report_plan(Status.COMPLETE)
            report_out_message.action_report.terminate = True  # --> 结束任务 <--

            LOGGER.info(f"[AGENT]答案2：agent:[{self.name}], answer[{report_out_message}]]")

            # 使用总结子Agent的reply作为最终的reply
            self._set(CtxKey.REPLY_MESSAGE, report_out_message)
            return True

        LOGGER.info(f"[AGENT]开始组装回复消息 agent:[{self.name}], reply_message[{reply_message.message_id}]")
        reply_message.action_report = (
            ActionOutput.from_dict(
                {
                    "view": await self._render_protocol(
                        vis_tag=SystemVisTag.VisText.value
                    ).display(
                        content=VisTextContent(
                            markdown=output.answer,
                            type="all",
                            uid=reply_message.message_id
                                + "_answer",
                            message_id=reply_message.message_id,
                        ).to_dict()
                    ),
                    "model_view": output.answer,
                    # "action_id": received_action_id + "-answer",
                    "extra": (self.received_message.context or {}) | {"title": "结论"},
                    "content": output.answer,
                    "observations": output.answer,
                    "action": self.name,
                    "action_name": AgentAction().name,
                    "action_input": self.received_message.content,
                    "terminate": True,  # --> 结束任务 <--
                }
            )
        )
        LOGGER.info(
            f"[AGENT][消息回复:开始] ----> "
            f"agent:[{self.name}], reply_message[{reply_message.message_id}], to [{self.sender.name}]"
        )
        # ================================↓↓↓ 消息回复 ↓↓↓================================ #
        if output.references:
            reply_message.action_report.view = (
                f"{reply_message.action_report.view}\n"
                + await self._render_reference_view(
                ref_resources=output.references,
                uid=reply_message.message_id + "_ref",
                message_id=reply_message.message_id,
            )
            )
        # await self.send(
        #     message=current_step_message,
        #     recipient=sender,
        #     request_reply=False,
        # )
        # if check_memory_resource(resource=self.resource):
        #     await self.write_memories(
        #         question=self.received_message.content or "",
        #         current_message=reply_message,
        #         observation=output.answer,
        #         check_pass=True,
        #         check_fail_reason="",
        #         agent_id=self.not_null_agent_context.agent_app_code,
        #     )

        # ================================↑↑↑ 消息回复 ↑↑↑================================ #
        LOGGER.info(
            f"[AGENT][消息回复:完成] <---- "
            f"agent:[{self.name}], reply_message[{reply_message.message_id}], to [{self.sender.name}]"
        )
        if output.actions:
            LOGGER.info(
                f"[AGENT]模型幻觉，既有结论又有action，size={len(output.actions)}。"
                f"agent:[{self.name}], reply_message[{reply_message.message_id}], to [{self.sender.name}]"
            )

        await self._push_summary_action()

        # 总结规划记忆更新
        await self._update_report_plan(Status.COMPLETE)

        LOGGER.info(f"[AGENT]答案1：agent:[{self.name}], answer[{reply_message}]]")

        return True

    async def _before_act(self):
        # 先初始化plan相关信息
        await self._init_plan()

        output = self._get(CtxKey.REASONING_OUTPUT)
        reply_message = self._get(CtxKey.REPLY_MESSAGE)
        if not output.actions:
            return

        # 先初始化action需要的数据
        self._init_actions_before(actions=output.actions)
        reply_message.action_report = ActionOutput(
            content="",
            state=Status.RUNNING.value,
            extra={"title": output.plans_brief_description},
        )

        # 将Action和Report转为Map存储
        action_map: Dict[str, Action] = {}
        action_reports: Dict[str, ActionOutput] = {}
        for idx, action in enumerate(output.actions):
            action_map[action.action_uid] = action
            action_reports[action.action_uid] = ActionOutput(
                content="",
                action="",
                action_name=action.name,
                action_input=action.action_input.json(),
                state=Status.RUNNING.value,
            )
        self._set(CtxKey.ACTIONS, action_map)
        self._set(CtxKey.ACTION_REPORTS, action_reports)

        # 初始化Plan信息
        await self._init_action_plan()

        # 记录步骤原因
        reason_view = (
            await self._render_markdown_view(
                output.action_reason,
                uid=reply_message.message_id + "_reason",
                message_id=reply_message.message_id,
            )
            if output.action_reason else "")
        self._set(CtxKey.REASON_VIEW, reason_view)

        # Action前先发消息
        await self._update_step_action_report()
        LOGGER.info(f"[AGENT][Action前先发消息] ----> agent:[{self.name}]")
        await self._push_action_message()

        # 记录Action开始时间
        self._set(CtxKey.ACTION_START_MS, _current_ms())

    async def _run_action(self, action_uid: str, idx: int):
        action_success = True
        reply_message: AgentMessage = self._get(CtxKey.REPLY_MESSAGE)
        action: Action = self._get(CtxKey.ACTIONS)[action_uid]
        action_report: ActionOutput = self._get(CtxKey.ACTION_REPORTS)[action_uid]
        action_size = len(self._get(CtxKey.ACTIONS))
        action_item_ms = _current_ms()
        try:
            LOGGER.info(
                f"[AGENT][V2执行Action:开始] ----> agent:[{self.name}], step:{self.current_retry_counter}, "
                f"Action:[{action.name}][{idx}]/[{action_size}][{action_uid}]"
            )
            await self._update_action_plan(action_uid=action_uid, state=Status.RUNNING)

            require_approval = not (self.recovering and any((1 for approved_action_report in self.approved_action_reports if approved_action_report)))
            try:
                action_report = await action.run(
                    agent=self,
                    message_id=reply_message.message_id,
                    resource=self.resource,
                    message=reply_message,
                    require_approval=require_approval,
                    is_retry_chat=self.is_retry_chat,
                ) if self.action_counter.add_and_count(action) else format_action_report_by_max_count(action_report)
            except Exception as e:
                action_report.is_exe_success = False
                action_report.content = "执行失败: " + repr(e)

            # 动作执行后 更新message并展示/落表
            action_report.action = action_report.action or action.name
            action_report.action_input = action_report.action_input or action.action_input.json()
            action_report.action_intention = action_report.action_intention or action.intention
            action_report.action_reason = action_report.action_reason or action.reason
            action_report.state = Status.WAITING.value if action_report.ask_user else Status.COMPLETE.value if action_report.is_exe_success else Status.FAILED.value
            action_report.cost_ms = action_report.cost_ms or (_current_ms() - action_item_ms)
            await push_context_event(event=AfterActionEvent(payload=ActionPayload(action_output=action_report)), agent=self)
            self._get(CtxKey.ACTION_REPORTS)[action_uid] = action_report
            await self._update_action_plan(
                action_uid=action_uid,
                state=Status.COMPLETE if action_report.is_exe_success else Status.FAILED
            )
            await self._update_step_action_report()
            await self._push_action_message()
        except Exception as e:
            action_success = False
            LOGGER.exception(
                f"[AGENT][V2执行Action:异常] <---- "
                f"agent:[{self.name}], Action:[{action.name}][{idx}]/[{action_size}], except:[{repr(e)}]"
            )
            raise ReasoningActionException(repr(e))
        finally:
            LOGGER.info(
                f"[AGENT][V2执行Action:结束] <---- "
                f"agent:[{self.name}], step:{self.current_retry_counter}, Action:[{action.name}][{idx}]/[{action_size}], "
                f"success:[{action_success}], content:[{action_report.content if action_report else None}]"
            )
            LOGGER.info(
                f""
                f"[DIGEST][ACTION]"
                f"agent_name=[{self.name.replace('[', '(').replace(']', ')')}],"  # 监控采集配的是左起'['、右至']'，统一替换以兼容
                f"received_message_id=[{self.received_message.message_id}],"
                f"current_step_message_id=[{reply_message.message_id}],"
                f"reasoning_engine_name=[{self.reasoning_engine.name}],"
                f"step_counter=[{self.current_retry_counter}],"  # 第几个step(轮次)
                f"retry_counter=[{0}],"  # 模型连续重试了几次
                f"action_size=[{action_size}],"  # 共几个action
                f"current_action_index=[{action.action_uid}],"  # 当前是第几个action
                f"action_ms=[{_current_ms() - action_item_ms}],"  # 本action执行耗时
                f"step_action_ms=[{_current_ms() - self._get(CtxKey.ACTION_START_MS)}],"  # 本轮action执行总耗时
                f"action_success=[{action_success}],"  # 本action是否成功
                f"action_name=[{action.name}],"  # action name
                f"action_id=[],"
            )

    async def _after_act(self):
        self._set(CtxKey.ACTION_END_MS, _current_ms())
        # if check_memory_resource(resource=self.resource):
        #     await self.write_memories(
        #         question=self.received_message.content or "",
        #         current_message=self._get(CtxKey.REPLY_MESSAGE),
        #         action_outputs=list(self._get(CtxKey.ACTION_REPORTS).values()),
        #         check_fail_reason="",
        #         agent_id=self.not_null_agent_context.agent_app_code,
        #     )

        reply_action_report: ActionOutput = self._get(CtxKey.REPLY_MESSAGE, AgentMessage).action_report
        for action_report in self._get(CtxKey.ACTION_REPORTS, dict[str, ActionOutput]).values():
            reply_action_report.ask_user = reply_action_report.ask_user or action_report.ask_user
            reply_action_report.terminate = reply_action_report.terminate or action_report.terminate or reply_action_report.ask_user

        LOGGER.info(f"[AGENT][所有Action均已执行完成] <---- agent:[{self.name}], step:[{self.current_retry_counter}]")

    def _next_plan_task_uid(self, initial: bool = False) -> str:
        if initial:
            task_uid = uuid.uuid4().hex
            self._set(CtxKey.TASK_UID, task_uid)
            LOGGER.info(f"_next_plan_task_uid[{initial}]: {task_uid}")
            return task_uid

        initial_task_uid = self._get(CtxKey.TASK_UID)
        if initial_task_uid:
            self._set(CtxKey.TASK_UID, None)
        task_uid = initial_task_uid or uuid.uuid4().hex
        LOGGER.info(f"_next_plan_task_uid[{initial}]: {task_uid}")
        return task_uid

    async def _init_plan(self):
        conv_round_id = uuid.uuid4().hex
        self._set(CtxKey.CONV_ROUND_ID, conv_round_id)

        task_uid = uuid.uuid4().hex
        self._set(CtxKey.TASK_UID, task_uid)

        if self.received_message.role == HUMAN_ROLE:
            plans: List[GptsPlan] = await self.memory.gpts_memory.get_plans(self.not_null_agent_context.conv_id)
            plan_num = 1
            if plans and len(plans) > 0:
                plan_num = plans[-1].conv_round
            await self.memory.gpts_memory.append_plans(
                conv_id=self.agent_context.conv_id,
                plans=[GptsPlan(
                    conv_id=self.agent_context.conv_id,
                    conv_session_id=self.agent_context.conv_session_id,
                    conv_round=plan_num + 1,
                    conv_round_id=conv_round_id,
                    sub_task_id=task_uid,
                    task_uid=task_uid,
                    action=ResourceType.Agent.value,
                    task_round_title=f"开始第{self.current_retry_counter + 1}轮探索分析...",
                    task_round_description="",
                    planning_agent=self.name,
                )], need_storage=False)

    async def _init_action_plan(self):
        # if self.recovering:
        #     plans: List[GptsPlan] = await self.memory.gpts_memory.get_plans(self.not_null_agent_context.conv_id)
        #     conv_round_id = plans[-1].conv_round_id if plans else uuid.uuid4().hex
        #     task_uid = plans[-1].task_uid if plans else uuid.uuid4().hex

        ### 目前只记录第一层的规划内容，内部子Agent的规划先不记录
        ### 规划轮次计算
        step_plans = []
        action_plan_map = {}
        output: ReasoningEngineOutput = self._get(CtxKey.REASONING_OUTPUT)

        if self.received_message.role == HUMAN_ROLE and output.actions:
            plans: List[GptsPlan] = await self.memory.gpts_memory.get_plans(self.not_null_agent_context.conv_id)
            plan_num = 1
            if plans and len(plans) > 0:
                plan_num = plans[-1].conv_round

            for idx, action in enumerate(output.actions):
                # task_uid = self._get(CtxKey.TASK_UID)
                task_uid = uuid.uuid4().hex

                ### 处理Action的类型，目前可枚举工具、agent、知识，暂无动态扩展诉求
                action_input, agent, agent_type = identify_action_info(action)

                step_plan: GptsPlan = GptsPlan(
                    conv_id=self.agent_context.conv_id,
                    conv_session_id=self.agent_context.conv_session_id,
                    conv_round=plan_num + 1,
                    conv_round_id=self._get(CtxKey.CONV_ROUND_ID),
                    sub_task_id=task_uid,
                    sub_task_num=0,
                    task_uid=task_uid,
                    sub_task_content=action.reason or "",
                    sub_task_title=action.intention,
                    sub_task_agent=agent,
                    state=Status.TODO.value,
                    action=agent_type,

                    task_round_title=f"[第{self.current_retry_counter + 1}轮探索分析]{output.plans_brief_description}",
                    task_round_description=output.action_reason,
                    planning_agent=self.name,
                    planning_model=output.model_name,
                )
                step_plans.append(step_plan)
                action_plan_map[action.action_uid] = step_plan
            await self.memory.gpts_memory.append_plans(
                conv_id=self.agent_context.conv_id,
                plans=step_plans)
            self._set(CtxKey.ACTION_PLAN, action_plan_map)
            self._get(CtxKey.REPLY_MESSAGE, AgentMessage).goal_id = task_uid  # todo: fix
            self._get(CtxKey.REPLY_MESSAGE, AgentMessage).current_goal = action.intention  # todo: fix

    async def _update_plan(self, plan: GptsPlan, state: Status):
        if not plan:
            return

        plan.state = state.value

        # 落表并更新显示
        await self.memory.gpts_memory.update_plan(
            conv_id=self.agent_context.conv_id,
            plan=plan,
            incremental=self.agent_context.incremental
        )

    async def _update_action_plan(self, action_uid: str, state: Status):
        plans = self._get(CtxKey.ACTION_PLAN, dict)
        if not plans:
            # 前面没有初始化 说明本Agent无需显示Plan(eg. sender不是Human)
            return

        plan: GptsPlan = plans.get(action_uid)
        await self._update_plan(plan, state=state)

    async def _update_report_plan(self, state: Status):
        plan: GptsPlan = self._get(CtxKey.REPORT_PLAN)
        await self._update_plan(plan, state=state)

    async def _init_report_plan(self, summary_agent: Agent):
        output: ReasoningEngineOutput = self._get(CtxKey.REASONING_OUTPUT)
        if self.received_message.role == HUMAN_ROLE and output.answer:
            # ================================↓↓↓ 规划轮次计算 ↓↓↓================================ #
            plans: List[GptsPlan] = await self.memory.gpts_memory.get_plans(
                self.not_null_agent_context.conv_id)
            plan_num = 1
            if plans and len(plans) > 0:
                plan_num = plans[-1].conv_round
            # ================================↑↑↑ 规划轮次计算 ↑↑↑================================ #
            task_uid = self._get(CtxKey.TASK_UID)
            report_plan: GptsPlan = GptsPlan(
                conv_id=self.agent_context.conv_id,
                conv_session_id=self.agent_context.conv_session_id,
                conv_round=plan_num + 1,
                conv_round_id=self._get(CtxKey.CONV_ROUND_ID),
                sub_task_id=task_uid,
                sub_task_num=0,
                task_uid=task_uid,
                sub_task_title="报告答案生成",
                task_round_title=f"[第{self.current_retry_counter + 1}轮探索分析]答案报告生成",
                sub_task_agent=summary_agent.name if summary_agent else self.name,
                state=Status.TODO.value,
                action=ResourceType.Agent.value,
                planning_agent=self.name,
                planning_model=output.model_name,
            )
            await self.memory.gpts_memory.append_plans(
                conv_id=self.agent_context.conv_id, plans=[report_plan])
            self._set(CtxKey.REPORT_PLAN, report_plan)
            self._get(CtxKey.REPLY_MESSAGE, AgentMessage).goal_id = task_uid
            self._get(CtxKey.REPLY_MESSAGE, AgentMessage).current_goal = "报告答案生成"

    @property
    def reasoning_engine(self) -> Optional[ReasoningEngine]:
        def _default_reasoning_engine():
            return ReasoningEngine.get_reasoning_engine(DEFAULT_REASONING_PLANNER_NAME)

        def _transfer(resource: Resource) -> Optional[ReasoningEngine]:
            if not resource:
                return None

            if isinstance(resource, ReasoningEngineResource):
                return ReasoningEngine.get_reasoning_engine(resource.name)

            if isinstance(resource, ResourcePack):
                return next((_engine for sub_resource in resource.sub_resources if (_engine := _transfer(sub_resource))), None, )

            return None

        return _transfer(self.resource) or _default_reasoning_engine()

    @property
    def ability_resources(self) -> list[Resource]:
        def _unpack(resource: Resource) -> Optional[list[Resource]]:
            if not resource:
                return []

            elif resource.type() in _ABILITY_RESOURCE_TYPES:
                return [resource]

            elif isinstance(resource, ResourcePack) and resource.sub_resources:
                result = []
                for r in resource.sub_resources:
                    if r.type() in _ABILITY_RESOURCE_TYPES:
                        result.append(r)
                    elif isinstance(r, ResourcePack):
                        result.extend(_unpack(r))
                return result

            return []

        return _unpack(self.resource)

    @property
    def abilities(self) -> list[Ability]:
        result = []
        ## 总结助手排除
        summary_agent = self._find_summary_agent()
        summary_agent_name = summary_agent.name if summary_agent else ""
        result.extend(
            [
                ability
                for agent in self.agents
                if (ability := Ability.by(agent)) and agent.name != self.name and agent.name != summary_agent_name
            ]
        )
        result.extend(
            [
                ability
                for resource in self.ability_resources
                if (ability := Ability.by(resource))
            ]
        )
        return result

    # async def write_memories(
    #     self,
    #     question: str,
    #     current_message: AgentMessage,
    #     observation: Optional[str] = None,
    #     action_outputs: Optional[List[ActionOutput]] = None,
    #     check_pass: bool = True,
    #     check_fail_reason: Optional[str] = None,
    #     agent_id: Optional[str] = None,
    # ) -> MemoryFragment:
    #     """Write the memories to the memory.
    #
    #     We suggest you to override this method to save the conversation to memory
    #     according to your needs.
    #
    #     Args:
    #         question(str): The question received.
    #         current_message(AgentMessage): The current message to write.
    #         observation(str): The observation, usually the final answer or output.
    #         action_outputs(Optional[List[ActionOutput]]): The action output.
    #         check_pass(bool): Whether the check pass.
    #         check_fail_reason(str): The check fail reason.
    #         agent_id(str): The agent_id.
    #
    #
    #     Returns:
    #         AgentMemoryFragment: The memory fragment created.
    #     """
    #     mem_thoughts = action_outputs[0].thoughts if \
    #         action_outputs and action_outputs[0].thoughts else current_message.content
    #     actions = []
    #     action_inputs = []
    #     action_results = []
    #     if action_outputs:
    #         for action_output in action_outputs:
    #             actions.append(action_output.action if action_output else "answer")
    #             action_results.append(
    #                 f"{action_output.action}:{observation or action_output.content}"
    #             )
    #             action_inputs.append(action_output.action_input if action_output else None)
    #     action = ",".join(actions) if actions else "answer"
    #     observation = "\n".join(action_results) if actions else observation
    #     memory_map = {
    #         "question": question,
    #         "thought": mem_thoughts,
    #         "action": action,
    #         "observation": observation,
    #     }
    #     if action_inputs:
    #         memory_map["action_input"] = "\n".join(action_inputs)
    #
    #     write_memory_template = self.write_memory_template
    #     memory_content = self._render_template(write_memory_template, **memory_map)
    #     from derisk_ext.agent.memory.session import SessionMemoryFragment
    #     fragment = SessionMemoryFragment(
    #         observation=memory_content,
    #         rounds=current_message.rounds,
    #         message_id=current_message.message_id,
    #         role=self.name,
    #         agent_id=agent_id,
    #         task_goal=question,
    #         thought=mem_thoughts,
    #         action=action,
    #         action_result=observation,
    #     )
    #     memory_parameter: MemoryParameters = self.get_memory_parameters()
    #     await self.memory.write(
    #         memory_fragment=fragment,
    #         enable_message_condense=memory_parameter.enable_message_condense,
    #         message_condense_mode=memory_parameter.message_condense_model,
    #         message_condense_prompt=memory_parameter.message_condense_prompt,
    #     )
    #     # if action_output:
    #     #     action_output.memory_fragments = {
    #     #         "memory": fragment.raw_observation,
    #     #         "id": fragment.id,
    #     #         "importance": fragment.importance,
    #     #     }
    #     return fragment

    def _render_protocol(self, vis_tag: str) -> Vis:

        return self.memory.gpts_memory.vis_converter(self.not_null_agent_context.conv_id).vis_inst(vis_tag)

    async def _render_markdown_view(
        self, text: str, uid: str, message_id: Optional[str] = None
    ) -> str:
        return self._render_protocol(vis_tag=SystemVisTag.VisText.value).sync_display(
            content=VisTextContent(
                markdown=text, type="all", uid=uid, message_id=message_id
            ).to_dict()
        )

    async def _render_reference_view(
        self, ref_resources: List[dict], uid: str, message_id: Optional[str] = None
    ) -> str:
        """Render a reference view for the given text."""
        return self._render_protocol(vis_tag=SystemVisTag.VisRefs.value).sync_display(
            content=ref_resources, uid=uid, message_id=message_id
        )

    async def _render_action_view(self) -> str:
        message_id: str = self._get(CtxKey.REPLY_MESSAGE, AgentMessage).message_id
        action_and_reports: list[tuple[Action, ActionOutput]] = [(
            self._get(CtxKey.ACTIONS)[action_uid],
            self._get(CtxKey.ACTION_REPORTS)[action_uid],
        ) for action in self._get(CtxKey.REASONING_OUTPUT, ReasoningEngineOutput).actions
            if (action_uid := action.action_uid)]

        # AgentAction放前面 统一放在VisPlansContent里
        agent_action_and_reports = [
            (action, report)
            for (action, report) in action_and_reports
            if isinstance(action, AgentAction)
        ]
        agent_actions_view = (
            await self._render_protocol(vis_tag=SystemVisTag.VisPlans.value).display(
                content=VisPlansContent(
                    uid=message_id + "_action_agent",
                    type="all",
                    message_id=message_id + "_action_agent",
                    tasks=[
                        await _format_vis_content(action=action, output=report)
                        for (action, report) in agent_action_and_reports
                    ],
                ).to_dict()
            )
            if agent_action_and_reports
            else None
        )

        # 其他Action(Tool/RAG)放后面 统一放在VisStepContent里
        other_action_views = []
        for idx, (action, report) in enumerate(action_and_reports):
            # if report.ask_user:
            #     continue
            if isinstance(action, AgentAction):
                continue
            step_content: StepInfo = await _format_vis_content(
                action=action, output=report
            )
            if not step_content:
                continue

            other_action_views.append(
                await self._render_protocol(vis_tag=SystemVisTag.VisTool.value).display(
                    content=VisStepContent(
                        uid=message_id + "_action_" + str(idx),
                        message_id=message_id + "_action_" + str(idx),
                        type="all",
                        status=step_content.status,
                        tool_name=step_content.tool_name,
                        tool_args=step_content.tool_args,
                        tool_result=step_content.tool_result,
                    ).to_dict()
                )
            )

        # # 需要用户授权的放最后
        # ask_user_view = await self._render_confirm_action(action_and_reports)
        ask_user_view = None

        return "\n".join(
            [view for view in [agent_actions_view] + other_action_views + [ask_user_view] if view]
        )

    async def _render_confirm_action(self, action_and_reports: list[tuple[Action, ActionOutput]]) -> str:
        reply_message: AgentMessage = self._get(CtxKey.REPLY_MESSAGE)

        def _make_one_markdown(action: Action, report: ActionOutput) -> str:
            return f"* 动作:{report.action_name}({report.action}),参数:{report.action_input}"

        markdown = "\n\n".join([_make_one_markdown(action, report)
                                for action, report in action_and_reports if report.ask_user])
        if not markdown:
            return ""

        markdown = "将执行如下动作:\n\n" + markdown + "\n\n是否确认执行?"
        return await self._render_protocol(vis_tag=SystemVisTag.VisConfirm.value).display(
            content=VisConfirm(
                uid=reply_message.message_id + "_confirm",
                message_id=reply_message.message_id + "_confirm",
                type="all",
                markdown=markdown,
                extra={"approval_message_id": reply_message.message_id}
            ).to_dict()
        )

    # async def _render_confirm_view(
    #     self, output: ReasoningEngineOutput, message_id: str
    # ) -> str:
    #     assert output and output.actions is not None and len(output.actions) > 0, (
    #         "模型未输出Action，无法供用户确认"
    #     )
    #
    #     items = []
    #
    #     items.append(
    #         await self._render_protocol(SystemVisTag.VisText.value).display(
    #             content=VisTextContent(
    #                 markdown=output.action_reason,
    #                 type="all",
    #                 uid=uuid.uuid4().hex,
    #                 message_id=message_id,
    #             ).to_dict()
    #         )
    #         if output.action_reason
    #         else None
    #     )
    #     for idx, action in enumerate(output.actions):
    #         vis_content = await _format_vis_content(action=action)
    #         content = (
    #             vis_content.task_content + f" `@ {vis_content.agent_name}`"
    #             if isinstance(vis_content, VisTaskContent)
    #             else vis_content.tool_name
    #         )
    #         confirm_view = await self._render_protocol(
    #             SystemVisTag.VisSelect.value
    #         ).display(
    #             content=VisSelectContent(
    #                 uid=message_id + "_action_" + str(idx),
    #                 message_id=message_id + "_action_" + str(idx),
    #                 type="all",
    #                 markdown=content,
    #                 confirm_message="请执行动作: " + content,
    #                 extra={},
    #             ).to_dict()
    #         )
    #         items.append(confirm_view)
    #
    #     return "\n".join([item for item in items if item])

    async def _format_view(self) -> str:
        # 页面显示给人看的信息包含两部分：1)上面是一段描述(可能为空)，介绍要执行这些动作的原因; 2)下面是执行的具体动作
        reason_view: str = self._get(CtxKey.REASON_VIEW)
        action_view: str = await self._render_action_view()
        return "\n".join([s for s in [reason_view, action_view] if s])

    async def _update_step_action_report(self) -> None:
        reply_message: AgentMessage = self._get(CtxKey.REPLY_MESSAGE)
        action_uids = [action.action_uid for action in self._get(CtxKey.REASONING_OUTPUT, ReasoningEngineOutput).actions]

        actions = []
        action_inputs = []
        action_results = []
        action_states = []
        for action_uid in action_uids:
            action_report: ActionOutput = self._get(CtxKey.ACTION_REPORTS)[action_uid]
            actions.append(action_report.action)
            action_inputs.append(action_report.action_input)
            action_results.append(f"{action_report.action}:{action_report.content}")
            action_states.append(action_report.state)
        reply_message.action_report.content = json.dumps(
            [
                self._get(CtxKey.ACTION_REPORTS)[action_uid].to_dict()
                for action_uid in action_uids
            ], ensure_ascii=False,
        )
        reply_message.action_report.view = await self._format_view()
        reply_message.action_report.action = json.dumps(actions, ensure_ascii=False)
        reply_message.action_report.action_input = json.dumps(action_inputs, ensure_ascii=False)
        reply_message.action_report.observations = json.dumps(action_results, ensure_ascii=False)
        reply_message.action_report.state = self._merge_action_report_states(action_states)

    def _merge_action_report_states(self, states: list[str]) -> str:
        state_priority = {
            Status.FAILED.value: 1,
            Status.RUNNING.value: 2,
            Status.WAITING.value: 3,
        }
        max_priority = -9999
        max_priority_state = None
        for state in states:
            priority = state_priority.get(state, -1)
            if priority > max_priority:
                max_priority = priority
                max_priority_state = state
        return max_priority_state

    async def _push_action_message(self) -> None:
        message: AgentMessage = self._get(CtxKey.REPLY_MESSAGE)
        await self.memory.gpts_memory.append_message(
            conv_id=self.agent_context.conv_id,
            message=message.to_gpts_message(sender=self, role=None, receiver=self),
            sender=self
        )
        LOGGER.info("_push_action_message, view: " + message.action_report.view)

    def _init_actions_before(self, actions: list[Action]):
        for action in actions:
            action.init_resource(self.resource)
            action.init_action(
                render_protocol=self.memory.gpts_memory.vis_converter(self.not_null_agent_context.conv_id))

    async def _push_summary_action(self):
        # 总结信息里面的引用摘要
        summary_actions = await self._get_summary_action(
            self.not_null_agent_context.conv_id,
            self._get(CtxKey.REASONING_OUTPUT))
        if len(summary_actions) > 0:
            LOGGER.info(
                f"[AGENT][总结更新:开始] ----> "
                f"agent:[{self.name}], reply_message[{self._get(CtxKey.REPLY_MESSAGE).message_id}], to [{self.sender.name}]"
            )
            actions = []
            for idx, action_output in enumerate(summary_actions):
                if action_output is None:
                    continue
                action_input: Optional[ToolInput] = ToolInput(
                    tool_name=action_output.action, thought="thought"
                )
                action_input.args = action_output.action_input
                action: Optional[ToolAction] = ToolAction()
                action.action_input = action_input
                actions.append(action)
            await self._update_step_action_report()
            await self._push_action_message()
            LOGGER.info(
                f"[AGENT][总结更新:完成] ----> "
                f"agent:[{self.name}], reply_message[{self._get(CtxKey.REPLY_MESSAGE).message_id}], to [{self.sender.name}]"
            )

    async def _get_summary_action(self, conv_id, output):
        summary_actions = []
        if "<message_id>" in output.answer:
            try:
                LOGGER.info(
                    f"[AGENT]_get_summary_action agent:[{self.name}], {output.answer}"
                )
                # 使用正则表达式提取<message_id>并移除相关内容
                pattern = r"<message_id>:\s*([a-f0-9]{32})"
                message_ids = re.findall(pattern, output.answer)  # 提取所有<message_id>
                text_cleaned = re.sub(
                    pattern, "", output.answer
                )  # 从文本中移除匹配的部分
                output.answer = text_cleaned

                intentions = re.findall(r"意图: ([^)]*)", text_cleaned)

                all_messages = await self.memory.gpts_memory.get_messages(conv_id)
                for idx, message_id in enumerate(message_ids):
                    # 根据message_id回查
                    message = next(
                        (msg for msg in all_messages if msg.message_id == message_id),
                        None,
                    )
                    if message is None:
                        continue
                    action_reports = parse_action_reports(message.action_report)
                    for _, action_report in enumerate(action_reports):
                        # 拍平
                        LOGGER.info(
                            f"[AGENT]_get_summary_action agent:[{self.name}], content:[{action_report.content if action_report else None}]"
                        )
                        if len(intentions) > idx:
                            action_report.action = "意图: " + intentions[idx]
                        summary_actions.append(action_report)
            except Exception as e:
                LOGGER.info(
                    f"[AGENT][_get_summary_action:异常] agent:[{self.name}], output:[{output.answer}], except:[{repr(e)}]"
                )
        return summary_actions

    def need_user_confirm(
        self,
        output: ReasoningEngineOutput,
        sender: Agent,
        step_counter: int,
        conv_id: str,
    ) -> bool:
        return (
            output
            and output.actions
            and sender.name == "User"
            and step_counter == 0
            and conv_id.endswith("_1")
            and False
        )

    # async def send_confirm_message(
    #     self,
    #     output: ReasoningEngineOutput,
    #     current_step_message: AgentMessage,
    #     received_message: AgentMessage,
    #     received_action_id: str,
    # ):
    #     current_step_message.action_report = ActionOutput.from_dict(
    #         {
    #             "view": await self._render_confirm_view(
    #                 output=output, message_id=current_step_message.message_id
    #             ),
    #             "model_view": output.answer,
    #             "action_id": received_action_id + "-confirm",
    #             "extra": received_message.context | {"title": "待用户确认"},
    #             "content": "待用户确认",
    #             "action": self.name,
    #             "action_name": UserConfirmAction().name,
    #             "action_input": received_message.content,
    #         }
    #     )
    #     await self._push_action_message(message=current_step_message)

    def _find_summary_agent(
        self,
    ) -> Agent | None:
        """Find current Summary Agent"""
        reason_engine_map = {}
        for agent in self.agents:
            from derisk.agent.expand.summary_assistant_agent import \
                SummaryAssistantAgent
            if isinstance(agent, SummaryAssistantAgent):
                return agent

            if hasattr(agent, "reasoning_engine") and agent.reasoning_engine:
                reason_engine_map[
                    agent.reasoning_engine.name
                ] = agent

        from derisk_ext.reasoning_engine.summary_reasoning_engine import \
            SUMMARY_REPORT_ENGINE_NAME
        if reason_engine_map and reason_engine_map.get(
            SUMMARY_REPORT_ENGINE_NAME
        ):
            return reason_engine_map.get(SUMMARY_REPORT_ENGINE_NAME)
        return None

    async def _parse_approved_action_report(self) -> list[ActionOutput]:
        approval_message_id: str = self.agent_context.extra.get('approval_message_id')
        if not approval_message_id:
            return []
        approval_message: GptsMessage = self.memory.gpts_memory.message_memory.get_by_message_id(approval_message_id)
        if not approval_message:
            return []

        return parse_action_reports(approval_message.action_report)


async def _format_vis_content(action: Action, output: ActionOutput = None) -> Any:
    if isinstance(action, AgentAction):
        content = VisTaskContent(task_uid=uuid.uuid4().hex)
        content.task_content = action.action_input.content
        content.task_name = action.action_input.content
        content.agent_name = action.action_input.agent_name
    elif isinstance(action, ToolAction):
        tool_name = action.action_input.tool_name
        tool_packs = ToolPack.from_resource(action.resource)
        for tool_pack in tool_packs:
            if not tool_pack:
                continue
            base_tool: BaseTool = await tool_pack.get_resources_info(
                resource_name=action.action_input.tool_name
            )
            if not (base_tool and base_tool.description):
                continue
            tool_name = base_tool.description
            break

        content = StepInfo()
        content.tool_name = tool_name
        content.tool_args = json.dumps(
            action.action_input.args, default=serialize, ensure_ascii=False
        )
        content.tool_result = output.content if output else None
        content.status = (
            Status.TODO.value
            if not output
            else Status.COMPLETE
            if output.is_exe_success
            else Status.FAILED
        )

    elif isinstance(action, KnowledgeRetrieveAction):
        content = StepInfo()
        content.tool_name = f"知识搜索{action.action_input.query}"
        content.tool_args = json.dumps(
            {"query": action.action_input.query}, default=serialize, ensure_ascii=False
        )
        content.tool_result = output.content if output else None
        content.status = (
            Status.TODO.value
            if not output
            else Status.COMPLETE
            if output.is_exe_success
            else Status.FAILED
        )
    else:
        raise NotImplementedError

    return content


def _format_action_model_view(action: Action, action_output: ActionOutput) -> str:
    # 如果是给下游agent发消息 content应该是发送的消息
    # 如果是执行工具/检索 content应该是执行结果
    # return action_output.action_input if isinstance(action, AgentAction) else f"动作: {action_output.action}\n\n参数: {action_output.action_input}\n\n结果:\n{action_output.content}"
    return (
        None
        if isinstance(action, AgentAction)
        else f"动作: {action_output.action}\n\n参数: {action_output.action_input}\n\n结果:\n{action_output.content or None}"
    )


def _format_engine_output_span(output: Optional[ReasoningEngineOutput]) -> dict:
    if not output:
        return {}

    return {
        "done": output.done,
        "answer": output.answer,
        # "actions": [{"name": action.name, "input": action.action_input} for action in output.actions],
        "action_reason": output.action_reason,
        "model_name": output.model_name,
        "messages": [message.to_llm_message() for message in output.messages],
        "user_prompt": output.user_prompt,
        "system_prompt": output.system_prompt,
        "model_content": output.model_content,
        "model_thinking": output.model_thinking,
    }


def format_action_id(
    step_counter: int, action_idx: int, received_action_id: str = None
) -> str:
    """
    组装action_id
    <a href='https://yuque.antfin.com/derisk/yydv2v/gfy12ght43enpgx0?singleDoc#'>《action_id原理》</a>
    :param step_counter: action位于当前agent的第几轮step
    :param action_idx:  action位于当前agent当前step轮次的第几个action
    :param received_action_id: 接收到的action_id，表示从哪个action_id派生而来
    :return:
    """
    return f"{received_action_id}-{step_counter}.{action_idx}"


def check_memory_resource(
    resource: Resource
) -> bool:
    """"""
    for r in resource.sub_resources:
        if isinstance(r, MemoryResource):
            return True
    return False


def format_action_report_by_max_count(action_output: ActionOutput) -> ActionOutput:
    action_output.view = "动作重复执行达到最大次数限制。"
    action_output.content = "动作重复执行达到最大次数限制。请回顾任务目标、认真审阅动作执行记录，调整操作逻辑，避免重复执行。"
    return action_output


def reset_message_context_engineering_info(current_step_message: AgentMessage):
    if current_step_message.context is None:
        current_step_message.context = {}

    for key in ContextEngineeringKey:
        current_step_message.context.pop(key.value, None)


def _current_ms() -> int:
    return int(datetime.now().timestamp() * 1000)


class ReasoningEngineException(Exception):
    """
    推理引擎相关异常
    """

    pass


class ReasoningActionException(Exception):
    """
    ACTION执行相关异常
    """

    pass
