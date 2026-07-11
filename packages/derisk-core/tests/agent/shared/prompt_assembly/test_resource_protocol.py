"""RFC-005 §3.3 ResourceProtocol 单测。

LegacyResourceAdapter(存量桥接)已随 RFC-005 全量迁移删除:所有资源经
capability wrapper 走原生 declare,无 legacy 桥接。本文件仅保留 ResourceProtocol
抽象契约测试(可被子类实现 / requires·consume 默认 / 抽象不可实例化)。

原 AC-2 字节等价测试(LegacyResourceAdapter ≡ ResourceInjector.inject_all)已无意义。
"""

import asyncio
from typing import Any, List

import pytest

from derisk.agent.shared.prompt_assembly.input_bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol


def test_resource_protocol_can_be_subclassed():
    """新资源直接实现 ResourceProtocol.declare,不依赖存量桥接。"""
    class MyResource(ResourceProtocol):
        capability_id = "my:resource"

        @classmethod
        def declare(cls, config: Any) -> List[Contribution]:
            return [
                Contribution(
                    capability_id=cls.capability_id,
                    slot=Slot.SYSTEM,
                    content=str(config),
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.GLOBAL,
                )
            ]

    contribs = MyResource.declare({"k": "v"})
    assert len(contribs) == 1
    assert contribs[0].cache_scope == CacheScope.GLOBAL
    assert contribs[0].capability_id == "my:resource"


def test_resource_protocol_default_requires_and_consume():
    """requires 默认空,consume 默认不实现(返回空)。"""
    class R(ResourceProtocol):
        capability_id = "r"

        @classmethod
        def declare(cls, config):
            return []

    r = R()
    assert R.requires({}) == []

    assert asyncio.get_event_loop().run_until_complete(r.consume("result")) == []


def test_resource_protocol_is_abstract():
    """ResourceProtocol 不能直接实例化(declare 未实现)。"""
    with pytest.raises(TypeError):
        ResourceProtocol()  # type: ignore[abstract]