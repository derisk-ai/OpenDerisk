"""
统一会话管理模块
"""

from .models import UnifiedMessage, UnifiedSession
from .manager import UnifiedSessionManager

__all__ = [
    "UnifiedMessage",
    "UnifiedSession",
    "UnifiedSessionManager",
]


_unified_session_manager = None


def get_unified_session_manager(system_app=None):
    """获取统一会话管理器实例"""
    global _unified_session_manager
    if _unified_session_manager is None:
        _unified_session_manager = UnifiedSessionManager(system_app)
    return _unified_session_manager