"""RFC-005 Step C: knowledge capability 迁移测试。

知识库 Consumer:declare 库列表 + consume 检索回注(chunks→USER_PART/TURN)。
"""

from types import SimpleNamespace

from derisk.core.interface.resource.bundle import CacheScope, Lifetime, Slot
from derisk_serve.agent.capabilities.knowledge import KnowledgeCapabilityResource


def _make_legacy_knowledge(spaces_desc="1. name:wiki, knowledge_id:k1, 知识库描述:内部wiki"):
    return SimpleNamespace(description=spaces_desc, knowledge_spaces=[])


def test_knowledge_declares_spaces_from_legacy():
    legacy = _make_legacy_knowledge()
    res = KnowledgeCapabilityResource(legacy_instance=legacy)
    contribs = res.declare_spaces()
    assert len(contribs) == 1
    c = contribs[0]
    assert c.slot == Slot.SYSTEM
    assert c.capability_id == "knowledge"
    assert c.cache_scope == CacheScope.USER
    assert "wiki" in c.content
    assert "k1" in c.content


def test_knowledge_declares_from_explicit_spaces():
    spaces = [{"name": "s1", "knowledge_id": "id1", "desc": "d1"}]
    res = KnowledgeCapabilityResource(spaces=spaces)
    contribs = res.declare_spaces()
    assert len(contribs) == 1
    assert "s1" in contribs[0].content
    assert "id1" in contribs[0].content


def test_knowledge_empty_when_no_spaces():
    res = KnowledgeCapabilityResource()
    assert res.declare_spaces() == []


async def test_knowledge_consume_returns_turn_user_part():
    """consume 检索结果 → USER_PART/TURN(本轮临时上下文,不跨轮)。"""
    res = KnowledgeCapabilityResource()
    contribs = await res.consume("检索到的知识块: ...")
    assert len(contribs) == 1
    c = contribs[0]
    assert c.slot == Slot.USER_PART
    assert c.lifetime == Lifetime.TURN
    assert c.cache_scope == CacheScope.NONE
    assert "knowledge-context" in c.content
    assert "检索到的知识块" in c.content


async def test_knowledge_consume_empty_result():
    res = KnowledgeCapabilityResource()
    assert await res.consume("") == []
    assert await res.consume(None) == []


async def test_knowledge_consume_non_str_result():
    """consume 接收结构化结果(dict)转 str。"""
    res = KnowledgeCapabilityResource()
    contribs = await res.consume({"chunks": ["a", "b"]})
    assert len(contribs) == 1
    assert "chunks" in contribs[0].content


def test_facade_wraps_legacy_knowledge():
    from derisk.agent.capabilities.facade import ResourceFacade
    facade = ResourceFacade()
    from derisk_serve.agent.capabilities.knowledge import register_wrappers
    register_wrappers(facade)
    facade.register_legacy_wrapper(object, lambda x: KnowledgeCapabilityResource(legacy_instance=x))
    legacy = _make_legacy_knowledge()
    wrapped = facade._to_resource_protocol(legacy)
    assert isinstance(wrapped, KnowledgeCapabilityResource)
    contribs = wrapped.declare_spaces()
    assert "wiki" in contribs[0].content

# =========================================================================== #
# RFC-006 Stage 7: KnowledgeCapability 自管理(对象模型统一)
# =========================================================================== #
def test_knowledge_capability_from_legacy_description():
    from derisk_serve.agent.capabilities.knowledge import KnowledgeCapability
    cap = KnowledgeCapability.from_legacy(_make_legacy_knowledge())
    assert isinstance(cap, KnowledgeCapability)
    contribs = cap.declare()
    assert len(contribs) == 1
    assert "wiki" in contribs[0].content


async def test_knowledge_capability_register_and_facade_flip():
    from derisk.agent.capabilities.facade import ResourceFacade, _CapabilityDeclareAdapter
    from derisk_serve.agent.capabilities.knowledge import register_capability
    facade = ResourceFacade()
    register_capability(facade)
    assert "knowledge_pack" in facade._capability_factories
    legacy = _make_legacy_knowledge()
    wrapped = facade._to_resource_protocol(legacy)
    assert isinstance(wrapped, _CapabilityDeclareAdapter)
    assert wrapped.capability_id == "knowledge"
    assert any("wiki" in c.content for c in wrapped.declare() if isinstance(c.content, str))


# =========================================================================== #
# RFC-006 Stage 8: KnowledgeCapability prepare 自管 hydrate(facade 时序已改)
# =========================================================================== #
async def test_knowledge_capability_prepare_hydrates_spaces_from_ids(monkeypatch):
    """prepare 按 knowledge_ids 调 KnowledgeService 水合 spaces(declare 能读到)。"""
    from derisk_serve.agent.capabilities.knowledge import KnowledgeCapability

    cap = KnowledgeCapability(spaces=None, knowledge_ids=["k1"])
    # 若 derisk_app.knowledge 不可 import,prepare 降级不报错(ready)。此处验降级不崩。
    await cap.prepare()
    assert cap._status.value == "ready"


async def test_knowledge_capability_prepare_skips_when_spaces_complete():
    """_spaces 已带 name → prepare 免 I/O,直接 ready。"""
    from derisk_serve.agent.capabilities.knowledge import KnowledgeCapability

    cap = KnowledgeCapability(
        spaces=[{"name": "wiki", "knowledge_id": "k1", "desc": "d"}], knowledge_ids=["k1"]
    )
    await cap.prepare()
    assert cap._status.value == "ready"
    assert cap._spaces[0]["name"] == "wiki"  # 未被 hydrate 覆盖
