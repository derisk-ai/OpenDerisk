import logging
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic_core._pydantic_core import ValidationError

from derisk._private.pydantic import (
    Field,
)
from derisk.agent.core.schema import Status
from derisk.vis import Vis

from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class AgentPlanItem(DrskVisBase):
    item_type: Optional[str] = Field(
        None, description="规划数据类型(plan、 agent、stage、task)"
    )
    parent_uid: Optional[str] = Field(
        None, description="父节点UID，用于前端构建树形结构"
    )
    title: Optional[str] = Field(None, description="当前工作项标题")
    agent_name: Optional[str] = Field(None, description="当前工作项所属Agent")
    agent_avatar: Optional[str] = Field(None, description="当前工作项所属Agent logo")
    description: Optional[str] = Field(None, description="当前工作项内容描述")
    task_type: Optional[str] = Field(
        None, description="当前工作项任务类型，report、tool、agent、knoledge"
    )
    status: Optional[str] = Field(Status.TODO.value, description="当前工作项状态")
    start_time: Optional[datetime] = Field(None, description="当前工作项开始时间")
    cost: Optional[float] = Field(None, description="当前工作项耗时")
    markdown: Optional[str] = Field(None, description="计划内容")
    layer_count: int = Field(0, description="当前工作项的嵌套深度")


class AgentPlan(Vis):
    """AgentPlan."""

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
            AgentPlanItem.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"AgentPlan可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "d-agent-plan"
