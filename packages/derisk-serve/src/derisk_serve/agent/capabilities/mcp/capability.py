"""MCPCapability —— MCP 工具聚合自管理资源能力(RFC-006 Stage 7)。

MCP 聚合一组 MCP server 工具,declare 把它们包成 ToolEntry 进 TOOLS 槽。

**架构约束(facade 时序锁)**:facade._build_static_bundle 时序 declare 先于 prepare。
MCP 工具列表来自 preload_resource I/O(连 MCP server 拉工具),declare 依赖这些已加载
工具对象 —— 无法用 DataRequirement 占位(tool 对象非 str)。故 MCPCapability 不自管
prepare 的 preload I/O:from_legacy 复用旧 MCPToolPack 实例(preload_resource 已拉工具,
sub_resources 已填充),declare 读其 sub_resources。prepare no-op。真正 preload 自管理
需待 facade 时序改造(或 MCPExecutor.prepare + 工具声明延迟到 prepare 后阶段),本轮不做。

execute 不收编:MCP 工具是 bound call_mcp_tool closure(Route A builtin 执行),收编需改
工具 model + bound closure 归属,风险高。本轮 MCPCapability 自管 declare,execute 保持
Route A builtin。双轨:register_wrappers 与 register_capability 并存,Stage 9 删前者。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

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
from derisk.core.interface.resource.tool_entry import (
    BUILTIN_EXECUTOR_ID,
    ToolEntry,
)

logger = logging.getLogger(__name__)


class MCPCapability(Capability):
    """MCP 工具聚合能力:declare 工具列表 ToolEntry。

    capability_id="mcp";executor_id="mcp"(单例,工具执行经 builtin)。
    """

    capability_id = "mcp"

    def __init__(self, tools: Optional[List[Any]] = None):
        self._tools = tools
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "MCPCapability":
        # config 无已加载工具对象(preload I/O 才有);from_config 暂产空,真实工具走 from_legacy。
        return cls(tools=None)

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "MCPCapability":
        """从旧 MCPToolPack/MCPSSEToolPack/LocalToolPack 实例构造(过渡期)。

        读 legacy.sub_resources(preload_resource 已拉的工具对象),无新增 I/O。
        """
        subs = getattr(legacy_instance, "sub_resources", None)
        return cls(tools=list(subs) if subs else None)

    @property
    def executor_id(self) -> str:
        return "mcp"

    # ----------------------------- 输入投影(declare 工具列表) ------------ #
    def declare(self, config: Any = None) -> List[Contribution]:
        tools = self._tools or []
        if not tools:
            return []
        contribs: List[Contribution] = []
        for t in tools:
            if t is None:
                continue
            name = getattr(t, "name", "") or getattr(t, "_name", "") or ""
            if not name:
                continue
            entry = ToolEntry(
                tool_name=name,
                tool=t,
                capability_id=self.capability_id,
                executor_id=BUILTIN_EXECUTOR_ID,  # 执行体自处理 MCP 调用(Route A)
                description=getattr(t, "description", "") or "",
            )
            contribs.append(
                Contribution(
                    capability_id=self.capability_id,
                    slot=Slot.TOOLS,
                    content=entry,
                    lifetime=Lifetime.CONFIG_STATIC,
                    cache_scope=CacheScope.NONE,
                    order=60,
                )
            )
        return contribs

    def requires(self, config: Any = None) -> List[str]:
        return []

    # ----------------------------- 生命周期(无自管 I/O) ------------------- #
    async def prepare(self) -> None:
        # preload 由旧 MCPToolPack.preload_resource 完成(from_legacy 复用);prepare 仅就绪。
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # MCP 工具暂走 Route A builtin(bound call_mcp_tool closure)。
        raise NotImplementedError(
            "MCPCapability.execute 未收编 —— MCP 工具暂走 Route A builtin"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._status = ExecutorStatus.RELEASED