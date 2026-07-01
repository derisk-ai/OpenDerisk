"""Knowledge-vault backed MemoryStore adapter.

Routes the hermes 4-tier memory pipeline into a per-agent llm-wiki Space:

    tier1 (turn)    -> L0 Verbat (extract_mode=convo), bypasses LLM extract
    tier2 (reflect) -> L1 Document (type=memory|insight) + derived-from edge
    tier3 (curate)  -> L1 doc merge + merged-into/supersedes edges
    tier0 (prefetch)-> doc_search (hybrid) + verbat_search

The MemoryStoreBase sync abstract methods are stubbed — the memory hook
pipeline only calls the async wrappers (awrite_memory / asearch_memory /
akg_add), which we override to call vault async methods directly.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from derisk.knowledge.types import (
    Edge,
    ExtractMode,
    Verbat,
    new_doc_id,
    new_edge_id,
)
from derisk.storage.memory.base import (
    KGTriple,
    MemoryEntry,
    MemoryStoreBase,
    MemoryStoreConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeVaultMemoryConfig(MemoryStoreConfig):
    """Config for KnowledgeVaultMemoryStore.

    `space_slug` is the llm-wiki Space slug (typically `memory-{app_code}`).
    The vault instance is supplied at construction time by the caller
    (agent_chat.py), who resolves it via KnowledgeService.get_vault(slug).
    """

    __type__ = "knowledge_vault"

    space_slug: str = ""
    enable_kg: bool = True

    def create_store(self, **kwargs) -> "KnowledgeVaultMemoryStore":
        vault = kwargs.get("vault")
        if vault is None:
            raise ValueError(
                "KnowledgeVaultMemoryConfig.create_store requires `vault` kwarg"
            )
        return KnowledgeVaultMemoryStore(
            config=self,
            vault=vault,
            system_app=kwargs.get("system_app"),
        )


class KnowledgeVaultMemoryStore(MemoryStoreBase):
    """MemoryStoreBase adapter backed by a BaseVaultFS instance.

    One store == one Space == one agent's memory. The vault is owned by
    KnowledgeService; this class only holds a reference for the lifetime
    of the agent's memory bundle.
    """

    def __init__(
        self,
        config: KnowledgeVaultMemoryConfig,
        vault: Any,
        system_app: Any = None,
    ):
        super().__init__()
        self._config = config
        self._vault = vault
        self._system_app = system_app
        self._space_id = vault.space_id

    # ------------------------------------------------------------------
    # Public helpers (used by longterm_manager tier2/tier3)
    # ------------------------------------------------------------------

    @property
    def vault(self) -> Any:
        return self._vault

    @property
    def space_slug(self) -> str:
        return self._config.space_slug

    async def write_doc(
        self,
        path: str,
        content: str,
        frontmatter: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Write an L1 Document directly (tier2 reflect path).

        Returns the doc_id. Caller is responsible for ensuring frontmatter
        `type` is declared in the space's schema.md.

        Content is threat-scanned before write — prompt-injection / exfil /
        invisible-unicode payloads are rejected with ValueError.
        """
        from derisk.storage.memory.threat_scanner import scan_memory_content
        is_safe, reasons = scan_memory_content(content)
        if not is_safe:
            logger.warning(
                "[KnowledgeVaultMemory] write_doc rejected threat: slug=%s path=%s reasons=%s",
                self._config.space_slug, path, reasons,
            )
            raise ValueError(
                f"Memory content rejected by threat scanner: {reasons}"
            )
        doc_id = await self._vault.doc_create(path, content, frontmatter)
        logger.info(
            "[KnowledgeVaultMemory] doc_create slug=%s path=%s doc_id=%s",
            self._config.space_slug, path, doc_id,
        )
        return doc_id

    async def curate_merge(
        self,
        source_paths: List[str],
        target_path: str,
        merged_content: str,
        frontmatter: Optional[Dict[str, Any]] = None,
    ) -> str:
        """tier3 curate: merge source docs into a new target doc.

        - Creates target L1 Document with merged content
        - For each source: marks deprecated (via doc_delete — L1 has no
          soft-deprecate; history is preserved through edges) and adds
          `merged-into` (source -> target) + `supersedes` (target -> source)
          edges with valid_from=now

        merged_content is threat-scanned before write.
        """
        from derisk.storage.memory.threat_scanner import scan_memory_content
        is_safe, reasons = scan_memory_content(merged_content)
        if not is_safe:
            logger.warning(
                "[KnowledgeVaultMemory] curate_merge rejected threat: slug=%s target=%s reasons=%s",
                self._config.space_slug, target_path, reasons,
            )
            raise ValueError(
                f"Memory content rejected by threat scanner: {reasons}"
            )
        target_doc_id = await self._vault.doc_create(
            target_path, merged_content, frontmatter
        )
        now = datetime.utcnow()
        for src in source_paths:
            try:
                # L1 doc_delete refuses protected files; memory docs aren't
                # protected. History preserved via edges + L0 verbats remain.
                await self._vault.doc_delete(src)
            except Exception as e:
                logger.warning(
                    "[KnowledgeVaultMemory] curate_merge: doc_delete %s failed: %s",
                    src, e,
                )
            src_entity = f"doc:{src}"
            tgt_entity = f"doc:{target_path}"
            try:
                await self._vault.edge_add(Edge(
                    id=new_edge_id(),
                    space_id=self._space_id,
                    subject=src_entity,
                    predicate="merged-into",
                    object=tgt_entity,
                    valid_from=now,
                    source_document_id=target_doc_id,
                ))
                await self._vault.edge_add(Edge(
                    id=new_edge_id(),
                    space_id=self._space_id,
                    subject=tgt_entity,
                    predicate="supersedes",
                    object=src_entity,
                    valid_from=now,
                    source_document_id=target_doc_id,
                ))
            except Exception as e:
                logger.warning(
                    "[KnowledgeVaultMemory] curate_merge: edge_add failed: %s", e
                )
        logger.info(
            "[KnowledgeVaultMemory] curate_merge slug=%s sources=%d target=%s",
            self._config.space_slug, len(source_paths), target_path,
        )
        return target_doc_id

    # ------------------------------------------------------------------
    # Async wrappers (override base — vault is async-native)
    # ------------------------------------------------------------------

    async def awrite_memory(
        self,
        content: str,
        wing: str,
        room: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """Route memory write by tier:

        - tier1 (metadata.tier==1): L0 Verbat, extract_mode=convo, no LLM
        - tier2 (metadata.tier==2): L1 Document via write_doc (caller
          should set metadata['doc_path'] and metadata['frontmatter'])
        - other: fall back to L0 Verbat (treat as raw evidence)
        """
        meta = metadata or {}
        tier = meta.get("tier")
        now = datetime.utcnow()

        if tier == 2 and meta.get("doc_path"):
            doc_path = meta["doc_path"]
            frontmatter = meta.get("frontmatter") or {
                "type": "memory",
                "title": (content[:40] + "...") if len(content) > 40 else content,
                "created": now.isoformat(),
                "updated": now.isoformat(),
            }
            doc_id = await self.write_doc(doc_path, content, frontmatter)
            return MemoryEntry(
                id=doc_id,
                content=content,
                wing=wing,
                room=room,
                metadata={**meta, "layer": "L1", "doc_path": doc_path},
                created_at=now.isoformat(),
            )

        # tier1 or fallback: L0 Verbat
        conv_id = meta.get("conv_id", "unknown")
        round_no = meta.get("round", 0)
        source_file = f"{conv_id}_{round_no}.txt" if tier == 1 else f"{conv_id}.txt"
        # 记忆元数据：提问人 + 时间 + 来源会话，承载时间线和归属信息
        verbat_meta = {
            "author": meta.get("user_name"),
            "user_id": meta.get("user_id"),
            "conv_id": conv_id,
            "turn_round": round_no,
            "tier": tier,
            "wing": wing,
            "room": room,
        }
        verbat_meta = {k: v for k, v in verbat_meta.items() if v is not None}
        verbat = Verbat.create(
            space_id=self._space_id,
            content=content,
            source_file=source_file,
            extract_mode=ExtractMode.CONVO,
            content_date=now,
            metadata=verbat_meta,
        )
        vid = await self._vault.verbat_add(verbat)
        return MemoryEntry(
            id=vid,
            content=content,
            wing=wing,
            room=room,
            metadata={**meta, "layer": "L0", "verbat_id": vid},
            created_at=now.isoformat(),
        )

    async def asearch_memory(
        self,
        query: str,
        top_k: int = 5,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        max_distance: float = 0.4,
    ) -> List[MemoryEntry]:
        """Hybrid search: L1 doc_search + L0 verbat_search, merged by score."""
        entries: List[MemoryEntry] = []
        try:
            doc_hits = await self._vault.doc_search(
                query=query, mode="hybrid", limit=top_k
            )
            for h in doc_hits:
                entries.append(MemoryEntry(
                    id=h.document_id,
                    content=h.snippet,
                    wing=wing or "default",
                    room="L1",
                    metadata={
                        "layer": "L1",
                        "path": h.path,
                        "title": h.title,
                        "type": h.type,
                    },
                    score=h.score,
                ))
        except Exception as e:
            logger.warning(
                "[KnowledgeVaultMemory] doc_search failed: %s", e
            )

        try:
            verbat_hits = await self._vault.verbat_search(
                query=query, limit=top_k
            )
            for h in verbat_hits:
                entries.append(MemoryEntry(
                    id=h.verbat_id,
                    content=h.snippet,
                    wing=wing or "default",
                    room="L0",
                    metadata={
                        "layer": "L0",
                        "verbat_id": h.verbat_id,
                        "source_file": h.source_file,
                        "extract_mode": str(h.extract_mode),
                    },
                    score=h.score,
                ))
        except Exception as e:
            logger.warning(
                "[KnowledgeVaultMemory] verbat_search failed: %s", e
            )

        entries.sort(key=lambda e: e.score or 0.0, reverse=True)
        return entries[:top_k]

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
        edge = Edge(
            id=new_edge_id(),
            space_id=self._space_id,
            subject=subject,
            predicate=predicate,
            object=object_,
            valid_from=_parse_dt(valid_from) or datetime.utcnow(),
            valid_to=_parse_dt(valid_to),
            weight=confidence if confidence is not None else 1.0,
        )
        eid = await self._vault.edge_add(edge)
        return eid

    async def akg_query(
        self,
        entity: str,
        as_of: Optional[str] = None,
    ) -> List[KGTriple]:
        as_of_dt = _parse_dt(as_of)
        subgraph = await self._vault.graph_query(
            entity=entity, hop=1, include_invalid=False
        )
        triples: List[KGTriple] = []
        for e in subgraph.edges:
            if as_of_dt is not None:
                if e.valid_from and e.valid_from > as_of_dt:
                    continue
                if e.valid_to and e.valid_to <= as_of_dt:
                    continue
            triples.append(KGTriple(
                subject=e.subject,
                predicate=e.predicate,
                object_=e.object,
                valid_from=e.valid_from.isoformat() if e.valid_from else None,
                valid_to=e.valid_to.isoformat() if e.valid_to else None,
                confidence=e.weight,
                source=e.source_document_id,
            ))
        return triples

    async def adelete_memory(self, memory_id: str) -> bool:
        """Soft-delete a verbat by id (L0). L1 docs are deleted via curate_merge."""
        try:
            await self._vault.verbat_deprecate(memory_id)
            return True
        except Exception as e:
            logger.warning(
                "[KnowledgeVaultMemory] verbat_deprecate %s failed: %s",
                memory_id, e,
            )
            return False

    async def akg_invalidate(self, triple_id: str) -> bool:
        try:
            await self._vault.edge_invalidate(eid=triple_id)
            return True
        except Exception as e:
            logger.warning(
                "[KnowledgeVaultMemory] edge_invalidate %s failed: %s",
                triple_id, e,
            )
            return False

    # ------------------------------------------------------------------
    # Sync abstract methods — NOT on the memory hook hot path.
    # The pipeline only uses the async wrappers above. Stubs raise to
    # surface accidental misuse.
    # ------------------------------------------------------------------

    def get_config(self) -> MemoryStoreConfig:
        return self._config

    def write_memory(self, content, wing, room, metadata=None) -> MemoryEntry:
        raise NotImplementedError(
            "KnowledgeVaultMemoryStore is async-only; use awrite_memory"
        )

    def search_memory(self, query, top_k=5, wing=None, room=None, max_distance=0.4):
        raise NotImplementedError(
            "KnowledgeVaultMemoryStore is async-only; use asearch_memory"
        )

    def delete_memory(self, memory_id: str) -> bool:
        raise NotImplementedError(
            "KnowledgeVaultMemoryStore is async-only; use adelete_memory"
        )

    def kg_add(self, subject, predicate, object_, valid_from=None, valid_to=None,
               confidence=None, source=None) -> str:
        raise NotImplementedError(
            "KnowledgeVaultMemoryStore is async-only; use akg_add"
        )

    def kg_query(self, entity, as_of=None):
        raise NotImplementedError(
            "KnowledgeVaultMemoryStore is async-only; use akg_query"
        )

    def kg_invalidate(self, triple_id: str) -> bool:
        raise NotImplementedError(
            "KnowledgeVaultMemoryStore is async-only; use akg_invalidate"
        )

    def import_documents(self, source_path, wing=None) -> Dict[str, int]:
        raise NotImplementedError("Use KnowledgeService ingest pipeline directly")

    def list_wings(self) -> List[Dict[str, Any]]:
        return [{"name": self._config.space_slug, "count": -1}]

    def list_rooms(self, wing: str) -> List[Dict[str, Any]]:
        return [
            {"name": "L0", "count": -1},
            {"name": "L1", "count": -1},
        ]

    def get_status(self) -> Dict[str, Any]:
        return {
            "space_slug": self._config.space_slug,
            "space_id": self._space_id,
            "backend": "knowledge_vault",
        }

    # --- IndexStoreBase abstract stubs (not used by memory pipeline) ---

    def load_document(self, chunks):
        raise NotImplementedError

    async def aload_document(self, chunks):
        raise NotImplementedError

    def similar_search_with_scores(self, doc, topk, score_threshold=None, filters=None):
        raise NotImplementedError

    def delete_by_ids(self, ids):
        raise NotImplementedError

    def truncate(self):
        raise NotImplementedError

    def delete_vector_name(self, index_name):
        raise NotImplementedError


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


__all__ = [
    "KnowledgeVaultMemoryConfig",
    "KnowledgeVaultMemoryStore",
]
