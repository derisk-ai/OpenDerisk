"""RFC-005 §3.6 / S9 ResourceFacade 单测。

覆盖:
- 静态快照缓存:同 (agent_id, config_hash) 命中,不重建
- SESSION 运行态叠加不污染静态快照
- 配置变更 invalidate 失效缓存
- end_session 清会话运行态 + release executor
- 无原生 declare(无 wrapper)的子资源 → 空资源层(legacy 桥接已移除)
"""

from typing import Any, List

import pytest

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    FrozenBundle,
    InputBundle,
    Lifetime,
    Slot,
)
from derisk.agent.capabilities.facade import (
    AgentInputsSnapshot,
    ResourceFacade,
    compute_config_hash,
)
from derisk.core.interface.resource.protocol import ResourceProtocol


# --------------------------------------------------------------------------- #
# 假 agent:提供 resource + resource_map,触发桥接兜底
# --------------------------------------------------------------------------- #
class _FakeCustomResource:
    def __init__(self, name="fc", desc="fake custom"):
        self.name = name
        self.scene_description = desc

    def type(self):
        return "fake_custom_type"


class _FakeAgent:
    def __init__(self):
        self.resource = None
        self.resource_map = {"fake_custom_type": [_FakeCustomResource()]}
        self.sandbox_manager = None


# --------------------------------------------------------------------------- #
# config_hash
# --------------------------------------------------------------------------- #
def test_config_hash_stable_for_same_config():
    class R:
        def __init__(self, t, v):
            self.type = t
            self.value = v
            self.name = None
            self.version = "v2"

    a = [R("db", "x"), R("app", "y")]
    b = [R("db", "x"), R("app", "y")]
    assert compute_config_hash(a) == compute_config_hash(b)


def test_config_hash_differs_for_different_config():
    class R:
        def __init__(self, t, v):
            self.type = t
            self.value = v
            self.name = None
            self.version = "v2"

    a = [R("db", "x")]
    b = [R("db", "z")]
    assert compute_config_hash(a) != compute_config_hash(b)


def test_config_hash_empty():
    assert compute_config_hash([]) == "empty"


# --------------------------------------------------------------------------- #
# Facade:静态快照缓存
# --------------------------------------------------------------------------- #
async def test_static_snapshot_cached_on_second_assemble():
    """同 (agent_id, config_hash) 第二次 assemble 命中缓存,frozen 同一对象。"""
    facade = ResourceFacade()
    agent = _FakeAgent()
    cfg = [type("R", (), {"type": "db", "value": "x", "name": None, "version": "v2"})()]

    snap1 = await facade.assemble(
        agent_id="a1", conv_id="c1", agent_resources=cfg, agent=agent,
    )
    snap2 = await facade.assemble(
        agent_id="a1", conv_id="c1", agent_resources=cfg, agent=agent,
    )
    # frozen 命中同一缓存对象
    assert snap1.frozen is snap2.frozen
    assert snap1.config_hash == snap2.config_hash


async def test_session_parts_do_not_pollute_static_snapshot():
    """SESSION 运行态叠加在快照外,不写入缓存,不改 frozen。"""
    facade = ResourceFacade()
    agent = _FakeAgent()
    cfg = [type("R", (), {"type": "db", "value": "x", "name": None, "version": "v2"})()]

    # 写入会话级运行态(模拟多模态加载)
    img = Contribution(
        "img_loader", Slot.USER_PART, {"type": "image"},
        lifetime=Lifetime.SESSION, cache_scope=CacheScope.NONE,
    )
    facade.add_session_part("c1", img)

    snap1 = await facade.assemble(
        agent_id="a1", conv_id="c1", agent_resources=cfg, agent=agent,
    )
    assert img in snap1.session_user_parts

    # 另一会话 c2 不应看到 c1 的 SESSION 内容
    snap2 = await facade.assemble(
        agent_id="a1", conv_id="c2", agent_resources=cfg, agent=agent,
    )
    assert img not in snap2.session_user_parts
    # 静态快照两会话共享(frozen 同对象,因 config_hash 相同)
    assert snap1.frozen is snap2.frozen


