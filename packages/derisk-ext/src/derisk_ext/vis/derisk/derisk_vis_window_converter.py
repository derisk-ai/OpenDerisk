import json
import logging
import uuid
from collections import defaultdict
from enum import Enum
from typing import List, Optional, Dict, Union

from derisk.agent import ActionOutput
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.agent.core.reasoning.reasoning_action import AgentAction
from derisk.vis.schema import VisTaskContent, VisTextContent, VisConfirm, VisPlansContent
from derisk.vis.vis_converter import SystemVisTag
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.derisk_vis_incr_converter import DeriskVisIncrConverter
from derisk_ext.vis.derisk.tags.nex_planning_window import NexPlansContent, NexTaskContent, PlanningWindowContent
from derisk_ext.vis.derisk.tags.nex_running_window import RunningContent, RunningWindowContent
from derisk_ext.vis.gptvis.gpt_vis_converter import GptVisTagPackage

from derisk_ext.vis.vis_protocol_data import UpdateType

NONE_GOAL_PREFIX: str = "none_goal_count_"
logger = logging.getLogger(__name__)


class NexVisTagPackage(Enum):
    """System Vis Tags."""

    NexMessage = "nex-msg"
    NexStep = "nex-step"
    NexPlanningWindow = "nex-planning-window"
    NexRunningWindow = "nex-running-window"


