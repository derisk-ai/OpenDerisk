"""CapabilityRegistry —— capability 注册发现(RFC-005)。

每个 capability 自管目录(agent/capabilities/{capability}/),目录 __init__.py
实现 register(registry) 自注册。本 registry 在 Agent 启动时扫描已注册的
capability,供 facade 按 capability_id 查资源实例。

扩展模型:新增 capability = 新建一个目录 + 实现 register(),零改其它。
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Dict, List, Optional

from derisk.core.interface.resource.protocol import ResourceProtocol

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """capability_id → ResourceProtocol 实例。

    每个 capability 目录的 __init__.py 调 registry.register(MyResource())
    自注册。discovery() 扫描 agent.capabilities 下所有子包,触发各自注册。
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, ResourceProtocol] = {}

    def register(self, resource: ResourceProtocol) -> None:
        """注册一个 capability 实例(幂等覆盖)。"""
        self._capabilities[resource.capability_id] = resource
        logger.debug(f"capability registered: {resource.capability_id}")

    def get(self, capability_id: str) -> Optional[ResourceProtocol]:
        return self._capabilities.get(capability_id)

    def has(self, capability_id: str) -> bool:
        return capability_id in self._capabilities

    def all(self) -> List[ResourceProtocol]:
        return list(self._capabilities.values())

    def capability_ids(self) -> List[str]:
        return list(self._capabilities.keys())

    def discover(self, package: str = "derisk.agent.capabilities") -> None:
        """扫描 package 下所有子包,触发各 capability 目录的自注册。

        约定:每个 capability 自管目录的 __init__.py 实现模块级 register()
        或定义 register(registry) 函数。本方法 import 子包即触发注册。
        可重复调用(幂等)。
        """
        try:
            pkg = importlib.import_module(package)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"discover: import {package} failed: {e}")
            return
        for _finder, name, ispkg in pkgutil.iter_modules(pkg.__path__):
            if not ispkg:
                continue  # 仅扫描子包(每个 capability 一个目录)
            full = f"{package}.{name}"
            try:
                mod = importlib.import_module(full)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"discover: import {full} failed: {e}")
                continue
            # 约定:子包若有 register(registry) 函数则调用
            register_fn = getattr(mod, "register", None)
            if callable(register_fn):
                try:
                    register_fn(self)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"discover: {full}.register() failed: {e}")


# 进程级单例(默认;Agent 可自建隔离的 registry)
_default_registry: Optional[CapabilityRegistry] = None


def get_default_registry() -> CapabilityRegistry:
    """获取进程级默认 CapabilityRegistry(懒加载,首次自动 discover)。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = CapabilityRegistry()
        _default_registry.discover()
    return _default_registry