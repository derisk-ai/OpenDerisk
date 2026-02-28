"""
Interaction Module - 统一交互模块

提供 Agent 与用户之间的标准化交互能力
支持多种交互类型、状态管理和恢复机制
"""

from .interaction_protocol import (
    InteractionType,
    InteractionPriority,
    InteractionStatus,
    NotifyLevel,
    InteractionOption,
    InteractionRequest,
    InteractionResponse,
    TodoItem,
    InterruptPoint,
    RecoveryState,
    RecoveryResult,
    ResumeResult,
    InteractionError,
    InteractionTimeoutError,
    InteractionCancelledError,
    InteractionPendingError,
    RecoveryError,
)

from .interaction_gateway import (
    StateStore,
    MemoryStateStore,
    WebSocketManager,
    MockWebSocketManager,
    InteractionGateway,
    get_interaction_gateway,
    set_interaction_gateway,
)

from .recovery_coordinator import (
    RecoveryCoordinator,
    get_recovery_coordinator,
    set_recovery_coordinator,
)


__all__ = [
    # Protocol
    "InteractionType",
    "InteractionPriority",
    "InteractionStatus",
    "NotifyLevel",
    "InteractionOption",
    "InteractionRequest",
    "InteractionResponse",
    "TodoItem",
    "InterruptPoint",
    "RecoveryState",
    "RecoveryResult",
    "ResumeResult",
    # Exceptions
    "InteractionError",
    "InteractionTimeoutError",
    "InteractionCancelledError",
    "InteractionPendingError",
    "RecoveryError",
    # Gateway
    "StateStore",
    "MemoryStateStore",
    "WebSocketManager",
    "MockWebSocketManager",
    "InteractionGateway",
    "get_interaction_gateway",
    "set_interaction_gateway",
    # Recovery
    "RecoveryCoordinator",
    "get_recovery_coordinator",
    "set_recovery_coordinator",
]