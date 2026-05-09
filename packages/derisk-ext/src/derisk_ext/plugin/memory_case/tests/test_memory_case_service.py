import math
import time
from datetime import UTC, datetime, timedelta
from typing import Dict, Optional

import pytest

from derisk_ext.plugin.memory_case import (
    FB_KEY,
    FB_LAMBDA_ACCEPTED,
    FB_MIN_SAMPLES,
    CandidateCase,
    CandidateCaseLifecycle,
    CaseRelationType,
    FeedbackStats,
    MemoryCasePluginService,
    cross_validate_relation,
    scope_filters_match,
    wilson_score,
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


# ---------------------------------------------------------------------------
# wilson_score unit tests
# ---------------------------------------------------------------------------


def test_wilson_score_zero_total():
    assert wilson_score(0, 0) == 0.0


def test_wilson_score_perfect_small_sample_low_confidence():
    """2/2 helpful is not trustworthy — Wilson lower bound should be << 1.0."""
    score = wilson_score(2, 2)
    assert score < 0.5, f"expected low score for small sample, got {score}"


def test_wilson_score_perfect_large_sample_high_confidence():
    """15/15 helpful should be trustworthy — Wilson lower bound > 0.7."""
    score = wilson_score(15, 15)
    assert score > 0.7, f"expected high score for large sample, got {score}"


def test_wilson_score_mixed():
    """8/10 should be lower than simple ratio 0.8."""
    score = wilson_score(8, 10)
    assert score < 0.8


def test_wilson_score_large_beats_small():
    """15/15 should rank above 2/2 despite both being "100% helpful"."""
    assert wilson_score(15, 15) > wilson_score(2, 2)


# ---------------------------------------------------------------------------
# fb structure helpers
# ---------------------------------------------------------------------------


def _make_case(
    case_id: str,
    confidence: float = 0.85,
    lifecycle: CandidateCaseLifecycle = CandidateCaseLifecycle.DRAFT,
    app_code: str = "order-svc",
    environment: str = "production",
    source_conv_id: str = "",
    metadata: Optional[Dict] = None,
    updated_at: Optional[datetime] = None,
) -> CandidateCase:
    meta = dict(metadata or {})
    meta.setdefault("case_context", {
        "app_code": app_code,
        "environment": environment,
    })
    return CandidateCase(
        case_id=case_id,
        fingerprint=f"fp-{case_id}",
        symptom_summary="test symptom",
        confidence=confidence,
        lifecycle=lifecycle,
        source_conv_id=source_conv_id,
        metadata=meta,
        updated_at=updated_at,
    )


def test_ensure_fb_structure_from_empty():
    case = _make_case("case-1")
    fb = MemoryCasePluginService._ensure_fb_structure(case)
    assert fb["global"] == {"h": 0, "u": 0, "ts": "", "cv": []}
    assert fb["by_app"] == {}
    assert fb["by_app_env"] == {}


def test_ensure_fb_structure_preserves_existing():
    case = _make_case("case-1", metadata={
        "case_context": {"app_code": "demo", "environment": "prod"},
        FB_KEY: {"global": {"h": 3, "u": 1, "ts": "2026-01-01T00:00:00Z", "cv": ["c1"]}},
    })
    fb = MemoryCasePluginService._ensure_fb_structure(case)
    assert fb["global"]["h"] == 3
    assert fb["by_app"] == {}
    assert fb["by_app_env"] == {}


def test_record_fb_event_three_levels():
    case = _make_case("case-1", app_code="order-svc", environment="production")
    fb = MemoryCasePluginService._ensure_fb_structure(case)

    fb = MemoryCasePluginService._record_fb_event(
        fb, case, helpful=True, conv_id="conv-new", is_cross_session=True
    )
    # global
    assert fb["global"]["h"] == 1
    assert fb["global"]["u"] == 0
    assert "conv-new" in fb["global"]["cv"]
    # by_app
    assert fb["by_app"]["order-svc"]["h"] == 1
    # by_app_env
    assert fb["by_app_env"]["order-svc:production"]["h"] == 1


def test_record_fb_event_unhelpful():
    case = _make_case("case-1", app_code="demo", environment="staging")
    fb = MemoryCasePluginService._ensure_fb_structure(case)

    fb = MemoryCasePluginService._record_fb_event(
        fb, case, helpful=False, conv_id="c1", is_cross_session=True
    )
    assert fb["global"]["u"] == 1
    assert fb["by_app"]["demo"]["u"] == 1
    assert fb["by_app_env"]["demo:staging"]["u"] == 1


def test_record_fb_event_dedup_conv_id():
    case = _make_case("case-1", source_conv_id="conv-source")
    fb = MemoryCasePluginService._ensure_fb_structure(case)
    # first feedback (cross session)
    fb = MemoryCasePluginService._record_fb_event(
        fb, case, helpful=True, conv_id="conv-a", is_cross_session=True
    )
    # same conv_id again
    fb = MemoryCasePluginService._record_fb_event(
        fb, case, helpful=True, conv_id="conv-a", is_cross_session=True
    )
    assert fb["global"]["cv"] == ["conv-a"]


# ---------------------------------------------------------------------------
# scope-aware fb lookup
# ---------------------------------------------------------------------------


def test_lookup_fb_stats_exact_scope_match():
    fb = {
        "global": {"h": 10, "u": 10, "ts": ""},
        "by_app_env": {
            "order-svc:production": {"h": 5, "u": 0, "ts": "2026-05-01T00:00:00Z"},
        },
    }
    stats = MemoryCasePluginService._lookup_fb_stats(
        fb, {"app_code": "order-svc", "environment": "production"}
    )
    assert stats is not None
    assert stats.h == 5
    assert stats.total >= FB_MIN_SAMPLES


def test_lookup_fb_stats_falls_back_to_by_app():
    fb = {
        "global": {"h": 10, "u": 10, "ts": ""},
        "by_app": {
            "trade-svc": {"h": 8, "u": 2, "ts": "2026-05-01T00:00:00Z"},
        },
    }
    # by_app_env doesn't have the key, so falls back to by_app
    stats = MemoryCasePluginService._lookup_fb_stats(
        fb, {"app_code": "trade-svc", "environment": "staging"}
    )
    assert stats is not None
    assert stats.h == 8  # from by_app fallback


def test_lookup_fb_stats_falls_back_to_global():
    fb = {
        "global": {"h": 5, "u": 2, "ts": "2026-05-01T00:00:00Z"},
    }
    stats = MemoryCasePluginService._lookup_fb_stats(
        fb, {"app_code": "unknown-svc", "environment": "production"}
    )
    assert stats is not None
    assert stats.h == 5  # from global fallback


def test_lookup_fb_stats_insufficient_samples_skips_level():
    """by_app_env has 1 total (< FB_MIN_SAMPLES) → skip to by_app → skip to global."""
    fb = {
        "global": {"h": 6, "u": 2, "ts": ""},
        "by_app_env": {
            "order-svc:production": {"h": 1, "u": 0, "ts": ""},  # total=1 < 3
        },
        "by_app": {
            "order-svc": {"h": 2, "u": 0, "ts": ""},  # total=2 < 3
        },
    }
    stats = MemoryCasePluginService._lookup_fb_stats(
        fb, {"app_code": "order-svc", "environment": "production"}
    )
    assert stats is not None
    assert stats.h == 6  # from global (both by_app_env and by_app insufficient)


def test_lookup_fb_stats_returns_none_for_no_feedback():
    fb = {"global": {"h": 0, "u": 0, "ts": "", "cv": []}}
    stats = MemoryCasePluginService._lookup_fb_stats(
        fb, {"app_code": "any", "environment": "any"}
    )
    assert stats is None


# ---------------------------------------------------------------------------
# rank score computation
# ---------------------------------------------------------------------------


def test_compute_rank_score_no_feedback_uses_confidence():
    case = _make_case("case-1", confidence=0.72)
    scope = {"app_code": "order-svc", "environment": "production"}
    score = MemoryCasePluginService._compute_rank_score(case, scope)
    # No feedback → base is confidence, no time decay (no ts)
    assert score == pytest.approx(0.72, abs=0.01)


def test_compute_rank_score_with_enough_feedback():
    case = _make_case(
        "case-1",
        confidence=0.85,
        metadata={
            "case_context": {"app_code": "order-svc", "environment": "production"},
            FB_KEY: {
                "global": {"h": 8, "u": 2, "ts": "2026-05-09T00:00:00Z", "cv": ["c1", "c2"]},
                "by_app_env": {
                    "order-svc:production": {"h": 8, "u": 2, "ts": "2026-05-09T00:00:00Z"},
                },
            },
        },
    )
    scope = {"app_code": "order-svc", "environment": "production"}
    score = MemoryCasePluginService._compute_rank_score(case, scope)
    # Wilson(8,10) ≈ 0.49, weight=1.0, so base≈0.49; decay near 1.0 since today
    w = wilson_score(8, 10)
    expected = w * 1.0 + 0.85 * 0.0  # weight=1.0 because total=10 >= FB_WEIGHT_CAP
    assert score == pytest.approx(expected, abs=0.01)


def test_compute_rank_score_blends_prior_with_few_samples():
    """total=4 (< FB_WEIGHT_CAP=10): weight=0.4 → 0.4*empirical + 0.6*confidence."""
    case = _make_case(
        "case-1",
        confidence=0.80,
        metadata={
            "case_context": {"app_code": "order-svc", "environment": "production"},
            FB_KEY: {
                "by_app_env": {
                    "order-svc:production": {"h": 3, "u": 1, "ts": "2026-05-09T00:00:00Z"},
                },
            },
        },
    )
    scope = {"app_code": "order-svc", "environment": "production"}
    score = MemoryCasePluginService._compute_rank_score(case, scope)
    w = wilson_score(3, 4)
    weight = 4.0 / 10.0  # 0.4
    expected = weight * w + (1.0 - weight) * 0.80
    assert score == pytest.approx(expected, abs=0.01)


def test_compute_rank_score_time_decay():
    case = _make_case(
        "case-1",
        confidence=0.85,
        lifecycle=CandidateCaseLifecycle.ACCEPTED,
        updated_at=datetime.now(UTC) - timedelta(days=100),
        metadata={
            "case_context": {"app_code": "order-svc", "environment": "production"},
        },
    )
    scope = {"app_code": "order-svc", "environment": "production"}
    score = MemoryCasePluginService._compute_rank_score(case, scope)
    # confidence 0.85 * exp(-0.001 * 100) ≈ 0.85 * 0.9048 ≈ 0.769
    expected_decay = math.exp(-FB_LAMBDA_ACCEPTED * 100)
    expected = 0.85 * expected_decay
    assert score == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------------------
# feedback lifecycle gating tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_stays_draft_after_single_helpful():
    """One helpful feedback should NOT promote to ACCEPTED (need >=2 + cross-session)."""
    dao = _FakeDao()
    case = _make_case("case-1", confidence=0.90, source_conv_id="conv-source")
    dao.upsert(case)

    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(), dao=dao, vector_index=_FakeVectorIndex()
    )
    result = await service.call_tool(
        "memory_case_feedback",
        {
            "case_id": "case-1",
            "helpful": True,
            "conv_id": "conv-different",  # cross-session
        },
    )
    saved = result["case"]
    # confidence bumped
    assert saved["confidence"] == 1.0
    # still DRAFT — single feedback insufficient
    assert saved["lifecycle"] == CandidateCaseLifecycle.DRAFT.value


