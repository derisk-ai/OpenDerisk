"""
Manus 双面板可视化布局转换器

将 Agent 执行消息转换为 manus-left-panel 和 manus-right-panel VIS tag 输出，
供前端 vis_manus 布局组件渲染。

VIS数据增量传输协议：
  1. type=INCR 情况下，组件按UID匹配，markdown和items做增量追加，其他字段有值替换无值不变
  2. type=ALL 模式下，所有字段都完全替换（包括空值）
"""

import json
import logging
import re
import uuid
from enum import Enum
from typing import List, Optional, Dict, Union, Any

from derisk.agent import ActionOutput, ConversableAgent, BlankAction
from derisk.agent.core.action.report_action import ReportAction
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
from derisk.agent.core_v2.vis_manus_protocol import (
    ManusStepType,
    ManusStepStatus,
    ManusOutputType,
    ManusArtifactType,
    ManusPanelView,
    ManusExecutionStep,
    ManusThinkingSection,
    ManusArtifactItem,
    ManusExecutionOutput,
    ManusActiveStepInfo,
    ManusLeftPanelData,
    ManusRightPanelData,
    VisManusData,
    ACTION_TO_STEP_TYPE,
)
from derisk.vis.vis_converter import SystemVisTag
from derisk_ext.vis.common.tags.derisk_attach import DeriskAttach
from derisk_ext.vis.common.tags.derisk_plan import AgentPlan, AgentPlanItem
from derisk_ext.vis.common.tags.derisk_thinking import (
    DeriskThinking,
    DrskThinkingContent,
)
from derisk_ext.vis.common.tags.derisk_tool import ToolSpace
from derisk_ext.vis.common.tags.derisk_todo_list import TodoList
from derisk_ext.vis.common.tags.derisk_system_events import (
    SystemEvents,
    SystemEventsContent,
)
from .derisk_vis_incr_converter import DeriskVisIncrConverter
from .derisk_vis_window3_converter import DeriskIncrVisWindow3Converter
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.tags.manus_left_panel import ManusLeftPanel
from derisk_ext.vis.derisk.tags.manus_right_panel import ManusRightPanel
from derisk_ext.vis.vis_protocol_data import UpdateType

logger = logging.getLogger(__name__)


# 阶段提取模式
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


