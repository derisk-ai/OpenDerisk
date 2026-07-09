"""RFC-005 §3.3 / S2 ResourceProtocol + LegacyResourceAdapter 单测。

核心验收(AC-2 等价重构):
- ``LegacyResourceAdapter.from_context`` 产出的 system 文本
  ≡ ``ResourceInjector.inject_all(ctx)`` 输出(字节相等)。
- tools 槽内容 ≡ ``ToolPack.from_resource(resource_root)`` 解析的工具集。
- 资源层 Contribution 的 cache_scope=USER(跨会话同用户稳定)。
- ResourceProtocol 抽象可被子类实现。
"""

from typing import Any, Dict, List

import pytest

from derisk.agent.shared.prompt_assembly.input_bundle import (
    CacheScope,
    Contribution,
    InputBundle,
    Lifetime,
    Slot,
)
from derisk.agent.shared.prompt_assembly.resource_injector import (
    ResourceContext,
    ResourceInjector,
)
from derisk.agent.shared.prompt_assembly.resource_protocol import (
    LegacyResourceAdapter,
    ResourceProtocol,
)


# --------------------------------------------------------------------------- #
# 测试夹具:最小假资源(触发 inject_custom 兜底分支产出非空 system)
# --------------------------------------------------------------------------- #
class _FakeCustomResource:
    """未被 inject_xxx 各分支命中的自定义资源,走 _extract_custom。"""

    def __init__(self, name="fake_custom", desc="a custom resource"):
        self.name = name
        self.scene_description = desc

    def type(self):  # inject_custom 用 item.type()
        return "my_custom_type"


@pytest.fixture
def ctx_with_custom() -> ResourceContext:
    return ResourceContext(resource_map={"my_custom_type": [_FakeCustomResource()]})


@pytest.fixture
def injector() -> ResourceInjector:
    return ResourceInjector()


# --------------------------------------------------------------------------- #
# AC-2 字节等价:system 文本 ≡ inject_all
# --------------------------------------------------------------------------- #
async def test_system_text_equals_inject_all(ctx_with_custom, injector):
    """AC-2: 桥接产出的 system 文本与 inject_all 字节相等。"""
    expected = await injector.inject_all(ctx_with_custom)
    assert expected  # 确保兜底分支确实产出了非空内容

    adapter = LegacyResourceAdapter(injector=injector)
    bundle = await adapter.from_context(ctx_with_custom)

    assert len(bundle.system) == 1
    assert bundle.system[0].content == expected
    assert isinstance(bundle.system[0], Contribution)
    # 文本通过 freeze + merge_to_str 也应等价(用 legacy separator)
    frozen = bundle.freeze()
    assert frozen.merge_to_str(LegacyResourceAdapter.legacy_separator()) == expected


async def test_empty_context_produces_no_system():
    """AC-2: 空 ctx(inject_all 返回空串)不写 system Contribution。"""
    empty_ctx = ResourceContext(resource_map={})
    adapter = LegacyResourceAdapter()
    bundle = await adapter.from_context(empty_ctx)

    assert bundle.system == []
    assert bundle.tools == []


# --------------------------------------------------------------------------- #
# 资源层 cache_scope = USER(跨会话同用户稳定)
# --------------------------------------------------------------------------- #
async def test_resource_layer_cache_scope_is_user(ctx_with_custom):
    """资源声明(DB schema/app 列表)跨会话同用户稳定 → USER scope。"""
    adapter = LegacyResourceAdapter()
    bundle = await adapter.from_context(ctx_with_custom)

    assert bundle.system[0].cache_scope == CacheScope.USER
    assert bundle.system[0].lifetime == Lifetime.CONFIG_STATIC


# --------------------------------------------------------------------------- #
# tools 槽:与 ToolPack.from_resource 一致
# --------------------------------------------------------------------------- #
def _make_function_tool(name: str):
    from derisk.agent.resource import FunctionTool

    def _fn(**kwargs):
        return "ok"

    _fn.__doc__ = f"tool {name}"
    return FunctionTool(name=name, func=_fn, description=f"tool {name}")


def test_tools_match_toolpack_from_resource():
    """tools 槽内容 ≡ ToolPack.from_resource 解析的工具集。"""
    from derisk.agent.resource import ToolPack

    tool_a = _make_function_tool("tool_a")
    tool_b = _make_function_tool("tool_b")
    pack = ToolPack([tool_a, tool_b])

    adapter = LegacyResourceAdapter()
    import asyncio

    bundle = asyncio.get_event_loop().run_until_complete(
        adapter.from_context(ResourceContext(resource_map={}), resource_root=pack)
    )

    # 工具数量一致
    expected_tools = ToolPack.from_resource(pack)[0].sub_resources
    assert len(bundle.tools) == len(expected_tools)
    # 工具引用一致(保留原始 BaseTool)
    bundle_tool_names = {
        getattr(c.content, "name", None) for c in bundle.tools
    }
    expected_names = {getattr(t, "name", None) for t in expected_tools}
    assert bundle_tool_names == expected_names
    assert bundle_tool_names == {"tool_a", "tool_b"}


def test_tools_cache_scope_none_and_static_lifetime():
    """tools 槽 cache_scope=NONE(缓存由 S12 处理),lifetime=CONFIG_STATIC。"""
    from derisk.agent.resource import ToolPack

    pack = ToolPack([_make_function_tool("t1")])
    adapter = LegacyResourceAdapter()
    import asyncio

    bundle = asyncio.get_event_loop().run_until_complete(
        adapter.from_context(ResourceContext(resource_map={}), resource_root=pack)
    )
    assert all(c.slot == Slot.TOOLS for c in bundle.tools)
    assert all(c.cache_scope == CacheScope.NONE for c in bundle.tools)
    assert all(c.lifetime == Lifetime.CONFIG_STATIC for c in bundle.tools)


# --------------------------------------------------------------------------- #
# ResourceProtocol 抽象可被实现
# --------------------------------------------------------------------------- #
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
    import asyncio

    assert asyncio.get_event_loop().run_until_complete(r.consume("result")) == []


def test_resource_protocol_is_abstract():
    """ResourceProtocol 不能直接实例化(declare 未实现)。"""
    with pytest.raises(TypeError):
        ResourceProtocol()  # type: ignore[abstract]