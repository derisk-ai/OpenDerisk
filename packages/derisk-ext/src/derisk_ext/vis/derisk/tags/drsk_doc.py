import logging
from enum import Enum
from typing import Optional, Dict, Any

from pydantic import Field, ValidationError

from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)

class GenerateDocTypeEnum(Enum):
    """Generate Doc type enum."""
    YUQUE = "yuque"
    SPEC = "spec"

class DrskDocContent(DrskVisBase):
    markdown: Optional[str] = Field(None, description="outline markdown")
    state: str = Field("complete", description="outline markdown")
    title: Optional[str] = Field("生成文档", description="title")
    doc_type: str = Field("", description="doc type")
    avatar: Optional[str] = Field("", description="avatar")

class DrskDoc(Vis):
    def vis_tag(cls) -> str:
        return "drsk-doc"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the drsk_vis protocol.

        Display corresponding content using drsk_vis protocol

        Args:
            **kwargs:

        Returns:
        drsk_vis protocol text
        """
        content = "" if kwargs.get("content") is None else kwargs.get("content")
        message_id = kwargs.get("message_id")
        state = kwargs.get("state", "complete")
        avatar = kwargs.get("avatar")
        type = kwargs.get("type", "all")
        title = kwargs.get("title")
        doc_type = kwargs.get("doc_type", GenerateDocTypeEnum.YUQUE.value)
        if title is None or title == "":
            title = "生成文档"
        try:
            outline = DrskDocContent(
                markdown=content,
                uid=message_id,
                type=type,
                dynamic=False,
                state=state,
                title=title,
                doc_type=doc_type,
                avatar=avatar,
            )
            return outline.to_dict()
        except ValidationError as e:
            logger.warning(
                f"DrskMsg可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content


