"""Skill capability —— 技能自管目录(RFC-005 Step B / RFC-006 Stage 7)。

技能是纯声明类:declare 渲染 skill 列表进 SYSTEM,无 I/O、无 executor。
register() 注册双轨 wrapper:旧 AgentSkillResource 实例 → SkillResource 走原生 declare。

RFC-006 Stage 7:register_capability 注册旧 AgentSkillResource→SkillCapability(自管理)
过渡 provider,facade 遍历旧 ResourcePack 时翻成 Capability 对象(统一对象模型)。
"""

from .capability import SkillCapability  # noqa: F401
from .resource import SkillResource  # noqa: F401

__all__ = ["SkillCapability", "SkillResource"]


def register(registry) -> None:
    """被 CapabilityRegistry.discover() 调用。

    本 capability 通过 facade 的双轨 wrapper 机制接入(register_legacy_wrapper),
    故此处主要占位;实际 wrapper 由 react_master_agent 启动时注册(见 _get_resource_facade)。
    保留 register 占位以符合 capability 目录约定。
    """
    pass


def register_wrappers(facade) -> None:
    """注册 skill capability 的双轨 wrapper 到 facade(旧路径)。"""
    try:
        from derisk.agent.resource.agent_skills import AgentSkillResource
        from .resource import SkillResource

        facade.register_legacy_wrapper(
            AgentSkillResource,
            lambda legacy: SkillResource(legacy_instance=legacy),
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(f"skill register_wrappers failed: {e}")


def build_capability(value, system_app=None):
    """RFC-006 Stage 7:从 config dict 构造 SkillCapability(若 config 带 name/path 则纯配置态)。"""
    return SkillCapability.from_config(value, system_app)


def register_capability(facade) -> None:
    """RFC-006 Stage 7:注册 skill config factory + 旧实例→SkillCapability 过渡 provider。"""
    try:
        from derisk.agent.resource.agent_skills import AgentSkillResource
        facade.register_capability_factory("skill(derisk)", build_capability)
        facade.register_legacy_capability_provider(
            AgentSkillResource, SkillCapability.from_legacy
        )
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(f"skill register_capability failed: {e}")

# RFC-006 Phase A:供 CapabilityFactoryRegistry 构造期 build_pack 用。
CAPABILITY_TYPE_KEY = "skill(derisk)"


def register_capability_to(registry) -> None:
    registry.register(CAPABILITY_TYPE_KEY, build_capability)
