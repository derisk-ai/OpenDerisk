"""MCPCapability —— MCP 工具聚合自管理资源能力(RFC-006 Stage 7/8)。

MCP 聚合一组 MCP server 工具。prepare 自管 preload:连 MCP server、调
get_mcp_tool_list 拉工具、用 FunctionTool 重建工具对象(执行体绑 call_mcp_tool 闭包)存
self._tools。declare 把 self._tools 包成 ToolEntry(builtin executor,Route A——执行体
bound_call 自处理 MCP 调用)。release 清工具。

facade 时序已改 prepare 先于 declare(RFC-006 Stage 8),declare 能读到 prepare 产的
self._tools。原 preload_resource 逻辑(挪自 MCPToolPack.preload_resource:mcp.py 219-340)
迁到 prepare:server 连接 + get_mcp_tool_list + switch_mcp_input_schema + FunctionTool 重建。

execute 不收编:工具是 BaseTool(Route A builtin 执行,ToolAction 直调 tool.execute →
bound_call → call_mcp_tool)。MCP 工具无状态(server/headers 在闭包里),适合 Route A。

每 server 一个独立的连接(prepare 时拉工具列表),工具执行时 call_mcp_tool 会重新连
SSE(无状态连接,与旧一致)。
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any, List, Optional, Union

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
    """MCP 工具聚合能力:自管 preload(prepare)+ declare 工具列表 + 持有工具对象。

    capability_id="mcp:{mcp_name}";executor_id 同(多 MCP 独立)。
    """

    def __init__(
        self,
        mcp_name: str = "",
        mcp_servers: Optional[Union[str, List[str]]] = None,
        headers: Optional[dict] = None,
        allow_tools: Optional[List[str]] = None,
        tool_id: Optional[str] = None,
        timeout: int = 60,
        source: str = "faas",
        overwrite_same_tool: bool = True,
    ):
        self._mcp_name = mcp_name
        self._mcp_servers = mcp_servers
        self._headers = headers or {}
        self._allow_tools = allow_tools
        self._tool_id = tool_id
        self._timeout = timeout
        self._source = source
        self._overwrite_same_tool = overwrite_same_tool
        self._tools: List[Any] = []
        self._status = ExecutorStatus.UNINITIALIZED

    @classmethod
    def from_config(cls, value: dict, system_app: Any = None) -> "MCPCapability":
        """从 AgentResource.value dict 构造(不连 server;prepare 时拉工具)。

        value 形如 {"mcp_name","mcp_servers"/"servers","headers","allow_tools",
        "tool_id","timeout","source"}。MCP 前端配置通常带 mcp_name + servers + headers。
        """
        value = value or {}
        servers = value.get("mcp_servers") or value.get("servers") or value.get("url")
        headers = value.get("headers")
        if isinstance(headers, str) and headers:
            import json

            try:
                headers = json.loads(headers)
            except Exception:  # noqa: BLE001
                headers = {}
        return cls(
            mcp_name=value.get("mcp_name") or value.get("name") or "",
            mcp_servers=servers,
            headers=headers if headers is not None else {},
            allow_tools=value.get("allow_tools"),
            tool_id=value.get("tool_id"),
            timeout=value.get("timeout", 60),
            source=value.get("source", "faas"),
        )

    @classmethod
    def from_legacy(cls, legacy_instance: Any) -> "MCPCapability":
        """从旧 MCPToolPack/MCPSSEToolPack 实例构造(过渡期)。

        读旧实例 runtime 配置(mcp_servers/headers/mcp_name/tool_id/allow_tools/timeout/
        source);若旧实例已 preload(._loaded=True)则复用其 _tools,否则 prepare 时拉。
        """
        cap = cls(
            mcp_name=getattr(legacy_instance, "_mcp_name", "") or getattr(legacy_instance, "name", ""),
            mcp_servers=getattr(legacy_instance, "_mcp_servers", None),
            headers=getattr(legacy_instance, "_headers", {}) or {},
            allow_tools=getattr(legacy_instance, "_allow_tools", None),
            tool_id=getattr(legacy_instance, "_tool_id", None),
            timeout=getattr(legacy_instance, "_timeout", 60) or 60,
            source=getattr(legacy_instance, "_source", "faas") or "faas",
            overwrite_same_tool=getattr(legacy_instance, "_overwrite_same_tool", True),
        )
        # 复用旧实例已 preload 的工具(sub_resources 非空即旧 ToolPack 已加载);prepare 见
        # self._tools 非空会免拉。无则 prepare 时重新连 server 拉(自管理)。
        subs = getattr(legacy_instance, "sub_resources", None) or []
        if subs:
            cap._tools = list(subs)
            cap._status = ExecutorStatus.READY
        return cap

    @property
    def capability_id(self) -> str:
        return f"mcp:{self._mcp_name}" if self._mcp_name else "mcp"

    @property
    def executor_id(self) -> str:
        return self.capability_id

    # ----------------------------- 输入投影(declare 工具列表) ------------ #
    def declare(self, config: Any = None) -> List[Contribution]:
        contribs: List[Contribution] = []
        for t in self._tools:
            if t is None:
                continue
            name = getattr(t, "name", "") or getattr(t, "_name", "") or ""
            if not name:
                continue
            entry = ToolEntry(
                tool_name=name,
                tool=t,
                capability_id=self.capability_id,
                executor_id=BUILTIN_EXECUTOR_ID,  # 执行体自处理 MCP(Route A builtin)
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
        # MCP 工具执行经 builtin(bound call_mcp_tool closure),不依赖共享 executor。
        return []

    # ----------------------------- 生命周期(preload I/O) ----------------- #
    async def prepare(self) -> None:
        """连 MCP server + get_mcp_tool_list + 重建 FunctionTool(挪自 preload_resource)。

        对每个 server:调 get_mcp_tool_list 拉工具列表,逐工具:
          args = switch_mcp_input_schema(tool.inputSchema)
          bound_call = partial(call_mcp_tool, mcp_name, tool_name, server, headers, timeout, tool_id)
          FunctionTool(name=tool.name, func=bound_call, description, args=args)
        存 self._tools。无 mcp_servers 或拉取失败降级(空工具列表,不崩)。
        """
        if self._tools:  # from_legacy 已复用旧 preload 工具
            self._status = ExecutorStatus.READY
            return
        if not self._mcp_servers:
            self._status = ExecutorStatus.READY
            return
        try:
            from derisk_serve.agent.resource.tool.mcp_utils import (
                call_mcp_tool,
                get_mcp_tool_list,
                switch_mcp_input_schema,
            )

            server_list = (
                list(self._mcp_servers)
                if isinstance(self._mcp_servers, list)
                else [s for s in str(self._mcp_servers).split(";") if s]
            )
            seen = set()
            for server in server_list:
                try:
                    result = await get_mcp_tool_list(
                        self._mcp_name,
                        server,
                        headers=self._headers,
                        allow_tools=self._allow_tools,
                        tool_id=self._tool_id,
                        timeout=self._timeout,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"[mcp-capability] get_mcp_tool_list from {server} failed: {e}"
                    )
                    continue
                if not result or not getattr(result, "tools", None):
                    continue
                for tool in result.tools:
                    tool_name = tool.name
                    if not self._overwrite_same_tool and tool_name in seen:
                        continue
                    try:
                        args = switch_mcp_input_schema(tool.inputSchema)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            f"[mcp-capability] switch input schema for {tool_name} failed: {e}"
                        )
                        args = {}
                    from derisk.agent.resource import FunctionTool

                    bound_call = partial(
                        call_mcp_tool,
                        mcp_name=self._mcp_name,
                        tool_name=tool_name,
                        server=server,
                        headers=self._headers,
                        timeout=self._timeout,
                        tool_id=self._tool_id,
                    )
                    try:
                        ft = FunctionTool(
                            name=tool_name,
                            func=bound_call,
                            description=tool.description or "",
                            args=args,
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            f"[mcp-capability] build FunctionTool {tool_name} failed: {e}"
                        )
                        continue
                    self._tools.append(ft)
                    seen.add(tool_name)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[mcp-capability] prepare preload failed: {e}")
        self._status = ExecutorStatus.READY

    async def execute(self, call: ExecutorCall) -> Any:
        # MCP 工具是 BaseTool,执行经 Route A builtin(ToolAction 直调 tool.execute → bound_call)。
        raise NotImplementedError(
            "MCPCapability.execute 未收编 —— MCP 工具走 Route A builtin(具名闭包)"
        )

    async def release(self, reason: ReleaseReason) -> None:
        self._tools = []
        self._status = ExecutorStatus.RELEASED