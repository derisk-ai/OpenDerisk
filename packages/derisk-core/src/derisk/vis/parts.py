"""
VIS Part系统 - 统一的Part数据结构定义

提供：
- PartType: Part类型枚举
- PartStatus: Part状态枚举
- VisPart: 基础Part类
- 具体Part类型: TextPart, CodePart, ToolUsePart等
- PartContainer: Part容器
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union

from pydantic import BaseModel, Field


class PartStatus(str, Enum):
    """Part状态枚举"""
    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    ERROR = "error"


class PartType(str, Enum):
    """Part类型枚举"""
    TEXT = "text"
    CODE = "code"
    TOOL_USE = "tool_use"
    THINKING = "thinking"
    PLAN = "plan"
    IMAGE = "image"
    FILE = "file"
    INTERACTION = "interaction"
    ERROR = "error"


class VisPart(BaseModel):
    """基础Part类 - 所有Part类型的基类"""
    
    type: PartType = Field(default=PartType.TEXT, description="Part类型")
    status: PartStatus = Field(default=PartStatus.PENDING, description="Part状态")
    uid: str = Field(default_factory=lambda: str(uuid.uuid4()), description="唯一标识")
    content: str = Field(default="", description="内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    updated_at: Optional[str] = Field(default=None, description="更新时间")
    parent_uid: Optional[str] = Field(default=None, description="父Part UID")
    
    model_config = {"extra": "allow"}
    
    def __init__(self, **data):
        if "created_at" not in data or data["created_at"] is None:
            data["created_at"] = datetime.now().isoformat()
        if "updated_at" not in data or data["updated_at"] is None:
            data["updated_at"] = data["created_at"]
        super().__init__(**data)
    
    @classmethod
    def create(cls, streaming: bool = False, **kwargs) -> "VisPart":
        """创建Part的工厂方法"""
        if streaming:
            kwargs["status"] = PartStatus.STREAMING
        return cls(**kwargs)
    
    def is_streaming(self) -> bool:
        """检查是否处于流式状态"""
        return self.status == PartStatus.STREAMING
    
    def is_completed(self) -> bool:
        """检查是否已完成"""
        return self.status == PartStatus.COMPLETED
    
    def is_error(self) -> bool:
        """检查是否处于错误状态"""
        return self.status == PartStatus.ERROR
    
    def is_pending(self) -> bool:
        """检查是否处于等待状态"""
        return self.status == PartStatus.PENDING
    
    def append(self, chunk: str) -> "VisPart":
        """追加内容（用于流式输出）"""
        return self.model_copy(update={
            "content": self.content + chunk,
            "updated_at": datetime.now().isoformat()
        })
    
    def complete(self) -> "VisPart":
        """标记为完成"""
        return self.model_copy(update={
            "status": PartStatus.COMPLETED,
            "updated_at": datetime.now().isoformat()
        })
    
    def mark_error(self, error_message: str) -> "VisPart":
        """标记为错误状态"""
        return self.model_copy(update={
            "status": PartStatus.ERROR,
            "content": f"{self.content}\n[ERROR] {error_message}" if self.content else f"[ERROR] {error_message}",
            "updated_at": datetime.now().isoformat()
        })
    
    def update_metadata(self, **kwargs) -> "VisPart":
        """更新元数据"""
        new_metadata = {**self.metadata, **kwargs}
        return self.model_copy(update={
            "metadata": new_metadata,
            "updated_at": datetime.now().isoformat()
        })
    
    def to_vis_dict(self) -> Dict[str, Any]:
        """转换为VIS协议字典格式"""
        return {
            "uid": self.uid,
            "type": "incr" if self.is_streaming() else "all",
            "status": self.status.value,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为普通字典"""
        return self.model_dump()


class TextPart(VisPart):
    """文本Part"""
    
    type: PartType = Field(default=PartType.TEXT)
    format: str = Field(default="markdown", description="格式: markdown, plain, html")
    
    @classmethod
    def create(cls, content: str = "", streaming: bool = False, **kwargs) -> "TextPart":
        """创建文本Part"""
        if streaming:
            kwargs["status"] = PartStatus.STREAMING
        return cls(content=content, **kwargs)


