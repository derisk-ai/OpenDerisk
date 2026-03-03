"""
Core V2 VIS Window3 Converter

轻量级 vis_window3 协议转换器，专为 core_v2 架构设计。
不依赖 ConversableAgent，直接从 stream_msg dict 生成 vis_window3 格式输出。

输出格式：
    {"planning_window": "<VIS标签字符串>", "running_window": "<VIS标签字符串>"}

VIS增量传输协议：
    1. type=INCR: 组件按UID匹配，markdown和items做增量追加，其他字段有值则替换，无值不变
    2. type=ALL: 所有字段都完全替换，包括空值
"""

import json
import logging
from typing import Dict, List, Optional, Union

from derisk.agent.core.memory.gpts import GptsMessage, GptsPlan
from derisk.vis.vis_converter import VisProtocolConverter

logger = logging.getLogger(__name__)


def _vis_tag(tag_name: str, data: dict) -> str:
    """生成 VIS 标签字符串。

    格式: ```{tag_name}\n{json}\n```

    与 Vis.sync_display() 的输出完全一致。
    """
    content = json.dumps(data, ensure_ascii=False)
    return f"```{tag_name}\n{content}\n```"


class CoreV2VisWindow3Converter(VisProtocolConverter):
    """Core V2 专用 vis_window3 转换器。

    不依赖 ConversableAgent，直接处理 stream_msg dict 生成 vis_window3 输出。
    输出格式与 DeriskIncrVisWindow3Converter 兼容，前端可正常渲染。
    """

    def __init__(self, paths: Optional[str] = None, **kwargs):
        # 不扫描 VIS 标签文件，我们直接生成标签字符串
        super().__init__(paths=None, **kwargs)

    @property
    def render_name(self):
        return "vis_window3"

    @property
    def reuse_name(self):
        return "nex_vis_window"

    @property
    def description(self) -> str:
        return "Core V2 vis_window3 可视化布局"

    @property
    def web_use(self) -> bool:
        return True

    @property
    def incremental(self) -> bool:
        return True

    async def visualization(
        self,
        messages: List[GptsMessage],
        plans_map: Optional[Dict[str, GptsPlan]] = None,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[GptsPlan]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict] = None,
        main_agent_name: Optional[str] = None,
        is_first_push: bool = False,
        **kwargs,
    ):
        try:
            planning_vis = ""
            running_vis = ""

            if stream_msg and isinstance(stream_msg, dict):
                planning_vis = self._build_planning_from_stream(
                    stream_msg, is_first_chunk
                )
                running_vis = self._build_running_from_stream(
                    stream_msg, is_first_chunk, is_first_push
                )
            elif gpt_msg:
                planning_vis = self._build_planning_from_msg(gpt_msg)
                running_vis = self._build_running_from_msg(gpt_msg)

            if planning_vis or running_vis:
                return json.dumps(
                    {
                        "planning_window": planning_vis,
                        "running_window": running_vis,
                    },
                    ensure_ascii=False,
                )
            return None
        except Exception:
            logger.exception("CoreV2VisWindow3Converter visualization 异常")
            return None

    async def final_view(
        self,
        messages: List[GptsMessage],
        plans_map: Optional[Dict[str, GptsPlan]] = None,
        senders_map: Optional[Dict] = None,
        **kwargs,
    ):
        return await self.visualization(messages, plans_map, **kwargs)

    # ──────────────────────────────────────────────────────────────────────
    #  Planning window: 左侧步骤/思考内容
    # ──────────────────────────────────────────────────────────────────────

    def _build_planning_from_stream(
        self, stream_msg: dict, is_first_chunk: bool
    ) -> str:
        """从 stream_msg 构建 planning_window 内容。

        使用 drsk-content 标签输出步骤思考信息，
        使用 drsk-thinking 标签输出 thinking 内容。
        """
        parts: List[str] = []
        message_id = stream_msg.get("message_id", "")
        goal_id = stream_msg.get("goal_id", message_id)
        thinking = stream_msg.get("thinking")
        content = stream_msg.get("content", "")
        update_type = "incr"

        # 思考内容 → planning window
        if thinking and thinking.strip():
            parts.append(
                _vis_tag(
                    "drsk-thinking",
                    {
                        "uid": f"{message_id}_thinking",
                        "type": update_type,
                        "dynamic": False,
                        "markdown": thinking.strip(),
                        "expand": True,
                    },
                )
            )

        # 普通文本内容 → planning window (作为步骤描述)
        if content and content.strip() and not thinking:
            parts.append(
                _vis_tag(
                    "drsk-content",
                    {
                        "uid": f"{message_id}_step_thought",
                        "type": update_type,
                        "dynamic": False,
                        "markdown": content.strip(),
                    },
                )
            )

        if not parts:
            return ""

        # 包装到 plan item 下挂载到 goal_id 节点
        leaf_vis = "\n".join(parts)
        plan_item = _vis_tag(
            "drsk-plan",
            {
                "uid": goal_id,
                "type": "incr",
                "markdown": leaf_vis,
            },
        )
        return plan_item

    def _build_planning_from_msg(self, gpt_msg: GptsMessage) -> str:
        """从 GptsMessage 构建 planning_window 内容。"""
        parts: List[str] = []
        message_id = gpt_msg.message_id or ""

        if gpt_msg.thinking and gpt_msg.thinking.strip():
            parts.append(
                _vis_tag(
                    "drsk-thinking",
                    {
                        "uid": f"{message_id}_thinking",
                        "type": "all",
                        "dynamic": False,
                        "markdown": gpt_msg.thinking.strip(),
                        "expand": False,
                    },
                )
            )

        if gpt_msg.content and gpt_msg.content.strip():
            parts.append(
                _vis_tag(
                    "drsk-content",
                    {
                        "uid": f"{message_id}_content",
                        "type": "all",
                        "dynamic": False,
                        "markdown": gpt_msg.content.strip(),
                    },
                )
            )

        # 处理 action_report
        if gpt_msg.action_report:
            for action_out in gpt_msg.action_report:
                action_id = getattr(action_out, "action_id", None) or ""
                action_name = getattr(action_out, "action", None) or getattr(
                    action_out, "name", "action"
                )
                status = getattr(action_out, "state", "running")
                parts.append(
                    _vis_tag(
                        "drsk-plan",
                        {
                            "uid": action_id,
                            "type": "all",
                            "item_type": "task",
                            "task_type": "tool",
                            "title": action_name,
                            "status": status,
                        },
                    )
                )

        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────────────
    #  Running window: 右侧工作空间内容
    # ──────────────────────────────────────────────────────────────────────

    def _build_running_from_stream(
        self, stream_msg: dict, is_first_chunk: bool, is_first_push: bool
    ) -> str:
        """从 stream_msg 构建 running_window 内容。

        running_window 展示当前步骤的详细输出。
        使用 nex-work-space 标签包裹工作项。
        """
        message_id = stream_msg.get("message_id", "")
        conv_session_uid = stream_msg.get("conv_session_uid", "")
        content = stream_msg.get("content", "")
        thinking = stream_msg.get("thinking")
        sender_name = stream_msg.get("sender_name", "assistant")

        work_items: List[str] = []

        # 思考内容 → 工作空间的 thinking 展示
        if thinking and thinking.strip():
            work_items.append(
                _vis_tag(
                    "drsk-thinking",
                    {
                        "uid": f"{message_id}_work_thinking",
                        "type": "incr",
                        "dynamic": False,
                        "markdown": thinking.strip(),
                        "expand": True,
                    },
                )
            )

        # 普通内容 → 工作空间的 LLM 输出
        if content and content.strip():
            work_items.append(
                _vis_tag(
                    "drsk-content",
                    {
                        "uid": f"{message_id}_work_content",
                        "type": "incr",
                        "dynamic": False,
                        "markdown": content.strip(),
                    },
                )
            )

        if not work_items:
            return ""

        # 用 nex-work-space 包裹
        workspace_data = {
            "uid": conv_session_uid or message_id,
            "type": "incr",
            "items": work_items,
        }

        return _vis_tag("nex-work-space", workspace_data)

    def _build_running_from_msg(self, gpt_msg: GptsMessage) -> str:
        """从 GptsMessage 构建 running_window 内容。"""
        message_id = gpt_msg.message_id or ""
        work_items: List[str] = []

        if gpt_msg.thinking and gpt_msg.thinking.strip():
            work_items.append(
                _vis_tag(
                    "drsk-thinking",
                    {
                        "uid": f"{message_id}_work_thinking",
                        "type": "all",
                        "dynamic": False,
                        "markdown": gpt_msg.thinking.strip(),
                        "expand": False,
                    },
                )
            )

        if gpt_msg.content and gpt_msg.content.strip():
            work_items.append(
                _vis_tag(
                    "drsk-content",
                    {
                        "uid": f"{message_id}_work_content",
                        "type": "all",
                        "dynamic": False,
                        "markdown": gpt_msg.content.strip(),
                    },
                )
            )

        if gpt_msg.action_report:
            for action_out in gpt_msg.action_report:
                action_id = getattr(action_out, "action_id", None) or ""
                view_content = getattr(action_out, "view", None) or getattr(
                    action_out, "content", ""
                )
                if view_content and view_content.strip():
                    work_items.append(
                        _vis_tag(
                            "drsk-content",
                            {
                                "uid": f"{action_id}_work_view",
                                "type": "all",
                                "dynamic": False,
                                "markdown": view_content.strip(),
                            },
                        )
                    )

        if not work_items:
            return ""

        conv_session_id = gpt_msg.conv_session_id or message_id
        workspace_data = {
            "uid": conv_session_id,
            "type": "incr",
            "items": work_items,
        }

        return _vis_tag("nex-work-space", workspace_data)
