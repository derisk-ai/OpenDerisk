"""Plan Action."""
import datetime
import json
import logging
import time
import uuid
from typing import List, Optional, Any

from derisk._private.pydantic import BaseModel, Field, model_to_dict
from derisk.vis import SystemVisTag
from derisk.vis.schema import VisTaskContent, VisPlansContent

from derisk.agent.resource.base import AgentResource
from derisk.agent.core.action.base import Action, ActionOutput
from derisk.agent.core.agent import AgentContext
from derisk.agent.core.memory.gpts.base import GptsPlan
from derisk.agent.core.memory.gpts.gpts_memory import GptsPlansMemory, GptsMemory
from derisk.agent.core.schema import Status, ActionInferenceMetrics

logger = logging.getLogger(__name__)


class Plan(BaseModel):
    task_id: str = Field(..., description="当前任务编号", )
    parent_id: Optional[str] = Field(None, description="相关的上一个任务编号")
    agent: str = Field(..., description="当前任务可交给那个代理、工具完成，根据定义选择，不要自行构造")
    task_goal: str = Field(
        ...,
        description="您下一步的指令。不要涉及复杂的多步骤指令。保持您的指令原子性，明确要求“做什么”和“怎么做”。如果您认为问题已解决，请自行回复摘要。如果您认为问题已解决，请自行回复摘要。如果您认为问题已解决，请自行回复摘要。",
    )
    slots: Optional[dict] = Field(
        None,
        description="关键参数信息(结合‘代理'、‘工具’定义的需求和已知消息，搜集各种关键参数，如:目标、时间、位置等出现的有真实实际值的参数，确保后续‘agent’或‘工具’能正确运行)",
    )
    assertion: Optional[str] = Field(None, description="目标是否符合预期和完成的的判断规则和标准", )

    def to_dict(self):
        """Convert the object to a dictionary."""
        return model_to_dict(self)

class PlanningOutput(BaseModel):
    """Planning output of the planner agent model"""
    plans_brief_description: str = Field(
        ..., description="简短介绍当前阶段要执行的动作，不超过10个字"
    )
    analysis: Optional[Any] = Field(
        None,
        description="您对上一阶段执行器代码执行结果的分析，并详细论证‘做了什么’和‘可以得出什么结论’以及‘当前阶段状态判定和plans拆解依据’。如果是第一步，简单解释下你整体的思路。",
    )
    plans: list[Plan] = Field(
        [], description="当前阶段的新动作目标（需对比历史动作确保不重复）"
    )
    status: str = Field(
        None,
        description="planing (仅当需要执行下一步动作时) | done (仅当任务可终结时) | abort (仅当任务异常或无法推进或需要用户提供更多信息时)",
    )

    def to_dict(self):
        """Convert the object to a dictionary."""
        return model_to_dict(self)

