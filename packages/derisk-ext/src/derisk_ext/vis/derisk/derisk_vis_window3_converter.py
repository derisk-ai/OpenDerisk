import json
import logging
import re
from enum import Enum
from typing import List, Optional, Dict, Union, Tuple, Any

from derisk.agent import ActionOutput, ConversableAgent, BlankAction
from derisk.agent.core.action.report_action import ReportAction
from derisk.agent.core.file_system.file_tree import TreeManager, TreeNodeData
from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.agent.core.memory.gpts.gpts_memory import AgentTaskContent, AgentTaskType
from derisk.agent.core.plan.planning_action import PlanningAction

from derisk.agent.core.reasoning.reasoning_action import (
    AgentAction,
    KnowledgeRetrieveAction,
)
from derisk.agent.core.schema import Status
from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
from derisk.agent.expand.actions.agent_action import AgentStart
from derisk.agent.expand.actions.code_action import CodeAction
from derisk.agent.expand.actions.tool_action import ToolAction
from derisk.agent.expand.react_agent.react_parser import (
    CONST_LLMOUT_THOUGHT,
    CONST_LLMOUT_TITLE,
    CONST_LLMOUT_TOOLS,
)
from derisk.vis.schema import VisAttachListContent, VisAttachContent
from derisk.vis.vis_converter import SystemVisTag
from derisk_ext.vis.common.tags.derisk_attach import DeriskAttach
from derisk_ext.vis.common.tags.derisk_plan import AgentPlan, AgentPlanItem
from derisk_ext.vis.common.tags.derisk_todo_list import TodoList
from derisk_ext.vis.common.tags.derisk_thinking import (
    DeriskThinking,
    DrskThinkingContent,
)
from derisk_ext.vis.common.tags.derisk_tool import ToolSpace
from derisk_ext.vis.common.tags.derisk_work_space import (
    WorkSpaceContent,
    WorkSpace,
    FolderNode,
)
from derisk_ext.vis.common.tags.derisk_system_events import (
    SystemEvents,
    SystemEventsContent,
)
from .derisk_vis_incr_converter import DeriskVisIncrConverter
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.tags.derisk_agent_folder import AgentFolder
from derisk_ext.vis.derisk.tags.derisk_space_llm import LLMSpaceContent, LLMSpace
from derisk_ext.vis.derisk.tags.drsk_content import DrskTextContent, DrskContent

from derisk_ext.vis.vis_protocol_data import UpdateType
from ..common.tags.derisk_attach_list import DeriskAttachList
from ...agent.actions.derisk_tool_action import DeriskToolAction
from ...agent.actions.monitor_action import MonitorAction

logger = logging.getLogger(__name__)


PHASE_PATTERNS = [
    (r"【阶段\s*[:：]\s*([^】]+)】", "zh"),
    (r"\[Phase\s*[:：]\s*([^\]]+)\]", "en"),
]

PHASE_NORMALIZE_MAP = {
    "分析": "analysis",
    "规划": "planning",
    "执行": "execution",
    "验证": "verification",
    "完成": "completion",
    "analysis": "analysis",
    "planning": "planning",
    "execution": "execution",
    "verification": "verification",
    "completion": "completion",
}

PHASE_DISPLAY_MAP = {
    "analysis": "分析阶段",
    "planning": "规划阶段",
    "execution": "执行阶段",
    "verification": "验证阶段",
    "completion": "完成阶段",
}


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
# ║
# ║ 🔧 2025-02-04 优化：
# ║   后端只发送变更的叶子节点数据（不再递归构建完整树结构）
# ║   前端根据 uid 自动合并增量数据
# ║   优势：大幅减少数据传输量，后端逻辑简化
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
    MonitorAction.name: "monitor",
    CodeAction.name: "code",
    ToolAction.name: "tool",
    DeriskToolAction.name: "tool",
    # 有展示分类需求的再这里进行分类处理
}


