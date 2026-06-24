"""SQLite schema for LocalVaultFS (RFC 001 §8.1).

The schema is derived state — safe to drop and rebuild via `reindex`.
L0 verbatim content lives on disk under raw/, L1 markdown lives under wiki/;
this SQLite DB holds metadata, chunks, edges, and embedder identity.
"""

from __future__ import annotations

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Space registration (single row per local space, but table exists for
-- multi-space coexistence within one ~/.ks/ root if user wants).
CREATE TABLE IF NOT EXISTS spaces (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    backend TEXT NOT NULL,
    schema_hash TEXT,
    embedder_model TEXT,
    embedder_dimension INTEGER,
    embedder_state TEXT DEFAULT 'unknown',
    visibility TEXT DEFAULT 'private',
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- v2: ingest pipeline config (RFC 004 §6). All nullable = unset.
    default_agent_id TEXT,
    llm_model TEXT,
    multimodal_model TEXT
);

-- L0 Verbatim metadata (content lives on disk under raw/)
CREATE TABLE IF NOT EXISTS verbats (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_path TEXT,
    content_hash TEXT NOT NULL,
    extract_mode TEXT NOT NULL,
    content_date TEXT,
    filed_at TEXT NOT NULL,
    source_mtime INTEGER,
    normalize_version INTEGER DEFAULT 1,
    deprecated INTEGER DEFAULT 0,
    -- content stored inline for small verbats, NULL for large (then on disk)
    content TEXT,
    content_ref TEXT,
    UNIQUE(space_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_verbats_space ON verbats(space_id, filed_at);
CREATE INDEX IF NOT EXISTS idx_verbats_extract_mode ON verbats(space_id, extract_mode);
CREATE INDEX IF NOT EXISTS idx_verbats_deprecated ON verbats(space_id, deprecated);

-- L1 Document metadata (markdown lives on disk under wiki/)
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    path TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    frontmatter TEXT,
    content_hash TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(space_id, path)
);
CREATE INDEX IF NOT EXISTS idx_documents_space_type ON documents(space_id, type);
CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(space_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(space_id, status);

-- L1 -> L0 pointer (which verbats contributed to a document)
CREATE TABLE IF NOT EXISTS document_sources (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    verbat_id TEXT NOT NULL REFERENCES verbats(id),
    PRIMARY KEY (document_id, verbat_id)
);
CREATE INDEX IF NOT EXISTS idx_doc_sources_verbat ON document_sources(verbat_id);

-- L1 chunks (FTS target; derived, rebuildable)
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_hash TEXT,
    content TEXT NOT NULL,
    token_count INTEGER,
    UNIQUE(document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(document_id);
-- idx_chunks_doc_hash is created by _migrate_chunks_hash after ensuring the
-- chunk_hash column exists, so that upgrading old DBs (table present, column
-- missing) doesn't fail during executescript.

-- L2 Edges with temporal validity
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    source_document_id TEXT REFERENCES documents(id),
    source_verbat_id TEXT REFERENCES verbats(id),
    weight REAL DEFAULT 1.0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_subj ON edges(space_id, subject, valid_to);
CREATE INDEX IF NOT EXISTS idx_edges_obj ON edges(space_id, object, valid_to);
CREATE INDEX IF NOT EXISTS idx_edges_pred ON edges(space_id, predicate);
CREATE INDEX IF NOT EXISTS idx_edges_active ON edges(space_id) WHERE valid_to IS NULL;

-- Embedder identity (single row per space)
CREATE TABLE IF NOT EXISTS embedder_identity (
    space_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- FTS5 full-text index (porter + unicode61 handles CJK reasonably; for
-- proper CJK bigram we add a separate trigram auxiliary at query time).
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content='document_chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON document_chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON document_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_update AFTER UPDATE ON document_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""


async def init_schema(db) -> None:
    """Apply schema to an open aiosqlite connection.

    Usage:
        import aiosqlite
        async with aiosqlite.connect(path) as db:
            await init_schema(db)
    """
    await db.executescript(SCHEMA_SQL)
    await _migrate_spaces_v2(db)
    await _migrate_chunks_hash(db)
    await db.commit()


# Columns added to `spaces` in schema v2. Each entry: (column, type, default).
# Used by `_migrate_spaces_v2` to ALTER existing databases that pre-date v2.
_SPACES_V2_COLUMNS = [
    ("default_agent_id", "TEXT", None),
    ("llm_model", "TEXT", None),
    ("multimodal_model", "TEXT", None),
]


async def _migrate_spaces_v2(db) -> None:
    """Add v2 columns to `spaces` if missing (idempotent).

    SQLite's `CREATE TABLE IF NOT EXISTS` won't add new columns to an
    existing table, so for upgrades from v1 we inspect `PRAGMA table_info`
    and ALTER missing columns in.
    """
    async with db.execute("PRAGMA table_info(spaces)") as cur:
        rows = await cur.fetchall()
    if not rows:
        return  # table doesn't exist yet; CREATE will handle it
    existing = {row[1] for row in rows}  # row[1] = column name
    for col, col_type, default in _SPACES_V2_COLUMNS:
        if col in existing:
            continue
        default_sql = "NULL" if default is None else f"'{default}'"
        await db.execute(
            f"ALTER TABLE spaces ADD COLUMN {col} {col_type} DEFAULT {default_sql}"
        )


async def _migrate_chunks_hash(db) -> None:
    """Add `chunk_hash` column to `document_chunks` if missing (idempotent).

    Used by vector layer to build stable vector IDs
    (`doc:{doc_id}:chunk:{hash}`) so re-chunking after an edit keeps
    stable IDs for unchanged chunks. See `vaultfs/_util.chunk_text`.
    """
    async with db.execute("PRAGMA table_info(document_chunks)") as cur:
        rows = await cur.fetchall()
    if not rows:
        return
    existing = {row[1] for row in rows}
    if "chunk_hash" in existing:
        return
    await db.execute("ALTER TABLE document_chunks ADD COLUMN chunk_hash TEXT")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_doc_hash "
        "ON document_chunks(document_id, chunk_hash)"
    )


def schema_version() -> int:
    """Bump when SCHEMA_SQL changes; used by future migration logic."""
    return 2
