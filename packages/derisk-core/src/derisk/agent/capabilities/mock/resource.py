"""MockResource —— 扩展性验证用 mock capability(RFC-005 结构验证)。

证明"新增 capability = 新建目录 + 实现协议 + register",零改其它代码,
CapabilityRegistry.discover() 自动发现。生产无此 capability,仅测试用。
"""

from __future__ import annotations

from typing import Any, List

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.protocol import ResourceProtocol


class MockResource(ResourceProtocol):
    """mock capability:declare 一条测试 SYSTEM Contribution。"""

    capability_id = "mock"
    protocol_version = 1

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        return [
            Contribution(
                capability_id=cls.capability_id,
                slot=Slot.SYSTEM,
                content="mock capability declared",
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.NONE,
                order=500,
            )
        ]