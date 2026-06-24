"""Knowledge Serve service — bridges HTTP API to VaultFS instances.

A single service instance manages all knowledge spaces in this process.
Spaces are loaded lazily on first access (per slug) and cached.

Backend selection (RFC 002 distributed variant):
- Local spaces (`backend="local"`): live under `<local_root>/<slug>/`,
  discovered by filesystem scan. Per-space config persisted in the
  space's own SQLite `spaces` row.
- Distributed spaces (`backend="distributed"`): live on S3 + SQL +
  pgvector. Tracked via a JSON registry file at `<local_root>/registry.json`
  so they're discoverable on restart (no local directory per space).

Per-space config (default_agent_id / llm_model / multimodal_model /
embedder_model) is persisted in each local space's vault.sqlite `spaces`
row. For distributed spaces, the config is stored in the relational DB's
`spaces` table (managed by SQLAlchemyRelationalStore).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from derisk.component import BaseComponent, SystemApp
from derisk.knowledge.types import Space, new_space_id

from derisk_ext.knowledge.extractors.registry_init import register_builtin_extractors
from derisk_ext.knowledge.resource import set_vault_factory
from derisk_ext.knowledge.vaultfs import DistributedVaultFS, LocalVaultFS

from ..config import SERVE_SERVICE_COMPONENT_NAME, SUPPORTED_VECTOR_STORES, ServeConfig
from ..ingest import IngestOrchestrator

logger = logging.getLogger(__name__)


# Sync → async driver translation map for SQLAlchemy URLs.
# The app's [service.web.database] config uses sync drivers (pymysql,
# psycopg2); distributed mode needs async (asyncmy, asyncpg) since
# SQLAlchemyRelationalStore uses create_async_engine.
_ASYNC_DRIVER_MAP = [
    ("mysql+mysqldb://", "mysql+asyncmy://"),
    ("mysql+pymysql://", "mysql+asyncmy://"),
    ("postgresql+psycopg2://", "postgresql+asyncpg://"),
    ("postgresql+psycopg://", "postgresql+asyncpg://"),
    ("postgresql://", "postgresql+asyncpg://"),
    ("sqlite:///", "sqlite+aiosqlite:///"),
]


def _translate_to_async_dsn(url: str) -> str:
    """Translate a sync SQLAlchemy URL to its async-driver equivalent.

    If the URL already uses an async driver or is unrecognized, returned
    unchanged.
    """
    for sync_prefix, async_prefix in _ASYNC_DRIVER_MAP:
        if url.startswith(sync_prefix):
            return async_prefix + url[len(sync_prefix):]
    return url


class Service(BaseComponent):
    """Knowledge serve service.

    Manages a registry of VaultFS instances keyed by space slug, plus
    per-space config persistence and the ingest orchestrator.
    """

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(self, system_app: SystemApp, serve_config: ServeConfig):
        # Initialize flags before super().__init__ — BaseComponent calls
        # init_app() during __init__, which references these attributes.
        self._extractors_registered = False
        super().__init__(system_app)
        self._serve_config = serve_config
        self._local_root = Path(serve_config.local_root or "~/.derisk/spaces").expanduser()
        self._vaults: Dict[str, Any] = {}  # slug → VaultFS (Local or Distributed)
        self._spaces: Dict[str, Space] = {}  # slug → Space config (cached)
        self._orchestrator: Optional[IngestOrchestrator] = None

    def init_app(self, system_app: SystemApp) -> None:
        """Called on init_app — register the vault factory so tools can resolve."""
        self._system_app = system_app
        set_vault_factory(self.get_vault)
        # Register built-in extractors once (idempotent).
        if not self._extractors_registered:
            try:
                register_builtin_extractors()
                self._extractors_registered = True
            except Exception as e:
                logger.warning("register_builtin_extractors failed: %s", e)

    @property
    def orchestrator(self) -> IngestOrchestrator:
        if self._orchestrator is None:
            self._orchestrator = IngestOrchestrator(self._system_app)
        return self._orchestrator

    # ------------------------------------------------------------------
    # Registry (JSON file for distributed spaces)
    # ------------------------------------------------------------------
    @property
    def _registry_path(self) -> Path:
        return self._local_root / "registry.json"

    def _load_registry(self) -> Dict[str, dict]:
        if not self._registry_path.exists():
            return {}
        try:
            return json.loads(self._registry_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load registry %s: %s", self._registry_path, e)
            return {}

    def _save_registry(self, data: Dict[str, dict]) -> None:
        self._local_root.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _registry_lookup(self, slug: str) -> Optional[dict]:
        return self._load_registry().get(slug)

    def _registry_upsert(self, slug: str, entry: dict) -> None:
        data = self._load_registry()
        data[slug] = entry
        self._save_registry(data)

    # ------------------------------------------------------------------
    # Vault construction
    # ------------------------------------------------------------------
    def _resolve_relational_dsn(self) -> str:
        """Derive an async SQLAlchemy DSN from `[service.web.database]`.

        Sync drivers are auto-translated to their async counterparts:
        - `mysql+pymysql` / `mysql+mysqldb` → `mysql+asyncmy`
        - `postgresql+psycopg2` / `postgresql` → `postgresql+asyncpg`
        - `sqlite` → `sqlite+aiosqlite` (rejected later — distributed mode
          needs a server DB)

        Raises RuntimeError if the app DB config is missing or SQLite
        (SQLite can't serve distributed mode: cross-process locks and
        pgvector both require a server DB).
        """
        try:
            from derisk_app.config import ApplicationConfig
        except ImportError as e:
            raise RuntimeError(
                "Cannot resolve service.web.database — derisk_app not available: "
                + str(e)
            )
        app_config = self._system_app.config.get_typed("app_config", ApplicationConfig)
        db_params = app_config.service.web.database
        if db_params is None:
            raise RuntimeError(
                "Distributed backend requires [service.web.database] to be "
                "configured with MySQL or Postgres."
            )

        db_type = getattr(db_params, "__type__", "")
        if db_type == "sqlite":
            raise RuntimeError(
                "Distributed backend does not support SQLite for "
                "[service.web.database]. Configure MySQL or Postgres "
                "(SQLite is local-only: no cross-process locks, no pgvector)."
            )

        sync_url = db_params.db_url()
        return _translate_to_async_dsn(sync_url)

    def _resolve_distributed_config(self) -> dict:
        """Resolve effective DistributedVaultFS config with quick-start defaults.

        - relational_dsn: from [service.web.database] (sync → async)
        - vector_store_config: dict shaped per chosen vector_store_type
          (pgvector / milvus / chroma / lance). pgvector defaults its dsn
          to the relational_dsn (single-DB mode) when vector_dsn is empty.
        - s3_bucket: from config, or reuse ServeConfig.uploads_bucket
        - s3_storage_type: from config, or None (use FileStorageClient default)
        """
        dcfg = self._serve_config.distributed
        if not dcfg.enabled:
            raise RuntimeError(
                "Distributed backend not enabled — set "
                "[knowledge.distributed] enabled=true in config"
            )

        relational_dsn = self._resolve_relational_dsn()
        vtype = dcfg.vector_store_type

        if vtype == "pgvector":
            dsn = dcfg.vector_dsn or relational_dsn
            if not dsn.startswith(("postgresql+asyncpg://", "postgresql://")):
                raise RuntimeError(
                    "pgvector requires a Postgres DSN. Either set "
                    "[service.web.database] type='postgresql', or provide "
                    "[knowledge.distributed] vector_dsn explicitly."
                )
            vector_store_config = {"type": "pgvector", "dsn": dsn}
        elif vtype == "milvus":
            if not dcfg.milvus_uri:
                raise RuntimeError(
                    "milvus requires [knowledge.distributed] milvus_uri "
                    "(e.g. localhost:19530)."
                )
            vector_store_config = {
                "type": "milvus",
                "uri": dcfg.milvus_uri,
                "collection_prefix": dcfg.milvus_collection_prefix,
            }
        elif vtype == "chroma":
            if not dcfg.chroma_uri:
                raise RuntimeError(
                    "chroma requires [knowledge.distributed] chroma_uri "
                    "(e.g. http://localhost:8000). Embedded local mode is "
                    "unsafe for distributed (multi-process races)."
                )
            vector_store_config = {"type": "chroma", "uri": dcfg.chroma_uri}
        elif vtype == "lance":
            if not dcfg.lance_s3_uri:
                raise RuntimeError(
                    "lance requires [knowledge.distributed] lance_s3_uri "
                    "(e.g. s3://bucket/knowledge-vectors)."
                )
            vector_store_config = {"type": "lance", "s3_uri": dcfg.lance_s3_uri}
        else:
            raise RuntimeError(
                f"Unknown vector_store_type: {vtype!r}. Supported: "
                f"{SUPPORTED_VECTOR_STORES}"
            )

        s3_bucket = dcfg.s3_bucket or self._serve_config.uploads_bucket
        if not s3_bucket:
            raise RuntimeError(
                "Distributed backend requires an S3 bucket. Set "
                "[knowledge] uploads_bucket or [knowledge.distributed] s3_bucket."
            )

        return {
            "relational_dsn": relational_dsn,
            "vector_store_config": vector_store_config,
            "s3_bucket": s3_bucket,
            "s3_storage_type": dcfg.s3_storage_type,
        }

    def _make_vault(self, space: Space) -> Any:
        """Build a VaultFS instance for the given space config.

        Backend is chosen by `space.backend`:
        - "distributed": DistributedVaultFS (S3 + SQL + pluggable vector store)
        - anything else: LocalVaultFS (FS + SQLite + LanceDB)
        """
        if space.backend == "distributed":
            cfg = self._resolve_distributed_config()
            vault = DistributedVaultFS(
                space_id=space.id,
                relational_dsn=cfg["relational_dsn"],
                vector_store_config=cfg["vector_store_config"],
                s3_bucket=cfg["s3_bucket"],
                s3_storage_type=cfg["s3_storage_type"],
                system_app=self._system_app,
            )
            self._configure_embedder_hint(vault, space)
            return vault

        # Local default
        root = self._local_root / space.slug
        vault = LocalVaultFS(space_id=space.id, root=root)
        self._configure_embedder_hint(vault, space)
        return vault

    def _configure_embedder_hint(self, vault: Any, space: Space) -> None:
        """Provide the embedder model hint for lazy identity provisioning.

        Priority: space.embedder_model → ServeConfig.default_embedder_model.
        Vector ops gracefully degrade (skip) when both are empty.
        """
        hint = space.embedder_model or self._serve_config.default_embedder_model
        try:
            vault.configure_embedder_hint(hint, system_app=self._system_app)
        except Exception as e:
            logger.warning(
                "configure_embedder_hint failed for space %s: %s",
                space.slug, e,
            )

    async def get_vault(self, slug: str) -> Any:
        """Resolve slug to a VaultFS instance, creating + initializing if needed."""
        if slug in self._vaults:
            return self._vaults[slug]

        # Determine backend: check JSON registry for distributed, else local
        reg = self._registry_lookup(slug)
        if reg and reg.get("backend") == "distributed":
            space = Space(
                id=reg.get("id") or new_space_id(),
                slug=slug,
                name=reg.get("name") or slug,
                description=reg.get("description") or "",
                backend="distributed",
            )
        else:
            space = Space(
                id=new_space_id(),
                slug=slug,
                name=slug,
                backend=self._serve_config.default_backend or "local",
            )

        vault = self._make_vault(space)
        await vault.initialize()
        self._vaults[slug] = vault
        self._spaces[slug] = space

        # For local spaces, load/seed the per-space SQLite `spaces` row
        if space.backend != "distributed":
            await self._load_space_config(slug, vault)

        return vault

    async def _load_space_config(self, slug: str, vault: LocalVaultFS) -> None:
        """Load Space config from the per-space SQLite `spaces` row, or seed it."""
        if slug in self._spaces:
            return
        try:
            row = await vault._db.execute_fetchall(
                "SELECT * FROM spaces WHERE slug=? LIMIT 1", (slug,)
            )
            if row:
                r = row[0]
                space = Space(
                    id=r["id"],
                    slug=r["slug"],
                    name=r["name"] or slug,
                    description=r["description"] or "",
                    backend=r["backend"] or "local",
                    embedder_model=r["embedder_model"],
                    embedder_dimension=r["embedder_dimension"],
                    default_agent_id=r["default_agent_id"],
                    llm_model=r["llm_model"],
                    multimodal_model=r["multimodal_model"],
                )
                self._spaces[slug] = space
                return
        except Exception as e:
            logger.warning("Load space config failed for %s: %s", slug, e)

        # Seed a row
        space = Space(
            id=new_space_id(),
            slug=slug,
            name=slug,
            backend="local",
        )
        await self._persist_space_config(slug, vault, space, is_new=True)
        self._spaces[slug] = space

    async def _persist_space_config(
        self,
        slug: str,
        vault: LocalVaultFS,
        space: Space,
        is_new: bool = False,
    ) -> None:
        """Insert or update the `spaces` row for this space."""
        now = datetime.utcnow().isoformat()
        try:
            if is_new:
                await vault._db.execute(
                    """
                    INSERT INTO spaces
                      (id, slug, name, description, backend, embedder_model,
                       embedder_dimension, embedder_state, visibility, owner_id,
                       created_at, updated_at, default_agent_id, llm_model,
                       multimodal_model)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'unknown', 'private', '', ?, ?, ?, ?, ?)
                    """,
                    (
                        space.id,
                        space.slug,
                        space.name,
                        space.description,
                        space.backend,
                        space.embedder_model,
                        space.embedder_dimension,
                        now,
                        now,
                        space.default_agent_id,
                        space.llm_model,
                        space.multimodal_model,
                    ),
                )
            else:
                await vault._db.execute(
                    """
                    UPDATE spaces SET
                      name=?, description=?, embedder_model=?, embedder_dimension=?,
                      default_agent_id=?, llm_model=?, multimodal_model=?, updated_at=?
                    WHERE slug=?
                    """,
                    (
                        space.name,
                        space.description,
                        space.embedder_model,
                        space.embedder_dimension,
                        space.default_agent_id,
                        space.llm_model,
                        space.multimodal_model,
                        now,
                        slug,
                    ),
                )
            await vault._db.commit()
        except Exception as e:
            logger.warning("Persist space config failed for %s: %s", slug, e)

    async def get_space_config(self, slug: str) -> Space:
        """Return the cached Space config, loading it if needed."""
        if slug not in self._spaces:
            await self.get_vault(slug)  # triggers _load_space_config
        return self._spaces[slug]

    async def update_space_config(
        self,
        slug: str,
        *,
        default_agent_id: Optional[str] = None,
        llm_model: Optional[str] = None,
        multimodal_model: Optional[str] = None,
        embedder_model: Optional[str] = None,
    ) -> Space:
        """Update non-None fields of the space config and persist."""
        space = await self.get_space_config(slug)
        if default_agent_id is not None:
            space.default_agent_id = default_agent_id or None
        if llm_model is not None:
            space.llm_model = llm_model or None
        if multimodal_model is not None:
            space.multimodal_model = multimodal_model or None
        if embedder_model is not None:
            space.embedder_model = embedder_model or None
        vault = self._vaults[slug]
        await self._persist_space_config(slug, vault, space, is_new=False)
        return space

    async def list_spaces(self) -> List[Dict[str, Any]]:
        """List all known spaces (local directories + distributed registry)."""
        out: List[Dict[str, Any]] = []

        # Local spaces: scan filesystem
        if self._local_root.exists():
            for child in sorted(self._local_root.iterdir()):
                if not child.is_dir():
                    continue
                # Heuristic: a knowledge space has a schema.md or .ks/ dir
                if (child / "schema.md").exists() or (child / ".ks").exists():
                    try:
                        space = await self.get_space_config(child.name)
                        out.append(
                            {
                                "slug": child.name,
                                "backend": "local",
                                "root": str(child),
                                "default_agent_id": space.default_agent_id,
                                "llm_model": space.llm_model,
                                "multimodal_model": space.multimodal_model,
                                "embedder_model": space.embedder_model,
                            }
                        )
                    except Exception as e:
                        logger.warning("list_spaces: load config for %s failed: %s", child.name, e)
                        out.append({"slug": child.name, "backend": "local", "root": str(child)})

        # Distributed spaces: from JSON registry
        for slug, entry in self._load_registry().items():
            if entry.get("backend") != "distributed":
                continue
            out.append(
                {
                    "slug": slug,
                    "backend": "distributed",
                    "root": f"s3://{self._serve_config.distributed.s3_bucket}/{slug}",
                    "default_agent_id": entry.get("default_agent_id"),
                    "llm_model": entry.get("llm_model"),
                    "multimodal_model": entry.get("multimodal_model"),
                    "embedder_model": entry.get("embedder_model"),
                }
            )

        return out

    async def create_space(
        self,
        slug: str,
        *,
        backend: Optional[str] = None,
        default_agent_id: Optional[str] = None,
        llm_model: Optional[str] = None,
        multimodal_model: Optional[str] = None,
        embedder_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new space (local or distributed)."""
        slug = slug.strip()
        if not slug or "/" in slug or slug.startswith("."):
            raise ValueError(f"invalid slug: {slug!r}")

        backend = backend or self._serve_config.default_backend or "local"

        # Pre-create the registry entry for distributed so _make_vault finds it
        if backend == "distributed":
            # Validate config eagerly so the user gets a clear error before
            # we touch the registry.
            self._resolve_distributed_config()
            self._registry_upsert(
                slug,
                {
                    "id": new_space_id(),
                    "backend": "distributed",
                    "name": slug,
                    "description": "",
                    "default_agent_id": default_agent_id,
                    "llm_model": llm_model,
                    "multimodal_model": multimodal_model,
                    "embedder_model": embedder_model,
                },
            )

        vault = await self.get_vault(slug)

        # Apply any initial config (local spaces persist to SQLite)
        if backend != "distributed" and (
            default_agent_id or llm_model or multimodal_model or embedder_model
        ):
            await self.update_space_config(
                slug,
                default_agent_id=default_agent_id,
                llm_model=llm_model,
                multimodal_model=multimodal_model,
                embedder_model=embedder_model,
            )

        space = self._spaces[slug]
        return {
            "slug": slug,
            "backend": backend,
            "root": str(vault.root),
            "default_agent_id": space.default_agent_id,
            "llm_model": space.llm_model,
            "multimodal_model": space.multimodal_model,
            "embedder_model": space.embedder_model,
        }

    async def close_all(self) -> None:
        for v in list(self._vaults.values()):
            try:
                await v.close()
            except Exception as e:
                logger.warning(f"close vault failed: {e}")
        self._vaults.clear()
        self._spaces.clear()


__all__ = ["Service"]
