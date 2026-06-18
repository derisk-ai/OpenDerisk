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
from typing import List, Optional, Dict, Union, Any, Tuple

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
from derisk.vis.vis_manus_protocol import (
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


def _normalize_text_for_dedup(text: Optional[Any]) -> str:
    """Normalize streamed/final text for dedup comparison."""
    if not isinstance(text, str):
        return ""
    normalized = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    return normalized


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

    MAX_STEPS_IN_MAP = 100

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
        self._agent_name: Optional[str] = None

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
                display_name = "执行步骤"
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

    @staticmethod
    def _is_duplicate_final_summary(
        candidate: Optional[str], final_summary: Optional[str]
    ) -> bool:
        """Whether a streamed/tool step content duplicates the final summary."""
        candidate_text = _normalize_text_for_dedup(candidate)
        final_text = _normalize_text_for_dedup(final_summary)
        if not candidate_text or not final_text:
            return False
        return candidate_text == final_text or final_text.startswith(candidate_text)

    def _remove_duplicate_summary_steps(self, final_summary: Optional[str]):
        """Remove streamed conclusion steps once a final summary is available."""
        if not final_summary:
            return

        duplicate_step_ids = []
        for step_id, outputs in list(self._outputs.items()):
            if not outputs:
                continue

            step = self._steps.get(step_id)
            if step and step.action and step.action.lower() in ("batch_tasks", "batchtasks"):
                continue

            output_texts = [
                out.content
                for out in outputs
                if isinstance(getattr(out, 'content', None), str)
            ]
            subtitle = step.subtitle if step else None
            candidate_texts = output_texts + ([subtitle] if subtitle else [])

            if any(self._is_duplicate_final_summary(text, final_summary) for text in candidate_texts):
                duplicate_step_ids.append(step_id)

        if not duplicate_step_ids:
            return

        duplicate_set = set(duplicate_step_ids)
        for step_id in duplicate_step_ids:
            self._steps.pop(step_id, None)
            self._outputs.pop(step_id, None)
            self._step_thoughts.pop(step_id, None)

        for section in self._sections.values():
            section.steps = [step for step in section.steps if step.id not in duplicate_set]

        self._planning_uid_to_step_id = {
            uid: sid
            for uid, sid in self._planning_uid_to_step_id.items()
            if sid not in duplicate_set
        }

        if self._active_step_id in duplicate_set:
            self._active_step_id = None
            if self._steps:
                self._active_step_id = next(reversed(self._steps))

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

                is_batch = act_name.lower() in ("batchtasks", "batch_tasks")
                if not is_batch and (act_name == BlankAction.name or is_terminate):
                    if conclusion and isinstance(conclusion, str) and conclusion.strip():
                        # 用 type=ALL 完整替换，确保 markdown 表格等结构完整渲染
                        text_content = DrskTextContent(
                            dynamic=False,
                            markdown=conclusion,
                            uid=f"{message_id}_planning_content",
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
        # batch_tasks 虽然 terminate=True（sync模式），但需要展示在执行步骤中
        is_batch_task = action_name and action_name.lower() in ("batchtasks", "batch_tasks")
        is_blank = action_name == BlankAction.name
        if not is_blank and act_out and not is_batch_task:
            if getattr(act_out, 'name', '') == BlankAction.name or getattr(act_out, 'terminate', False):
                is_blank = True

        if is_blank:
            return None

        self._step_counter += 1
        # 使用 message_id 前缀确保跨轮次步骤 ID 唯一，避免前端映射覆盖
        msg_id_prefix = gpt_msg.message_id[:8] if gpt_msg.message_id else "unknown"
        step_id = f"step_{msg_id_prefix}_{self._step_counter}"

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

        # batch_tasks：将 view 中的 d-batch-tasks 数据合并到 action_input，供 TaskRenderer 使用
        if is_batch_task and act_out:
            batch_view_data = None
            view_str = getattr(act_out, 'view', None)
            if view_str and 'd-batch-tasks' in str(view_str):
                try:
                    start = view_str.find('\n', view_str.find('d-batch-tasks')) + 1
                    end = view_str.rfind('```')
                    if start > 0 and end > start:
                        batch_view_data = json.loads(view_str[start:end])
                except (json.JSONDecodeError, ValueError):
                    pass
            if not batch_view_data:
                extra = getattr(act_out, 'extra', None) or {}
                batch_view_data = {
                    'batch_id': extra.get('batch_id', ''),
                    'mode': extra.get('mode', 'async'),
                    'total': extra.get('total', 0),
                    'completed': 0,
                    'failed': 0,
                    'tasks': [],
                }
            if batch_view_data:
                if isinstance(action_input, dict):
                    action_input = {**action_input, **batch_view_data}
                else:
                    action_input = batch_view_data

        step = ManusExecutionStep(
            id=step_id,
            type=step_type,
            title=title,
            subtitle=observation[:100] if observation and isinstance(observation, str) else None,
            description=gpt_msg.current_goal,
            phase=phase,
            status=status,
            action=action_name,
            action_input=action_input,
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
        # Prioritize 'content' field as it contains the raw d-sql-query output
        # 'view' contains VisStepContent JSON where newlines are escaped, breaking regex
        for attr in ('content', 'view', 'simple_view', 'observations'):
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
            # Must check for 'sql' field to distinguish from VisStepContent JSON
            if '"columns"' in val and '"rows"' in val and '"sql"' in val:
                try:
                    data = json.loads(val)
                    if isinstance(data, dict) and 'columns' in data and 'rows' in data and 'sql' in data:
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
    def _build_left_panel_from_steps(
        steps: List[ManusExecutionStep],
        active_step_id: Optional[str] = None,
        is_working: bool = False,
    ) -> ManusLeftPanelData:
        """从无状态步骤列表构建左面板数据（用于 visualization/final_view）。

        步骤按 phase 分组；无 phase 的归入默认 section。
        """
        sections_map: Dict[str, ManusThinkingSection] = {}
        for step in steps:
            phase_key = step.phase or "default"
            if phase_key not in sections_map:
                display_name = PHASE_DISPLAY_MAP.get(phase_key, phase_key)
                if phase_key == "default":
                    display_name = "执行步骤"
                sections_map[phase_key] = ManusThinkingSection(
                    id=f"section_{phase_key}",
                    title=display_name,
                )
            sections_map[phase_key].steps.append(step)

        sections = list(sections_map.values())
        for section in sections:
            all_done = all(
                s.status in (ManusStepStatus.COMPLETED.value, ManusStepStatus.ERROR.value)
                for s in section.steps
            ) if section.steps else False
            section.is_completed = all_done

        return ManusLeftPanelData(
            sections=sections,
            active_step_id=active_step_id,
            is_working=is_working,
        )

    @staticmethod
    def _outputs_to_dict_list(outputs: List[ManusExecutionOutput]) -> List[Dict[str, Any]]:
        """Convert outputs to dict list for steps_map."""
        return [o.to_dict() for o in outputs]

    def _build_right_panel_data(self, is_running: bool = False, agent_name: Optional[str] = None, lazy_mode: bool = False) -> ManusRightPanelData:
        """构建右面板数据

        Args:
            is_running: 是否运行中
            agent_name: Agent 名称
            lazy_mode: 按需加载模式。True 时 steps_map 只保留步骤元信息（无 outputs），
                      前端通过 /nexa/chat/step_detail API 按需获取步骤详情。
                      用于 final_view / 历史回放场景，减少数据量。
        """
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
                action=step.action,
                action_input=step.action_input,
            )
            outputs = self._outputs.get(self._active_step_id, [])

        # 确定面板视图
        panel_view = ManusPanelView.EXECUTION.value
        if active_step_info:
            if active_step_info.type == ManusStepType.HTML.value:
                panel_view = ManusPanelView.HTML_PREVIEW.value
            elif active_step_info.type == ManusStepType.SKILL.value:
                panel_view = ManusPanelView.SKILL_PREVIEW.value

        def _step_to_info(step: ManusExecutionStep) -> ManusActiveStepInfo:
            return ManusActiveStepInfo(
                id=step.id,
                type=step.type,
                title=step.title,
                subtitle=step.subtitle,
                status=step.status,
                detail=step.description,
                action=step.action,
                action_input=step.action_input,
            )

        # Build steps_map: planning UID → step data for click-to-switch
        # Also index by step_id so left panel clicks (which use step_id) work too
        steps_map: Dict[str, Dict[str, Any]] = {}

        # Build steps_map: all entries include outputs so frontend click-to-switch works
        for planning_uid, sid in self._planning_uid_to_step_id.items():
            step = self._steps.get(sid)
            if step:
                step_data = {
                    "active_step": _step_to_info(step).to_dict(),
                    "outputs": self._outputs_to_dict_list(self._outputs.get(sid, [])),
                }
                steps_map[planning_uid] = step_data
                if sid not in steps_map:
                    steps_map[sid] = step_data

        for sid, step in self._steps.items():
            if sid not in steps_map:
                steps_map[sid] = {
                    "active_step": _step_to_info(step).to_dict(),
                    "outputs": self._outputs_to_dict_list(self._outputs.get(sid, [])),
                }

        meta = {
            "total_steps": len(self._steps),
            "default_step_id": self._active_step_id,
        } if lazy_mode else None

        return ManusRightPanelData(
            active_step=active_step_info,
            outputs=outputs,
            is_running=is_running,
            artifacts=self._artifacts,
            panel_view=panel_view,
            steps_map=steps_map,
            agent_name=agent_name,
            lazy_loading=lazy_mode,
            meta=meta,
        )

    def _extract_step_from_gpt_msg(
        self, gpt_msg: "GptsMessage"
    ) -> Tuple[Optional[ManusActiveStepInfo], List[ManusExecutionOutput]]:
        """从 gpt_msg 提取当前 step 信息（无副作用，不写 self 状态）."""
        if not gpt_msg or not gpt_msg.action_report:
            return None, []

        act_out = None
        for ao in reversed(gpt_msg.action_report if isinstance(gpt_msg.action_report, list) else [gpt_msg.action_report]):
            act_name = getattr(ao, 'action', None) or getattr(ao, 'action_name', None) or getattr(ao, 'name', None)
            if act_name != BlankAction.name:
                act_out = ao
                break

        if not act_out:
            return None, []

        action_name = getattr(act_out, 'action', None) or getattr(act_out, 'action_name', None) or getattr(act_out, 'name', None)
        action_input = getattr(act_out, 'action_input', None)
        observation = getattr(act_out, 'observations', None) or getattr(act_out, 'content', None)
        is_success = getattr(act_out, 'is_exe_success', True)
        action_id = getattr(act_out, 'action_id', None) or ""

        step_info = ManusActiveStepInfo(
            id=action_id,
            type=self._map_action_to_step_type(action_name, action_input),
            title=action_name or "执行中",
            subtitle=observation[:100] if observation and isinstance(observation, str) else None,
            status=ManusStepStatus.COMPLETED.value if is_success else ManusStepStatus.ERROR.value,
            action=action_name,
            action_input=action_input,
        )

        outputs = []
        if observation and isinstance(observation, str):
            outputs.append(ManusExecutionOutput(
                output_type=ManusOutputType.TEXT.value,
                content=observation,
            ))

        return step_info, outputs

    def _extract_step_from_stream_msg(
        self, stream_msg: Union[Dict, str], is_first_chunk: bool = False
    ) -> Tuple[Optional[ManusActiveStepInfo], List[ManusExecutionOutput]]:
        """从 stream_msg 提取当前 step 信息（无副作用，不写 self 状态）."""
        if not stream_msg:
            return None, []

        if isinstance(stream_msg, str):
            return None, []

        action_report = stream_msg.get("action_report")
        if not action_report:
            return None, []

        act_out = action_report[-1] if isinstance(action_report, list) else action_report
        action_name = getattr(act_out, 'action', None) or getattr(act_out, 'action_name', None)
        if not action_name and isinstance(act_out, dict):
            action_name = act_out.get('action') or act_out.get('action_name') or act_out.get('name')

        action_input = getattr(act_out, 'action_input', None)
        if not action_input and isinstance(act_out, dict):
            action_input = act_out.get('action_input')

        observation = getattr(act_out, 'observations', None) or getattr(act_out, 'content', None)
        if not observation and isinstance(act_out, dict):
            observation = act_out.get('observations') or act_out.get('content')

        action_id = getattr(act_out, 'action_id', None) or ""
        if not action_id and isinstance(act_out, dict):
            action_id = act_out.get('action_id', '')

        if not action_name:
            return None, []

        step_info = ManusActiveStepInfo(
            id=action_id,
            type=self._map_action_to_step_type(action_name, action_input),
            title=action_name or "执行中",
            subtitle=observation[:100] if observation and isinstance(observation, str) else None,
            status=ManusStepStatus.RUNNING.value,
            action=action_name,
            action_input=action_input,
        )

        outputs = []
        if observation and isinstance(observation, str):
            outputs.append(ManusExecutionOutput(
                output_type=ManusOutputType.TEXT.value,
                content=observation,
            ))

        return step_info, outputs

    async def render_step_detail(
        self,
        gpt_msg: "GptsMessage",
        step_uid: str,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ) -> Optional[Dict]:
        """Manus layout: render step detail with manus-specific VIS components.
        
        追问场景：用户点击历史步骤时，返回该步骤的详情和对应的任务文件。
        """
        vis_text = await self._gen_plan_items(gpt_msg=gpt_msg, senders_map=senders_map)

        step_info, outputs = self._extract_step_from_gpt_msg(gpt_msg)

        if step_info and gpt_msg.action_report:
            for act_out in (gpt_msg.action_report if isinstance(gpt_msg.action_report, list) else [gpt_msg.action_report]):
                if step_info.type == ManusStepType.SQL.value:
                    sql_data = self._extract_sql_query_data(act_out)
                    if sql_data:
                        outputs = [ManusExecutionOutput(
                            output_type=ManusOutputType.SQL_QUERY.value,
                            content=sql_data,
                        )]
                        break

        # 收集该消息的任务文件（点击历史步骤时展示）
        task_files: List[ManusTaskFileItem] = []
        deliverable_files: List[ManusDeliverableFile] = []
        if gpt_msg:
            task_files, deliverable_files = self._collect_files_from_messages([gpt_msg])

        step_data = None
        if step_info:
            step_data = {
                "active_step": step_info.to_dict(),
                "outputs": [o.to_dict() for o in outputs],
                "task_files": [f.to_dict() for f in task_files],
                "deliverable_files": [f.to_dict() for f in deliverable_files],
            }

        return {
            "vis_content": vis_text or "",
            "step_data": step_data,
        }

    def _build_steps_from_messages_stateless(
        self, messages: List["GptsMessage"]
    ) -> Tuple[Dict[str, Dict[str, Any]], Optional[ManusActiveStepInfo], List[ManusExecutionOutput]]:
        """从 messages 无状态构建 steps_map、active_step_info 和 outputs。

        不依赖 self._steps 等单例状态，避免并发冲突和数据泄漏。
        """
        local_steps: Dict[str, ManusExecutionStep] = {}
        local_uid_map: Dict[str, str] = {}
        local_outputs: Dict[str, list] = {}
        step_counter = 0

        if messages:
            for msg in messages:
                if msg.role == HUMAN_ROLE:
                    continue
                if not msg.action_report:
                    continue
                for act_out in (msg.action_report if isinstance(msg.action_report, list) else [msg.action_report]):
                    action_name = getattr(act_out, 'action', None) or getattr(act_out, 'action_name', None) or getattr(act_out, 'name', None)
                    is_blank = action_name == BlankAction.name
                    if not is_blank and getattr(act_out, 'terminate', False):
                        is_batch = action_name and action_name.lower() in ("batchtasks", "batch_tasks")
                        if not is_batch:
                            is_blank = True
                    if is_blank:
                        continue

                    step_counter += 1
                    # 使用 message_id 前缀确保跨轮次步骤 ID 唯一
                    msg_id_prefix = msg.message_id[:8] if msg.message_id else "unknown"
                    step_id = f"step_{msg_id_prefix}_{step_counter}"
                    action_input = getattr(act_out, 'action_input', None)
                    observation = getattr(act_out, 'observations', None) or getattr(act_out, 'content', None)

                    step = ManusExecutionStep(
                        id=step_id,
                        type=self._map_action_to_step_type(action_name, action_input),
                        title=action_name or "执行中",
                        subtitle=observation[:100] if observation and isinstance(observation, str) else None,
                        description=msg.current_goal,
                        status=ManusStepStatus.COMPLETED.value if getattr(act_out, 'is_exe_success', True) else ManusStepStatus.ERROR.value,
                        action=action_name,
                        action_input=action_input,
                    )
                    local_steps[step_id] = step

                    action_id = getattr(act_out, 'action_id', None)
                    if action_id:
                        local_uid_map[action_id] = step_id

                    if observation and isinstance(observation, str):
                        # SQL 步骤特殊处理：提取 d-sql-query VIS Tag 中的结构化数据
                        if step.type == ManusStepType.SQL.value:
                            sql_data = self._extract_sql_query_data(act_out)
                            if sql_data:
                                local_outputs[step_id] = [ManusExecutionOutput(
                                    output_type=ManusOutputType.SQL_QUERY.value,
                                    content=sql_data,
                                )]
                                continue
                        local_outputs[step_id] = [ManusExecutionOutput(
                            output_type=ManusOutputType.TEXT.value,
                            content=observation,
                        )]

        def _step_to_info(s: ManusExecutionStep) -> ManusActiveStepInfo:
            return ManusActiveStepInfo(
                id=s.id, type=s.type, title=s.title,
                subtitle=s.subtitle, status=s.status,
                detail=s.description, action=s.action,
                action_input=s.action_input,
            )

        steps_map: Dict[str, Dict[str, Any]] = {}
        last_sid = list(local_steps.keys())[-1] if local_steps else None
        for uid, sid in local_uid_map.items():
            step = local_steps.get(sid)
            if step:
                step_data = {
                    "active_step": _step_to_info(step).to_dict(),
                    "outputs": self._outputs_to_dict_list(local_outputs.get(sid, [])),
                }
                steps_map[uid] = step_data
                if sid not in steps_map:
                    steps_map[sid] = step_data
        for sid, step in local_steps.items():
            if sid not in steps_map:
                steps_map[sid] = {
                    "active_step": _step_to_info(step).to_dict(),
                    "outputs": self._outputs_to_dict_list(local_outputs.get(sid, [])),
                }

        total_step_count = len(local_steps)
        if len(steps_map) > self.MAX_STEPS_IN_MAP:
            keep_sids = set(list(local_steps.keys())[-self.MAX_STEPS_IN_MAP:])
            steps_map = {
                k: v for k, v in steps_map.items()
                if k in keep_sids or local_uid_map.get(k) in keep_sids
            }

        last_step = list(local_steps.values())[-1] if local_steps else None
        active_step_info = _step_to_info(last_step) if last_step else None
        current_outputs = local_outputs.get(last_step.id, []) if last_step else []

        return steps_map, active_step_info, current_outputs

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
        if main_agent_name:
            self._agent_name = main_agent_name
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
            # 追问场景：messages 为空时，从 gpts_memory 加载历史 messages 构建 steps_map
            # 但不加载历史交付文件（每轮对话只展示自己的交付文件）
            if not messages and conv_id and senders_map and main_agent_name:
                main_agent = senders_map.get(main_agent_name)
                if main_agent and hasattr(main_agent, "memory") and hasattr(main_agent.memory, "gpts_memory"):
                    try:
                        from derisk.agent.core.memory.gpts import GptsMemory
                        gpts_memory = main_agent.memory.gpts_memory
                        if isinstance(gpts_memory, GptsMemory):
                            messages = await gpts_memory.get_messages_with_work_entries(conv_id)
                            logger.debug(
                                f"[ManusConverter] Loaded {len(messages)} messages from gpts_memory "
                                f"for conv_id={conv_id} (追问场景构建 steps_map)"
                            )
                    except Exception as e:
                        logger.warning(f"[ManusConverter] Failed to load messages from gpts_memory: {e}")

            # 无状态构建：从 messages 构建 steps_map 和 active_step，叠加当前消息
            steps_map, active_step_info, current_outputs = self._build_steps_from_messages_stateless(
                messages
            )

            # 叠加当前消息的步骤（gpt_msg 或 stream_msg 优先）
            if gpt_msg and gpt_msg.role != HUMAN_ROLE:
                step_info, outputs = self._extract_step_from_gpt_msg(gpt_msg)
                if step_info:
                    active_step_info = step_info
                    current_outputs = outputs
            elif stream_msg:
                step_info, outputs = self._extract_step_from_stream_msg(
                    stream_msg, is_first_chunk
                )
                if step_info:
                    active_step_info = step_info
                    current_outputs = outputs

            right_panel = ManusRightPanelData(
                active_step=active_step_info,
                outputs=current_outputs,
                is_running=is_working,
                steps_map=steps_map,
                agent_name=self._agent_name,
            )

            # 收集任务文件和交付文件
            # 对话结束时（is_working=False），优先从 gpts_memory.list_files 获取
            # 增量推送时（is_working=True），从 messages 收集
            task_files: List[ManusTaskFileItem] = []
            deliverable_files: List[ManusDeliverableFile] = []

            if not is_working and conv_id and senders_map and main_agent_name:
                # 对话结束时，从 gpts_memory 获取完整文件列表
                task_files, deliverable_files = await self._collect_files_from_gpts_memory(
                    conv_id, senders_map, main_agent_name
                )
                logger.info(
                    f"[ManusConverter] visualization end: collected {len(deliverable_files)} deliverable files from gpts_memory"
                )

            # Fallback: 从 messages 收集
            if not deliverable_files and messages:
                task_files, deliverable_files = self._collect_files_from_messages(messages)
                logger.info(
                    f"[ManusConverter] visualization fallback: collected {len(deliverable_files)} deliverable files from messages"
                )

            right_panel.task_files = task_files
            right_panel.deliverable_files = deliverable_files

            # 任务结束时设置摘要和自动切换视图
            if not is_working and messages:
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
                    logger.debug(
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

            # Planning window eviction
            eviction_vis = self._check_and_evict()
            if eviction_vis:
                if planning_window:
                    planning_window = planning_window + "\n" + eviction_vis
                else:
                    planning_window = eviction_vis

            if planning_window or running_window:
                return json.dumps(
                    {
                        "planning_window": planning_window,
                        "running_window": running_window,
                        "meta_window": self._build_meta_window(),
                    },
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
                action=tool_name,
                action_input=tool_input,
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
            # batch_tasks 虽然 terminate=True，但需要展示
            is_batch = action_name and action_name.lower() in ("batchtasks", "batch_tasks")
            is_blank = action_name == BlankAction.name
            if not is_blank:
                report_name = getattr(report, 'name', '') if hasattr(report, 'name') else (report.get('name', '') if isinstance(report, dict) else '')
                is_blank = report_name == BlankAction.name
            if not is_blank and not is_batch:
                is_terminate = getattr(report, 'terminate', False) if hasattr(report, 'terminate') else (report.get('terminate', False) if isinstance(report, dict) else False)
                is_blank = is_terminate

            if is_blank:
                continue

            display_title = action_name

            # 创建新步骤
            self._step_counter += 1
            
            # 优先使用 action_id 作为 step_id 的一部分，确保全局唯一
            report_action_id = getattr(report, 'action_id', None) if hasattr(report, 'action_id') else (report.get('action_id') if isinstance(report, dict) else None)
            if report_action_id:
                # 使用 action_id 的后8位作为前缀，确保跨轮次唯一
                action_id_prefix = report_action_id[:8]
                step_id = f"step_{action_id_prefix}_{self._step_counter}"
            else:
                step_id = f"step_{self._step_counter}"
            
            step_type = self._map_action_to_step_type(action_name, action_input)

            # batch_tasks：将 view 中的 d-batch-tasks 数据合并到 action_input
            if is_batch:
                batch_view_data = None
                view_str = getattr(report, 'view', None) if hasattr(report, 'view') else (report.get('view') if isinstance(report, dict) else None)
                if view_str and 'd-batch-tasks' in str(view_str):
                    try:
                        start = view_str.find('\n', view_str.find('d-batch-tasks')) + 1
                        end = view_str.rfind('```')
                        if start > 0 and end > start:
                            batch_view_data = json.loads(view_str[start:end])
                    except (json.JSONDecodeError, ValueError):
                        pass
                if not batch_view_data:
                    extra = getattr(report, 'extra', None) if hasattr(report, 'extra') else (report.get('extra') if isinstance(report, dict) else None)
                    extra = extra or {}
                    batch_view_data = {
                        'batch_id': extra.get('batch_id', ''),
                        'mode': extra.get('mode', 'async'),
                        'total': extra.get('total', 0),
                        'completed': 0,
                        'failed': 0,
                        'tasks': [],
                    }
                if batch_view_data:
                    if isinstance(action_input, dict):
                        action_input = {**action_input, **batch_view_data}
                    else:
                        action_input = batch_view_data

            step = ManusExecutionStep(
                id=step_id,
                type=step_type,
                title=display_title,
                status=ManusStepStatus.COMPLETED.value if is_success else ManusStepStatus.ERROR.value,
                action=action_name,
                action_input=action_input,
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
        # Archive (zip, rar, 7z, tar, gz)
        archive_exts = (".zip", ".rar", ".7z", ".tar", ".gz", ".tar.gz", ".tgz")
        if any(name_lower.endswith(ext) for ext in archive_exts):
            return "archive"
        archive_mimes = ("application/zip", "application/x-rar-compressed", "application/x-7z-compressed",
                         "application/x-tar", "application/gzip", "application/x-gzip")
        if any(mime in mime_lower for mime in archive_mimes):
            return "archive"
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

        logger.info(f"[ManusConverter] _collect_files_from_messages: {len(messages)} messages to scan")
        for msg in messages:
            if not msg.action_report:
                continue
            for action_out in msg.action_report:
                if isinstance(action_out, dict):
                    output_files = action_out.get("output_files") or []
                else:
                    output_files = getattr(action_out, "output_files", None) or []

                if output_files:
                    logger.info(f"[ManusConverter] Found {len(output_files)} output_files in action_report")

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

                    if file_type == "deliverable":
                        oss_url = file_info.get("oss_url")
                        preview_url = file_info.get("preview_url")
                        if oss_url and oss_url.startswith("derisk-fs://"):
                            content_url = oss_url
                        else:
                            content_url = preview_url or oss_url
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

        logger.info(f"[ManusConverter] _collect_files_from_messages result: task={len(task_files)}, deliverable={len(deliverable_files)}")
        return task_files, deliverable_files

    async def _collect_files_from_gpts_memory(
        self, conv_id: str, senders_map: Optional[Dict[str, "ConversableAgent"]] = None, 
        main_agent_name: Optional[str] = None
    ) -> tuple:
        """从 gpts_memory.list_files 获取文件信息（BAIZE agent 主路径）

        Args:
            conv_id: 会话ID
            senders_map: Agent映射
            main_agent_name: 主Agent名称

        Returns:
            (task_files: List[ManusTaskFileItem], deliverable_files: List[ManusDeliverableFile])
        """
        task_files: List[ManusTaskFileItem] = []
        deliverable_files: List[ManusDeliverableFile] = []

        try:
            from derisk.agent.core.memory.gpts import GptsMemory
            from derisk.agent.core.memory.gpts.file_base import FileType

            gpts_memory = None
            if senders_map and main_agent_name:
                main_agent = senders_map.get(main_agent_name)
                if main_agent and hasattr(main_agent, "memory") and hasattr(main_agent.memory, "gpts_memory"):
                    gpts_memory = main_agent.memory.gpts_memory

            if not gpts_memory:
                logger.warning(f"[ManusConverter] No gpts_memory available for file collection")
                return task_files, deliverable_files

            if not isinstance(gpts_memory, GptsMemory):
                logger.warning(f"[ManusConverter] gpts_memory is not GptsMemory instance")
                return task_files, deliverable_files

            files = await gpts_memory.list_files(conv_id)
            logger.info(f"[ManusConverter] list_files returned {len(files)} files for conv_id={conv_id}")

            for file_meta in files:
                file_id = file_meta.file_id
                file_name = file_meta.file_name
                file_type = file_meta.file_type or ""
                mime_type = file_meta.mime_type

                task_files.append(ManusTaskFileItem(
                    file_id=file_id,
                    file_name=file_name,
                    file_type=file_type,
                    file_size=file_meta.file_size or 0,
                    mime_type=mime_type,
                    oss_url=file_meta.oss_url,
                    preview_url=file_meta.preview_url,
                    download_url=file_meta.download_url,
                    description=file_meta.metadata.get("description") if file_meta.metadata else None,
                    created_at=file_meta.created_at.isoformat() if hasattr(file_meta.created_at, 'isoformat') else str(file_meta.created_at),
                    object_path=file_meta.metadata.get("object_path") if file_meta.metadata else None,
                ))

                if file_type == FileType.DELIVERABLE.value or file_type == "deliverable":
                    oss_url = file_meta.oss_url
                    preview_url = file_meta.preview_url
                    if oss_url and oss_url.startswith("derisk-fs://"):
                        content_url = oss_url
                    else:
                        content_url = preview_url or oss_url
                    deliverable_files.append(ManusDeliverableFile(
                        file_id=file_id,
                        file_name=file_name,
                        mime_type=mime_type,
                        file_size=file_meta.file_size or 0,
                        content_url=content_url,
                        download_url=file_meta.download_url or preview_url,
                        object_path=file_meta.metadata.get("object_path") if file_meta.metadata else None,
                        render_type=self._determine_render_type(file_name, mime_type),
                    ))

            logger.info(f"[ManusConverter] _collect_files_from_gpts_memory result: task={len(task_files)}, deliverable={len(deliverable_files)}")

        except Exception as e:
            logger.warning(f"[ManusConverter] Failed to collect files from gpts_memory: {e}")

        return task_files, deliverable_files

    async def final_view(
        self,
        messages: List["GptsMessage"],
        plans_map: Optional[Dict[str, "GptsPlan"]] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs,
    ):
        """最终视图 - planning_window 复用 vis_window3，running_window 用 manus-right-panel"""
        # 从 kwargs 中提取 main_agent_name
        main_agent_name = kwargs.get("main_agent_name", None)

        # 从 messages 完整构建 steps（使用局部变量，不依赖 self._steps 单例状态）
        local_steps: Dict[str, ManusExecutionStep] = {}
        local_uid_map: Dict[str, str] = {}
        local_outputs: Dict[str, list] = {}
        step_counter = 0

        if messages:
            for msg in messages:
                if msg.role == HUMAN_ROLE and msg.action_report is None:
                    continue
                if not msg.action_report:
                    continue
                for act_out in (msg.action_report if isinstance(msg.action_report, list) else [msg.action_report]):
                    action_name = getattr(act_out, 'action', None) or getattr(act_out, 'action_name', None) or getattr(act_out, 'name', None)
                    is_blank = action_name == BlankAction.name
                    if not is_blank and getattr(act_out, 'terminate', False):
                        is_batch = action_name and action_name.lower() in ("batchtasks", "batch_tasks")
                        if not is_batch:
                            is_blank = True
                    if is_blank:
                        continue

                    step_counter += 1
                    # 使用 message_id 前缀确保跨轮次步骤 ID 唯一
                    msg_id_prefix = msg.message_id[:8] if msg.message_id else "unknown"
                    step_id = f"step_{msg_id_prefix}_{step_counter}"
                    action_input = getattr(act_out, 'action_input', None)
                    observation = getattr(act_out, 'observations', None) or getattr(act_out, 'content', None)

                    step = ManusExecutionStep(
                        id=step_id,
                        type=self._map_action_to_step_type(action_name, action_input),
                        title=action_name or "执行中",
                        subtitle=observation[:100] if observation and isinstance(observation, str) else None,
                        description=msg.current_goal,
                        status=ManusStepStatus.COMPLETED.value if getattr(act_out, 'is_exe_success', True) else ManusStepStatus.ERROR.value,
                        action=action_name,
                        action_input=action_input,
                    )
                    local_steps[step_id] = step

                    action_id = getattr(act_out, 'action_id', None)
                    if action_id:
                        local_uid_map[action_id] = step_id

                    if observation and isinstance(observation, str):
                        # SQL 步骤特殊处理：提取 d-sql-query VIS Tag 中的结构化数据
                        if step.type == ManusStepType.SQL.value:
                            sql_data = self._extract_sql_query_data(act_out)
                            if sql_data:
                                local_outputs[step_id] = [ManusExecutionOutput(
                                    output_type=ManusOutputType.SQL_QUERY.value,
                                    content=sql_data,
                                )]
                                continue
                        local_outputs[step_id] = [ManusExecutionOutput(
                            output_type=ManusOutputType.TEXT.value,
                            content=observation,
                        )]

        # 构建 steps_map（局部数据）— lazy mode: 包含 outputs 以便前端切换
        steps_map: Dict[str, Dict[str, Any]] = {}
        def _step_to_info(step):
            return ManusActiveStepInfo(
                id=step.id, type=step.type, title=step.title,
                subtitle=step.subtitle, status=step.status,
                detail=step.description, action=step.action,
                action_input=step.action_input,
            )

        for uid, sid in local_uid_map.items():
            step = local_steps.get(sid)
            if step:
                step_meta = {
                    "active_step": _step_to_info(step).to_dict(),
                    "outputs": self._outputs_to_dict_list(local_outputs.get(sid, [])),
                }
                steps_map[uid] = step_meta
                if sid not in steps_map:
                    steps_map[sid] = step_meta
        for sid, step in local_steps.items():
            if sid not in steps_map:
                steps_map[sid] = {
                    "active_step": _step_to_info(step).to_dict(),
                    "outputs": self._outputs_to_dict_list(local_outputs.get(sid, [])),
                }

        total_step_count = len(local_steps)
        if len(steps_map) > self.MAX_STEPS_IN_MAP:
            keep_sids = set(list(local_steps.keys())[-self.MAX_STEPS_IN_MAP:])
            steps_map = {
                k: v for k, v in steps_map.items()
                if k in keep_sids or local_uid_map.get(k) in keep_sids
            }

        # 调用父类 final_view 获取 planning_window
        parent_result = await super().final_view(
            messages=messages, plans_map=plans_map, senders_map=senders_map, **kwargs
        )

        # 构建 right panel（使用局部 steps_map，不依赖 self._steps）
        last_step = list(local_steps.values())[-1] if local_steps else None
        active_step_info = _step_to_info(last_step) if last_step else None
        last_outputs = local_outputs.get(last_step.id, []) if last_step else []
        right_panel = ManusRightPanelData(
            active_step=active_step_info,
            outputs=last_outputs,
            is_running=False,
            steps_map=steps_map,
            agent_name=self._agent_name,
            lazy_loading=True,
            meta={
                "total_steps": total_step_count,
                "visible_steps": len(steps_map),
                "default_step_id": last_step.id if last_step else None,
            },
        )

        # 收集任务文件和交付文件
        # 优先从 gpts_memory.list_files 获取（BAIZE agent 主路径）
        # fallback 到 messages.action_report.output_files
        conv_id = None
        for msg in messages:
            if msg.conv_id:
                conv_id = msg.conv_id
                break

        task_files: List[ManusTaskFileItem] = []
        deliverable_files: List[ManusDeliverableFile] = []

        if conv_id and senders_map and main_agent_name:
            task_files, deliverable_files = await self._collect_files_from_gpts_memory(
                conv_id, senders_map, main_agent_name
            )

        # Fallback: 从 messages 的 action_report 收集
        if not deliverable_files:
            task_files, deliverable_files = self._collect_files_from_messages(messages)

        right_panel.task_files = task_files
        right_panel.deliverable_files = deliverable_files

        if messages:
            last_msg = messages[-1]
            if last_msg.role != HUMAN_ROLE:
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
                pw = result_data.get("planning_window") or ""
                if deliverable_vis:
                    pw = pw + "\n" + deliverable_vis if pw else deliverable_vis
                result_data["planning_window"] = pw
                return json.dumps(result_data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass

        # 构建新的 planning_window: deliverable
        pw = deliverable_vis if deliverable_vis else ""
        return json.dumps(
            {
                "planning_window": pw,
                "running_window": right_vis,
                "meta_window": self._build_meta_window(),
            },
            ensure_ascii=False,
        )

    async def _footer_vis_build(
        self,
        gpt_msg: "GptsMessage",
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
    ) -> Optional[str]:
        """Manus 布局不在 planning_window 渲染最终结论，但需要保留 ask_user/confirm 交互组件。"""
        plans_vis = []

        if gpt_msg and gpt_msg.action_report:
            ask_user_vis = await self.gen_ask_user_vis(gpt_msg)
            if ask_user_vis:
                plans_vis.append(ask_user_vis)

        return "\n".join(plans_vis) if plans_vis else None

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

    def get_step_detail(
        self,
        messages: Optional[List["GptsMessage"]] = None,
        step_id: Optional[str] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """On-demand load full outputs for a specific step.

        First tries in-memory state (self._steps, self._outputs).
        If not found (e.g., history replay), re-processes messages to find the step.
        """
        if not step_id:
            return None

        resolved_step_id = step_id
        if step_id in self._planning_uid_to_step_id:
            resolved_step_id = self._planning_uid_to_step_id[step_id]

        # Try in-memory state
        step = self._steps.get(resolved_step_id)
        if step:
            step_info = ManusActiveStepInfo(
                id=step.id,
                type=step.type,
                title=step.title,
                subtitle=step.subtitle,
                status=step.status,
                detail=step.description,
                action=step.action,
                action_input=step.action_input,
            )
            return {
                "active_step": step_info.to_dict(),
                "outputs": self._outputs_to_dict_list(
                    self._outputs.get(resolved_step_id, [])
                ),
            }

        # History replay: re-process messages to find the step
        if messages:
            temp_counter = 0
            for msg in messages:
                if not msg.action_report:
                    continue
                for act_out in msg.action_report:
                    action_name = getattr(act_out, 'action', None) or getattr(act_out, 'name', '')
                    is_batch = action_name and action_name.lower() in ("batchtasks", "batch_tasks")
                    if action_name == BlankAction.name:
                        continue
                    if not is_batch and getattr(act_out, 'terminate', False):
                        continue
                    temp_counter += 1
                    # 使用与创建时相同的格式生成 temp_step_id
                    msg_id_prefix = msg.message_id[:8] if msg.message_id else "unknown"
                    temp_step_id = f"step_{msg_id_prefix}_{temp_counter}"

                    action_id = getattr(act_out, 'action_id', None)
                    if temp_step_id == resolved_step_id or action_id == step_id:
                        action_input = getattr(act_out, 'action_input', None)
                        step_type = self._map_action_to_step_type(action_name, action_input)
                        is_success = getattr(act_out, 'is_exe_success', True)
                        obs = getattr(act_out, 'observations', None)
                        cnt = getattr(act_out, 'content', None)
                        display_content = obs or cnt

                        out_type = ManusOutputType.TEXT.value
                        if step_type in (ManusStepType.PYTHON.value,):
                            out_type = ManusOutputType.CODE.value
                        elif step_type == ManusStepType.HTML.value:
                            out_type = ManusOutputType.HTML.value
                        elif step_type == ManusStepType.SQL.value:
                            sql_data = self._extract_sql_query_data(act_out)
                            if sql_data:
                                return {
                                    "active_step": {
                                        "id": temp_step_id,
                                        "type": step_type,
                                        "title": action_name,
                                        "status": ManusStepStatus.COMPLETED.value if is_success else ManusStepStatus.ERROR.value,
                                        "action": action_name,
                                        "action_input": action_input,
                                    },
                                    "outputs": [{"output_type": ManusOutputType.SQL_QUERY.value, "content": sql_data}],
                                }

                        outputs = []
                        if display_content:
                            outputs.append({"output_type": out_type, "content": display_content})

                        return {
                            "active_step": {
                                "id": temp_step_id,
                                "type": step_type,
                                "title": action_name,
                                "status": ManusStepStatus.COMPLETED.value if is_success else ManusStepStatus.ERROR.value,
                                "action": action_name,
                                "action_input": action_input,
                            },
                            "outputs": outputs,
                        }

        return None
