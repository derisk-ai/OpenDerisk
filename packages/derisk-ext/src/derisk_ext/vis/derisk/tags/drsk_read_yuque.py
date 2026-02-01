import json
from typing import Optional, Dict, Any

from pydantic import ValidationError, Field

from derisk.component import logger
from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase


class DrskReadYuqueContent(DrskVisBase):
    operation: Optional[str] = Field(None, description="ReadYuque operation")
    url: Optional[str] = Field(None, description="ReadYuque markdown")
    file_id: Optional[str] = Field(None, description="file_id")
    doc_info: Optional[str] = Field(None, description="doc_info")
    doc_id: Optional[str] = Field(None, description="doc_id")
    repo: Optional[str] = Field(None, description="repo")
    monitor_image_url: Optional[str] = Field(None, description="monitor_image_url")
    monitor_id: Optional[str] = Field(None, description="monitor_id")
    image_id: Optional[str] = Field(None, description="image_id")
    datasource: Optional[str] = Field("yuque", description="datasource")


class DrskReadYuque(Vis):
    def vis_tag(cls) -> str:
        return "drsk-read-yuque"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the drsk_vis protocol.

        Display corresponding content using drsk_vis protocol

        Args:
            **kwargs:

        Returns:
        drsk_vis protocol text
        """
        content = kwargs["content"]
        content_dict = json.loads(content)
        message_id = kwargs["message_id"]

        try:
            outline = DrskReadYuqueContent(
                url=content_dict.get("url"),
                operation=content_dict.get("operation"),
                file_id=content_dict.get("file_id"),
                doc_info=content_dict.get("doc_info"),
                doc_id=content_dict.get("doc_id"),
                repo=content_dict.get("repo"),
                monitor_image_url=content_dict.get("monitor_image_url"),
                monitor_id=content_dict.get("monitor_id"),
                image_id=content_dict.get("image_id"),
                datasource=content_dict.get("datasource"),
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