async def test_invalidate_config_drops_snapshot():
    """配置变更 invalidate 后,缓存失效、下次重建。"""
    facade = ResourceFacade()
    agent = _FakeAgent()
    cfg = [type("R", (), {"type": "db", "value": "x", "name": None, "version": "v2"})()]

    snap1 = await facade.assemble(
        agent_id="a1", conv_id="c1", agent_resources=cfg, agent=agent,
    )
    facade.invalidate_config("a1", snap1.config_hash)

    snap2 = await facade.assemble(
        agent_id="a1", conv_id="c1", agent_resources=cfg, agent=agent,
    )
    assert snap1.frozen is not snap2.frozen  # 缓存已失效,重建


# --------------------------------------------------------------------------- #
# 无原生 declare 的子资源 → 空资源层(legacy 桥接已移除)
# --------------------------------------------------------------------------- #
async def test_no_native_declare_produces_empty_resource_layer():
    """无 wrapper / declare 为空的资源 → 资源层为空(不再走 LegacyResourceAdapter)。"""
    facade = ResourceFacade()
    agent = _FakeAgent()
    cfg = [type("R", (), {"type": "fake", "value": "x", "name": None, "version": "v2"})()]

    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", agent_resources=cfg, agent=agent,
    )
    assert isinstance(snap.frozen, FrozenBundle)
    # _FakeCustomResource 无 wrapper → 整体资源层 system 为空(空 tuple)
    assert not snap.frozen.system


# --------------------------------------------------------------------------- #
# 原生 declare 资源被 facade 调用
# --------------------------------------------------------------------------- #
async def test_native_declare_resource_is_collected():
    """实现 ResourceProtocol 的资源,其 declare 输出直接进 bundle(不走桥接)。"""

    class _NativeRes(ResourceProtocol):
        capability_id = "native:test"

        @classmethod
        def declare(cls, config: Any) -> List[Contribution]:
            return [
                Contribution(
                    capability_id=cls.capability_id,
                    slot=Slot.SYSTEM,
                    content="native system text",
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.GLOBAL,
                )
            ]

    # 包一个假 pack,is_pack=True、sub_resources=[_NativeRes()]
    native = _NativeRes()

    class _Pack:
        is_pack = True

        @property
        def sub_resources(self):
            return [native]

    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", resource_root=_Pack(),
    )
    texts = [b.text for b in snap.frozen.system]
    assert "native system text" in texts


# --------------------------------------------------------------------------- #
# end_session 清理
# --------------------------------------------------------------------------- #
async def test_end_session_clears_session_parts():
    facade = ResourceFacade()
    agent = _FakeAgent()
    cfg = [type("R", (), {"type": "db", "value": "x", "name": None, "version": "v2"})()]

    img = Contribution(
        "img", Slot.USER_PART, "img",
        lifetime=Lifetime.SESSION, cache_scope=CacheScope.NONE,
    )
    facade.add_session_part("c1", img)
    assert facade._session_store.get("c1")

    await facade.end_session("c1")
    assert facade._session_store.get("c1") is None


def test_add_session_part_rejects_non_session_lifetime():
    facade = ResourceFacade()
    with pytest.raises(ValueError, match="SESSION lifetime"):
        facade.add_session_part(
            "c1",
            Contribution("c", Slot.USER_PART, "x", lifetime=Lifetime.TURN),
        )


async def test_turn_user_parts_merged():
    """本轮 TURN user_parts 进入 snapshot,与 session parts 合并。"""
    facade = ResourceFacade()
    agent = _FakeAgent()
    cfg = [type("R", (), {"type": "db", "value": "x", "name": None, "version": "v2"})()]

    turn = Contribution(
        "rag", Slot.USER_PART, "chunks",
        lifetime=Lifetime.TURN, cache_scope=CacheScope.NONE,
    )
    snap = await facade.assemble(
        agent_id="a1", conv_id="c1", agent_resources=cfg, agent=agent,
        turn_user_parts=[turn],
    )
    assert turn in snap.turn_user_parts
    assert turn in snap.all_user_parts()

