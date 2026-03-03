"""
统一交互模型定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class InteractionType(str, Enum):
    """交互类型"""
    TEXT_INPUT = "text_input"
    OPTION_SELECT = "option_select"
    FILE_UPLOAD = "file_upload"
    CONFIRMATION = "confirmation"
    MULTI_SELECT = "multi_select"


class InteractionStatus(str, Enum):
    """交互状态"""
    PENDING = "pending"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class InteractionRequest:
    """交互请求"""
    request_id: str
    interaction_type: InteractionType
    question: str
    options: List[str] = None
    default_value: str = None
    timeout: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InteractionResponse:
    """交互响应"""
    request_id: str
    response: str
    status: InteractionStatus
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileUploadRequest:
    """文件上传请求"""
    request_id: str
    allowed_types: List[str] = field(default_factory=list)
    max_size: int = 10 * 1024 * 1024  # 10MB
    multiple: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileUploadResponse:
    """文件上传响应"""
    request_id: str
    file_ids: List[str]
    file_names: List[str]
    status: InteractionStatus
    metadata: Dict[str, Any] = field(default_factory=dict)