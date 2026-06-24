"""DistributedVaultFS — S3 + SQL (Postgres/MySQL) + pluggable vector store.

Composition (RFC 002 §4 distributed variant):
- L0 verbatim content: S3 (via FileStorageClient)
- L1 document markdown: S3 (via FileStorageClient)
- L0/L1/L2 metadata + chunks + edges: SQL (Postgres or MySQL via SQLAlchemy)
- Vectors: pluggable via `vector_store_config` — pgvector / milvus /
  chroma / lance
- Writer lock: SQL advisory lock (pg_advisory_lock / GET_LOCK)
- Events: in-process asyncio.Queue fan-out (LISTEN/NOTIFY deferred)
- Filesystem watcher: not supported (deferred per user decision)

Relational DSN is auto-derived from `[service.web.database]` by the
service layer; vector store config is a dict shaped like
`{type: "pgvector" | "milvus" | "chroma" | "lance", ...per-store-params}`.

High-level L0/L1/L2 orchestration (path normalization, schema
validation, event publishing, lock flow) is inherited from BaseVaultFS.
This class only wires the storage collaborators and implements the
abstract storage methods by delegating to them.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Optional

from derisk.knowledge.frontmatter import extract_footnotes, extract_wikilinks
from derisk.knowledge.schema import default_schema_md
from derisk.knowledge.types import (
    ChangeEvent,
    DocHit,
    DocId,
    Document,
    DocumentMeta,
    Edge,
    EdgeId,
    EmbedderIdentity,
    EmbedderState,
    ExtractMode,
    FtsHit,
    ReindexReport,
    SpaceId,
    Verbat,
    VerbatId,
    new_edge_id,
)
from derisk.knowledge.vaultfs import Subscription, Watcher

from ._util import (
    INLINE_THRESHOLD,
    PROTECTED_FILES,
    chunk_text,
    make_snippet,
    normalize_wiki_path,
    parse_dt,
)
from .base import BaseVaultFS
from .files.s3_store import S3FileStore
from .lock.sql_lock import SQLAdvisoryLock
from .relational.sqlalchemy_store import SQLAlchemyRelationalStore
from .pg_vector_store import PgVectorStore
from .vector_chroma import ChromaVectorStore
from .vector_lance_s3 import LanceS3VectorStore
from .vector_milvus import MilvusVectorStore

logger = logging.getLogger(__name__)


# Vector store types supported by DistributedVaultFS. Each has its own
# adapter module loaded lazily in `_make_vector_store`.
SUPPORTED_VECTOR_STORE_TYPES = ("pgvector", "milvus", "chroma", "lance")


class DistributedVaultFS(BaseVaultFS):
    """Distributed VaultFS backed by S3 + SQL + pluggable vector store.

    Instantiate one per Space. Do not share across spaces — every
    instance carries its own `space_id` partition key.
    """

    def __init__(
        self,
        space_id: SpaceId,
        relational_dsn: str,
        vector_store_config: dict,
        s3_bucket: str = "",
        s3_storage_type: Optional[str] = None,
        system_app: Optional[object] = None,
    ):
        super().__init__(space_id)

        self._relational = SQLAlchemyRelationalStore(relational_dsn)
        self._files = S3FileStore(
            bucket=s3_bucket,
            space_id=space_id,
            storage_type=s3_storage_type,
            system_app=system_app,
        )
        self._lock = SQLAdvisoryLock(self._relational)

        vtype = vector_store_config.get("type", "pgvector")
        if vtype not in SUPPORTED_VECTOR_STORE_TYPES:
            raise ValueError(
                f"Unknown vector_store_type: {vtype!r}. "
                f"Supported: {SUPPORTED_VECTOR_STORE_TYPES}"
            )
        self._vector_store_config = dict(vector_store_config)
        self._vector_store_config["type"] = vtype
        self._vector_table_name = f"ks_vectors_{_safe_table_suffix(str(space_id))}"
        self._system_app = system_app

    # ----- metadata -----
    @property
    def backend_type(self) -> str:
        return "distributed"

    @property
    def root(self) -> str:
        return f"s3://{self._files.bucket}/{self._space_id}"

    # ----- lifecycle -----
    async def initialize(self) -> None:
        await super().initialize()
        await self._relational.init()

        # Seed schema.md + protected wiki files if missing
        schema_md = default_schema_md(str(self._space_id))
        protected = {
            "index.md": "# Index\n\n",
            "log.md": "# Operation Log\n\n",
            "overview.md": "# Overview\n\n",
        }
        await self._files.seed_protected_files_if_missing(schema_md, protected)

    async def close(self) -> None:
        # Close vector store if we instantiated one
        if self._vector_store is not None:
            try:
                await self._vector_store.close()
            except Exception:
                pass
        await self._relational.close()
        await super().close()

    # ===================================================================
    # Schema (config layer)
    # ===================================================================
    async def read_schema_md(self) -> str:
        return await self._files.read_schema()

    async def write_schema_md(self, content: str) -> None:
        await self._files.write_schema(content)
        await self.publish_event(
            ChangeEvent(
                space_id=self._space_id,
                layer="L1",
                op="update",
                id="schema.md",
                path="schema.md",
            )
        )

    async def read_purpose_md(self) -> str:
        return await self._files.read_purpose()

    # ===================================================================
    # L0 Verbatim — delegate to relational + files
    # ===================================================================
    async def _verbat_exists_by_hash(self, content_hash: str) -> Optional[VerbatId]:
        return await self._relational.verbat_exists_by_hash(self._space_id, content_hash)

    async def _verbat_insert(
        self, v: Verbat, inline_content: Optional[str], content_ref: Optional[str]
    ) -> None:
        # If content is large, store in S3 and persist the verbat_id as content_ref.
        # `content_ref` from base class is "raw/{mode}/{id}.txt" (path-style);
        # for distributed we override to the S3-resolvable verbat_id + extract_mode.
        actual_ref = content_ref
        actual_inline = inline_content
        if inline_content is None and content_ref is not None:
            # Large verbat — store in S3
            await self._files.write_raw(v.extract_mode.value, v.id, v.content)
            actual_ref = f"s3://{self._files.bucket}/{v.extract_mode.value}/{v.id}"
        await self._relational.verbat_insert(v, actual_inline, actual_ref)

    async def _verbat_fetch(self, vid: VerbatId) -> Optional[Verbat]:
        row = await self._relational.verbat_fetch(self._space_id, vid)
        if not row:
            return None
        return await self._row_to_verbat(row)

    async def _verbat_list_rows(
        self, extract_mode: Optional[str], limit: int, offset: int
    ) -> list[Verbat]:
        rows = await self._relational.verbat_list_rows(
            self._space_id, extract_mode, limit, offset
        )
        return [await self._row_to_verbat(r) for r in rows]

    async def _verbat_search_rows(
        self, query: str, limit: int, extract_mode: Optional[str]
    ) -> list[Verbat]:
        rows = await self._relational.verbat_search_rows(
            self._space_id, query, limit, extract_mode
        )
        return [await self._row_to_verbat(r) for r in rows]

    async def _verbat_deprecate_row(self, vid: VerbatId) -> None:
        await self._relational.verbat_deprecate_row(self._space_id, vid)

    # ===================================================================
    # L1 Document — delegate to relational + files
    # ===================================================================
    async def _doc_insert(
        self,
        doc_id: DocId,
        norm_path: str,
        page_type: str,
        title: str,
        raw_frontmatter: str,
        content_hash: str,
        now: datetime,
    ) -> None:
        await self._relational.doc_insert(
            self._space_id,
            doc_id,
            norm_path,
            page_type,
            title,
            raw_frontmatter,
            content_hash,
            now,
        )

    async def _doc_fetch_meta_by_path(self, norm_path: str) -> Optional[tuple[DocId, int]]:
        return await self._relational.doc_fetch_meta_by_path(self._space_id, norm_path)

    async def _doc_fetch_row(self, doc_id: DocId) -> Optional[dict]:
        return await self._relational.doc_fetch_row(self._space_id, doc_id)

    async def _doc_update_version(
        self,
        doc_id: DocId,
        page_type: str,
        title: str,
        raw_frontmatter: str,
        content_hash: str,
        now: datetime,
    ) -> None:
        await self._relational.doc_update_version(
            self._space_id,
            doc_id,
            page_type,
            title,
            raw_frontmatter,
            content_hash,
            now,
        )

    async def _doc_delete_row(self, doc_id: DocId) -> None:
        await self._relational.doc_delete_row(self._space_id, doc_id)

    async def _doc_list_rows(
        self, type: Optional[str], limit: int, offset: int
    ) -> list[DocumentMeta]:
        return await self._relational.doc_list_rows(self._space_id, type, limit, offset)

    async def _doc_invalidate_edges(self, doc_id: DocId, now_iso: str) -> None:
        await self._relational.doc_invalidate_edges(self._space_id, doc_id, now_iso)

    async def _chunks_replace_for_doc(self, doc_id: DocId, body: str) -> None:
        chunks = chunk_text(body, max_chars=2000)
        await self._relational.chunks_replace_for_doc(
            self._space_id, doc_id, body, chunks
        )

    async def _doc_list_chunk_hashes(self, doc_id: DocId) -> list[str]:
        return await self._relational.doc_list_chunk_hashes(self._space_id, doc_id)

    async def _fts_search_chunks(self, query: str, limit: int) -> list[FtsHit]:
        return await self._relational.fts_search_chunks(self._space_id, query, limit)

    async def _lookup_doc_verbats(self, doc_id: DocId) -> list[VerbatId]:
        return await self._relational.lookup_doc_verbats(self._space_id, doc_id)

    async def _doc_search_references(self, query: str, limit: int) -> list[DocHit]:
        rows = await self._relational.doc_search_references(
            self._space_id, query, limit
        )
        return [
            DocHit(
                document_id=r["id"],
                path=r["path"],
                title=r["title"],
                type=r["type"],
                score=1.0,
                snippet="",
                verbats=[],
            )
            for r in rows
        ]

    # ===================================================================
    # File I/O — delegate to S3FileStore
    # ===================================================================
    async def _raw_write(self, rel_path: str, content: str) -> None:
        # rel_path is like "raw/{extract_mode}/{verbat_id}.txt"
        parts = rel_path.split("/", 2)
        if len(parts) != 3 or parts[0] != "raw":
            await self._files.write_raw("misc", rel_path, content)
            return
        extract_mode, vid_with_ext = parts[1], parts[2]
        verbat_id = vid_with_ext[:-4] if vid_with_ext.endswith(".txt") else vid_with_ext
        await self._files.write_raw(extract_mode, verbat_id, content)

    async def _raw_read(self, rel_path: str) -> str:
        parts = rel_path.split("/", 2)
        if len(parts) != 3 or parts[0] != "raw":
            return await self._files.read_raw("misc", rel_path)
        extract_mode, vid_with_ext = parts[1], parts[2]
        verbat_id = vid_with_ext[:-4] if vid_with_ext.endswith(".txt") else vid_with_ext
        return await self._files.read_raw(extract_mode, verbat_id)

    async def _raw_delete(self, rel_path: str) -> None:
        parts = rel_path.split("/", 2)
        if len(parts) != 3 or parts[0] != "raw":
            await self._files.delete_raw("misc", rel_path)
            return
        extract_mode, vid_with_ext = parts[1], parts[2]
        verbat_id = vid_with_ext[:-4] if vid_with_ext.endswith(".txt") else vid_with_ext
        await self._files.delete_raw(extract_mode, verbat_id)

    async def _wiki_write(self, norm_path: str, content: str) -> None:
        await self._files.write_wiki(norm_path, content)

    async def _wiki_read(self, norm_path: str) -> str:
        return await self._files.read_wiki(norm_path)

    async def _wiki_delete(self, norm_path: str) -> None:
        await self._files.delete_wiki(norm_path)

    # ===================================================================
    # L2 Graph — delegate to relational
    # ===================================================================
    async def _edge_insert(self, e: Edge) -> None:
        await self._relational.edge_insert(self._space_id, e)

    async def _edge_invalidate_row(self, eid: EdgeId, valid_to_iso: str) -> None:
        await self._relational.edge_invalidate_row(self._space_id, eid, valid_to_iso)

    async def _edges_query(
        self,
        entity: Optional[str],
        predicate: Optional[str],
        include_invalid: bool,
    ) -> list[Edge]:
        rows = await self._relational.edges_query(
            self._space_id, entity, predicate, include_invalid
        )
        return [self._row_to_edge(r) for r in rows]

    async def _edges_for_node(self, node: str) -> list[Edge]:
        rows = await self._relational.edges_for_node(self._space_id, node)
        return [self._row_to_edge(r) for r in rows]

    async def _edges_timeline(self, entity: str) -> list[Edge]:
        rows = await self._relational.edges_timeline(self._space_id, entity)
        return [self._row_to_edge(r) for r in rows]

    async def _edges_backlinks(self, entity: str) -> list[Edge]:
        rows = await self._relational.edges_backlinks(self._space_id, entity)
        return [self._row_to_edge(r) for r in rows]

    async def _rebuild_doc_edges(
        self, doc_id: DocId, frontmatter: dict, body: str
    ) -> None:
        # Same logic as LocalVaultFS — wikilinks/footnotes/sources → edges
        wikilinks = extract_wikilinks(body)
        related = frontmatter.get("related", []) or []
        if isinstance(related, str):
            related = [related]
        wikilinks.extend(related)

        title = frontmatter.get("title", "")
        now = datetime.utcnow()
        for target in wikilinks:
            e = Edge(
                id=new_edge_id(),
                space_id=self._space_id,
                subject=title,
                predicate="links-to",
                object=target,
                valid_from=now,
                source_document_id=doc_id,
                weight=1.0,
                created_at=now,
            )
            await self._relational.edge_insert(self._space_id, e)

        for fn in extract_footnotes(body):
            e = Edge(
                id=new_edge_id(),
                space_id=self._space_id,
                subject=title,
                predicate="cites",
                object=fn["source"],
                valid_from=now,
                source_document_id=doc_id,
                weight=1.0,
                created_at=now,
            )
            await self._relational.edge_insert(self._space_id, e)

        sources = frontmatter.get("sources", []) or []
        if isinstance(sources, str):
            sources = [sources]
        for vid in sources:
            await self._relational.doc_sources_insert(self._space_id, doc_id, vid)
            e = Edge(
                id=new_edge_id(),
                space_id=self._space_id,
                subject=title,
                predicate="derived-from",
                object=vid,
                valid_from=now,
                source_document_id=doc_id,
                source_verbat_id=vid,
                weight=1.0,
                created_at=now,
            )
            await self._relational.edge_insert(self._space_id, e)

    # ===================================================================
    # Cross-cutting: vector store (pluggable — pgvector/milvus/chroma/lance)
    # ===================================================================
    async def _make_vector_store(self):
        identity = await self.get_embedder_identity()
        if identity is None:
            raise RuntimeError(
                "Embedder identity not set — call set_embedder_identity() before vector ops"
            )
        cfg = self._vector_store_config
        vtype = cfg.get("type", "pgvector")
        dim = identity.dimension

        if vtype == "pgvector":
            dsn = cfg.get("dsn") or cfg.get("vector_dsn") or ""
            if not dsn:
                raise ValueError(
                    "pgvector requires 'dsn' (Postgres DSN with pgvector extension)"
                )
            return PgVectorStore(
                dsn=dsn,
                table_name=self._vector_table_name,
                dimension=dim,
            )

        if vtype == "milvus":
            uri = cfg.get("uri") or cfg.get("milvus_uri") or ""
            if not uri:
                raise ValueError("milvus requires 'uri' (e.g. localhost:19530)")
            prefix = cfg.get("collection_prefix", "ks_")
            collection_name = f"{prefix}{_safe_table_suffix(str(self._space_id))}"
            return MilvusVectorStore(
                uri=uri,
                collection_name=collection_name,
                dimension=dim,
            )

        if vtype == "chroma":
            uri = cfg.get("uri") or cfg.get("chroma_uri") or ""
            if not uri:
                raise ValueError("chroma requires 'uri' (e.g. http://localhost:8000)")
            return ChromaVectorStore(
                uri=uri,
                collection_name=self._vector_table_name,
                dimension=dim,
            )

        if vtype == "lance":
            s3_uri = cfg.get("s3_uri") or cfg.get("lance_s3_uri") or ""
            if not s3_uri:
                raise ValueError(
                    "lance requires 's3_uri' (e.g. s3://bucket/knowledge-vectors)"
                )
            return LanceS3VectorStore(
                s3_uri=s3_uri,
                table_name=self._vector_table_name,
            )

        raise ValueError(f"Unknown vector_store_type: {vtype!r}")

    # ===================================================================
    # Cross-cutting: writer lock (SQL advisory)
    # ===================================================================
    async def _acquire_distributed_lock(self, timeout: int) -> Any:
        handle = await self._lock.acquire(self._space_id, timeout)
        if handle is None:
            raise TimeoutError(
                f"Could not acquire SQL advisory lock for space {self._space_id} "
                f"within {timeout}s"
            )
        return handle

    async def _release_distributed_lock(self, handle: Any) -> None:
        await self._lock.release(handle)

    # ===================================================================
    # Cross-cutting: filesystem watcher (not supported in distributed)
    # ===================================================================
    async def watch_changes(
        self, callback: Callable[[ChangeEvent], None]
    ) -> Watcher:
        logger.info(
            "watch_changes is not supported on DistributedVaultFS (deferred); "
            "returning no-op watcher"
        )
        return await super().watch_changes(callback)

    # ===================================================================
    # Rebuild helpers
    # ===================================================================
    async def _chunks_clear_all(self) -> None:
        await self._relational.chunks_clear_all(self._space_id)

    async def _edges_invalidate_all(self, now_iso: str) -> None:
        await self._relational.edges_invalidate_all(self._space_id, now_iso)

    # ===================================================================
    # Embedder identity
    # ===================================================================
    async def _embedder_identity_get(self) -> Optional[EmbedderIdentity]:
        return await self._relational.embedder_identity_get(self._space_id)

    async def _embedder_identity_upsert(
        self, model_name: str, dimension: int, state: EmbedderState, now: datetime
    ) -> None:
        await self._relational.embedder_identity_upsert(
            self._space_id, model_name, dimension, state, now
        )

    async def _embedder_identity_update_state(
        self, state: EmbedderState, now: datetime
    ) -> None:
        await self._relational.embedder_identity_update_state(
            self._space_id, state, now
        )

    # ===================================================================
    # Row mappers (dict → typed object)
    # ===================================================================
    async def _row_to_verbat(self, r: dict) -> Verbat:
        """Convert a relational row dict to a Verbat, resolving content
        from inline (DB) or S3 (content_ref) as needed.
        """
        content = r.get("content")
        if content is None and r.get("content_ref"):
            # content_ref is "s3://bucket/{mode}/{verbat_id}" — extract
            ref = r["content_ref"]
            parts = ref.rsplit("/", 2)
            if len(parts) == 3:
                extract_mode, verbat_id = parts[1], parts[2]
                content = await self._files.read_raw(extract_mode, verbat_id)
            else:
                content = ""
        elif content is None:
            content = ""

        return Verbat(
            id=r["id"],
            space_id=r["space_id"],
            source_file=r["source_file"],
            source_path=r.get("source_path"),
            content=content,
            content_hash=r["content_hash"],
            extract_mode=ExtractMode(r["extract_mode"]),
            content_date=parse_dt(r["content_date"]) if r.get("content_date") else None,
            filed_at=parse_dt(r["filed_at"]) if r.get("filed_at") else None,
            source_mtime=r.get("source_mtime"),
            normalize_version=r.get("normalize_version", 1),
            deprecated=bool(r.get("deprecated", 0)),
        )

    def _row_to_edge(self, r: dict) -> Edge:
        return Edge(
            id=r["id"],
            space_id=r["space_id"],
            subject=r["subject"],
            predicate=r["predicate"],
            object=r["object"],
            valid_from=parse_dt(r["valid_from"]) if r.get("valid_from") else None,
            valid_to=parse_dt(r["valid_to"]) if r.get("valid_to") else None,
            source_document_id=r.get("source_document_id"),
            source_verbat_id=r.get("source_verbat_id"),
            weight=r.get("weight", 1.0),
            created_at=parse_dt(r["created_at"]) if r.get("created_at") else None,
        )


def _safe_table_suffix(s: str) -> str:
    """Make a string safe to embed in a Postgres table name."""
    import re

    return re.sub(r"[^a-zA-Z0-9_]", "_", s)[:48]


__all__ = ["DistributedVaultFS"]
