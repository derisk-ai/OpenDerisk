import logging
from typing import List, Dict, Any, Optional, Union

from pydantic_core._pydantic_core import ValidationError

from derisk.vis import Vis
from derisk._private.pydantic import (
    Field,
    model_to_dict,
)
from derisk_ext.vis.common.tags.derisk_work_space import WorkSpaceContent
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase
from derisk_ext.vis.derisk.tags.nex_running_window import RunningContent

logger = logging.getLogger(__name__)


class RunningWindowContent(DrskVisBase):
    running_agent: Optional[Union[str, List[str]]] = Field(None, description="agent role")
    items: List[Union[WorkSpaceContent, RunningContent]] = Field(default=[], description="work agent items")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        tasks_dict = []
        for step in self.items:
            tasks_dict.append(step.to_dict())
        dict_value = model_to_dict(self, exclude={"items"})
        dict_value["items"] = tasks_dict
        return dict_value


class DeriskRunningWindow(Vis):
    """DeriskRunningWindow."""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the derisk_vis protocol.

        Display corresponding content using derisk_vis protocol

        Args:
            **kwargs:

        Returns:
        derisk_vis protocol text
        """
        content = kwargs["content"]
        try:
            RunningWindowContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"DeriskRunningWindow可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "derisk-running-window"