class DeriskIncrVisManusConverter(DeriskIncrVisWindow3Converter):
    """Manus 双面板增量可视化布局转换器

    继承自 DeriskIncrVisWindow3Converter，复用其 planning_window 逻辑，
    仅覆写 running_window 部分为 manus-right-panel VIS tag。
    """

    def __init__(self, paths: Optional[str] = None, **kwargs):
        super().__init__(paths, **kwargs)
        self._step_counter = 0
        self._sections: Dict[str, ManusThinkingSection] = {}
        self._steps: Dict[str, ManusExecutionStep] = {}
        self._artifacts: List[ManusArtifactItem] = []
        self._outputs: Dict[str, List[ManusExecutionOutput]] = {}
        self._step_thoughts: Dict[str, str] = {}
        self._active_step_id: Optional[str] = None

    @property
    def web_use(self) -> bool:
        return True

    @property
    def reuse_name(self):
        return "vis_manus"

    @property
    def render_name(self):
        return "vis_manus"

    @property
    def description(self) -> str:
        return "Manus双面板可视化布局"

    # 用于检测 bash 命令中实际执行的代码语言
    _CODE_EXEC_PATTERNS = [
        # python 执行
        (r'(?:^|\s)python[23]?\s', ManusStepType.PYTHON),
        (r'(?:^|\s)pip\s+install', ManusStepType.PYTHON),
        (r'\.py\b', ManusStepType.PYTHON),
        # node/js 执行
        (r'(?:^|\s)node\s', ManusStepType.PYTHON),  # 用 code renderer
        (r'(?:^|\s)npm\s', ManusStepType.PYTHON),
        (r'(?:^|\s)npx\s', ManusStepType.PYTHON),
        (r'(?:^|\s)tsx?\s', ManusStepType.PYTHON),
        (r'\.js\b', ManusStepType.PYTHON),
        (r'\.ts\b', ManusStepType.PYTHON),
    ]

    def _detect_code_in_bash(self, action_input: Optional[Any]) -> Optional[str]:
        """检测 bash 命令中是否执行的是 Python/JS 代码

        如果是，返回应使用的步骤类型；否则返回 None（保持 bash/terminal）
        """
        if not action_input:
            return None

        command = ""
        if isinstance(action_input, str):
            try:
                parsed = json.loads(action_input)
                command = parsed.get("command", "") or parsed.get("cmd", "")
            except (json.JSONDecodeError, TypeError):
                command = action_input
        elif isinstance(action_input, dict):
            command = action_input.get("command", "") or action_input.get("cmd", "")

        if not command:
            return None

        for pattern, step_type in self._CODE_EXEC_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return step_type.value

        return None

    def _map_action_to_step_type(
        self, action_name: Optional[str], action_input: Optional[Any] = None
    ) -> str:
        """将 action 名称映射到 Manus 步骤类型

        对 bash 类型工具，进一步检测命令内容是否为代码执行
        """
        if not action_name:
            return ManusStepType.OTHER.value
        action_lower = action_name.lower()

        # 先做基本匹配
        base_type = ManusStepType.OTHER.value
        for key, step_type in ACTION_TO_STEP_TYPE.items():
            if key in action_lower:
                base_type = step_type.value
                break

        # 如果是 bash 类型，进一步检测是否执行代码
        if base_type == ManusStepType.BASH.value and action_input:
            code_type = self._detect_code_in_bash(action_input)
            if code_type:
                return code_type

        return base_type

    def _extract_phase_key(self, text: str) -> Optional[str]:
        """从文本中提取阶段信息（仅返回阶段 key）"""
        if not text:
            return None
        for pattern, _ in PHASE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                phase_raw = match.group(1).strip().lower()
                return PHASE_NORMALIZE_MAP.get(phase_raw, phase_raw)
        return None

    def _get_or_create_section(self, phase: Optional[str]) -> ManusThinkingSection:
        """获取或创建阶段分组"""
        phase_key = phase or "default"
        if phase_key not in self._sections:
            display_name = PHASE_DISPLAY_MAP.get(phase_key, phase_key)
            if phase_key == "default":
                display_name = "执行阶段"
            self._sections[phase_key] = ManusThinkingSection(
                id=f"section_{phase_key}",
                title=display_name,
            )
        return self._sections[phase_key]

    @staticmethod
    def _get_action_report_summary(gpt_msg: GptsMessage) -> Optional[str]:
        """Extract a summary string from action_report list."""
        if not gpt_msg.action_report:
            return None
        for act_out in gpt_msg.action_report:
            for attr in ('simple_view', 'view', 'observations', 'content'):
                val = getattr(act_out, attr, None)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
        return None

    def _process_gpt_message(self, gpt_msg: GptsMessage) -> Optional[ManusExecutionStep]:
        """处理单条 GptsMessage，提取为执行步骤

        支持两种数据来源：
        1. V1 Agent: action_report (List[ActionOutput]) 包含工具执行详情
        2. content JSON: 包含 action/tool/thought 等字段
        """
        if not gpt_msg:
            return None

        self._step_counter += 1
        step_id = f"step_{self._step_counter}"

        # 提取 action 信息 - 优先从 action_report 获取（V1 Agent 主要路径）
        action_name = None
        action_input = None
        thought = None
        observation = None

        # 路径1: 从 action_report (List[ActionOutput]) 提取
        if gpt_msg.action_report:
            for act_out in gpt_msg.action_report:
                if hasattr(act_out, 'action') and act_out.action:
                    action_name = act_out.action
                elif hasattr(act_out, 'action_name') and act_out.action_name:
                    action_name = act_out.action_name
                elif hasattr(act_out, 'name') and act_out.name:
                    action_name = act_out.name
                if hasattr(act_out, 'action_input') and act_out.action_input:
                    action_input = act_out.action_input
                if hasattr(act_out, 'thoughts') and act_out.thoughts:
                    thought = act_out.thoughts
                if hasattr(act_out, 'observations') and act_out.observations:
                    observation = act_out.observations
                elif hasattr(act_out, 'content') and act_out.content:
                    observation = act_out.content
                break  # 取第一个 action_report

        # 路径2: 从 content JSON 解析（V2 或 fallback）
        content = gpt_msg.content or ""
        if isinstance(content, str) and not action_name:
            try:
                content_dict = json.loads(content)
                action_name = action_name or content_dict.get("action") or content_dict.get("tool")
                action_input = action_input or content_dict.get("action_input") or content_dict.get("tool_input")
                thought = thought or content_dict.get("thought") or content_dict.get("thinking")
            except (json.JSONDecodeError, TypeError):
                pass

        # 从 gpt_msg.thinking 获取思考内容
        if not thought and gpt_msg.thinking:
            thought = gpt_msg.thinking

        # 确定步骤类型（bash 时检测是否执行代码）
        step_type = self._map_action_to_step_type(action_name, action_input)

        # 确定步骤标题 - BlankAction 显示为 "任务完成"
        is_blank = action_name == BlankAction.name
        if not is_blank and gpt_msg.action_report:
            for act_out in gpt_msg.action_report:
                if getattr(act_out, 'name', '') == BlankAction.name:
                    is_blank = True
                    break

        if is_blank:
            title = "任务完成"
        else:
            title = action_name or self._get_action_report_summary(gpt_msg) or "执行中"

        # 确定阶段
        phase = self._extract_phase_key(thought or content if isinstance(content, str) else "")

        # 确定状态 - 从 action_report 获取更精确的状态
        status = ManusStepStatus.RUNNING.value
        if gpt_msg.action_report:
            all_success = all(
                getattr(a, 'is_exe_success', True) for a in gpt_msg.action_report
            )
            if all_success:
                status = ManusStepStatus.COMPLETED.value
            else:
                status = ManusStepStatus.ERROR.value
        elif gpt_msg.current_goal and "failed" in gpt_msg.current_goal.lower():
            status = ManusStepStatus.ERROR.value
        elif self._get_action_report_summary(gpt_msg) and "完成" in self._get_action_report_summary(gpt_msg):
            status = ManusStepStatus.COMPLETED.value

        step = ManusExecutionStep(
            id=step_id,
            type=step_type,
            title=title,
            subtitle=self._get_action_report_summary(gpt_msg),
            description=gpt_msg.current_goal,
            phase=phase,
            status=status,
        )

        # 保存思考内容
        if thought:
            self._step_thoughts[step_id] = thought

        # 提取输出
        outputs = []

        # 从 action_report 提取输出（V1 主要路径）
        if gpt_msg.action_report:
            for act_out in gpt_msg.action_report:
                # view 是给人看的信息
                # 优先使用 observations/content（实际工具执行结果），
                # 避免使用 view/simple_view（包含 VIS tag 标记，如 ```d-tool {...}```）
                obs_content = getattr(act_out, 'observations', None)
                act_content = getattr(act_out, 'content', None)

                display_content = obs_content or act_content
                if display_content:
                    # 根据步骤类型决定输出类型
                    if step_type == ManusStepType.BASH.value:
                        out_type = ManusOutputType.TEXT.value
                    elif step_type in (ManusStepType.PYTHON.value, ManusStepType.SQL.value):
                        out_type = ManusOutputType.CODE.value
                    elif step_type == ManusStepType.HTML.value:
                        out_type = ManusOutputType.HTML.value
                    else:
                        out_type = ManusOutputType.MARKDOWN.value
                    outputs.append(ManusExecutionOutput(
                        output_type=out_type,
                        content=display_content,
                    ))
        elif self._get_action_report_summary(gpt_msg):
            outputs.append(ManusExecutionOutput(
                output_type=ManusOutputType.TEXT.value,
                content=self._get_action_report_summary(gpt_msg),
            ))

        # 处理 content 中的各类输出
        if isinstance(content, str) and content.strip():
            try:
                content_dict = json.loads(content)
                observation = content_dict.get("observation", "")
                if observation:
                    # 根据 action 类型确定输出类型
                    if step_type == ManusStepType.BASH.value:
                        outputs.append(ManusExecutionOutput(
                            output_type=ManusOutputType.TEXT.value,
                            content=observation,
                        ))
                    elif step_type == ManusStepType.PYTHON.value:
                        outputs.append(ManusExecutionOutput(
                            output_type=ManusOutputType.CODE.value,
                            content=observation,
                        ))
                    elif step_type == ManusStepType.SQL.value:
                        outputs.append(ManusExecutionOutput(
                            output_type=ManusOutputType.TABLE.value,
                            content=observation,
                        ))
                    elif step_type == ManusStepType.HTML.value:
                        outputs.append(ManusExecutionOutput(
                            output_type=ManusOutputType.HTML.value,
                            content=observation,
                        ))
                    else:
                        outputs.append(ManusExecutionOutput(
                            output_type=ManusOutputType.MARKDOWN.value,
                            content=observation,
                        ))
            except (json.JSONDecodeError, TypeError):
                if not self._get_action_report_summary(gpt_msg):
                    outputs.append(ManusExecutionOutput(
                        output_type=ManusOutputType.TEXT.value,
                        content=content,
                    ))

        if outputs:
            self._outputs[step_id] = outputs

        # 提取产物
        self._extract_artifacts(step_id, step_type, content)

        self._steps[step_id] = step
        self._active_step_id = step_id

        # 添加到对应阶段分组
        section = self._get_or_create_section(phase)
        section.steps.append(step)

        return step

    def _extract_artifacts(self, step_id: str, step_type: str, content: Any):
        """从步骤输出中提取产物"""
        if not content:
            return

        content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)

        # 检测 HTML 文件
        html_pattern = r'[\w\-]+\.html'
        html_matches = re.findall(html_pattern, content_str)
        for name in html_matches:
            self._artifacts.append(ManusArtifactItem(
                id=f"artifact_{step_id}_{name}",
                type=ManusArtifactType.HTML.value,
                name=name,
                content=content_str,
            ))

        # 检测图片
        img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        img_matches = re.findall(img_pattern, content_str)
        for alt, url in img_matches:
            self._artifacts.append(ManusArtifactItem(
                id=f"artifact_{step_id}_{alt or 'image'}",
                type=ManusArtifactType.IMAGE.value,
                name=alt or "image",
                content=url,
            ))

        # 检测 CSV/文件输出
        file_pattern = r'>\s*([\w\-]+\.\w+)'
        file_matches = re.findall(file_pattern, content_str)
        for name in file_matches:
            ext = name.rsplit('.', 1)[-1].lower()
            artifact_type = ManusArtifactType.FILE.value
            if ext in ('csv', 'xlsx', 'xls'):
                artifact_type = ManusArtifactType.TABLE.value
            elif ext in ('png', 'jpg', 'jpeg', 'gif', 'svg'):
                artifact_type = ManusArtifactType.IMAGE.value
            elif ext in ('py', 'js', 'ts', 'sh'):
                artifact_type = ManusArtifactType.CODE.value
            elif ext == 'md':
                artifact_type = ManusArtifactType.MARKDOWN.value

            self._artifacts.append(ManusArtifactItem(
                id=f"artifact_{step_id}_{name}",
                type=artifact_type,
                name=name,
                downloadable=True,
            ))

    def _build_left_panel_data(
        self,
        is_working: bool = False,
        user_query: Optional[str] = None,
    ) -> ManusLeftPanelData:
        """构建左面板数据"""
        sections = list(self._sections.values())

        # 更新分组完成状态
        for section in sections:
            all_done = all(
                s.status in (ManusStepStatus.COMPLETED.value, ManusStepStatus.ERROR.value)
                for s in section.steps
            ) if section.steps else False
            section.is_completed = all_done

        return ManusLeftPanelData(
            sections=sections,
            active_step_id=self._active_step_id,
            is_working=is_working,
            user_query=user_query,
            step_thoughts=self._step_thoughts,
            artifacts=self._artifacts,
        )

    def _build_right_panel_data(self, is_running: bool = False) -> ManusRightPanelData:
        """构建右面板数据"""
        active_step_info = None
        outputs = []

        if self._active_step_id and self._active_step_id in self._steps:
            step = self._steps[self._active_step_id]
            active_step_info = ManusActiveStepInfo(
                id=step.id,
                type=step.type,
                title=step.title,
                subtitle=step.subtitle,
                status=step.status,
                detail=step.description,
            )
            outputs = self._outputs.get(self._active_step_id, [])

        # 确定面板视图
        panel_view = ManusPanelView.EXECUTION.value
        if active_step_info:
            if active_step_info.type == ManusStepType.HTML.value:
                panel_view = ManusPanelView.HTML_PREVIEW.value
            elif active_step_info.type == ManusStepType.SKILL.value:
                panel_view = ManusPanelView.SKILL_PREVIEW.value

        return ManusRightPanelData(
            active_step=active_step_info,
            outputs=outputs,
            is_running=is_running,
            artifacts=self._artifacts,
            panel_view=panel_view,
        )

    def _generate_vis_tag_output(
        self, tag: str, uid: str, data: Dict, update_type: str = UpdateType.ALL.value
    ) -> str:
        """生成 VIS tag 格式的输出"""
        payload = {
            "uid": uid,
            "type": update_type,
            **data,
        }
        return f"```{tag}\n{json.dumps(payload, ensure_ascii=False)}\n```"

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
        """主可视化方法 - planning_window 复用 vis_window3，running_window 使用 manus-right-panel"""
        running_agents: List[str] = []
        if senders_map:
            for k, v in senders_map.items():
                agent_state = await v.agent_state()
                if agent_state == Status.RUNNING:
                    running_agents.append(v.name)

        is_working = bool(running_agents)

        task_manager = kwargs.get("task_manager")
        event_manager = kwargs.get("event_manager")
        conv_id = kwargs.get("conv_id") or kwargs.get("cache")
        if conv_id and hasattr(conv_id, "conv_id"):
            conv_id = conv_id.conv_id

        try:
            # === planning_window: 完全复用 vis_window3 的规划空间逻辑 ===
            planning_vis = ""
            new_task_nodes = kwargs.get("new_task_nodes")
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

            planning_window = planning_vis
            if gpt_msg:
                foot_vis = await self._footer_vis_build(gpt_msg, senders_map)
                if foot_vis:
                    if planning_window:
                        planning_window = planning_window + "\n" + foot_vis
                    else:
                        planning_window = foot_vis

            # 系统事件
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

            # === running_window: 使用 manus-right-panel 渲染工具执行结果 ===
            # 处理新消息，追踪步骤状态
            if gpt_msg and gpt_msg.role != HUMAN_ROLE:
                self._process_gpt_message(gpt_msg)

            if stream_msg:
                await self._process_stream_message(stream_msg, is_first_chunk)

            right_panel = self._build_right_panel_data(is_running=is_working)
            running_window = self._generate_vis_tag_output(
                tag=ManusRightPanel.vis_tag(),
                uid="manus_right_panel",
                data=right_panel.to_dict(),
                update_type=UpdateType.ALL.value,
            )

            if planning_window or running_window:
                return json.dumps(
                    {"planning_window": planning_window, "running_window": running_window},
                    ensure_ascii=False,
                )
            return None
        except Exception as e:
            logger.exception("vis_manus visualization error!")
            return None

    async def _process_stream_message(
        self, stream_msg: Union[Dict, str], is_first_chunk: bool
    ):
        """处理流式消息增量更新

        兼容两种消息格式：
        1. V2 格式: type="thinking"/"tool_start"/"tool_result"/"response"
        2. V1 格式: type="incr", thinking/content 为顶层字段, action_report 嵌套
        """
        if isinstance(stream_msg, str):
            try:
                stream_msg = json.loads(stream_msg)
            except (json.JSONDecodeError, TypeError):
                # 纯文本流式内容 - 追加到当前步骤
                if self._active_step_id:
                    outputs = self._outputs.setdefault(self._active_step_id, [])
                    if outputs and outputs[-1].output_type == ManusOutputType.MARKDOWN.value:
                        outputs[-1].content = (outputs[-1].content or "") + stream_msg
                    else:
                        outputs.append(ManusExecutionOutput(
                            output_type=ManusOutputType.MARKDOWN.value,
                            content=stream_msg,
                        ))
                return

        if not isinstance(stream_msg, dict):
            return

        msg_type = stream_msg.get("type", "")

        # ============================================================
        # V1 格式: type="incr", thinking/content/action_report 为顶层字段
        # ============================================================
        if msg_type == "incr":
            # 处理 thinking
            thinking = stream_msg.get("thinking")
            if thinking and self._active_step_id:
                existing = self._step_thoughts.get(self._active_step_id, "")
                self._step_thoughts[self._active_step_id] = existing + thinking

            # 处理 action_report (V1 工具执行报告)
            action_report = stream_msg.get("action_report")
            if action_report:
                self._process_v1_action_report(action_report)

            # 处理 content（非工具执行的文本内容）
            content = stream_msg.get("content")
            if content and not action_report:
                if not self._active_step_id:
                    # 没有活跃步骤，创建一个通用响应步骤
                    self._step_counter += 1
                    step_id = f"step_{self._step_counter}"
                    step = ManusExecutionStep(
                        id=step_id,
                        type=ManusStepType.OTHER.value,
                        title="回复",
                        status=ManusStepStatus.RUNNING.value,
                    )
                    self._steps[step_id] = step
                    self._active_step_id = step_id
                    section = self._get_or_create_section(None)
                    section.steps.append(step)

                outputs = self._outputs.setdefault(self._active_step_id, [])
                if outputs and outputs[-1].output_type == ManusOutputType.MARKDOWN.value:
                    outputs[-1].content = (outputs[-1].content or "") + content
                else:
                    outputs.append(ManusExecutionOutput(
                        output_type=ManusOutputType.MARKDOWN.value,
                        content=content,
                    ))
            return

        # ============================================================
        # V2 格式: type="thinking"/"tool_start"/"tool_result"/"response"
        # ============================================================
        if msg_type == "thinking" or ("thought" in stream_msg and msg_type not in ("tool_start", "tool_result", "response")):
            thought = stream_msg.get("content") or stream_msg.get("thought", "")
            if self._active_step_id and thought:
                existing = self._step_thoughts.get(self._active_step_id, "")
                self._step_thoughts[self._active_step_id] = existing + thought

        elif msg_type == "tool_start":
            # 新工具调用开始 - 创建新步骤
            tool_name = stream_msg.get("tool") or stream_msg.get("action", "")
            tool_input = stream_msg.get("input") or stream_msg.get("action_input")
            self._step_counter += 1
            step_id = f"step_{self._step_counter}"
            step_type = self._map_action_to_step_type(tool_name, tool_input)

            step = ManusExecutionStep(
                id=step_id,
                type=step_type,
                title=tool_name or "执行中",
                status=ManusStepStatus.RUNNING.value,
            )
            self._steps[step_id] = step
            self._active_step_id = step_id

            # 添加到默认阶段
            section = self._get_or_create_section(None)
            section.steps.append(step)

        elif msg_type == "tool_result":
            if self._active_step_id:
                step = self._steps.get(self._active_step_id)
                if step:
                    success = stream_msg.get("success", True)
                    step.status = (
                        ManusStepStatus.COMPLETED.value if success
                        else ManusStepStatus.ERROR.value
                    )

                result = stream_msg.get("result", "")
                if result:
                    self._outputs.setdefault(self._active_step_id, []).append(
                        ManusExecutionOutput(
                            output_type=ManusOutputType.TEXT.value,
                            content=result,
                        )
                    )

        elif msg_type == "response" or "content" in stream_msg:
            content = stream_msg.get("content", "")
            if self._active_step_id and content:
                outputs = self._outputs.setdefault(self._active_step_id, [])
                if outputs and outputs[-1].output_type == ManusOutputType.MARKDOWN.value:
                    outputs[-1].content = (outputs[-1].content or "") + content
                else:
                    outputs.append(ManusExecutionOutput(
                        output_type=ManusOutputType.MARKDOWN.value,
                        content=content,
                    ))

    def _process_v1_action_report(self, action_report: Any):
        """处理 V1 Agent 的 action_report

        V1 的 action_report 可以是:
        - List[ActionOutput] 对象列表
        - List[Dict] 序列化后的字典列表
        """
        reports = action_report if isinstance(action_report, list) else [action_report]

        for report in reports:
            # 支持 ActionOutput 对象和 Dict
            if hasattr(report, 'action'):
                action_name = report.action or getattr(report, 'action_name', '') or getattr(report, 'name', '')
                action_input = getattr(report, 'action_input', None)
                thought = getattr(report, 'thoughts', None)
                is_success = getattr(report, 'is_exe_success', True)
                # 跳过 view/simple_view（包含 VIS tag 标记），优先使用实际执行结果
                observations = getattr(report, 'observations', None)
                content = getattr(report, 'content', None)
            elif isinstance(report, dict):
                action_name = report.get('action', '') or report.get('action_name', '') or report.get('name', '')
                action_input = report.get('action_input')
                thought = report.get('thoughts') or report.get('thought')
                is_success = report.get('is_exe_success', True)
                observations = report.get('observations')
                content = report.get('content', '')
            else:
                continue

            if not action_name:
                continue

            # BlankAction 显示为 "任务完成"
            is_blank = action_name == BlankAction.name
            if not is_blank:
                report_name = getattr(report, 'name', '') if hasattr(report, 'name') else (report.get('name', '') if isinstance(report, dict) else '')
                is_blank = report_name == BlankAction.name

            display_title = "任务完成" if is_blank else action_name

            # 创建新步骤
            self._step_counter += 1
            step_id = f"step_{self._step_counter}"
            step_type = self._map_action_to_step_type(action_name, action_input)

            step = ManusExecutionStep(
                id=step_id,
                type=step_type,
                title=display_title,
                status=ManusStepStatus.COMPLETED.value if is_success else ManusStepStatus.ERROR.value,
            )
            self._steps[step_id] = step
            self._active_step_id = step_id

            section = self._get_or_create_section(None)
            section.steps.append(step)

            # 保存思考
            if thought:
                self._step_thoughts[step_id] = thought

            # 提取输出 - 使用 observations/content（实际工具结果），不使用 view（VIS 标记）
            display_content = observations or content
            if display_content:
                out_type = ManusOutputType.TEXT.value
                if step_type in (ManusStepType.PYTHON.value, ManusStepType.SQL.value):
                    out_type = ManusOutputType.CODE.value
                elif step_type == ManusStepType.HTML.value:
                    out_type = ManusOutputType.HTML.value
                self._outputs.setdefault(step_id, []).append(
                    ManusExecutionOutput(output_type=out_type, content=display_content)
                )

    async def final_view(
        self,
        messages: List["GptsMessage"],
        plans_map: Optional[Dict[str, "GptsPlan"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs,
    ):
        """最终视图 - planning_window 复用 vis_window3，running_window 用 manus-right-panel"""
        # 将所有运行中的步骤标记为完成
        for step in self._steps.values():
            if step.status == ManusStepStatus.RUNNING.value:
                step.status = ManusStepStatus.COMPLETED.value

        # 调用父类 final_view 获取 planning_window（vis_window3 格式）
        parent_result = await super().final_view(
            messages=messages, plans_map=plans_map, senders_map=senders_map, **kwargs
        )

        # 构建 manus right panel 数据
        right_panel = self._build_right_panel_data(is_running=False)
        if messages:
            last_msg = messages[-1]
            if last_msg.role != HUMAN_ROLE and last_msg.content:
                right_panel.summary_content = last_msg.content
                right_panel.panel_view = ManusPanelView.SUMMARY.value

        right_vis = self._generate_vis_tag_output(
            tag=ManusRightPanel.vis_tag(),
            uid="manus_right_panel",
            data=right_panel.to_dict(),
            update_type=UpdateType.ALL.value,
        )

        # 替换 running_window 为 manus right panel
        if parent_result:
            try:
                result_data = json.loads(parent_result)
                result_data["running_window"] = right_vis
                return json.dumps(result_data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass

        return json.dumps(
            {"planning_window": "", "running_window": right_vis},
            ensure_ascii=False,
        )
