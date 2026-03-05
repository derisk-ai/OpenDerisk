"""
VIS Protocol V2 - Incremental Index Manager

Provides O(1) incremental index updates instead of O(n) full rebuilds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from weakref import WeakValueDictionary

logger = logging.getLogger(__name__)


@dataclass
class IndexEntry:
    """Entry in the incremental index."""
    
    uid: str
    node: Any
    node_type: str
    parent_uid: Optional[str] = None
    depth: int = 0
    path: List[str] = field(default_factory=list)
    
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    
    markdown_host_uid: Optional[str] = None
    items_host_uid: Optional[str] = None
    item_index: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "node_type": self.node_type,
            "parent_uid": self.parent_uid,
            "depth": self.depth,
            "path": self.path,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
        }


@dataclass
class IndexStats:
    """Statistics about the index."""
    
    total_entries: int = 0
    max_depth: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    orphan_count: int = 0
    circular_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "max_depth": self.max_depth,
            "by_type": self.by_type,
            "orphan_count": self.orphan_count,
            "circular_count": self.circular_count,
        }


class DependencyGraph:
    """
    Dependency graph for tracking component relationships.
    
    Used to compute affected nodes during incremental updates.
    """
    
    def __init__(self):
        self._edges: Dict[str, Set[str]] = {}
        self._reverse_edges: Dict[str, Set[str]] = {}
    
    def add_edge(self, from_uid: str, to_uid: str) -> None:
        """Add a dependency edge: from_uid depends on to_uid."""
        if from_uid not in self._edges:
            self._edges[from_uid] = set()
        self._edges[from_uid].add(to_uid)
        
        if to_uid not in self._reverse_edges:
            self._reverse_edges[to_uid] = set()
        self._reverse_edges[to_uid].add(from_uid)
    
    def remove_edge(self, from_uid: str, to_uid: str) -> None:
        """Remove a dependency edge."""
        if from_uid in self._edges:
            self._edges[from_uid].discard(to_uid)
        if to_uid in self._reverse_edges:
            self._reverse_edges[to_uid].discard(from_uid)
    
    def remove_node(self, uid: str) -> None:
        """Remove a node and all its edges."""
        for dep in list(self._edges.get(uid, set())):
            self.remove_edge(uid, dep)
        for dependent in list(self._reverse_edges.get(uid, set())):
            self.remove_edge(dependent, uid)
        
        self._edges.pop(uid, None)
        self._reverse_edges.pop(uid, None)
    
    def get_dependencies(self, uid: str) -> Set[str]:
        """Get all nodes this node depends on."""
        return self._edges.get(uid, set()).copy()
    
    def get_dependents(self, uid: str) -> Set[str]:
        """Get all nodes that depend on this node."""
        return self._reverse_edges.get(uid, set()).copy()
    
    def get_all_dependents(self, uid: str) -> Set[str]:
        """Get all transitive dependents (descendants) of a node."""
        result = set()
        queue = list(self.get_dependents(uid))
        
        while queue:
            current = queue.pop(0)
            if current in result:
                continue
            result.add(current)
            queue.extend(self.get_dependents(current))
        
        return result
    
    def detect_cycle(self, uid: str) -> Optional[List[str]]:
        """Detect if there's a cycle involving this node."""
        visited = set()
        path = []
        
        def dfs(node: str) -> Optional[List[str]]:
            if node in path:
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]
            
            if node in visited:
                return None
            
            visited.add(node)
            path.append(node)
            
            for dep in self._edges.get(node, set()):
                cycle = dfs(dep)
                if cycle:
                    return cycle
            
            path.pop()
            return None
        
        return dfs(uid)


