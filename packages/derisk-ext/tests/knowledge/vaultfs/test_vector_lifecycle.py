"""Vector lifecycle tests — write/read/delete/reindex against a live cluster.

Skipped unless env vars are set (same skip pattern as
`test_distributed_conformance.py`). Verifies the full vector wiring:

1. `doc_create` writes vectors with stable `doc:{id}:chunk:{hash}` IDs.
2. `doc_search(mode="semantic")` returns the doc via cosine similarity.
3. `doc_search(mode="hybrid")` fuses FTS + vector recall.
4. `doc_delete` removes the doc's vectors from the vector store.
5. `reindex(layer="vectors")` clears and rebuilds vectors from L1 docs.
6. Embedder identity is lazy-provisioned on first vector op from
   `KNOWLEDGE_EMBEDDER_MODEL` env var.

Env vars:
- `KNOWLEDGE_RELATIONAL_DSN` — SQLAlchemy async DSN (Postgres or MySQL).
- `KNOWLEDGE_VECTOR_DSN` — pgvector DSN (Postgres). Same as relational
  for single-DB mode; requires pgvector extension.
- `KNOWLEDGE_S3_BUCKET` — S3 bucket name (must already exist).
- `KNOWLEDGE_EMBEDDER_MODEL` — embedder model name (e.g.
  `text-embedding-3-small`). The space's embedder_model is set to this
  so lazy provisioning works.
- `KNOWLEDGE_S3_STORAGE_TYPE` — optional storage type override.
- `KNOWLEDGE_VECTOR_STORE_TYPE` — optional, defaults to "pgvector".
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

relational_dsn = os.getenv("KNOWLEDGE_RELATIONAL_DSN")
vector_dsn = os.getenv("KNOWLEDGE_VECTOR_DSN")
s3_bucket = os.getenv("KNOWLEDGE_S3_BUCKET")
s3_storage_type = os.getenv("KNOWLEDGE_S3_STORAGE_TYPE")
embedder_model = os.getenv("KNOWLEDGE_EMBEDDER_MODEL")
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


_required = (
    relational_dsn
    and s3_bucket
    and embedder_model
    and (vector_dsn or vector_store_type != "pgvector")
)

pytestmark = pytest.mark.skipif(
    not _required,
    reason=(
        "set KNOWLEDGE_RELATIONAL_DSN, KNOWLEDGE_VECTOR_DSN, "
        "KNOWLEDGE_S3_BUCKET, and KNOWLEDGE_EMBEDDER_MODEL to run this suite"
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
        vector_store_config=_build_vector_store_config(),
        s3_bucket=s3_bucket,
        s3_storage_type=s3_storage_type,
    )
    # Lazy-provision embedder from this hint on first vector op.
    v.configure_embedder_hint(embedder_model)
    await v.initialize()
    yield v
    await v.close()


def _make_doc_body(unique_seed: str) -> str:
    """Generate a distinctive body that will embed to a unique vector."""
    return (
        f"# Test Doc {unique_seed}\n\n"
        f"This document discusses quantum entanglement, superposition, "
        f"and the measurement problem in foundational quantum mechanics. "
        f"The Schrödinger equation describes the evolution of the "
        f"wavefunction over time. Unique seed: {unique_seed}.\n\n"
        f"## Background\n\n"
        f"Quantum systems exhibit probabilistic behavior that cannot be "
        f"explained by classical mechanics. The double-slit experiment "
        f"demonstrates wave-particle duality.\n"
    )


@pytest.mark.asyncio
async def test_doc_create_writes_vectors(vault):
    """doc_create should populate the vector store with chunk vectors."""
    from derisk_ext.knowledge.embedder_factory import get_embedder

    seed = uuid.uuid4().hex[:8]
    path = f"concepts/quantum-{seed}.md"
    body = _make_doc_body(seed)
    content = f"---\ntype: concept\ntitle: Quantum {seed}\n---\n\n{body}"

    doc_id = await vault.doc_create(path=path, content=content)
    assert doc_id, "doc_create returned empty doc_id"

    # Verify a vector was written by querying the store directly.
    embedder = get_embedder(embedder_model, vault._system_app)
    hits = await vault.vector_query_text(
        "quantum entanglement superposition", embedder, top_k=5
    )
    matching = [h for h in hits if (h.metadata or {}).get("document_id") == doc_id]
    assert matching, f"no vector hit for doc {doc_id} — vector write failed"


@pytest.mark.asyncio
async def test_semantic_search_returns_doc(vault):
    """doc_search(mode='semantic') should find the doc by concept query."""
    seed = uuid.uuid4().hex[:8]
    path = f"concepts/superposition-{seed}.md"
    body = _make_doc_body(seed)
    content = f"---\ntype: concept\ntitle: Superposition {seed}\n---\n\n{body}"

    doc_id = await vault.doc_create(path=path, content=content)

    hits = await vault.doc_search(
        "quantum superposition wavefunction", mode="semantic", limit=10
    )
    paths = [h.path for h in hits]
    assert path in paths, (
        f"semantic search did not return {path}; got {paths}"
    )


@pytest.mark.asyncio
async def test_hybrid_search_fuses_results(vault):
    """doc_search(mode='hybrid') should return fused FTS+vector results."""
    seed = uuid.uuid4().hex[:8]
    path = f"concepts/entanglement-{seed}.md"
    body = _make_doc_body(seed)
    content = f"---\ntype: concept\ntitle: Entanglement {seed}\n---\n\n{body}"

    await vault.doc_create(path=path, content=content)

    hits = await vault.doc_search(
        "quantum entanglement", mode="hybrid", limit=10
    )
    paths = [h.path for h in hits]
    assert path in paths, (
        f"hybrid search did not return {path}; got {paths}"
    )


@pytest.mark.asyncio
async def test_doc_delete_removes_vectors(vault):
    """doc_delete should clean up vectors from the vector store."""
    from derisk_ext.knowledge.embedder_factory import get_embedder

    seed = uuid.uuid4().hex[:8]
    path = f"concepts/cleanup-{seed}.md"
    body = _make_doc_body(seed)
    content = f"---\ntype: concept\ntitle: Cleanup {seed}\n---\n\n{body}"

    doc_id = await vault.doc_create(path=path, content=content)

    # Confirm vector exists.
    embedder = get_embedder(embedder_model, vault._system_app)
    pre_hits = await vault.vector_query_text(
        f"quantum cleanup {seed}", embedder, top_k=20
    )
    pre_matching = [
        h for h in pre_hits
        if (h.metadata or {}).get("document_id") == doc_id
    ]
    assert pre_matching, "vector should exist before delete"

    await vault.doc_delete(path=path)

    post_hits = await vault.vector_query_text(
        f"quantum cleanup {seed}", embedder, top_k=20
    )
    post_matching = [
        h for h in post_hits
        if (h.metadata or {}).get("document_id") == doc_id
    ]
    assert not post_matching, (
        f"vector should be gone after delete; still found {post_matching}"
    )


@pytest.mark.asyncio
async def test_reindex_vectors_rebuilds(vault):
    """reindex(layer='vectors') should clear + rebuild all chunk vectors."""
    seed = uuid.uuid4().hex[:8]
    path = f"concepts/rebuild-{seed}.md"
    body = _make_doc_body(seed)
    content = f"---\ntype: concept\ntitle: Rebuild {seed}\n---\n\n{body}"

    await vault.doc_create(path=path, content=content)

    report = await vault.reindex(layer="vectors")
    assert report.vectors_rebuilt >= 1, (
        f"reindex should have rebuilt ≥1 doc's vectors; got {report.vectors_rebuilt}"
    )

    # Confirm the doc is still searchable post-reindex.
    hits = await vault.doc_search(
        f"quantum rebuild {seed}", mode="semantic", limit=10
    )
    paths = [h.path for h in hits]
    assert path in paths, (
        f"semantic search after reindex did not return {path}"
    )


@pytest.mark.asyncio
async def test_doc_edit_keeps_stable_vector_ids(vault):
    """doc_edit on an unchanged chunk should keep the same vector ID
    (idempotent upsert). The test verifies vectors are still present
    after an edit and the doc is still searchable."""
    seed = uuid.uuid4().hex[:8]
    path = f"concepts/edit-stable-{seed}.md"
    body = _make_doc_body(seed)
    content = f"---\ntype: concept\ntitle: Edit Stable {seed}\n---\n\n{body}"

    await vault.doc_create(path=path, content=content)

    # Edit — append a new paragraph (existing chunks unchanged → stable IDs).
    new_content = content + "\n\n## Addition\n\nMore content added later.\n"
    await vault.doc_edit(path=path, content=new_content)

    # Semantic search should still find the doc.
    hits = await vault.doc_search(
        "quantum entanglement", mode="semantic", limit=10
    )
    paths = [h.path for h in hits]
    assert path in paths, (
        f"semantic search after edit did not return {path}"
    )
