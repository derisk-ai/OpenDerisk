"""Simple SQLite-based Memory Store.

A lightweight MemoryStore implementation that uses SQLite for storage
and simple text matching for search. Does not require external
dependencies like vector databases. This is the default short-term
memory backend.

Useful for:
- Development and testing
- Simple deployments without vector infrastructure
"""

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from derisk.storage.memory.base import (
    KGTriple,
    MemoryEntry,
    MemoryStoreBase,
    MemoryStoreConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class SimpleSQLiteMemoryConfig(MemoryStoreConfig):
    """Configuration for SimpleSQLiteMemoryStore."""

    __type__ = "simple_sqlite"

    db_path: str = ""
    enable_kg: bool = True

    def create_store(self, embedding_fn=None, **kwargs) -> "SimpleSQLiteMemoryStore":
        """Create a new SimpleSQLiteMemoryStore instance."""
        return SimpleSQLiteMemoryStore(config=self, embedding_fn=embedding_fn, **kwargs)


class SimpleSQLiteMemoryStore(MemoryStoreBase):
    """SQLite-based memory store with simple text search.

    Features:
    - No external dependencies (uses built-in sqlite3)
    - Simple text search using LIKE and word matching
    - Optional knowledge graph support (stored in SQLite)
    - Per-space isolation via separate database files
    """

    def __init__(
        self,
        config: SimpleSQLiteMemoryConfig,
        embedding_fn=None,
        index_name: str = None,
        **kwargs
    ):
        """Initialize the SQLite memory store."""
        super().__init__()
        self._config = config
        self._embedding_fn = embedding_fn
        self._index_name = index_name or "default"

        # Determine database path
        if config.db_path:
            self._db_path = config.db_path
        else:
            # Use default path under data directory
            data_dir = Path(os.getcwd()) / "data" / "memory"
            data_dir.mkdir(parents=True, exist_ok=True)
            self._db_path = str(data_dir / f"{self._index_name}.db")

        logger.info(f"[SimpleSQLiteMemoryStore] Using database: {self._db_path}")

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database tables."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        # Memory entries table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                wing TEXT NOT NULL,
                room TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_wing_room
            ON memories(wing, room)
        """)

        # Knowledge graph triples table
        if self._config.enable_kg:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kg_triples (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    valid_from TEXT,
                    valid_to TEXT,
                    confidence REAL,
                    source TEXT,
                    created_at TEXT
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_kg_subject
                ON kg_triples(subject)
            """)

        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # MemoryStoreBase abstract methods
    # ------------------------------------------------------------------

    def get_config(self) -> MemoryStoreConfig:
        """Return the config that created this store."""
        return self._config

    def write_memory(
        self,
        content: str,
        wing: str,
        room: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Write a single memory entry."""
        memory_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO memories (id, content, wing, room, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            memory_id,
            content,
            wing,
            room,
            json.dumps(metadata or {}),
            now,
            now
        ))

        conn.commit()
        conn.close()

        logger.info(f"[SimpleSQLiteMemoryStore] Written memory {memory_id} to {wing}/{room}")

        return MemoryEntry(
            id=memory_id,
            content=content,
            wing=wing,
            room=room,
            metadata=metadata or {},
            created_at=now
        )

    async def awrite_memory(
        self,
        content: str,
        wing: str,
        room: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Async write - calls sync version."""
        return self.write_memory(content, wing, room, metadata)

    def search_memory(
        self,
        query: str,
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        max_distance: float = 0.4,
    ) -> List[MemoryEntry]:
        """Search memories using simple text matching.

        Note: This is a simple implementation using LIKE and word matching.
        For production use with vector search, route agent conversation
        fragments as L0 verbats (extract_mode="convo") into a knowledge
        space — see RFC 001 §3.3.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Build query with filters
        sql = "SELECT * FROM memories WHERE content LIKE ?"
        params = [f"%{query}%"]

        if wing:
            sql += " AND wing = ?"
            params.append(wing)

        if room:
            sql += " AND room = ?"
            params.append(room)

        sql += f" ORDER BY created_at DESC LIMIT {top_k}"

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            # Calculate a simple "score" based on word overlap
            query_words = set(query.lower().split())
            content_words = set(row["content"].lower().split())
            overlap = len(query_words & content_words)
            score = overlap / max(len(query_words), 1) if query_words else 0.0

            results.append(MemoryEntry(
                id=row["id"],
                content=row["content"],
                wing=row["wing"],
                room=row["room"],
                metadata=json.loads(row["metadata"] or "{}"),
                score=score,
                created_at=row["created_at"]
            ))

        conn.close()
        return results

    async def asearch_memory(
        self,
        query: str,
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        max_distance: float = 0.4,
    ) -> List[MemoryEntry]:
        """Async search - calls sync version."""
        return self.search_memory(query, top_k, wing, room, max_distance)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a single memory entry by id."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return deleted

    async def adelete_memory(self, memory_id: str) -> bool:
        """Async delete - calls sync version."""
        return self.delete_memory(memory_id)

    # --- Knowledge graph methods ---

    def kg_add(
        self,
        subject: str,
        predicate: str,
        object_: str,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
    ) -> str:
        """Add a knowledge graph triple."""
        if not self._config.enable_kg:
            logger.warning("[SimpleSQLiteMemoryStore] KG is disabled")
            return ""

        triple_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO kg_triples
            (id, subject, predicate, object, valid_from, valid_to, confidence, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            triple_id,
            subject,
            predicate,
            object_,
            valid_from,
            valid_to,
            confidence,
            source,
            now
        ))

        conn.commit()
        conn.close()

        return triple_id

    async def akg_add(
        self,
        subject: str,
        predicate: str,
        object_: str,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
    ) -> str:
        """Async KG add - calls sync version."""
        return self.kg_add(subject, predicate, object_, valid_from, valid_to, confidence, source)

    def kg_query(
        self,
        entity: str,
        as_of: Optional[str] = None,
    ) -> List[KGTriple]:
        """Query knowledge graph triples for an entity."""
        if not self._config.enable_kg:
            return []

        conn = self._get_conn()
        cursor = conn.cursor()

        sql = "SELECT * FROM kg_triples WHERE subject = ?"
        params = [entity]

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append(KGTriple(
                subject=row["subject"],
                predicate=row["predicate"],
                object_=row["object"],
                valid_from=row["valid_from"],
                valid_to=row["valid_to"],
                confidence=row["confidence"],
                source=row["source"]
            ))

        conn.close()
        return results

    async def akg_query(
        self,
        entity: str,
        as_of: Optional[str] = None,
    ) -> List[KGTriple]:
        """Async KG query - calls sync version."""
        return self.kg_query(entity, as_of)

    # --- Management methods ---

    def kg_invalidate(self, triple_id: str) -> bool:
        """Invalidate (soft-delete) a knowledge graph triple."""
        if not self._config.enable_kg:
            return False

        conn = self._get_conn()
        cursor = conn.cursor()

        # Set valid_to to now to invalidate
        now = datetime.now().isoformat()
        cursor.execute(
            "UPDATE kg_triples SET valid_to = ? WHERE id = ? AND valid_to IS NULL",
            (now, triple_id)
        )
        invalidated = cursor.rowcount > 0

        conn.commit()
        conn.close()

        return invalidated

    async def akg_invalidate(self, triple_id: str) -> bool:
        """Async KG invalidate - calls sync version."""
        return self.kg_invalidate(triple_id)

    def import_documents(
        self,
        source_path: str,
        wing: Optional[str] = None,
    ) -> Dict[str, int]:
        """Bulk import documents / files into the memory store.

        Args:
            source_path: Path to a directory or file to import.
            wing: Optional wing name override.

        Returns:
            Dict with import statistics.
        """
        import os
        from pathlib import Path

        wing = wing or "documents"
        files_processed = 0
        entries_created = 0

        source = Path(source_path)
        if not source.exists():
            logger.warning(f"[SimpleSQLiteMemoryStore] Source path does not exist: {source_path}")
            return {"files_processed": 0, "entries_created": 0}

        if source.is_file():
            # Single file
            try:
                content = source.read_text(encoding="utf-8", errors="ignore")
                self.write_memory(
                    content=content,
                    wing=wing,
                    room=source.stem,
                    metadata={"source_file": str(source)}
                )
                files_processed = 1
                entries_created = 1
            except Exception as e:
                logger.warning(f"[SimpleSQLiteMemoryStore] Failed to read file {source}: {e}")
        elif source.is_dir():
            # Directory - process all files
            for file_path in source.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        self.write_memory(
                            content=content,
                            wing=wing,
                            room=file_path.stem,
                            metadata={"source_file": str(file_path)}
                        )
                        files_processed += 1
                        entries_created += 1
                    except Exception as e:
                        logger.warning(f"[SimpleSQLiteMemoryStore] Failed to read {file_path}: {e}")

        logger.info(
            f"[SimpleSQLiteMemoryStore] Imported {files_processed} files, "
            f"{entries_created} entries from {source_path}"
        )

        return {"files_processed": files_processed, "entries_created": entries_created}

    async def aimport_documents(
        self,
        source_path: str,
        wing: Optional[str] = None,
    ) -> Dict[str, int]:
        """Async import documents - calls sync version."""
        return self.import_documents(source_path, wing)

    def list_wings(self) -> List[Dict[str, Any]]:
        """List all wings with entry counts."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT wing, COUNT(*) as count
            FROM memories
            GROUP BY wing
            ORDER BY wing
        """)
        rows = cursor.fetchall()

        conn.close()
        return [{"name": row["wing"], "count": row["count"]} for row in rows]

    def list_rooms(self, wing: str) -> List[Dict[str, Any]]:
        """List rooms within a wing with entry counts."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT room, COUNT(*) as count
            FROM memories
            WHERE wing = ?
            GROUP BY room
            ORDER BY room
        """, (wing,))
        rows = cursor.fetchall()

        conn.close()
        return [{"name": row["room"], "count": row["count"]} for row in rows]

    def get_status(self) -> Dict[str, Any]:
        """Get memory store status."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Count memories
        cursor.execute("SELECT COUNT(*) as count FROM memories")
        memory_count = cursor.fetchone()["count"]

        # Count KG triples
        kg_count = 0
        if self._config.enable_kg:
            cursor.execute("SELECT COUNT(*) as count FROM kg_triples")
            kg_count = cursor.fetchone()["count"]

        conn.close()

        return {
            "total_entries": memory_count,
            "kg_triples": kg_count,
            "wings": self.list_wings(),
            "provider": "simple_sqlite",
            "db_path": self._db_path
        }

    # --- IndexStoreBase required methods (minimal implementation) ---

    def load_document(self, chunks: List[Any]) -> List[str]:
        """Load document chunks as memories."""
        ids = []
        for chunk in chunks:
            entry = self.write_memory(
                content=chunk.content if hasattr(chunk, "content") else str(chunk),
                wing="documents",
                room="imported",
                metadata={"source": chunk.metadata if hasattr(chunk, "metadata") else {}}
            )
            ids.append(entry.id)
        return ids

    async def aload_document(self, chunks: List[Any]) -> List[str]:
        """Async load document."""
        return self.load_document(chunks)

    def similar_search_with_scores(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Any] = None,
    ) -> List[Tuple[Any, float]]:
        """Similar search with scores - delegates to search_memory."""
        results = self.search_memory(query, top_k)
        return [(MemoryEntry(
            id=r.id,
            content=r.content,
            wing=r.wing,
            room=r.room,
            metadata=r.metadata,
            created_at=r.created_at
        ), r.score or 0.0) for r in results]

    def delete_by_ids(self, ids: List[str]) -> int:
        """Delete memories by IDs."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM memories WHERE id IN ({})".format(
                ",".join("?" * len(ids))
            ),
            ids
        )
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        return deleted

    def truncate(self) -> int:
        """Truncate all memories."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM memories")
        count = cursor.fetchone()["count"]

        cursor.execute("DELETE FROM memories")
        if self._config.enable_kg:
            cursor.execute("DELETE FROM kg_triples")

        conn.commit()
        conn.close()

        return count

    def delete_vector_name(self, vector_name: str) -> int:
        """Delete by wing name (treating vector_name as wing)."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM memories WHERE wing = ?", (vector_name,))
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        return deleted


# Register as fallback provider
def get_simple_sqlite_config():
    """Get SimpleSQLiteMemoryConfig for registration."""
    return SimpleSQLiteMemoryConfig