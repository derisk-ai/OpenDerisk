"""Memory store implementations."""

# SimpleSQLiteMemoryStore - always available (no external dependencies).
# This is the default short-term memory backend. Long-term plan is to
# route agent conversation fragments as L0 verbats with
# extract_mode="convo" into a designated knowledge space (RFC 001 §3.3).
from derisk_ext.storage.memory.simple_sqlite_store import (  # noqa: F401
    SimpleSQLiteMemoryConfig,
    SimpleSQLiteMemoryStore,
)

# KnowledgeVaultMemoryStore - routes the hermes 4-tier memory pipeline
# into a per-agent llm-wiki Space (L0 Verbat / L1 Document / L2 Edge).
from derisk_ext.storage.memory.knowledge_vault_store import (  # noqa: F401
    KnowledgeVaultMemoryConfig,
    KnowledgeVaultMemoryStore,
)

# LettaMemoryStore - requires Letta backend
try:
    from derisk_ext.storage.memory.letta_adapter import (  # noqa: F401
        LettaMemoryStore,
        LettaMemoryConfig,
    )
except ImportError:
    LettaMemoryStore = None  # type: ignore
    LettaMemoryConfig = None  # type: ignore

__all__ = [
    "SimpleSQLiteMemoryConfig",
    "SimpleSQLiteMemoryStore",
    "KnowledgeVaultMemoryConfig",
    "KnowledgeVaultMemoryStore",
    "LettaMemoryStore",
    "LettaMemoryConfig",
]
