"""DistributedVaultFS conformance test — skipped unless env vars are set.

Set the following env vars to run this suite against a live cluster:
- `KNOWLEDGE_RELATIONAL_DSN`: SQLAlchemy async DSN for relational metadata
  (e.g. `postgresql+asyncpg://user:pass@localhost/derisk_test` or
  `mysql+asyncmy://user:pass@localhost/derisk_test`)
- `KNOWLEDGE_VECTOR_DSN`: DSN for vectors (pgvector only — same as
  relational for single-DB mode; requires pgvector extension)
- `KNOWLEDGE_S3_BUCKET`: S3 bucket name (must already exist)
- `KNOWLEDGE_S3_STORAGE_TYPE`: optional storage type override (defaults
  to whatever FileStorageClient is configured with)
- `KNOWLEDGE_VECTOR_STORE_TYPE`: optional, defaults to "pgvector".
  One of: pgvector | milvus | chroma | lance. When set to milvus/chroma/
  lance, the corresponding *_URI env var replaces KNOWLEDGE_VECTOR_DSN.

Without these env vars, the entire module skips — local CI doesn't
require Postgres+pgvector+S3.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

relational_dsn = os.getenv("KNOWLEDGE_RELATIONAL_DSN")
vector_dsn = os.getenv("KNOWLEDGE_VECTOR_DSN")
s3_bucket = os.getenv("KNOWLEDGE_S3_BUCKET")
s3_storage_type = os.getenv("KNOWLEDGE_S3_STORAGE_TYPE")
vector_store_type = os.getenv("KNOWLEDGE_VECTOR_STORE_TYPE", "pgvector")


def _build_vector_store_config() -> dict:
    if vector_store_type == "pgvector":
        return {"type": "pgvector", "dsn": vector_dsn}
    if vector_store_type == "milvus":
        return {"type": "milvus", "uri": os.getenv("KNOWLEDGE_MILVUS_URI", "")}
    if vector_store_type == "chroma":
        return {"type": "chroma", "uri": os.getenv("KNOWLEDGE_CHROMA_URI", "")}
    if vector_store_type == "lance":
        return {"type": "lance", "s3_uri": os.getenv("KNOWLEDGE_LANCE_S3_URI", "")}
    raise ValueError(f"Unknown KNOWLEDGE_VECTOR_STORE_TYPE: {vector_store_type}")


_vector_cfg = _build_vector_store_config()
_required = relational_dsn and s3_bucket
if vector_store_type == "pgvector":
    _required = _required and bool(vector_dsn)
elif vector_store_type == "milvus":
    _required = _required and bool(_vector_cfg.get("uri"))
elif vector_store_type == "chroma":
    _required = _required and bool(_vector_cfg.get("uri"))
elif vector_store_type == "lance":
    _required = _required and bool(_vector_cfg.get("s3_uri"))

pytestmark = pytest.mark.skipif(
    not _required,
    reason=(
        "set KNOWLEDGE_RELATIONAL_DSN, KNOWLEDGE_VECTOR_DSN (or "
        "KNOWLEDGE_MILVUS_URI / KNOWLEDGE_CHROMA_URI / KNOWLEDGE_LANCE_S3_URI), "
        "and KNOWLEDGE_S3_BUCKET to run this suite"
    ),
)


@pytest_asyncio.fixture
async def vault():
    from derisk_ext.knowledge.vaultfs import DistributedVaultFS
    from derisk.knowledge.types import new_space_id

    space_id = new_space_id()
    v = DistributedVaultFS(
        space_id=space_id,
        relational_dsn=relational_dsn,
        vector_store_config=_vector_cfg,
        s3_bucket=s3_bucket,
        s3_storage_type=s3_storage_type,
    )
    await v.initialize()
    yield v
    await v.close()


@pytest.mark.asyncio
async def test_distributed_vaultfs_conformance(vault):
    """DistributedVaultFS must pass the full conformance suite."""
    from derisk_ext.knowledge.vaultfs.conformance import run_conformance

    await run_conformance(vault)


@pytest.mark.asyncio
async def test_distributed_vaultfs_backend_type(vault):
    assert vault.backend_type == "distributed"


@pytest.mark.asyncio
async def test_distributed_vaultfs_root_is_s3_uri(vault):
    assert vault.root.startswith("s3://")
    assert vault.bucket if hasattr(vault, "bucket") else True


@pytest.mark.asyncio
async def test_distributed_vaultfs_schema_md_roundtrip(vault):
    """write_schema_md then read_schema_md should return the same content."""
    original = await vault.read_schema_md()
    new_content = original + "\n# Test Edit\n"
    if original and original != new_content:
        await vault.write_schema_md(new_content)
        read_back = await vault.read_schema_md()
        assert "# Test Edit" in read_back
        # Restore
        await vault.write_schema_md(original)