class CodePart(VisPart):
    """代码Part"""
    
    type: PartType = Field(default=PartType.CODE)
    language: str = Field(default="python", description="编程语言")
    filename: Optional[str] = Field(default=None, description="文件名")
    line_numbers: bool = Field(default=True, description="是否显示行号")
    
    @classmethod
    def create(
        cls,
        code: str = "",
        language: str = "python",
        filename: Optional[str] = None,
        streaming: bool = False,
        **kwargs
    ) -> "CodePart":
        """创建代码Part"""
        if streaming:
            kwargs["status"] = PartStatus.STREAMING
        return cls(
            content=code,
            language=language,
            filename=filename,
            **kwargs
        )


class ToolUsePart(VisPart):
    """工具使用Part"""
    
    type: PartType = Field(default=PartType.TOOL_USE)
    tool_name: str = Field(default="", description="工具名称")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    tool_result: Optional[str] = Field(default=None, description="工具执行结果")
    tool_error: Optional[str] = Field(default=None, description="工具执行错误")
    execution_time: Optional[float] = Field(default=None, description="执行时间(秒)")
    
    @classmethod
    def create(
        cls,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        streaming: bool = True,
        **kwargs
    ) -> "ToolUsePart":
        """创建工具使用Part"""
        if streaming:
            kwargs["status"] = PartStatus.STREAMING
        return cls(
            tool_name=tool_name,
            tool_args=tool_args or {},
            **kwargs
        )
    
    def set_result(self, result: str, execution_time: Optional[float] = None) -> "ToolUsePart":
        """设置工具执行结果"""
        return self.model_copy(update={
            "tool_result": result,
            "execution_time": execution_time,
            "status": PartStatus.COMPLETED,
            "updated_at": datetime.now().isoformat()
        })
    
    def set_error(self, error: str) -> "ToolUsePart":
        """设置工具执行错误"""
        return self.model_copy(update={
            "tool_error": error,
            "status": PartStatus.ERROR,
            "updated_at": datetime.now().isoformat()
        })


class ThinkingPart(VisPart):
    """思考Part"""
    
    type: PartType = Field(default=PartType.THINKING)
    expand: bool = Field(default=False, description="是否展开显示")
    think_link: Optional[str] = Field(default=None, description="思考链接")
    
    @classmethod
    def create(
        cls,
        content: str = "",
        expand: bool = False,
        streaming: bool = False,
        **kwargs
    ) -> "ThinkingPart":
        """创建思考Part"""
        if streaming:
            kwargs["status"] = PartStatus.STREAMING
        return cls(content=content, expand=expand, **kwargs)


class PlanItem(BaseModel):
    """计划项"""
    task: str = Field(default="", description="任务描述")
    status: str = Field(default="pending", description="状态: pending, working, completed, failed")


class PlanPart(VisPart):
    """计划Part"""
    
    type: PartType = Field(default=PartType.PLAN)
    title: Optional[str] = Field(default=None, description="计划标题")
    items: List[Dict[str, Any]] = Field(default_factory=list, description="计划项列表")
    current_index: int = Field(default=0, description="当前执行项索引")
    
    @classmethod
    def create(
        cls,
        title: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None,
        streaming: bool = False,
        **kwargs
    ) -> "PlanPart":
        """创建计划Part"""
        if streaming:
            kwargs["status"] = PartStatus.STREAMING
        return cls(title=title, items=items or [], **kwargs)
    
    def update_progress(self, index: int) -> "PlanPart":
        """更新计划进度"""
        new_items = []
        for i, item in enumerate(self.items):
            new_item = dict(item)
            if i < index:
                new_item["status"] = "completed"
            elif i == index:
                new_item["status"] = "working"
            else:
                new_item["status"] = "pending"
            new_items.append(new_item)
        
        return self.model_copy(update={
            "items": new_items,
            "current_index": index,
            "updated_at": datetime.now().isoformat()
        })
    
    def complete_plan(self) -> "PlanPart":
        """完成计划"""
        new_items = [
            {**item, "status": "completed"}
            for item in self.items
        ]
        return self.model_copy(update={
            "items": new_items,
            "status": PartStatus.COMPLETED,
            "updated_at": datetime.now().isoformat()
        })


class ImagePart(VisPart):
    """图片Part"""
    
    type: PartType = Field(default=PartType.IMAGE)
    url: str = Field(default="", description="图片URL")
    alt: Optional[str] = Field(default=None, description="替代文本")
    width: Optional[int] = Field(default=None, description="宽度")
    height: Optional[int] = Field(default=None, description="高度")
    
    @classmethod
    def create(
        cls,
        url: str,
        alt: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **kwargs
    ) -> "ImagePart":
        """创建图片Part"""
        return cls(url=url, alt=alt, width=width, height=height, **kwargs)


