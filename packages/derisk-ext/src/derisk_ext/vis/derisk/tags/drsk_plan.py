import logging
from typing import Optional, Dict, Any, List

from pydantic_core._pydantic_core import ValidationError

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_to_json,
    model_validator,
    model_to_dict,
)
from derisk.vis import Vis
from derisk.vis.schema import VisTaskContent
from .drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class DrskPlanContent(DrskVisBase):
    tasks: List[VisTaskContent] = Field(default=[], description="drsk drsk_plan tasks")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        tasks_dict = []
        for step in self.tasks:
            tasks_dict.append(step.to_dict())
        dict_value = model_to_dict(self, exclude={"tasks"})
        dict_value["tasks"] = tasks_dict
        return dict_value


class DrskPlan(Vis):
    """DrskMsg."""

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
            DrskPlanContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"DrskPlan可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "drsk-plan"
