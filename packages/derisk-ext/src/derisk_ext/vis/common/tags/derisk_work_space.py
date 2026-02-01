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
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class FolderNode(DrskVisBase):
    item_type: Optional[str] = Field(None, description="当前节点所属路径")
    path: Optional[str] = Field(None, description="当前节点所属路径uid")
    conv_id: Optional[str] = Field(None, description="当前节点所属路径对话uid")
    tags: Optional[List[str]]=Field(None, description="当前节点分类标签")
    title: Optional[str] = Field(None, description="当前节点标题")
    description: Optional[str] = Field(None, description="当前节点内容描述")
    status: Optional[str] = Field(None, description="当前节点状态")
    start_time: Optional[Any] = Field(None, description="当前节点开始时间")
    cost: Optional[float] = Field(0, description="当前节点耗时")
    avatar: Optional[str] = Field(None, description="task logo")
    task_type: Optional[str] = Field(None, description="当前节点的具体任务类型，file类型时区分(tool、knowledge, llm、code、file等)")
    markdown: Optional[str] = Field(None, description="当前节点的内容,item_type为 file时存在")
    items: Optional[List['FolderNode']] = Field(None, description="当前节点的子节点信息")



class WorkSpaceContent(DrskVisBase):
    agent_role: Optional[str] = Field(None, description="agent role")
    agent_name: Optional[str] = Field(None, description="agent name")
    description: Optional[str] = Field(None, description="agent description")
    avatar: Optional[str] = Field(None, description="task logo")
    vis: Optional[str] = Field(None, description="this content vis tag")
    running_agents: Optional[List[str]] = Field(None, description="运行的工作项")
    items: Optional[List[FolderNode]] = Field(None, description="工作空间资源内容")
    explorer: Optional[str] = Field(None, description="工作空间资源管理器")
    # markdown: Optional[str] = Field(None, description="")


class WorkSpace(Vis):
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
            WorkSpaceContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"WorkSpace可视化组件收到了非法的数据内容，可能导致显示失败！{content}"
            )
            return content

    @classmethod
    def vis_tag(cls):
        """Vis tag name.

        Returns:
            str: The tag name associated with the visualization.
        """
        return "d-work"
