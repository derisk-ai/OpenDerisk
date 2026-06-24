"""Knowledge module - LLM Wiki based knowledge system.

Three-layer data model (RFC 001):
- L0 Verbatim: immutable raw sources (files, conversations, clips)
- L1 Document: LLM-maintained markdown wiki pages
- L2 Graph: materialized entity-relationship edges with temporal validity

See docs/knowledge/rfc-001-three-layer-data-model.md for the full spec.
"""

from derisk.knowledge.types import (
    SpaceId,
    VerbatId,
    DocId,
    EdgeId,
    Space,
    Verbat,
    Document,
    Edge,
    Subgraph,
    VerbatHit,
    DocHit,
    VectorHit,
    FtsHit,
    ChangeEvent,
    WriteLock,
    ReindexReport,
    EmbedderIdentity,
    LintIssue,
    ExtractMode,
    Visibility,
)
from derisk.knowledge.schema import (
    PageType,
    RelationType,
    LintRules,
    Schema,
    default_schema_md,
    parse_schema,
    validate_schema,
    route_path,
    validate_predicate,
    inverse_predicate,
)

__all__ = [
    "SpaceId",
    "VerbatId",
    "DocId",
    "EdgeId",
    "Space",
    "Verbat",
    "Document",
    "Edge",
    "Subgraph",
    "VerbatHit",
    "DocHit",
    "VectorHit",
    "FtsHit",
    "ChangeEvent",
    "WriteLock",
    "ReindexReport",
    "EmbedderIdentity",
    "LintIssue",
    "ExtractMode",
    "Visibility",
    "PageType",
    "RelationType",
    "LintRules",
    "Schema",
    "default_schema_md",
    "parse_schema",
    "validate_schema",
    "route_path",
    "validate_predicate",
    "inverse_predicate",
]
