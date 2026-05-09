from typing import Dict

import pytest

from derisk_ext.plugin.memory_case import (
    CandidateCase,
    CandidateCaseLifecycle,
    CaseRelationType,
    MemoryCasePluginService,
    cross_validate_relation,
    scope_filters_match,
)


class _FakeDao:
    def __init__(self):
        self._store = {}

    def upsert(self, case: CandidateCase) -> CandidateCase:
        self._store[case.case_id] = case
        return case

    def get_by_case_id(self, case_id: str):
        return self._store.get(case_id)

    def search(self, scope, query_text=None, limit=10):
        results = []
        for case in self._store.values():
            if not scope_filters_match(case.metadata, scope):
                continue
            if query_text and query_text not in (case.symptom_summary or ""):
                continue
            results.append(case)
        return results[:limit]


class _FakeSystemApp:
    def __init__(self):
        self.config = {}


class _FakeVectorIndex:
    async def upsert(self, case: CandidateCase):
        return None

    async def search(self, query: str, case_scope: dict, top_k: int):
        return []

    async def search_with_scores(self, query, case_scope, top_k):
        return []

    async def invalidate(self, case_id: str):
        return None


@pytest.mark.asyncio
async def test_upsert_sets_lifecycle_draft():
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
    )
    out = await service.call_tool(
        "memory_case_upsert",
        {
            "case": {
                "case_id": "case-1",
                "app_code": "demo",
                "environment": "prod",
                "fingerprint": "f-1",
                "symptom_summary": "cpu alert",
                "confidence": 0.35,
            }
        },
    )
    assert out["case"]["lifecycle"] == CandidateCaseLifecycle.DRAFT.value


@pytest.mark.asyncio
async def test_upsert_without_fingerprint_gets_stable_hash():
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
    )
    out = await service.call_tool(
        "memory_case_upsert",
        {
            "case": {
                "case_id": "case-no-fp",
                "app_code": "demo",
                "environment": "prod",
                "symptom_summary": "oom kill",
                "confidence": 0.5,
            }
        },
    )
    fp = out["case"]["fingerprint"]
    assert fp and len(fp) == 64
    out2 = await service.call_tool(
        "memory_case_upsert",
        {
            "case": {
                "case_id": "case-no-fp",
                "app_code": "demo",
                "environment": "prod",
                "symptom_summary": "oom kill",
                "confidence": 0.6,
            }
        },
    )
    assert out2["case"]["fingerprint"] == fp


# ---------------------------------------------------------------------------
# cross_validate_relation unit tests
# ---------------------------------------------------------------------------


def test_cross_validate_same_failure_layer_and_runtime():
    ctx_a = {"failure_layer": "jvm", "runtime": "java", "related_services": ["order-svc"]}
    ctx_b = {"failure_layer": "jvm", "runtime": "java", "related_services": ["order-svc", "trade-svc"]}
    assert cross_validate_relation(ctx_a, ctx_b) is True


def test_cross_validate_different_failure_layer_blocked():
    ctx_a = {"failure_layer": "jvm", "runtime": "java"}
    ctx_b = {"failure_layer": "k8s", "runtime": "java"}
    assert cross_validate_relation(ctx_a, ctx_b) is False


def test_cross_validate_different_runtime_blocked():
    ctx_a = {"runtime": "java"}
    ctx_b = {"runtime": "go"}
    assert cross_validate_relation(ctx_a, ctx_b) is False


def test_cross_validate_no_shared_services_blocked():
    ctx_a = {"related_services": ["order-svc", "checkout-api"]}
    ctx_b = {"related_services": ["trade-svc", "risk-engine"]}
    assert cross_validate_relation(ctx_a, ctx_b) is False


def test_cross_validate_missing_fields_pass():
    """Missing fields never block — only present keys on both sides are checked."""
    ctx_a = {"failure_layer": "jvm"}
    ctx_b = {}
    assert cross_validate_relation(ctx_a, ctx_b) is True


def test_cross_validate_one_service_overlap_passes():
    ctx_a = {"related_services": ["order-svc", "checkout-api"]}
    ctx_b = {"related_services": ["order-svc", "trade-svc"]}
    assert cross_validate_relation(ctx_a, ctx_b) is True


# ---------------------------------------------------------------------------
# _classify_relation unit tests
# ---------------------------------------------------------------------------


def test_classify_same_root_cause():
    rel = MemoryCasePluginService._classify_relation(
        score_symptom=0.9,
        score_diagnosis=0.85,
        score_root_cause=0.92,
        struct_match=True,
    )
    assert rel == CaseRelationType.SAME_ROOT_CAUSE


