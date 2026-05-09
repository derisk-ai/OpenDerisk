"""Test MemoryCaseDao.upsert() with a real SQLite database — verify that inserting
new records does NOT delete existing ones.
"""

import pytest
from sqlalchemy import create_engine

from derisk.storage.metadata.db_manager import db as global_db
from derisk.storage.metadata import Model as GlobalModel

from derisk_ext.plugin.memory_case.models import CandidateCase, CandidateCaseLifecycle
from derisk_ext.plugin.memory_case.sqlalchemy_dao import MemoryCaseDao, MemoryCaseEntity


@pytest.fixture
def dao():
    """Create a MemoryCaseDao backed by a throwaway SQLite in-memory database.

    Since MemoryCaseEntity inherits from the global db.Model, we must
    temporarily repoint the global db to a test engine and create tables there.
    """
    old_engine = global_db._engine
    old_session = global_db._session

    test_engine = create_engine("sqlite:///:memory:")
    global_db._engine = test_engine
    global_db._session = None  # force re-init below

    from sqlalchemy.orm import sessionmaker, Session
    from derisk.storage.metadata.db_manager import BaseQuery
    session_factory = sessionmaker(
        bind=test_engine, class_=Session, query_cls=BaseQuery
    )
    global_db._session = session_factory

    # Create the table on the test engine
    GlobalModel.metadata.create_all(test_engine)

    try:
        yield MemoryCaseDao()
    finally:
        global_db._engine = old_engine
        global_db._session = old_session
        test_engine.dispose()


def _make_case(case_id: str, symptom: str, confidence: float = 0.5) -> CandidateCase:
    return CandidateCase(
        case_id=case_id,
        symptom_summary=symptom,
        confidence=confidence,
    )


def test_upsert_five_records_keeps_previous_four(dao):
    # --- insert 4 records ---
    for i in range(1, 5):
        case = _make_case(case_id=f"case-{i}", symptom=f"issue #{i}", confidence=0.6)
        saved = dao.upsert(case)
        assert saved.case_id == f"case-{i}"

    # verify 4 exist
    assert dao.get_by_case_id("case-1") is not None
    assert dao.get_by_case_id("case-2") is not None
    assert dao.get_by_case_id("case-3") is not None
    assert dao.get_by_case_id("case-4") is not None

    # --- insert 5th record ---
    case5 = _make_case(case_id="case-5", symptom="new issue #5", confidence=0.7)
    dao.upsert(case5)

    # verify all 5 still exist (old 4 are NOT deleted)
    for i in range(1, 6):
        found = dao.get_by_case_id(f"case-{i}")
        assert found is not None, f"case-{i} should still exist after inserting case-5"

    # also spot-check field values of an old record
    c1 = dao.get_by_case_id("case-1")
    assert c1.symptom_summary == "issue #1"
    assert c1.confidence == 0.6


def test_upsert_existing_record_does_not_delete_others(dao):
    # same as above but simulate a merge (same case_id)
    for i in range(1, 4):
        dao.upsert(_make_case(case_id=f"case-{i}", symptom=f"old #{i}"))

    # merge case-2: update resolution only
    merged = CandidateCase(
        case_id="case-2",
        symptom_summary="",  # should NOT overwrite
        resolution="merged resolution",
        confidence=0.8,
    )
    dao.upsert(merged)

    # old records still exist
    assert dao.get_by_case_id("case-1") is not None
    assert dao.get_by_case_id("case-3") is not None

    # merged record: symptom preserved, resolution updated
    c2 = dao.get_by_case_id("case-2")
    assert c2.symptom_summary == "old #2", "existing symptom should be preserved"
    assert c2.resolution == "merged resolution", "new resolution should be set"
    assert c2.confidence == 0.8, "confidence should be updated"


def test_upsert_concurrent_like_scenario(dao):
    """Simulate the Agent writing many cases in rapid succession with different metadata."""
    import json

    base_data = [
        {"case_id": "case-a", "symptom": "CPU 飙升", "metadata": {"case_context": {"app_code": "app1", "environment": "prod"}}},
        {"case_id": "case-b", "symptom": "OOM Kill", "metadata": {"case_context": {"app_code": "app1", "environment": "prod"}}},
        {"case_id": "case-c", "symptom": "Disk full", "metadata": {"case_context": {"app_code": "app2", "environment": "prod"}}},
        {"case_id": "case-d", "symptom": "Latency spike", "metadata": {"case_context": {"app_code": "app1", "environment": "staging"}}},
    ]

    for item in base_data:
        case = CandidateCase(**item)
        dao.upsert(case)

    # verify 4 records
    results = dao.search(scope={"app_code": "default"}, limit=50)
    assert len(results) == 4, f"Expected 4 records before new insert, got {len(results)}"

    # insert 5th
    new_case = CandidateCase(
        case_id="case-e",
        symptom_summary="Network timeout",
        metadata={"case_context": {"app_code": "app1", "environment": "prod"}},
    )
    dao.upsert(new_case)

    # verify all 5 still exist
    results_after = dao.search(scope={"app_code": "default"}, limit=50)
    assert len(results_after) == 5, (
        f"Expected 5 records after insert, got {len(results_after)}. "
        f"Found case_ids: {[r.case_id for r in results_after]}"
    )

    # verify individual lookup
    for cid in ["case-a", "case-b", "case-c", "case-d", "case-e"]:
        assert dao.get_by_case_id(cid) is not None, f"{cid} should exist"


