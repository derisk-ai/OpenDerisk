"""
统一会话模型定义
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class UnifiedMessage:
    """统一消息模型"""
    id: str
    role: str  # user/assistant/system/tool
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class UnifiedSession:
    """统一会话实例"""
    session_id: str
    conv_id: str
    app_code: str
    user_id: str = None
    agent_version: str = "v2"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    storage_conv: Any = None
    runtime_session: Any = None
    history: List[UnifiedMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "conv_id": self.conv_id,
            "app_code": self.app_code,
            "user_id": self.user_id,
            "agent_version": self.agent_version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message_count": self.message_count,
            "metadata": self.metadata,
        }