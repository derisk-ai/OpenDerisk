"""
MCP (Model Context Protocol) 工具适配器

提供MCP协议工具与Core_v2工具体系的适配：
- MCPToolAdapter: MCP工具适配器
- MCPToolRegistry: MCP工具注册管理
"""

from typing import Any, Dict, List, Optional, Callable
import logging
import asyncio
import json

from .tool_base import ToolBase, ToolMetadata, ToolResult, ToolRegistry

logger = logging.getLogger(__name__)


class MCPToolAdapter(ToolBase):
    """
    MCP工具适配器
    
    将MCP协议工具适配为Core_v2 ToolBase接口
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
            description=self._tool_description or f"MCP tool: {self._tool_name}",
            parameters=self._input_schema or {},
            requires_permission=True,
            dangerous=False,
            category="mcp",
            version="1.0.0"
        )
    
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
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
                    error="MCP工具无法执行：缺少执行能力"
                )
            
            return ToolResult(
                success=True,
                output=self._format_result(result),
                metadata={
                    "server": self._server_name,
                    "tool": self._tool_name,
                    "original_result": result
                }
            )
            
        except Exception as e:
            logger.error(f"[MCPToolAdapter] 执行失败 {self._tool_name}: {e}")
            return ToolResult(
                success=False,
                output="",
                error=str(e)
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
    MCP工具注册管理器
    
    管理MCP服务器连接和工具加载
    """
    
    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self._tool_registry = tool_registry or ToolRegistry()
        self._mcp_clients: Dict[str, Any] = {}
        self._server_tools: Dict[str, List[str]] = {}
    
    def register_mcp_client(self, server_name: str, client: Any):
        """注册MCP客户端"""
        self._mcp_clients[server_name] = client
        logger.info(f"[MCPRegistry] 已注册MCP客户端: {server_name}")
    
    def unregister_mcp_client(self, server_name: str):
        """注销MCP客户端"""
        if server_name in self._mcp_clients:
            del self._mcp_clients[server_name]
        
        if server_name in self._server_tools:
            for tool_name in self._server_tools[server_name]:
                self._tool_registry.unregister(tool_name)
            del self._server_tools[server_name]
        
        logger.info(f"[MCPRegistry] 已注销MCP客户端: {server_name}")
    
    async def load_tools_from_server(self, server_name: str) -> List[ToolBase]:
        """从MCP服务器加载工具"""
        client = self._mcp_clients.get(server_name)
        if not client:
            logger.warning(f"[MCPRegistry] MCP客户端不存在: {server_name}")
            return []
        
        tools = []
        tool_names = []
        
        try:
            if hasattr(client, "list_tools"):
                mcp_tools = await client.list_tools()
            elif hasattr(client, "tools"):
                mcp_tools = client.tools
            else:
                logger.warning(f"[MCPRegistry] MCP客户端不支持列出工具: {server_name}")
                return []
            
            for mcp_tool in mcp_tools:
                adapter = MCPToolAdapter(
                    mcp_tool=mcp_tool,
                    server_name=server_name,
                    mcp_client=client
                )
                self._tool_registry.register(adapter)
                tools.append(adapter)
                tool_names.append(adapter.metadata.name)
            
            self._server_tools[server_name] = tool_names
            
            logger.info(
                f"[MCPRegistry] 从 {server_name} 加载了 {len(tools)} 个工具"
            )
            
        except Exception as e:
            logger.error(f"[MCPRegistry] 加载工具失败 {server_name}: {e}")
        
        return tools
    
    async def load_all_tools(self) -> Dict[str, List[ToolBase]]:
        """加载所有MCP服务器的工具"""
        all_tools = {}
        for server_name in list(self._mcp_clients.keys()):
            tools = await self.load_tools_from_server(server_name)
            all_tools[server_name] = tools
        return all_tools
    
    def get_tool_registry(self) -> ToolRegistry:
        """获取底层工具注册表"""
        return self._tool_registry
    
    def list_server_tools(self, server_name: str) -> List[str]:
        """列出指定服务器的工具"""
        return self._server_tools.get(server_name, [])
    
    def list_all_servers(self) -> List[str]:
        """列出所有MCP服务器"""
        return list(self._mcp_clients.keys())


