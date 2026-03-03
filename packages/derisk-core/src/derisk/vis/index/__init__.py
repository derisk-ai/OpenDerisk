"""
VIS Protocol V2 - Index Module

Provides incremental indexing capabilities for O(1) updates.
"""

from .incremental_index import (
    IndexEntry,
    IndexStats,
    DependencyGraph,
    IncrementalIndexManager,
)

__all__ = [
    "IndexEntry",
    "IndexStats",
    "DependencyGraph",
    "IncrementalIndexManager",
]