@pytest.mark.asyncio
async def test_feedback_promotes_to_accepted_after_two_cross_session():
    """Two cross-session helpful feedbacks + confidence>=0.8 → ACCEPTED."""
    dao = _FakeDao()
    case = _make_case("case-1", confidence=0.85, source_conv_id="conv-source")
    dao.upsert(case)

    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(), dao=dao, vector_index=_FakeVectorIndex()
    )
    # First cross-session feedback
    await service.call_tool(
        "memory_case_feedback",
        {"case_id": "case-1", "helpful": True, "conv_id": "conv-a"},
    )
    # Second cross-session feedback
    result = await service.call_tool(
        "memory_case_feedback",
        {"case_id": "case-1", "helpful": True, "conv_id": "conv-b"},
    )
    saved = result["case"]
    assert saved["lifecycle"] == CandidateCaseLifecycle.ACCEPTED.value
    # fb recorded correctly
    assert saved["metadata"][FB_KEY]["global"]["h"] == 2
    assert len(saved["metadata"][FB_KEY]["global"]["cv"]) == 2


@pytest.mark.asyncio
async def test_feedback_same_session_does_not_increment_cv():
    """Feedback from the same session as source should not count as cross-session."""
    dao = _FakeDao()
    case = _make_case("case-1", confidence=0.85, source_conv_id="conv-same")
    dao.upsert(case)

    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(), dao=dao, vector_index=_FakeVectorIndex()
    )
    result = await service.call_tool(
        "memory_case_feedback",
        {"case_id": "case-1", "helpful": True, "conv_id": "conv-same"},
    )
    saved = result["case"]
    # h is incremented
    assert saved["metadata"][FB_KEY]["global"]["h"] == 1
    # but cv is empty (same session)
    assert saved["metadata"][FB_KEY]["global"]["cv"] == []
    # still DRAFT — no cross-session feedback
    assert saved["lifecycle"] == CandidateCaseLifecycle.DRAFT.value


