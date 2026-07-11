"""MemoryCapability —— 记忆自管理资源能力(RFC-006 Stage 5,最小占位)。

记忆的特殊性:真检索逻辑在 ``_memory_bundle``/``longterm_manager`` 独立路径
(agent_chat 隐式挂载,经 memory_pipeline.prefetch → react_master 内联 consume_prefetch),
**不**经 ResourcePack 的 MemoryResource 子资源执行。MemoryResource 旧类只是配置载体
(get_prompt 空)。故 MemoryCapability 本轮只做"对象模型统一 + 旧实例翻成 Capability",
保持原有空 declare 行为(记忆 static_block 走 memory_pipeline 独立路径,非资源 declare)。

不做的(风险收益不成比例,留待后续):
- memory_context 改走 facade snapshot.user_parts(经 apply_consumption):当前走
  assemble_user_prompt 拼接,改之动记忆热路径。
- memory_search/write 工具改 Route B:当前 MemoryToolPack builtin,需另动 MemoryToolPack。
- execute 委托 store:旧 MemoryResource 不持有 store(在 bundle.manager),无可委托。

本轮:MemoryCapability(declare 空、prepare no-op、from_legacy)统一自管理对象模型,
修复旧 MemoryCapabilityResource 的 declare 桩形态(虽本就空),为后续接线留接口。
"""

from __future__ import annotations

import logging
from typing import Any, List

from derisk.core.interface.resource.bundle import (
    CacheScope,
    Contribution,
    Lifetime,
    Slot,
)
from derisk.core.interface.resource.capability import Capability
from derisk.core.interface.resource.executor import (
    ExecutorCall,
    ExecutorStatus,
    ReleaseReason,
)

logger = logging.getLogger(__name__)


class MemoryCapability(Capability):
    """记忆能力自管理对象(最小占位)。

    capability_id="memory";executor_id="memory"(单例,无 live 实例)。
    declare 空(记忆 static_block 走 memory_pipeline 独立路径)。
    """

    capability_id = "memory"

    def __init__(self, memory_params: Any = None):
        self._memory_params = memory_params
        self._status = ExecutorStatus.UNINITIALIZED
        self._store = None  # 真检索 store 在 _memory_bundle.manager,非本对象持有

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "MemoryCapability":
        """从旧 MemoryResource 实例构造(过渡期)。无 I/O。"""
        params = getattr(legacy_instance, "memory_params", None)
        if callable(params):
            try:
                params = params()
            except Exception:  # noqa: BLE001
                params = None
        elif params is None:
            params = getattr(legacy_instance, "_memory_params", None)
        return cls(memory_params=params)

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "MemoryCapability":
        return cls(memory_params=value or None)

    # ----------------------------- 输入投影(空) --------------------------- #
    def declare(self, config: Any = None) -> List[Contribution]:
        # 记忆资源不产 system 声明(static_block 走 memory_pipeline 独立路径)。
        return []

    def requires(self, config: Any = None) -> List[str]:
        return []

    async def consume(self, call_result: Any) -> List[Contribution]:
        """记忆检索结果回注输入(供将来 apply_consumption 接线;本轮未接生产路径)。"""
        if not call_result:
            return []
        content = call_result if isinstance(call_result, str) else str(call_result)
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.USER_PART,
                content=f"<memory-context>\n{content}\n</memory-context>",
                lifetime=Lifetime.SESSION,
                cache_scope=CacheScope.NONE,
            )
        ]

    # ----------------------------- 生命周期(无 I/O) ----------------------- #
    async def prepare(self) -> None:
        # 真检索 store 在 _memory_bundle.manager(独立路径),本对象不持有故 prepare no-op。
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # memory_search/write 工具暂留 MemoryToolPack builtin(Route A);本 execute 未接 store。
        raise NotImplementedError(
            "MemoryCapability.execute 未接 store —— memory_* 工具暂走 MemoryToolPack builtin"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED