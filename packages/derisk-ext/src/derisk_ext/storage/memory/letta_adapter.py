"""Letta memory provider adapter.

Borrows from Hermes-Agent's plugin architecture:
- Implements MemoryStoreBase interface for Letta backend
- Maps OpenDerisk concepts to Letta concepts:
  * wing="recall" → core_memory (editable state)
  * wing="archive" → archival_memory (semantic search)

This allows OpenDerisk to use Letta as a memory backend
while maintaining the same MemoryStoreBase interface.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from derisk.storage.memory.base import (
    KGTriple,
    MemoryEntry,
    MemoryStoreBase,
    MemoryStoreConfig,
)

logger = logging.getLogger(__name__)


def _require_letta():
    """Lazy-check that letta-client is installed."""
    try:
        import letta  # noqa: F401
        return True
    except ImportError:
        raise ImportError(
            "letta-client is required for LettaMemoryStore. "
            "Install it with: pip install letta-client"
        )


@dataclass
class LettaMemoryConfig(MemoryStoreConfig):
    """Configuration for the Letta memory provider.

    Set __type__ = "letta" so StorageManager can auto-discover this
    config via MemoryStoreConfig.__subclasses__().
    """

    __type__ = "letta"

    agent_id: str = field(
        metadata={"help": "Letta agent ID to use for memory operations."},
    )
    api_key: str = field(
        default="",
        metadata={"help": "Letta API key."},
    )
    base_url: str = field(
        default="http://localhost:8283",
        metadata={"help": "Letta server URL."},
    )
    default_wing: str = field(
        default="archive",
        metadata={"help": "Default wing: 'recall' for core_memory, 'archive' for archival."},
    )

    def create_store(self, **kwargs) -> "LettaMemoryStore":
        """Create a LettaMemoryStore from this config."""
        return LettaMemoryStore(config=self, **kwargs)


class LettaMemoryStore(MemoryStoreBase):
    """Letta backend adapter.

    Letta provides two memory layers:
    - core_memory: Editable, structured state (like working memory)
    - archival_memory: Semantic search over past conversations

    This adapter maps OpenDerisk's wing concept to Letta's layers:
    - wing="recall" → core_memory
    - wing="archive" (default) → archival_memory
    """

    def __init__(
        self,
        config: LettaMemoryConfig,
        name: Optional[str] = None,
        embedding_fn: Optional[Any] = None,
        executor: Optional[Any] = None,
    ):
        super().__init__(executor)
        self._config = config
        self._name = name
        self._default_wing = config.default_wing
        self._client = None

    def _get_client(self):
        """Lazy-initialize Letta client."""
        if self._client is None:
            _require_letta()
            from letta import LettaClient

            self._client = LettaClient(
                base_url=self._config.base_url,
                token=self._config.api_key,
            )
        return self._client

    # ------------------------------------------------------------------
    # MemoryStoreBase abstract methods
    # ------------------------------------------------------------------

    def write_memory(
        self,
        content: str,
        wing: str,
        room: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Write content to Letta memory.

        Maps wing to Letta concept:
        - "recall" → core_memory_append
        - "archive" → archival_memory_insert
        """
        client = self._get_client()
        agent_id = self._config.agent_id

        if wing == "recall":
            # Core memory is structured - format content
            formatted = f"[{room}] {content}"
            client.core_memory_append(agent_id, formatted)
        else:
            # Archival memory is unstructured
            client.archival_memory_insert(agent_id, content)

        return MemoryEntry(
            id="",  # Letta doesn't return IDs
            content=content,
            wing=wing,
            room=room,
            metadata=metadata or {},
        )

    def search_memory(
        self,
        query: str,
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        max_distance: float = 0.4,
    ) -> List[MemoryEntry]:
        """Search Letta memory.

        Maps wing to Letta concept:
        - "recall" → core_memory_get (no semantic search, local filtering)
        - "archive" → archival_memory_search (semantic)
        """
        client = self._get_client()
        agent_id = self._config.agent_id

        wing = wing or self._default_wing

        if wing == "recall":
            # Core memory: get all, then filter locally
            core_memory = client.core_memory_get(agent_id)
            content = core_memory.get("content", "")

            # Simple keyword matching for core memory
            entries = []
            query_lower = query.lower()
            for block in content.split("\n\n"):
                if query_lower in block.lower():
                    entries.append(
                        MemoryEntry(
                            id="",
                            content=block.strip(),
                            wing="recall",
                            room="core",
                            score=0.5,
                        )
                    )
            return entries[:top_k]

        else:
            # Archival memory: semantic search
            results = client.archival_memory_search(
                agent_id,
                query,
                count=top_k,
            )

            entries = []
            for r in results.get("results", []):
                entries.append(
                    MemoryEntry(
                        id=r.get("id", ""),
                        content=r.get("content", ""),
                        wing="archive",
                        room=r.get("metadata", {}).get("room", "general"),
                        score=r.get("score", 0.5),
                    )
                )
            return entries

    def delete_memory(self, memory_id: str) -> bool:
        """Delete from Letta memory.

        Letta doesn't support individual archival deletion directly,
        so this is limited.
        """
        logger.warning("Letta does not support individual memory deletion.")
        return False

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
        """Letta does not support knowledge graph."""
        raise NotImplementedError(
            "LettaMemoryStore does not support knowledge graph operations. "
            "Use a composite store with a separate KG backend."
        )

    def kg_query(
        self,
        entity: str,
        as_of: Optional[str] = None,
    ) -> List[KGTriple]:
        """Letta does not support knowledge graph."""
        raise NotImplementedError(
            "LettaMemoryStore does not support knowledge graph operations."
        )

    def kg_invalidate(self, triple_id: str) -> bool:
        """Letta does not support knowledge graph."""
        raise NotImplementedError(
            "LettaMemoryStore does not support knowledge graph operations."
        )

    def import_documents(
        self,
        source_path: str,
        wing: Optional[str] = None,
    ) -> Dict[str, int]:
        """Import documents to Letta archival memory.

        Reads file and inserts each line/paragraph as archival memory.
        """
        import os

        client = self._get_client()
        agent_id = self._config.agent_id

        if not os.path.exists(source_path):
            return {"files_processed": 0, "entries_created": 0}

        entries_created = 0
        try:
            with open(source_path, "r") as f:
                content = f.read()

            # Split by paragraphs and insert
            for paragraph in content.split("\n\n"):
                paragraph = paragraph.strip()
                if paragraph:
                    client.archival_memory_insert(agent_id, paragraph)
                    entries_created += 1

        except Exception as e:
            logger.warning(f"Failed to import documents: {e}")

        return {"files_processed": 1, "entries_created": entries_created}

    def list_wings(self) -> List[Dict[str, Any]]:
        """List memory wings (core and archival)."""
        return [
            {"name": "recall", "type": "core_memory", "count": 1},
            {"name": "archive", "type": "archival_memory", "count": -1},  # Unknown
        ]

    def list_rooms(self, wing: str) -> List[Dict[str, Any]]:
        """List rooms (not supported by Letta)."""
        logger.warning("Letta does not support rooms.")
        return []

    def get_status(self) -> Dict[str, Any]:
        """Get Letta memory status."""
        try:
            client = self._get_client()
            agent_state = client.get_agent(self._config.agent_id)

            return {
                "agent_id": self._config.agent_id,
                "agent_name": agent_state.get("name", ""),
                "core_memory": agent_state.get("memory", {}).get("core_memory", ""),
                "archival_memory_count": agent_state.get("archival_memory_count", 0),
            }
        except Exception as e:
            return {"error": str(e)}
