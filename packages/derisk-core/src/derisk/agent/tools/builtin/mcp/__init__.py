"""
MCP (Model Context Protocol) 工具适配器 - 已迁移到统一工具框架

提供MCP协议工具与统一工具体系的适配：
- MCPToolAdapter: MCP工具适配器
- MCPToolRegistry: MCP工具注册管理
"""

from typing import Any, Dict, List, Optional, Callable
import logging
import asyncio
import json

from ...base import ToolBase, ToolCategory, ToolRiskLevel, ToolSource
from ...metadata import ToolMetadata
from ...result import ToolResult
from ...context import ToolContext
from ...registry import ToolRegistry, tool_registry

logger = logging.getLogger(__name__)


class MCPToolAdapter(ToolBase):
    """
    MCP工具适配器 - 已迁移
    
    将MCP协议工具适配为统一 ToolBase 接口
    """
    
    def __init__(
        self,
        mcp_tool: Any,
        server_name: str,
        mcp_client: Optional[Any] = None
    ):
        self._mcp_tool = mcp_tool
        self._server_name = server_name
        self._mcp_client = mcp_client
        self._tool_name = getattr(mcp_tool, "name", str(mcp_tool))
        self._tool_description = getattr(mcp_tool, "description", "")
        self._input_schema = getattr(mcp_tool, "inputSchema", {})
        super().__init__()
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=f"mcp_{self._server_name}_{self._tool_name}",
            display_name=f"MCP: {self._tool_name}",
            description=self._tool_description or f"MCP tool: {self._tool_name}",
            category=ToolCategory.MCP,
            risk_level=ToolRiskLevel.MEDIUM,
            source=ToolSource.MCP,
            requires_permission=True,
            tags=["mcp", "external", self._server_name],
            timeout=60,
        )
    
    def _define_parameters(self) -> Dict[str, Any]:
        return self._input_schema or {
            "type": "object",
            "properties": {},
        }
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            if self._mcp_client:
                result = await self._execute_via_client(args)
            elif hasattr(self._mcp_tool, "execute"):
                result = await self._execute_direct(args)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="MCP工具无法执行：缺少执行能力",
                    tool_name=self.name
                )
            
            return ToolResult(
                success=True,
                output=self._format_result(result),
                tool_name=self.name,
                metadata={
                    "server": self._server_name,
                    "tool": self._tool_name,
                }
            )
            
        except Exception as e:
            logger.error(f"[MCPToolAdapter] 执行失败 {self._tool_name}: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                tool_name=self.name
            )
    
    async def _execute_via_client(self, args: Dict[str, Any]) -> Any:
        if hasattr(self._mcp_client, "call_tool"):
            return await self._mcp_client.call_tool(
                server_name=self._server_name,
                tool_name=self._tool_name,
                arguments=args
            )
        raise ValueError("MCP客户端缺少call_tool方法")
    
    async def _execute_direct(self, args: Dict[str, Any]) -> Any:
        result = self._mcp_tool.execute(**args)
        if asyncio.iscoroutine(result):
            result = await result
        return result
    
    def _format_result(self, result: Any) -> str:
        if isinstance(result, str):
            return result
        elif isinstance(result, dict):
            content = result.get("content", [])
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            texts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            texts.append(f"[Image: {item.get('data', '')[:50]}...]")
                        else:
                            texts.append(str(item))
                    else:
                        texts.append(str(item))
                return "\n".join(texts)
            return json.dumps(result, indent=2, ensure_ascii=False)
        elif isinstance(result, list):
            return "\n".join(str(item) for item in result)
        else:
            return str(result)
    
    def get_original_name(self) -> str:
        return self._tool_name
    
    def get_server_name(self) -> str:
        return self._server_name


class MCPToolRegistry:
    """
    MCP工具注册管理器 - 已迁移
    
    管理MCP服务器连接和工具加载
    """
    
    def __init__(self, registry: Optional[ToolRegistry] = None):
        self._tool_registry = registry or tool_registry
        self._mcp_clients: Dict[str, Any] = {}
        self._server_tools: Dict[str, List[str]] = {}
    
    def register_mcp_client(self, server_name: str, client: Any):
        """注册MCP客户端"""
        self._mcp_clients[server_name] = client
        logger.info(f"[MCPRegistry] 已注册MCP客户端: {server_name}")
    
    def unregister_mcp_client(self, server_name: str):
        """注销MCP客户端"""
        self._mcp_clients.pop(server_name, None)
        tool_names = self._server_tools.pop(server_name, [])
        for name in tool_names:
            self._tool_registry.unregister(name)
        logger.info(f"[MCPRegistry] 已注销MCP客户端: {server_name}")
    
    async def load_tools_from_server(self, server_name: str) -> List[str]:
        """从MCP服务器加载工具"""
        client = self._mcp_clients.get(server_name)
        if not client:
            logger.warning(f"[MCPRegistry] MCP服务器未注册: {server_name}")
            return []
        
        try:
            if hasattr(client, "list_tools"):
                tools = await client.list_tools()
            else:
                tools = []
            
            loaded_tools = []
            for mcp_tool in tools:
                adapter = MCPToolAdapter(
                    mcp_tool=mcp_tool,
                    server_name=server_name,
                    mcp_client=client
                )
                self._tool_registry.register(adapter)
                loaded_tools.append(adapter.name)
            
            self._server_tools[server_name] = loaded_tools
            logger.info(f"[MCPRegistry] 从 {server_name} 加载了 {len(loaded_tools)} 个工具")
            
            return loaded_tools
            
        except Exception as e:
            logger.error(f"[MCPRegistry] 加载工具失败: {e}")
            return []
    
    def get_server_tools(self, server_name: str) -> List[str]:
        """获取服务器的工具列表"""
        return self._server_tools.get(server_name, [])
    
    def list_servers(self) -> List[str]:
        """列出所有MCP服务器"""
        return list(self._mcp_clients.keys())


def register_mcp_tools(registry, mcp_clients: Optional[Dict[str, Any]] = None) -> None:
    """注册MCP工具"""
    mcp_registry = MCPToolRegistry(registry)
    
    if mcp_clients:
        for server_name, client in mcp_clients.items():
            mcp_registry.register_mcp_client(server_name, client)
    
    logger.info("[MCPTools] MCP工具注册器已初始化")


__all__ = [
    'MCPToolAdapter',
    'MCPToolRegistry',
    'register_mcp_tools',
]