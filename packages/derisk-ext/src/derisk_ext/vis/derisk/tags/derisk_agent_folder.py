from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, Union

from pydantic_core._pydantic_core import ValidationError
from derisk._private.pydantic import (
    Field,
    BaseModel,
    model_to_json,
    model_validator,
    model_to_dict,
)
from typing import Optional

from derisk.vis import Vis
from derisk_ext.vis.common.tags.derisk_work_space import FolderNode
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)






class AgentFolder(Vis):
    """WorkSpace."""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the vis protocol.

        Display corresponding content using vis protocol

        Args:
            **kwargs:

        Returns:
        vis protocol text
        """
        content = kwargs["content"]
        try:
            FolderNode.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"AgentFolder可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "d-agent-folder"
