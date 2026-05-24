"""Memory processing extensions for OpenDerisk.

This module provides LLM-based memory processing capabilities
that integrate with the MemoryStoreBase storage layer.
"""

from .llm_processor import LLMMemoryProcessor

__all__ = [
    "LLMMemoryProcessor",
]
