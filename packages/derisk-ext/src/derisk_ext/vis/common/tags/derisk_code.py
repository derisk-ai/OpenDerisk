import logging
from datetime import datetime
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
from derisk.agent.core.action.base import OutputType
from derisk.vis import Vis
from derisk.vis.schema import VisStepContent, VisBase

logger = logging.getLogger(__name__)


class CodeItem(VisBase):
    exit_success: Optional[bool] = Field(default=None, description="执行成功状态")
    name: Optional[str] = Field(default=None, description="名称")
    path: Optional[str] = Field(default=None, description="路径")
    language: Optional[str] = Field(default=None, description="代码语言")
    markdown: Optional[str] = Field(default=None, description="代码内容")
    console: Optional[str] = Field(default=None, description="控制台输出")
    env: Optional[str] = Field(default="", description="执行环境")
    start_time: Optional[Any] = Field(default="", description="开始时间")
    cost: Optional[int] = Field(default=0, description="执行耗时")


class CodeContent(VisBase):
    name: Optional[str] = Field(default="", description="名称")
    items: Optional[List[CodeItem]] = Field(default=None, description="子项列表")
    thought: Optional[str] = Field(default="", description="思考内容")
    markdown: Optional[str] = Field(default=None, description="思考内容")
    start_time: Optional[Any] = Field(default="", description="开始时间")


class CodeSpace(Vis):
    """Monitor Space."""

    def __init__(self, **kwargs):
        self._derisk_web_url = kwargs.get("derisk_web_url", "")
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
            CodeContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"CodeSpace可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "d-code"
