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


class KnowledgeWindowContent(DrskVisBase):
    agent_role: Optional[str] = Field(None, description="agent role")
    agent_name: Optional[str] = Field(None, description="agent name")
    description: Optional[str] = Field(None, description="agent description")
    generate_type: Optional[str] = Field("outline", description="generate_type")
    avatar: Optional[str] = Field(None, description="task logo")
    markdown: Optional[str] = Field(None, description="task's content")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        dict_value = model_to_dict(self, exclude={"items"})
        return dict_value


class KnowledgeSpaceWindow(Vis):
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
            KnowledgeWindowContent.model_validate(content)
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
        return "knowledge-space-window"
