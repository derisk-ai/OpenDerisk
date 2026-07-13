"""Memory capability —— 记忆能力自管目录(RFC-005 Step D / RFC-006 Stage 5)。

记忆资源是配置载体 + Consumer(检索回注)。declare 空,consume 提供接口。
register_wrappers 注册旧 MemoryResource → MemoryCapabilityResource(旧 wrapper)。

RFC-006 Stage 5:新增 register_capability,注册旧 MemoryResource → MemoryCapability
(自管理 Capability)过渡 provider,facade 遍历时翻成 Capability 对象(统一对象模型,
修复旧 wrapper declare 桩形态)。注:记忆真检索走 _memory_bundle 独立路径,本轮只统一
对象模型,不接 consume/execute 生产路径(留待后续)。
"""

from .capability import MemoryCapability  # noqa: F401
from .resource import MemoryCapabilityResource  # noqa: F401

__all__ = ["MemoryCapability", "MemoryCapabilityResource"]


def register(registry) -> None:
    pass


def register_wrappers(facade) -> None:
    """注册 memory capability 双轨 wrapper 到 facade。"""
    import logging
    log = logging.getLogger(__name__)
    try:
        from derisk.agent.resource.memory import MemoryResource
        facade.register_legacy_wrapper(
            MemoryResource,
            lambda legacy: MemoryCapabilityResource(legacy_instance=legacy),
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"memory register_wrappers failed: {e}")


def build_capability(value, system_app=None):
    """RFC-006:从 config dict 构造 MemoryCapability(无 I/O)。"""
    return MemoryCapability.from_config(value, system_app)


def register_capability(facade) -> None:
    """RFC-006 Stage 5:注册 memory config factory + 旧实例→Capability 过渡 provider。"""
    facade.register_capability_factory("memory", build_capability)
    try:
        from derisk.agent.resource.memory import MemoryResource
        facade.register_legacy_capability_provider(
            MemoryResource, MemoryCapability.from_legacy
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(f"memory register_capability legacy provider failed: {e}")

# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "memory"


def register_capability_to(registry) -> None:
    registry.register(CAPABILITY_TYPE_KEY, build_capability)
