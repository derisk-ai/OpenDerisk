"""MCP capability —— MCP 工具聚合自管目录(RFC-005 Step C / RFC-006 Stage 7)。

MCP 资源(ToolPack 子类)是工具聚合:declare 产工具列表 TOOLS。
register_wrappers 用纯 core 谓词(ToolPack 在 core,可 isinstance)注册,
不 import serve 层的具体 MCPToolPack 等子类。

RFC-006 Stage 7:register_capability 注册旧 ToolPack→MCPCapability(自管理)过渡
provider。注:facade 时序 declare 先于 prepare,MCP 工具列表来自 preload_resource I/O
(对象非 str,无法 DataRequirement 占位),故 MCPCapability 不自管 preload——from_legacy
复用旧 ToolPack.preload_resource 已拉的工具。详见 capability.py。
"""

from .capability import MCPCapability  # noqa: F401
from .resource import MCPCapabilityResource  # noqa: F401

__all__ = ["MCPCapability", "MCPCapabilityResource"]


def register(registry) -> None:
    pass


def _is_toolpack_legacy(sub) -> bool:
    """纯 core 谓词:识别 ToolPack(工具聚合,在 core 可 isinstance)。"""
    try:
        from derisk.agent.resource.tool.pack import ToolPack
        return isinstance(sub, ToolPack)
    except Exception:  # noqa: BLE001
        return False


def register_wrappers(facade) -> None:
    """注册 MCP/Tool/Pack 族双轨 wrapper 到 facade(纯 core,旧路径)。"""
    from .resource import MCPCapabilityResource
    facade.register_legacy_wrapper(
        _is_toolpack_legacy,
        lambda legacy: MCPCapabilityResource(legacy_instance=legacy),
    )


def build_capability(value, system_app=None):
    """RFC-006 Stage 7:从 config 构造 MCPCapability(工具对象需 preload,config 暂产空)。"""
    return MCPCapability.from_config(value, system_app)


def register_capability(facade) -> None:
    """RFC-006 Stage 7:注册 mcp config factory + 旧 ToolPack→Capability 过渡 provider。"""
    from .capability import MCPCapability
    facade.register_capability_factory("tool", build_capability)
    facade.register_legacy_capability_provider(
        _is_toolpack_legacy, MCPCapability.from_legacy
    )

# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "tool"


def register_capability_to(registry) -> None:
    registry.register(CAPABILITY_TYPE_KEY, build_capability)
