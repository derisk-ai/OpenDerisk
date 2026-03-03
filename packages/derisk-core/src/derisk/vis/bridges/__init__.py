"""
VIS桥接层模块

提供不同Agent架构到统一VIS系统的桥接
"""

from .core_bridge import CoreVisBridge  # noqa: F401
from .core_v2_bridge import CoreV2VisBridge  # noqa: F401

__all__ = [
    "CoreVisBridge",
    "CoreV2VisBridge",
]