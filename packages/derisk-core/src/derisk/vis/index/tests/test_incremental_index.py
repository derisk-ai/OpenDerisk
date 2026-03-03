"""
Tests for VIS Protocol V2 - Incremental Index Manager
"""

import pytest
from derisk.vis.index import IncrementalIndexManager, IndexEntry


class TestIncrementalIndexManager:
    """Tests for IncrementalIndexManager."""

    def test_add_single_entry(self):
        """Test adding a single entry."""
        manager = IncrementalIndexManager()
        
        entry = IndexEntry(
            uid="test-1",
            node={"data": "test"},
            node_type="ast",
            parent_uid=None,
            depth=0,
            path=["test-1"],
        )
        
        manager.add(entry)
        
        assert manager.has("test-1")
        assert manager.get("test-1").uid == "test-1"

    def test_add_multiple_entries(self):
        """Test adding multiple entries."""
        manager = IncrementalIndexManager()
        
        for i in range(10):
            entry = IndexEntry(
                uid=f"test-{i}",
                node={"data": f"test-{i}"},
                node_type="ast",
                parent_uid=None,
                depth=0,
                path=[f"test-{i}"],
            )
            manager.add(entry)
        
        assert manager.size == 10

    def test_remove_entry(self):
        """Test removing an entry."""
        manager = IncrementalIndexManager()
        
        entry = IndexEntry(
            uid="test-1",
            node={"data": "test"},
            node_type="ast",
            parent_uid=None,
            depth=0,
            path=["test-1"],
        )
        
        manager.add(entry)
        assert manager.has("test-1")
        
        removed = manager.remove("test-1")
        assert removed is not None
        assert removed.uid == "test-1"
        assert not manager.has("test-1")

    def test_update_entry(self):
        """Test updating an entry."""
        manager = IncrementalIndexManager()
        
        entry = IndexEntry(
            uid="test-1",
            node={"data": "test"},
            node_type="ast",
            parent_uid=None,
            depth=0,
            path=["test-1"],
        )
        
        manager.add(entry)
        
        manager.update("test-1", {"depth": 1})
        
        updated = manager.get("test-1")
        assert updated.depth == 1

    def test_dependency_tracking(self):
        """Test dependency tracking."""
        manager = IncrementalIndexManager()
        
        parent = IndexEntry(
            uid="parent",
            node={"data": "parent"},
            node_type="ast",
            parent_uid=None,
            depth=0,
            path=["parent"],
        )
        
        child = IndexEntry(
            uid="child",
            node={"data": "child"},
            node_type="ast",
            parent_uid="parent",
            depth=1,
            path=["parent", "child"],
        )
        
        manager.add(parent)
        manager.add(child)
        
        assert manager.add_dependency("child", "parent")
        
        affected = manager.get_affected_uids("parent")
        assert "parent" in affected
        assert "child" in affected

    def test_circular_dependency_detection(self):
        """Test circular dependency detection."""
        manager = IncrementalIndexManager()
        
        a = IndexEntry(uid="a", node={}, node_type="ast", parent_uid=None, depth=0, path=["a"])
        b = IndexEntry(uid="b", node={}, node_type="ast", parent_uid=None, depth=0, path=["b"])
        c = IndexEntry(uid="c", node={}, node_type="ast", parent_uid=None, depth=0, path=["c"])
        
        manager.add(a)
        manager.add(b)
        manager.add(c)
        
        assert manager.add_dependency("b", "a")
        assert manager.add_dependency("c", "b")
        
        # This should fail - would create cycle a -> c -> b -> a
        assert not manager.add_dependency("a", "c")

    def test_bulk_operations(self):
        """Test bulk operation mode."""
        manager = IncrementalIndexManager()
        
        changes = []
        manager.on_change(lambda uid, entry: changes.append(uid))
        
        manager.begin_bulk()
        
        for i in range(5):
            entry = IndexEntry(
                uid=f"test-{i}",
                node={},
                node_type="ast",
                parent_uid=None,
                depth=0,
                path=[f"test-{i}"],
            )
            manager.add(entry)
        
        # Changes should not be notified during bulk mode
        assert len(changes) == 0
        
        manager.end_bulk()
        
        # All changes should be notified after bulk mode ends
        assert len(changes) == 5

    def test_find_by_parent(self):
        """Test finding entries by parent."""
        manager = IncrementalIndexManager()
        
        parent = IndexEntry(
            uid="parent",
            node={},
            node_type="ast",
            parent_uid=None,
            depth=0,
            path=["parent"],
        )
        
        manager.add(parent)
        
        for i in range(3):
            child = IndexEntry(
                uid=f"child-{i}",
                node={},
                node_type="ast",
                parent_uid="parent",
                depth=1,
                path=["parent", f"child-{i}"],
            )
            manager.add(child)
        
        children = manager.find_by_parent("parent")
        assert len(children) == 3

    def test_find_by_type(self):
        """Test finding entries by type."""
        manager = IncrementalIndexManager()
        
        for i in range(5):
            entry = IndexEntry(
                uid=f"ast-{i}",
                node={},
                node_type="ast",
                parent_uid=None,
                depth=0,
                path=[f"ast-{i}"],
            )
            manager.add(entry)
        
        for i in range(3):
            entry = IndexEntry(
                uid=f"item-{i}",
                node={},
                node_type="item",
                parent_uid=None,
                depth=0,
                path=[f"item-{i}"],
            )
            manager.add(entry)
        
        ast_entries = manager.find_by_type("ast")
        assert len(ast_entries) == 5
        
        item_entries = manager.find_by_type("item")
        assert len(item_entries) == 3

    def test_get_stats(self):
        """Test getting statistics."""
        manager = IncrementalIndexManager()
        
        for i in range(10):
            entry = IndexEntry(
                uid=f"test-{i}",
                node={},
                node_type="ast",
                parent_uid=None,
                depth=i % 3,
                path=[f"test-{i}"],
            )
            manager.add(entry)
        
        stats = manager.get_stats()
        
        assert stats.total_entries == 10
        assert stats.max_depth == 2
        assert stats.by_type.get("ast") == 10

    def test_validate(self):
        """Test validation."""
        manager = IncrementalIndexManager()
        
        # Add entries with valid structure
        parent = IndexEntry(
            uid="parent",
            node={},
            node_type="ast",
            parent_uid=None,
            depth=0,
            path=["parent"],
        )
        
        child = IndexEntry(
            uid="child",
            node={},
            node_type="ast",
            parent_uid="parent",
            depth=1,
            path=["parent", "child"],
        )
        
        manager.add(parent)
        manager.add(child)
        
        issues = manager.validate()
        assert len(issues) == 0

    def test_validate_orphan(self):
        """Test validation detects orphan entries."""
        manager = IncrementalIndexManager()
        
        # Add entry with non-existent parent
        orphan = IndexEntry(
            uid="orphan",
            node={},
            node_type="ast",
            parent_uid="non-existent",
            depth=1,
            path=["non-existent", "orphan"],
        )
        
        manager.add(orphan)
        
        issues = manager.validate()
        assert len(issues) > 0
        assert any("non-existent" in issue for issue in issues)

    def test_clear(self):
        """Test clearing all entries."""
        manager = IncrementalIndexManager()
        
        for i in range(5):
            entry = IndexEntry(
                uid=f"test-{i}",
                node={},
                node_type="ast",
                parent_uid=None,
                depth=0,
                path=[f"test-{i}"],
            )
            manager.add(entry)
        
        assert manager.size == 5
        
        manager.clear()
        
        assert manager.size == 0


class TestIndexEntry:
    """Tests for IndexEntry."""

    def test_to_dict(self):
        """Test converting entry to dictionary."""
        entry = IndexEntry(
            uid="test-1",
            node={"data": "test"},
            node_type="ast",
            parent_uid="parent",
            depth=1,
            path=["parent", "test-1"],
        )
        
        d = entry.to_dict()
        
        assert d["uid"] == "test-1"
        assert d["node_type"] == "ast"
        assert d["parent_uid"] == "parent"
        assert d["depth"] == 1
        assert d["path"] == ["parent", "test-1"]