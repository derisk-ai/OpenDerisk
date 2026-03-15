"""Blank Action for the Agent."""

import datetime
import logging
import re
import time
from typing import Optional

from ..schema import Status, ActionInferenceMetrics
from ...resource.base import AgentResource
from .base import Action, ActionOutput

logger = logging.getLogger(__name__)


class BlankAction(Action[Optional[str]]):
    """Blank action class."""

    name = "Blank"

    def __init__(self, **kwargs):
        """Blank action init."""
        super().__init__(**kwargs)
        self._terminate = kwargs.get("terminate", True)

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

        metrics.end_time_ms = time.time_ns() // 1_000_000
        metrics.result_tokens = len(str(ai_message))
        cost_ms = metrics.end_time_ms - metrics.start_time_ms
        metrics.cost_seconds = round(cost_ms / 1000, 2)

        action_id = kwargs.get("action_id", None)
        terminate = kwargs.get("terminate", None) or self._terminate

        thought_match = re.search(r"<thought>(.*?)</thought>", ai_message, re.DOTALL)
        if thought_match:
            ai_message = thought_match.group(1).strip()

        result = self.action_input or ai_message
        return ActionOutput(
            name=self.name,
            action_id=action_id or self.action_uid,
            action="blank",  # 使用 "blank" 而不是 "结论"，避免被误认为是有效的工具调用
            start_time=datetime.datetime.now(),
            is_exe_success=True,
            state=Status.COMPLETE.value,
            content=result,
            metrics=metrics,
            terminate=terminate,
        )