class MCPConnectionManager:
    """
    MCP连接管理器
    
    管理MCP服务器的连接和生命周期
    """
    
    def __init__(self):
        self._connections: Dict[str, Any] = {}
        self._tool_registry = MCPToolRegistry()
    
    async def connect(
        self,
        server_name: str,
        config: Dict[str, Any]
    ) -> bool:
        """连接到MCP服务器"""
        try:
            client = await self._create_client(config)
            
            if client:
                self._connections[server_name] = {
                    "config": config,
                    "client": client,
                    "status": "connected"
                }
                self._tool_registry.register_mcp_client(server_name, client)
                
                await self._tool_registry.load_tools_from_server(server_name)
                
                logger.info(f"[MCPManager] 连接成功: {server_name}")
                return True
            
        except Exception as e:
            logger.error(f"[MCPManager] 连接失败 {server_name}: {e}")
            return False
        
        return False
    
    async def disconnect(self, server_name: str) -> bool:
        """断开MCP服务器连接"""
        if server_name not in self._connections:
            return False
        
        try:
            conn = self._connections[server_name]
            client = conn.get("client")
            
            if client and hasattr(client, "close"):
                await client.close()
            
            self._tool_registry.unregister_mcp_client(server_name)
            del self._connections[server_name]
            
            logger.info(f"[MCPManager] 已断开: {server_name}")
            return True
            
        except Exception as e:
            logger.error(f"[MCPManager] 断开失败 {server_name}: {e}")
            return False
    
    async def _create_client(self, config: Dict[str, Any]) -> Optional[Any]:
        """创建MCP客户端"""
        transport = config.get("transport", "stdio")
        
        if transport == "stdio":
            return await self._create_stdio_client(config)
        elif transport == "sse":
            return await self._create_sse_client(config)
        elif transport == "websocket":
            return await self._create_ws_client(config)
        else:
            logger.warning(f"[MCPManager] 不支持的传输类型: {transport}")
            return None
    
    async def _create_stdio_client(self, config: Dict[str, Any]) -> Optional[Any]:
        """创建STDIO客户端"""
        try:
            from derisk.agent.resource.tool.mcp import MCPToolsKit
            
            command = config.get("command")
            args = config.get("args", [])
            env = config.get("env", {})
            
            if not command:
                return None
            
            client = MCPToolsKit(
                command=command,
                args=args,
                env=env
            )
            
            return client
            
        except ImportError:
            logger.warning("[MCPManager] MCPToolsKit不可用")
            return None
        except Exception as e:
            logger.error(f"[MCPManager] 创建STDIO客户端失败: {e}")
            return None
    
    async def _create_sse_client(self, config: Dict[str, Any]) -> Optional[Any]:
        """创建SSE客户端"""
        try:
            url = config.get("url")
            if not url:
                return None
            
            class SSEMCPClient:
                def __init__(self, url: str):
                    self._url = url
                    self._tools = []
                
                async def list_tools(self):
                    return self._tools
                
                async def call_tool(self, tool_name: str, arguments: dict):
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{self._url}/tools/{tool_name}/call",
                            json={"arguments": arguments}
                        ) as response:
                            return await response.json()
                
                async def close(self):
                    pass
            
            return SSEMCPClient(url)
            
        except Exception as e:
            logger.error(f"[MCPManager] 创建SSE客户端失败: {e}")
            return None
    
    async def _create_ws_client(self, config: Dict[str, Any]) -> Optional[Any]:
        """创建WebSocket客户端"""
        try:
            url = config.get("url")
            if not url:
                return None
            
            class WSMCPClient:
                def __init__(self, url: str):
                    self._url = url
                    self._ws = None
                    self._tools = []
                
                async def connect(self):
                    import websockets
                    self._ws = await websockets.connect(self._url)
                
                async def list_tools(self):
                    return self._tools
                
                async def call_tool(self, tool_name: str, arguments: dict):
                    if self._ws:
                        import json
                        await self._ws.send(json.dumps({
                            "type": "tool_call",
                            "tool": tool_name,
                            "arguments": arguments
                        }))
                        response = await self._ws.recv()
                        return json.loads(response)
                    return None
                
                async def close(self):
                    if self._ws:
                        await self._ws.close()
            
            client = WSMCPClient(url)
            await client.connect()
            return client
            
        except Exception as e:
            logger.error(f"[MCPManager] 创建WebSocket客户端失败: {e}")
            return None
    
    def get_tool_registry(self) -> MCPToolRegistry:
        """获取MCP工具注册表"""
        return self._tool_registry
    
    def get_connection_status(self) -> Dict[str, str]:
        """获取所有连接状态"""
        return {
            name: conn.get("status", "unknown")
            for name, conn in self._connections.items()
        }


mcp_connection_manager = MCPConnectionManager()


def adapt_mcp_tool(
    mcp_tool: Any,
    server_name: str,
    mcp_client: Optional[Any] = None
) -> MCPToolAdapter:
    """将MCP工具适配为ToolBase"""
    return MCPToolAdapter(
        mcp_tool=mcp_tool,
        server_name=server_name,
        mcp_client=mcp_client
    )


def register_mcp_tools(
    registry: ToolRegistry,
    server_name: str,
    mcp_tools: List[Any],
    mcp_client: Optional[Any] = None
) -> List[ToolBase]:
    """批量注册MCP工具"""
    adapters = []
    for mcp_tool in mcp_tools:
        adapter = adapt_mcp_tool(mcp_tool, server_name, mcp_client)
        registry.register(adapter)
        adapters.append(adapter)
    
    logger.info(
        f"[MCPTools] 从 {server_name} 注册了 {len(adapters)} 个工具"
    )
    
    return adapters