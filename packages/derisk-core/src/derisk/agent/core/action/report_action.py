"""Blank Action for the Agent."""
import datetime
import logging
import time
import uuid
from typing import Optional

from derisk.util.string_utils import StringSizeConverter
from derisk.vis import SystemVisTag
from derisk.vis.schema import VisTextContent, VisAttachsContent, VisAttach
from ..schema import Status, ActionInferenceMetrics
from ...resource.base import AgentResource
from .base import Action, ActionOutput

logger = logging.getLogger(__name__)


class ReportAction(Action):
    """Report action class."""
    name = "Report"

    def __init__(self, **kwargs):
        """Blank action init."""
        super().__init__(**kwargs)
        self.action_view_tag: str = SystemVisTag.VisReport.value

    @property
    def ai_out_schema(self) -> Optional[str]:
        """Return the AI output schema."""
        return None

    async def run(
        self,
        ai_message: str = None,
        resource: Optional[AgentResource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        need_vis_render: bool = True,
        **kwargs,
    ) -> ActionOutput:
        """Perform the action.

        Just return the AI message.
        """
        metrics = ActionInferenceMetrics()
        metrics.start_time_ms = time.time_ns() // 1_000_000
        start_time = datetime.datetime.now()
        message_id = kwargs.get("message_id")
        sender = kwargs.get("sender")
        report_content = VisTextContent(markdown=ai_message, uid=message_id + "_content", type="all")
        self._render = kwargs.get("render_protocol") or self._render

        simple_view = None
        view = None
        if self.render_protocol:
            view = self.render_protocol.sync_display(
                content=report_content.to_dict()
            )
        attach_content = VisAttachsContent(
            uid=uuid.uuid4().hex,
            type="all",
            items=[
                VisAttach(uid=self.action_uid + "_report", task_id=self.action_uid, type='all', file_type="markdown",
                          name="结论报告",
                          description=next((line.strip() for line in ai_message.splitlines() if line.strip()), ""),
                          created=start_time, author=sender.name if sender else None,
                          size=StringSizeConverter.auto_format(view))
            ]
        )
        attach_vis_inst = self._render.vis_inst(SystemVisTag.VisAttach.value)
        if attach_vis_inst:
            simple_view = attach_vis_inst.sync_display(content=attach_content.to_dict())

        metrics.end_time_ms = time.time_ns() // 1_000_000
        metrics.result_tokens = len(str(ai_message))
        cost_ms = metrics.end_time_ms - metrics.start_time_ms
        metrics.cost_seconds = round(cost_ms / 1000, 2)
        return ActionOutput(
            name=self.name,
            action_id=self.action_uid,
            action="结论报告",
            start_time=start_time,
            is_exe_success=True,
            state=Status.COMPLETE.value,
            content=ai_message,
            metrics=metrics,
            simple_view=simple_view,
            view=view,
            terminate=True,
        )
