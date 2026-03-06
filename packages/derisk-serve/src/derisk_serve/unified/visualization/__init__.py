"""
统一可视化模块
"""

from .models import VisMessageType, VisOutput
from .adapter import UnifiedVisAdapter

__all__ = [
    "VisMessageType",
    "VisOutput",
    "UnifiedVisAdapter",
]


_unified_vis_adapter = None


def get_unified_vis_adapter(system_app=None):
    """获取统一可视化适配器实例"""
    global _unified_vis_adapter
    if _unified_vis_adapter is None:
        _unified_vis_adapter = UnifiedVisAdapter(system_app)
    return _unified_vis_adapter