class IncrementalIndexManager:
    """
    Incremental index manager for VIS components.
    
    Key improvements over VisBaseParser's rebuildIndex():
    - O(1) single-node updates vs O(n) full rebuild
    - Dependency tracking for efficient invalidation
    - Circular reference detection
    - Memory-efficient with weak references
    """
    
    MAX_DEPTH = 100
    
    def __init__(self):
        self._index: Dict[str, IndexEntry] = {}
        self._dependency_graph = DependencyGraph()
        self._change_callbacks: List[Callable[[str, IndexEntry], None]] = []
        self._bulk_mode = False
        self._pending_changes: Set[str] = set()
    
    def get(self, uid: str) -> Optional[IndexEntry]:
        """Get index entry by UID - O(1) lookup."""
        return self._index.get(uid)
    
    def has(self, uid: str) -> bool:
        """Check if UID exists in index - O(1)."""
        return uid in self._index
    
    def add(self, entry: IndexEntry) -> None:
        """
        Add or update an index entry - O(1) amortized.
        
        Automatically:
        - Updates dependency graph
        - Detects circular references
        - Notifies change listeners
        """
        if len(entry.path) > self.MAX_DEPTH:
            logger.warning(f"Entry depth {len(entry.path)} exceeds max {self.MAX_DEPTH}")
            return
        
        existing = self._index.get(entry.uid)
        
        if existing:
            self._update_existing_entry(existing, entry)
        else:
            self._add_new_entry(entry)
        
        if self._bulk_mode:
            self._pending_changes.add(entry.uid)
        else:
            self._notify_change(entry.uid, entry)
    
    def remove(self, uid: str) -> Optional[IndexEntry]:
        """Remove an entry and clean up dependencies - O(d) where d is dependent count."""
        entry = self._index.pop(uid, None)
        if not entry:
            return None
        
        self._dependency_graph.remove_node(uid)
        
        for dep_uid in entry.dependencies:
            dep_entry = self._index.get(dep_uid)
            if dep_entry:
                dep_entry.dependents.discard(uid)
        
        for dependent_uid in entry.dependents:
            dependent_entry = self._index.get(dependent_uid)
            if dependent_entry:
                dependent_entry.dependencies.discard(uid)
        
        if self._bulk_mode:
            self._pending_changes.add(uid)
        else:
            self._notify_change(uid, None)
        
        return entry
    
    def update(self, uid: str, updates: Dict[str, Any]) -> Optional[IndexEntry]:
        """
        Update specific fields of an entry - O(1).
        
        Args:
            uid: Entry UID
            updates: Fields to update
            
        Returns:
            Updated entry or None if not found
        """
        entry = self._index.get(uid)
        if not entry:
            return None
        
        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        
        if self._bulk_mode:
            self._pending_changes.add(uid)
        else:
            self._notify_change(uid, entry)
        
        return entry
    
    def get_affected_uids(self, uid: str) -> Set[str]:
        """
        Get all UIDs affected by a change to the given UID.
        
        Returns the UID itself plus all its transitive dependents.
        """
        result = {uid}
        result.update(self._dependency_graph.get_all_dependents(uid))
        return result
    
    def find_by_parent(self, parent_uid: str) -> List[IndexEntry]:
        """Find all entries with a given parent - O(n) scan."""
        return [
            entry for entry in self._index.values()
            if entry.parent_uid == parent_uid
        ]
    
    def find_by_depth(self, min_depth: int, max_depth: int) -> List[IndexEntry]:
        """Find entries within a depth range - O(n) scan."""
        return [
            entry for entry in self._index.values()
            if min_depth <= entry.depth <= max_depth
        ]
    
    def find_by_type(self, node_type: str) -> List[IndexEntry]:
        """Find entries by node type - O(n) scan."""
        return [
            entry for entry in self._index.values()
            if entry.node_type == node_type
        ]
    
    def add_dependency(self, uid: str, depends_on_uid: str) -> bool:
        """
        Add a dependency relationship - O(1).
        
        Returns False if it would create a circular dependency.
        """
        if uid not in self._index or depends_on_uid not in self._index:
            return False
        
        self._dependency_graph.add_edge(uid, depends_on_uid)
        
        cycle = self._dependency_graph.detect_cycle(uid)
        if cycle:
            self._dependency_graph.remove_edge(uid, depends_on_uid)
            logger.warning(f"Detected circular dependency: {' -> '.join(cycle)}")
            return False
        
        self._index[uid].dependencies.add(depends_on_uid)
        self._index[depends_on_uid].dependents.add(uid)
        
        return True
    
    def remove_dependency(self, uid: str, depends_on_uid: str) -> None:
        """Remove a dependency relationship - O(1)."""
        self._dependency_graph.remove_edge(uid, depends_on_uid)
        
        if uid in self._index:
            self._index[uid].dependencies.discard(depends_on_uid)
        if depends_on_uid in self._index:
            self._index[depends_on_uid].dependents.discard(uid)
    
    def begin_bulk(self) -> None:
        """Begin bulk operation mode - defer change notifications."""
        self._bulk_mode = True
        self._pending_changes.clear()
    
    def end_bulk(self) -> Set[str]:
        """End bulk mode and return all changed UIDs."""
        self._bulk_mode = False
        changed = self._pending_changes.copy()
        self._pending_changes.clear()
        
        for uid in changed:
            entry = self._index.get(uid)
            if entry:
                self._notify_change(uid, entry)
        
        return changed
    
    def on_change(self, callback: Callable[[str, Optional[IndexEntry]], None]) -> None:
        """Register a change callback."""
        self._change_callbacks.append(callback)
    
    def clear(self) -> None:
        """Clear all entries."""
        self._index.clear()
        self._dependency_graph = DependencyGraph()
        self._pending_changes.clear()
    
    def get_stats(self) -> IndexStats:
        """Get index statistics."""
        stats = IndexStats()
        stats.total_entries = len(self._index)
        
        orphan_uids = set()
        for entry in self._index.values():
            stats.by_type[entry.node_type] = stats.by_type.get(entry.node_type, 0) + 1
            stats.max_depth = max(stats.max_depth, entry.depth)
            
            if entry.parent_uid and entry.parent_uid not in self._index:
                orphan_uids.add(entry.uid)
        
        stats.orphan_count = len(orphan_uids)
        
        checked = set()
        for uid in self._index:
            if uid not in checked:
                cycle = self._dependency_graph.detect_cycle(uid)
                if cycle:
                    stats.circular_count += 1
                    checked.update(cycle)
        
        return stats
    
    def validate(self) -> List[str]:
        """Validate index integrity and return any issues."""
        issues = []
        
        for entry in self._index.values():
            if len(entry.path) > self.MAX_DEPTH:
                issues.append(f"Entry {entry.uid} exceeds max depth")
            
            for dep_uid in entry.dependencies:
                if dep_uid not in self._index:
                    issues.append(f"Entry {entry.uid} depends on non-existent {dep_uid}")
            
            if entry.parent_uid and entry.parent_uid not in self._index:
                issues.append(f"Entry {entry.uid} has non-existent parent {entry.parent_uid}")
        
        for uid in self._index:
            cycle = self._dependency_graph.detect_cycle(uid)
            if cycle:
                issues.append(f"Circular dependency detected: {' -> '.join(cycle)}")
        
        return issues
    
    def _add_new_entry(self, entry: IndexEntry) -> None:
        """Add a new entry to the index."""
        self._index[entry.uid] = entry
        
        if entry.parent_uid:
            self.add_dependency(entry.uid, entry.parent_uid)
    
    def _update_existing_entry(self, existing: IndexEntry, new: IndexEntry) -> None:
        """Update an existing entry."""
        if existing.parent_uid != new.parent_uid:
            if existing.parent_uid:
                self.remove_dependency(existing.uid, existing.parent_uid)
            if new.parent_uid:
                self.add_dependency(existing.uid, new.parent_uid)
        
        existing.node = new.node
        existing.node_type = new.node_type
        existing.parent_uid = new.parent_uid
        existing.depth = new.depth
        existing.path = new.path
        existing.markdown_host_uid = new.markdown_host_uid
        existing.items_host_uid = new.items_host_uid
        existing.item_index = new.item_index
    
    def _notify_change(self, uid: str, entry: Optional[IndexEntry]) -> None:
        """Notify change callbacks."""
        for callback in self._change_callbacks:
            try:
                callback(uid, entry)
            except Exception as e:
                logger.error(f"Change callback error: {e}")
    
    def __len__(self) -> int:
        return len(self._index)
    
    def __contains__(self, uid: str) -> bool:
        return uid in self._index
    
    def __iter__(self):
        return iter(self._index.items())