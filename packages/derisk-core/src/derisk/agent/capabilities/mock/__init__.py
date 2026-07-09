"""Mock capability —— 扩展性验证(非生产)。

register() 把 MockResource 实例登记到 CapabilityRegistry,
证明 discover() 自动发现新 capability 目录。
"""

from .resource import MockResource  # noqa: F401

__all__ = ["MockResource"]


def register(registry) -> None:
    """被 CapabilityRegistry.discover() 调用,自注册。"""
    from .resource import MockResource
    registry.register(MockResource())