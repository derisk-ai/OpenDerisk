"""RFC-005 S8 Consumer 回注编排骨架单测。

覆盖:
- ConsumerRegistry 注册/查询
- apply_consumption:Consumer 结果按 lifetime 分流
  - SESSION → 写 facade 会话运行态
  - TURN → 透传返回(供当轮 user_parts)
  - 非 Consumer → 空列表,不反改
- consume 异常不影响主流程(吞掉返回空)
"""

from typing import Any, List

import pytest

from derisk.core.interface.resource.bundle import CacheScope, Contribution, Lifetime, Slot
from derisk.agent.capabilities.facade import ResourceFacade
from derisk.core.interface.resource.protocol import (
    ConsumerRegistry,
    ResourceProtocol,
    apply_consumption,
)


# --------------------------------------------------------------------------- #
# 测试 Consumer
# --------------------------------------------------------------------------- #
class _ImageLoaderConsumer(ResourceProtocol):
    """多模态图片加载:工具结果 → USER_PART 图片,SESSION 生命周期。"""

    capability_id = "image_loader"

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.USER_PART,
                content={"type": "image", "data": call_result},
                lifetime=Lifetime.SESSION,
                cache_scope=CacheScope.NONE,
            )
        ]


class _RagConsumer(ResourceProtocol):
    """RAG 检索:结果 → USER_PART chunks,TURN 生命周期。"""

    capability_id = "rag_search"

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.USER_PART,
                content=f"chunks: {call_result}",
                lifetime=Lifetime.TURN,
                cache_scope=CacheScope.NONE,
            )
        ]


class _FailingConsumer(ResourceProtocol):
    capability_id = "failing"

    @classmethod
    def declare(cls, config: Any) -> List[Contribution]:
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        raise RuntimeError("boom")


# --------------------------------------------------------------------------- #
# ConsumerRegistry
# --------------------------------------------------------------------------- #
def test_consumer_registry_register_and_get():
    reg = ConsumerRegistry()
    c = _ImageLoaderConsumer()
    reg.register(c)
    assert reg.has("image_loader")
    assert reg.get("image_loader") is c
    assert not reg.has("rag_search")


# --------------------------------------------------------------------------- #
# apply_consumption: SESSION 分流
# --------------------------------------------------------------------------- #
async def test_apply_consumption_session_writes_to_facade():
    """SESSION lifetime 的 consume 产物写入 facade 会话运行态。"""
    reg = ConsumerRegistry()
    reg.register(_ImageLoaderConsumer())
    facade = ResourceFacade()

    turn = await apply_consumption(
        reg, facade, "image_loader", "img-data-123", "conv-1"
    )
    # SESSION 不在 turn 返回(它进会话存储)
    assert turn == []
    # facade 会话存储有该图片
    session = facade._session_store.get("conv-1", [])
    assert len(session) == 1
    assert session[0].lifetime == Lifetime.SESSION


# --------------------------------------------------------------------------- #
# apply_consumption: TURN 分流
# --------------------------------------------------------------------------- #
async def test_apply_consumption_turn_returns_for_current_turn():
    """TURN lifetime 的 consume 产物透传返回,不进会话存储。"""
    reg = ConsumerRegistry()
    reg.register(_RagConsumer())
    facade = ResourceFacade()

    turn = await apply_consumption(
        reg, facade, "rag_search", "query-result", "conv-1"
    )
    assert len(turn) == 1
    assert turn[0].lifetime == Lifetime.TURN
    assert "query-result" in turn[0].content
    # 不进会话存储
    assert facade._session_store.get("conv-1", []) == []


# --------------------------------------------------------------------------- #
# 非 Consumer:不反改
# --------------------------------------------------------------------------- #
async def test_apply_consumption_non_consumer_returns_empty():
    """capability 未注册为 Consumer → 返回空,不动 facade。"""
    reg = ConsumerRegistry()
    facade = ResourceFacade()

    turn = await apply_consumption(reg, facade, "some_tool", "result", "conv-1")
    assert turn == []
    assert facade._session_store.get("conv-1", []) == []


# --------------------------------------------------------------------------- #
# consume 异常吞掉
# --------------------------------------------------------------------------- #
async def test_apply_consumption_swallows_consume_exception():
    """Consumer.consume 抛异常 → 返回空,不影响主流程。"""
    reg = ConsumerRegistry()
    reg.register(_FailingConsumer())
    facade = ResourceFacade()

    turn = await apply_consumption(reg, facade, "failing", "x", "conv-1")
    assert turn == []


# --------------------------------------------------------------------------- #
# 混合:一次 consume 含 SESSION + TURN
# --------------------------------------------------------------------------- #
async def test_apply_consumption_mixed_lifetimes():
    class _Mixed(ResourceProtocol):
        capability_id = "mixed"

        @classmethod
        def declare(cls, config):
            return []

        async def consume(self, call_result):
            return [
                Contribution(
                    "mixed", Slot.USER_PART, "session-part",
                    lifetime=Lifetime.SESSION, cache_scope=CacheScope.NONE,
                ),
                Contribution(
                    "mixed", Slot.USER_PART, "turn-part",
                    lifetime=Lifetime.TURN, cache_scope=CacheScope.NONE,
                ),
            ]

    reg = ConsumerRegistry()
    reg.register(_Mixed())
    facade = ResourceFacade()

    turn = await apply_consumption(reg, facade, "mixed", "r", "conv-1")
    # SESSION 进存储,TURN 返回
    assert len(turn) == 1
    assert turn[0].content == "turn-part"
    assert len(facade._session_store["conv-1"]) == 1