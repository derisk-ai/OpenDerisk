"""Unified Memory Framework for Derisk.

This module provides a unified memory interface that combines:
1. Vector storage for semantic search
2. File-backed storage for Git-friendly sharing
3. Claude Code compatible memory format
4. GptsMemory adapter for Core V1/V2 integration
"""

from .base import (
    MemoryItem,
    MemoryType,
    SearchOptions,
    UnifiedMemoryInterface,
    MemoryConsolidationResult,
)
from .file_backed_storage import FileBackedStorage
from .unified_manager import UnifiedMemoryManager
from .claude_compatible import ClaudeCodeCompatibleMemory
from .gpts_adapter import GptsMemoryAdapter
from .message_converter import (
    MessageConverter,
    gpts_to_agent,
    agent_to_gpts,
)

__all__ = [
    # Base classes
    "MemoryItem",
    "MemoryType",
    "SearchOptions",
    "UnifiedMemoryInterface",
    "MemoryConsolidationResult",
    # Storage implementations
    "FileBackedStorage",
    "UnifiedMemoryManager",
    "ClaudeCodeCompatibleMemory",
    "GptsMemoryAdapter",
    # Message conversion
    "MessageConverter",
    "gpts_to_agent",
    "agent_to_gpts",
]