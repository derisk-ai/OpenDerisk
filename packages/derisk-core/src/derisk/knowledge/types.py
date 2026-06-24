"""Core types for the three-layer knowledge model (RFC 001).

All types are framework-agnostic dataclasses / Pydantic models so they can be
shared between LocalVaultFS and DistributedVaultFS without coupling to either
storage backend.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

# Strongly-typed id aliases (kept as str for storage simplicity, but typed
# at the API boundary to prevent accidental cross-use).
SpaceId = str
VerbatId = str
DocId = str
EdgeId = str


class ExtractMode(str, Enum):
    """How a verbatim entered the space (RFC 001 §3.3)."""

    MINE = "mine"           # project files / code mined actively
    CLIP = "clip"           # browser clip
    UPLOAD = "upload"       # user upload
    CONVO = "convo"         # agent conversation fragment (replaces mempalace drawer)
    LEGACY_CHUNK = "legacy_chunk"  # one-time migration from old RAG


class Visibility(str, Enum):
    """Space visibility (RFC 001 §7.3)."""

    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


class EmbedderState(str, Enum):
    """Embedder identity state machine (RFC 001 §7.1, learns from mempalace).

    - unknown:        never embedded yet, identity not locked
    - known_match:    identity locked, current embedder matches
    - known_mismatch: identity locked, current embedder differs (must force_swap)
    """

    UNKNOWN = "unknown"
    KNOWN_MATCH = "known_match"
    KNOWN_MISMATCH = "known_mismatch"


# ---------------------------------------------------------------------------
# L0 Verbatim
# ---------------------------------------------------------------------------


def _ulid(prefix: str) -> str:
    """Generate a time-sortable id with a prefix.

    Uses ULID-like format (timestamp + random) for sortability without an
    external dependency. 26 chars total: 10 ms-precision timestamp + 16 random.
    """
    import os
    import time

    ts_ms = int(time.time() * 1000)
    rand = os.urandom(8).hex()
    return f"{prefix}_{ts_ms:010x}{rand}"


def new_verbat_id() -> VerbatId:
    return _ulid("v")


def new_doc_id() -> DocId:
    return _ulid("d")


def new_edge_id() -> EdgeId:
    return _ulid("e")


def new_space_id() -> SpaceId:
    return _ulid("s")


def sha256_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class Space:
    """A knowledge space - top-level container (RFC 001 §7).

    One Space = one VaultFS instance. Spaces are isolated from each other.
    """

    id: SpaceId
    slug: str                        # URL-friendly, globally unique
    name: str
    description: str = ""
    backend: str = "local"           # "local" | "distributed"
    schema_hash: Optional[str] = None
    embedder_model: Optional[str] = None
    embedder_dimension: Optional[int] = None
    embedder_state: EmbedderState = EmbedderState.UNKNOWN
    visibility: Visibility = Visibility.PRIVATE
    owner_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # v2 ingest pipeline config (RFC 004 §6). All optional — fall back to
    # system defaults at the serve layer.
    default_agent_id: Optional[str] = None
    llm_model: Optional[str] = None
    multimodal_model: Optional[str] = None


@dataclass
class Verbat:
    """L0 verbatim - immutable raw source (RFC 001 §3).

    Once written, `content` must never change. Duplicate content within the
    same space is deduped by `content_hash`.
    """

    id: VerbatId
    space_id: SpaceId
    source_file: str             # basename only, never absolute path
    source_path: Optional[str]   # full path, internal use only
    content: str                 # verbatim text, never summarized
    content_hash: str            # SHA256
    extract_mode: ExtractMode
    content_date: Optional[datetime] = None
    filed_at: Optional[datetime] = None
    source_mtime: Optional[int] = None
    normalize_version: int = 1
    deprecated: bool = False

    @classmethod
    def create(
        cls,
        space_id: SpaceId,
        content: str,
        source_file: str,
        extract_mode: ExtractMode,
        source_path: Optional[str] = None,
        content_date: Optional[datetime] = None,
        source_mtime: Optional[int] = None,
    ) -> "Verbat":
        import os

        return cls(
            id=new_verbat_id(),
            space_id=space_id,
            source_file=os.path.basename(source_file) if source_file else source_file,
            source_path=source_path,
            content=content,
            content_hash=sha256_hash(content),
            extract_mode=extract_mode,
            content_date=content_date,
            filed_at=datetime.utcnow(),
            source_mtime=source_mtime,
        )


# ---------------------------------------------------------------------------
# L1 Document
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """L1 document - LLM-maintained markdown page (RFC 001 §4).

    Stored both as a file on disk (FS-as-truth) and as a row in `documents`
    table (derived index). `path` is relative to the space's `wiki/` dir.
    """

    id: DocId
    space_id: SpaceId
    path: str                    # relative to wiki/, e.g. "concepts/attention.md"
    type: str                    # schema.md Page Type
    title: str
    frontmatter: dict            # parsed YAML
    content: str                 # markdown body (without frontmatter fence)
    raw_content: str             # full markdown including frontmatter
    content_hash: str
    version: int = 1
    status: str = "active"       # active | deprecated
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DocumentMeta:
    """Lightweight document metadata for list views (no content)."""

    id: DocId
    path: str
    type: str
    title: str
    status: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# ---------------------------------------------------------------------------
# L2 Graph
# ---------------------------------------------------------------------------


@dataclass
class Edge:
    """L2 graph edge with temporal validity (RFC 001 §5)."""

    id: EdgeId
    space_id: SpaceId
    subject: str                 # entity string
    predicate: str               # schema.md Relation Type
    object: str                  # entity string
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None   # None = currently valid
    source_document_id: Optional[DocId] = None
    source_verbat_id: Optional[VerbatId] = None
    weight: float = 1.0
    created_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        now = datetime.utcnow()
        if self.valid_from and self.valid_from > now:
            return False
        if self.valid_to and self.valid_to <= now:
            return False
        return True


@dataclass
class Subgraph:
    """Result of a graph query - nodes + edges."""

    nodes: list[str] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    root: Optional[str] = None   # starting entity for traverse


# ---------------------------------------------------------------------------
# Search hits
# ---------------------------------------------------------------------------


@dataclass
class VerbatHit:
    verbat_id: VerbatId
    score: float
    snippet: str
    source_file: str
    extract_mode: ExtractMode


@dataclass
class DocHit:
    document_id: DocId
    path: str
    title: str
    type: str
    score: float
    snippet: str
    verbats: list[VerbatId] = field(default_factory=list)  # L0 back-pointers


@dataclass
class VectorHit:
    id: str                      # chunk_id or verbat_id
    score: float
    metadata: dict
    document_id: Optional[DocId] = None
    verbat_id: Optional[VerbatId] = None


@dataclass
class FtsHit:
    chunk_id: str
    document_id: DocId
    path: str
    title: str
    score: float
    snippet: str


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


@dataclass
class ChangeEvent:
    """Published when L0/L1/L2 changes (RFC 002 §3 events)."""

    space_id: SpaceId
    layer: Literal["L0", "L1", "L2"]
    op: Literal["create", "update", "delete", "invalidate"]
    id: str                      # verbat_id / doc_id / edge_id
    path: Optional[str] = None   # for L1
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WriteLock:
    """Space-level writer lock handle (RFC 002 §8)."""

    space_id: SpaceId
    acquired_at: datetime
    backend: str                 # "flock" | "pg_advisory"
    handle: Any                  # backend-specific

    async def release(self) -> None:
        """Release the lock. Implemented by backend."""
        raise NotImplementedError


@dataclass
class ReindexReport:
    """Result of a reindex operation (RFC 002 §3 reindex)."""

    layer: str                   # "chunks" | "L2" | "vectors" | "all"
    verbats_processed: int = 0
    documents_processed: int = 0
    chunks_built: int = 0
    edges_built: int = 0
    vectors_rebuilt: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class EmbedderIdentity:
    """Persisted embedder identity for a space (RFC 002 §3)."""

    space_id: SpaceId
    model_name: str
    dimension: int               # 0 means unknown (mempalace convention)
    state: EmbedderState
    updated_at: datetime


@dataclass
class LintIssue:
    """One lint finding (RFC 003 §7)."""

    rule: str                    # orphan_pages | stale_edges | ...
    severity: Literal["info", "warning", "error"]
    path: Optional[str] = None
    edge_id: Optional[EdgeId] = None
    message: str = ""
