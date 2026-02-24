from typing import Optional, Dict, Any

from pydantic import Field, ValidationError

from derisk.component import logger
from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase


class DrskLSContent(DrskVisBase):
    markdown: Optional[str] = Field(None, description="outline markdown")

class DrskLS(Vis):
    def vis_tag(cls) -> str:
        return "drsk-ls"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the drsk_vis protocol.

        Display corresponding content using drsk_vis protocol

        Args:
            **kwargs:

        Returns:
        drsk_vis protocol text
        """
        content = kwargs["content"]
        message_id = kwargs["message_id"]

        try:
            outline = DrskLSContent(
                markdown=content,
                uid=message_id,
                type="all",
                dynamic=False
            )
            return outline.to_dict()
        except ValidationError as e:
            logger.warning(
                f"DrskMsg可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return {}
