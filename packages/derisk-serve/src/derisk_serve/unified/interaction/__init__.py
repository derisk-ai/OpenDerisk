"""
统一用户交互模块
"""

from .models import (
    InteractionType,
    InteractionStatus,
    InteractionRequest,
    InteractionResponse,
    FileUploadRequest,
    FileUploadResponse,
)
from .gateway import UnifiedInteractionGateway

__all__ = [
    "InteractionType",
    "InteractionStatus",
    "InteractionRequest",
    "InteractionResponse",
    "FileUploadRequest",
    "FileUploadResponse",
    "UnifiedInteractionGateway",
]


_unified_interaction_gateway = None


def get_unified_interaction_gateway(system_app=None):
    """获取统一交互网关实例"""
    global _unified_interaction_gateway
    if _unified_interaction_gateway is None:
        _unified_interaction_gateway = UnifiedInteractionGateway(system_app)
    return _unified_interaction_gateway