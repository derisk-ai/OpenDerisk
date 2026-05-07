
import pytest

from derisk_ext.plugin.memory_case import (
    CandidateCase,
    CandidateCaseLifecycle,
    MemoryCasePluginService,
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
    def __init__(self):
        self._ids = []

    async def upsert(self, case: CandidateCase):
        self._ids.append(case.case_id)

    async def search(self, query: str, case_scope: dict, top_k: int):
        return list(self._ids)[:top_k]

    async def invalidate(self, case_id: str):
        return None


@pytest.mark.asyncio
async def test_lifecycle_and_feedback_review_flag():
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
    )
    upserted = await service.call_tool(
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
    assert upserted["case"]["lifecycle"] == CandidateCaseLifecycle.DRAFT.value

    feedback = await service.call_tool(
        "memory_case_feedback",
        {"case_id": "case-1", "helpful": False, "signal": "rollback"},
    )
    case = feedback["case"]
    assert case["metadata"]["requires_human_review"] is True
    assert case["confidence"] < 0.35


@pytest.mark.asyncio
async def test_scope_isolation_and_topk_trim():
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
    )
    for idx in range(6):
        await service.call_tool(
            "memory_case_upsert",
            {
                "case": {
                    "case_id": f"case-{idx}",
                    "app_code": "demo",
                    "environment": "prod",
                    "fingerprint": f"f-{idx}",
                    "symptom_summary": "cpu alert",
                    "confidence": 0.7,
                }
            },
        )
    result = await service.call_tool(
        "memory_case_search",
        {"scope": {"app_code": "demo", "environment": "prod"}, "top_k": 3},
    )
    assert result["count"] <= 3


@pytest.mark.asyncio
async def test_markdown_render_fallback():
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
    )
    rendered = await service.call_tool(
        "memory_case_render",
        {
            "cases": [
                {
                    "case_id": "case-2",
                    "app_code": "demo",
                    "environment": "prod",
                    "fingerprint": "f-2",
                    "markdown_summary": "bad markdown without sections",
                }
            ]
        },
    )
    assert rendered["count"] == 1
    assert "bad markdown" in rendered["markdown"]


@pytest.mark.asyncio
async def test_timeout_error_semantics():
    service = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
        timeout_seconds=0,
    )

    with pytest.raises(Exception) as exc:
        await service.call_tool(
            "memory_case_search",
            {"scope": {"app_code": "demo", "environment": "prod"}, "top_k": 1},
        )
    assert "TOOL_TIMEOUT" in str(exc.value)