def test_stress_many_upserts_never_delete_old_records(dao):
    """Stress-test: insert 20 records one by one, each time verify all previous exist."""
    ids_inserted = []
    for i in range(20):
        cid = f"stress-{i}"
        dao.upsert(_make_case(case_id=cid, symptom=f"stress symptom {i}"))
        ids_inserted.append(cid)
        # verify all previously inserted still exist
        for prev_cid in ids_inserted:
            assert dao.get_by_case_id(prev_cid) is not None, (
                f"{prev_cid} disappeared after inserting {cid}"
            )
    # final verification: all 20 exist
    results = dao.search(scope={"app_code": "default"}, limit=100)
    assert len(results) == 20, f"Expected 20, got {len(results)}"


def test_full_service_upsert_flow_with_real_dao(dao):
    """Exercise the complete service._upsert → dao path (no vector store)."""
    from derisk_ext.plugin.memory_case.service import MemoryCasePluginService

    class _DummySystemApp:
        config = {}

    class _FakeVector:
        async def upsert(self, case): pass
        async def search(self, query, scope, top_k): return []
        async def search_with_scores(self, query, scope, top_k): return []
        async def invalidate(self, case_id): pass

    service = MemoryCasePluginService(
        system_app=_DummySystemApp(),
        dao=dao,
        vector_index=_FakeVector(),
    )

    # Write 4 cases through the service (same path the Agent uses)
    import asyncio
    for i in range(1, 5):
        result = asyncio.get_event_loop().run_until_complete(
            service.call_tool("memory_case_upsert", {
                "case": {
                    "case_id": f"svc-{i}",
                    "symptom_summary": f"service issue {i}",
                    "resolution": f"fix {i}",
                    "metadata": {"case_context": {"app_code": "demo", "environment": "prod"}},
                }
            })
        )
        assert result["code"] == "OK"
        assert result["case"]["case_id"] == f"svc-{i}"

    # Verify 4 exist
    results = dao.search(scope={"app_code": "default"}, limit=50)
    assert len(results) == 4, f"Expected 4, got {len(results)}"

    # Write 5th
    result = asyncio.get_event_loop().run_until_complete(
        service.call_tool("memory_case_upsert", {
            "case": {
                "case_id": "svc-5",
                "symptom_summary": "new service issue",
                "metadata": {"case_context": {"app_code": "demo", "environment": "prod"}},
            }
        })
    )
    assert result["code"] == "OK"

    # Verify ALL 5 still exist
    results_after = dao.search(scope={"app_code": "default"}, limit=50)
    assert len(results_after) == 5, (
        f"CRITICAL: Expected 5 records, got {len(results_after)}. "
        f"Found: {[r.case_id for r in results_after]}"
    )
    for i in range(1, 6):
        found = dao.get_by_case_id(f"svc-{i}")
        assert found is not None, f"svc-{i} disappeared after 5th insert"

    # Spot-check: old record field values preserved
    c1 = dao.get_by_case_id("svc-1")
    assert c1.symptom_summary == "service issue 1"
    assert c1.resolution == "fix 1"


def test_search_with_narrow_scope_does_not_mistake_scoping_for_deletion(dao):
    """Scope filters narrow results — this is expected, not data loss."""
    cases = [
        CandidateCase(case_id="c1", symptom_summary="A", metadata={"case_context": {"app_code": "team-x"}}),
        CandidateCase(case_id="c2", symptom_summary="B", metadata={"case_context": {"app_code": "team-x"}}),
        CandidateCase(case_id="c3", symptom_summary="C", metadata={"case_context": {"app_code": "team-y"}}),
    ]
    for c in cases:
        dao.upsert(c)

    # search with team-x scope → returns 2
    r_x = dao.search(scope={"app_code": "team-x"}, limit=10)
    assert len(r_x) == 2, f"team-x should see 2 cases, got {len(r_x)}"

    # search with team-y scope → returns 1
    r_y = dao.search(scope={"app_code": "team-y"}, limit=10)
    assert len(r_y) == 1

    # search with default scope → returns ALL 3
    r_all = dao.search(scope={"app_code": "default"}, limit=10)
    assert len(r_all) == 3, f"default scope should see all 3, got {len(r_all)}"
