"""RFC-005 Step D / RFC-006 Stage 5: memory capability 测试。

记忆:declare 空(配置载体)+ consume 检索回注(memory_context→USER_PART/SESSION)。
"""

from types import SimpleNamespace

import pytest

from derisk.core.interface.resource.bundle import CacheScope, Lifetime, Slot
from derisk.agent.capabilities.memory import MemoryCapability, MemoryCapabilityResource


def test_memory_declare_empty():
    """记忆资源不产 system(static_block 走 memory_pipeline 独立路径)。"""
    res = MemoryCapabilityResource(legacy_instance=SimpleNamespace())
    assert res.declare(None) == []
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


# =========================================================================== #
# RFC-006 Stage 5:MemoryCapability 自管理对象模型(最小占位)
# =========================================================================== #
def test_memory_capability_declare_empty():
    cap = MemoryCapability()
    assert cap.declare() == []
    assert cap.capability_id == "memory"
    assert cap.executor_id == "memory"


def test_memory_capability_from_legacy():
    """from_legacy 读旧 MemoryResource.memory_params() 产 MemoryCapability。"""
    legacy = SimpleNamespace(memory_params=lambda: {"top_k": 5})
    cap = MemoryCapability.from_legacy(legacy)
    assert isinstance(cap, MemoryCapability)
    assert cap._memory_params == {"top_k": 5}


async def test_memory_capability_consume():
    cap = MemoryCapability()
    contribs = await cap.consume("ctx")
    assert len(contribs) == 1
    assert "memory-context" in contribs[0].content
    assert contribs[0].lifetime == Lifetime.SESSION


def test_memory_capability_prepare_release():
    import asyncio
    from derisk.core.interface.resource.executor import ExecutorStatus, ReleaseReason

    cap = MemoryCapability()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(cap.prepare())
    assert cap._status == ExecutorStatus.READY
    loop.run_until_complete(cap.release(ReleaseReason.SESSION_END))
    assert cap._status == ExecutorStatus.RELEASED


def test_memory_capability_execute_not_implemented():
    """execute 未接 store(memory_* 工具暂走 MemoryToolPack builtin)。"""
    import asyncio
    from derisk.core.interface.resource.executor import ExecutorCall

    cap = MemoryCapability()
    with pytest.raises(NotImplementedError):
        asyncio.get_event_loop().run_until_complete(
            cap.execute(ExecutorCall(executor_id="memory", capability_id="memory", tool_name="memory_search", args={}))
        )


async def test_register_capability_and_legacy_provider():
    from derisk.agent.capabilities.facade import ResourceFacade
    from derisk.agent.capabilities.memory import register_capability

    facade = ResourceFacade()
    register_capability(facade)
    assert "memory" in facade._capability_factories


async def test_facade_flips_legacy_memory_to_capability():
    """旧 MemoryResource 实例 → facade 翻成 MemoryCapability(经 provider)。"""
    from derisk.agent.capabilities.facade import ResourceFacade, _CapabilityDeclareAdapter
    from derisk.agent.capabilities.memory import register_capability
    from derisk.agent.resource.memory import MemoryResource

    facade = ResourceFacade()
    register_capability(facade)
    # 构造一个真 MemoryResource 实例
    legacy = MemoryResource(name="mem")
    wrapped = facade._to_resource_protocol(legacy)
    assert isinstance(wrapped, _CapabilityDeclareAdapter)
    assert wrapped.capability_id == "memory"
    assert wrapped.declare() == []
    assert "memory" in facade.executor_provider