class PlanningAction(Action[PlanningOutput]):
    """Plan action class."""
    name = "Planning"
    def __init__(self, **kwargs):
        """Create a plan action."""
        super().__init__()
        self.action_view_tag: str = SystemVisTag.VisPlans.value

    @property
    def out_model_type(self):
        """Return the output model type."""
        return PlanningOutput

    @property
    def ai_out_schema_json(self) -> Optional[str]:
        return """{
            "analysis": "您对上一阶段执行器代码执行结果的分析，并详细论证‘做了什么’和‘可以得出什么结论’以及‘当前阶段状态判定和plans拆解依据’。如果是第一步，简单解释下你整体的思路。",
            "plans": [
                {
                    "task_id": "当前任务编号，确保唯一",
                    "parent_id"?: "相关的上一个任务编号",
                    "task_goal": "您下一步的指令。不要涉及复杂的多步骤指令。保持您的指令原子性，明确要求“做什么”和“怎么做”。如果您认为问题已解决，请自行回复摘要。注意结合历史记录不要重复",
                    "agent": "当前任务可交给那个代理或工具完成，根据定义给出范围选择，不要自行构造",
                    "slots"?: {
                        "参数名": "参数值",
                    }
                }
            ],
            "plans_brief_description": "简短介绍当前阶段要执行的动作，不超过10个字"
        }"""

    async def run(
            self,
            ai_message: str = None,
            resource: Optional[AgentResource] = None,
            rely_action_out: Optional[ActionOutput] = None,
            need_vis_render: bool = True,
            **kwargs,
    ) -> ActionOutput:
        """Run the plan action."""
        metrics = ActionInferenceMetrics()
        start_time = datetime.datetime.now()
        metrics.start_time_ms = time.time_ns() // 1_000_000
        try:
            context: AgentContext = kwargs["context"]
            gpts_memory: GptsMemory = kwargs["gpts_memory"]
            planning_agent = kwargs.get("planning_agent")
            planning_model = kwargs.get("planning_model")
            planning_round = kwargs.get("round", 0)
            retry_times = kwargs.get("retry_times", 0)
            conv_round_id = kwargs.get("round_id")
            init_uids = kwargs.get("init_uids", [])
            self._render = kwargs.get("render_protocol") or self._render
            planning_out: PlanningOutput = self._input_convert(
                ai_message, PlanningOutput
            )

            tasks: List[VisTaskContent] = []

            plans: List[GptsPlan] = []
            for item in planning_out.plans:
                task_uid = None
                plan = None
                if init_uids and len(init_uids) > 0:
                    task_uid = init_uids.pop()
                    ## 如果存在初始化uid代表有一些需要覆盖的plan,
                    old_plan = await gpts_memory.get_plan(conv_id=context.conv_id, task_uid=task_uid)
                    if old_plan:
                        old_plan.sub_task_id = item.task_id
                        old_plan.sub_task_title = item.task_goal
                        old_plan.sub_task_content = json.dumps(item.slots)
                        old_plan.task_parent = item.parent_id
                        old_plan.sub_task_agent = item.agent
                        old_plan.retry_times = retry_times
                        old_plan.planning_agent = planning_agent
                        old_plan.planning_model = planning_model
                        old_plan.task_round_title = planning_out.plans_brief_description
                        old_plan.task_round_description = planning_out.analysis
                        old_plan.state = Status.TODO.value
                        plan = old_plan
                if not plan:
                    plan = GptsPlan(
                        conv_id=context.conv_id,
                        conv_session_id=context.conv_session_id,
                        task_uid=uuid.uuid4().hex,
                        sub_task_num=0,
                        sub_task_id=item.task_id,
                        sub_task_title=item.task_goal,
                        sub_task_content=json.dumps(item.slots),
                        task_parent=item.parent_id,
                        conv_round=planning_round,
                        conv_round_id=conv_round_id,
                        resource_name=None,
                        max_retry_times=context.max_retry_round,
                        sub_task_agent=item.agent,
                        retry_times=retry_times,
                        planning_agent=planning_agent,
                        planning_model=planning_model,
                        task_round_title=planning_out.plans_brief_description,
                        task_round_description=planning_out.analysis,
                        state=Status.TODO.value,
                    )
                plans.append(plan)
                tasks.append(
                    VisTaskContent(
                        task_uid=task_uid,
                        task_id=str(item.task_id),
                        task_title=item.task_goal,
                        task_name=item.task_goal,
                        task_content=json.dumps(item.slots),
                        task_parent=str(item.parent_id),
                        task_link=None,
                        agent_id=item.agent,
                        agent_name=item.agent,
                        agent_link="",
                        avatar="",
                    )
                )
            await gpts_memory.append_plans(conv_id=context.conv_id, plans=plans)
            drsk_plan_content = VisPlansContent(
                uid=uuid.uuid4().hex,
                type="all",
                round_title=planning_out.plans_brief_description,
                round_description=planning_out.analysis,
                tasks=tasks
            )

            if self.render_protocol:
                view = await self.render_protocol.display(
                    content=drsk_plan_content.to_dict()
                )
            elif need_vis_render:
                raise NotImplementedError("The render_protocol should be implemented.")
            else:
                view = None

            metrics.end_time_ms = time.time_ns() // 1_000_000
            metrics.result_tokens = 0
            cost_ms = metrics.end_time_ms - metrics.start_time_ms
            metrics.cost_seconds = round(cost_ms / 1000, 2)
            return ActionOutput(
                action_id=conv_round_id or self.action_uid,
                name=self.name,
                action="任务规划",
                action_name=planning_out.plans_brief_description,
                is_exe_success=True,
                start_time=start_time,
                metrics=metrics,
                state=Status.COMPLETE.value,
                content=json.dumps(planning_out.to_dict(), ensure_ascii=False),
                view=view,
            )
        except Exception as e:
            logger.exception("React Plan Action Run Failed！")
            return ActionOutput(
                action_id=self.action_uid,
                name=self.name,
                action="任务规划",
                action_name=f"{str(e)}",
                state=Status.FAILED.value,
                is_exe_success=False, content=f"React Plan action run failed!{str(e)}"
            )
