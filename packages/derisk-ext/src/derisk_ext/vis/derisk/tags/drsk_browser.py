import logging
from typing import Optional, List, Dict, Any

from pydantic import Field, ValidationError

from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase
logger = logging.getLogger(__name__)

class DrskBrowserContent(DrskVisBase):
    title: Optional[str] = Field(
        default="Derisk的浏览器",
        description="浏览器title",
    )
    title_avatar: Optional[str] = Field(
        default="",
        description="浏览器title",
    )
    current_index: Optional[int] = Field(
        default=None,
        description="当前index",
    )
    items: Optional[List[dict]] = Field(
        None,
        description="items",
    )
    state: str = Field(
        default="complete",
        description="state of wiki structure",
    )
    avatar: str = Field(
        default="",
        description="avatar",
    )

class DrskBrowser(Vis):
    def vis_tag(cls) -> str:
        return "drsk-browser"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the drsk_vis protocol.

        Display corresponding content using drsk_vis protocol

        Args:
            **kwargs:

        Returns:
        drsk_vis protocol text
        """
        message_id = kwargs["message_id"]
        items = kwargs["items"]

        try:
            browser = DrskBrowserContent(
                uid=message_id,
                type="all",
                dynamic=False,
                current_index=kwargs.get("current_index"),
                items=items
            )
            return browser.to_dict()
        except ValidationError as e:
            logger.warning(
                f"DrskBrowser可视化组件收到了非法的数据内容，可能导致显示失败！{items}"
            )
            return {}