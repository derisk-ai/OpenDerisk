"""RFC-006 Phase A:CapabilityFactoryRegistry + CapabilityPack 构造期产单测。"""

import asyncio

import pytest

from derisk.agent.capabilities.registry_factory import (
    CapabilityFactoryRegistry,
    get_default_factory_registry,
)
from derisk.core.interface.resource.capability import Capability, CapabilityPack
from types import SimpleNamespace


def _res(type_key, value=None, name="n"):
    return SimpleNamespace(type=type_key, name=name, value=value or {}, version="v2")


def test_registry_register_and_get():
    r = CapabilityFactoryRegistry()
    assert not r.has("x")
    r.register("x", lambda v, s: None)
    assert r.has("x")
    assert r.get("x") is not None


def test_build_pack_constructs_capabilities_from_config():
    r = CapabilityFactoryRegistry()
    r.register("app", lambda v, s: _AppCap(v.get("app_name", "")))
    r._discovered = True
    pack = r.build_pack([_res("app", {"app_name": "Canvas"})], None)
    assert isinstance(pack, CapabilityPack)
    assert len(pack.sub_resources) == 1
    assert getattr(pack.sub_resources[0], "app_name", "") == "Canvas"


def test_build_pack_skips_types_without_factory():
    """无 factory 的 type(边角类如 workflow)跳过,留旧 Resource 路径。"""
    r = CapabilityFactoryRegistry()
    r.register("app", lambda v, s: _AppCap("x"))
    r._discovered = True
    pack = r.build_pack([_res("app"), _res("workflow"), _res("reasoning_engine")], None)
    assert len(pack.sub_resources) == 1  # 只有 app


def test_build_pack_factory_failure_skipped():
    r = CapabilityFactoryRegistry()

    def _boom(v, s):
        raise RuntimeError("bad config")

    r.register("app", _boom)
    r._discovered = True
    pack = r.build_pack([_res("app")], None)
    assert pack.sub_resources == []  # 异常不阻塞,空包


def test_build_pack_empty_or_none():
    r = CapabilityFactoryRegistry()
    r._discovered = True
    assert r.build_pack(None, None).sub_resources == []
    assert r.build_pack([], None).sub_resources == []


async def test_capability_pack_preload_resource_calls_prepare():
    """CapabilityPack.preload_resource 遍历子 Capability 调 prepare(eager load)。"""
    from derisk.core.interface.resource.executor import (
        ExecutorCall,
        ExecutorStatus,
        ReleaseReason,
    )

    class _Cap(Capability):
        capability_id = "test:x"

        def __init__(self):
            self.prepare_calls = 0

        def declare(self, config=None):
            return []

        async def prepare(self):
            self.prepare_calls += 1

        async def execute(self, call: ExecutorCall):
            return None

        async def release(self, reason: ReleaseReason):
            pass

    c1, c2 = _Cap(), _Cap()
    pack = CapabilityPack([c1, c2])
    await pack.preload_resource()
    assert c1.prepare_calls == 1
    assert c2.prepare_calls == 1


async def test_capability_pack_preload_isolates_failures():
    """单能力 prepare 失败不阻塞其它(对齐旧 ResourcePack 容错)。"""
    from derisk.core.interface.resource.executor import (
        ExecutorCall,
        ExecutorStatus,
        ReleaseReason,
    )

    class _Ok(Capability):
        capability_id = "ok"

        def __init__(self):
            self.prepare_calls = 0

        def declare(self, config=None):
            return []

        async def prepare(self):
            self.prepare_calls += 1

        async def execute(self, call):
            return None

        async def release(self, reason):
            pass

    class _Bad(Capability):
        capability_id = "bad"

        def declare(self, config=None):
            return []

        async def prepare(self):
            raise RuntimeError("prepare boom")

        async def execute(self, call):
            return None

        async def release(self, reason):
            pass

    ok = _Ok()
    pack = CapabilityPack([_Bad(), ok])
    await pack.preload_resource()  # 不抛
    assert ok.prepare_calls == 1


def test_capability_pack_get_by_prefix():
    from derisk.core.interface.resource.executor import (
        ExecutorCall,
        ExecutorStatus,
        ReleaseReason,
    )

    class _C(Capability):
        def __init__(self, cid):
            self.capability_id = cid

        def declare(self, config=None):
            return []

        async def prepare(self):
            pass

        async def execute(self, call):
            return None

        async def release(self, reason):
            pass

    pack = CapabilityPack([_C("db:1"), _C("db:2"), _C("app:x")])
    assert pack.get("db:").capability_id == "db:1"
    assert len(pack.get_all("db:")) == 2
    assert pack.get("knowledge:") is None


def test_default_registry_discovers_all_six_type_keys():
    """进程级 registry discover 后应含 6 能力 type_key。"""
    r = get_default_factory_registry()
    keys = set(r.type_keys())
    assert {"app", "datasource", "knowledge_pack", "memory", "skill(derisk)", "tool"} <= keys


class _AppCap(Capability):
    capability_id = "app"

    def __init__(self, app_name=""):
        self.app_name = app_name

    def declare(self, config=None):
        return []

    async def prepare(self):
        pass

    async def execute(self, call):
        return None

    async def release(self, reason):
        pass