#!/usr/bin/env python3
"""一次性迁移脚本：SimpleSQLite 记忆 → MemPalace (unified-Chroma)。

背景：mempalace 未安装时，Agent 的记忆写入回退到 SimpleSQLiteMemoryStore
（``data/memory/{knowledge_id}.db``）。安装 mempalace 后，读写都改走
MemPalace 的 unified-Chroma 后端，但旧数据仍留在 .db 文件里、UI 读不到。

本脚本把每个 ``data/memory/*.db`` 的 ``memories`` 表内容写入对应空间的
MemPalace store。幂等（``_unified_add`` 按 wing/room/content 去重），对源
只读，**不删除** .db 文件。

用法::

    .venv/bin/python scripts/migrate_memory_sqlite_to_mempalace.py \
        --config configs/derisk-proxy-openai.toml

风险提示：必须在 mempalace_store.py 的 per-space 隔离改动（A1）合入后运行，
否则数据会落到共享目录、隔离生效后读不到。脚本会断言 store 处于 unified
模式（``_use_derisk_embedding is True``），否则中止。
"""

import argparse
import json
import logging
import os
import sqlite3
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migrate_memory")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _pkg in ("derisk-core", "derisk-ext", "derisk-serve", "derisk-app"):
    _src = os.path.join(PROJECT_ROOT, "packages", _pkg, "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)


def _build_embedding_fn(app_config):
    """Build an embedding function from the server config's first embedding.

    The running server resolves embeddings through a WorkerManager, which is
    heavy to bootstrap standalone. Since the configured provider is an
    OpenAI-compatible HTTP endpoint, we construct the same OpenAPIEmbeddings
    directly — it produces vectors from the identical model/endpoint, so the
    migrated vectors live in the same space the server later reads.
    """
    embeddings = getattr(app_config.models, "embeddings", None) or []
    if not embeddings:
        return None
    emb = embeddings[0]
    api_url = getattr(emb, "api_url", None) or getattr(emb, "api_base", None)
    api_key = getattr(emb, "api_key", None)
    model_name = getattr(emb, "name", None)
    if not api_url:
        return None

    # TODO: rewire to new knowledge module (Task #9)
    from derisk.rag.embedding.embeddings import OpenAPIEmbeddings  # type: ignore

    logger.info(
        "Building OpenAPIEmbeddings: model=%s url=%s", model_name, api_url
    )
    return OpenAPIEmbeddings(
        api_url=api_url, api_key=api_key, model_name=model_name
    )


def _bootstrap(config_file: str):
    """Load config and build the pieces needed to create memory stores.

    Returns ``(memory_cfg, embedding_fn)`` where ``memory_cfg`` is the
    ``[rag.storage.memory]`` config and ``embedding_fn`` is an Embeddings
    instance (or None). Stores are created directly so we don't depend on a
    running WorkerManager.
    """
    from derisk_app.app import scan_configs, load_config

    scan_configs()

    # Importing the config triggers MemoryStoreConfig subclass registration.
    from derisk_ext.storage.memory.mempalace_store import (  # noqa: F401
        MemPalaceMemoryConfig,
    )

    app_config = load_config(config_file)
    memory_cfg = app_config.rag.storage.memory
    logger.info(
        "Config loaded: memory type=%s, default_embedding=%s",
        getattr(memory_cfg, "type", None),
        getattr(app_config.models, "default_embedding", None),
    )

    embedding_fn = _build_embedding_fn(app_config)
    return memory_cfg, embedding_fn


def _create_store(memory_cfg, embedding_fn, index_name: str):
    """Create a MemPalace store exactly as StorageManager would.

    Mirrors StorageManager.create_memory_store's config construction so the
    palace_path / collection match what the running server uses for reads.
    """
    from derisk_ext.storage.memory.mempalace_store import (
        MemPalaceMemoryConfig,
        MemPalaceMemoryStore,
    )

    kwargs = {}
    for k in ("palace_path", "enable_kg", "default_wing", "use_builtin_embedding"):
        v = getattr(memory_cfg, k, None)
        if v is not None:
            kwargs[k] = v
    config_instance = MemPalaceMemoryConfig(**kwargs)
    return config_instance.create_store(name=index_name, embedding_fn=embedding_fn)



def _read_sqlite_memories(db_path: str):
    """Read all rows from the SimpleSQLite ``memories`` table (read-only)."""
    rows = []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, content, wing, room, metadata, created_at "
            "FROM memories"
        )
        for r in cur.fetchall():
            rows.append(dict(r))
    finally:
        conn.close()
    return rows


