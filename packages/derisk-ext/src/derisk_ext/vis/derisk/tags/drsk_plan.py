import logging
from typing import Optional, Dict, Any

from pydantic_core._pydantic_core import ValidationError

from derisk.vis import Vis
from derisk.vis.schema import VisPlanContent

logger = logging.getLogger(__name__)


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
            VisPlanContent.model_validate(content)
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
