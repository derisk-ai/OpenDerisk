from __future__ import annotations

import logging
from typing import Dict, Any

from pydantic_core._pydantic_core import ValidationError
from derisk._private.pydantic import (
    Field,
)
from typing import Optional

from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class PlanningSpaceContent(DrskVisBase):
    agent_role: Optional[str] = Field(None, description="agent role")
    agent_name: Optional[str] = Field(None, description="agent name")
    title: Optional[str] = Field(None, description="title of planning window")
    description: Optional[str] = Field(None, description="agent description")
    avatar: Optional[str] = Field(None, description="task logo")
    todolist: Optional[str] = Field(
        None, description="待办列表可视化标签，显示在agent信息之后、任务列表之前"
    )
    markdown: Optional[str] = Field(None, description="工作空间资源管理器")


class PlanningSpace(Vis):
    """PlanningSpace."""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the vis protocol.

        Display corresponding content using vis protocol

        Args:
            **kwargs:

        Returns:
        vis protocol text
        """
        content = kwargs["content"]
        try:
            PlanningSpaceContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"PlanningSpace可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "d-planning-space"
