"""MCP Protocol Integration for Enhanced Agent System.

Provides seamless integration of MCP (Model Context Protocol) tools
with the enhanced agent system.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from .enhanced_agent import (
    ActionResult,
    Decision,
    DecisionType,
    AgentBase,
    AgentInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class MCPToolConfig:
    """Configuration for an MCP tool."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    server_name: str = ""
    requires_permission: bool = True


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""
    name: str
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    transport: str = "stdio"  # stdio, sse, websocket


class MCPToolAdapter:
    """Adapter for MCP tools to work with enhanced agent system.
    
    This class bridges MCP protocol tools with the enhanced agent's
    tool execution system.
    """
    
    def __init__(
        self,
        server_config: MCPServerConfig,
        tool_config: MCPToolConfig,
    ):
        self.server_config = server_config
        self.tool_config = tool_config
        self._client = None
        self._connected = False
    
    @property
    def name(self) -> str:
        """Tool name with MCP prefix."""
        if self.server_config.name:
            return f"mcp__{self.server_config.name}__{self.tool_config.name}"
        return self.tool_config.name
    
    @property
    def description(self) -> str:
        return self.tool_config.description
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return self.tool_config.parameters
    
    async def connect(self) -> bool:
        """Connect to the MCP server."""
        if self._connected:
            return True
        
        try:
            if self.server_config.transport == "stdio":
                self._client = await self._connect_stdio()
            elif self.server_config.transport == "sse":
                self._client = await self._connect_sse()
            elif self.server_config.transport == "websocket":
                self._client = await self._connect_websocket()
            
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {self.server_config.name}: {e}")
            return False
    
    async def _connect_stdio(self):
        """Connect via stdio transport."""
        import asyncio
        
        if not self.server_config.command:
            raise ValueError("stdio transport requires command")
        
        process = await asyncio.create_subprocess_exec(
            self.server_config.command,
            *self.server_config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**dict(__import__('os').environ), **self.server_config.env},
        )
        
        return MCPStdioClient(process)
    
    async def _connect_sse(self):
        """Connect via SSE transport."""
        if not self.server_config.url:
            raise ValueError("sse transport requires url")
        
        return MCPSSEClient(self.server_config.url)
    
    async def _connect_websocket(self):
        """Connect via WebSocket transport."""
        if not self.server_config.url:
            raise ValueError("websocket transport requires url")
        
        import websockets
        
        ws = await websockets.connect(self.server_config.url)
        return MCPWebSocketClient(ws)
    
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionResult:
        """Execute the MCP tool."""
        if not self._connected:
            if not await self.connect():
                return ActionResult(
                    success=False,
                    output="",
                    error=f"Failed to connect to MCP server {self.server_config.name}",
                )
        
        try:
            result = await self._client.call_tool(
                tool_name=self.tool_config.name,
                arguments=arguments,
            )
            
            if result.get("isError"):
                return ActionResult(
                    success=False,
                    output="",
                    error=result.get("content", [{}])[0].get("text", "Unknown error"),
                )
            
            content = result.get("content", [])
            if isinstance(content, list) and len(content) > 0:
                text_content = " ".join(
                    item.get("text", str(item))
                    for item in content
                    if isinstance(item, dict)
                )
            else:
                text_content = str(content)
            
            return ActionResult(
                success=True,
                output=text_content,
                metadata={
                    "server": self.server_config.name,
                    "tool": self.tool_config.name,
                },
            )
        
        except Exception as e:
            logger.error(f"MCP tool execution failed: {e}")
            return ActionResult(
                success=False,
                output="",
                error=str(e),
            )
    
    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self._client and hasattr(self._client, 'close'):
            await self._client.close()
        self._connected = False
        self._client = None
    
    def get_openai_spec(self) -> Dict[str, Any]:
        """Get OpenAI function specification."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class MCPStdioClient:
    """MCP client for stdio transport."""
    
    def __init__(self, process):
        self.process = process
        self._request_id = 0
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call a tool via stdio."""
        self._request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        
        message = json.dumps(request) + "\n"
        self.process.stdin.write(message.encode())
        await self.process.stdin.drain()
        
        response_line = await self.process.stdout.readline()
        response = json.loads(response_line.decode())
        
        if "error" in response:
            return {
                "isError": True,
                "content": [{"text": response["error"].get("message", str(response["error"]))}],
            }
        
        return response.get("result", {})
    
    async def close(self):
        """Close the process."""
        if self.process:
            self.process.terminate()
            await self.process.wait()


class MCPSSEClient:
    """MCP client for SSE transport."""
    
    def __init__(self, url: str):
        self.url = url
        self._request_id = 0
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call a tool via SSE."""
        import aiohttp
        
        self._request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.url,
                json=request,
            ) as response:
                result = await response.json()
        
        if "error" in result:
            return {
                "isError": True,
                "content": [{"text": result["error"].get("message", str(result["error"]))}],
            }
        
        return result.get("result", {})
    
    async def close(self):
        pass


class MCPWebSocketClient:
    """MCP client for WebSocket transport."""
    
    def __init__(self, ws):
        self.ws = ws
        self._request_id = 0
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call a tool via WebSocket."""
        self._request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        
        await self.ws.send(json.dumps(request))
        response = await self.ws.recv()
        result = json.loads(response)
        
        if "error" in result:
            return {
                "isError": True,
                "content": [{"text": result["error"].get("message", str(result["error"]))}],
            }
        
        return result.get("result", {})
    
    async def close(self):
        await self.ws.close()


