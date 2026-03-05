"""
统一可视化模型定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict


class VisMessageType(str, Enum):
    """可视化消息类型"""
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    RESPONSE = "response"
    ERROR = "error"
    CODE = "code"
    CHART = "chart"
    FILE = "file"
    IMAGE = "image"


@dataclass
class VisOutput:
    """可视化输出"""
    type: VisMessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }