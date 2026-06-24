"""LocalVaultFS - single-machine storage backend (RFC 002 §4).

Composition:
- L0 verbatim content: FS under raw/{sources,convos,clips}/
- L1 document markdown: FS under wiki/<type>/<slug>.md
- L0/L1/L2 metadata + chunks + edges: SQLite (.ks/index.db)
- Vectors: LanceDB (.ks/vectors.lance) - lazy-imported, optional
- Writer lock: flock on .ks/writer.lock
- Events: in-process asyncio.Queue fan-out
- Filesystem watcher: watchfiles (optional)

Layout:
    <root>/
      schema.md
      purpose.md
      raw/
        sources/
        convos/
        clips/
      wiki/
        index.md
        log.md
        overview.md
        <type>/<slug>.md
      .ks/
        index.db
        vectors.lance/      (only if embedding used)
        writer.lock
        chats/

High-level L0/L1/L2 orchestration (path normalization, schema validation,
event publishing, lock flow) lives in BaseVaultFS. This subclass only
implements the SQLite + FS + LanceDB storage seam.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import aiosqlite

from derisk.knowledge.frontmatter import parse_markdown
from derisk.knowledge.schema import default_schema_md
from derisk.knowledge.schema_sql import init_schema
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
    Subgraph,
    Verbat,
    VerbatHit,
    VerbatId,
    VectorHit,
    new_doc_id,
    new_edge_id,
    new_verbat_id,
    sha256_hash,
)
from derisk.knowledge.vaultfs import Subscription, Watcher

from ._util import (
    INLINE_THRESHOLD,
    PROTECTED_FILES,
    chunk_text,
    make_snippet,
    normalize_wiki_path,
    parse_dt,
    serialize_markdown,
    validate_wiki_path,
)
from .base import BaseVaultFS, EmbedderMismatchError

logger = logging.getLogger(__name__)


class LocalWriteLock:
    """flock-based cross-process lock handle.

    Returned by `_acquire_distributed_lock` and released by
    `_release_distributed_lock`. The in-process asyncio.Lock is released
    separately by `_BaseWriteLock.release()`.
    """

    def __init__(self, fd: int, lock_path: Path):
        self.fd = fd
        self.lock_path = lock_path


class LocalSubscription(Subscription):
    def __init__(self, queue: asyncio.Queue, subscribers: set, task: Optional[asyncio.Task] = None):
        self._queue = queue
        self._subscribers = subscribers
        self._task = task

    def cancel(self) -> None:
        self._subscribers.discard(self._queue)
        if self._task is not None:
            self._task.cancel()


class LocalWatcher(Watcher):
    def __init__(self, stop_fn: Callable[[], None]):
        self._stop_fn = stop_fn

    def stop(self) -> None:
        self._stop_fn()


class LocalVaultFS(BaseVaultFS):
    """Single-machine VaultFS implementation.

    Instantiate one per Space. Do not share across spaces.
    """

    def __init__(self, space_id: SpaceId, root: Path | str):
        super().__init__(space_id)
        self._root = Path(root).expanduser().resolve()
        self._db_path = self._root / ".ks" / "index.db"
        self._lock_path = self._root / ".ks" / "writer.lock"
        self._db: Optional[aiosqlite.Connection] = None
        self._lock_fd: Optional[int] = None
        self._watcher_task: Optional[asyncio.Task] = None

    # ----- metadata -----
    @property
    def backend_type(self) -> str:
        return "local"

    @property
    def root(self) -> Path:
        return self._root

    # ----- lifecycle -----
    async def initialize(self) -> None:
        """Create directory structure + open DB + apply schema."""
        await super().initialize()

        for sub in ["raw/sources", "raw/convos", "raw/clips", "wiki", ".ks/chats"]:
            (self._root / sub).mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await init_schema(self._db)

        self._lock_fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o644)

        # Seed schema.md + protected files if missing (RFC 003 §3.7)
        schema_path = self._root / "schema.md"
        if not schema_path.exists():
            schema_path.write_text(
                default_schema_md(self._root.name), encoding="utf-8"
            )
        for name in ("index.md", "log.md", "overview.md", "purpose.md"):
            p = self._root / "wiki" / name if name != "purpose.md" else self._root / name
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f"# {name[:-3].title()}\n\n", encoding="utf-8")

    async def close(self) -> None:
        if self._watcher_task:
            self._watcher_task.cancel()
        if self._db:
            await self._db.close()
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        await super().close()

    # ===================================================================
    # Schema (config layer)
    # ===================================================================
    async def read_schema_md(self) -> str:
        path = self._root / "schema.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    async def write_schema_md(self, content: str) -> None:
        path = self._root / "schema.md"
        path.write_text(content, encoding="utf-8")
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
        path = self._root / "purpose.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # ===================================================================
    # L0 Verbatim — SQLite storage
    # ===================================================================
    async def _verbat_exists_by_hash(self, content_hash: str) -> Optional[VerbatId]:
        rows = await self._db.execute_fetchall(
            "SELECT id FROM verbats WHERE space_id=? AND content_hash=? AND deprecated=0",
            (self._space_id, content_hash),
        )
        if rows:
            return rows[0]["id"]
        return None

    async def _verbat_insert(
        self, v: Verbat, inline_content: Optional[str], content_ref: Optional[str]
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO verbats
              (id, space_id, source_file, source_path, content_hash,
               extract_mode, content_date, filed_at, source_mtime,
               normalize_version, deprecated, content, content_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                v.id,
                self._space_id,
                v.source_file,
                v.source_path,
                v.content_hash,
                v.extract_mode.value,
                v.content_date.isoformat() if v.content_date else None,
                (v.filed_at or datetime.utcnow()).isoformat(),
                v.source_mtime,
                v.normalize_version,
                inline_content,
                content_ref,
            ),
        )
        await self._db.commit()

    async def _verbat_fetch(self, vid: VerbatId) -> Optional[Verbat]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM verbats WHERE id=? AND space_id=?",
            (vid, self._space_id),
        )
        if not rows:
            return None
        return self._row_to_verbat(rows[0])

    async def _verbat_list_rows(
        self, extract_mode: Optional[str], limit: int, offset: int
    ) -> list[Verbat]:
        if extract_mode:
            cursor = await self._db.execute(
                "SELECT * FROM verbats WHERE space_id=? AND extract_mode=? "
                "ORDER BY filed_at DESC LIMIT ? OFFSET ?",
                (self._space_id, extract_mode, limit, offset),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM verbats WHERE space_id=? "
                "ORDER BY filed_at DESC LIMIT ? OFFSET ?",
                (self._space_id, limit, offset),
            )
        rows = await cursor.fetchall()
        return [self._row_to_verbat(r) for r in rows]

    async def _verbat_search_rows(
        self, query: str, limit: int, extract_mode: Optional[str]
    ) -> list[Verbat]:
        if extract_mode:
            cursor = await self._db.execute(
                "SELECT * FROM verbats WHERE space_id=? AND extract_mode=? "
                "AND deprecated=0 AND content LIKE ? LIMIT ?",
                (self._space_id, extract_mode, f"%{query}%", limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM verbats WHERE space_id=? AND deprecated=0 "
                "AND content LIKE ? LIMIT ?",
                (self._space_id, f"%{query}%", limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_verbat(r) for r in rows]

    async def _verbat_deprecate_row(self, vid: VerbatId) -> None:
        await self._db.execute(
            "UPDATE verbats SET deprecated=1 WHERE id=? AND space_id=?",
            (vid, self._space_id),
        )
        await self._db.commit()

    # ===================================================================
    # L1 Document — SQLite storage
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
        await self._db.execute(
            """
            INSERT INTO documents
              (id, space_id, path, type, title, frontmatter, content_hash,
               version, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, ?)
            """,
            (
                doc_id,
                self._space_id,
                norm_path,
                page_type,
                title,
                raw_frontmatter,
                content_hash,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        await self._db.commit()

    async def _doc_fetch_meta_by_path(self, norm_path: str) -> Optional[tuple[DocId, int]]:
        rows = await self._db.execute_fetchall(
            "SELECT id, version FROM documents WHERE space_id=? AND path=?",
            (self._space_id, norm_path),
        )
        if not rows:
            return None
        return (rows[0]["id"], rows[0]["version"])

    async def _doc_fetch_row(self, doc_id: DocId) -> Optional[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM documents WHERE id=? AND space_id=?",
            (doc_id, self._space_id),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "type": r["type"],
            "title": r["title"],
            "content_hash": r["content_hash"],
            "version": r["version"],
            "status": r["status"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    async def _doc_update_version(
        self,
        doc_id: DocId,
        page_type: str,
        title: str,
        raw_frontmatter: str,
        content_hash: str,
        now: datetime,
    ) -> None:
        rows = await self._db.execute_fetchall(
            "SELECT version FROM documents WHERE id=?", (doc_id,)
        )
        new_version = (rows[0]["version"] + 1) if rows else 1
        await self._db.execute(
            """
            UPDATE documents SET
              type=?, title=?, frontmatter=?, content_hash=?,
              version=?, updated_at=?
            WHERE id=?
            """,
            (
                page_type,
                title,
                raw_frontmatter,
                content_hash,
                new_version,
                now.isoformat(),
                doc_id,
            ),
        )
        await self._db.commit()

    async def _doc_delete_row(self, doc_id: DocId) -> None:
        await self._db.execute(
            "DELETE FROM documents WHERE id=?", (doc_id,)
        )
        await self._db.commit()

    async def _doc_list_rows(
        self, type: Optional[str], limit: int, offset: int
    ) -> list[DocumentMeta]:
        if type:
            cursor = await self._db.execute(
                "SELECT id, path, type, title, status, created_at, updated_at "
                "FROM documents WHERE space_id=? AND type=? "
                "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (self._space_id, type, limit, offset),
            )
        else:
            cursor = await self._db.execute(
                "SELECT id, path, type, title, status, created_at, updated_at "
                "FROM documents WHERE space_id=? "
                "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (self._space_id, limit, offset),
            )
        rows = await cursor.fetchall()
        return [
            DocumentMeta(
                id=r["id"],
                path=r["path"],
                type=r["type"],
                title=r["title"],
                status=r["status"],
                created_at=parse_dt(r["created_at"]),
                updated_at=parse_dt(r["updated_at"]),
            )
            for r in rows
        ]

    async def _doc_invalidate_edges(self, doc_id: DocId, now_iso: str) -> None:
        # Invalidate edges whose source is this doc; NULL the FK so subsequent
        # document deletion doesn't trip the FOREIGN KEY constraint
        # (edges.source_document_id has no ON DELETE SET NULL).
        await self._db.execute(
            "UPDATE edges SET valid_to=?, source_document_id=NULL "
            "WHERE source_document_id=? AND valid_to IS NULL",
            (now_iso, doc_id),
        )
        await self._db.commit()

    async def _chunks_replace_for_doc(self, doc_id: DocId, body: str) -> None:
        await self._db.execute(
            "DELETE FROM document_chunks WHERE document_id=?", (doc_id,)
        )
        chunks = chunk_text(body, max_chars=2000)
        for idx, chunk_text_body, chunk_hash in chunks:
            chunk_id = f"{doc_id}_c{chunk_hash}"
            await self._db.execute(
                "INSERT INTO document_chunks (id, document_id, chunk_index, chunk_hash, content, token_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chunk_id, doc_id, idx, chunk_hash, chunk_text_body, len(chunk_text_body) // 4),
            )
        await self._db.commit()

    async def _doc_list_chunk_hashes(self, doc_id: DocId) -> list[str]:
        async with self._db.execute(
            "SELECT chunk_hash FROM document_chunks "
            "WHERE document_id=? AND chunk_hash IS NOT NULL",
            (doc_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def _fts_search_chunks(self, query: str, limit: int) -> list[FtsHit]:
        cursor = await self._db.execute(
            """
            SELECT c.id as chunk_id, c.document_id, d.path, d.title,
                   bm25(chunks_fts) as score,
                   snippet(chunks_fts, 0, '<<', '>>', '...', 20) as snippet
            FROM chunks_fts
            JOIN document_chunks c ON c.rowid = chunks_fts.rowid
            JOIN documents d ON d.id = c.document_id
            WHERE chunks_fts MATCH ? AND d.space_id=?
            ORDER BY score LIMIT ?
            """,
            (query, self._space_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            FtsHit(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                path=r["path"],
                title=r["title"],
                score=-r["score"],
                snippet=r["snippet"] or "",
            )
            for r in rows
        ]

    async def _lookup_doc_verbats(self, doc_id: DocId) -> list[VerbatId]:
        cursor = await self._db.execute(
            "SELECT verbat_id FROM document_sources WHERE document_id=?",
            (doc_id,),
        )
        rows = await cursor.fetchall()
        return [r["verbat_id"] for r in rows]

    async def _doc_search_references(self, query: str, limit: int) -> list[DocHit]:
        cursor = await self._db.execute(
            """
            SELECT DISTINCT d.id, d.path, d.type, d.title, d.updated_at
            FROM documents d
            JOIN edges e ON e.source_document_id = d.id
            WHERE d.space_id=? AND (e.subject=? OR e.object=?)
            ORDER BY d.updated_at DESC
            LIMIT ?
            """,
            (self._space_id, query, query, limit),
        )
        rows = await cursor.fetchall()
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
    # File I/O (FS-backed)
    # ===================================================================
    async def _raw_write(self, rel_path: str, content: str) -> None:
        path = self._root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    async def _raw_read(self, rel_path: str) -> str:
        path = self._root / rel_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    async def _raw_delete(self, rel_path: str) -> None:
        path = self._root / rel_path
        if path.exists():
            path.unlink()

    async def _wiki_write(self, norm_path: str, content: str) -> None:
        path = self._root / "wiki" / norm_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    async def _wiki_read(self, norm_path: str) -> str:
        path = self._root / "wiki" / norm_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    async def _wiki_delete(self, norm_path: str) -> None:
        path = self._root / "wiki" / norm_path
        if path.exists():
            path.unlink()

    # ===================================================================
    # L2 Graph — SQLite storage
    # ===================================================================
    async def _edge_insert(self, e: Edge) -> None:
        await self._db.execute(
            """
            INSERT INTO edges
              (id, space_id, subject, predicate, object, valid_from, valid_to,
               source_document_id, source_verbat_id, weight, created_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
            """,
            (
                e.id,
                self._space_id,
                e.subject,
                e.predicate,
                e.object,
                e.valid_from.isoformat() if e.valid_from else None,
                e.source_document_id,
                e.source_verbat_id,
                e.weight,
                e.created_at.isoformat(),
            ),
        )
        await self._db.commit()

    async def _edge_invalidate_row(self, eid: EdgeId, valid_to_iso: str) -> None:
        await self._db.execute(
            "UPDATE edges SET valid_to=? WHERE id=? AND space_id=? AND valid_to IS NULL",
            (valid_to_iso, eid, self._space_id),
        )
        await self._db.commit()

    async def _edges_query(
        self,
        entity: Optional[str],
        predicate: Optional[str],
        include_invalid: bool,
    ) -> list[Edge]:
        clauses = ["space_id=?"]
        params: list[Any] = [self._space_id]
        if entity:
            clauses.append("(subject=? OR object=?)")
            params.extend([entity, entity])
        if predicate:
            clauses.append("predicate=?")
            params.append(predicate)
        if not include_invalid:
            clauses.append("valid_to IS NULL")
        where = " AND ".join(clauses)

        cursor = await self._db.execute(
            f"SELECT * FROM edges WHERE {where} LIMIT 500", params
        )
        rows = await cursor.fetchall()
        return [self._row_to_edge(r) for r in rows]

    async def _edges_for_node(self, node: str) -> list[Edge]:
        cursor = await self._db.execute(
            "SELECT * FROM edges WHERE space_id=? AND (subject=? OR object=?) "
            "AND valid_to IS NULL",
            (self._space_id, node, node),
        )
        rows = await cursor.fetchall()
        return [self._row_to_edge(r) for r in rows]

    async def _edges_timeline(self, entity: str) -> list[Edge]:
        cursor = await self._db.execute(
            "SELECT * FROM edges WHERE space_id=? AND (subject=? OR object=?) "
            "ORDER BY COALESCE(valid_from, created_at) ASC",
            (self._space_id, entity, entity),
        )
        rows = await cursor.fetchall()
        return [self._row_to_edge(r) for r in rows]

    async def _edges_backlinks(self, entity: str) -> list[Edge]:
        cursor = await self._db.execute(
            "SELECT * FROM edges WHERE space_id=? AND object=? AND valid_to IS NULL "
            "ORDER BY created_at DESC",
            (self._space_id, entity),
        )
        rows = await cursor.fetchall()
        return [self._row_to_edge(r) for r in rows]

    async def _rebuild_doc_edges(
        self, doc_id: DocId, frontmatter: dict, body: str
    ) -> None:
        from derisk.knowledge.frontmatter import extract_footnotes, extract_wikilinks

        # 1. Wikilinks → links-to edges
        wikilinks = extract_wikilinks(body)
        related = frontmatter.get("related", []) or []
        if isinstance(related, str):
            related = [related]
        wikilinks.extend(related)

        title = frontmatter.get("title", "")
        now = datetime.utcnow()
        for target in wikilinks:
            await self._db.execute(
                "INSERT INTO edges (id, space_id, subject, predicate, object, valid_from, valid_to, "
                "source_document_id, weight, created_at) "
                "VALUES (?, ?, ?, 'links-to', ?, ?, NULL, ?, 1.0, ?)",
                (
                    new_edge_id(),
                    self._space_id,
                    title,
                    target,
                    now.isoformat(),
                    doc_id,
                    now.isoformat(),
                ),
            )

        # 2. Footnotes → cites edges
        footnotes = extract_footnotes(body)
        for fn in footnotes:
            await self._db.execute(
                "INSERT INTO edges (id, space_id, subject, predicate, object, valid_from, valid_to, "
                "source_document_id, weight, created_at) "
                "VALUES (?, ?, ?, 'cites', ?, ?, NULL, ?, 1.0, ?)",
                (
                    new_edge_id(),
                    self._space_id,
                    title,
                    fn["source"],
                    now.isoformat(),
                    doc_id,
                    now.isoformat(),
                ),
            )

        # 3. sources[] → derived-from edges (and document_sources rows)
        sources = frontmatter.get("sources", []) or []
        if isinstance(sources, str):
            sources = [sources]
        for vid in sources:
            await self._db.execute(
                "INSERT INTO document_sources (document_id, verbat_id) VALUES (?, ?)",
                (doc_id, vid),
            )
            await self._db.execute(
                "INSERT INTO edges (id, space_id, subject, predicate, object, valid_from, valid_to, "
                "source_document_id, source_verbat_id, weight, created_at) "
                "VALUES (?, ?, ?, 'derived-from', ?, ?, NULL, ?, ?, 1.0, ?)",
                (
                    new_edge_id(),
                    self._space_id,
                    title,
                    vid,
                    now.isoformat(),
                    doc_id,
                    vid,
                    now.isoformat(),
                ),
            )

        await self._db.commit()

    # ===================================================================
    # Cross-cutting: vector store (lazy LanceDB)
    # ===================================================================
    async def _make_vector_store(self):
        from derisk_ext.knowledge.vaultfs.vector_lancedb import LanceVectorStore

        return LanceVectorStore(self._root / ".ks" / "vectors.lance")

    # ===================================================================
    # Cross-cutting: writer lock (flock)
    # ===================================================================
    async def _acquire_distributed_lock(self, timeout: int) -> int:
        """Acquire flock on a dup'd fd. Returns the fd handle.

        Caller (BaseVaultFS.acquire_write_lock) wraps this with the
        in-process asyncio.Lock and releases via
        `_release_distributed_lock(fd)`.
        """
        dup_fd = os.dup(self._lock_fd)
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(dup_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return dup_fd
            except BlockingIOError:
                if time.time() >= deadline:
                    os.close(dup_fd)
                    raise TimeoutError(
                        f"Could not acquire flock for space {self._space_id} "
                        f"within {timeout}s"
                    )
                await asyncio.sleep(0.1)

    async def _release_distributed_lock(self, handle: Any) -> None:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            try:
                os.close(handle)
            except OSError:
                pass

    # ===================================================================
    # Cross-cutting: filesystem watcher (LocalVaultFS-specific)
    # ===================================================================
    async def watch_changes(
        self, callback: Callable[[ChangeEvent], None]
    ) -> LocalWatcher:
        try:
            from watchfiles import awatch
        except ImportError:
            logger.warning(
                "watchfiles not installed; filesystem watcher disabled"
            )
            return LocalWatcher(stop_fn=lambda: None)

        async def _watch():
            async for changes in awatch(self._root / "raw", self._root / "wiki"):
                for change_type, path in changes:
                    rel = os.path.relpath(path, self._root)
                    layer = "L0" if rel.startswith("raw/") else "L1"
                    op_map = {
                        "added": "create",
                        "modified": "update",
                        "deleted": "delete",
                    }
                    op = op_map.get(change_type.name.lower(), "update")
                    await callback(
                        ChangeEvent(
                            space_id=self._space_id,
                            layer=layer,
                            op=op,
                            id=rel,
                            path=rel,
                        )
                    )

        task = asyncio.create_task(_watch())
        self._watcher_task = task
        return LocalWatcher(stop_fn=task.cancel)

    # ===================================================================
    # Rebuild helpers
    # ===================================================================
    async def _chunks_clear_all(self) -> None:
        await self._db.execute("DELETE FROM document_chunks")
        await self._db.commit()

    async def _edges_invalidate_all(self, now_iso: str) -> None:
        await self._db.execute(
            "UPDATE edges SET valid_to=? WHERE space_id=? AND valid_to IS NULL",
            (now_iso, self._space_id),
        )
        await self._db.commit()

    # ===================================================================
    # Embedder identity
    # ===================================================================
    async def _embedder_identity_get(self) -> Optional[EmbedderIdentity]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM embedder_identity WHERE space_id=?",
            (self._space_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return EmbedderIdentity(
            space_id=self._space_id,
            model_name=r["model_name"],
            dimension=r["dimension"],
            state=EmbedderState(r["state"]),
            updated_at=parse_dt(r["updated_at"]),
        )

    async def _embedder_identity_upsert(
        self, model_name: str, dimension: int, state: EmbedderState, now: datetime
    ) -> None:
        # Upsert: INSERT OR REPLACE for first-time; UPDATE for swap
        existing = await self._db.execute_fetchall(
            "SELECT space_id FROM embedder_identity WHERE space_id=?",
            (self._space_id,),
        )
        if existing:
            await self._db.execute(
                "UPDATE embedder_identity SET model_name=?, dimension=?, state=?, updated_at=? "
                "WHERE space_id=?",
                (
                    model_name,
                    dimension,
                    state.value,
                    now.isoformat(),
                    self._space_id,
                ),
            )
        else:
            await self._db.execute(
                "INSERT INTO embedder_identity (space_id, model_name, dimension, state, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._space_id, model_name, dimension, state.value, now.isoformat()),
            )
        await self._db.commit()

    async def _embedder_identity_update_state(
        self, state: EmbedderState, now: datetime
    ) -> None:
        await self._db.execute(
            "UPDATE embedder_identity SET state=?, updated_at=? WHERE space_id=?",
            (state.value, now.isoformat(), self._space_id),
        )
        await self._db.commit()

    # ===================================================================
    # SQLite-specific row mappers
    # ===================================================================
    def _row_to_verbat(self, r: aiosqlite.Row) -> Verbat:
        if r["content"] is not None:
            content = r["content"]
        elif r["content_ref"]:
            content = (self._root / r["content_ref"]).read_text(encoding="utf-8")
        else:
            content = ""

        return Verbat(
            id=r["id"],
            space_id=r["space_id"],
            source_file=r["source_file"],
            source_path=r["source_path"],
            content=content,
            content_hash=r["content_hash"],
            extract_mode=ExtractMode(r["extract_mode"]),
            content_date=parse_dt(r["content_date"]) if r["content_date"] else None,
            filed_at=parse_dt(r["filed_at"]),
            source_mtime=r["source_mtime"],
            normalize_version=r["normalize_version"],
            deprecated=bool(r["deprecated"]),
        )

    def _row_to_edge(self, r: aiosqlite.Row) -> Edge:
        return Edge(
            id=r["id"],
            space_id=r["space_id"],
            subject=r["subject"],
            predicate=r["predicate"],
            object=r["object"],
            valid_from=parse_dt(r["valid_from"]) if r["valid_from"] else None,
            valid_to=parse_dt(r["valid_to"]) if r["valid_to"] else None,
            source_document_id=r["source_document_id"],
            source_verbat_id=r["source_verbat_id"],
            weight=r["weight"],
            created_at=parse_dt(r["created_at"]) if r["created_at"] else None,
        )


# Re-export for backwards compatibility (existing imports reference
# `from .local import EmbedderMismatchError`).
__all__ = ["LocalVaultFS", "LocalWriteLock", "LocalSubscription", "EmbedderMismatchError"]
