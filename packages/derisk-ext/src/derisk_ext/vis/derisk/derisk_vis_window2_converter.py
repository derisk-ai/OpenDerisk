import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Union

from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.agent.core.schema import Status, AgentSpaceMode
from derisk.vis.vis_converter import SystemVisTag
from derisk_ext.vis.common.tags.derisk_work_space import WorkSpaceContent, FolderNode
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.derisk_vis_incr_converter import DeriskVisIncrConverter
from derisk_ext.vis.derisk.tags.derisk_running_window import DeriskRunningWindow, RunningWindowContent
from derisk_ext.vis.derisk.tags.derisk_space_llm import LLMSpace, LLMSpaceContent

from derisk_ext.vis.derisk.tags.drsk_content import DrskTextContent, DrskContent
from derisk_ext.vis.derisk.tags.drsk_thinking import DrskThinkingContent, DrskThinking
from derisk_ext.vis.derisk.tags.nex_planning_window import NexPlansContent, NexTaskContent, PlanningWindowContent

from derisk_ext.vis.vis_protocol_data import UpdateType

logger = logging.getLogger(__name__)


class NexVisTagPackage(Enum):
    """System Vis Tags."""
    NexMessage = "nex-msg"
    NexStep = "nex-step"


class DeriskIncrVisWindow2Converter(DeriskVisIncrConverter):
    """Incremental task window mode protocol converter.

    """

    @property
    def reuse_name(self):
        ## 复用下面转换器的前端布局
        from derisk_ext.vis.derisk.derisk_vis_window_converter import DeriskIncrVisWindowConverter
        return DeriskIncrVisWindowConverter().render_name

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
        return "derisk_vis_window2"

    @property
    def description(self) -> str:
        return "(视窗模式2)VIS可视化布局数据转换协议"

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
        if gpt_msg or stream_msg:
            if gpt_msg:
                from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
                if gpt_msg.receiver == HUMAN_ROLE:
                    report_view = await self.gen_final_report_vis(gpt_msg)

            new_running_view = await self._running_vis_build(gpt_msg=gpt_msg, stream_msg=stream_msg,
                                                             senders_map=senders_map, is_first_chunk=is_first_chunk)
        if report_view:
            new_plans_view = new_plans_view + "\n" + report_view
        if new_plans_view or new_running_view:
            return json.dumps({
                "planning_window": new_plans_view,
                "running_window": new_running_view
            }, ensure_ascii=False)
        else:
            return None

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
                    description=v.sub_task_content,
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

        from derisk_ext.vis.derisk.tags.nex_running_window import RunningContent
        agent_works: List[Union[WorkSpaceContent, RunningContent]] = []

        for k, v in grouped.items():
            sender_agent: ConversableAgent = senders_map.get(k)

            match sender_agent.agent_space:
                case AgentSpaceMode.WORK_SPACE:
                    work_items = []
                    for message in v:
                        if message.model_name:
                            work_items.append(
                                await self.gen_work_item_content(message))

                    agent_works.append(WorkSpaceContent(
                        uid=v[0].conv_session_id + k,
                        type=UpdateType.ALL.value,
                        agent_role=sender_agent.role if sender_agent else None,
                        agent_name=k,
                        description=sender_agent.desc if sender_agent else None,
                        avatar=sender_agent.avatar if sender_agent else None,
                        items=work_items
                    ))

                case _:
                    message_view_list = []
                    for message in v:
                        message_view_list.append(await self.gen_message_vis(message))
                    running_content = RunningContent(
                        uid=v[0].conv_session_id + k,
                        type=UpdateType.ALL.value,
                        agent_role=sender_agent.role if sender_agent else None,
                        agent_name=k,
                        description=sender_agent.desc if sender_agent else None,
                        avatar=sender_agent.avatar if sender_agent else None,
                        markdown="\n".join(message_view_list)
                    )
                    agent_works.append(running_content)

        return self.vis_inst(DeriskRunningWindow.vis_tag()).sync_display(
            content=RunningWindowContent(
                uid=messages[0].conv_session_id,
                type=UpdateType.INCR.value,
                running_agent=None,
                items=agent_works
            ).to_dict()
        )

    async def _running_vis_build(self, gpt_msg: Optional[GptsMessage] = None,
                                 stream_msg: Optional[Union[Dict, str]] = None,
                                 senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
                                 is_first_chunk: bool = False, ):
        agent_name = None
        running_uid = None
        if gpt_msg:
            agent_name = gpt_msg.sender_name
            running_uid = gpt_msg.conv_session_id
        if stream_msg:
            agent_name = stream_msg.get("sender")
            running_uid = stream_msg.get("conv_session_uid")

        if agent_name not in senders_map:
            logger.error("无法获取发送该消息的应用信息！「{agent_name}」")
            return None
        agent_info = senders_map.get(agent_name)
        chat_final = False
        from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
        if gpt_msg and gpt_msg.receiver == HUMAN_ROLE:
            chat_final = True

        # 如果并行模式要给出所有运行的agent名称，否则直接使用当前消息发送者作为running_agent (兼容并行逻辑
        # )
        running_agent = None
        if not chat_final:
            ## 并行情况下搜集当前运行中Agent信息
            running_agents: List[str] = []
            for k, v in senders_map.items():
                agent_state = await v.agent_state()
                if agent_state == Status.RUNNING:
                    running_agents.append(v.name)
            running_agent = running_agents

        ## 区分是否为工作分区Agent还是简单内容输出Agent
        match agent_info.agent_space:
            case AgentSpaceMode.WORK_SPACE:
                work_item = await self.gen_work_item_content(gpt_msg=gpt_msg, stream_msg=stream_msg)
                if work_item:
                    running_window_content = RunningWindowContent(
                        uid=running_uid,
                        type=UpdateType.INCR.value,
                        running_agent=running_agent,
                        items=[WorkSpaceContent(
                            uid=running_uid + agent_info.name,
                            type=UpdateType.INCR.value,
                            agent_role=agent_info.role,
                            agent_name=agent_info.name,
                            description=agent_info.desc,
                            avatar=agent_info.avatar,
                            items=[work_item]
                        )]
                    )

                    return self.vis_inst(DeriskRunningWindow.vis_tag()).sync_display(
                        content=running_window_content.to_dict()
                    )
            case _:
                from derisk_ext.vis.derisk.tags.nex_running_window import RunningContent
                message_view = ""
                if gpt_msg:
                    message_view = await self.gen_message_vis(gpt_msg)
                if stream_msg:
                    message_view = await self.gen_stream_message_vis(
                        stream_msg, is_first_chunk=is_first_chunk
                    )

                running_window_content = RunningWindowContent(
                    uid=running_uid,
                    type=UpdateType.INCR.value,
                    running_agent=running_agent,
                    items=[RunningContent(
                        uid=running_uid + agent_name,
                        type=UpdateType.INCR.value,
                        agent_role=agent_info.role,
                        agent_name=agent_info.name,
                        description=agent_info.desc,
                        avatar=agent_info.avatar,
                        markdown=message_view
                    )]
                )

                return self.vis_inst(DrskVisTagPackage.NexRunningWindow.value).sync_display(
                    content=running_window_content.to_dict()
                )

        return None

    async def gen_work_item_content(self, gpt_msg: GptsMessage, stream_msg: Optional[Union[Dict, str]] = None,
                                    is_first_chunk: bool = False, ):
        action_space_markdown = ""
        llm_space = ""
        status = Status.COMPLETE.value
        uid = None
        title = None
        conv_id = None
        goal = None
        start_time = None
        cost = 0
        # if gpt_msg or stream_msg:
        if gpt_msg:
            if gpt_msg.model_name:
                uid = gpt_msg.message_id
                conv_id = gpt_msg.conv_id
                goal = gpt_msg.current_goal
                llm_model = gpt_msg.model_name
                if gpt_msg.created_at:
                    start_time = gpt_msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                title = gpt_msg.observation

                view_info = gpt_msg.content
                action_views: List[str] = []
                if gpt_msg.action_report:
                    for action_out in gpt_msg.action_report:
                        if action_out.is_exe_success:  # noqa
                            view = action_out.view
                            action_views.append( view if view else action_out.content)
                        else:
                            status = Status.FAILED.value

                if action_views:
                    view_info = "\n".join(action_views)
                action_space_markdown = view_info

                llm_space = await self.gen_llm_space(gpt_msg)
            else:
                return None
        if stream_msg:
            uid = stream_msg.get("message_id", uuid.uuid4().hex)
            llm_space = await self.gen_stream_llm_space(stream_msg)
            status = Status.RUNNING.value
            conv_id = stream_msg.get("conv_id")
            goal = stream_msg.get("task_goal")
            llm_model = stream_msg.get("model")
            tem_start = stream_msg.get("start_time")
            title = stream_msg.get("observation")
            if tem_start:
                start_time = tem_start.strftime("%Y-%m-%d %H:%M:%S")
        markdown = ""
        if llm_space:
            markdown = llm_space
        if markdown:
            markdown = markdown + "\n" + action_space_markdown
        return FolderNode(
            uid=uid,
            type=UpdateType.INCR.value,
            conv_id=conv_id,
            topic=goal,
            title=title,
            description=None,
            status=status,
            start_time=start_time,
            cost=cost,
            markdown=markdown
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

    async def _gen_llm_space(self, message_id: str, llm_model: str, thinking: Optional[str] = None,
                             content: Optional[str] = None, tokens: int = 0, cost: int = 0,
                             start_time: Optional[Union[datetime, str]] = None, ):
        msg_markdown = ""
        if thinking:
            thinking_content = DrskThinkingContent(
                dynamic=True,
                markdown=thinking,
                uid=message_id + "_thinking",
                type="incr",
            )

            vis_thinking = DrskThinking().sync_display(
                content=thinking_content.to_dict(exclude_none=True)
            )
            msg_markdown = vis_thinking
        if content:
            llm_content = DrskTextContent(
                dynamic=True, markdown=content, uid=message_id + "_content", type="incr"
            )
            vis_content = DrskContent().sync_display(
                content=llm_content.to_dict(exclude_none=True)
            )
            msg_markdown = msg_markdown + "\n" + vis_content
        if len(msg_markdown) > 0:

            content = LLMSpaceContent(
                uid=message_id + "_llm_space",
                type="incr",
                markdown=msg_markdown,
                llm_name=llm_model,
                token_use=tokens,
                cost=cost,
                start_time=start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else None,
                firt_out_time=0,
            )
            return await self.vis(LLMSpace.vis_tag())().display(content=content.to_dict())
        else:
            return None

    async def gen_llm_space(self, message: GptsMessage) -> Optional[str]:
        cost = 0
        tokens = 0
        content = message.content
        action_contents = []
        if message.action_report:
            for action_out in message.action_report:
                action_contents.append(action_out.thoughts or action_out.content)
        if action_contents:
            content = "\n".join(action_contents)
        return await self._gen_llm_space(message_id=message.message_id, llm_model=message.model_name,
                                         thinking=message.thinking, content=content, tokens=tokens, cost=cost,
                                         start_time=message.created_at)

    async def gen_stream_llm_space(self, message: Dict) -> Optional[str]:
        thinking = message.get("thinking")
        content = message.get("content")
        llm_model = message.get("llm_model")
        start_time = message.get("start_time")
        tokens = message.get("tokens")
        cost = message.get("cost", 0)
        message_id = message.get('message_id')
        conv_id = message.get('conv_id')
        return await self._gen_llm_space(message_id=message_id, llm_model=llm_model, thinking=thinking, content=content,
                                         tokens=tokens, cost=cost, start_time=start_time)
