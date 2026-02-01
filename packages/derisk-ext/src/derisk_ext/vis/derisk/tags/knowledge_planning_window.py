from datetime import datetime
import logging
from typing import List, Dict, Any, Optional, Union

from pydantic_core._pydantic_core import ValidationError

from derisk.vis import Vis
from derisk._private.pydantic import (
    Field,
    model_to_dict,
)
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)

class KnowledgeTaskBase(DrskVisBase):
    title: str = Field(..., description="task title")
    task_id: str = Field(..., description="task id")
    status: Optional[str] = Field(..., description="task status")
    avatar: Optional[str] = Field(None, description="task logo")
    model: Optional[str] = Field(None, description="task deal model")
    agent: Optional[str] = Field(None, description="task deal agent")
    task_type: Optional[str] = Field(None, description="task type('agent','tool', 'knowledge')")
    start_time: Optional[Union[str, datetime]] = Field(default=None, description="plans start time")
    cost: Optional[float] = Field(default=0.00, description="plans cost(Time unit: seconds)")
    step_avatar: Optional[str] = Field("https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*pRx-Q6mEvbwAAAAAAAAAAAAADprcAQ/original", description="step avatar")


class KnowledgeTaskContent(KnowledgeTaskBase):
    markdown: Optional[str] = Field(None, description="task deal result")
    browser: Optional[str] = Field(None, description="browser")
    description: Optional[str] = Field(None, description="task description")


class KnowledgePlansContent(DrskVisBase):
    title: str = Field(..., description="task title")
    description: Optional[str] = Field(None, description="task description")
    model: Optional[str] = Field(None, description="task deal model")
    agent: Optional[str] = Field(None, description="task deal agent")
    avatar: Optional[str] = Field(None, description="task deal agent avatar")
    items: List[Union[KnowledgeTaskContent, KnowledgeTaskBase]] = Field(default=[], description="plans items")
    start_time: Optional[Union[str, datetime]] = Field(default=None, description="plans start time")
    cost: Optional[float] = Field(default=0.00, description="plans cost(Time unit: seconds)")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        tasks_dict = []
        for step in self.items:
            tasks_dict.append(step.to_dict())
        dict_value = model_to_dict(self, exclude={"items"})
        dict_value["items"] = tasks_dict
        return dict_value


class KnowledgePlanningContent(DrskVisBase):
    items: List[KnowledgePlansContent] = Field(default=[], description="window plan items")


class KnowledgePlanningWindow(Vis):
    """KnowledgePlanningWindow."""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the drsk_vis protocol.

        Display corresponding content using drsk_vis protocol

        Args:
            **kwargs:

        Returns:
        drsk_vis protocol text
        """
        content = kwargs["content"]
        try:
            KnowledgePlanningContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"KnowledgePlanningWindow可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "knowledge-planning-window"
