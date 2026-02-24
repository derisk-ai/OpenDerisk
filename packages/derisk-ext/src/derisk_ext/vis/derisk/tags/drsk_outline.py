import logging
from typing import Optional, Dict, Any, List

from pydantic import Field, ValidationError, BaseModel

from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class DrskOutlineContent(DrskVisBase):
    markdown: Optional[str] = Field(None, description="outline markdown")
    title: Optional[str] = Field(
        default="生成文档名",
        description="生成文档名",
    )
    children: Optional[List[dict]] = Field(
        None,
        description="children of wiki structure",
    )
    state: str = Field(
        default="complete",
        description="state of wiki structure",
    )

class DrskOutline(Vis):
    def vis_tag(cls) -> str:
        return "drsk-outline"


    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the drsk_vis protocol.

        Display corresponding content using drsk_vis protocol

        Args:
            **kwargs:

        Returns:
        drsk_vis protocol text
        """
        title = kwargs.get("title")
        children = kwargs.get("children")
        message_id = kwargs.get("message_id")
        state = kwargs.get("state", "complete")

        try:
            outline = DrskOutlineContent(
                title=title,
                children=children,
                uid=message_id, type="all",
                dynamic=False,
                markdown="",
                state=state,
            )
            return outline.to_dict()
        except ValidationError as e:
            logger.warning(
                f"DrskMsg可视化组件收到了非法的数据内容，可能导致显示失败！{title}"
            )
            return {}
