"""Knowledge Serve module configuration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from derisk.util.i18n_utils import _
from derisk_serve.core import BaseServeConfig

APP_NAME = "knowledge"
SERVE_APP_NAME = "derisk_serve_knowledge"
SERVE_APP_NAME_HUMP = "derisk_serve_Knowledge"
SERVE_CONFIG_KEY_PREFIX = "derisk.serve.knowledge."
SERVE_SERVICE_COMPONENT_NAME = f"{SERVE_APP_NAME}_service"


# Allowed vector store backends for DistributedVaultFS.
SUPPORTED_VECTOR_STORES = ("pgvector", "milvus", "chroma", "lance")


@dataclass
class DistributedConfig:
    """Configuration for DistributedVaultFS (S3 + SQL + pluggable vector store).

    Quick start: set `enabled = true` and pick a `vector_store_type`. The
    relational DSN is auto-derived from `[service.web.database]` (sync
    driver auto-translated to async — `mysql+pymysql` → `mysql+asyncmy`,
    `postgresql+psycopg2` → `postgresql+asyncpg`). MySQL or Postgres
    required; SQLite is local-only and cannot serve distributed mode.

    Vector store is pluggable. Pick one via `vector_store_type`:

    - **`pgvector`** (default): uses Postgres+pgvector extension.
      `vector_dsn` empty = reuse relational DSN (single-DB mode, requires
      Postgres). Set `vector_dsn` explicitly for split mode
      (e.g. MySQL relational + Postgres pgvector).
    - **`milvus`**: uses a Milvus cluster. Configure `milvus_uri`.
    - **`chroma`**: uses a Chroma server. Configure `chroma_uri`
      (server mode required for distributed; embedded local mode
      would race across processes).
    - **`lance`**: uses LanceDB with S3 backing (so multiple processes
      share the same vector set). Configure `lance_s3_uri`.

    S3 bucket for blobs defaults to `ServeConfig.uploads_bucket`. Override
    only when distributed spaces need a separate bucket. `s3_storage_type`
    defaults to `FileStorageClient`'s configured default
    (set via `[[serves.backends]]` TOML).
    """

    enabled: bool = field(default=False)

    # ---- Vector store selection ----
    vector_store_type: str = field(
        default="pgvector",
        metadata={
            "help": _(
                "Vector store type: pgvector | milvus | chroma | lance"
            ),
            "valid_values": list(SUPPORTED_VECTOR_STORES),
        },
    )

    # ---- pgvector-specific ----
    vector_dsn: str = field(
        default="",
        metadata={
            "help": _(
                "Postgres DSN for pgvector. Empty = reuse relational DSN "
                "(single-DB mode, requires Postgres+pgvector)."
            )
        },
    )

    # ---- milvus-specific ----
    milvus_uri: str = field(
        default="",
        metadata={"help": _("Milvus connection URI, e.g. localhost:19530")},
    )
    milvus_collection_prefix: str = field(
        default="ks_",
        metadata={"help": _("Prefix for Milvus collection names per space")},
    )

    # ---- chroma-specific ----
    chroma_uri: str = field(
        default="",
        metadata={
            "help": _(
                "Chroma server URI, e.g. http://localhost:8000. "
                "Required when vector_store_type='chroma' (embedded local "
                "mode is unsafe for distributed — multiple processes race)."
            )
        },
    )

    # ---- lance-specific (S3 backing for multi-process sharing) ----
    lance_s3_uri: str = field(
        default="",
        metadata={
            "help": _(
                "S3 URI for LanceDB backing, e.g. s3://bucket/knowledge-vectors. "
                "Required when vector_store_type='lance'."
            )
        },
    )

    # ---- S3 file storage (raw + wiki blobs) ----
    s3_bucket: str = field(
        default="",
        metadata={
            "help": _(
                "S3 bucket for raw + wiki blobs. Empty = reuse uploads_bucket."
            )
        },
    )
    s3_storage_type: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "FileStorageClient storage type (s3, oss, minio, ...). "
                "Empty = use FileStorageClient's configured default."
            )
        },
    )


@dataclass
class ServeConfig(BaseServeConfig):
    """Knowledge serve configuration."""

    __type__ = APP_NAME

    local_root: Optional[str] = field(
        default="~/.derisk/spaces",
        metadata={"help": _("Root directory for local-mode knowledge spaces")},
    )
    default_backend: Optional[str] = field(
        default="local",
        metadata={"help": _("Default VaultFS backend for new spaces")},
    )
    api_keys: Optional[str] = field(
        default=None,
        metadata={"help": _("Comma-separated API keys; empty = no auth")},
    )
    # v2 ingest pipeline fallbacks (RFC 004 §6). Per-space config takes
    # precedence; these are used when a space doesn't set its own.
    default_llm_model: Optional[str] = field(
        default=None,
        metadata={"help": _("Fallback LLM model for wiki generation")},
    )
    default_agent_id: Optional[str] = field(
        default=None,
        metadata={"help": _("Fallback default agent id for ingest")},
    )
    default_embedder_model: Optional[str] = field(
        default=None,
        metadata={
            "help": _(
                "Fallback embedder model name for spaces without embedder_model "
                "set. Lazy-provisions embedder_identity on first vector op. "
                "Empty = vector ops disabled (FTS still works)."
            )
        },
    )
    uploads_bucket: Optional[str] = field(
        default="knowledge-uploads",
        metadata={"help": _("Bucket name for raw uploaded files (FileStorageClient)")},
    )
    distributed: DistributedConfig = field(
        default_factory=DistributedConfig,
        metadata={"help": _("DistributedVaultFS configuration (S3 + SQL + pluggable vector store)")},
    )


__all__ = [
    "APP_NAME",
    "SERVE_APP_NAME",
    "SERVE_APP_NAME_HUMP",
    "SERVE_CONFIG_KEY_PREFIX",
    "SERVE_SERVICE_COMPONENT_NAME",
    "ServeConfig",
    "DistributedConfig",
    "SUPPORTED_VECTOR_STORES",
]
