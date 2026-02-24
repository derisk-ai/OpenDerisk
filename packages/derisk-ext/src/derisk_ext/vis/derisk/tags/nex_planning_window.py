from datetime import datetime
import logging
from typing import List, Dict, Any, Optional, Union

from pydantic_core._pydantic_core import ValidationError

from derisk.vis import Vis

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_to_json,
    model_validator,
    model_to_dict,
)
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class NexTaskContent(DrskVisBase):
    title: str = Field(..., description="task title")
    task_id: str = Field(..., description="task id")
    status: Optional[str] = Field(..., description="task status")
    description: Optional[str] = Field(None, description="task description")
    avatar: Optional[str] = Field(None, description="task logo")
    model: Optional[str] = Field(None, description="task deal model")
    agent: Optional[str] = Field(None, description="task deal agent")
    task_type: Optional[str] = Field(None, description="task type('agent','tool', 'knowledge')")
    start_time: Optional[Union[str, datetime]] = Field(default=None, description="plans start time")
    cost: Optional[float] = Field(default=0.00, description="plans cost(Time unit: seconds)")

class NexPlansContent(DrskVisBase):
    title: str = Field(..., description="task title")
    description: Optional[str] = Field(None, description="task description")
    model: Optional[str] = Field(None, description="task deal model")
    agent: Optional[str] = Field(None, description="task deal agent")
    avatar: Optional[str] = Field(None, description="task deal agent avatar")
    items: List[NexTaskContent] = Field(default=[], description="plans items")
    start_time: Optional[Union[str, datetime]] = Field(default=None, description="plans start time")
    cost: Optional[float] = Field(default=0.00, description="plans cost(Time unit: seconds)")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        tasks_dict = []
        for step in self.items:
            tasks_dict.append(step.to_dict())
        dict_value = model_to_dict(self, exclude={"items"})
        dict_value["items"] = tasks_dict
        return dict_value


class PlanningWindowContent(DrskVisBase):
    items: List[NexPlansContent] = Field(default=[], description="window plan items")


class NexPlanningWindow(Vis):
    """NexPlanningWindow."""

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
            PlanningWindowContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"NexPlanningWindow可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "nex-planning-window"
