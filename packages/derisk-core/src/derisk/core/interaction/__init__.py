"""
Interaction Module - Unified Tool Authorization System

This module provides the interaction system:
- Protocol: Interaction types, requests, and responses
- Gateway: Interaction gateway for user communication

Version: 2.0
"""

from .protocol import (
    InteractionType,
    InteractionPriority,
    InteractionStatus,
    InteractionOption,
    InteractionRequest,
    InteractionResponse,
    # Convenience functions
    create_authorization_request,
    create_text_input_request,
    create_confirmation_request,
    create_selection_request,
    create_notification,
    create_progress_update,
)

from .gateway import (
    ConnectionManager,
    MemoryConnectionManager,
    StateStore,
    MemoryStateStore,
    InteractionGateway,
    get_interaction_gateway,
)

__all__ = [
    # Protocol
    "InteractionType",
    "InteractionPriority",
    "InteractionStatus",
    "InteractionOption",
    "InteractionRequest",
    "InteractionResponse",
    "create_authorization_request",
    "create_text_input_request",
    "create_confirmation_request",
    "create_selection_request",
    "create_notification",
    "create_progress_update",
    # Gateway
    "ConnectionManager",
    "MemoryConnectionManager",
    "StateStore",
    "MemoryStateStore",
    "InteractionGateway",
    "get_interaction_gateway",
]