class DeriskIncrVisWindowConverter(DeriskVisIncrConverter):
    """Incremental task window mode protocol converter.

    """

    def system_vis_tag_map(self):
        return {
            SystemVisTag.VisMessage.value: NexVisTagPackage.NexMessage.value,
            SystemVisTag.VisTool.value: NexVisTagPackage.NexStep.value,

            SystemVisTag.VisPlans.value: DrskVisTagPackage.DrskPlans.value,
            SystemVisTag.VisText.value: DrskVisTagPackage.DrskContent.value,
            SystemVisTag.VisThinking.value: DrskVisTagPackage.DrskThinking.value,
            SystemVisTag.VisTools.value: DrskVisTagPackage.DrskSteps.value,
            SystemVisTag.VisSelect.value: DrskVisTagPackage.DrskSelect.value,
            SystemVisTag.VisRefs.value: DrskVisTagPackage.DrskRefs.value,
        }

    @property
    def web_use(self) -> bool:
        return False

    @property
    def render_name(self):
        return "derisk_vis_window"

    @property
    def description(self) -> str:
        return "(视窗模式)VIS可视化布局数据转换协议"

    async def visualization(
        self,
        messages: List[GptsMessage],
        plans_map: Optional[Dict[str, GptsPlan]] = None,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[GptsPlan]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
    ):
        ### 增量模式，处理当前最小的消息或者最新的计划或者流式数据

        new_plans_view = ""
        if new_plans and len(new_plans) > 0:
            new_plans_map = {item.task_uid: item for item in new_plans}
            new_plans_view = await self._planning_vis_build(new_plans[0].conv_id, new_plans_map, senders_map)

        new_running_view = ""
        report_view = None
        chat_final = False
        if gpt_msg or stream_msg:
            if gpt_msg:
                agent_name = gpt_msg.sender_name
                sender_agent = senders_map.get(agent_name)

                conv_session_uid = gpt_msg.conv_session_id
                task_goal_id = gpt_msg.goal_id
                message_view = await self.gen_message_vis(gpt_msg)
                agent_avatar = gpt_msg.avatar
                from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
                if gpt_msg.receiver == HUMAN_ROLE:
                    report_view = await self.gen_final_report_vis(gpt_msg)
                    chat_final = True
            else:
                agent_name = stream_msg.get("sender")
                sender_agent = senders_map.get(agent_name)

                conv_session_uid = stream_msg.get("conv_session_uid")
                task_goal_id = stream_msg.get("task_goal_id")
                agent_avatar = stream_msg.get("avatar")
                message_view = await self.gen_stream_message_vis(
                    stream_msg, is_first_chunk=is_first_chunk
                )
            agent_role = None
            agent_desc = None
            if not sender_agent:
                logger.error(f"{agent_name}无法在当前会话的agent cache中获取到，请排查代码，当前展示异常！")
            else:
                agent_avatar = sender_agent.avatar
                agent_role = sender_agent.role
                agent_desc = sender_agent.desc

            ## 并行情况下搜集当前运行中Agent信息
            running_agents: List[str] = []
            # for k, v in senders_map.items():
            #     agent_state = await v.agent_state()
            #     if agent_state == Status.RUNNING:
            #         running_agents.append(v.name)

            new_running_view = await self._running_vis_build(conv_session_uid, message_view, agent_role, agent_name,
                                                             agent_desc, agent_avatar, chat_final,
                                                             running_agents=running_agents)
        if report_view:
            new_plans_view = new_plans_view + "\n" + report_view
        return json.dumps({
            "planning_window": new_plans_view,
            "running_window": new_running_view
        }, ensure_ascii=False)

    async def _planning_vis_build(self, planning_uid, plans_map: Optional[Dict[str, GptsPlan]] = None,
                                  senders_map: Optional[Dict[str, "ConversableAgent"]] = None):

        from derisk.agent import ResourceType

        plan_items_map: Dict[str, NexPlansContent] = {}
        for k, v in plans_map.items():
            task_agent = senders_map.get(v.sub_task_agent)

            if v.action == ResourceType.Agent.value:
                avatar = task_agent.avatar if task_agent else None
            elif v.action == ResourceType.Tool.value:
                avatar = None
            elif v.action == ResourceType.KnowledgePack.value:
                avatar = None
            else:
                avatar = None
            if v.sub_task_title or v.sub_task_content:
                plan_task = NexTaskContent(
                    uid=k,
                    type=UpdateType.ALL.value,
                    title=v.sub_task_title or v.sub_task_content,
                    descriptio=v.sub_task_content,
                    task_id=k,
                    status=v.state,
                    avatar=avatar,
                    model=v.agent_model,
                    agent=v.sub_task_agent,
                    task_type=v.action,  # 任务类型 是agent 还是 tool类型的 还是知识类型
                    start_time=v.created_at
                )
            else:
                plan_task = None
            if v.conv_round_id in plan_items_map:
                plan_items_map.get(v.conv_round_id).items.append(plan_task)
            else:
                plan_agent = senders_map.get(v.planning_agent)
                cost = None
                if v.created_at and v.updated_at:
                    delta = v.updated_at - v.created_at
                    cost = delta.total_seconds()
                plan_items_map[v.conv_round_id] = NexPlansContent(
                    uid=v.conv_round_id,
                    type=UpdateType.ALL.value,
                    title=v.task_round_title,
                    description=v.task_round_description,
                    model=v.planning_model,
                    agent=v.planning_agent,
                    start_time=v.created_at,
                    cost=cost,
                    avatar=plan_agent.avatar if plan_agent else None,
                    items=[plan_task] if plan_task else []
                )

        planning_window_content = PlanningWindowContent(
            uid=planning_uid,
            type=UpdateType.INCR.value,
            items=plan_items_map.values()
        )

        return self.vis_inst(DrskVisTagPackage.NexPlanningWindow.value).sync_display(
            content=planning_window_content.to_dict()
        )

    async def _all_running_vis_build(self, messages: List[GptsMessage],
                                     senders_map: Optional[Dict[str, "ConversableAgent"]] = None):

        from derisk.agent import ConversableAgent
        ## 通过消息构建 agent items
        grouped = defaultdict(list)
        for message in messages:
            grouped[message.sender_name].append(message)

        running_items: List[RunningContent] = []
        for k, v in grouped.items():

            sender_agent: ConversableAgent = senders_map.get(k)
            message_view_list = []
            for message in v:
                message_view_list.append(await self.gen_message_vis(message))

            running_items.append(RunningContent(
                uid=v[0].conv_session_id + k,
                type=UpdateType.INCR.value,
                agent_role=sender_agent.role if sender_agent else None,
                agent_name=k,
                description=sender_agent.desc if sender_agent else None,
                avatar=sender_agent.avatar if sender_agent else None,
                markdown="\n".join(message_view_list)
            ))

        running_window_content = RunningWindowContent(
            uid=messages[0].conv_session_id,
            type=UpdateType.INCR.value,
            running_agent=None,
            items=running_items
        )

        return self.vis_inst(DrskVisTagPackage.NexRunningWindow.value).sync_display(
            content=running_window_content.to_dict()
        )

    async def _running_vis_build(self, running_uid: str, message_view: str, agent_role: str, agent_name: str,
                                 agent_desc: str, agent_avatar: Optional[str] = None, chat_final: bool = False,
                                 running_agents: Optional[List[str]] = None):

        # 如果并行模式要给出所有运行的agent名称，否则直接使用当前消息发送者作为running_agent (兼容并行逻辑
        # )
        running_agent = None
        if not chat_final:
            if running_agents:
                running_agent = running_agents
            else:
                running_agent = agent_name

        running_window_content = RunningWindowContent(
            uid=running_uid,
            type=UpdateType.INCR.value,
            running_agent=running_agent,
            items=[RunningContent(
                uid=running_uid + agent_name,
                type=UpdateType.INCR.value,
                agent_role=agent_role,
                agent_name=agent_name,
                description=agent_desc,
                avatar=agent_avatar,
                markdown=message_view
            )]
        )

        return self.vis_inst(DrskVisTagPackage.NexRunningWindow.value).sync_display(
            content=running_window_content.to_dict()
        )




    async def _render_actions_view(
        self, action_reports: list[ActionOutput], message_id: str
    ) -> str:
        # AgentAction放前面 统一放在VisPlansContent里
        # 其他Action(Tool/RAG)放后面 统一放在VisStepContent里
        all_views: List[str] = []
        agent_action_contents: List[VisTaskContent] = []
        agent_action_views: List[str] = []
        other_action_views: List[str] = []
        for output in action_reports:
            if output.name == AgentAction.name:

                if not output.view:
                    content = VisTaskContent(task_uid=uuid.uuid4().hex, task_content=output.action_input,
                                             task_name=output.action_input, agent_name=output.action)
                    agent_action_contents.append(content)
                else:
                    agent_action_views.append(output.view)
            else:
                other_action_views.append(output.view or output.content)
        if action_reports[0].thoughts:
            reasoning_view = self.vis_inst(SystemVisTag.VisText.value).sync_display(content=VisTextContent(
                markdown=action_reports[0].thoughts, type="all", uid=message_id + "_reason", message_id=message_id
            ).to_dict())
            all_views.append(reasoning_view)
        if agent_action_views:
            all_views.extend(agent_action_views)
        if agent_action_contents:
            all_views.append(self.vis_inst(vis_tag=SystemVisTag.VisPlans.value).sync_display(
                content=VisPlansContent(
                    uid=message_id + "_action_agent",
                    type="all",
                    message_id=message_id + "_action_agent",
                    tasks=agent_action_contents,
                ).to_dict()
            ))
        if other_action_views:
            all_views.extend(other_action_views)

        return "\n".join(all_views)

    async def _render_confirm_action(self, message_id: str, action_reports: list[ActionOutput]) -> str:

        def _make_one_markdown(report: ActionOutput) -> str:
            return f"* 动作:{report.action_name}({report.action}),参数:{report.action_input}"

        markdown = "\n\n".join([_make_one_markdown(report)
                                for report in action_reports if report.ask_user])
        if not markdown:
            return ""

        markdown = "将执行如下动作:\n\n" + markdown + "\n\n是否确认执行?"
        return await self.vis_inst(vis_tag=SystemVisTag.VisConfirm.value).display(
            content=VisConfirm(
                uid=message_id + "_confirm",
                message_id=message_id + "_confirm",
                type="all",
                markdown=markdown,
                extra={"approval_message_id": message_id}
            ).to_dict()
        )

    async def _messages_to_agents_vis(
        self, messages: List[GptsMessage], is_last_message: bool = False
    ):
        if messages is None or len(messages) <= 0:
            return ""
        messages_view = []
        for message in messages:
            action_reports = message.action_report
            content_view = ""
            if action_reports and len(action_reports) > 0:
                content_view = await self._render_actions_view(action_reports, message.message_id)
            view_info = content_view
            if not view_info:
                view_info = message.content


            thinking = message.thinking
            vis_thinking = self.vis_inst(SystemVisTag.VisThinking.value)
            if thinking:
                vis_thinking = vis_thinking.sync_display(content=thinking)
                view_info = vis_thinking + "\n" + view_info

            messages_view.append(
                {
                    "sender": message.sender,
                    "receiver": message.receiver,
                    "avatar": message.avatar,
                    "model": message.model_name,
                    "markdown": view_info,
                    "resource": (
                        message.resource_info if message.resource_info else None
                    ),
                }
            )
        return await self.vis_inst(GptVisTagPackage.AgentMessage.value).display(
            content=messages_view
        )

    async def final_view(
        self,
        messages: List["GptsMessage"],
        plans_map: Optional[Dict[str, "GptsPlan"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs
    ):
        if not messages:
            return None
        logger.info(f"final_view:{messages[0].conv_id}")
        new_plans_view = await self._planning_vis_build(messages[0].conv_id, plans_map, senders_map)

        from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
        report_view = None

        re_messages = messages.copy()
        re_messages.reverse()
        for message in re_messages:
            if message.receiver == HUMAN_ROLE:
                final_report_vis = await self.gen_final_report_vis(message)
                if final_report_vis:
                    report_view = final_report_vis

        new_running_view = await self._all_running_vis_build(messages, senders_map)

        if report_view:
            new_plans_view = new_plans_view + "\n" + report_view

        return json.dumps({
            "planning_window": new_plans_view,
            "running_window": new_running_view
        }, ensure_ascii=False)
