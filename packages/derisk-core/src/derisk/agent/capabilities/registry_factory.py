"""CapabilityFactoryRegistry —— type_key → Capability 工厂注册(RFC-006 收尾 Phase A)。

进程级单例,持有 AgentResource.type → factory(value, system_app) -> Capability 映射。
`build_pack(real_all_resources, system_app)` 遍历配置态资源列表,对每个有 factory 的
type 调 factory 产 Capability 装进 CapabilityPack;无 factory 的 type 跳过(留旧
Resource 路径,如 Workflow/ReasoningEngine/OpenRca 等边角类)。

填充:各 capability 目录的 `register_capability(facade)` 原本注册到 facade 的
`_capability_factories`;Phase A 把这套扫描提到本 registry。`discover()` 扫
core+serve capabilities 包调各 `register_capability_to(registry)`(或复用 register_capability
但目标改为本 registry)。

react_master 的 `_register_capability_factories` 仍注册到 facade(供 facade 渲染期
legacy provider 用),但 **构造期**(`agent_chat.build_agent_by_gpts`)用本 registry 产
CapabilityPack 绑 agent——这是"agent 持有稳定 Capability 对象"的入口,而非每轮临时翻转。
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any, Callable, Dict, List, Optional

from derisk.core.interface.resource.capability import Capability, CapabilityPack

logger = logging.getLogger(__name__)

# type_key(AgentResource.type str) → factory(value: dict, system_app) -> Capability
Factory = Callable[[dict, Any], Capability]


class CapabilityFactoryRegistry:
    """type_key → Capability factory 映射(构造期用,产 CapabilityPack)。"""

    def __init__(self) -> None:
        self._factories: Dict[str, Factory] = {}
        self._discovered = False

    def register(self, type_key: str, factory: Factory) -> None:
        """注册 type_key → Capability 工厂(幂等覆盖)。"""
        self._factories[type_key] = factory
        logger.debug(f"capability factory registered: {type_key}")

    def get(self, type_key: str) -> Optional[Factory]:
        return self._factories.get(type_key)

    def has(self, type_key: str) -> bool:
        return type_key in self._factories

    def type_keys(self) -> List[str]:
        return list(self._factories.keys())

    def discover(self) -> None:
        """扫描 core+serve capabilities 包,调各 `register_capability_to(registry)`。

        约定:每个 capability 子包 `__init__.py` 暴露 `register_capability_to(registry)`,
        把本能力的 `build_capability`(value, system_app)→Capability 注册到 registry。
        幂等(重复调不重复注册,register 覆盖)。
        """
        if self._discovered:
            return
        for package_name in [
            "derisk.agent.capabilities",
            "derisk_serve.agent.capabilities",
        ]:
            try:
                pkg = importlib.import_module(package_name)
            except Exception:  # noqa: BLE001
                continue  # serve 在 core 测试环境不可导入时跳过
            pkg_path = getattr(pkg, "__path__", None)
            if not pkg_path:
                continue
            for _finder, name, ispkg in pkgutil.iter_modules(pkg_path):
                if not ispkg:
                    continue
                full = f"{package_name}.{name}"
                try:
                    mod = importlib.import_module(full)
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"factory discover: skip {full}: {e}")
                    continue
                # 优先 register_capability_to(registry)(本 registry 专用);回退
                # 复用 build_capability(value, system_app) 直接注册(build_capability
                # 是 register_capability 内绑到 facade 的工厂,签名一致可复用)。
                reg_to = getattr(mod, "register_capability_to", None)
                if callable(reg_to):
                    try:
                        reg_to(self)
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"factory discover: {full}.register_capability_to failed: {e}")
                    continue
                build = getattr(mod, "build_capability", None)
                type_key = getattr(mod, "CAPABILITY_TYPE_KEY", None)
                if callable(build) and type_key:
                    self.register(type_key, build)
        self._discovered = True

    def build_pack(
        self,
        agent_resources: Optional[List[Any]],
        system_app: Any = None,
    ) -> CapabilityPack:
        """从配置态资源列表产 CapabilityPack。

        遍历 agent_resources,对每个有 factory 的 type 调 factory(value, system_app) 产
        Capability 装包;无 factory 的 type 跳过(留旧 Resource 路径)。未 discover 时先 discover。
        """
        if not self._discovered:
            self.discover()
        pack = CapabilityPack()
        if not agent_resources:
            return pack
        for ar in agent_resources:
            type_key = getattr(ar, "type", None)
            if not type_key:
                continue
            factory = self._factories.get(type_key)
            if factory is None:
                continue  # 无 factory(边角类),留旧 Resource
            value = getattr(ar, "value", None)
            if value is None:
                value = {}
            try:
                cap = factory(value, system_app)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"capability factory {type_key} failed for "
                    f"{getattr(ar,'name','?')}: {e}; skipping"
                )
                continue
            if cap is not None:
                pack.add(cap)
        return pack


_default_registry: Optional[CapabilityFactoryRegistry] = None


def get_default_factory_registry() -> CapabilityFactoryRegistry:
    """进程级默认 CapabilityFactoryRegistry(懒加载,首次自动 discover)。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = CapabilityFactoryRegistry()
        _default_registry.discover()
    return _default_registry


__all__ = [
    "CapabilityFactoryRegistry",
    "Factory",
    "get_default_factory_registry",
]