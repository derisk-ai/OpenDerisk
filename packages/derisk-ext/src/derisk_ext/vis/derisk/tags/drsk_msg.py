import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Union

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
from .drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class DrskMsgContent(DrskVisBase):
    markdown: str = Field(..., description="drsk drsk_vis msg content")
    role: Optional[str] = Field(default=None, description="drsk drsk_vis role param")
    name: Optional[str] = Field(default=None, description="drsk drsk_vis name param")
    avatar: Optional[str] = Field(
        default=None, description="drsk drsk_vis avatar param"
    )
    model: Optional[str] = Field(default=None, description="drsk drsk_vis model param")
    start_time: Optional[Union[str, datetime]] = Field(default=None, description="drsk message start time")
    task_id: Optional[str] = Field(default=None, description="The ID of the task topic to which the message belongs")

class DrskTaskPlanContent(DrskVisBase):
    thinking: Optional[str] = Field(..., description="drsk thinking content")
    content: Optional[str] = Field(..., description="drsk output content")
    app_code: Optional[str] = Field(..., description="app_code")
    role: Optional[str] = Field(default=None, description="drsk task plan role param")
    name: Optional[str] = Field(default=None, description="drsk task plan name param")
    avatar: Optional[str] = Field(
        default=None, description="drsk task plan avatar param"
    )
    model: Optional[str] = Field(default=None, description="drsk task plan model param")


class DrskMsg(Vis):
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
            DrskMsgContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"DrskMsg可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "drsk-msg"
