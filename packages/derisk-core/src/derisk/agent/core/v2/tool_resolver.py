"""工具解析器 + 资源→工具自动注入。

等价 BAIZE tool_action.py:344-362 四路查找 + base_agent.py:837-889 _inject_resource_based_tools。
"""
from typing import Any, Dict, List, Optional


class ToolResolver:
    def __init__(
        self,
        *,
        sandbox_tools: Optional[Dict[str, Any]] = None,
        system_tools: Optional[Dict[str, Any]] = None,
        unified_registry: Any = None,  # tool_registry
        resource_pack: Any = None,     # agent.resource（MCP 工具树）
        resource_map: Optional[Dict[str, List[Any]]] = None,
        sandbox_manager: Optional[Any] = None,
        enable_async_subagent: bool = False,
    ):
        self._sandbox_tools = sandbox_tools or {}
        self._system_tools = system_tools or {}
        self._unified_registry = unified_registry
        self._resource_pack = resource_pack
        self._resource_map = resource_map or {}
        self._sandbox_manager = sandbox_manager
        self._enable_async_subagent = enable_async_subagent
        self._tools: Dict[str, Any] = {}
        self._assemble()

    def _assemble(self):
        """组装工具集，等价 BAIZE preload_resource 的工具注入。"""
        # 1. 系统工具
        self._tools.update(self._system_tools)

        # 2. 沙箱工具（仅当 sandbox_manager 存在）
        if self._sandbox_manager is not None:
            self._tools.update(self._sandbox_tools)

        # 3. 统一注册表
        if self._unified_registry is not None:
            for name in self._list_registry_names():
                tool = self._unified_registry.get(name) if hasattr(self._unified_registry, "get") else None
                if tool is not None and name not in self._tools:
                    self._tools[name] = tool

    def _list_registry_names(self) -> List[str]:
        if hasattr(self._unified_registry, "list_names"):
            return list(self._unified_registry.list_names())
        if hasattr(self._unified_registry, "tools"):
            return list(self._unified_registry.tools.keys())
        return []

    def resolve(self, name: str) -> Optional[Any]:
        # 优先从已组装工具集查
        if name in self._tools:
            return self._tools[name]
        # 兜底：递归查 Resource pack（MCP 工具）
        if self._resource_pack is not None:
            return self._lookup_resource_pack(name)
        return None

    def _lookup_resource_pack(self, name: str) -> Optional[Any]:
        """递归遍历 resource pack 树查找工具。"""
        return _find_tool_in_pack(self._resource_pack, name)

    def list_tools_for_llm(self) -> List[dict]:
        """生成 LLM tool list（OpenAI 格式）。"""
        result = []
        for tool in self._tools.values():
            if hasattr(tool, "to_openai_tool"):
                result.append(tool.to_openai_tool())
            elif hasattr(tool, "_tool_base") and hasattr(tool._tool_base, "to_openai_tool"):
                result.append(tool._tool_base.to_openai_tool())
        return result


def _find_tool_in_pack(pack: Any, name: str, visited: Optional[set] = None) -> Optional[Any]:
    """递归遍历 Resource pack 树查找工具（按 name 匹配）。"""
    if visited is None:
        visited = set()
    pack_id = id(pack)
    if pack_id in visited:
        return None
    visited.add(pack_id)

    # pack 是 ToolPack / ResourcePack，有 _resources dict
    resources = getattr(pack, "_resources", None) or {}
    if isinstance(resources, dict):
        for tool_name, tool in resources.items():
            if tool_name == name:
                return tool
            # 递归子 pack
            if getattr(tool, "is_pack", False) or hasattr(tool, "sub_resources"):
                found = _find_tool_in_pack(tool, name, visited)
                if found is not None:
                    return found
    return None