@pytest.mark.asyncio
async def test_feedback_reject_low_confidence():
    """helpful=False drops confidence, and below 0.2 → REJECTED."""
    dao = _FakeDao()
    case = _make_case("case-1", confidence=0.25, source_conv_id="conv-src")
    dao.upsert(case)

    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(), dao=dao, vector_index=_FakeVectorIndex()
    )
    result = await service.call_tool(
        "memory_case_feedback",
        {"case_id": "case-1", "helpful": False},
    )
    saved = result["case"]
    # confidence: 0.25 - 0.2 = 0.05 < 0.2 → REJECTED
    assert saved["confidence"] == pytest.approx(0.05)
    assert saved["lifecycle"] == CandidateCaseLifecycle.REJECTED.value
    assert saved["metadata"][FB_KEY]["global"]["u"] == 1


@pytest.mark.asyncio
async def test_feedback_stale_signal_overrides_lifecycle():
    dao = _FakeDao()
    case = _make_case("case-1", confidence=0.85, source_conv_id="conv-src")
    dao.upsert(case)

    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(), dao=dao, vector_index=_FakeVectorIndex()
    )
    result = await service.call_tool(
        "memory_case_feedback",
        {"case_id": "case-1", "helpful": True, "signal": "stale"},
    )
    saved = result["case"]
    assert saved["lifecycle"] == CandidateCaseLifecycle.STALE.value
    assert saved["confidence"] == pytest.approx(0.85)  # +0.1(helpful) -0.1(stale)


# ---------------------------------------------------------------------------
# upsert strips system-managed keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_strips_fb_and_similar_cases():
    """LLM-injected fb and similar_cases must be discarded during upsert."""
    dao = _FakeDao()
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(), dao=dao, vector_index=_FakeVectorIndex()
    )
    result = await service.call_tool(
        "memory_case_upsert",
        {
            "case": {
                "case_id": "case-strip",
                "symptom_summary": "test",
                "confidence": 0.7,
                "metadata": {
                    "case_context": {"app_code": "demo", "environment": "prod"},
                    FB_KEY: {"global": {"h": 999, "u": 0, "ts": "", "cv": ["fake"]}},
                    "similar_cases": [{"case_id": "fake", "score": 1.0}],
                },
            }
        },
    )
    saved_meta = result["case"]["metadata"]
    # fb stripped — should be empty (not present since system didn't set it)
    assert FB_KEY not in saved_meta
    # similar_cases stripped — would be empty unless _find_similar_cases found something
    assert "similar_cases" not in saved_meta
