import logging
from typing import Optional, Dict, Any, List

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
from derisk.vis.schema import VisStepContent
from .drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class DrskStep(Vis):
    """DrskMsg."""

    def __init__(self, **kwargs):
        self._drsk_web_url = kwargs.get(
            "drsk_web_url", ""
        )
        super().__init__(**kwargs)

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
            VisStepContent.model_validate(content)
            #  'EXECUTING' | 'FINISHED' | 'FAILED';
            drsk_status = "EXECUTING"
            from derisk.agent.core.schema import Status

            # status = content.get("status", Status.RUNNING.value)
            # if Status.FAILED.value == status:
            #     drsk_status = "FAILED"
            # elif Status.COMPLETE.value == status:
            #     drsk_status = "FINISHED"
            # content["status"] = drsk_status
            message_id = content.get("message_id") + "_" + content.get("uid")
            content["tool_execute_link"] = (
                f"{self._drsk_web_url}/nexa/drsk/tool/execute/content?message_id={message_id}"
            )
            return content
        except ValidationError as e:
            logger.warning(
                f"DrskStep可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "drsk-step"