class FilePart(VisPart):
    """文件Part"""
    
    type: PartType = Field(default=PartType.FILE)
    filename: str = Field(default="", description="文件名")
    size: Optional[int] = Field(default=None, description="文件大小(字节)")
    file_type: Optional[str] = Field(default=None, description="文件类型")
    url: Optional[str] = Field(default=None, description="文件URL")
    
    @classmethod
    def create(
        cls,
        filename: str,
        size: Optional[int] = None,
        file_type: Optional[str] = None,
        url: Optional[str] = None,
        **kwargs
    ) -> "FilePart":
        """创建文件Part"""
        return cls(filename=filename, size=size, file_type=file_type, url=url, **kwargs)


class InteractionPart(VisPart):
    """交互Part"""
    
    type: PartType = Field(default=PartType.INTERACTION)
    interaction_type: str = Field(default="confirm", description="交互类型: confirm, select, input")
    message: str = Field(default="", description="交互消息")
    options: List[str] = Field(default_factory=list, description="选项列表")
    default_choice: Optional[str] = Field(default=None, description="默认选择")
    response: Optional[str] = Field(default=None, description="用户响应")
    
    @classmethod
    def create(
        cls,
        interaction_type: str,
        message: str,
        options: Optional[List[str]] = None,
        default_choice: Optional[str] = None,
        **kwargs
    ) -> "InteractionPart":
        """创建交互Part"""
        return cls(
            interaction_type=interaction_type,
            message=message,
            options=options or [],
            default_choice=default_choice,
            **kwargs
        )


class ErrorPart(VisPart):
    """错误Part"""
    
    type: PartType = Field(default=PartType.ERROR)
    error_type: str = Field(default="", description="错误类型")
    stack_trace: Optional[str] = Field(default=None, description="堆栈跟踪")
    
    @classmethod
    def create(
        cls,
        content: str,
        error_type: str = "Error",
        stack_trace: Optional[str] = None,
        **kwargs
    ) -> "ErrorPart":
        """创建错误Part"""
        kwargs["status"] = PartStatus.ERROR
        return cls(content=content, error_type=error_type, stack_trace=stack_trace, **kwargs)


class PartContainer:
    """Part容器 - 管理多个Part"""
    
    def __init__(self):
        self._parts: Dict[str, VisPart] = {}
        self._order: List[str] = []
    
    def __len__(self) -> int:
        return len(self._parts)
    
    def __iter__(self):
        for uid in self._order:
            yield self._parts[uid]
    
    def __getitem__(self, index: int) -> VisPart:
        return self._parts[self._order[index]]
    
    def add_part(self, part: VisPart) -> str:
        """添加Part，返回UID"""
        self._parts[part.uid] = part
        if part.uid not in self._order:
            self._order.append(part.uid)
        return part.uid
    
    def get_part(self, uid: str) -> Optional[VisPart]:
        """通过UID获取Part"""
        return self._parts.get(uid)
    
    def update_part(
        self,
        uid: str,
        update_fn: Callable[[VisPart], VisPart]
    ) -> Optional[VisPart]:
        """更新Part"""
        part = self._parts.get(uid)
        if part is None:
            return None
        
        updated = update_fn(part)
        self._parts[uid] = updated
        return updated
    
    def remove_part(self, uid: str) -> bool:
        """移除Part"""
        if uid in self._parts:
            del self._parts[uid]
            self._order.remove(uid)
            return True
        return False
    
    def get_parts_by_type(self, part_type: PartType) -> List[VisPart]:
        """按类型获取Part列表"""
        return [
            part for part in self._parts.values()
            if part.type == part_type
        ]
    
    def get_parts_by_status(self, status: PartStatus) -> List[VisPart]:
        """按状态获取Part列表"""
        return [
            part for part in self._parts.values()
            if part.status == status
        ]
    
    def to_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表"""
        return [self._parts[uid].to_dict() for uid in self._order]
    
    def clear(self):
        """清空容器"""
        self._parts.clear()
        self._order.clear()


# 导出所有类型
__all__ = [
    "PartType",
    "PartStatus",
    "VisPart",
    "TextPart",
    "CodePart",
    "ToolUsePart",
    "ThinkingPart",
    "PlanPart",
    "PlanItem",
    "ImagePart",
    "FilePart",
    "InteractionPart",
    "ErrorPart",
    "PartContainer",
]
