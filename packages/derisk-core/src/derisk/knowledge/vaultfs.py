"""VaultFS unified storage abstraction (RFC 002).

The Protocol every storage backend must implement. LocalVaultFS and
DistributedVaultFS share this contract; conformance tests in
derisk_ext.knowledge.vaultfs.conformance enforce functional equivalence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional, Protocol, runtime_checkable

from derisk.knowledge.types import (
    ChangeEvent,
    DocHit,
    DocId,
    Document,
    DocumentMeta,
    Edge,
    EdgeId,
    EmbedderIdentity,
    FtsHit,
    LintIssue,
    ReindexReport,
    SpaceId,
    Subgraph,
    Verbat,
    VerbatHit,
    VerbatId,
    VectorHit,
    WriteLock,
)


@runtime_checkable
class VaultFS(Protocol):
    """Unified storage interface covering L0/L1/L2 + cross-cutting concerns.

    Each Space owns one VaultFS instance. Cross-Space sharing is forbidden
    (avoids the module-level global state anti-pattern seen in llmwiki's
    `_db` / `_workspace_root`).
    """

    # ----- metadata -----
    @property
    def space_id(self) -> SpaceId: ...

    @property
    def backend_type(self) -> str: ...   # "local" | "distributed"

    # ===== Schema (config layer) =====
    async def read_schema_md(self) -> str:
        """Return the raw content of schema.md for this space."""
        ...

    async def write_schema_md(self, content: str) -> None:
        """Update schema.md. Caller is responsible for triggering L2 rebuild
        if Relation Types changed."""
        ...

    async def read_purpose_md(self) -> str: ...

    # ===== L0 Verbatim =====
    async def verbat_add(self, v: Verbat) -> VerbatId:
        """Add a verbatim. Dedupes by content_hash within the space.

        If a verbatim with the same content_hash already exists (and is not
        deprecated), returns the existing id without writing a new row.
        """
        ...

    async def verbat_get(self, vid: VerbatId) -> Optional[Verbat]: ...

    async def verbat_list(
        self,
        extract_mode: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Verbat]: ...

    async def verbat_search(
        self,
        query: str,
        limit: int = 10,
        extract_mode: Optional[str] = None,
    ) -> list[VerbatHit]: ...

    async def verbat_deprecate(self, vid: VerbatId) -> None:
        """Soft-delete: mark deprecated=True, keep content."""
        ...

    # ===== L1 Document =====
    async def doc_create(
        self,
        path: str,
        content: str,
        frontmatter: Optional[dict] = None,
    ) -> DocId: ...

    async def doc_edit(self, path: str, content: str) -> None:
        """Edit a document. Re-parses frontmatter, rebuilds L2 edges for it."""
        ...

    async def doc_read(self, path: str) -> Optional[Document]: ...

    async def doc_delete(self, path: str) -> None:
        """Delete a document. Refuses to delete protected files
        (log.md, overview.md, index.md, schema.md, purpose.md)."""
        ...

    async def doc_list(
        self,
        type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocumentMeta]: ...

    async def doc_search(
        self,
        query: str,
        mode: str = "documents",   # "documents" | "references"
        limit: int = 10,
    ) -> list[DocHit]: ...

    async def doc_lint(self, path: Optional[str] = None) -> list[LintIssue]: ...

    async def doc_append_log(self, entry: str) -> None:
        """Append a line to wiki/log.md (spec llm-wiki.md:49)."""
        ...

    # ===== L2 Graph =====
    async def edge_add(self, e: Edge) -> EdgeId: ...

    async def edge_invalidate(
        self, eid: EdgeId, valid_to: Optional[datetime] = None
    ) -> None:
        """Set valid_to=now (or given) on an edge. Keeps history."""
        ...

    async def graph_query(
        self,
        entity: Optional[str] = None,
        predicate: Optional[str] = None,
        hop: int = 1,
        include_invalid: bool = False,
    ) -> Subgraph: ...

    async def graph_traverse(
        self, start: str, hop: int = 2, mode: str = "bfs"
    ) -> Subgraph: ...

    async def graph_timeline(self, entity: str) -> list[Edge]: ...

    async def graph_backlinks(self, entity: str) -> list[Edge]:
        """Edges pointing TO this entity (reverse lookup)."""
        ...

    # ===== Cross-cutting: vector =====
    async def vector_upsert(
        self, id: str, embedding: list[float], meta: dict
    ) -> None: ...

    async def vector_query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filter: Optional[dict] = None,
    ) -> list[VectorHit]: ...

    async def vector_delete(self, id: str) -> None: ...

    # ===== Cross-cutting: full-text =====
    async def fts_search(
        self, query: str, limit: int = 10, filter: Optional[dict] = None
    ) -> list[FtsHit]: ...

    # ===== Cross-cutting: writer lock =====
    async def acquire_write_lock(self, timeout: int = 30) -> WriteLock: ...

    # ===== Cross-cutting: events =====
    async def publish_event(self, event: ChangeEvent) -> None: ...

    async def subscribe_events(
        self, callback: Callable[[ChangeEvent], None]
    ) -> "Subscription": ...

    # ===== Cross-cutting: filesystem watcher =====
    async def watch_changes(
        self, callback: Callable[[ChangeEvent], None]
    ) -> "Watcher": ...

    # ===== Rebuild =====
    async def reindex(self, layer: str = "all") -> ReindexReport:
        """Rebuild derived layers. layer ∈ {"chunks", "L2", "all"}.
        L0 is never rebuilt."""
        ...

    # ===== Embedder identity =====
    async def get_embedder_identity(self) -> Optional[EmbedderIdentity]: ...

    async def set_embedder_identity(
        self, model_name: str, dimension: int, force_swap: bool = False
    ) -> None:
        """Lock or swap the embedder. force_swap=True triggers vector rebuild."""
        ...


class Subscription(Protocol):
    """Handle returned by subscribe_events()."""

    def cancel(self) -> None: ...


class Watcher(Protocol):
    """Handle returned by watch_changes()."""

    def stop(self) -> None: ...
