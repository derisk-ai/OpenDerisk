"""App(子 Agent)capability —— 自管目录(RFC-005 Step B / RFC-006 Stage 4)。

App 资源纯声明类:declare app 描述,无 I/O。
register_wrappers 用纯 core 谓词(属性判断)注册,不 import serve 层 Resource 类,
避免 core→serve 反向依赖分层倒置。

RFC-006 Stage 4:新增 register_capability,注册 config→AppCapability factory,
使 facade 能直接从 AgentResource 配置构造自管理 Capability(不经旧 Resource 子类)。
"""

from .capability import AppCapability  # noqa: F401
from .resource import AppCapabilityResource  # noqa: F401

__all__ = ["AppCapability", "AppCapabilityResource"]


def register(registry) -> None:
    pass


def _is_app_legacy(sub) -> bool:
    """纯 core 谓词:识别 App 资源(不 import serve 类,鸭式属性判断)。"""
    return (
        hasattr(sub, "app_code")
        and hasattr(sub, "app_name")
        and hasattr(sub, "app_desc")
    )


def register_wrappers(facade) -> None:
    """注册 app capability 双轨 wrapper 到 facade(纯 core,无 serve 依赖)。"""
    from .resource import AppCapabilityResource
    facade.register_legacy_wrapper(
        _is_app_legacy,
        lambda legacy: AppCapabilityResource(legacy_instance=legacy),
    )


def build_capability(value, system_app=None):
    """RFC-006:从 AgentResource.value dict 构造 AppCapability(无 I/O)。"""
    return AppCapability.from_config(value, system_app)


def register_capability(facade) -> None:
    """RFC-006:注册 type_key→AppCapability factory + 旧实例→Capability 过渡 provider。

    type_key="app"(ResourceType.App / GptAppResource.type() 的别名)。AgentResource.type
    为 "app" 时,react_master._register_capability_factories 命中本 factory 直接产 Capability。

    Stage 4.5 过渡:同时注册 legacy provider,使 facade 遍历旧 ResourcePack 时把旧
    GptAppResource 实例翻成 AppCapability(修复旧 wrapper declare 空桩 → app 描述注入生效)。
    无需改 ResourceManager / react_master 构造链。Stage 9 旧类退役后删本 provider。
    """
    facade.register_capability_factory("app", build_capability)
    facade.register_legacy_capability_provider(_is_app_legacy, AppCapability.from_legacy)


# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "app"


def register_capability_to(registry) -> None:
    """注册 build_capability 到 CapabilityFactoryRegistry(构造期产 CapabilityPack)。"""
    registry.register(CAPABILITY_TYPE_KEY, build_capability)