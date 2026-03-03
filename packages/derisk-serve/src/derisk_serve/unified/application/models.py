"""
统一应用模型定义
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class UnifiedResource:
    """统一资源模型"""
    type: str
    name: str
    config: Dict[str, Any] = field(default_factory=dict)
    version: str = "v2"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedAppInstance:
    """统一应用实例"""
    app_code: str
    app_name: str
    agent: Any
    version: str
    resources: List[UnifiedResource] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_code": self.app_code,
            "app_name": self.app_name,
            "version": self.version,
            "resources": [r.__dict__ for r in self.resources],
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }