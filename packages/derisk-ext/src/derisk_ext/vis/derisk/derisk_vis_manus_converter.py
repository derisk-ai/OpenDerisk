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
    ManusTaskFileItem,
    ManusDeliverableFile,
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
from derisk_ext.vis.derisk.tags.drsk_content import DrskContent, DrskTextContent
from derisk_ext.vis.common.tags.derisk_system_events import (
    SystemEvents,
    SystemEventsContent,
)
from .derisk_vis_incr_converter import DeriskVisIncrConverter
from .derisk_vis_window3_converter import DeriskIncrVisWindow3Converter
from derisk_ext.vis.derisk.derisk_vis_converter import DrskVisTagPackage
from derisk_ext.vis.derisk.tags.manus_left_panel import ManusLeftPanel
from derisk_ext.vis.derisk.tags.manus_right_panel import ManusRightPanel
from derisk_ext.vis.derisk.tags.drsk_deliverable import DrskDeliverable
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
        # Map planning_window UID (action_id) → step_id for click-to-switch
        self._planning_uid_to_step_id: Dict[str, str] = {}
        # Buffer: (planning_uid, action_name) captured from _act_out_2_plan,
        # consumed by _process_gpt_message matching by action_name (FIFO)
        self._pending_planning_uids: List[tuple] = []

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

    def _act_out_2_plan(self, action_out, layer_count):
        """Override parent to capture the exact UIDs used for planning items.

        The planning_window uses action_out.action_id as the UID for each plan item.
        We capture these UIDs so we can map them to manus steps for click-to-switch.
        Only capture when the parent actually creates a planning item (returns non-None).
        """
        result = super()._act_out_2_plan(action_out, layer_count)
        if result is not None:
            action_id = getattr(action_out, 'action_id', None)
            action_name = getattr(action_out, 'action', None) or getattr(action_out, 'name', '') or ''
            if action_id:
                self._pending_planning_uids.append((action_id, action_name))
                logger.debug(f"[manus] captured planning UID: {action_id} (action={action_name})")
        return result

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

    async def _gen_plan_items(
        self,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        layer_count: int = 0,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ) -> Optional[str]:
        """覆写父类方法，处理 BlankAction 结论的流式渲染问题

        父类对 BlankAction(terminate=True) 的处理：
        - step_thought 走 INCR 路径 → 流式推送产生多个 DrskContent 片段
        - _act_out_2_plan() 返回 None → action 输出被丢弃

        覆写后：
        - 检测 BlankAction（无论 terminate 值）→ 用 observations/content 生成 type=ALL 的 DrskContent
        - 每次推送完整替换内容，确保 markdown 可正确渲染（表格、标题等不被拆分）
        """
        # 提取 action_outs
        action_outs = None
        message_id = None
        if gpt_msg:
            action_outs = gpt_msg.action_report
            message_id = gpt_msg.message_id
        elif stream_msg and isinstance(stream_msg, dict):
            action_outs = stream_msg.get("action_report")
            message_id = stream_msg.get("message_id")

        if action_outs:
            for act_out in (action_outs if isinstance(action_outs, list) else [action_outs]):
                # 兼容 ActionOutput 对象和 dict
                if isinstance(act_out, dict):
                    act_name = act_out.get('name', '') or act_out.get('action', '')
                    is_terminate = act_out.get('terminate', False)
                    conclusion = act_out.get('observations') or act_out.get('content')
                else:
                    act_name = getattr(act_out, 'name', '') or getattr(act_out, 'action', '')
                    is_terminate = getattr(act_out, 'terminate', False)
                    conclusion = getattr(act_out, 'observations', None) or getattr(act_out, 'content', None)

                if act_name == BlankAction.name or is_terminate:
                    if conclusion and isinstance(conclusion, str) and conclusion.strip():
                        # 用 type=ALL 完整替换，确保 markdown 表格等结构完整渲染
                        text_content = DrskTextContent(
                            dynamic=False,
                            markdown=conclusion,
                            uid=f"{message_id}_'step_thought'",
                            type=UpdateType.ALL.value,
                        )
                        return DrskContent().sync_display(
                            content=text_content.to_dict(exclude_none=True)
                        )
                    return None

        # 非 BlankAction：走父类默认逻辑
        return await super()._gen_plan_items(
            gpt_msg=gpt_msg,
            stream_msg=stream_msg,
            layer_count=layer_count,
            senders_map=senders_map,
        )

    def _process_gpt_message(self, gpt_msg: GptsMessage) -> Optional[ManusExecutionStep]:
        """处理单条 GptsMessage，提取为执行步骤

        支持并行工具调用：当 action_report 包含多个 ActionOutput 时，
        为每个创建独立的执行步骤，确保所有步骤都可点击切换。
        """
        if not gpt_msg:
            return None

        # Multiple action_reports = parallel tool calls → one step per report
        if gpt_msg.action_report and len(gpt_msg.action_report) > 1:
            last_step = None
            for act_out in gpt_msg.action_report:
                step = self._create_step_for_action(gpt_msg, act_out)
                if step:
                    last_step = step
            return last_step

        # Single action_report or none
        single_report = gpt_msg.action_report[0] if gpt_msg.action_report else None
        return self._create_step_for_action(gpt_msg, single_report)

    def _create_step_for_action(
        self, gpt_msg: GptsMessage, act_out=None
    ) -> Optional[ManusExecutionStep]:
        """为单个 ActionOutput 创建执行步骤

        Args:
            gpt_msg: 原始 GptsMessage（用于 fallback 字段如 content, thinking, current_goal）
            act_out: 单个 ActionOutput 对象（可为 None，此时从 content JSON 解析）
        """
        # 提取 action 信息
        action_name = None
        action_input = None
        thought = None
        observation = None

        # 从指定的 act_out 提取
        if act_out:
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

        # Fallback: 从 content JSON 解析（V2 或 fallback）
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

        # BlankAction / terminate — 跳过，不在执行步骤中展示
        is_blank = action_name == BlankAction.name
        if not is_blank and act_out:
            if getattr(act_out, 'name', '') == BlankAction.name or getattr(act_out, 'terminate', False):
                is_blank = True

        if is_blank:
            return None

        self._step_counter += 1
        step_id = f"step_{self._step_counter}"

        title = action_name or self._get_action_report_summary(gpt_msg) or "执行中"

        # 确定阶段
        phase = self._extract_phase_key(thought or content if isinstance(content, str) else "")

        # 确定状态
        status = ManusStepStatus.RUNNING.value
        if act_out:
            is_success = getattr(act_out, 'is_exe_success', True)
            status = ManusStepStatus.COMPLETED.value if is_success else ManusStepStatus.ERROR.value
        elif gpt_msg.current_goal and "failed" in gpt_msg.current_goal.lower():
            status = ManusStepStatus.ERROR.value
        elif self._get_action_report_summary(gpt_msg) and "完成" in self._get_action_report_summary(gpt_msg):
            status = ManusStepStatus.COMPLETED.value

        step = ManusExecutionStep(
            id=step_id,
            type=step_type,
            title=title,
            subtitle=observation[:100] if observation and isinstance(observation, str) else None,
            description=gpt_msg.current_goal,
            phase=phase,
            status=status,
        )

        # 保存思考内容
        if thought:
            self._step_thoughts[step_id] = thought

        # 提取输出
        outputs = []

        if act_out:
            # SQL 步骤特殊处理：提取 d-sql-query VIS tag 中的结构化数据
            if step_type == ManusStepType.SQL.value:
                sql_data = self._extract_sql_query_data(act_out)
                if sql_data:
                    outputs.append(ManusExecutionOutput(
                        output_type=ManusOutputType.SQL_QUERY.value,
                        content=sql_data,
                    ))

            if not outputs:
                # 优先使用 observations/content（实际工具执行结果）
                obs_content = getattr(act_out, 'observations', None)
                act_content = getattr(act_out, 'content', None)
                display_content = obs_content or act_content
                if display_content:
                    if step_type == ManusStepType.BASH.value:
                        out_type = ManusOutputType.TEXT.value
                    elif step_type in (ManusStepType.PYTHON.value,):
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

        # 处理 content 中的各类输出（仅在无 act_out 时作为 fallback）
        if not act_out and isinstance(content, str) and content.strip():
            try:
                content_dict = json.loads(content)
                observation = content_dict.get("observation", "")
                if observation:
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

        # Map planning UID → step_id for click-to-switch
        mapped = False
        if act_out:
            action_id = getattr(act_out, 'action_id', None)
            if not action_id and isinstance(act_out, dict):
                action_id = act_out.get('action_id')
            if action_id:
                self._planning_uid_to_step_id[action_id] = step_id
                self._pending_planning_uids = [
                    (u, n) for u, n in self._pending_planning_uids if u != action_id
                ]
                mapped = True
                logger.debug(f"[manus] direct mapped UID {action_id} → {step_id} (action={action_name})")
        # Fallback: if direct mapping failed, try pending buffer from _act_out_2_plan
        if not mapped and self._pending_planning_uids:
            uid, pname = self._pending_planning_uids.pop(0)
            self._planning_uid_to_step_id[uid] = step_id
            logger.debug(f"[manus] fallback mapped UID {uid} → {step_id} (pending_action={pname}, step_action={action_name})")

        # 添加到对应阶段分组
        section = self._get_or_create_section(phase)
        section.steps.append(step)

        return step

    # Regex to extract JSON from ```d-sql-query\n{...}\n``` VIS tag
    _VIS_SQL_QUERY_RE = re.compile(
        r'```d-sql-query\s*\n(.*?)\n```', re.DOTALL
    )

    def _extract_sql_query_data(self, act_out) -> Optional[Dict[str, Any]]:
        """Extract structured SQL query data from ActionOutput.

        The execute_sql tool returns a d-sql-query VIS tag in its view/content.
        We parse the JSON from it to pass structured data to the frontend.
        """
        # Try all possible fields that might contain the d-sql-query VIS tag
        for attr in ('view', 'simple_view', 'observations', 'content'):
            val = getattr(act_out, attr, None) if hasattr(act_out, attr) else (
                act_out.get(attr) if isinstance(act_out, dict) else None
            )
            if not val or not isinstance(val, str):
                continue
            match = self._VIS_SQL_QUERY_RE.search(val)
            if match:
                try:
                    return json.loads(match.group(1))
                except (json.JSONDecodeError, TypeError):
                    continue
            # Also try parsing as direct JSON (in case content is pure JSON)
            if '"columns"' in val and '"rows"' in val:
                try:
                    data = json.loads(val)
                    if isinstance(data, dict) and 'columns' in data and 'rows' in data:
                        return data
                except (json.JSONDecodeError, TypeError):
                    continue
        return None

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

    @staticmethod
    def _format_outputs_for_map(outputs: List[ManusExecutionOutput]) -> List[Dict[str, Any]]:
        """Format output content for steps_map.

        Note: We do NOT truncate here because ToolAction already handles result size:
        - Large outputs are archived by Truncator (lines 487-516 in tool_action.py)
        - d-attach VIS tag is generated for users to view full content
        - execute_sql, get_table_spec, skill_read etc. are explicitly skipped

        Truncating here would:
        1. Double-truncate already processed content
        2. Break structured data (SQL results JSON)
        3. Confuse users with "... (truncated)" when the full file is already in d-attach

        The steps_map shows ToolAction's output as-is. If ToolAction archived the content,
        the result already contains a truncated version + d-attach link.
        """
        result = []
        for o in outputs:
            d = o.to_dict()
            # Do NOT truncate - ToolAction already handled size management
            result.append(d)
        return result

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

        # Build steps_map: planning UID → step data for click-to-switch
        # Also index by step_id so left panel clicks (which use step_id) work too
        steps_map: Dict[str, Dict[str, Any]] = {}
        for planning_uid, sid in self._planning_uid_to_step_id.items():
            step = self._steps.get(sid)
            if step:
                step_info = ManusActiveStepInfo(
                    id=step.id,
                    type=step.type,
                    title=step.title,
                    subtitle=step.subtitle,
                    status=step.status,
                    detail=step.description,
                )
                step_data = {
                    "active_step": step_info.to_dict(),
                    "outputs": self._format_outputs_for_map(self._outputs.get(sid, [])),
                }
                steps_map[planning_uid] = step_data
                # Also register by step_id for left panel click-to-switch
                if sid not in steps_map:
                    steps_map[sid] = step_data

        # Also add steps that have no planning_uid mapping (e.g. streaming steps)
        for sid, step in self._steps.items():
            if sid not in steps_map:
                step_info = ManusActiveStepInfo(
                    id=step.id,
                    type=step.type,
                    title=step.title,
                    subtitle=step.subtitle,
                    status=step.status,
                    detail=step.description,
                )
                steps_map[sid] = {
                    "active_step": step_info.to_dict(),
                    "outputs": self._format_outputs_for_map(self._outputs.get(sid, [])),
                }

        return ManusRightPanelData(
            active_step=active_step_info,
            outputs=outputs,
            is_running=is_running,
            artifacts=self._artifacts,
            panel_view=panel_view,
            steps_map=steps_map,
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

            # 收集任务文件和交付文件（增量推送时也需要）
            if messages:
                task_files, deliverable_files = self._collect_files_from_messages(messages)
                right_panel.task_files = task_files
                right_panel.deliverable_files = deliverable_files

                # 任务结束时设置摘要和自动切换视图
                if not is_working:
                    # 提取摘要内容
                    for msg in reversed(messages):
                        if msg.role == HUMAN_ROLE:
                            continue
                        if msg.action_report:
                            for act_out in msg.action_report:
                                obs = getattr(act_out, 'observations', None)
                                cnt = getattr(act_out, 'content', None)
                                candidate = obs or cnt
                                if candidate and isinstance(candidate, str) and candidate.strip():
                                    right_panel.summary_content = candidate
                                    break
                        if right_panel.summary_content:
                            break

                    if deliverable_files:
                        right_panel.panel_view = ManusPanelView.DELIVERABLE.value
                    elif right_panel.summary_content:
                        right_panel.panel_view = ManusPanelView.SUMMARY.value

            # DEBUG: log deliverable files before serialization
            if right_panel.deliverable_files:
                for df in right_panel.deliverable_files:
                    logger.info(
                        f"[ManusConverter] RIGHT PANEL deliverable: "
                        f"file_name={df.file_name}, content_url={df.content_url}, "
                        f"download_url={df.download_url}, render_type={df.render_type}"
                    )

            running_window = self._generate_vis_tag_output(
                tag=ManusRightPanel.vis_tag(),
                uid="manus_right_panel",
                data=right_panel.to_dict(),
                update_type=UpdateType.ALL.value,
            )

            # 追加 drsk-deliverable VIS 标签到 planning_window
            if right_panel.deliverable_files or right_panel.task_files:
                deliverable_data = {
                    "deliverable_files": [
                        {
                            "file_id": f.file_id,
                            "file_name": f.file_name,
                            "render_type": f.render_type,
                        }
                        for f in right_panel.deliverable_files
                    ],
                    "task_files_count": len(right_panel.task_files),
                }
                deliverable_vis = self._generate_vis_tag_output(
                    tag=DrskDeliverable.vis_tag(),
                    uid="deliverable_card",
                    data=deliverable_data,
                    update_type=UpdateType.ALL.value,
                )
                if planning_window:
                    planning_window = planning_window + "\n" + deliverable_vis
                else:
                    planning_window = deliverable_vis

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
                # 纯文本流式内容 - LLM 输出，不追加到右面板执行步骤
                # 右面板只展示工具执行结果，LLM 文本在左面板展示
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

            # content 字段（非工具执行的文本内容）是 LLM 输出
            # 右面板只展示工具执行结果，LLM 文本在左面板展示，不追加到右面板
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

        elif msg_type == "response":
            # LLM response 文本不追加到右面板执行步骤，只在左面板展示
            pass

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

            # BlankAction — 跳过，不在执行步骤中展示
            is_blank = action_name == BlankAction.name
            if not is_blank:
                report_name = getattr(report, 'name', '') if hasattr(report, 'name') else (report.get('name', '') if isinstance(report, dict) else '')
                is_blank = report_name == BlankAction.name
            if not is_blank:
                is_terminate = getattr(report, 'terminate', False) if hasattr(report, 'terminate') else (report.get('terminate', False) if isinstance(report, dict) else False)
                is_blank = is_terminate

            if is_blank:
                continue

            display_title = action_name

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

            # Map planning UID → step_id for click-to-switch (direct by action_id)
            mapped = False
            report_action_id = getattr(report, 'action_id', None) if hasattr(report, 'action_id') else (report.get('action_id') if isinstance(report, dict) else None)
            if report_action_id:
                self._planning_uid_to_step_id[report_action_id] = step_id
                self._pending_planning_uids = [
                    (u, n) for u, n in self._pending_planning_uids if u != report_action_id
                ]
                mapped = True
                logger.debug(f"[manus] direct mapped UID {report_action_id} → {step_id} (action={action_name})")
            if not mapped and self._pending_planning_uids:
                uid, pname = self._pending_planning_uids.pop(0)
                self._planning_uid_to_step_id[uid] = step_id
                logger.debug(f"[manus] fallback mapped UID {uid} → {step_id} (pending_action={pname}, step_action={action_name})")

            section = self._get_or_create_section(None)
            section.steps.append(step)

            # 保存思考
            if thought:
                self._step_thoughts[step_id] = thought

            # 提取输出
            # SQL 步骤特殊处理：提取 d-sql-query VIS tag 中的结构化数据
            if step_type == ManusStepType.SQL.value:
                sql_data = self._extract_sql_query_data(report)
                if sql_data:
                    self._outputs.setdefault(step_id, []).append(
                        ManusExecutionOutput(output_type=ManusOutputType.SQL_QUERY.value, content=sql_data)
                    )
                    continue

            # 使用 observations/content（实际工具结果），不使用 view（VIS 标记）
            display_content = observations or content
            if display_content:
                out_type = ManusOutputType.TEXT.value
                if step_type in (ManusStepType.PYTHON.value,):
                    out_type = ManusOutputType.CODE.value
                elif step_type == ManusStepType.HTML.value:
                    out_type = ManusOutputType.HTML.value
                self._outputs.setdefault(step_id, []).append(
                    ManusExecutionOutput(output_type=out_type, content=display_content)
                )

    async def _render_terminate_files(
        self,
        messages: List["GptsMessage"],
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ) -> Optional[str]:
        """覆写父类方法 - Manus 布局的文件展示由右面板 tab 负责，不走 d-attach-list"""
        return None

    @staticmethod
    def _determine_render_type(file_name: str, mime_type: Optional[str] = None) -> str:
        """根据文件名和 mime_type 确定渲染类型"""
        name_lower = (file_name or "").lower()
        mime_lower = (mime_type or "").lower()

        # HTML
        if name_lower.endswith(".html") or name_lower.endswith(".htm") or "text/html" in mime_lower:
            return "iframe"
        # Markdown
        if name_lower.endswith(".md") or "text/markdown" in mime_lower:
            return "markdown"
        # Image
        if any(name_lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            return "image"
        if mime_lower.startswith("image/"):
            return "image"
        # PDF
        if name_lower.endswith(".pdf") or "application/pdf" in mime_lower:
            return "pdf"
        # Code
        code_exts = (".py", ".js", ".ts", ".java", ".go", ".rs", ".sql", ".yaml", ".yml", ".json", ".xml", ".css", ".sh")
        if any(name_lower.endswith(ext) for ext in code_exts):
            return "code"
        # Plain text
        if name_lower.endswith(".txt") or name_lower.endswith(".log") or "text/plain" in mime_lower:
            return "text"
        # Default
        return "iframe"

    def _collect_files_from_messages(
        self, messages: List["GptsMessage"]
    ) -> tuple:
        """从所有消息的 action_report[].output_files 中提取文件信息

        Returns:
            (task_files: List[ManusTaskFileItem], deliverable_files: List[ManusDeliverableFile])
        """
        task_files: List[ManusTaskFileItem] = []
        deliverable_files: List[ManusDeliverableFile] = []
        seen_file_ids = set()

        for msg in messages:
            if not msg.action_report:
                continue
            for action_out in msg.action_report:
                if isinstance(action_out, dict):
                    output_files = action_out.get("output_files") or []
                else:
                    output_files = getattr(action_out, "output_files", None) or []

                for file_info in output_files:
                    if not isinstance(file_info, dict):
                        continue
                    file_id = file_info.get("file_id", "")
                    if not file_id or file_id in seen_file_ids:
                        continue
                    seen_file_ids.add(file_id)

                    file_name = file_info.get("file_name", "")
                    file_type = file_info.get("file_type", "")
                    mime_type = file_info.get("mime_type")

                    # 所有文件都加入 task_files
                    task_files.append(ManusTaskFileItem(
                        file_id=file_id,
                        file_name=file_name,
                        file_type=file_type,
                        file_size=file_info.get("file_size", 0),
                        mime_type=mime_type,
                        oss_url=file_info.get("oss_url"),
                        preview_url=file_info.get("preview_url"),
                        download_url=file_info.get("download_url"),
                        description=file_info.get("description"),
                        created_at=file_info.get("created_at"),
                        object_path=file_info.get("object_path"),
                    ))

                    # 仅 deliverable 类型的文件获得独立 tab
                    if file_type == "deliverable":
                        # 优先使用 derisk-fs:// URI 作为 content_url，
                        # 前端通过 /api/v2/serve/file/files/preview 代理加载，
                        # 避免直接用 OSS HTTPS URL 在 iframe 中受 X-Frame-Options 限制。
                        oss_url = file_info.get("oss_url")
                        preview_url = file_info.get("preview_url")
                        if oss_url and oss_url.startswith("derisk-fs://"):
                            content_url = oss_url
                        else:
                            content_url = preview_url or oss_url
                        logger.info(
                            f"[ManusConverter] deliverable file_info keys: "
                            f"file_name={file_name}, file_type={file_type}, "
                            f"preview_url={preview_url}, "
                            f"oss_url={oss_url}, "
                            f"download_url={file_info.get('download_url')}, "
                            f"object_path={file_info.get('object_path')}, "
                            f"content_url(resolved)={content_url}"
                        )
                        deliverable_files.append(ManusDeliverableFile(
                            file_id=file_id,
                            file_name=file_name,
                            mime_type=mime_type,
                            file_size=file_info.get("file_size", 0),
                            content_url=content_url,
                            download_url=file_info.get("download_url") or preview_url,
                            object_path=file_info.get("object_path"),
                            render_type=self._determine_render_type(file_name, mime_type),
                        ))

        return task_files, deliverable_files

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

        # 收集任务文件和交付文件
        task_files, deliverable_files = self._collect_files_from_messages(messages)
        right_panel.task_files = task_files
        right_panel.deliverable_files = deliverable_files

        if messages:
            last_msg = messages[-1]
            if last_msg.role != HUMAN_ROLE:
                # 优先从 action_report 提取完整结论内容（observations > content），
                # last_msg.content 可能只是 agent 的 thinking/response 文本，不含完整输出
                summary = None
                if last_msg.action_report:
                    for act_out in last_msg.action_report:
                        obs = getattr(act_out, 'observations', None)
                        cnt = getattr(act_out, 'content', None)
                        candidate = obs or cnt
                        if candidate and isinstance(candidate, str) and candidate.strip():
                            summary = candidate
                            break
                if not summary and last_msg.content:
                    summary = last_msg.content
                if summary:
                    right_panel.summary_content = summary

        # 确定 panel_view：交付文件优先 > 摘要
        if deliverable_files:
            right_panel.panel_view = ManusPanelView.DELIVERABLE.value
        elif right_panel.summary_content:
            right_panel.panel_view = ManusPanelView.SUMMARY.value

        right_vis = self._generate_vis_tag_output(
            tag=ManusRightPanel.vis_tag(),
            uid="manus_right_panel",
            data=right_panel.to_dict(),
            update_type=UpdateType.ALL.value,
        )

        # 构建 drsk-deliverable VIS 标签追加到 planning_window
        deliverable_vis = ""
        if deliverable_files or task_files:
            deliverable_data = {
                "deliverable_files": [
                    {
                        "file_id": f.file_id,
                        "file_name": f.file_name,
                        "render_type": f.render_type,
                    }
                    for f in deliverable_files
                ],
                "task_files_count": len(task_files),
            }
            deliverable_vis = self._generate_vis_tag_output(
                tag=DrskDeliverable.vis_tag(),
                uid="deliverable_card",
                data=deliverable_data,
                update_type=UpdateType.ALL.value,
            )

        # 替换 running_window 为 manus right panel
        if parent_result:
            try:
                result_data = json.loads(parent_result)
                result_data["running_window"] = right_vis
                # 追加 deliverable VIS 标签到 planning_window
                if deliverable_vis:
                    pw = result_data.get("planning_window") or ""
                    result_data["planning_window"] = (
                        pw + "\n" + deliverable_vis if pw else deliverable_vis
                    )
                return json.dumps(result_data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass

        return json.dumps(
            {
                "planning_window": deliverable_vis,
                "running_window": right_vis,
            },
            ensure_ascii=False,
        )

    async def _footer_vis_build(
        self,
        gpt_msg: "GptsMessage",
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ) -> Optional[str]:
        """Manus 布局不在 planning_window 渲染最终结论，结论已在右侧面板 summary tab 展示。"""
        return None

    async def _render_final_conclusion(
        self, output_message: GptsMessage
    ) -> Optional[str]:
        """渲染最终结论 - 覆写父类方法，优先使用 observations/content 而非 view

        父类 _render_final_conclusion 优先使用 action_report.view，
        但 view 可能包含 VIS tag 标记（如 ```d-tool {...}```），
        导致在 DrskContent 中作为 markdown 渲染时出现问题。
        """
        conclusion_content = None

        def _get_val(action_out, key, default=None):
            if isinstance(action_out, dict):
                return action_out.get(key, default)
            return getattr(action_out, key, default)

        # 从 terminate action 提取结论 - 优先 observations/content，避免 view 中的 VIS 标记
        if output_message.action_report:
            for action_out in output_message.action_report:
                if _get_val(action_out, "terminate"):
                    conclusion_content = (
                        _get_val(action_out, "observations")
                        or _get_val(action_out, "content")
                        or _get_val(action_out, "view")
                    )
                    if conclusion_content:
                        break

        # fallback: 发给用户的消息
        if not conclusion_content and output_message.receiver == HUMAN_ROLE:
            if output_message.action_report:
                for action_out in output_message.action_report:
                    conclusion_content = (
                        _get_val(action_out, "observations")
                        or _get_val(action_out, "content")
                        or _get_val(action_out, "view")
                    )
                    if conclusion_content:
                        break
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
