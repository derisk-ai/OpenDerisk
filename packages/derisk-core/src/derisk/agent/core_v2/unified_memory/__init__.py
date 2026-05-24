"""Unified Memory Framework for Derisk.

This module provides a unified memory interface that combines:
1. Vector storage for semantic search
2. File-backed storage for Git-friendly sharing
3. Claude Code compatible memory format
4. GptsMemory adapter for Core V1/V2 integration
5. Long-term memory manager for Memory-type knowledge spaces
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
from .longterm_manager import (
    LongTermMemoryConfig,
    LongTermMemoryManager,
    create_long_term_memory_manager,
    MemoryIntegrationBundle,
    create_memory_integration_bundle,
)
from .store_adapter import MemoryStoreAdapter
from .pipeline import MemoryPipeline
from derisk.storage.memory.processor import MemoryProcessor
from derisk.storage.memory.strategy import MemorySpaceStrategy
from derisk.storage.memory.recall_tracker import RecallTracker

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
    # Long-term memory
    "LongTermMemoryConfig",
    "LongTermMemoryManager",
    "create_long_term_memory_manager",
    # Message conversion
    "MessageConverter",
    "gpts_to_agent",
    "agent_to_gpts",
    # Memory processing (NEW)
    "MemoryProcessor",
    "MemorySpaceStrategy",
    "RecallTracker",
    # Full integration bundle (NEW)
    "MemoryIntegrationBundle",
    "create_memory_integration_bundle",
    # Store adapter (NEW)
    "MemoryStoreAdapter",
    # Memory pipeline (NEW)
    "MemoryPipeline",
]