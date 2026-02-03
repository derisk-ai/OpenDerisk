import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Union

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


class MonitorSpaceContent(VisBase):
    tool_args: Optional[dict] = Field(default_factory=dict, description="工具参数")
    status: Optional[str] = Field(default="todo", description="任务状态")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    tool_desc: Optional[str] = Field(default=None, description="工具描述")
    tool_version: Optional[str] = Field(default=None, description="工具版本")
    tool_author: Optional[str] = Field(default=None, description="工具作者")
    run_env: Optional[str] = Field(default=None, description="运行环境")
    tool_cost: float = Field(default=0, description="工具成本")
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    out_type: str = Field(default="json", description="输出类型")
    data: Optional[Union[dict, str, list]] = Field(default=None, description="数据文件路径或URL")
    group_colums: Optional[List[str]] = Field(default=None, description="分组列")
    time_colum: Optional[str] = Field(default=None, description="时间列")
    progress: int = Field(default=0, description="进度")
    eval_view: Optional[dict] = Field(default=None, description="评测过程信息")
class MonitorSpace(Vis):
    """Monitor Space."""

    def __init__(self, **kwargs):
        self._derisk_web_url = kwargs.get( "derisk_web_url", "")
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
            MonitorSpaceContent.model_validate(content)
            #  'EXECUTING' | 'FINISHED' | 'FAILED';
            from derisk.agent.core.schema import Status
            status = content.get("status", Status.RUNNING.value)
            drsk_status = "EXECUTING"
            if Status.FAILED.value == status:
                drsk_status = "FAILED"
            elif Status.COMPLETE.value == status:
                drsk_status = "FINISHED"
            content["status"] = drsk_status

            return content
        except ValidationError as e:
            logger.warning(
                f"MonitorSpace可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "d-monitor"
