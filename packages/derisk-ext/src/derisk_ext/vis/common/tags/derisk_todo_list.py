"""
看板TodoList可视化组件
用于在planning_window区域展示Agent的看板stage进度

设计理念：
- 轻量级：只包含必要的状态和展示信息
- 状态映射清晰：明确的状态转换规则
- 错误容错：异常情况下不影响整体可视化流程
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List, Literal
from enum import Enum

from pydantic_core._pydantic_core import ValidationError
from derisk._private.pydantic import (
    Field,
    field_validator,
)

from derisk.vis import Vis
from derisk_ext.vis.derisk.tags.drsk_base import DrskVisBase

logger = logging.getLogger(__name__)


class TodoStatus(str, Enum):
    """Todo状态枚举"""
    PENDING = "pending"  # 待完成
    WORKING = "working"  # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class TodoItem(DrskVisBase):
    """Todo列表项"""
    id: str = Field(..., description="todo item id")
    title: str = Field(..., description="todo item title")
    description: Optional[str] = Field(None, description="todo item description")
    status: TodoStatus = Field(TodoStatus.PENDING, description="todo item status")
    index: int = Field(0, description="todo item order index")

    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """验证状态值，确保是有效的TodoStatus"""
        if isinstance(v, str):
            try:
                return TodoStatus(v.lower())
            except ValueError:
                logger.warning(f"Invalid todo status '{v}', defaulting to PENDING")
                return TodoStatus.PENDING
        return v


class TodoListContent(DrskVisBase):
    """TodoList内容"""
    agent_name: Optional[str] = Field(None, description="所属Agent名称")
    agent_avatar: Optional[str] = Field(None, description="所属Agent头像")
    mission: Optional[str] = Field(None, description="看板任务描述")
    items: List[TodoItem] = Field(default_factory=list, description="todo列表项")
    current_index: int = Field(0, description="当前执行的todo项索引", ge=0)

    @field_validator('current_index')
    @classmethod
    def validate_current_index(cls, v, info):
        """验证current_index不超过items数量"""
        items = info.data.get('items', [])
        if v >= len(items) and len(items) > 0:
            logger.warning(f"current_index {v} exceeds items count {len(items)}, setting to last index")
            return max(0, len(items) - 1)
        return v


class TodoList(Vis):
    """TodoList可视化组件"""

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """生成vis协议所需的参数

        使用vis协议显示对应内容

        Args:
            **kwargs:

        Returns:
            vis protocol data
        """
        content = kwargs["content"]
        try:
            TodoListContent.model_validate(content)
            return content
        except ValidationError as e:
            logger.warning(
                f"TodoList可视化组件收到了非法的数据内容，可能导致显示失败！{content}，错误: {e}"
            )
            # 返回原始内容，让前端处理
            return content
        except Exception as e:
            logger.exception(f"TodoList组件验证异常: {e}")
            return content

    @classmethod
    def vis_tag(cls):
        """Vis标签名称

        Returns:
            str: 关联的可视化标签
        """
        return "d-todo-list"