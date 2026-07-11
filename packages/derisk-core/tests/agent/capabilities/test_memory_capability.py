"""RFC-005 Step D: memory capability 测试。

记忆:declare 空(配置载体)+ consume 检索回注(memory_context→USER_PART/SESSION)。
"""

from types import SimpleNamespace

from derisk.core.interface.resource.bundle import CacheScope, Lifetime, Slot
from derisk.agent.capabilities.memory import MemoryCapabilityResource


def test_memory_declare_empty():
    """记忆资源不产 system(static_block 走 memory_pipeline 独立路径)。"""
    res = MemoryCapabilityResource(legacy_instance=SimpleNamespace())
    assert res.declare_spaces if hasattr(res, "declare_spaces") else res.declare(None) == []
    # declare 类方法空
    assert MemoryCapabilityResource.declare(None) == []


async def test_memory_consume_returns_session_user_part():
    """consume 记忆检索 → USER_PART/SESSION(会话级参考,跨轮)。"""
    res = MemoryCapabilityResource()
    contribs = await res.consume("用户偏好:简洁回复")
    assert len(contribs) == 1
    c = contribs[0]
    assert c.slot == Slot.USER_PART
    assert c.lifetime == Lifetime.SESSION
    assert c.cache_scope == CacheScope.NONE
    assert "memory-context" in c.content
    assert "用户偏好" in c.content


async def test_memory_consume_empty():
    res = MemoryCapabilityResource()
    assert await res.consume("") == []
    assert await res.consume(None) == []


def test_facade_wraps_legacy_memory():
    from derisk.agent.capabilities.facade import ResourceFacade
    facade = ResourceFacade()
    from derisk.agent.capabilities.memory import register_wrappers
    register_wrappers(facade)
    facade.register_legacy_wrapper(object, lambda x: MemoryCapabilityResource(legacy_instance=x))
    wrapped = facade._to_resource_protocol(SimpleNamespace())
    assert isinstance(wrapped, MemoryCapabilityResource)