"""
统一应用构建模块
"""

from .models import UnifiedResource, UnifiedAppInstance
from .builder import UnifiedAppBuilder

__all__ = [
    "UnifiedResource",
    "UnifiedAppInstance",
    "UnifiedAppBuilder",
]


_unified_app_builder = None


def get_unified_app_builder(system_app=None):
    """获取统一应用构建器实例"""
    global _unified_app_builder
    if _unified_app_builder is None:
        _unified_app_builder = UnifiedAppBuilder(system_app)
    return _unified_app_builder