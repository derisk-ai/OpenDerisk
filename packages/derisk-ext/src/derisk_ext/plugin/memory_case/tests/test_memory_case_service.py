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
    async def upsert(self, case: CandidateCase):
        return None

    async def search(self, query: str, case_scope: dict, top_k: int):
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