def test_classify_similar_diagnosis_with_struct_match():
    rel = MemoryCasePluginService._classify_relation(
        score_symptom=0.85,
        score_diagnosis=0.75,
        score_root_cause=0.5,
        struct_match=True,
    )
    assert rel == CaseRelationType.SIMILAR_DIAGNOSIS


def test_classify_surface_similar_only():
    """High symptom match but no struct match → surface_similar."""
    rel = MemoryCasePluginService._classify_relation(
        score_symptom=0.9,
        score_diagnosis=0.3,
        score_root_cause=0.1,
        struct_match=False,
    )
    assert rel == CaseRelationType.SURFACE_SIMILAR


def test_classify_root_cause_high_but_no_struct():
    """High root_cause score without struct match is NOT same_root_cause."""
    rel = MemoryCasePluginService._classify_relation(
        score_symptom=0.92,
        score_diagnosis=0.88,
        score_root_cause=0.85,
        struct_match=False,
    )
    assert rel != CaseRelationType.SAME_ROOT_CAUSE


# ---------------------------------------------------------------------------
# _find_similar_cases integration test
# ---------------------------------------------------------------------------


class _RichFakeVectorIndex:
    """Fake vector index that returns different scores per query text."""

    def __init__(self, store: Dict[str, "CandidateCase"]):
        self._store = store

    async def upsert(self, case):
        return None

    async def search(self, query, case_scope, top_k):
        return []

    async def search_with_scores(self, query: str, case_scope: dict, top_k: int):
        import hashlib

        q = str(query).lower()
        results = []
        for cid, case in self._store.items():
            score = 0.0
            # Root cause match scores highest
            if case.root_cause and case.root_cause.lower() in q:
                score = max(score, 0.9)
            elif any(w in q for w in (case.root_cause or "").lower().split()):
                score = max(score, 0.7)
            # Symptom overlap
            sym = (case.symptom_summary or "").lower()
            sym_overlap = len(set(q.split()) & set(sym.split())) / max(len(set(q.split())), 1)
            score = max(score, sym_overlap * 0.6)
            # Minimal baseline
            score = max(score, 0.15)
            results.append((cid, score))
        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    async def invalidate(self, case_id):
        return None


@pytest.mark.asyncio
async def test_find_similar_cases_returns_typed_relations():
    """End-to-end: weighted search + struct cross-check + relation typing."""
    dao = _FakeDao()

    # Seed existing cases in DAO
    existing = [
        CandidateCase(
            case_id="case-root",
            symptom_summary="Pod OOMKilled 内存溢出",
            diagnosis="查 JVM 堆配置 → 发现 -Xmx 512M → 调大",
            root_cause="JVM 堆配置 512M 过小",
            metadata={
                "case_context": {
                    "failure_layer": "jvm",
                    "runtime": "java",
                    "related_services": ["order-svc"],
                }
            },
        ),
        CandidateCase(
            case_id="case-surface",
            symptom_summary="Pod OOMKilled 内存溢出频繁重启",
            diagnosis="查下游 risk-engine 内存泄漏导致请求堆积",
            root_cause="risk-engine 内存泄漏",
            metadata={
                "case_context": {
                    "failure_layer": "application",
                    "runtime": "go",
                    "related_services": ["risk-engine", "trade-svc"],
                }
            },
        ),
    ]
    for c in existing:
        dao.upsert(c)

    vec = _RichFakeVectorIndex({c.case_id: c for c in existing})
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(), dao=dao, vector_index=vec
    )

    new_case = CandidateCase(
        case_id="new-case",
        symptom_summary="Pod OOMKilled JVM 内存不足",
        diagnosis="怀疑 JVM 堆配置过小 → 查 -Xmx 参数",
        root_cause="JVM 堆内存 512M 过小",
        metadata={
            "case_context": {
                "failure_layer": "jvm",
                "runtime": "java",
                "related_services": ["order-svc"],
            }
        },
    )

    results = await service._find_similar_cases(new_case, top_k=3)
    assert len(results) > 0

    by_id = {r["case_id"]: r for r in results}
    if "case-root" in by_id:
        r = by_id["case-root"]
        assert r["struct_match"] is True
        # Should be same_root_cause because root_cause matches + struct match
        assert r["relation"] in (
            CaseRelationType.SAME_ROOT_CAUSE.value,
            CaseRelationType.SIMILAR_DIAGNOSIS.value,
        ), f"expected typed relation, got {r['relation']}"

    if "case-surface" in by_id:
        r = by_id["case-surface"]
        # Different failure_layer + different runtime → likely surface_similar
        assert r["relation"] == CaseRelationType.SURFACE_SIMILAR.value, (
            f"expected surface_similar for mismatched struct, got {r['relation']}"
        )
