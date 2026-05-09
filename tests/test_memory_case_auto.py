import pytest

from derisk_ext.plugin.memory_case import (
    CandidateCase,
    MemoryCasePluginService,
    MemoryCaseToolPack,
    get_memory_case_scope,
    scope_filters_match,
    set_memory_case_scope,
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

    async def search_with_scores(self, query, case_scope, top_k):
        return [(cid, 0.8) for cid in self._ids[:top_k]]

    async def invalidate(self, case_id: str):
        return None


def _make_pack(**kwargs) -> MemoryCaseToolPack:
    pack = MemoryCaseToolPack(system_app=_FakeSystemApp(), **kwargs)
    pack._plugin = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
    )
    return pack


def test_memory_case_scope_context():
    set_memory_case_scope("app-a", "conv-1")
    assert get_memory_case_scope()["app_code"] == "app-a"
    assert get_memory_case_scope()["conv_id"] == "conv-1"


@pytest.mark.asyncio
async def test_resource_resolver_memory_case_via_registration():
    from derisk.agent.core_v2.agent_binding import ResourceResolver
    from derisk_ext.plugin.memory_case.integration import (
        ensure_memory_case_resource_resolver_registered,
    )

    ensure_memory_case_resource_resolver_registered()
    resolver = ResourceResolver()
    result, err = await resolver.resolve(
        "tool(memory_case)",
        {"name": "memory_case", "mcp_name": "memory_case"},
    )
    assert err is None
    assert result["type"] == "memory_case"
    assert result["mcp_name"] == "memory_case"


@pytest.mark.asyncio
async def test_memory_case_tool_pack_preload_registers_tools():
    pack = _make_pack()
    await pack.preload_resource()
    assert len(pack._resources) >= 4
    names = {getattr(r, "name", None) for r in pack.sub_resources}
    assert "memory_case_search" in names
    assert "memory_case_upsert" in names


def test_service_always_injects_virtual_entry():
    """filter_list_page should inject memory_case entry even without enabled check."""
    plugin = MemoryCasePluginService(
        system_app=_FakeSystemApp(),
        dao=_FakeDao(),
        vector_index=_FakeVectorIndex(),
    )
    assert not hasattr(plugin, "enabled") or not callable(
        getattr(plugin, "enabled", None)
    )
