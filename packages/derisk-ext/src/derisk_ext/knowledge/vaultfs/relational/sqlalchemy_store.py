"""SQLAlchemy async relational store for DistributedVaultFS.

Implements all the `BaseVaultFS` abstract relational methods against
Postgres or MySQL via SQLAlchemy 2.x async. DSN examples:
- `postgresql+asyncpg://user:pass@host:5432/db`
- `mysql+asyncmy://user:pass@host:3306/db`

Table shapes mirror the SQLite schema (schema_sql.py) — `verbats`,
`documents`, `document_chunks`, `document_sources`, `edges`,
`embedder_identity` — with one addition: every row carries `space_id`
so multiple distributed spaces share the same cluster.

FTS is dialect-aware:
- Postgres: `tsvector` generated column + GIN index on
  `document_chunks.content`; queries use `websearch_to_tsquery` +
  `ts_rank_cd` scoring.
- MySQL: `FULLTEXT` index on `document_chunks(content)`; queries use
  `MATCH(content) AGAINST(? IN NATURAL LANGUAGE MODE)`.

All writes commit per call — the BaseVaultFS write_lock already
provides cross-call atomicity, and per-call commits keep the session
lifecycle simple.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from derisk.knowledge.types import (
    DocId,
    DocumentMeta,
    Edge,
    EdgeId,
    EmbedderIdentity,
    EmbedderState,
    ExtractMode,
    FtsHit,
    Verbat,
    VerbatId,
)
from derisk_ext.knowledge.vaultfs._util import parse_dt

logger = logging.getLogger(__name__)


# DDL — written to work on both Postgres and MySQL with minor dialect
# differences handled in `_apply_ddl`. JSONB on Postgres, JSON on MySQL;
# tsvector+GIN on Postgres, FULLTEXT on MySQL.
_DDL_BASE = """
CREATE TABLE IF NOT EXISTS verbats (
    id VARCHAR(64) PRIMARY KEY,
    space_id VARCHAR(64) NOT NULL,
    source_file VARCHAR(512) NOT NULL,
    source_path VARCHAR(1024),
    content_hash VARCHAR(128) NOT NULL,
    extract_mode VARCHAR(32) NOT NULL,
    content_date VARCHAR(64),
    filed_at VARCHAR(64) NOT NULL,
    source_mtime BIGINT,
    normalize_version INTEGER DEFAULT 1,
    deprecated INTEGER DEFAULT 0,
    content TEXT,
    content_ref VARCHAR(1024),
    UNIQUE(space_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_verbats_space ON verbats(space_id, filed_at);
CREATE INDEX IF NOT EXISTS idx_verbats_extract_mode ON verbats(space_id, extract_mode);
CREATE INDEX IF NOT EXISTS idx_verbats_deprecated ON verbats(space_id, deprecated);

CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(64) PRIMARY KEY,
    space_id VARCHAR(64) NOT NULL,
    path VARCHAR(1024) NOT NULL,
    type VARCHAR(64) NOT NULL,
    title VARCHAR(1024) NOT NULL,
    frontmatter TEXT,
    content_hash VARCHAR(128) NOT NULL,
    version INTEGER DEFAULT 1,
    status VARCHAR(32) DEFAULT 'active',
    created_at VARCHAR(64) NOT NULL,
    updated_at VARCHAR(64) NOT NULL,
    UNIQUE(space_id, path)
);
CREATE INDEX IF NOT EXISTS idx_documents_space_type ON documents(space_id, type);
CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(space_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(space_id, status);

CREATE TABLE IF NOT EXISTS document_sources (
    document_id VARCHAR(64) NOT NULL,
    verbat_id VARCHAR(64) NOT NULL,
    space_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (document_id, verbat_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (verbat_id) REFERENCES verbats(id)
);
CREATE INDEX IF NOT EXISTS idx_doc_sources_verbat ON document_sources(verbat_id);

CREATE TABLE IF NOT EXISTS document_chunks (
    id VARCHAR(128) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL,
    space_id VARCHAR(64) NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_hash VARCHAR(64),
    content TEXT NOT NULL,
    token_count INTEGER,
    UNIQUE(document_id, chunk_index),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_hash ON document_chunks(document_id, chunk_hash);

CREATE TABLE IF NOT EXISTS edges (
    id VARCHAR(64) PRIMARY KEY,
    space_id VARCHAR(64) NOT NULL,
    subject VARCHAR(1024) NOT NULL,
    predicate VARCHAR(128) NOT NULL,
    object VARCHAR(1024) NOT NULL,
    valid_from VARCHAR(64),
    valid_to VARCHAR(64),
    source_document_id VARCHAR(64),
    source_verbat_id VARCHAR(64),
    weight REAL DEFAULT 1.0,
    created_at VARCHAR(64) NOT NULL,
    FOREIGN KEY (source_document_id) REFERENCES documents(id),
    FOREIGN KEY (source_verbat_id) REFERENCES verbats(id)
);
CREATE INDEX IF NOT EXISTS idx_edges_subj ON edges(space_id, subject, valid_to);
CREATE INDEX IF NOT EXISTS idx_edges_obj ON edges(space_id, object, valid_to);
CREATE INDEX IF NOT EXISTS idx_edges_pred ON edges(space_id, predicate);

CREATE TABLE IF NOT EXISTS embedder_identity (
    space_id VARCHAR(64) PRIMARY KEY,
    model_name VARCHAR(256) NOT NULL,
    dimension INTEGER NOT NULL,
    state VARCHAR(32) NOT NULL,
    updated_at VARCHAR(64) NOT NULL
);
"""

# Postgres-specific: tsvector generated column + GIN index for FTS.
_DDL_POSTGRES_FTS = """
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
CREATE INDEX IF NOT EXISTS idx_chunks_content_tsv ON document_chunks USING gin(content_tsv);
"""

# MySQL-specific: FULLTEXT index on content.
_DDL_MYSQL_FTS = """
CREATE FULLTEXT INDEX idx_chunks_content_fts ON document_chunks(content);
"""


class SQLAlchemyRelationalStore:
    """Async SQLAlchemy store backing DistributedVaultFS.

    The store is partitioned by `space_id` — every row carries it, so
    multiple distributed spaces share the same DB cluster safely.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._engine = None
        self._sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None
        self._dialect: Optional[str] = None

    @property
    def dialect(self) -> str:
        if self._dialect is None:
            raise RuntimeError("Store not initialized — call init() first")
        return self._dialect

    async def init(self) -> None:
        """Create engine + apply schema (idempotent)."""
        self._engine = create_async_engine(self._dsn, echo=False, future=True)
        self._dialect = self._engine.dialect.name  # "postgresql" | "mysql"

        async with self._engine.begin() as conn:
            for stmt in _DDL_BASE.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))

            if self._dialect == "postgresql":
                for stmt in _DDL_POSTGRES_FTS.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        try:
                            await conn.execute(text(stmt))
                        except Exception as e:
                            # Idempotency: ALTER TABLE ADD COLUMN IF NOT EXISTS
                            # is supported in PG 9.6+, but be defensive.
                            logger.debug("Postgres FTS DDL skipped: %s", e)
                # Migration: add chunk_hash column to pre-existing tables.
                try:
                    await conn.execute(
                        text(
                            "ALTER TABLE document_chunks "
                            "ADD COLUMN IF NOT EXISTS chunk_hash VARCHAR(64)"
                        )
                    )
                    await conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS idx_chunks_doc_hash "
                            "ON document_chunks(document_id, chunk_hash)"
                        )
                    )
                except Exception as e:
                    logger.debug("chunk_hash migration skipped: %s", e)
            elif self._dialect == "mysql":
                # CREATE FULLTEXT INDEX IF NOT EXISTS is not supported on
                # older MySQL; use try/except.
                try:
                    await conn.execute(text(_DDL_MYSQL_FTS))
                except Exception as e:
                    logger.debug("MySQL FTS DDL skipped: %s", e)
                # Migration: add chunk_hash column to pre-existing tables.
                try:
                    await conn.execute(
                        text(
                            "SELECT COUNT(*) FROM information_schema.columns "
                            "WHERE table_schema = DATABASE() "
                            "AND table_name = 'document_chunks' "
                            "AND column_name = 'chunk_hash'"
                        )
                    )
                    row = await conn.execute(
                        text(
                            "SELECT COUNT(*) FROM information_schema.columns "
                            "WHERE table_schema = DATABASE() "
                            "AND table_name = 'document_chunks' "
                            "AND column_name = 'chunk_hash'"
                        )
                    )
                    if row.scalar() == 0:
                        await conn.execute(
                            text(
                                "ALTER TABLE document_chunks "
                                "ADD COLUMN chunk_hash VARCHAR(64)"
                            )
                        )
                        await conn.execute(
                            text(
                                "CREATE INDEX idx_chunks_doc_hash "
                                "ON document_chunks(document_id, chunk_hash)"
                            )
                        )
                except Exception as e:
                    logger.debug("MySQL chunk_hash migration skipped: %s", e)
            else:
                logger.warning(
                    "Unknown dialect %s — FTS will fall back to LIKE",
                    self._dialect,
                )

        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    # ------------------------------------------------------------------
    # Session helper
    # ------------------------------------------------------------------
    def _session(self) -> AsyncSession:
        if self._sessionmaker is None:
            raise RuntimeError("Store not initialized — call init() first")
        return self._sessionmaker()

    # ==================================================================
    # L0 Verbatim
    # ==================================================================
    async def verbat_exists_by_hash(
        self, space_id: str, content_hash: str
    ) -> Optional[VerbatId]:
        async with self._session() as s:
            r = await s.execute(
                text(
                    "SELECT id FROM verbats WHERE space_id=:sid AND content_hash=:h "
                    "AND deprecated=0 LIMIT 1"
                ),
                {"sid": space_id, "h": content_hash},
            )
            row = r.first()
            return row[0] if row else None

    async def verbat_insert(
        self,
        v: Verbat,
        inline_content: Optional[str],
        content_ref: Optional[str],
    ) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    """
                    INSERT INTO verbats
                      (id, space_id, source_file, source_path, content_hash,
                       extract_mode, content_date, filed_at, source_mtime,
                       normalize_version, deprecated, content, content_ref)
                    VALUES (:id, :sid, :sf, :sp, :ch, :em, :cd, :fa, :sm, :nv, 0, :c, :cr)
                    """
                ),
                {
                    "id": v.id,
                    "sid": v.space_id,
                    "sf": v.source_file,
                    "sp": v.source_path,
                    "ch": v.content_hash,
                    "em": v.extract_mode.value,
                    "cd": v.content_date.isoformat() if v.content_date else None,
                    "fa": (v.filed_at or datetime.utcnow()).isoformat(),
                    "sm": v.source_mtime,
                    "nv": v.normalize_version,
                    "c": inline_content,
                    "cr": content_ref,
                },
            )
            await s.commit()

    async def verbat_fetch(
        self, space_id: str, vid: VerbatId
    ) -> Optional[dict]:
        async with self._session() as s:
            r = await s.execute(
                text("SELECT * FROM verbats WHERE id=:id AND space_id=:sid"),
                {"id": vid, "sid": space_id},
            )
            row = r.first()
            if not row:
                return None
            return self._row_to_dict(row)

    async def verbat_list_rows(
        self,
        space_id: str,
        extract_mode: Optional[str],
        limit: int,
        offset: int,
    ) -> list[dict]:
        async with self._session() as s:
            if extract_mode:
                r = await s.execute(
                    text(
                        "SELECT * FROM verbats WHERE space_id=:sid AND extract_mode=:em "
                        "ORDER BY filed_at DESC LIMIT :l OFFSET :o"
                    ),
                    {"sid": space_id, "em": extract_mode, "l": limit, "o": offset},
                )
            else:
                r = await s.execute(
                    text(
                        "SELECT * FROM verbats WHERE space_id=:sid "
                        "ORDER BY filed_at DESC LIMIT :l OFFSET :o"
                    ),
                    {"sid": space_id, "l": limit, "o": offset},
                )
            return [self._row_to_dict(row) for row in r.fetchall()]

    async def verbat_search_rows(
        self,
        space_id: str,
        query: str,
        limit: int,
        extract_mode: Optional[str],
    ) -> list[dict]:
        # LIKE-based search — verbats don't have FTS; vectors cover semantic.
        async with self._session() as s:
            if extract_mode:
                r = await s.execute(
                    text(
                        "SELECT * FROM verbats WHERE space_id=:sid AND extract_mode=:em "
                        "AND deprecated=0 AND content LIKE :q LIMIT :l"
                    ),
                    {
                        "sid": space_id,
                        "em": extract_mode,
                        "q": f"%{query}%",
                        "l": limit,
                    },
                )
            else:
                r = await s.execute(
                    text(
                        "SELECT * FROM verbats WHERE space_id=:sid AND deprecated=0 "
                        "AND content LIKE :q LIMIT :l"
                    ),
                    {"sid": space_id, "q": f"%{query}%", "l": limit},
                )
            return [self._row_to_dict(row) for row in r.fetchall()]

    async def verbat_deprecate_row(self, space_id: str, vid: VerbatId) -> None:
        async with self._session() as s:
            await s.execute(
                text("UPDATE verbats SET deprecated=1 WHERE id=:id AND space_id=:sid"),
                {"id": vid, "sid": space_id},
            )
            await s.commit()

    # ==================================================================
    # L1 Document
    # ==================================================================
    async def doc_insert(
        self,
        space_id: str,
        doc_id: DocId,
        norm_path: str,
        page_type: str,
        title: str,
        raw_frontmatter: str,
        content_hash: str,
        now: datetime,
    ) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    """
                    INSERT INTO documents
                      (id, space_id, path, type, title, frontmatter, content_hash,
                       version, status, created_at, updated_at)
                    VALUES (:id, :sid, :p, :t, :ti, :fm, :ch, 1, 'active', :ca, :ua)
                    """
                ),
                {
                    "id": doc_id,
                    "sid": space_id,
                    "p": norm_path,
                    "t": page_type,
                    "ti": title,
                    "fm": raw_frontmatter,
                    "ch": content_hash,
                    "ca": now.isoformat(),
                    "ua": now.isoformat(),
                },
            )
            await s.commit()

    async def doc_fetch_meta_by_path(
        self, space_id: str, norm_path: str
    ) -> Optional[tuple[DocId, int]]:
        async with self._session() as s:
            r = await s.execute(
                text("SELECT id, version FROM documents WHERE space_id=:sid AND path=:p"),
                {"sid": space_id, "p": norm_path},
            )
            row = r.first()
            if not row:
                return None
            return (row[0], row[1])

    async def doc_fetch_row(self, space_id: str, doc_id: DocId) -> Optional[dict]:
        async with self._session() as s:
            r = await s.execute(
                text("SELECT * FROM documents WHERE id=:id AND space_id=:sid"),
                {"id": doc_id, "sid": space_id},
            )
            row = r.first()
            if not row:
                return None
            return self._row_to_dict(row)

    async def doc_update_version(
        self,
        space_id: str,
        doc_id: DocId,
        page_type: str,
        title: str,
        raw_frontmatter: str,
        content_hash: str,
        now: datetime,
    ) -> None:
        async with self._session() as s:
            r = await s.execute(
                text("SELECT version FROM documents WHERE id=:id"),
                {"id": doc_id},
            )
            row = r.first()
            new_version = (row[0] + 1) if row else 1
            await s.execute(
                text(
                    """
                    UPDATE documents SET
                      type=:t, title=:ti, frontmatter=:fm, content_hash=:ch,
                      version=:v, updated_at=:ua
                    WHERE id=:id AND space_id=:sid
                    """
                ),
                {
                    "id": doc_id,
                    "sid": space_id,
                    "t": page_type,
                    "ti": title,
                    "fm": raw_frontmatter,
                    "ch": content_hash,
                    "v": new_version,
                    "ua": now.isoformat(),
                },
            )
            await s.commit()

    async def doc_delete_row(self, space_id: str, doc_id: DocId) -> None:
        async with self._session() as s:
            # NULL out edges FK first (edges.source_document_id has no
            # ON DELETE SET NULL in our schema).
            await s.execute(
                text(
                    "UPDATE edges SET source_document_id=NULL "
                    "WHERE source_document_id=:id AND space_id=:sid"
                ),
                {"id": doc_id, "sid": space_id},
            )
            await s.execute(
                text("DELETE FROM documents WHERE id=:id AND space_id=:sid"),
                {"id": doc_id, "sid": space_id},
            )
            await s.commit()

    async def doc_list_rows(
        self,
        space_id: str,
        type: Optional[str],
        limit: int,
        offset: int,
    ) -> list[DocumentMeta]:
        async with self._session() as s:
            if type:
                r = await s.execute(
                    text(
                        "SELECT id, path, type, title, status, created_at, updated_at "
                        "FROM documents WHERE space_id=:sid AND type=:t "
                        "ORDER BY updated_at DESC LIMIT :l OFFSET :o"
                    ),
                    {"sid": space_id, "t": type, "l": limit, "o": offset},
                )
            else:
                r = await s.execute(
                    text(
                        "SELECT id, path, type, title, status, created_at, updated_at "
                        "FROM documents WHERE space_id=:sid "
                        "ORDER BY updated_at DESC LIMIT :l OFFSET :o"
                    ),
                    {"sid": space_id, "l": limit, "o": offset},
                )
            return [
                DocumentMeta(
                    id=row[0],
                    path=row[1],
                    type=row[2],
                    title=row[3],
                    status=row[4],
                    created_at=parse_dt(row[5]),
                    updated_at=parse_dt(row[6]),
                )
                for row in r.fetchall()
            ]

    async def doc_invalidate_edges(
        self, space_id: str, doc_id: DocId, now_iso: str
    ) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    "UPDATE edges SET valid_to=:vt, source_document_id=NULL "
                    "WHERE source_document_id=:id AND space_id=:sid AND valid_to IS NULL"
                ),
                {"vt": now_iso, "id": doc_id, "sid": space_id},
            )
            await s.commit()

    async def chunks_replace_for_doc(
        self,
        space_id: str,
        doc_id: DocId,
        body: str,
        chunks: list[tuple[int, str, str]],
    ) -> None:
        """Replace all chunks for a doc.

        `chunks` is a list of `(chunk_index, chunk_text, chunk_hash)` tuples
        (see `vaultfs._util.chunk_text`). The chunk_hash is content-addressed
        so re-chunking after an edit keeps stable IDs for unchanged chunks —
        vector IDs derived from the hash survive.
        """
        async with self._session() as s:
            await s.execute(
                text("DELETE FROM document_chunks WHERE document_id=:id"),
                {"id": doc_id},
            )
            for idx, chunk_text_body, chunk_hash in chunks:
                chunk_id = f"{doc_id}_c{chunk_hash}"
                await s.execute(
                    text(
                        "INSERT INTO document_chunks (id, document_id, space_id, chunk_index, chunk_hash, content, token_count) "
                        "VALUES (:id, :did, :sid, :ci, :ch, :c, :tc)"
                    ),
                    {
                        "id": chunk_id,
                        "did": doc_id,
                        "sid": space_id,
                        "ci": idx,
                        "ch": chunk_hash,
                        "c": chunk_text_body,
                        "tc": len(chunk_text_body) // 4,
                    },
                )
            await s.commit()

    async def doc_list_chunk_hashes(self, space_id: str, doc_id: DocId) -> list[str]:
        """Return all chunk_hash values for a doc — used by doc_delete to
        clean up the corresponding vectors.
        """
        async with self._session() as s:
            res = await s.execute(
                text(
                    "SELECT chunk_hash FROM document_chunks "
                    "WHERE document_id=:id AND space_id=:sid AND chunk_hash IS NOT NULL"
                ),
                {"id": doc_id, "sid": space_id},
            )
            return [r[0] for r in res.fetchall()]

    async def fts_search_chunks(
        self, space_id: str, query: str, limit: int
    ) -> list[FtsHit]:
        if self._dialect == "postgresql":
            sql = """
                SELECT c.id as chunk_id, c.document_id, d.path, d.title,
                       ts_rank_cd(c.content_tsv, q) as score,
                       ts_headline('simple', c.content, q, 'MaxFragments=10, MaxWords=20') as snippet
                FROM document_chunks c, documents d, websearch_to_tsquery('simple', :q) q
                WHERE c.document_id = d.id AND d.space_id = :sid
                  AND c.content_tsv @@ q
                ORDER BY score DESC LIMIT :l
            """
            params = {"sid": space_id, "q": query, "l": limit}
        elif self._dialect == "mysql":
            sql = """
                SELECT c.id as chunk_id, c.document_id, d.path, d.title,
                       MATCH(c.content) AGAINST(:q IN NATURAL LANGUAGE MODE) as score,
                       SUBSTRING(c.content, 1, 200) as snippet
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.space_id = :sid
                  AND MATCH(c.content) AGAINST(:q IN NATURAL LANGUAGE MODE) > 0
                ORDER BY score DESC LIMIT :l
            """
            params = {"sid": space_id, "q": query, "l": limit}
        else:
            # Fallback: LIKE
            sql = """
                SELECT c.id as chunk_id, c.document_id, d.path, d.title,
                       1.0 as score,
                       SUBSTRING(c.content, 1, 200) as snippet
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.space_id = :sid AND c.content LIKE :q
                LIMIT :l
            """
            params = {"sid": space_id, "q": f"%{query}%", "l": limit}

        async with self._session() as s:
            r = await s.execute(text(sql), params)
            return [
                FtsHit(
                    chunk_id=row[0],
                    document_id=row[1],
                    path=row[2],
                    title=row[3],
                    score=float(row[4]),
                    snippet=row[5] or "",
                )
                for row in r.fetchall()
            ]

    async def lookup_doc_verbats(
        self, space_id: str, doc_id: DocId
    ) -> list[VerbatId]:
        async with self._session() as s:
            r = await s.execute(
                text("SELECT verbat_id FROM document_sources WHERE document_id=:id"),
                {"id": doc_id},
            )
            return [row[0] for row in r.fetchall()]

    async def doc_search_references(
        self, space_id: str, query: str, limit: int
    ) -> list[dict]:
        async with self._session() as s:
            r = await s.execute(
                text(
                    """
                    SELECT DISTINCT d.id, d.path, d.type, d.title
                    FROM documents d
                    JOIN edges e ON e.source_document_id = d.id
                    WHERE d.space_id=:sid AND (e.subject=:q OR e.object=:q)
                    ORDER BY d.updated_at DESC LIMIT :l
                    """
                ),
                {"sid": space_id, "q": query, "l": limit},
            )
            return [
                {
                    "id": row[0],
                    "path": row[1],
                    "type": row[2],
                    "title": row[3],
                }
                for row in r.fetchall()
            ]

    # ==================================================================
    # L2 Graph
    # ==================================================================
    async def edge_insert(self, space_id: str, e: Edge) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    """
                    INSERT INTO edges
                      (id, space_id, subject, predicate, object, valid_from, valid_to,
                       source_document_id, source_verbat_id, weight, created_at)
                    VALUES (:id, :sid, :sub, :pred, :obj, :vf, NULL, :sdid, :svid, :w, :ca)
                    """
                ),
                {
                    "id": e.id,
                    "sid": space_id,
                    "sub": e.subject,
                    "pred": e.predicate,
                    "obj": e.object,
                    "vf": e.valid_from.isoformat() if e.valid_from else None,
                    "sdid": e.source_document_id,
                    "svid": e.source_verbat_id,
                    "w": e.weight,
                    "ca": e.created_at.isoformat() if e.created_at else datetime.utcnow().isoformat(),
                },
            )
            await s.commit()

    async def edge_invalidate_row(
        self, space_id: str, eid: EdgeId, valid_to_iso: str
    ) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    "UPDATE edges SET valid_to=:vt WHERE id=:id AND space_id=:sid "
                    "AND valid_to IS NULL"
                ),
                {"vt": valid_to_iso, "id": eid, "sid": space_id},
            )
            await s.commit()

    async def edges_query(
        self,
        space_id: str,
        entity: Optional[str],
        predicate: Optional[str],
        include_invalid: bool,
    ) -> list[dict]:
        clauses = ["space_id=:sid"]
        params: dict[str, Any] = {"sid": space_id}
        if entity:
            clauses.append("(subject=:e OR object=:e)")
            params["e"] = entity
        if predicate:
            clauses.append("predicate=:p")
            params["p"] = predicate
        if not include_invalid:
            clauses.append("valid_to IS NULL")
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM edges WHERE {where} LIMIT 500"
        async with self._session() as s:
            r = await s.execute(text(sql), params)
            return [self._row_to_dict(row) for row in r.fetchall()]

    async def edges_for_node(self, space_id: str, node: str) -> list[dict]:
        async with self._session() as s:
            r = await s.execute(
                text(
                    "SELECT * FROM edges WHERE space_id=:sid AND (subject=:n OR object=:n) "
                    "AND valid_to IS NULL"
                ),
                {"sid": space_id, "n": node},
            )
            return [self._row_to_dict(row) for row in r.fetchall()]

    async def edges_timeline(self, space_id: str, entity: str) -> list[dict]:
        async with self._session() as s:
            r = await s.execute(
                text(
                    "SELECT * FROM edges WHERE space_id=:sid AND (subject=:e OR object=:e) "
                    "ORDER BY COALESCE(valid_from, created_at) ASC"
                ),
                {"sid": space_id, "e": entity},
            )
            return [self._row_to_dict(row) for row in r.fetchall()]

    async def edges_backlinks(self, space_id: str, entity: str) -> list[dict]:
        async with self._session() as s:
            r = await s.execute(
                text(
                    "SELECT * FROM edges WHERE space_id=:sid AND object=:e AND valid_to IS NULL "
                    "ORDER BY created_at DESC"
                ),
                {"sid": space_id, "e": entity},
            )
            return [self._row_to_dict(row) for row in r.fetchall()]

    async def doc_sources_insert(
        self, space_id: str, doc_id: DocId, verbat_id: VerbatId
    ) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    "INSERT INTO document_sources (document_id, verbat_id, space_id) "
                    "VALUES (:d, :v, :s)"
                ),
                {"d": doc_id, "v": verbat_id, "s": space_id},
            )
            await s.commit()

    # ==================================================================
    # Rebuild helpers
    # ==================================================================
    async def chunks_clear_all(self, space_id: str) -> None:
        async with self._session() as s:
            await s.execute(
                text("DELETE FROM document_chunks WHERE space_id=:sid"),
                {"sid": space_id},
            )
            await s.commit()

    async def edges_invalidate_all(self, space_id: str, now_iso: str) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    "UPDATE edges SET valid_to=:vt WHERE space_id=:sid AND valid_to IS NULL"
                ),
                {"vt": now_iso, "sid": space_id},
            )
            await s.commit()

    # ==================================================================
    # Embedder identity
    # ==================================================================
    async def embedder_identity_get(
        self, space_id: str
    ) -> Optional[EmbedderIdentity]:
        async with self._session() as s:
            r = await s.execute(
                text("SELECT * FROM embedder_identity WHERE space_id=:sid"),
                {"sid": space_id},
            )
            row = r.first()
            if not row:
                return None
            d = self._row_to_dict(row)
            return EmbedderIdentity(
                space_id=space_id,
                model_name=d["model_name"],
                dimension=d["dimension"],
                state=EmbedderState(d["state"]),
                updated_at=parse_dt(d["updated_at"]),
            )

    async def embedder_identity_upsert(
        self,
        space_id: str,
        model_name: str,
        dimension: int,
        state: EmbedderState,
        now: datetime,
    ) -> None:
        async with self._session() as s:
            if self._dialect == "postgresql":
                await s.execute(
                    text(
                        """
                        INSERT INTO embedder_identity (space_id, model_name, dimension, state, updated_at)
                        VALUES (:sid, :mn, :d, :st, :ua)
                        ON CONFLICT (space_id) DO UPDATE SET
                          model_name=EXCLUDED.model_name,
                          dimension=EXCLUDED.dimension,
                          state=EXCLUDED.state,
                          updated_at=EXCLUDED.updated_at
                        """
                    ),
                    {
                        "sid": space_id,
                        "mn": model_name,
                        "d": dimension,
                        "st": state.value,
                        "ua": now.isoformat(),
                    },
                )
            elif self._dialect == "mysql":
                await s.execute(
                    text(
                        """
                        INSERT INTO embedder_identity (space_id, model_name, dimension, state, updated_at)
                        VALUES (:sid, :mn, :d, :st, :ua)
                        ON DUPLICATE KEY UPDATE
                          model_name=VALUES(model_name),
                          dimension=VALUES(dimension),
                          state=VALUES(state),
                          updated_at=VALUES(updated_at)
                        """
                    ),
                    {
                        "sid": space_id,
                        "mn": model_name,
                        "d": dimension,
                        "st": state.value,
                        "ua": now.isoformat(),
                    },
                )
            else:
                # Generic: try UPDATE then INSERT
                r = await s.execute(
                    text("SELECT 1 FROM embedder_identity WHERE space_id=:sid"),
                    {"sid": space_id},
                )
                if r.first():
                    await s.execute(
                        text(
                            "UPDATE embedder_identity SET model_name=:mn, dimension=:d, "
                            "state=:st, updated_at=:ua WHERE space_id=:sid"
                        ),
                        {
                            "sid": space_id,
                            "mn": model_name,
                            "d": dimension,
                            "st": state.value,
                            "ua": now.isoformat(),
                        },
                    )
                else:
                    await s.execute(
                        text(
                            "INSERT INTO embedder_identity (space_id, model_name, dimension, state, updated_at) "
                            "VALUES (:sid, :mn, :d, :st, :ua)"
                        ),
                        {
                            "sid": space_id,
                            "mn": model_name,
                            "d": dimension,
                            "st": state.value,
                            "ua": now.isoformat(),
                        },
                    )
            await s.commit()

    async def embedder_identity_update_state(
        self, space_id: str, state: EmbedderState, now: datetime
    ) -> None:
        async with self._session() as s:
            await s.execute(
                text(
                    "UPDATE embedder_identity SET state=:st, updated_at=:ua WHERE space_id=:sid"
                ),
                {"st": state.value, "ua": now.isoformat(), "sid": space_id},
            )
            await s.commit()

    # ==================================================================
    # Lock helpers (used by SQLAdvisoryLock)
    # ==================================================================
    async def acquire_advisory_lock(
        self, space_id: str, timeout: int
    ) -> Optional[Any]:
        """Acquire a cross-process advisory lock.

        Returns an opaque handle on success, None on timeout.
        - Postgres: `pg_try_advisory_lock(hash)` polled until acquired
          or timeout. Handle is the int key for `pg_advisory_unlock`.
        - MySQL: `GET_LOCK('ks:{sid}', timeout)` returns 1 on success.
          Handle is the lock name string for `RELEASE_LOCK`.
        """
        if self._dialect == "postgresql":
            from derisk_ext.knowledge.vaultfs.pg_vector_store import advisory_lock_key

            key = advisory_lock_key(space_id)
            import asyncio

            deadline = asyncio.get_event_loop().time() + timeout
            async with self._session() as s:
                while True:
                    r = await s.execute(
                        text("SELECT pg_try_advisory_lock(:k)"), {"k": key}
                    )
                    row = r.first()
                    if row and row[0]:
                        await s.commit()
                        return ("pg", key)
                    if asyncio.get_event_loop().time() >= deadline:
                        await s.commit()
                        return None
                    await asyncio.sleep(0.1)
        elif self._dialect == "mysql":
            lock_name = f"ks:{space_id}"
            async with self._session() as s:
                r = await s.execute(
                    text("SELECT GET_LOCK(:n, :t)"),
                    {"n": lock_name, "t": timeout},
                )
                row = r.first()
                await s.commit()
                if row and row[0] == 1:
                    return ("mysql", lock_name)
                return None
        else:
            raise NotImplementedError(
                f"Advisory lock not supported on dialect {self._dialect}"
            )

    async def release_advisory_lock(self, handle: Any) -> None:
        kind, key = handle
        async with self._session() as s:
            if kind == "pg":
                await s.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": key}
                )
            elif kind == "mysql":
                await s.execute(
                    text("SELECT RELEASE_LOCK(:n)"), {"n": key}
                )
            await s.commit()

    # ==================================================================
    # Helpers
    # ==================================================================
    def _row_to_dict(self, row) -> dict:
        """Convert a SQLAlchemy Row to a plain dict by column name."""
        try:
            return dict(row._mapping)
        except Exception:
            # Fallback for older SQLAlchemy versions
            return {k: getattr(row, k) for k in row._fields} if hasattr(row, "_fields") else dict(row)
