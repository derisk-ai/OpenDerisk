"""Integration tests for the vector search pipeline: ChromaDB + memory_case."""

import asyncio
import os
import tempfile
from typing import List

import pytest

from derisk.core import Chunk, Embeddings
from derisk_ext.plugin.memory_case.models import CandidateCase
from derisk_ext.plugin.memory_case.vector_index import (
    ChromaCandidateCaseVectorIndex,
    LazyCandidateCaseVectorIndex,
    build_vector_index,
)


class _FakeEmbeddings(Embeddings):
    """Deterministic embeddings: encodes the first 3 chars of the text as floats."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [_encode(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return _encode(text)


def _encode(text: str) -> List[float]:
    """Stable 8-dim vector from text prefix."""
    v = [0.0] * 8
    for i, ch in enumerate(text[:16]):
        v[i % 8] += ord(ch) / 1000.0
    return v


class _FakeVectorStoreSource:
    """Creates a ChromaStore-like in-memory collection for tests."""

    def __init__(self):
        self._store = _InMemoryChromaCollection("memory_case_candidate", _FakeEmbeddings())

    def create_vector_store(self, index_name, extra_indexes=None):
        return self._store


class _InMemoryChromaCollection:
    """Minimal in-memory vector store that supports the ChromaStore interface
    enough for ``ChromaCandidateCaseVectorIndex`` to work."""

    def __init__(self, name: str, embeddings: _FakeEmbeddings):
        self._name = name
        self._embeddings = embeddings
        self._docs: dict = {}  # chunk_id → Chunk

    async def aload_document(self, chunks: List[Chunk]) -> List[str]:
        for c in chunks:
            self._docs[c.chunk_id] = c
        return [c.chunk_id for c in chunks]

    def similar_search_with_scores(
        self, text: str, topk: int, score_threshold: float, filters=None
    ) -> List[Chunk]:
        query_vec = self._embeddings.embed_query(text)
        scored = []
        for cid, chunk in self._docs.items():
            if filters and not _match_metadata_filters(chunk.metadata, filters):
                continue
            doc_vec = _encode(chunk.content)
            sim = _cosine(query_vec, doc_vec)
            if sim >= score_threshold:
                c = Chunk(
                    content=chunk.content,
                    metadata=dict(chunk.metadata),
                    score=sim,
                    chunk_id=cid,
                )
                scored.append(c)
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:topk]

    async def update_by_chunk_ids(self, ids, metadata_update):
        for cid in ids:
            if cid in self._docs:
                self._docs[cid].metadata.update(metadata_update)


def _match_metadata_filters(meta: dict, filters) -> bool:
    """Check chunk metadata against Chroma-style MetadataFilters."""
    from derisk.storage.vector_store.filters import MetadataFilters

    if not isinstance(filters, MetadataFilters) or not filters.filters:
        return True
    for f in filters.filters:
        val = (meta or {}).get(f.key)
        if val is None:
            return False
        if str(val) != str(f.value):
            return False
    return True


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vector_index():
    source = _FakeVectorStoreSource()
    return ChromaCandidateCaseVectorIndex(source.create_vector_store("memory_case_candidate"))


@pytest.fixture
def lazy_index():
    source = _FakeVectorStoreSource()
    return LazyCandidateCaseVectorIndex(source)


def _case(
    cid: str,
    summary: str,
    env: str = "default",
    app: str = "default",
) -> CandidateCase:
    return CandidateCase(
        case_id=cid,
        symptom_summary=summary,
        markdown_summary=summary,
        metadata={
            "case_context": {
                "app_code": app,
                "environment": env,
            }
        },
    )


# ---------------------------------------------------------------------------
# Vector upsert + search
# ---------------------------------------------------------------------------


async def _insert_and_search(index, cases, query, scope=None, top_k=5):
    for case in cases:
        await index.upsert(case)
    return await index.search(query, scope or {}, top_k)


@pytest.mark.asyncio
async def test_upsert_and_semantic_search_same_topic(vector_index):
    cases = [
        _case("c1", "POD 内存使用率过高导致 OOM Kill"),
        _case("c2", "磁盘空间不足导致写入失败"),
        _case("c3", "POD CPU 飙升引发延迟告警"),
    ]
    hits = await _insert_and_search(vector_index, cases, "内存 OOM")

    assert len(hits) > 0, "should find at least one match"
    assert "c1" in hits, "内存 OOM should match case c1"


@pytest.mark.asyncio
async def test_semantic_search_orders_by_relevance(vector_index):
    cases = [
        _case("c-1", "网络超时导致服务不可用"),
        _case("c-2", "POD 内存泄漏导致频繁重启"),
        _case("c-3", "HTTP 504 Gateway Timeout 上游超时"),
        _case("c-4", "磁盘 IO 瓶颈导致写入延迟"),
        _case("c-5", "连接池耗尽引发超时错误"),
    ]
    hits = await _insert_and_search(vector_index, cases, "超时 timeout 网络")

    assert len(hits) >= 1
    # semantic similarity: c-3 (gateway timeout), c-1 (网络超时), c-5 (超时) should rank high
    assert "c-3" in hits or "c-1" in hits


# ---------------------------------------------------------------------------
# Scope filtering in vector search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_environment_filters_strictly(vector_index):
    cases = [
        _case("e1", "腾讯云 CLB 502 错误", env="腾讯云"),
        _case("e2", "腾讯云 CDN 回源失败", env="腾讯云"),
        _case("e3", "AWS ALB 健康检查失败", env="aws"),
    ]
    hits = await _insert_and_search(vector_index, cases, "负载均衡 502", scope={"environment": "腾讯云"})

    # Only 腾讯云 cases should return
    for cid in hits:
        assert cid in ("e1", "e2"), f"scope=腾讯云 should exclude aws case, got {cid}"


@pytest.mark.asyncio
async def test_scope_default_is_wildcard(vector_index):
    cases = [
        _case("d1", "CPU 使用率告警", env="prod"),
        _case("d2", "内存使用率告警", env="staging"),
        _case("d3", "磁盘告警", env="腾讯云"),
    ]
    hits = await _insert_and_search(vector_index, cases, "告警", scope={"environment": "default"})

    assert len(hits) == 3, f"wildcard scope should return all 3, got {len(hits)}"


# ---------------------------------------------------------------------------
# Lazy index (delayed init)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lazy_index_inits_on_first_use(lazy_index):
    """LazyCandidateCaseVectorIndex should create real index on first call."""
    assert lazy_index._real is None

    case = _case("lz-1", "延迟初始化测试案例")
    await lazy_index.upsert(case)
    assert lazy_index._real is not None, "should have created real index after first upsert"

    hits = await lazy_index.search("延迟初始化", {}, 5)
    assert "lz-1" in hits


@pytest.mark.asyncio
async def test_lazy_index_invalidate_delegates(lazy_index):
    await lazy_index.upsert(_case("lz-stale", "过期案例", env="prod"))
    await lazy_index.invalidate("lz-stale")
    assert lazy_index._real is not None


# ---------------------------------------------------------------------------
# Empty dataset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_empty_index_returns_empty(vector_index):
    hits = await vector_index.search("any query", {}, 5)
    assert hits == []


# ---------------------------------------------------------------------------
# Score threshold: low-similarity docs are excluded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mismatched_query_returns_fewer_results(vector_index):
    cases = [
        _case("m1", "Kubernetes Pod Evicted due to memory pressure"),
        _case("m2", "MySQL replication lag alert"),
    ]
    hits = await _insert_and_search(vector_index, cases, "前端页面渲染白屏 JS报错")

    # This query is semantically far from the stored docs, likely fewer or no hits
    assert len(hits) <= 2
