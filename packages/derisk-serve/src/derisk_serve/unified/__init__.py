"""
统一用户产品层架构

提供统一的接口层，支持V1/V2 Agent架构的透明接入
"""

from .application import UnifiedAppBuilder, UnifiedAppInstance
from .session import UnifiedSessionManager, UnifiedSession
from .interaction import UnifiedInteractionGateway
from .visualization import UnifiedVisAdapter

__all__ = [
    "UnifiedAppBuilder",
    "UnifiedAppInstance",
    "UnifiedSessionManager",
    "UnifiedSession",
    "UnifiedInteractionGateway",
    "UnifiedVisAdapter",
]