class MCPToolRegistry:
    """Registry for MCP tools.
    
    Manages MCP server connections and tool registration.
    """
    
    def __init__(self):
        self._servers: Dict[str, MCPServerConfig] = {}
        self._tools: Dict[str, MCPToolAdapter] = {}
        self._initialized_servers: Dict[str, Any] = {}
    
    def register_server(
        self,
        config: MCPServerConfig,
    ) -> "MCPToolRegistry":
        """Register an MCP server configuration."""
        self._servers[config.name] = config
        return self
    
    def register_tool(
        self,
        server_name: str,
        tool_config: MCPToolConfig,
    ) -> "MCPToolRegistry":
        """Register a tool from an MCP server."""
        if server_name not in self._servers:
            raise ValueError(f"Server {server_name} not registered")
        
        server_config = self._servers[server_name]
        adapter = MCPToolAdapter(server_config, tool_config)
        self._tools[adapter.name] = adapter
        return self
    
    def get_tool(self, name: str) -> Optional[MCPToolAdapter]:
        """Get a tool by name."""
        # 支持带前缀和不带前缀的查找
        if name in self._tools:
            return self._tools[name]
        
        mcp_name = f"mcp__{name}"
        for tool_name, tool in self._tools.items():
            if tool_name.endswith(f"__{name}") or tool_name == mcp_name:
                return tool
        
        return None
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get OpenAI function specifications for all tools."""
        return [tool.get_openai_spec() for tool in self._tools.values()]
    
    async def initialize_server(
        self,
        server_name: str,
    ) -> bool:
        """Initialize a server and discover its tools."""
        if server_name not in self._servers:
            return False
        
        config = self._servers[server_name]
        
        # 这里应该调用MCP的list_tools方法获取工具列表
        # 简化实现，实际需要与MCP服务器交互
        return True
    
    async def initialize_all(self) -> Dict[str, bool]:
        """Initialize all registered servers."""
        results = {}
        for server_name in self._servers:
            results[server_name] = await self.initialize_server(server_name)
        return results
    
    async def shutdown(self):
        """Shutdown all connections."""
        for tool in self._tools.values():
            await tool.disconnect()


class MCPEnabledAgent(AgentBase):
    """Agent that can use MCP tools.
    
    Extends AgentBase with MCP tool support.
    """
    
    def __init__(
        self,
        info: AgentInfo,
        mcp_registry: Optional[MCPToolRegistry] = None,
        **kwargs,
    ):
        super().__init__(info, **kwargs)
        self._mcp_registry = mcp_registry or MCPToolRegistry()
    
    async def execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionResult:
        """Execute a tool, supporting both regular and MCP tools."""
        # 首先检查是否是MCP工具
        mcp_tool = self._mcp_registry.get_tool(tool_name)
        if mcp_tool:
            return await mcp_tool.execute(tool_args, context)
        
        # 回退到基类的工具执行
        return await super().act(
            Decision(
                type=DecisionType.TOOL_CALL,
                tool_name=tool_name,
                tool_args=tool_args,
            ),
        )


def create_mcp_agent(
    name: str,
    description: str,
    mcp_servers: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    **kwargs,
) -> MCPEnabledAgent:
    """Factory function to create an MCP-enabled agent.
    
    Args:
        name: Agent name
        description: Agent description
        mcp_servers: List of MCP server configurations
        tools: List of tool configurations
        **kwargs: Additional agent configuration
    
    Returns:
        Configured MCP-enabled agent
    
    Example:
        agent = create_mcp_agent(
            name="data_agent",
            description="Data analysis agent",
            mcp_servers=[
                {
                    "name": "database",
                    "url": "http://localhost:8080/mcp",
                    "transport": "sse",
                }
            ],
            tools=[
                {
                    "server": "database",
                    "name": "query",
                    "description": "Execute SQL query",
                }
            ],
        )
    """
    mcp_registry = MCPToolRegistry()
    
    for server_config in mcp_servers:
        server = MCPServerConfig(
            name=server_config["name"],
            command=server_config.get("command"),
            args=server_config.get("args", []),
            env=server_config.get("env", {}),
            url=server_config.get("url"),
            transport=server_config.get("transport", "stdio"),
        )
        mcp_registry.register_server(server)
    
    for tool_config in tools:
        tool_name = f"mcp__{tool_config['server']}__{tool_config['name']}"
        tool = MCPToolConfig(
            name=tool_config["name"],
            description=tool_config.get("description", f"MCP tool {tool_name}"),
            parameters=tool_config.get("parameters", {}),
            server_name=tool_config["server"],
        )
        mcp_registry.register_tool(tool_config["server"], tool)
    
    info = AgentInfo(
        name=name,
        description=description,
        tools=list(mcp_registry.list_tools()),
        **{k: v for k, v in kwargs.items() if hasattr(AgentInfo, k)},
    )
    
    return MCPEnabledAgent(info=info, mcp_registry=mcp_registry)


__all__ = [
    "MCPToolConfig",
    "MCPServerConfig",
    "MCPToolAdapter",
    "MCPToolRegistry",
    "MCPEnabledAgent",
    "create_mcp_agent",
]