# --------------------------------------------------------------------------- #
# S10 四层完整 system 快照(路线B)
# --------------------------------------------------------------------------- #
async def test_full_system_snapshot_layers_ordered():
    """身份(GLOBAL)→控制(GLOBAL)→记忆(USER),按 scope 优先级+order。

    _FakeAgent 的 _FakeCustomResource 无 wrapper,资源层为空(legacy 桥接已移除),
    故本用例验证身份/控制/记忆三层排序。
    """
    facade = ResourceFacade()
    snap = await facade.assemble(
        agent_id="a1", conv_id="c1",
        agent=_FakeAgent(),
        identity="你是助手",
        control_block="## 核心工作流",
        memory_static_block="## 偏好:简洁",
    )
    blocks = snap.full_system_blocks()
    texts = [b.text for b in blocks]
    scopes = [b.cache_scope for b in blocks]
    # GLOBAL 两块在前(身份→控制),USER 记忆在后
    assert texts[0] == "你是助手"
    assert texts[1] == "## 核心工作流"
    assert "## 偏好:简洁" in texts
    assert texts.index("## 偏好:简洁") > texts.index("## 核心工作流")
    assert scopes[0] == CacheScope.GLOBAL
    assert scopes[1] == CacheScope.GLOBAL


async def test_memory_block_not_in_cached_frozen():
    """记忆层会话级,不进 frozen 缓存;身份/控制变才重建 frozen。"""
    facade = ResourceFacade()
    agent = _FakeAgent()
    snap1 = await facade.assemble(
        agent_id="a1", conv_id="c1", agent=agent,
        identity="id", control_block="ctl", memory_static_block="mem1",
    )
    # 同身份/控制不同记忆 → frozen 同对象(记忆不进缓存键)
    snap2 = await facade.assemble(
        agent_id="a1", conv_id="c1", agent=agent,
        identity="id", control_block="ctl", memory_static_block="mem2",
    )
    assert snap1.frozen is snap2.frozen
    assert snap1.memory_static_block == "mem1"
    assert snap2.memory_static_block == "mem2"


# --------------------------------------------------------------------------- #
# S16 declare 并行加载
# --------------------------------------------------------------------------- #
async def test_declare_runs_in_parallel():
    """几十资源并行 declare,总耗时约等于最慢单个,而非串行之和。"""
    import asyncio
    import time

    def _slow_resource(i):
        class _R(ResourceProtocol):
            capability_id = f"slow:{i}"

            @classmethod
            def declare(cls, config):
                # 返回 awaitable 让并行路径执行 sleep
                async def _decl():
                    await asyncio.sleep(0.05)
                    return [Contribution(
                        cls.capability_id, Slot.SYSTEM, f"sys-{i}",
                        lifetime=Lifetime.CONFIG_STATIC, cache_scope=CacheScope.USER,
                    )]
                return _decl()

        return _R()

    class _Pack:
        is_pack = True

        @property
        def sub_resources(self):
            return [_slow_resource(i) for i in range(8)]  # 8 个各 50ms

    facade = ResourceFacade()
    start = time.monotonic()
    snap = await facade.assemble(agent_id="a", conv_id="c", resource_root=_Pack())
    elapsed = time.monotonic() - start

    # 串行: 8 × 50ms = 400ms;并行应 < ~150ms
    assert elapsed < 0.2, f"declare 未并行,耗时 {elapsed:.3f}s"
    texts = {b.text for b in snap.frozen.system}
    assert len(texts) == 8


async def test_declare_failure_does_not_block_others():
    """某资源 declare 抛异常,不阻塞其它资源、不污染 bundle。"""

    def _ok(i):
        class _R(ResourceProtocol):
            capability_id = f"ok:{i}"

            @classmethod
            def declare(cls, config):
                return [Contribution(
                    cls.capability_id, Slot.SYSTEM, f"ok-{i}",
                    lifetime=Lifetime.CONFIG_STATIC, cache_scope=CacheScope.USER,
                )]
        return _R()

    def _bad():
        class _R(ResourceProtocol):
            capability_id = "bad"

            @classmethod
            def declare(cls, config):
                raise RuntimeError("declare boom")
        return _R()

    class _Pack:
        is_pack = True

        @property
        def sub_resources(self):
            return [_ok(1), _bad(), _ok(2)]

    facade = ResourceFacade()
    snap = await facade.assemble(agent_id="a", conv_id="c", resource_root=_Pack())
    texts = {b.text for b in snap.frozen.system}
    assert "ok-1" in texts and "ok-2" in texts