def migrate_space(memory_cfg, embedding_fn, index_name: str, db_path: str) -> dict:
    """Migrate one .db file into its MemPalace space. Idempotent."""
    stats = {"index_name": index_name, "read": 0, "written": 0, "errors": 0}

    rows = _read_sqlite_memories(db_path)
    stats["read"] = len(rows)
    if not rows:
        logger.info("[%s] no rows to migrate", index_name)
        return stats

    store = _create_store(memory_cfg, embedding_fn, index_name)
    if store is None:
        logger.error("[%s] store creation returned None — skipping", index_name)
        stats["errors"] = len(rows)
        return stats

    if not getattr(store, "_use_derisk_embedding", False):
        raise SystemExit(
            f"[{index_name}] memory store is NOT in unified embedding mode. "
            "Aborting to avoid writing into an inconsistent vector space. "
            "Ensure an embedding model is configured in the server config "
            "([[models.embeddings]]) and that "
            "[rag.storage.memory] use_builtin_embedding is not true."
        )

    for row in rows:
        content = row.get("content") or ""
        wing = row.get("wing") or "default"
        room = row.get("room") or "general"
        metadata = {}
        if row.get("metadata"):
            try:
                metadata = json.loads(row["metadata"])
            except (ValueError, TypeError):
                metadata = {"raw": row["metadata"]}
        try:
            store.write_memory(
                content=content, wing=wing, room=room, metadata=metadata
            )
            stats["written"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[%s] failed to write entry %s: %s",
                           index_name, row.get("id"), e)
            stats["errors"] += 1

    try:
        total = store.get_status().get("total_entries", "?")
    except Exception:  # noqa: BLE001
        total = "?"
    logger.info(
        "[%s] migrated %d/%d entries (errors=%d); store now has %s entries",
        index_name, stats["written"], stats["read"], stats["errors"], total,
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/derisk-proxy-openai.toml",
        help="Server config TOML (same one the server runs with).",
    )
    parser.add_argument(
        "--memory-dir",
        default=os.path.join(PROJECT_ROOT, "data", "memory"),
        help="Directory containing SimpleSQLite {knowledge_id}.db files.",
    )
    args = parser.parse_args()

    config_file = args.config
    if not os.path.isabs(config_file):
        config_file = os.path.join(PROJECT_ROOT, config_file)

    memory_dir = args.memory_dir
    if not os.path.isdir(memory_dir):
        logger.error("memory dir not found: %s", memory_dir)
        return 1

    db_files = [
        f for f in os.listdir(memory_dir) if f.endswith(".db")
    ]
    if not db_files:
        logger.info("No .db files found in %s — nothing to migrate.", memory_dir)
        return 0

    logger.info("Found %d SimpleSQLite db file(s): %s", len(db_files), db_files)

    memory_cfg, embedding_fn = _bootstrap(config_file)
    if embedding_fn is None:
        raise SystemExit(
            "No embedding model resolved from config. Add a "
            "[[models.embeddings]] entry to the server config so memory "
            "vectors use the same model the server reads with."
        )

    summary = []
    for fname in db_files:
        index_name = fname[:-3]  # strip ".db" → knowledge_id
        db_path = os.path.join(memory_dir, fname)
        summary.append(
            migrate_space(memory_cfg, embedding_fn, index_name, db_path)
        )

    logger.info("==== Migration summary ====")
    for s in summary:
        logger.info(
            "  %s: read=%d written=%d errors=%d",
            s["index_name"], s["read"], s["written"], s["errors"],
        )
    logger.info(
        "Source .db files were NOT deleted. Archive them once you've "
        "verified counts in the UI."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
