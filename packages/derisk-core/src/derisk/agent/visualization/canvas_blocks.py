"""
Canvas Blocks - Canvas 可视化块定义

参考 OpenClaw 的 Block Streaming 设计
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import uuid


class ElementType(str, Enum):
    TEXT = "text"
    CODE = "code"
    CHART = "chart"
    TABLE = "table"
    IMAGE = "image"
    FILE = "file"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TASK = "task"
    PLAN = "plan"
    ERROR = "error"


class ElementStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Position(BaseModel):
    x: int = 0
    y: int = 0
    width: Optional[int] = None
    height: Optional[int] = None


class Style(BaseModel):
    background: Optional[str] = None
    color: Optional[str] = None
    font_size: Optional[int] = None
    border: Optional[str] = None


class CanvasElement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    type: ElementType
    content: Any
    position: Position = Field(default_factory=Position)
    style: Style = Field(default_factory=Style)
    status: ElementStatus = ElementStatus.COMPLETED
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    children: List["CanvasElement"] = Field(default_factory=list)

    class Config:
        use_enum_values = True


CanvasElement.model_rebuild()


class CanvasBlock(BaseModel):
    block_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    block_type: str
    content: Any
    title: Optional[str] = None
    collapsible: bool = False
    expanded: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ThinkingBlock(CanvasBlock):
    block_type: str = "thinking"
    thoughts: List[str] = Field(default_factory=list)
    reasoning: Optional[str] = None


class ToolCallBlock(CanvasBlock):
    block_type: str = "tool_call"
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[str] = None
    execution_time: Optional[float] = None
    status: str = "pending"


class MessageBlock(CanvasBlock):
    block_type: str = "message"
    role: str
    content: str
    round: int = 0


class TaskBlock(CanvasBlock):
    block_type: str = "task"
    task_name: str
    description: Optional[str] = None
    status: str = "pending"
    subtasks: List["TaskBlock"] = Field(default_factory=list)


class PlanBlock(CanvasBlock):
    block_type: str = "plan"
    stages: List[Dict[str, Any]] = Field(default_factory=list)
    current_stage: int = 0


class ErrorBlock(CanvasBlock):
    block_type: str = "error"
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None


class FileBlock(CanvasBlock):
    block_type: str = "file"
    file_name: str
    file_type: str
    file_path: Optional[str] = None
    preview: Optional[str] = None


class CodeBlock(CanvasBlock):
    block_type: str = "code"
    language: str = "python"
    code: str
    line_numbers: bool = True


class ChartBlock(CanvasBlock):
    block_type: str = "chart"
    chart_type: str
    data: Dict[str, Any]
    options: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ElementType",
    "ElementStatus",
    "Position",
    "Style",
    "CanvasElement",
    "CanvasBlock",
    "ThinkingBlock",
    "ToolCallBlock",
    "MessageBlock",
    "TaskBlock",
    "PlanBlock",
    "ErrorBlock",
    "FileBlock",
    "CodeBlock",
    "ChartBlock",
]
