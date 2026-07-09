"""场景空间 AgentWorkspace 可视化转换器。

产出结构化 vis 产物 {render_name, planning, execution[], summary},前端 AgentWorkspaceRenderer 消费。
注册靠子类扫描(render_name = scene_agent_workspace)。
"""
import json
import uuid
from typing import Any, Dict, List, Optional, Union

from derisk_ext.vis.derisk.derisk_vis_manus_converter import (
    DeriskIncrVisManusConverter,
)


class SceneAgentWorkspaceConverter(DeriskIncrVisManusConverter):
    """场景空间 AgentWorkspace 转换器。

    复用 manus converter 的消息解析与 action_report 抽取逻辑,
    但输出形态改为 AgentWorkspace 需要的结构化 JSON(planning/execution/summary)。
    """

    SCENE_TAG = "scene_agent_workspace"

    @property
    def reuse_name(self):
        return "scene_agent_workspace"

    @property
    def render_name(self):
        return "scene_agent_workspace"

    @property
    def web_use(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "场景空间 AgentWorkspace 结构化可视化布局"

    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None

    def _step_from_action_report(self, report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从 action_report 抽取一个 execution step。"""
        content = self._safe_json_loads(report.get("content"))
        if not isinstance(content, dict):
            return None
        status_raw = str(content.get("status", "")).lower()
        status = (
            "running" if status_raw in ("running", "executing", "pending")
            else "failed" if status_raw in ("failed", "error", "blocked")
            else "done"
        )
        action = content.get("name") or report.get("view")
        action_input = content.get("args") if isinstance(content.get("args"), dict) else None
        output = content.get("content") if isinstance(content.get("content"), str) else None
        return {
            "id": str(content.get("name") or uuid.uuid4().hex),
            "type": "tool_call",
            "title": str(action or "工具调用"),
            "status": status,
            "action": action,
            "action_input": action_input,
            "output": output,
            "artifact": None,
            "vis": None,
        }

    async def visualization(
        self,
        messages: List[Any],
        plans_map: Optional[Dict[str, Any]] = None,
        gpt_msg: Any = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[Any]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict[str, Any]] = None,
        main_agent_name: Optional[str] = None,
        is_first_push: bool = False,
        **kwargs,
    ) -> str:
        """产出结构化 vis tag 包裹的 JSON。"""
        execution: List[Dict[str, Any]] = []
        summary: Optional[str] = None

        # 优先从 gpt_msg / stream_msg 取当前 action_report
        report = None
        if gpt_msg is not None and getattr(gpt_msg, "action_report", None):
            report = gpt_msg.action_report
        elif isinstance(stream_msg, dict) and stream_msg.get("action_report"):
            report = stream_msg["action_report"]
        if isinstance(report, dict):
            step = self._step_from_action_report(report)
            if step:
                execution.append(step)

        # assistant 文本作为 summary 候选
        ai_text = getattr(gpt_msg, "ai_message", None) if gpt_msg is not None else None
        if isinstance(ai_text, str) and ai_text.strip():
            summary = ai_text.strip()

        payload = {
            "render_name": "scene_agent_workspace",
            "planning": None,
            "execution": execution,
            "summary": summary,
        }
        body = json.dumps(payload, ensure_ascii=False)
        return f"```{self.SCENE_TAG}\n{body}\n```"