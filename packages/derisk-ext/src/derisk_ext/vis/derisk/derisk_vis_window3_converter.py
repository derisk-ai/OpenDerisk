import json
import logging
from enum import Enum
from typing import List, Optional, Dict, Union

from derisk.agent import ActionOutput, ConversableAgent, BlankAction
from derisk.agent.core.action.report_action import ReportAction
from derisk.agent.core.file_system.file_tree import TreeManager, TreeNodeData
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.agent.core.memory.gpts.gpts_memory import AgentTaskContent, AgentTaskType
from derisk.agent.core.plan.planning_action import PlanningAction

from derisk.agent.core.reasoning.reasoning_action import AgentAction, KnowledgeRetrieveAction
from derisk.agent.core.schema import Status
from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
from derisk.agent.expand.actions.code_action import CodeAction
from derisk.agent.expand.actions.tool_action import ToolAction
from derisk.agent.expand.react_agent.react_parser import CONST_LLMOUT_THOUGHT, CONST_LLMOUT_TITLE, CONST_LLMOUT_TOOLS
from derisk.vis.vis_converter import SystemVisTag
from derisk_ext.agent.actions.ant_tool_action import AntToolAction
from derisk_ext.agent.actions.code_action import DeriskCodeAction
from derisk_ext.agent.actions.monitor_action import AntMonitorAction

from derisk_ext.vis.common.tags.derisk_attach import DeriskAttach

from derisk_ext.vis.common.tags.derisk_plan import AgentPlan, AgentPlanItem
from derisk_ext.vis.common.tags.derisk_planning_space import PlanningSpaceContent, PlanningSpace
from derisk_ext.vis.common.tags.derisk_thinking import DeriskThinking, DrskThinkingContent
from derisk_ext.vis.common.tags.derisk_tool import ToolSpace
from derisk_ext.vis.common.tags.derisk_work_space import WorkSpaceContent, WorkSpace, FolderNode
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.derisk_vis_incr_converter import DeriskVisIncrConverter
from derisk_ext.vis.derisk.tags.derisk_agent_folder import AgentFolder
from derisk_ext.vis.derisk.tags.derisk_space_llm import LLMSpace, LLMSpaceContent
from derisk_ext.vis.derisk.tags.drsk_content import DrskTextContent, DrskContent

from derisk_ext.vis.vis_protocol_data import UpdateType

logger = logging.getLogger(__name__)


# ╔══════════════════════════════════════════════════════════════════════════════
# ║ 🚨🚨🚨 重要逻辑提示：请勿随意修改以下代码！ 🚨🚨🚨
# ╟──────────────────────────────────────────────────────────────────────────────
# ║ 下面注释逻辑提示了VIS增量传输核心规则直接关系到
# ║   • 可视化展示
# ║   • 数据传输
# ║   • 页面布局和数据转换逻辑
# ║
# ║ VIS数据增量传输协议：
# ║   1. type=INCR得情况下，组件按UID匹配，数据内容中markdown和items做增量追加, 其他字段如果有值做替换，无值不变
# ║   2. type=ALL的模式下, 所有字段 都完全替换 包括如果是空也替换为空
# ║
# ║ 💡 小贴士：基于上述逻辑合理进行VIS组件动态更新数据的协议转换
# ╚══════════════════════════════════════════════════════════════════════════════

class NexVisTagPackage(Enum):
    """System Vis Tags."""

    NexMessage = "nex-msg"
    NexStep = "nex-step"
    NexPlanningWindow = "nex-planning-window"
    NexRunningWindow = "nex-running-window"


# task_type ["tool","report","knowledge","code", "monitor","agent","plan"]
ACTION_TASK_MAP = {
    BlankAction.name: "report",
    ReportAction.name: "report",
    KnowledgeRetrieveAction.name: "knowledge",
    PlanningAction.name: "plan",
    AgentAction.name: "agent",
    AntMonitorAction.name: "monitor",
    CodeAction.name: "code",
    DeriskCodeAction.name: "code",
    ToolAction.name: "tool",
    AntToolAction.name: "tool",
    # 有展示分类需求的再这里进行分类处理
}