class DeriskIncrVisWindow3Converter(DeriskVisIncrConverter):
    """Incremental task window mode protocol converter."""

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
            SystemVisTag.VisTodo.value: TodoList.vis_tag(),
        }

    @property
    def web_use(self) -> bool:
        return True

    @property
    def reuse_name(self):
        ## 复用下面转换器的前端布局
        from derisk_ext.vis.derisk.derisk_vis_window_converter import (
            DeriskIncrVisWindowConverter,
        )

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
        **kwargs,
    ):
        ## 并行情况下搜集当前运行中Agent信息
        running_agents: List[str] = []
        for k, v in senders_map.items():
            agent_state = await v.agent_state()
            if agent_state == Status.RUNNING:
                running_agents.append(v.name)

        task_manager: TreeManager = kwargs.get("task_manager")
        event_manager = kwargs.get("event_manager")
        conv_id = kwargs.get("conv_id") or kwargs.get("cache")
        if conv_id and hasattr(conv_id, "conv_id"):
            conv_id = conv_id.conv_id
        try:
            planning_vis = ""
            ## 规划空间更新
            new_task_nodes = kwargs.get("new_task_nodes")
            ## 规划空间内容增量更新
            if new_task_nodes or stream_msg:
                planning_vis = await self._planning_vis_build(
                    messages=messages,
                    stream_msg=stream_msg,
                    new_task_nodes=new_task_nodes,
                    is_first_chunk=is_first_chunk,
                    senders_map=senders_map,
                    main_agent_name=main_agent_name,
                    actions_map=kwargs.get("actions_map"),
                    task_manager=task_manager,
                    event_manager=None,
                    running_agents=running_agents,
                    conv_id=conv_id,
                )

            ## 工作空间增量更新
            work_vis = ""
            if gpt_msg or stream_msg:
                work_vis = await self._running_vis_build(
                    gpt_msg=gpt_msg,
                    stream_msg=stream_msg,
                    is_first_push=is_first_push,
                    is_first_chunk=is_first_chunk,
                    senders_map=senders_map,
                    main_agent_name=main_agent_name,
                    running_agents=running_agents,
                    cache=kwargs.get("cache"),
                )

            # 对话结束时推送文件交付列表
            if gpt_msg and gpt_msg.receiver == HUMAN_ROLE:
                files_view = await self._render_terminate_files(messages, senders_map)
                if files_view:
                    if work_vis:
                        work_vis = work_vis + "\n" + files_view
                    else:
                        work_vis = files_view

            planning_window = planning_vis
            if gpt_msg:
                foot_vis = await self._footer_vis_build(gpt_msg, senders_map)
                if foot_vis:
                    if planning_window:
                        planning_window = planning_window + "\n" + foot_vis
                    else:
                        planning_window = foot_vis

            system_events_vis = ""
            if event_manager:
                if not conv_id:
                    if (
                        main_agent_name
                        and senders_map
                        and main_agent_name in senders_map
                    ):
                        main_agent = senders_map[main_agent_name]
                        if (
                            hasattr(main_agent, "agent_context")
                            and main_agent.agent_context
                        ):
                            conv_id = main_agent.agent_context.conv_id
                    elif messages:
                        conv_id = messages[0].conv_id if messages else None

                if not conv_id and event_manager:
                    conv_id = event_manager.conv_id

                if conv_id:
                    if not planning_window:
                        planning_window = self._create_placeholder_planning_space(
                            conv_id
                        )

                    all_events = event_manager.get_all_events()
                    has_completion_event = any(
                        e.event_type.value in ["agent_complete", "error_occurred"]
                        for e in all_events
                    )
                    has_events = len(all_events) > 0
                    is_actually_running = (
                        bool(running_agents)
                        or (has_events and not has_completion_event)
                    ) and not has_completion_event
                    system_events_vis = await self._system_events_vis_build(
                        conv_id=conv_id,
                        event_manager=event_manager,
                        is_running=is_actually_running,
                    )

            if system_events_vis:
                if planning_window:
                    planning_window = planning_window + "\n" + system_events_vis
                else:
                    planning_window = system_events_vis

            if planning_window or work_vis:
                return json.dumps(
                    {"planning_window": planning_window, "running_window": work_vis},
                    ensure_ascii=False,
                )
            else:
                return None
        except Exception as e:
            logger.exception("vis_window3异常!")
            return None

    async def _gen_plan_items(
        self,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        layer_count: int = 0,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ) -> Optional[str]:
        plan_tasks_vis = []
        thought = None
        title = None
        thinking = None
        content = None
        tool_calls_info = None
        action_outs = None
        message_id = None
        is_streaming = False
        phase = None

        if gpt_msg:
            action_outs = gpt_msg.action_report
            agent = senders_map.get(gpt_msg.sender_name) if senders_map else None
            message_id = gpt_msg.message_id
            thinking = gpt_msg.thinking
            content = gpt_msg.content
            if agent and agent.agent_parser:
                thought = agent.agent_parser.parse_streaming_xml(
                    gpt_msg.content, CONST_LLMOUT_THOUGHT
                )
                title = agent.agent_parser.parse_streaming_xml(
                    gpt_msg.content, CONST_LLMOUT_TITLE
                )

        elif stream_msg:
            if isinstance(stream_msg, str):
                return None
            prev_content = stream_msg.get("prev_content")
            sender_name = stream_msg.get("sender_name")
            message_id = stream_msg.get("message_id")
            action_outs = stream_msg.get("action_report")
            thinking = stream_msg.get("thinking")
            content = stream_msg.get("content")
            tool_calls_info = stream_msg.get("tool_calls")
            is_streaming = True
            agent = senders_map.get(sender_name) if senders_map else None
            if agent and agent.agent_parser and prev_content:
                title = agent.agent_parser.parse_streaming_xml(
                    prev_content, CONST_LLMOUT_TITLE
                )
                thought = agent.agent_parser.parse_streaming_xml(
                    prev_content, CONST_LLMOUT_THOUGHT
                )
                tools = agent.agent_parser.parse_streaming_xml(
                    prev_content, CONST_LLMOUT_TOOLS
                )
                if tools or thought:
                    title = None
        else:
            return None

        step_thought = ""
        extracted_phase = None

        has_blank_action = False
        if action_outs:
            for action_out in action_outs:
                if action_out.name == BlankAction.name and not action_out.terminate:
                    has_blank_action = True
                    break

        if title:
            step_thought = title
        elif thinking:
            extracted_phase, clean_thinking = self._extract_phase(thinking)
            if extracted_phase:
                phase = extracted_phase
            if clean_thinking and clean_thinking.strip():
                step_thought = clean_thinking.strip()
        elif thought:
            extracted_phase, clean_thought = self._extract_phase(thought)
            if extracted_phase and not phase:
                phase = extracted_phase
            if clean_thought and clean_thought.strip():
                step_thought = clean_thought.strip()
            else:
                step_thought = thought.strip()
        elif (
            content and content.strip() and not tool_calls_info and not has_blank_action
        ):
            if len(content.strip()) < 500:
                step_thought = content.strip()

        if step_thought and phase:
            phase_display = PHASE_DISPLAY_MAP.get(phase, phase)
            step_thought = f"**{phase_display}**\n\n{step_thought}"

        has_completed_actions = False
        if action_outs:
            for action_out in action_outs:
                if action_out.state == Status.COMPLETE.value:
                    has_completed_actions = True
                    break

        if step_thought:
            update_type = (
                UpdateType.INCR.value if is_streaming else UpdateType.ALL.value
            )
            report_content = DrskTextContent(
                dynamic=False,
                markdown=step_thought,
                uid=f"{message_id}_'step_thought'",
                type=update_type,
            )
            plan_tasks_vis.append(
                DrskContent().sync_display(
                    content=report_content.to_dict(exclude_none=True)
                )
            )

        if action_outs:
            for action_out in action_outs:
                if action_out.name == BlankAction.name and not action_out.terminate:
                    if action_out.content and action_out.content.strip():
                        # 使用和 step_thought 相同的 uid，利用 VIS 协议的增量更新机制自动覆盖
                        text_content = DrskTextContent(
                            dynamic=False,
                            markdown=action_out.content,
                            uid=f"{message_id}_'step_thought'",
                            type=UpdateType.ALL.value,
                        )
                        plan_tasks_vis.append(
                            DrskContent().sync_display(
                                content=text_content.to_dict(exclude_none=True)
                            )
                        )
                    continue
                plan_item = self._act_out_2_plan(action_out, layer_count)
                if plan_item:
                    plan_tasks_vis.append(plan_item)

        return "\n".join(plan_tasks_vis)

    def _extract_phase(self, text: str) -> Tuple[Optional[str], str]:
        """从文本中提取阶段标记，返回 (阶段key, 清理后的文本)

        支持格式：
        - 中文：【阶段: 分析】或【阶段：分析】
        - 英文：[Phase: Analysis] 或 [Phase：Analysis]

        修复：移除所有重复的阶段标记，避免重复渲染
        """
        if not text:
            return None, text

        phase_key = None
        clean_text = text

        # 遍历所有模式，提取第一个阶段标记并移除所有阶段标记
        for pattern, _ in PHASE_PATTERNS:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                # 使用第一个匹配的阶段
                if phase_key is None:
                    phase_raw = matches[0].group(1).strip()
                    phase_key = PHASE_NORMALIZE_MAP.get(
                        phase_raw.lower(), phase_raw.lower()
                    )
                # 移除所有匹配的阶段标记
                for match in reversed(matches):  # 从后往前移除，避免索引变化
                    clean_text = clean_text[: match.start()] + clean_text[match.end() :]

        if phase_key:
            clean_text = clean_text.strip()
            return phase_key, clean_text

        return None, text

    def _unpack_agent(self, parent_agent: ConversableAgent, parent: FolderNode):
        details: List[FolderNode] = []
        if hasattr(parent_agent, "agents"):
            for item in parent_agent.agents:
                detail_folder: FolderNode = FolderNode(
                    uid=f"{parent_agent.agent_context.conv_session_id}_{item.agent_context.agent_app_code}",
                    type=UpdateType.INCR.value,
                    item_type="folder",
                    title=item.name,
                    description=item.desc,
                    avatar=item.avatar,
                    items=[],
                )
                details.append(detail_folder)
                if item.is_team:
                    self._unpack_agent(item, detail_folder)
            parent.items.extend(details)

    async def _process_stream_msg(
        self,
        stream_msg: Dict,
        senders_map: Optional[Dict[str, "ConversableAgent"]],
        task_manager: Optional[TreeManager] = None,
    ) -> Optional[str]:
        """处理 stream_msg 虚拟节点数据，message本身是hidden节点，需要把当前叶子节点内容挂载到父节点，也就是goal_id节点。"""
        goal_id = stream_msg.get("goal_id")
        if not goal_id:
            return None

        leaf_item_vis = await self._gen_plan_items(
            stream_msg=stream_msg,
            layer_count=0,
            senders_map=senders_map,
        )

        if not leaf_item_vis:
            return None

        # 父节点挂载stream msg
        stream_item = AgentPlanItem(
            uid=goal_id,
            type=UpdateType.INCR.value,
            markdown=leaf_item_vis,
        )

        return self.vis_inst(AgentPlan.vis_tag()).sync_display(
            content=stream_item.to_dict()
        )

    def _build_task_item(
        self,
        task_node: TreeNodeData[AgentTaskContent],
        markdown: str,
        senders_map: Optional[Dict[str, "ConversableAgent"]],
    ) -> AgentPlanItem:
        """构建任务节点的 AgentPlanItem。"""
        agent = (
            senders_map.get(task_node.content.agent_name) if task_node.content else None
        )

        return AgentPlanItem(
            uid=task_node.node_id,
            parent_uid=task_node.parent_id,
            type=UpdateType.INCR.value,
            title=task_node.name,
            description=task_node.description,
            item_type=(
                task_node.content.task_type or AgentTaskType.PLAN.value
                if task_node.content
                else AgentTaskType.PLAN.value
            ),
            agent_role=agent.role if agent else None,
            agent_name=agent.name if agent else None,
            agent_avatar=agent.avatar if agent else None,
            status=task_node.state,
            start_time=task_node.created_at,
            layer_count=task_node.layer_count,
            cost=task_node.content.cost if task_node.content else 0,
            markdown=markdown,
        )

    async def _build_nested_task_nodes(
        self,
        new_task_nodes: List[TreeNodeData[AgentTaskContent]],
        messages: List[GptsMessage],
        senders_map: Optional[Dict[str, "ConversableAgent"]],
        task_manager: Optional[TreeManager] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
    ) -> List[str]:
        """构建嵌套任务节点。

        核心逻辑：
        1. hidden 类型节点：渲染结果为空，不输出任何内容
        2. 非 hidden 节点：查找父节点，如果父节点是 hidden，parent_uid 设置为父节点的父节点
        3. stream_msg 虚拟节点：处理逻辑与普通节点一致，节点 id 为 message_id

        Returns list of vis texts.
        """
        messages_map = {item.message_id: item for item in messages}
        result_vis_list: List[str] = []

        # 处理 stream_msg 虚拟节点
        if stream_msg and isinstance(stream_msg, dict):
            stream_vis = await self._process_stream_msg(
                stream_msg, senders_map, task_manager
            )
            if stream_vis:
                result_vis_list.append(stream_vis)

        # 按有效父节点分组
        parent_groups: Dict[Optional[str], List[TreeNodeData[AgentTaskContent]]] = {}

        for task_node in new_task_nodes:
            if task_node.node_id == task_node.parent_id or not task_node.parent_id:
                parent_groups.setdefault(None, []).append(task_node)
            else:
                parent_groups.setdefault(task_node.parent_id, []).append(task_node)

        # 处理有父节点的任务（作为子节点挂载到父节点下）
        for parent_id, children in parent_groups.items():
            # 收集所有子节点的 vis
            children_vis_list: List[str] = []
            for child_node in children:
                # 生成子节点的内容(Task节点根据消息生成，非Task类型节点直接生成任务节点)
                leaf_item_vis = ""
                if child_node.content is None:
                    continue
                if child_node.content.task_type == AgentTaskType.TASK.value:
                    gpt_msg = messages_map.get(child_node.content.message_id)
                    if gpt_msg:
                        leaf_item_vis = await self._gen_plan_items(
                            gpt_msg=gpt_msg,
                            layer_count=child_node.layer_count + 1,
                            senders_map=senders_map,
                        )

                else:
                    leaf_item_vis = self.vis_inst(AgentPlan.vis_tag()).sync_display(
                        content=self._build_task_item(
                            child_node, "", senders_map
                        ).to_dict()
                    )

                children_vis_list.append(leaf_item_vis)

            if parent_id and children_vis_list:
                parent_task = task_manager.get_node(parent_id)
                parent_item = AgentPlanItem(
                    uid=parent_task.node_id,
                    type=UpdateType.INCR.value,
                    item_type=parent_task.content.task_type,
                    status=parent_task.state,
                    start_time=parent_task.created_at,
                    cost=parent_task.content.cost if parent_task.content else 0,
                    markdown="\n".join(children_vis_list),
                )

                parent_vis = self.vis_inst(AgentPlan.vis_tag()).sync_display(
                    content=parent_item.to_dict()
                )
                result_vis_list.append(parent_vis)
            else:
                logger.info("没有父节点的 子节点直接作为根节点返回")
                ## 没有父节点的 子节点直接作为根节点返回
                result_vis_list.extend(children_vis_list)
        return result_vis_list

    async def _footer_vis_build(
        self,
        gpt_msg: GptsMessage,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        is_retry_chat: bool = False,
    ):
        plans_vis = []
        foot_vis = None
        confirm_vis = None
        ask_user_vis = None

        if gpt_msg:
            if gpt_msg.action_report:
                if not is_retry_chat:
                    ask_user_vis = await self.gen_ask_user_vis(gpt_msg)

                confirm_vis = await self._render_tool_confirm_action(
                    gpt_msg.message_id, gpt_msg.action_report
                )

            if gpt_msg.receiver == HUMAN_ROLE:
                foot_vis_parts = []

                notice_view = await self.gen_one_final_notice_vis(gpt_msg)
                if notice_view:
                    foot_vis_parts.append(notice_view)

                if foot_vis_parts:
                    foot_vis = "\n".join(foot_vis_parts)
        if foot_vis:
            plans_vis.append(foot_vis)

        if ask_user_vis:
            plans_vis.append(ask_user_vis)
        elif confirm_vis:
            plans_vis.append(confirm_vis)

        return "\n".join(plans_vis)

    def _find_agent_root_node(
        self, task_manager: TreeManager
    ) -> Optional[TreeNodeData]:
        if not task_manager:
            return None
        # 优先查找 item_type='agent' 的节点
        for node in task_manager.node_map.values():
            if (
                node.content
                and hasattr(node.content, "task_type")
                and node.content.task_type == "agent"
            ):
                return node
        # 降级策略：查找根节点
        for node in task_manager.node_map.values():
            if not node.parent_id:
                return node
        return None

    def _is_hidden_node(self, task_node: TreeNodeData[AgentTaskContent]) -> bool:
        """检查节点是否为 hidden 类型。"""
        return (
            task_node.content
            and task_node.content.task_type == AgentTaskType.HIDDEN.value
        )

    def _get_effective_parent_id(
        self,
        task_node: TreeNodeData[AgentTaskContent],
        task_manager: Optional[TreeManager],
    ) -> Optional[str]:
        """获取有效的父节点 ID。

        如果直接父节点是 hidden 类型，则返回父节点的父节点（跳过 hidden 节点）。
        """
        if not task_manager:
            return task_node.parent_id

        # 如果没有父节点或者父节点不存在，根节点作为父节点
        parent_id = task_node.parent_id
        if not parent_id or task_node.parent_id == task_node.node_id:
            return None

        parent_task = task_manager.get_node(parent_id)

        if not parent_task:
            return None

        # 如果父节点是 hidden，向上查找直到非 hidden 节点
        if self._is_hidden_node(parent_task):
            return parent_task.parent_id

        return parent_id

    async def _planning_vis_build(
        self,
        messages: Optional[List[GptsMessage]] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_task_nodes: Optional[List[TreeNodeData[AgentTaskContent]]] = None,
        is_first_chunk: bool = False,
        main_agent_name: Optional[str] = None,
        actions_map: Optional[Dict[str, "ActionOutput"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        task_manager: Optional[TreeManager] = None,
        event_manager: Optional[Any] = None,
        running_agents: Optional[List[str]] = None,
        conv_id: Optional[str] = None,
    ) -> Optional[str]:
        """构建规划空间可视化数据。

        优化：只发送变更的叶子节点，前端根据 uid 自动合并。
        不再递归构建完整树结构，大幅降低数据传输量。
        """
        main_agent = None
        if senders_map and main_agent_name:
            if main_agent_name not in senders_map:
                logger.debug(
                    f"main_agent_name '{main_agent_name}' not found in senders_map"
                )
            main_agent = senders_map.get(main_agent_name)

        if not conv_id:
            if (
                main_agent
                and hasattr(main_agent, "agent_context")
                and main_agent.agent_context
            ):
                conv_id = main_agent.agent_context.conv_id
            elif messages:
                conv_id = messages[0].conv_id if messages else None

        if not conv_id and event_manager:
            conv_id = event_manager.conv_id

        if not conv_id:
            logger.warning("_planning_vis_build error: unable to determine conv_id")
            return None

        task_items_vis = []

        # --- 新增逻辑：提取看板相关工具的输出 ---
        kanban_todolist_content = None
        target_actions = ["create_kanban", "submit_deliverable"]

        # 检查流式消息
        if stream_msg:
            action_outs = stream_msg.get("action_report")
            if action_outs:
                for out in action_outs:
                    if out.name in target_actions or out.action in target_actions:
                        kanban_todolist_content = (
                            out.simple_view or out.view or out.content
                        )

        # 检查新任务节点中的消息
        if new_task_nodes and messages:
            messages_map = {m.message_id: m for m in messages}
            for node in new_task_nodes:
                if node.content is None:
                    continue
                msg = messages_map.get(node.content.message_id)
                if msg and msg.action_report:
                    for out in msg.action_report:
                        if out.name in target_actions or out.action in target_actions:
                            kanban_todolist_content = (
                                out.simple_view or out.view or out.content
                            )

        # 如果有看板更新，挂载到 Agent 根节点
        if kanban_todolist_content and task_manager:
            root_node = self._find_agent_root_node(task_manager)
            if root_node:
                # 创建一个虚拟的子节点来承载 TodoList，确保状态单一且能刷新
                # 使用 UpdateType.ALL 确保每次都是全量替换，避免重复追加
                todolist_item = AgentPlanItem(
                    uid=root_node.node_id,
                    parent_uid=root_node.parent_id,
                    type=UpdateType.INCR.value,
                    # title="Task Board",
                    # description="Mission deliverables and status",
                    markdown=kanban_todolist_content,
                    status=Status.RUNNING.value,
                )
                task_items_vis.append(
                    self.vis_inst(AgentPlan.vis_tag()).sync_display(
                        content=todolist_item.to_dict()
                    )
                )
        # 处理 stream_msg 和 new_task_nodes
        # stream_msg 作为虚拟节点，与 new_task_nodes 统一处理
        if stream_msg or new_task_nodes:
            nested_vis_list = await self._build_nested_task_nodes(
                new_task_nodes or [],
                messages,
                senders_map,
                task_manager,
                stream_msg,
            )
            task_items_vis.extend(nested_vis_list)

        if task_items_vis:
            return "\n".join(task_items_vis)
        else:
            return None

    async def gen_work_item(
        self,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        is_first_chunk: bool = False,
        senders_map: Optional[Dict] = None,
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
            total_tokens = (
                gpt_msg.metrics.llm_metrics.total_tokens
                if gpt_msg.metrics and gpt_msg.metrics.llm_metrics
                else 0
            )
            tokens = (
                gpt_msg.metrics.llm_metrics.completion_tokens
                if gpt_msg.metrics and gpt_msg.metrics.llm_metrics
                else 0
            )
            update_type = UpdateType.ALL.value
        elif stream_msg:
            sender_name = stream_msg.get("sender")
            action_outs: Optional[List[ActionOutput]] = stream_msg.get("action_report")

            message_id = stream_msg.get("message_id")
            start_time = stream_msg.get("start_time")
            llm_model = stream_msg.get("model")
            llm_avatar = stream_msg.get("llm_avatar")
            tokens = stream_msg.get("tokens", 0)
            total_tokens = stream_msg.get("total_tokens", 0)
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

        # 🔧 修复：检测 thinking 和 content 是否包含相似内容，避免重复渲染
        def _is_similar_content(text1: Optional[str], text2: Optional[str]) -> bool:
            """检测两个文本是否包含相似内容（忽略空白字符差异）"""
            if not text1 or not text2:
                return False
            # 移除空白字符后比较
            clean1 = re.sub(r"\s+", "", text1)
            clean2 = re.sub(r"\s+", "", text2)
            # 如果一个文本是另一个的子串，或者相似度超过80%，认为是重复
            if clean1 in clean2 or clean2 in clean1:
                return True
            # 简单的相似度检测：检查前100个字符
            prefix_len = min(100, len(clean1), len(clean2))
            if prefix_len > 0 and clean1[:prefix_len] == clean2[:prefix_len]:
                return True
            return False

        # 如果 thinking 和 content 相似，只保留 thinking
        skip_content = False
        if thinking and content and _is_similar_content(thinking, content):
            skip_content = True

        ## 模型数据文件
        llm_content_md = ""
        if thinking:
            # 移除重复的阶段标记
            _, clean_thinking = self._extract_phase(thinking)
            thinking_content = DrskThinkingContent(
                markdown=thinking,
                uid=message_id + "_thinking",
                type=update_type,
                expand=thinkin_expand,
            )
            vis_thinking = DeriskThinking().sync_display(
                content=thinking_content.to_dict(exclude_none=True)
            )
            llm_content_md = llm_content_md + "\n" + vis_thinking

        if content and not skip_content:
            llm_content = DrskTextContent(
                markdown=content, uid=message_id + "_content", type=update_type
            )
            vis_content = DrskContent().sync_display(
                content=llm_content.to_dict(exclude_none=True)
            )
            llm_content_md = llm_content_md + "\n" + vis_content

        if llm_content_md:
            # Handle potential None values for metrics
            cost_val = 0
            speed_val = 0.0

            if gpt_msg and gpt_msg.metrics and gpt_msg.metrics.llm_metrics:
                if (
                    gpt_msg.metrics.llm_metrics.end_time_ms
                    and gpt_msg.metrics.start_time_ms
                ):
                    cost_val = (
                        gpt_msg.metrics.llm_metrics.end_time_ms
                        - gpt_msg.metrics.start_time_ms
                    ) // 1000
                if gpt_msg.metrics.llm_metrics.speed_per_second is not None:
                    speed_val = float(gpt_msg.metrics.llm_metrics.speed_per_second)

            llm_vis_md = LLMSpace().sync_display(
                content=LLMSpaceContent(
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
                    link_url=f"{self._drsk_web_url}/api/derisk/thinking/detail?message_id={message_id}",
                ).to_dict()
            )

            result.append(
                FolderNode(
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
                    markdown=llm_vis_md,
                )
            )

        ## 行动区域，每个action out为一个单独文件
        if action_outs:
            for action_out in action_outs:
                if (
                    action_out.name == AgentAction.name
                    or action_out.name == PlanningAction.name
                ):
                    continue
                result.append(
                    FolderNode(
                        uid=action_out.action_id,
                        type=UpdateType.INCR.value
                        if action_out.stream
                        else UpdateType.ALL.value,
                        item_type="file",
                        conv_id=conv_id,
                        tags=[goal] if goal else [],
                        path=f"{sender.agent_context.conv_session_id}_{sender.agent_context.agent_app_code}",
                        title=action_out.action_name or action_out.action,
                        description=action_out.thoughts or str(action_out.action_input),
                        status=action_out.state,
                        task_type=ACTION_TASK_MAP[action_out.name]
                        if action_out.name in ACTION_TASK_MAP
                        else "tool",
                        start_time=action_out.start_time
                        if action_out.start_time
                        else None,
                        cost=action_out.metrics.cost_seconds
                        if action_out.metrics
                        else 0,
                        markdown=action_out.view or action_out.content,
                    )
                )

        return result

    async def _build_agent_folder(
        self,
        main_agent: Optional["ConversableAgent"],
    ) -> FolderNode:
        main_agent_folder = FolderNode(
            uid=f"{main_agent.agent_context.conv_session_id}_{main_agent.agent_context.agent_app_code}",
            type=UpdateType.INCR.value,
            item_type="folder",
            title=main_agent.name,
            description=main_agent.desc,
            avatar=main_agent.avatar,
            items=[],
        )
        self._unpack_agent(main_agent, main_agent_folder)
        return main_agent_folder

    async def _build_file_system_folder(
        self,
        main_agent: Optional["ConversableAgent"],
    ) -> Optional[FolderNode]:
        conv_id = main_agent.agent_context.conv_id
        conv_session_id = main_agent.agent_context.conv_session_id

        file_system_folder = FolderNode(
            uid=f"{conv_session_id}_file_system",
            type=UpdateType.INCR.value,
            item_type="folder",
            title="📁 文件系统",
            description="AgentFileSystem 文件目录",
            avatar="https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original",
            items=[],
        )

        try:
            from derisk.agent.core.memory.gpts import GptsMemory
            from derisk.agent.core.memory.gpts.file_base import FileType

            memory = main_agent.memory
            if not memory or not hasattr(memory, "gpts_memory"):
                return file_system_folder

            gpts_memory = memory.gpts_memory
            if not isinstance(gpts_memory, GptsMemory):
                return file_system_folder

            files = await gpts_memory.list_files(conv_id)

            if not files:
                return file_system_folder

            type_groups: Dict[str, List] = {}
            for file_meta in files:
                file_type = file_meta.file_type or "other"
                if file_type not in type_groups:
                    type_groups[file_type] = []
                type_groups[file_type].append(file_meta)

            type_display_names = {
                FileType.CONCLUSION.value: "📋 结论文件",
                FileType.TOOL_OUTPUT.value: "🔧 工具输出",
                FileType.WRITE_FILE.value: "📝 写入文件",
                FileType.DELIVERABLE.value: "📦 交付物",
                FileType.TRUNCATED_OUTPUT.value: "📄 截断输出",
                FileType.KANBAN.value: "📊 看板文件",
                FileType.WORK_LOG.value: "📆 工作日志",
                FileType.TODO.value: "✅ 任务列表",
                "other": "📁 其他文件",
            }

            for file_type, file_list in type_groups.items():
                type_folder = FolderNode(
                    uid=f"{conv_session_id}_fs_{file_type}",
                    type=UpdateType.INCR.value,
                    item_type="folder",
                    title=type_display_names.get(file_type, f"📁 {file_type}"),
                    items=[],
                )

                for file_meta in file_list:
                    file_node = FolderNode(
                        uid=f"{conv_session_id}_file_{file_meta.file_id}",
                        type=UpdateType.INCR.value,
                        item_type="file",
                        title=file_meta.file_name,
                        description=f"{file_meta.file_size} bytes"
                        if file_meta.file_size
                        else None,
                        status=file_meta.status,
                        task_type="afs_file",
                        file_id=file_meta.file_id,
                        file_name=file_meta.file_name,
                        file_type=file_meta.file_type,
                        file_size=file_meta.file_size,
                        preview_url=file_meta.preview_url,
                        download_url=file_meta.download_url,
                        oss_url=file_meta.oss_url,
                        mime_type=file_meta.mime_type,
                    )
                    type_folder.items.append(file_node)

                file_system_folder.items.append(type_folder)

            return file_system_folder

        except Exception as e:
            logger.warning(f"Failed to build file system folder: {e}")
            return file_system_folder

    async def _build_incremental_file_nodes(
        self,
        main_agent: Optional["ConversableAgent"],
        cache: Optional[Any] = None,
    ) -> List[FolderNode]:
        conv_id = main_agent.agent_context.conv_id
        conv_session_id = main_agent.agent_context.conv_session_id

        incremental_nodes: List[FolderNode] = []

        try:
            from derisk.agent.core.memory.gpts import GptsMemory
            from derisk.agent.core.memory.gpts.file_base import FileType

            memory = main_agent.memory
            if not memory or not hasattr(memory, "gpts_memory"):
                return incremental_nodes

            gpts_memory = memory.gpts_memory
            if not isinstance(gpts_memory, GptsMemory):
                return incremental_nodes

            files = await gpts_memory.list_files(conv_id)
            if not files:
                return incremental_nodes

            rendered_file_ids = cache.rendered_file_ids if cache else set()

            type_display_names = {
                FileType.CONCLUSION.value: "📋 结论文件",
                FileType.TOOL_OUTPUT.value: "🔧 工具输出",
                FileType.WRITE_FILE.value: "📝 写入文件",
                FileType.DELIVERABLE.value: "📦 交付物",
                FileType.TRUNCATED_OUTPUT.value: "📄 截断输出",
                FileType.KANBAN.value: "📊 看板文件",
                FileType.WORK_LOG.value: "📆 工作日志",
                FileType.TODO.value: "✅ 任务列表",
                "other": "📁 其他文件",
            }

            for file_meta in files:
                if file_meta.file_id in rendered_file_ids:
                    continue

                file_type = file_meta.file_type or "other"
                type_folder_uid = f"{conv_session_id}_fs_{file_type}"
                file_node_uid = f"{conv_session_id}_file_{file_meta.file_id}"

                file_node = FolderNode(
                    uid=file_node_uid,
                    type=UpdateType.INCR.value,
                    item_type="file",
                    path=type_folder_uid,
                    title=file_meta.file_name,
                    description=f"{file_meta.file_size} bytes"
                    if file_meta.file_size
                    else None,
                    status=file_meta.status,
                    task_type="afs_file",
                    file_id=file_meta.file_id,
                    file_name=file_meta.file_name,
                    file_type=file_meta.file_type,
                    file_size=file_meta.file_size,
                    preview_url=file_meta.preview_url,
                    download_url=file_meta.download_url,
                    oss_url=file_meta.oss_url,
                    mime_type=file_meta.mime_type,
                )
                incremental_nodes.append(file_node)

                if cache:
                    cache.rendered_file_ids.add(file_meta.file_id)

            return incremental_nodes

        except Exception as e:
            logger.warning(f"Failed to build incremental file nodes: {e}")
            return incremental_nodes

    async def _running_vis_build(
        self,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        is_first_chunk: bool = False,
        is_first_push: bool = False,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        main_agent_name: Optional[str] = None,
        running_agents: Optional[List[str]] = None,
        cache: Optional[Any] = None,
    ):
        main_agent = senders_map[main_agent_name]
        conv_session_id = main_agent.agent_context.conv_session_id

        work_items = await self.gen_work_item(
            gpt_msg=gpt_msg,
            stream_msg=stream_msg,
            is_first_chunk=is_first_chunk,
            senders_map=senders_map,
        )
        main_agent_folder = None
        file_system_folder = None
        incremental_file_items: List[FolderNode] = []

        # 🔧 修复：每次都构建 agent folder，确保 explorer 始终存在
        # 这样追问时也能正确更新 AgentFolder 数据
        main_agent_folder = await self._build_agent_folder(main_agent=main_agent)

        if is_first_push:
            logger.info("构建vis_window3空间，进行首次资源管理器刷新!")
            file_system_folder = await self._build_file_system_folder(
                main_agent=main_agent
            )
            if main_agent_folder and file_system_folder:
                if main_agent_folder.items is None:
                    main_agent_folder.items = []
                main_agent_folder.items.append(file_system_folder)

            if cache and file_system_folder:
                for type_folder in file_system_folder.items or []:
                    for file_node in type_folder.items or []:
                        if hasattr(file_node, "file_id") and file_node.file_id:
                            cache.rendered_file_ids.add(file_node.file_id)
        else:
            incremental_file_items = await self._build_incremental_file_nodes(
                main_agent=main_agent,
                cache=cache,
            )

        work_space_content = None
        all_items = (work_items or []) + incremental_file_items

        if all_items and main_agent_folder:
            work_space_content = WorkSpaceContent(
                uid=conv_session_id,
                type=UpdateType.INCR.value,
                running_agents=running_agents,
                explorer=self.vis_inst(AgentFolder.vis_tag()).sync_display(
                    content=main_agent_folder.to_dict()
                ),
                items=all_items,
            )
        elif all_items:
            work_space_content = WorkSpaceContent(
                uid=conv_session_id, type=UpdateType.INCR.value, items=all_items
            )
        elif main_agent_folder:
            work_space_content = WorkSpaceContent(
                uid=conv_session_id,
                type=UpdateType.INCR.value,
                running_agents=running_agents,
                explorer=self.vis_inst(AgentFolder.vis_tag()).sync_display(
                    content=main_agent_folder.to_dict()
                ),
                items=[],
            )

        if work_space_content:
            return self.vis_inst(WorkSpace.vis_tag()).sync_display(
                content=work_space_content.to_dict()
            )
        else:
            return None

    def _act_out_2_plan(
        self,
        action_out: ActionOutput,
        layer_count: int,
    ):
        if action_out.name == BlankAction.name and not action_out.terminate:
            return None

        target_actions = ["create_kanban", "submit_deliverable"]
        if action_out.action in target_actions or action_out.name in target_actions:
            return None

        if action_out.terminate:
            return None

        title = action_out.action
        if action_out.name in [AgentStart.name]:
            title = action_out.name
        return self.vis_inst(AgentPlan.vis_tag()).sync_display(
            content=AgentPlanItem(
                uid=action_out.action_id,
                type=UpdateType.INCR.value,
                item_type="task",
                task_type=ACTION_TASK_MAP[action_out.name]
                if action_out.name in ACTION_TASK_MAP
                else "tool",
                title=title,
                description=str(action_out.action_input)
                if action_out.action_input
                else None,
                status=action_out.state,
                start_time=action_out.start_time,
                layer_count=layer_count,
                cost=action_out.metrics.cost_seconds if action_out.metrics else 0,
            ).to_dict()
        )

    TOOL_STEP_DESCRIPTIONS = {
        "view": "正在查看文件内容...",
        "write_file": "正在写入文件...",
        "execute_code": "正在执行代码...",
        "knowledge_search": "正在搜索知识库...",
        "agent_start": "正在启动子代理...",
        "send_message": "正在发送消息...",
        "terminate": "任务已完成",
        "web_search": "正在搜索网页...",
        "browser_navigate": "正在浏览网页...",
        "browser_click": "正在点击网页元素...",
        "browser_scroll": "正在滚动网页...",
        "browser_input": "正在输入文本...",
        "read_file": "正在读取文件...",
        "list_directory": "正在列出目录...",
        "execute_command": "正在执行命令...",
    }

    PHASE_DESCRIPTIONS = {
        "analysis": "分析阶段",
        "planning": "规划阶段",
        "execution": "执行阶段",
        "verification": "验证阶段",
        "completion": "完成阶段",
    }

    def _generate_tool_step_description(
        self, action_out: ActionOutput
    ) -> Optional[str]:
        """根据工具调用生成步骤描述，用于原生 FunctionCall 模式"""
        tool_name = action_out.action or action_out.name
        if not tool_name:
            return None

        if action_out.name == AgentStart.name:
            return "开始执行任务..."

        if action_out.terminate:
            return "任务执行完成"

        if tool_name in self.TOOL_STEP_DESCRIPTIONS:
            return self.TOOL_STEP_DESCRIPTIONS[tool_name]

        if action_out.thoughts and action_out.thoughts.strip():
            return action_out.thoughts.strip()[:200]

        phase = self._infer_phase_from_tool(tool_name)
        if phase:
            return f"{phase}: 执行 {tool_name}"

        return f"正在执行 {tool_name}..."

    def _infer_phase_from_tool(self, tool_name: str) -> Optional[str]:
        """根据工具名称推断执行阶段"""
        analysis_tools = [
            "view",
            "read_file",
            "list_directory",
            "knowledge_search",
            "web_search",
        ]
        planning_tools = []
        execution_tools = [
            "write_file",
            "execute_code",
            "execute_command",
            "browser_navigate",
            "browser_click",
            "browser_input",
            "browser_scroll",
            "send_message",
            "agent_start",
        ]
        verification_tools = []
        completion_tools = ["terminate"]

        tool_lower = tool_name.lower()

        for t in analysis_tools:
            if t in tool_lower:
                return self.PHASE_DESCRIPTIONS["analysis"]
        for t in execution_tools:
            if t in tool_lower:
                return self.PHASE_DESCRIPTIONS["execution"]
        for t in completion_tools:
            if t in tool_lower:
                return self.PHASE_DESCRIPTIONS["completion"]

        return None

    def _collect_kanban_for_agents(
        self,
        task_node: TreeNodeData[AgentTaskContent],
        task_manager: TreeManager,
        messages_map: Optional[Dict[str, GptsMessage]] = None,
    ) -> Dict[str, Tuple[int, str]]:
        """预收集看板信息，返回 {agent_node_id: (position, kanban_content)}。

        position 是第一次发现看板的位置（第几个子节点下）。
        content 是最后一个看板的内容（支持多次更新）。
        遇到子 Agent 时停止遍历（属于另一个 Agent 的看板逻辑）。
        """
        # 结构：{agent_id: {"position": int, "content": str}}
        result: Dict[str, Dict[str, any]] = {}

        if not messages_map:
            return {}

        target_actions = ["create_kanban", "submit_deliverable"]

        def collect_from_agent(agent_node: TreeNodeData[AgentTaskContent]):
            """从 Agent 节点开始遍历其子节点，收集看板信息。"""
            agent_id = agent_node.node_id

            for position, child_id in enumerate(agent_node.child_ids):
                child = task_manager.get_node(child_id)
                if not child:
                    continue

                # 跳过子 Agent（属于另一个 Agent 的看板逻辑）
                if (
                    child.content
                    and child.content.task_type == AgentTaskType.AGENT.value
                ):
                    continue

                # 在当前子树中搜索看板
                search_in_subtree(child, agent_id, position, result)

        def search_in_subtree(
            node: TreeNodeData[AgentTaskContent],
            agent_id: str,
            position: int,
            result: Dict[str, Dict[str, any]],
        ):
            """在非 Agent 子树中搜索看板，position 记录相对于 Agent 子节点的位置。

            遇到看板就更新 content（保留最后一个），但 position 只记录第一次的。
            """
            if not node.content:
                # 继续递归子节点（跳过子 Agent）
                for child_id in node.child_ids:
                    child = task_manager.get_node(child_id)
                    if (
                        child
                        and child.content
                        and child.content.task_type == AgentTaskType.AGENT.value
                    ):
                        continue
                    if child:
                        search_in_subtree(child, agent_id, position, result)
                return

            # 检查当前节点是否有看板
            message = messages_map.get(node.content.message_id)
            if message and message.action_report:
                for out in message.action_report:
                    if out.name in target_actions or out.action in target_actions:
                        kanban_content = out.simple_view or out.view or out.content
                        # 第一次发现：记录 position 和 content
                        # 后续发现：只更新 content（保留最后一个）
                        if agent_id not in result:
                            result[agent_id] = {
                                "position": position,
                                "content": kanban_content,
                            }
                        else:
                            result[agent_id]["content"] = kanban_content
                        break

            # 继续递归子节点（跳过子 Agent）
            for child_id in node.child_ids:
                child = task_manager.get_node(child_id)
                if (
                    child
                    and child.content
                    and child.content.task_type == AgentTaskType.AGENT.value
                ):
                    continue
                if child:
                    search_in_subtree(child, agent_id, position, result)

        # 从根节点开始，找到每个 Agent 及其看板
        def traverse_for_agents(node: TreeNodeData[AgentTaskContent]):
            """遍历树，对每个 Agent 节点收集看板。"""
            if not node.content:
                for child_id in node.child_ids:
                    child = task_manager.get_node(child_id)
                    if child:
                        traverse_for_agents(child)
                return

            if node.content.task_type == AgentTaskType.AGENT.value:
                # 处理这个 Agent
                collect_from_agent(node)

            # 继续遍历子节点
            for child_id in node.child_ids:
                child = task_manager.get_node(child_id)
                if child:
                    traverse_for_agents(child)

        traverse_for_agents(task_node)

        # 转换为最终格式
        return {
            agent_id: (info["position"], info["content"])
            for agent_id, info in result.items()
        }

    async def _unpack_task_space(
        self,
        task_space: TreeNodeData[AgentTaskContent],
        task_manager: TreeManager,
        actions_map: Dict[str, "ActionOutput"],
        messages_map: Optional[Dict[str, GptsMessage]] = None,
        agent_map: Optional[Dict[str, "ConversableAgent"]] = None,
        kanban_mount_map: Optional[Dict[str, Tuple[int, str]]] = None,
    ) -> Optional[str]:
        """递归解包任务空间，返回当前节点的渲染结果。

        核心逻辑：
        1. TASK 类型叶子节点：直接返回 _gen_plan_items 结果（不包装）
        2. 非 TASK 类型节点：包装成 AgentPlanItem，子节点作为 markdown
        3. Agent 节点：根据 kanban_mount_map 在指定位置挂载看板内容
        """
        if kanban_mount_map is None:
            kanban_mount_map = {}

        is_task = (
            task_space.content
            and task_space.content.task_type == AgentTaskType.TASK.value
        )
        is_agent = (
            task_space.content
            and task_space.content.task_type == AgentTaskType.AGENT.value
        )
        message = (
            messages_map.get(task_space.content.message_id)
            if messages_map and task_space.content
            else None
        )

        # 1. 递归处理所有子节点
        children_vis_list: List[str] = []

        for child_id in task_space.child_ids:
            child: TreeNodeData[AgentTaskContent] = task_manager.get_node(child_id)
            if child:
                child_vis = await self._unpack_task_space(
                    child,
                    task_manager,
                    actions_map,
                    messages_map,
                    agent_map,
                    kanban_mount_map,
                )
                if child_vis:
                    children_vis_list.append(child_vis)

        # 2. 如果是 Agent 节点，挂载看板到指定位置
        if is_agent and task_space.node_id in kanban_mount_map:
            position, kanban_content = kanban_mount_map[task_space.node_id]
            # position 表示在第几个子节点位置插入看板
            if position <= 0:
                children_vis_list.insert(0, kanban_content)
            elif position >= len(children_vis_list):
                children_vis_list.append(kanban_content)
            else:
                children_vis_list.insert(position, kanban_content)

        # 3. TASK 类型处理
        if is_task:
            node_content = ""
            if message:
                node_content = (
                    await self._gen_plan_items(
                        gpt_msg=message,
                        layer_count=task_space.layer_count + 1,
                        senders_map=agent_map,
                    )
                    or ""
                )

            # TASK 叶子节点：直接返回内容
            if not children_vis_list:
                return node_content

            # TASK 有子节点：内容 + 子节点
            markdown = "\n".join([node_content] + children_vis_list)
        else:
            markdown = "\n".join(children_vis_list)

        # 4. 非 TASK 节点构建 AgentPlanItem
        agent = (
            agent_map.get(task_space.content.agent_name)
            if task_space.content and agent_map
            else None
        )

        plan_item = AgentPlanItem(
            uid=task_space.node_id,
            parent_uid=task_space.parent_id,
            type=UpdateType.INCR.value,
            item_type=task_space.content.task_type
            if task_space.content
            else AgentTaskType.PLAN.value,
            title=task_space.name,
            description=task_space.description,
            status=task_space.state,
            agent_name=agent.name if agent else None,
            agent_avatar=agent.avatar if agent else None,
            start_time=task_space.created_at,
            layer_count=task_space.layer_count,
            cost=task_space.content.cost if task_space.content else 0,
            markdown=markdown,
        )
        return self.vis_inst(AgentPlan.vis_tag()).sync_display(
            content=plan_item.to_dict()
        )

    async def _planning_vis_all(
        self,
        messages_map: Dict[str, "GptsMessage"],
        actions_map: Dict[str, "ActionOutput"],
        main_agent: Optional["ConversableAgent"] = None,
        task_manager: Optional[TreeManager] = None,
        input_message_id: Optional[str] = None,
        output_message_id: Optional[str] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ):
        # 当 main_agent 为 None 时，从 messages_map 中获取 conv_id
        if main_agent is None:
            # 从 messages_map 中获取第一条消息的 conv_id
            if messages_map:
                first_message = next(iter(messages_map.values()), None)
                if first_message and hasattr(first_message, 'conv_id'):
                    conv_id: str = first_message.conv_id
                else:
                    logger.warning("_planning_vis_all: cannot get conv_id from messages_map")
                    return ""
            else:
                logger.warning("_planning_vis_all: main_agent is None and messages_map is empty")
                return ""
        else:
            conv_id: str = main_agent.agent_context.conv_id
        user_message: Optional[GptsMessage] = messages_map.get(input_message_id)
        if not user_message:
            logger.warning("_planning_vis_all eroor, not have user in message!")

        task_items_vis = []

        ## 处理 任务推进显示
        root_task_space = task_manager.get_node(user_message.goal_id)

        # 预收集看板挂载信息 {agent_id: (position, content)}
        kanban_mount_map = self._collect_kanban_for_agents(
            root_task_space, task_manager, messages_map
        )

        # 递归构建 vis，传入看板挂载信息
        root_vis = await self._unpack_task_space(
            root_task_space,
            task_manager,
            actions_map,
            messages_map,
            senders_map,
            kanban_mount_map,
        )

        if root_vis:
            task_items_vis.append(root_vis)

        foot_vis = ""
        output_message: Optional[GptsMessage] = messages_map.get(output_message_id)
        if output_message:
            logger.info(f"output message is {output_message.content}")
            final_conclusion_vis = await self._render_final_conclusion(output_message)
            if final_conclusion_vis:
                foot_vis = final_conclusion_vis

        return "\n".join(task_items_vis) + "\n" + foot_vis

    async def _running_vis_all(
        self,
        messages: List["GptsMessage"],
        main_agent_name: Optional[str] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ):
        main_agent = senders_map.get(main_agent_name) if senders_map else None
        # 当 main_agent 为 None 时，从 messages 中获取 conv_session_id
        if main_agent is None:
            if messages and len(messages) > 0:
                conv_session_id = messages[0].conv_session_id
            else:
                logger.warning("_running_vis_all: main_agent is None and messages is empty")
                return ""
        else:
            conv_session_id = main_agent.agent_context.conv_session_id
            main_agent_folder = await self._build_agent_folder(main_agent)

        work_items = []
        for item in messages:
            work_item = await self.gen_work_item(
                gpt_msg=item,
                stream_msg=None,
                is_first_chunk=True,
                senders_map=senders_map,
            )
            if work_item:
                work_items.extend(work_item)

        # 当 main_agent 为 None 时，explorer 设为空
        if main_agent is None:
            explorer_content = ""
        else:
            explorer_content = self.vis_inst(AgentFolder.vis_tag()).sync_display(
                content=main_agent_folder.to_dict()
            )

        work_space_content = WorkSpaceContent(
            uid=conv_session_id,
            type=UpdateType.INCR.value,
            running_agents=[],
            explorer=explorer_content,
            items=work_items,
        )

        return self.vis_inst(WorkSpace.vis_tag()).sync_display(
            content=work_space_content.to_dict()
        )

    async def _render_terminate_files(
        self,
        messages: List["GptsMessage"],
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ) -> Optional[str]:
        """渲染交付的文件列表.

        从messages中查找包含output_files的action，并提取其中的文件信息，
        使用d-attach-list组件渲染文件列表。

        Returns:
            d-attach-list组件的vis字符串，如果没有文件则返回None
        """
        file_contents = []

        for msg in messages:
            if not msg.action_report:
                continue
            for action_out in msg.action_report:
                # 从output_files获取文件信息
                # 兼容两种情况：ActionOutput对象 或 字典（从数据库读取时）
                if isinstance(action_out, dict):
                    output_files = action_out.get("output_files") or []
                else:
                    output_files = getattr(action_out, "output_files", None) or []
                if not output_files:
                    continue

                for file_info in output_files:
                    if isinstance(file_info, dict):
                        # 构建VisAttachContent
                        attach_content = VisAttachContent(
                            uid=f"file_{file_info.get('file_id', 'unknown')}",
                            type=UpdateType.ALL.value,
                            file_id=file_info.get("file_id", ""),
                            file_name=file_info.get("file_name", "未知文件"),
                            file_type=file_info.get("file_type", "unknown"),
                            file_size=file_info.get("file_size", 0),
                            oss_url=file_info.get("oss_url"),
                            preview_url=file_info.get("preview_url"),
                            download_url=file_info.get("download_url"),
                            mime_type=file_info.get("mime_type"),
                            created_at=file_info.get("created_at"),
                            task_id=file_info.get("task_id"),
                            description=file_info.get("description"),
                        )
                        file_contents.append(attach_content)

        if not file_contents:
            return None

        # 构建VisAttachListContent
        total_size = sum(f.file_size for f in file_contents)

        attach_list_content = VisAttachListContent(
            uid=f"terminate_files_{messages[0].conv_id if messages else 'unknown'}",
            type=UpdateType.ALL.value,
            title="交付文件",
            description=f"共 {len(file_contents)} 个文件，总大小 {self._format_file_size(total_size)}",
            files=file_contents,
            total_count=len(file_contents),
            total_size=total_size,
            show_batch_download=True,
        )

        # 渲染d-attach-list组件
        return self.vis_inst(DeriskAttachList.vis_tag()).sync_display(
            content=attach_list_content.to_dict()
        )

    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小显示."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    async def _render_final_conclusion(
        self, output_message: GptsMessage
    ) -> Optional[str]:
        """渲染最终结论.

        从 output_message 中提取最终结论并渲染到规划空间。
        最终结论可能存储在:
        1. action_report 中 terminate=True 的内容 (ReActMaster 等)
        2. 发送给 HUMAN_ROLE 的消息 content (CodeExpert 等)

        Returns:
            渲染后的 vis 字符串，如果没有结论则返回 None
        """
        from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
        from derisk.agent.core.action.base import ActionOutput

        conclusion_content = None

        def _get_action_out_value(action_out, key, default=None):
            """helper to get value from ActionOutput or dict"""
            if isinstance(action_out, dict):
                return action_out.get(key, default)
            return getattr(action_out, key, default)

        # 优先从 action_report 中获取 terminate 的结论 (ReActMaster 等使用 terminate 工具的场景)
        if output_message.action_report:
            for action_out in output_message.action_report:
                if _get_action_out_value(action_out, "terminate"):
                    conclusion_content = (
                        _get_action_out_value(action_out, "view")
                        or _get_action_out_value(action_out, "content")
                        or _get_action_out_value(action_out, "simple_view")
                    )
                    if conclusion_content:
                        break

        # 如果没有 terminate 结论，检查是否是发给用户的消息 (CodeExpert 等无 terminate 工具的场景)
        if not conclusion_content and output_message.receiver == HUMAN_ROLE:
            # 优先使用 action_report 的内容
            if output_message.action_report:
                for action_out in output_message.action_report:
                    if _get_action_out_value(
                        action_out, "view"
                    ) or _get_action_out_value(action_out, "content"):
                        conclusion_content = _get_action_out_value(
                            action_out, "view"
                        ) or _get_action_out_value(action_out, "content")
                        break
            # 否则使用消息 content
            if not conclusion_content:
                conclusion_content = output_message.content

        if not conclusion_content:
            return None

        final_conclusion = DrskTextContent(
            dynamic=False,
            markdown=f"## 最终结论\n\n{conclusion_content}",
            uid=f"{output_message.message_id}_final_conclusion",
            type="all",
        )
        return DrskContent().sync_display(
            content=final_conclusion.to_dict(exclude_none=True)
        )

    async def final_view(
        self,
        messages: List["GptsMessage"],
        plans_map: Optional[Dict[str, "GptsPlan"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs,
    ):
        if not messages:
            return None
        logger.info(f"final_view:{messages[0].conv_id}")
        main_agent_name = kwargs.get("main_agent_name")

        messages_map = kwargs.get("messages_map")
        actions_map = kwargs.get("actions_map")
        task_manager = kwargs.get("task_manager")
        input_message_id = kwargs.get("input_message_id")
        output_message_id = kwargs.get("output_message_id")

        main_agent = senders_map.get(main_agent_name)
        if not main_agent:
            logger.warning(f"can't find main agent [{main_agent_name}] in sender's map")

        all_plans_view = await self._planning_vis_all(
            messages_map=messages_map,
            actions_map=actions_map,
            main_agent=main_agent,
            task_manager=task_manager,
            input_message_id=input_message_id,
            output_message_id=output_message_id,
            senders_map=senders_map,
        )

        all_running_view = await self._running_vis_all(
            messages=messages, main_agent_name=main_agent_name, senders_map=senders_map
        )

        # 渲染terminate文件交付
        files_view = await self._render_terminate_files(messages, senders_map)

        # 如果有文件交付，添加到running_window
        if files_view and all_running_view:
            all_running_view = all_running_view + "\n" + files_view
        elif files_view:
            all_running_view = files_view

        all_vis = json.dumps(
            {"planning_window": all_plans_view, "running_window": all_running_view},
            ensure_ascii=False,
        )
        return all_vis

    async def _system_events_vis_build(
        self,
        conv_id: str,
        event_manager: Optional["SystemEventManager"],
        is_running: bool = True,
    ) -> Optional[str]:
        """Build system events visualization for planning window.

        This method generates a d-system-events vis component that displays
        real-time agent lifecycle events including preparation phase
        (build, resource loading, sandbox init) and execution phase
        (LLM calls, actions, retries, errors).

        Args:
            conv_id: Conversation ID
            event_manager: SystemEventManager instance containing events
            is_running: Whether the agent is currently running

        Returns:
            Vis string for the system events component, or None if no events
        """
        if not event_manager:
            return None

        all_events = event_manager.get_all_events()

        if not all_events and not is_running:
            return None

        current_phase = event_manager.get_current_phase().value

        current_action = self._get_current_action(
            all_events[:5] if all_events else [], is_running
        )

        merged_events = self._merge_events(all_events)

        events_data = []
        for event in merged_events:
            events_data.append(
                {
                    "event_id": event["event_id"],
                    "event_type": event["event_type"],
                    "title": event["title"],
                    "description": event.get("description"),
                    "timestamp": event.get("timestamp"),
                    "duration_ms": event.get("duration_ms"),
                    "status": event.get("status", "done"),
                }
            )

        content = {
            "uid": f"{conv_id}_system_events",
            "type": UpdateType.INCR.value,
            "is_running": is_running,
            "current_action": current_action,
            "current_phase": current_phase,
            "recent_events": events_data,
            "total_count": len(merged_events),
            "has_more": False,
            "total_duration_ms": event_manager.get_total_duration_ms(),
        }

        return self.vis_inst(SystemEvents.vis_tag()).sync_display(content=content)

    def _merge_events(self, events: List) -> List[Dict]:
        """Merge start/end event pairs into single events with duration.

        Args:
            events: List of SystemEvent objects

        Returns:
            List of merged event dictionaries
        """
        if not events:
            return []

        skip_events = {
            "llm_complete",
            "llm_failed",
            "action_complete",
            "action_failed",
            "agent_build_complete",
            "sandbox_create_done",
            "sandbox_create_failed",
            "sandbox_init_done",
            "sandbox_init_failed",
            "resource_build_done",
            "resource_build_failed",
            "resource_loaded",
            "resource_failed",
            "sub_agent_build_done",
            "sub_agent_build_failed",
            "agent_complete",
        }

        event_pairs = {
            "llm_thinking": ["llm_complete", "llm_failed"],
            "action_start": ["action_complete", "action_failed"],
            "agent_build_start": ["agent_build_complete"],
            "sandbox_create_start": ["sandbox_create_done", "sandbox_create_failed"],
            "sandbox_init_start": ["sandbox_init_done", "sandbox_init_failed"],
            "resource_build_start": ["resource_build_done", "resource_build_failed"],
            "resource_loading": ["resource_loaded", "resource_failed"],
            "sub_agent_build_start": ["sub_agent_build_done", "sub_agent_build_failed"],
            "agent_start": ["agent_complete"],
        }

        merged = []

        for event in events:
            event_type = event.event_type.value

            if event_type in skip_events:
                continue

            title = self._build_event_title(event)

            if event_type in event_pairs:
                end_types = event_pairs[event_type]

                duration_ms = event.duration_ms
                status = "running"

                for e in events:
                    if e.event_type.value in end_types:
                        if e.duration_ms is not None:
                            duration_ms = e.duration_ms
                        status = "failed" if "failed" in e.event_type.value else "done"
                        break

                merged.append(
                    {
                        "event_id": event.event_id,
                        "event_type": event_type,
                        "title": title,
                        "duration_ms": duration_ms,
                        "status": status,
                        "timestamp": event.timestamp.isoformat()
                        if event.timestamp
                        else None,
                    }
                )
            else:
                merged.append(
                    {
                        "event_id": event.event_id,
                        "event_type": event_type,
                        "title": title,
                        "description": event.description,
                        "duration_ms": event.duration_ms,
                        "status": "done",
                        "timestamp": event.timestamp.isoformat()
                        if event.timestamp
                        else None,
                    }
                )

        return merged

    def _build_event_title(self, event) -> str:
        """Build a descriptive title for an event using its context.

        Args:
            event: SystemEvent object

        Returns:
            Human-readable title with context
        """
        event_type = event.event_type.value
        original_title = event.title or ""
        description = event.description or ""

        if event_type == "llm_thinking":
            agent_name = ""
            if description.startswith("Agent:"):
                agent_name = description.replace("Agent:", "").strip()
            if agent_name:
                return f"{agent_name} 思考"
            return "LLM 思考"

        elif event_type == "action_start":
            tool_name = original_title.replace("执行 ", "").strip()
            if description:
                return f"{tool_name} ({description})"
            return f"{tool_name}"

        elif event_type == "resource_build_start":
            if "Manager" in original_title:
                return "构建 Manager Agent 资源"
            elif "Agent" in original_title:
                return "构建 Agent 资源"
            return "资源构建"

        elif event_type == "agent_instance_create":
            if description:
                return f"创建实例 ({description})"
            return original_title

        elif event_type == "sub_agent_build_start":
            return "构建子 Agent"

        elif event_type == "agent_build_start":
            return "构建 Agent"

        elif event_type == "sandbox_create_start":
            return "创建沙箱"

        elif event_type == "sandbox_init_start":
            return "初始化沙箱"

        elif event_type == "agent_start":
            return "Agent 开始运行"

        else:
            return original_title if original_title else event_type

    def _get_current_action(
        self, recent_events: List, is_running: bool
    ) -> Optional[str]:
        """Get human-readable description of current action.

        Args:
            recent_events: List of SystemEvent objects
            is_running: Whether agent is currently running

        Returns:
            Human-readable current action description
        """
        if not is_running:
            return "执行完成"

        if not recent_events:
            return "初始化中..."

        latest_event = recent_events[0]
        event_type = latest_event.event_type.value

        if event_type == "llm_thinking":
            description = latest_event.description or ""
            agent_name = (
                description.replace("Agent:", "").strip()
                if description.startswith("Agent:")
                else ""
            )
            return f"{agent_name} 思考中..." if agent_name else "思考中..."

        elif event_type == "action_start":
            title = latest_event.title or ""
            tool_name = title.replace("执行 ", "").strip()
            return f"执行 {tool_name}..."

        elif event_type in ["resource_build_start", "resource_loading"]:
            return "构建资源..."

        elif event_type == "sandbox_create_start":
            return "创建沙箱..."

        elif event_type == "sandbox_init_start":
            return "初始化沙箱..."

        elif event_type == "agent_instance_create":
            return "创建 Agent 实例..."

        elif event_type == "sub_agent_build_start":
            return "构建子 Agent..."

        elif event_type == "agent_build_start":
            return "构建 Agent..."

        elif event_type == "agent_start":
            return "Agent 运行中..."

        else:
            return latest_event.title or "处理中..."

    def _create_placeholder_planning_space(self, conv_id: str) -> str:
        """Create a placeholder d-planning-space component for initial rendering.

        This ensures d-system-events always appears after d-planning-space,
        even when no task nodes exist yet.

        Args:
            conv_id: Conversation ID

        Returns:
            Vis string for placeholder planning space
        """
        from derisk_ext.vis.common.tags.derisk_planning_space import (
            PlanningSpace,
            PlanningSpaceContent,
        )

        planning_window_content = PlanningSpaceContent(
            uid=f"{conv_id}_planning",
            type=UpdateType.INCR.value,
            agent_role="agent",
            agent_name="Agent",
            title=None,
            description=None,
            avatar=None,
            markdown="",
        )
        return self.vis_inst(PlanningSpace.vis_tag()).sync_display(
            content=planning_window_content.to_dict()
        )
