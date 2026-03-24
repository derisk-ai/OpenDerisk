"""
ReasoningArgSupplier - 推理参数供应器

提供动态参数的供应功能。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ReasoningArgSupplier:
    """
    推理参数供应器

    用于提供动态参数值。
    """

    _suppliers: Dict[str, "ReasoningArgSupplier"] = {}

    def __init__(
        self,
        arg_key: str,
        description: str = "",
        params: Optional[Dict[str, Any]] = None,
    ):
        self.arg_key = arg_key
        self.description = description
        self.params = params or {}

    @classmethod
    def register(cls, supplier: "ReasoningArgSupplier") -> None:
        """注册供应器"""
        cls._suppliers[supplier.arg_key] = supplier

    @classmethod
    def get_supplier(cls, key: str) -> Optional["ReasoningArgSupplier"]:
        """获取供应器"""
        return cls._suppliers.get(key)

    @classmethod
    def get_all_suppliers(cls) -> Dict[str, "ReasoningArgSupplier"]:
        """获取所有供应器"""
        return cls._suppliers.copy()

    async def supply(self, params: Dict[str, Any], agent: Any, context: Any) -> None:
        """供应参数值"""
        # 默认实现：不做任何事情
        pass