from derisk._private.config import Config

class DeriskIncrVisWindow3Converter(DeriskVisIncrConverter):
    """Incremental task window mode protocol converter.
    """
    
    def __init__(self, paths: Optional[str] = None, **kwargs):
        super().__init__(paths, **kwargs)
        # self._drsk_web_url = Config().DERISK_WEB_URL
        self._drsk_web_url = ""

    def system_vis_tag_map(self):
        return {
            SystemVisTag.VisTool.value: ToolSpace.vis_tag(),
            SystemVisTag.VisText.value: DrskVisTagPackage.DrskContent.value,
            SystemVisTag.VisThinking.value: DrskVisTagPackage.DeriskThinking.value,
            SystemVisTag.VisSelect.value: DrskVisTagPackage.DrskSelect.value,
            SystemVisTag.VisRefs.value: DrskVisTagPackage.DrskRefs.value,
            SystemVisTag.VisConfirm.value: DrskVisTagPackage.DrskConfirm.value,
            SystemVisTag.VisPlans.value: DrskVisTagPackage.DrskPlans.value,
            SystemVisTag.VisReport.value: DrskVisTagPackage.NexReport.value,
            SystemVisTag.VisAttach.value: DeriskAttach.vis_tag(),
        }

    @property
    def web_use(self) -> bool:
        return True

    @property
    def reuse_name(self):
        ## 复用下面转换器的前端布局
        from derisk_ext.vis.derisk.derisk_vis_window_converter import DeriskIncrVisWindowConverter
        return DeriskIncrVisWindowConverter().render_name

    @property
    def render_name(self):
        return "vis_window3"

    @property
    def description(self) -> str:
        return "文件系统可视化布局"

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
        main_agent_name: Optional[str] = None,
        is_first_push: bool = False,
        **kwargs
    ):

        ## 并行情况下搜集当前运行中Agent信息
        running_agents: List[str] = []
        for k, v in senders_map.items():
            agent_state = await v.agent_state()
            if agent_state == Status.RUNNING:
                running_agents.append(v.name)

        task_manager: TreeManager = kwargs.get("task_manager")
        try:
            planning_vis = ""
            ## 规划空间更新
            new_task_nodes = kwargs.get('new_task_nodes')
            ## 规划空间内容增量更新
            if new_task_nodes or stream_msg:
                planning_vis = await self._planning_vis_build(messages=messages, stream_msg=stream_msg,
                                                              new_task_nodes=new_task_nodes,
                                                              is_first_chunk=is_first_chunk, senders_map=senders_map,
                                                              main_agent_name=main_agent_name,
                                                              actions_map=kwargs.get("actions_map"),
                                                              task_manager=task_manager)

            ## 工作空间增量更新
            work_vis = ""
            if gpt_msg or stream_msg:
                work_vis = await self._running_vis_build(gpt_msg=gpt_msg, stream_msg=stream_msg,
                                                         is_first_push=is_first_push,
                                                         is_first_chunk=is_first_chunk, senders_map=senders_map,
                                                         main_agent_name=main_agent_name,
                                                         running_agents=running_agents)

            planning_window = planning_vis
            if gpt_msg:
                foot_vis = await self._footer_vis_build(gpt_msg)
                if foot_vis:
                    planning_window = planning_window + "\n" + foot_vis
            if planning_vis or work_vis:
                return json.dumps({
                    "planning_window": planning_window,
                    "running_window": work_vis
                }, ensure_ascii=False)
            else:
                return None
        except Exception as e:
            logger.exception("vis_window2异常!")
            return None

    async def _gen_plan_items(self, gpt_msg: Optional[GptsMessage] = None,
                              stream_msg: Optional[Union[Dict, str]] = None,
                              layer_count: int = 0, senders_map: Optional[Dict[str, "ConversableAgent"]] = None) -> \
        Optional[str]:
        plan_tasks_vis = []
        thought = None
        title = None
        tools = None
        if gpt_msg:
            action_outs: Optional[List[ActionOutput]] = gpt_msg.action_report
            agent = senders_map.get(gpt_msg.sender_name) if senders_map else None
            message_id = gpt_msg.message_id
            if agent and agent.agent_parser:
                thought = agent.agent_parser.parse_streaming_xml(gpt_msg.content, CONST_LLMOUT_THOUGHT)
                title = agent.agent_parser.parse_streaming_xml(gpt_msg.content, CONST_LLMOUT_TITLE)

        elif stream_msg:
            prev_content = stream_msg.get("prev_content")
            content = stream_msg.get("content")
            sender_name = stream_msg.get("sender_name")
            message_id = stream_msg.get("message_id")
            action_outs: Optional[List[ActionOutput]] = stream_msg.get("action_report")
            agent = senders_map.get(sender_name) if senders_map else None
            # if action_outs and not any(
            #     item for item in action_outs if item.name in [BlankAction.name, ReportAction.name]):
            #     final_answer = stream_msg.get("content")
            if agent and agent.agent_parser and prev_content:
                title = agent.agent_parser.parse_streaming_xml(prev_content, CONST_LLMOUT_TITLE)
                thought = agent.agent_parser.parse_streaming_xml(prev_content, CONST_LLMOUT_THOUGHT)
                tools = agent.agent_parser.parse_streaming_xml(prev_content, CONST_LLMOUT_TOOLS)
                # 开始输出别的就不在获取title了 TODO
                if tools or thought:
                    title = None
            ## 流式输出过程，规划内容不展示工具输出过程(也可以考虑展示为Loading待实现)
            # if not action_outs and tools:
            #     return None
        else:
            return None
        report_content = None
        if title or thought:
            step_thought = ""
            if title:
                step_thought += f"{title}"
            # if thought:
            #     step_thought += f"{thought}\n"
            if step_thought:
                report_content = DrskTextContent(
                    dynamic=False, markdown=step_thought, uid=f"{message_id}_'step_thought'", type="all"
                )
                plan_tasks_vis.append(DrskContent().sync_display(
                    content=report_content.to_dict(exclude_none=True)
                ))

        ## 行动区域，每个action out为一个单独文件
        if action_outs:
            for action_out in action_outs:
                ## 规划的Agent转发任务已经再任务中通过空间挂载，不需要Action展示
                if action_out.name == AgentAction.name :
                    continue
                plan_tasks_vis.append(
                    self._act_out_2_plan(action_out, layer_count))

        return "\n".join(plan_tasks_vis)

    def _unpack_agent(self, parent_agent: ConversableAgent, parent: FolderNode):
        details: List[FolderNode] = []
        if hasattr(parent_agent, 'agents'):
            for item in parent_agent.agents:
                detail_folder: FolderNode = FolderNode(
                    uid=f"{parent_agent.agent_context.conv_session_id}_{item.agent_context.agent_app_code}",
                    type=UpdateType.INCR.value,
                    item_type='folder',
                    title=item.name,
                    description=item.desc,
                    avatar=item.avatar,
                    items=[]
                )
                details.append(detail_folder)
                if item.is_team:
                    self._unpack_agent(item, detail_folder)
            parent.items.extend(details)

    async def _gen_plan_tree_by_task(self, task_manager: TreeManager, current_task: TreeNodeData[AgentTaskContent],
                                     leaf_vis: str, is_nest: bool = False,
                                     senders_map: Optional[Dict[str, "ConversableAgent"]] = None) -> AgentPlanItem:

        agent = None
        if senders_map and current_task.content.agent_name:
            agent = senders_map.get(current_task.content.agent_name)

        item_type = AgentTaskType.PLAN.value
        if current_task.content.task_type == AgentTaskType.STAGE.value:
            item_type = AgentTaskType.STAGE.value
        elif current_task.content.task_type == AgentTaskType.AGENT.value:
            item_type = AgentTaskType.AGENT.value

        current_item = AgentPlanItem(
            uid=current_task.node_id,
            type=UpdateType.INCR.value,
            title=current_task.name,
            description=current_task.description,
            item_type=item_type,
            agent_role=agent.role if agent else None,
            agent_name=agent.name if agent else None,
            agent_avatar=agent.avatar if agent else None,
            status=current_task.state,
            start_time=current_task.created_at,
            layer_count=current_task.layer_count,
            cost=current_task.content.cost,
            markdown=leaf_vis
        )

        current_task_vis = self.vis_inst(AgentPlan.vis_tag()).sync_display(content=current_item.to_dict())
        parent_task = task_manager.get_node(current_task.parent_id)
        if parent_task and parent_task.node_id != current_task.node_id:
            return await self._gen_plan_tree_by_task(task_manager, parent_task, current_task_vis, True, senders_map)
        else:
            return current_item

    async def _footer_vis_build(self, gpt_msg: GptsMessage):
        plans_vis = []
        foot_vis = None
        confirm_vis = None
        # 任务更新(属于规划任务的消息都需要更新规划)
        if gpt_msg:
            if gpt_msg.action_report:
                confirm_vis = await self._render_confirm_action(gpt_msg.message_id, gpt_msg.action_report)

            if gpt_msg.receiver == HUMAN_ROLE:
                foot_vis = ""

                notice_view = await self.gen_one_final_notice_vis(gpt_msg)
                if notice_view:
                    foot_vis = foot_vis + "\n" + notice_view
        ## 规划空间的footer信息
        if foot_vis:
            plans_vis.append(foot_vis)

        if confirm_vis:
            plans_vis.append(confirm_vis)

        return "\n".join(plans_vis)

    async def _planning_vis_build(self,
                                  messages: Optional[List[GptsMessage]] = None,
                                  stream_msg: Optional[Union[Dict, str]] = None,
                                  new_task_nodes: Optional[List[TreeNodeData[AgentTaskContent]]] = None,
                                  is_first_chunk: bool = False,
                                  main_agent_name: Optional[str] = None,
                                  actions_map: Optional[Dict[str, 'ActionOutput']] = None,
                                  senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
                                  task_manager: Optional[TreeManager] = None) -> Optional[str]:
        if main_agent_name not in senders_map:
            logger.warning(f"main_agent_name '{main_agent_name}' not found in senders_map：{senders_map}")
        main_agent = senders_map[main_agent_name]
        conv_id: str = main_agent.agent_context.conv_id

        task_items_vis = []
        if stream_msg:
            goal_id = stream_msg.get("goal_id")

            current_task = None
            if goal_id:
                current_task = task_manager.get_node(goal_id)
            if current_task:
                leaf_item_vis = await self._gen_plan_items(stream_msg=stream_msg,
                                                           layer_count=current_task.layer_count + 1,
                                                           senders_map=senders_map)
                if not leaf_item_vis:
                    return None
                task_item: AgentPlanItem = await self._gen_plan_tree_by_task(task_manager, current_task,
                                                                             leaf_item_vis, senders_map=senders_map)
                task_items_vis.append(self.vis_inst(AgentPlan.vis_tag()).sync_display(content=task_item.to_dict()))

        if new_task_nodes:
            messages_map = {item.message_id: item for item in messages}
            for task_node in new_task_nodes:
                gpt_msg = messages_map.get(task_node.content.message_id)
                if gpt_msg:
                    logger.info(f"找到了新节点的消息{task_node.content.message_id}!")

                    # 修复：找到父节点，将新节点的内容作为子节点挂载到父节点下
                    parent_task = task_manager.get_node(task_node.parent_id)
                    if parent_task and parent_task.node_id != task_node.node_id:
                        leaf_item_vis = await self._gen_plan_items(gpt_msg=gpt_msg,
                                                                   layer_count=task_node.layer_count + 1,
                                                                   senders_map=senders_map)
                        if leaf_item_vis:
                            # 将新节点的内容挂载到父节点下
                            task_item: AgentPlanItem = await self._gen_plan_tree_by_task(task_manager, parent_task,
                                                                                         leaf_item_vis,
                                                                                         senders_map=senders_map)
                            task_items_vis.append(
                                self.vis_inst(AgentPlan.vis_tag()).sync_display(content=task_item.to_dict()))
                else:
                    # 将新节点的内容挂载到父节点下
                    task_item: AgentPlanItem = await self._gen_plan_tree_by_task(task_manager, task_node,
                                                                                 "",
                                                                                 senders_map=senders_map)
                    task_items_vis.append(
                        self.vis_inst(AgentPlan.vis_tag()).sync_display(content=task_item.to_dict()))

                # leaf_item_vis = await self._gen_plan_items(gpt_msg=gpt_msg,
                #                                            layer_count=task_node.layer_count + 1,
                #                                            senders_map=senders_map)
                # if not leaf_item_vis:
                #     continue
                # task_item: AgentPlanItem = await self._gen_plan_tree_by_task(task_manager, task_node,
                #                                                              leaf_item_vis, senders_map=senders_map)
                # task_items_vis.append(self.vis_inst(AgentPlan.vis_tag()).sync_display(content=task_item.to_dict()))

        if task_items_vis:
            planning_window_content = PlanningSpaceContent(
                uid=f'{conv_id}_planning',
                type=UpdateType.INCR.value,
                agent_role=main_agent.role,
                agent_name=main_agent_name,
                title=None,
                description=None,
                avatar=main_agent.avatar,
                markdown="\n".join(task_items_vis)
            )
            return self.vis_inst(PlanningSpace.vis_tag()).sync_display(
                content=planning_window_content.to_dict()
            )
        else:
            return None

    async def gen_work_item(self,
                            gpt_msg: Optional[GptsMessage] = None,
                            stream_msg: Optional[Union[Dict, str]] = None,
                            is_first_chunk: bool = False,
                            senders_map: Optional[Dict] = None
                            ) -> Optional[List[FolderNode]]:
        status = Status.COMPLETE.value
        conv_id = None
        goal = None
        cost = 0

        ## 任务项，区分多Action和单Action， 如果多Action进行文件拆分，单Action模型和Action合并到一个文件

        result: List[FolderNode] = []
        update_type = UpdateType.INCR.value
        thinkin_expand: bool = True
        thinking: Optional[str] = None
        content: Optional[str] = None

        is_strem: bool = False
        if gpt_msg:
            if not gpt_msg.action_report:
                return None
            sender_name = gpt_msg.sender_name
            action_outs: Optional[List[ActionOutput]] = gpt_msg.action_report

            message_id = gpt_msg.message_id
            start_time = gpt_msg.created_at
            llm_model = gpt_msg.model_name
            llm_avatar = gpt_msg.model_name
            thinking = gpt_msg.thinking
            content = gpt_msg.content
            thinkin_expand = False
            total_tokens = (gpt_msg.metrics.llm_metrics.total_tokens if gpt_msg.metrics and gpt_msg.metrics.llm_metrics else 0) or 0
            tokens = (gpt_msg.metrics.llm_metrics.completion_tokens if gpt_msg.metrics and gpt_msg.metrics.llm_metrics else 0) or 0
            update_type = UpdateType.ALL.value
        elif stream_msg:
            sender_name = stream_msg.get('sender')
            action_outs: Optional[List[ActionOutput]] = stream_msg.get("action_report")

            message_id = stream_msg.get('message_id')
            start_time = stream_msg.get("start_time")
            llm_model = stream_msg.get("model")
            llm_avatar = stream_msg.get("llm_avatar")
            tokens = stream_msg.get("tokens", 0) or 0
            total_tokens = stream_msg.get("total_tokens", 0) or 0
            thinking = stream_msg.get("thinking")
            content = stream_msg.get("content")
            if content:
                thinkin_expand = False
            if is_first_chunk:
                update_type = UpdateType.ALL.value
            else:
                update_type = UpdateType.INCR.value
        else:
            return None

        sender: ConversableAgent = senders_map.get(sender_name)
        if not sender:
            return None
        ## 模型数据文件
        llm_content_md = ""
        if thinking:
            thinking_content = DrskThinkingContent(markdown=thinking, uid=message_id + "_thinking", type=update_type,
                                                   expand=thinkin_expand)
            vis_thinking = DeriskThinking().sync_display(content=thinking_content.to_dict(exclude_none=True))
            llm_content_md = llm_content_md + "\n" + vis_thinking

            if content:
                llm_content = DrskTextContent(markdown=content, uid=message_id + "_content", type=update_type)
                vis_content = DrskContent().sync_display(content=llm_content.to_dict(exclude_none=True))
                llm_content_md = llm_content_md + "\n" + vis_content

        if llm_content_md:
            # Handle potential None values for metrics
            cost_val = 0
            speed_val = 0.0
            
            if gpt_msg and gpt_msg.metrics and gpt_msg.metrics.llm_metrics:
                if gpt_msg.metrics.llm_metrics.end_time_ms and gpt_msg.metrics.start_time_ms:
                     cost_val = (gpt_msg.metrics.llm_metrics.end_time_ms - gpt_msg.metrics.start_time_ms) // 1000
                if gpt_msg.metrics.llm_metrics.speed_per_second is not None:
                     speed_val = float(gpt_msg.metrics.llm_metrics.speed_per_second)

            llm_vis_md = LLMSpace().sync_display(content=LLMSpaceContent(
                uid=message_id + "_llm_",
                type=UpdateType.INCR.value,
                markdown=llm_content_md,
                llm_model=llm_model,
                llm_avatar=llm_avatar,
                token_use=tokens or 0,
                total_tokens=total_tokens or 0,
                start_time=start_time,
                cost=cost_val,
                token_speed=speed_val,
                link_url=f"{self._drsk_web_url}/api/derisk/thinking/detail?message_id={message_id}"

            ).to_dict())

            result.append(FolderNode(
                uid=message_id + "_task_llm",
                type=UpdateType.INCR.value,
                item_type="file",
                conv_id=conv_id,
                tags=[goal] if goal else [],
                path=f"{sender.agent_context.conv_session_id}_{sender.agent_context.agent_app_code}",
                title=llm_model,
                avatar=llm_avatar,
                description=None,
                status=status,
                task_type="llm",
                start_time=start_time,
                cost=cost,
                markdown=llm_vis_md
            ))

        ## 行动区域，每个action out为一个单独文件
        if action_outs:
            for action_out in action_outs:
                if action_out.name == AgentAction.name or action_out.name == PlanningAction.name:
                    continue
                result.append(FolderNode(
                    uid=action_out.action_id,
                    type=UpdateType.INCR.value if action_out.stream else UpdateType.ALL.value,
                    item_type="file",
                    conv_id=conv_id,
                    tags=[goal] if goal else [],
                    path=f"{sender.agent_context.conv_session_id}_{sender.agent_context.agent_app_code}",
                    title=action_out.action_name or action_out.action,
                    description=action_out.thoughts or str(action_out.action_input),
                    status=action_out.state,
                    task_type=ACTION_TASK_MAP[action_out.name] if action_out.name in ACTION_TASK_MAP else "tool",
                    start_time=action_out.start_time if action_out.start_time else None,
                    cost=action_out.metrics.cost_seconds if action_out.metrics else 0,
                    markdown=action_out.view or action_out.content
                ))

        return result

    async def _build_agent_folder(self, main_agent: Optional["ConversableAgent"], ) -> FolderNode:
        main_agent_folder = FolderNode(
            uid=f"{main_agent.agent_context.conv_session_id}_{main_agent.agent_context.agent_app_code}",
            type=UpdateType.INCR.value,
            item_type='folder',
            title=main_agent.name,
            description=main_agent.desc,
            avatar=main_agent.avatar,
            items=[],
        )
        self._unpack_agent(main_agent, main_agent_folder)
        return main_agent_folder

    async def _running_vis_build(self,
                                 gpt_msg: Optional[GptsMessage] = None,
                                 stream_msg: Optional[Union[Dict, str]] = None,
                                 is_first_chunk: bool = False,
                                 is_first_push: bool = False,
                                 senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
                                 main_agent_name: Optional[str] = None,
                                 running_agents: Optional[List[str]] = None,
                                 ):
        main_agent = senders_map[main_agent_name]
        conv_session_id = main_agent.agent_context.conv_session_id
        if gpt_msg and not gpt_msg.action_report and not is_first_push:
            return None

        work_items = await self.gen_work_item(gpt_msg=gpt_msg, stream_msg=stream_msg,
                                              is_first_chunk=is_first_chunk, senders_map=senders_map)
        main_agent_folder = None
        if is_first_push:
            logger.info("构建vis_window2空间，进行首次资源管理器刷新!")
            main_agent_folder = await self._build_agent_folder(main_agent=main_agent)

        work_space_content = None
        if work_items and main_agent_folder:
            work_space_content = WorkSpaceContent(
                uid=conv_session_id,
                type=UpdateType.INCR.value,
                running_agents=running_agents,
                explorer=self.vis_inst(AgentFolder.vis_tag()).sync_display(content=main_agent_folder.to_dict()),
                items=work_items
            )
        elif work_items:
            work_space_content = WorkSpaceContent(
                uid=conv_session_id,
                type=UpdateType.INCR.value,
                items=work_items
            )
        elif main_agent_folder:
            work_space_content = WorkSpaceContent(
                uid=conv_session_id,
                type=UpdateType.INCR.value,
                running_agents=running_agents,
                explorer=self.vis_inst(AgentFolder.vis_tag()).sync_display(content=main_agent_folder.to_dict()),
                items=[]
            )

        if work_space_content:
            return self.vis_inst(WorkSpace.vis_tag()).sync_display(
                content=work_space_content.to_dict()
            )
        else:
            return None

    def _act_out_2_plan(self, action_out: ActionOutput, layer_count: int):
        return self.vis_inst(AgentPlan.vis_tag()).sync_display(content=AgentPlanItem(
            uid=action_out.action_id,
            type=UpdateType.INCR.value,
            item_type="task",
            task_type=ACTION_TASK_MAP[action_out.name] if action_out.name in ACTION_TASK_MAP else "tool",
            title=action_out.action,
            description=str(action_out.action_input) if action_out.action_input else None,
            status=action_out.state,
            start_time=action_out.start_time,
            layer_count=layer_count,
            markdown=action_out.simple_view or action_out.view or action_out.content if action_out.terminate else None,
            cost=action_out.metrics.cost_seconds if action_out.metrics else 0,
        ).to_dict())

    def _unpack_task_space(self, task_space: TreeNodeData[AgentTaskContent], task_manager: TreeManager,
                           actions_map: Dict[str, 'ActionOutput'],
                           messages_map: Optional[Dict[str, GptsMessage]] = None,
                           agent_map: Optional[Dict[str, "ConversableAgent"]] = None) -> AgentPlanItem:
        child_vis = []

        ## 构建当前任务的自节点数据，需要关注task和plan的顺序
        ### 使用messages字段顺序，message要么属于child的任务id，要么关联了当前的action信息
        for child_id in task_space.child_ids:
            item: TreeNodeData[AgentTaskContent] = task_manager.get_node(child_id)

            if item and item.child_ids:
                agent_plan_item = self._unpack_task_space(item, task_manager, actions_map, messages_map, agent_map)
                child_vis.append(self.vis_inst(AgentPlan.vis_tag()).sync_display(content=agent_plan_item.to_dict()))
            else:
                if messages_map and agent_map:
                    message = messages_map.get(item.content.message_id)
                    if message:
                        agent = agent_map.get(message.sender_name)
                        if agent and agent.agent_parser:
                            thought = agent.agent_parser.parse_streaming_xml(message.content, CONST_LLMOUT_THOUGHT)
                            title = agent.agent_parser.parse_streaming_xml(message.content, CONST_LLMOUT_TITLE)
                            if title:
                                report_content = DrskTextContent(
                                    dynamic=False, markdown=title, uid=f"{message.message_id}_'step_thought'",
                                    type="all"
                                )

                                child_vis.append(DrskContent().sync_display(
                                    content=report_content.to_dict(exclude_none=True)
                                ))
                            # if thought:
                            #     child_vis.append(thought)
                        if message.action_report:
                            for action_out in message.action_report:
                                ### 规划的Agent转发任务已经再任务中通过空间挂载，不需要Action展示
                                if action_out.name == AgentAction.name:
                                    continue
                                else:
                                    child_vis.append(self._act_out_2_plan(action_out, task_space.layer_count + 1))

        agent = agent_map.get(task_space.content.agent_name)
        return AgentPlanItem(
            uid=task_space.node_id,
            type=UpdateType.INCR.value,
            item_type=AgentTaskType.PLAN.value,  # task_space.content.task_type
            title=task_space.name,
            description=task_space.description,
            status=task_space.state,
            agent_name=agent.name if agent else None,
            agent_avatar=agent.avatar if agent else None,
            start_time=task_space.created_at,
            layer_count=task_space.layer_count,
            cost=task_space.content.cost,
            markdown="\n".join(child_vis)
        )

    async def _planning_vis_all(self,
                                messages_map: Dict[str, 'GptsMessage'],
                                actions_map: Dict[str, 'ActionOutput'],
                                main_agent: Optional["ConversableAgent"] = None,
                                task_manager: Optional[TreeManager] = None,
                                input_message_id: Optional[str] = None,
                                output_message_id: Optional[str] = None,
                                senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
                                ):
        conv_id: str = main_agent.agent_context.conv_id
        user_message: Optional[GptsMessage] = messages_map.get(input_message_id)
        if not user_message:
            logger.warning("_planning_vis_all eroor, not have user in message!")

        ## 处理 任务推进显示
        root_task_space = task_manager.get_node(user_message.goal_id)
        root_plan_item = self._unpack_task_space(root_task_space, task_manager, actions_map, messages_map, senders_map)

        planning_window_content = PlanningSpaceContent(
            uid=f'{conv_id}_planning',
            type=UpdateType.INCR.value,
            agent_role=main_agent.role,
            agent_name=main_agent.name,
            avatar=main_agent.avatar,
            title=None,
            description=None,
            markdown=self.vis_inst(AgentPlan.vis_tag()).sync_display(content=root_plan_item.to_dict())
        )
        all_plans_vis = self.vis_inst(PlanningSpace.vis_tag()).sync_display(
            content=planning_window_content.to_dict()
        )

        foot_vis = ""
        output_message: Optional[GptsMessage] = messages_map.get(output_message_id)
        if output_message:
            logger.info(f"output message is {output_message.content}")

        return all_plans_vis + "\n" + foot_vis

    async def _running_vis_all(self,
                               messages: List["GptsMessage"],
                               main_agent_name: Optional[str] = None,
                               senders_map: Optional[Dict[str, "ConversableAgent"]] = None):
        main_agent = senders_map[main_agent_name]
        conv_session_id = main_agent.agent_context.conv_session_id
        main_agent_folder = await self._build_agent_folder(main_agent)

        work_items = []
        for item in messages:
            work_item = await self.gen_work_item(gpt_msg=item, stream_msg=None,
                                                 is_first_chunk=True, senders_map=senders_map)
            if work_item:
                work_items.extend(work_item)

        work_space_content = WorkSpaceContent(
            uid=conv_session_id,
            type=UpdateType.INCR.value,
            running_agents=[],
            explorer=self.vis_inst(AgentFolder.vis_tag()).sync_display(content=main_agent_folder.to_dict()),
            items=work_items
        )

        return self.vis_inst(WorkSpace.vis_tag()).sync_display(
            content=work_space_content.to_dict()
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
        main_agent_name = kwargs.get('main_agent_name')

        messages_map = kwargs.get('messages_map')
        actions_map = kwargs.get('actions_map')
        task_manager = kwargs.get('task_manager')
        input_message_id = kwargs.get('input_message_id')
        output_message_id = kwargs.get('output_message_id')

        main_agent = senders_map.get(main_agent_name)
        if not main_agent:
            logger.warning(f"can’t find main agent [{main_agent_name}] in sender's map")

        all_plans_view = await self._planning_vis_all(messages_map=messages_map,
                                                      actions_map=actions_map,
                                                      main_agent=main_agent,
                                                      task_manager=task_manager,
                                                      input_message_id=input_message_id,
                                                      output_message_id=output_message_id,
                                                      senders_map=senders_map,
                                                      )

        all_running_view = await self._running_vis_all(messages=messages, main_agent_name=main_agent_name,
                                                       senders_map=senders_map)

        all_vis = json.dumps({
            "planning_window": all_plans_view,
            "running_window": all_running_view
        }, ensure_ascii=False)
        return all_vis
