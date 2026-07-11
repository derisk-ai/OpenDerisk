"""MCPCapabilityResource —— MCP 工具聚合 capability(RFC-005 Step C)。

MCP 资源(MCPToolPack/MCPSSEToolPack/MCPCollectSSEToolPack/LocalToolPack)都是
ToolPack 子类,本质是"工具聚合":declare 产工具列表 TOOLS 槽,工具执行体在
MCP server / 本地函数。无 system 声明内容(工具即全部)。

双轨:包装旧 ToolPack 子类实例(由 build_resource 构建进 ResourcePack),declare
把 ToolPack.sub_resources(各 BaseTool)包成 ToolEntry(capability_id=mcp,
executor_id=builtin,选B 执行复用)。MCPExecutor 包装 server 调用留后续。
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
from derisk.core.interface.resource.tool_entry import (
    BUILTIN_EXECUTOR_ID,
    ToolEntry,
)
from derisk.core.interface.resource.protocol import ResourceProtocol

logger = logging.getLogger(__name__)


class MCPCapabilityResource(ResourceProtocol):
    """MCP 工具聚合 capability:声明工具列表 TOOLS。

    capability_id="mcp"。包装旧 ToolPack 子类,declare 把其 sub_resources
    包成 ToolEntry(capability_id=mcp, executor_id=builtin)。
    """

    capability_id = "mcp"
    protocol_version = 1

    def __init__(self, legacy_instance: Any = None, tools: Optional[List[Any]] = None):
        self._legacy = legacy_instance
        self._tools = tools

    def declare(self, config: Any = None) -> List[Contribution]:
        """实例 declare:委托 declare_tools 产 TOOLS Contribution(每个工具一个 ToolEntry)。"""
        return self.declare_tools()

    def declare_tools(self) -> List[Contribution]:
        """产工具列表 TOOLS Contribution(每个工具一个 ToolEntry,缓存 NONE)。"""
        tools = self._resolve_tools()
        if not tools:
            return []
        tool_entries = [
            ToolEntry(
                tool_name=getattr(t, "name", "") or getattr(t, "_name", "") or "",
                tool=t,
                capability_id=self.capability_id,
                executor_id=BUILTIN_EXECUTOR_ID,  # 选B:工具执行体自处理 MCP 调用
                description=getattr(t, "description", "") or "",
            )
            for t in tools
            if t is not None
        ]
        if not tool_entries:
            return []
        # 每个 ToolEntry 作为一个 TOOLS Contribution
        return [
            Contribution(
                capability_id=self.capability_id,
                slot=Slot.TOOLS,
                content=entry,
                lifetime=Lifetime.CONFIG_STATIC,
                cache_scope=CacheScope.NONE,
                order=60,
            )
            for entry in tool_entries
        ]

    def _resolve_tools(self) -> List[Any]:
        """从显式 tools 或 legacy ToolPack.sub_resources 取工具列表。"""
        if self._tools is not None:
            return self._tools
        if self._legacy is None:
            return []
        # ToolPack.sub_resources 是工具列表(BaseTool)
        try:
            subs = getattr(self._legacy, "sub_resources", None)
            if subs:
                return list(subs)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[mcp] resolve sub_resources failed: {e}")
        return []

    def requires(self, config: Any = None) -> List[str]:
        return []