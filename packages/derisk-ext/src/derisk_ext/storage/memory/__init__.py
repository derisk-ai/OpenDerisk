"""Memory store implementations."""

# SimpleSQLiteMemoryStore - always available (no external dependencies)
from derisk_ext.storage.memory.simple_sqlite_store import (  # noqa: F401
    SimpleSQLiteMemoryConfig,
    SimpleSQLiteMemoryStore,
)

# MemPalaceMemoryStore - requires mempalace>=3.3.0
try:
    from derisk_ext.storage.memory.mempalace_store import (  # noqa: F401
        MemPalaceMemoryConfig,
        MemPalaceMemoryStore,
    )
except ImportError:
    # MemPalace not installed, will use SimpleSQLite fallback
    MemPalaceMemoryConfig = None  # type: ignore
    MemPalaceMemoryStore = None  # type: ignore

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
    "MemPalaceMemoryConfig",
    "MemPalaceMemoryStore",
    "LettaMemoryStore",
    "LettaMemoryConfig",
]