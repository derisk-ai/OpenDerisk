import asyncio
import json
import logging
import socket
import traceback
import uuid
import os
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools.base import Tool
from mcp.server.sse import SseServerTransport
from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS
from starlette.applications import Starlette
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route, WebSocketRoute
from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_validator
from .types import ServerSettings, StdioToWsArgs

logger = logging.getLogger(__name__)


class BearerAuthBackend(AuthenticationBackend):
    def __init__(self, valid_tokens):
        self.valid_tokens = valid_tokens

    async def authenticate(self, request):
        if not self.valid_tokens:
            # Return authentication credentials and user object
            return AuthCredentials(["authenticated"]), SimpleUser("anonymous")

        if "Authorization" not in request.headers:
            return None

        auth = request.headers["Authorization"]
        try:
            scheme, token = auth.split()
            if scheme.lower() != "bearer":
                return None

            if token in self.valid_tokens:
                # Return authentication credentials and user object
                return AuthCredentials(["authenticated"]), SimpleUser(token)
        except ValueError:
            pass

        return None


class MCPGateway:
    def __init__(
            self,
            gateway_host: str = "localhost",
            gateway_port: int = 8765,
            settings=None,
            auth_tokens: List[str] = None,
    ):
        self.gateway_host = gateway_host
        self.gateway_port = gateway_port
        self.settings = settings
        self.auth_tokens = auth_tokens or []

        # Store registered MCP server connections
        self.registered_servers: Dict[str, Dict[str, Any]] = {}

        # For generating unique request IDs
        self.next_request_id = 1

        # Store pending requests and responses
        self.pending_requests: Dict[int, asyncio.Future] = {}

        # Create FastMCP instance for the gateway
        self.gateway_mcp = FastMCP()

        # Add basic tools for the gateway here
        self.gateway_mcp.add_tool(
            self.list_servers, "list_servers", "List all registered MCP servers"
        )

    async def list_servers(self) -> List[Dict[str, Any]]:
        """List all registered servers"""
        return [
            {
                "id": server_id,
                "name": server["name"],
                "tools_count": len(server.get("tools", [])),
            }
            for server_id, server in self.registered_servers.items()
        ]

    async def handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connections from Starlette"""
        if not websocket.user or not websocket.user.is_authenticated:
            await websocket.close(code=1008, reason="Unauthorized")
            logger.warning("Unauthorized WebSocket connection attempt")
            return

        await websocket.accept()
        logger.debug("WebSocket connection accepted")

        # Create message queue for handling received messages
        message_queue = asyncio.Queue()

        # Start message receiving task
        receiver_task = asyncio.create_task(
            self.websocket_receiver(websocket, message_queue)
        )

        try:
            await self.server_registration_handler(websocket, message_queue)
        except Exception as e:
            logger.error(f"Error handling WebSocket connection: {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            # Cancel receiver task
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass

    async def websocket_receiver(
            self, websocket: WebSocket, message_queue: asyncio.Queue
    ):
        """Continuously receive WebSocket messages and put them in queue"""
        try:
            while True:
                message = await websocket.receive()
                logger.debug(f"Received raw WebSocket message: {message}")
                if "text" in message:
                    await message_queue.put(message["text"])
                elif "bytes" in message:
                    await message_queue.put(message["bytes"])
                else:
                    logger.warning(f"Unknown message type: {message}")
                    continue
                # Ignore other types of messages
        except Exception as e:
            logger.error(f"WebSocket receiver error: {str(e)}")
            # Put an error marker to let the consumer know that reception has stopped
            await message_queue.put(None)

    async def server_registration_handler(
            self, websocket: WebSocket, message_queue: asyncio.Queue
    ):
        """Handle registration requests from MCP servers"""
        server_id = None

        # Receive first message (registration info)
        registration_info_raw = await message_queue.get()
        if registration_info_raw is None:
            logger.error("Failed to receive registration info")
            return

        try:
            info = json.loads(registration_info_raw)

            # Use client-provided ID or generate new ID
            server_id = info.get("id") or str(uuid.uuid4())

            # If it's a JSONRPC format registration request, get info from params
            if (
                    "method" in info
                    and info.get("method") == "register"
                    and "params" in info
            ):
                params = info.get("params", {})
                server_name = params.get("name", f"server-{server_id}")
            else:
                # Compatible with old format
                server_name = info.get("name", f"server-{server_id}")

            logger.info(f"MCP server registered: {server_name} (ID: {server_id})")

            # Store server connection
            self.registered_servers[server_id] = {
                "websocket": websocket,
                "message_queue": message_queue,
                "name": server_name,
                "info": info,
                "tools": [],
            }

            # Send registration response
            await websocket.send_text(
                json.dumps(
                    {
                        "status": "received",
                        "id": server_id,
                        "message": f"Registration request received, server ID: {server_id}",
                    }
                )
            )

            # Wait 5 seconds, then send initialization request
            logger.info("Waiting 5 seconds before sending initialization request")

            # Send initialization request
            logger.info(f"Sending initialization request to server {server_id}")
            init_result = await self.send_request_to_server(
                server_id,
                "initialize",
                {
                    "protocolVersion": "0.1.0",
                    "clientInfo": {"name": "MCPGateway", "version": "1.0.0"},
                    "capabilities": {},
                },
            )

            if not init_result:
                logger.error(f"Failed to initialize server {server_id}")
                del self.registered_servers[server_id]
                await websocket.send_text(
                    json.dumps({"status": "error", "message": "Initialization failed"})
                )
                return
            # protocol_version = init_result.get("protocolVersion")
            # if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            #     raise ValueError(
            #         f"Unsupported protocol version from the server: {protocol_version}"
            #     )

            logger.info(f"Server {server_id} initialized successfully: {init_result}")
            # Then Send notifications/initialized
            await websocket.send_text(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    }
                )
            )
            await asyncio.sleep(5)

            # Get server tools list
            logger.info(f"Requesting tools list from server {server_id}")
            tools_result = await self.send_request_to_server(
                server_id, "tools/list", {}
            )

            if not tools_result or "tools" not in tools_result:
                logger.error(f"Failed to get tools list from server {server_id}")
                del self.registered_servers[server_id]
                await websocket.send_text(
                    json.dumps(
                        {"status": "error", "message": "Failed to get tools list"}
                    )
                )
                return

            # Register tools
            for tool in tools_result["tools"]:
                self.register_remote_tool(server_id, tool, server_name)

            # Update server tools list
            self.registered_servers[server_id]["tools"] = tools_result["tools"]

            # Send confirmation message
            await websocket.send_text(
                json.dumps(
                    {
                        "status": "registered",
                        "id": server_id,
                        "message": f"Registration successful, loaded {len(tools_result['tools'])} tools",
                    }
                )
            )

            logger.info(f"Tools registered successfully: {server_id}")

            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self.send_heartbeat(server_id))

            try:
                # Enter message processing loop
                await self.handle_server_messages(server_id, message_queue)
            finally:
                # Cancel heartbeat task
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"Error processing server registration: {str(e)}")
            logger.error(traceback.format_exc())
            try:
                await websocket.send_text(
                    json.dumps(
                        {
                            "status": "error",
                            "message": f"Registration processing error: {str(e)}",
                        }
                    )
                )
            except:
                pass

    async def wait_for_response(
            self,
            server_id: str,
            message_queue: asyncio.Queue,
            request_id: int,
            future: asyncio.Future,
    ):
        """Wait for response with specific request ID"""
        try:
            while True:
                message_raw = await message_queue.get()
                logger.debug(f"Received message: {message_raw}")
                if message_raw is None:
                    # Receiver has stopped
                    if not future.done():
                        future.set_exception(Exception("WebSocket connection closed"))
                    return

                try:
                    message = json.loads(message_raw)
                    logger.debug(f"Processing message: {message}")

                    # Check if it's a response
                    if "id" in message and message["id"] == request_id:
                        if "result" in message:
                            logger.debug(f"Found response for request {request_id}")
                            if not future.done():
                                future.set_result(message["result"])
                            return
                        elif "error" in message:
                            logger.debug(
                                f"Found error response for request {request_id}"
                            )
                            if not future.done():
                                future.set_exception(
                                    Exception(f"Server error: {message['error']}")
                                )
                            return
                    else:
                        # Not the response we're looking for, put it back in the queue for other handlers
                        logger.debug(
                            f"Message is not a response for request {request_id}, putting it back in queue"
                        )
                        await message_queue.put(message_raw)
                        await asyncio.sleep(
                            0.1
                        )  # Brief sleep to avoid immediately processing the same message

                except json.JSONDecodeError:
                    logger.error(f"Cannot parse JSON: {message_raw}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                    continue
        except asyncio.CancelledError:
            logger.debug("Task waiting for response was cancelled")
            raise
        except Exception as e:
            logger.error(f"Error waiting for response: {str(e)}")
            logger.error(traceback.format_exc())
            if not future.done():
                future.set_exception(Exception(f"Error waiting for response: {str(e)}"))

    async def handle_server_messages(
            self, server_id: str, message_queue: asyncio.Queue
    ):
        """Process messages from the server"""
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self.send_heartbeat(server_id))
        while True:
            try:
                message_raw = await message_queue.get()
                if message_raw is None:
                    logger.info(f"Server {server_id} connection closed")
                    break

                logger.debug(f"Received message from server {server_id}: {message_raw}")
                data = json.loads(message_raw)

                # Handle responses
                if "id" in data and "result" in data:
                    req_id = data["id"]
                    logger.debug(f"Received response for request {req_id}")
                    if req_id in self.pending_requests:
                        future = self.pending_requests.pop(req_id)
                        if not future.done():
                            future.set_result(data["result"])
                    else:
                        logger.warning(
                            f"Received response for unknown request ID: {req_id}"
                        )

                # Handle error responses
                elif "id" in data and "error" in data:
                    req_id = data["id"]
                    logger.debug(f"Received error response for request {req_id}")
                    if req_id in self.pending_requests:
                        future = self.pending_requests.pop(req_id)
                        if not future.done():
                            future.set_exception(
                                Exception(f"Server error: {data['error']}")
                            )
                    else:
                        logger.warning(
                            f"Received error for unknown request ID: {req_id}"
                        )

                # Handle notifications (if needed)
                elif "method" in data and "id" not in data:
                    # Handle notifications, e.g., tools/list_changed
                    if data["method"] == "notifications/tools/list_changed":
                        await self.refresh_server_tools(server_id)

                else:
                    logger.warning(f"Received unrecognized message: {data}")

            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {str(e)}")
                continue
            except Exception as e:
                logger.error(
                    f"Error processing message from server {server_id}: {str(e)}"
                )
                logger.error(traceback.format_exc())
            finally:
                # Cancel heartbeat task
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def send_heartbeat(self, server_id: str):
        """Periodically send heartbeat messages to keep connection active, currently not manually handled"""
        if server_id not in self.registered_servers:
            logger.error(f"Server {server_id} not registered")
            return

    async def send_request_to_server(
            self,
            server_id: str,
            method: str,
            params: Dict[str, Any],
            timeout: Optional[int] = None,
    ) -> Any:
        """Send request to specified server and wait for response"""
        if server_id not in self.registered_servers:
            logger.error(f"Server {server_id} not registered")
            return None

        websocket = self.registered_servers[server_id]["websocket"]
        message_queue = self.registered_servers[server_id]["message_queue"]
        request_id = self.next_request_id
        self.next_request_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Create Future to wait for response
        future = asyncio.get_running_loop().create_future()
        self.pending_requests[request_id] = future

        # Start task to receive response
        response_task = asyncio.create_task(
            self.wait_for_response(server_id, message_queue, request_id, future)
        )

        try:
            # Send request
            request_str = json.dumps(request)
            logger.debug(
                f"Sending request {request_id} to server {server_id}: {request_str}"
            )
            await websocket.send_text(request_str)

            timeout = timeout or self.settings.timeout_rpc
            # Wait for response with timeout
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Request {method} timed out")
            response_task.cancel()
            try:
                await response_task
            except asyncio.CancelledError:
                pass
            self.pending_requests.pop(request_id, None)
            return None
        except Exception as e:
            logger.error(f"Error sending request {method}: {str(e)}")
            response_task.cancel()
            try:
                await response_task
            except asyncio.CancelledError:
                pass
            self.pending_requests.pop(request_id, None)
            return None
        finally:
            # Cancel response task (if not yet completed)
            if not response_task.done():
                response_task.cancel()
                try:
                    await response_task
                except asyncio.CancelledError:
                    pass

    async def refresh_server_tools(self, server_id: str):
        """Refresh the server's tool list"""
        try:
            # Get latest tool list
            tools_result = await self.send_request_to_server(
                server_id, "tools/list", {}
            )

            if not tools_result or "tools" not in tools_result:
                logger.error(f"Failed to refresh tools list for server {server_id}")
                return

            # Get existing tool list
            existing_tools = {
                tool["name"]: tool
                for tool in self.registered_servers[server_id].get("tools", [])
            }

            # Get new tool list
            new_tools = {tool["name"]: tool for tool in tools_result["tools"]}

            # Find tools that need to be added
            for tool_name, tool in new_tools.items():
                if tool_name not in existing_tools:
                    self.register_remote_tool(server_id, tool)

            # Update server tool list
            self.registered_servers[server_id]["tools"] = tools_result["tools"]

            logger.info(
                f"Refreshed tool list for server {server_id}, total {len(tools_result['tools'])} tools"
            )

        except Exception as e:
            logger.error(f"Error refreshing tools for server {server_id}: {str(e)}")

    def register_remote_tool(
            self,
            server_id: str,
            tool_info: Dict[str, Any],
            server_name: Optional[str] = None,
    ):
        """Register remote tool to FastMCP"""
        from mcp.server.fastmcp import Context
        from mcp.server.fastmcp.server import ServerSessionT
        from mcp.server.fastmcp.utilities.func_metadata import (
            ArgModelBase,
            FuncMetadata,
        )
        from mcp.shared.context import LifespanContextT
        from pydantic import create_model

        try:
            tool_name = tool_info["name"]
            tool_description = tool_info.get(
                "description", f"Tool provided by server {server_id}"
            )
            input_schema = tool_info.get(
                "inputSchema", {"properties": {}, "required": []}
            )

            send_func = self.send_request_to_server
            timeout = self.settings.timeout_run_tool

            class WrappedTool(Tool):
                async def run(
                        self,
                        arguments: dict[str, Any],
                        context: Context[ServerSessionT, LifespanContextT] | None = None,
                ) -> Any:
                    pass_context = (
                        {self.context_kwarg: context}
                        if self.context_kwarg is not None
                        else None
                    )
                    arguments |= pass_context or {}
                    try:
                        # Call tool using established WebSocket connection
                        result = await send_func(
                            server_id,
                            "tools/call",
                            {"name": tool_name, "arguments": arguments},
                            timeout=timeout,
                        )

                        if not result:
                            raise Exception("Tool call failed")

                        # Process tool call result
                        content = result.get("content", [])

                        # Extract text content
                        text_content = []
                        for item in content:
                            if item.get("type") == "text":
                                text_content.append(item.get("text", ""))

                        # Return processed result
                        if text_content:
                            # Try to parse JSON, if fails return original text
                            try:
                                return json.loads("".join(text_content))
                            except:
                                return "".join(text_content)
                        else:
                            return result

                    except Exception as e:
                        logger.error(f"Error calling tool {tool_name}: {str(e)}")
                        raise Exception(f"Tool call failed: {str(e)}")

            # Use prefix to distinguish tools from different servers
            domain = server_name or server_id
            prefixed_name = f"{domain}_{tool_name}"
            prefixed_description = f"{tool_description}"
            empty_arg_model = create_model(
                "EmptyArguments",
                __base__=ArgModelBase,
            )

            self.gateway_mcp._tool_manager._tools[prefixed_name] = WrappedTool(
                fn=lambda x: x,
                name=prefixed_name,
                description=prefixed_description,
                parameters=input_schema,
                fn_metadata=FuncMetadata(arg_model=empty_arg_model),
                is_async=True,
            )

            logger.info(f"Tool registered: {prefixed_name}")

        except Exception as e:
            logger.error(
                f"Error registering tool {tool_info.get('name', 'unknown')}: {str(e)}"
            )

    def parse_input_schema(
            self, input_schema: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Parse tool input schema, convert to parameter information"""
        args = {}
        try:
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])

            for k, v in properties.items():
                arg = {}

                title = v.get("title")
                description = v.get("description")
                items = v.get("items")
                items_str = str(items) if items else None
                any_of = v.get("anyOf")
                any_of_str = str(any_of) if any_of else None

                default = v.get("default")
                type_info = v.get("type", "string")

                arg["type"] = type_info
                if title:
                    arg["title"] = title
                arg["description"] = description or items_str or any_of_str or str(v)
                arg["required"] = k in required
                if default is not None:
                    arg["default"] = default

                args[k] = arg

            return args
        except Exception as e:
            logger.error(f"Error parsing input schema: {str(e)}")
            return {}

    async def attach_exsit_app(self, app: FastAPI):
        """Attach Starlette application with integrated SSE and WebSocket"""
        if not self.settings:
            raise ValueError("Settings required to create Starlette application")
        # Create SSE transport
        sse = SseServerTransport(self.settings.message_path)

        # Function to handle SSE requests
        async def handle_sse(request: Request) -> None:
            # Check if the user is authenticated
            if not request.user.is_authenticated:
                # Return 401 Unauthorized
                return Response("Unauthorized", status_code=401)
            async with sse.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,  # type: ignore[reportPrivateUsage]
            ) as streams:
                await self.gateway_mcp._mcp_server.run(
                    streams[0],
                    streams[1],
                    self.gateway_mcp._mcp_server.create_initialization_options(),
                )

        # 添加中间件
        app.add_middleware(
            AuthenticationMiddleware,
            backend=BearerAuthBackend(self.auth_tokens)
        )

        # SSE路由
        @app.get(self.settings.sse_path)
        async def handle_sse_route(request: Request):
            return await handle_sse(request)

        # WebSocket路由
        @app.websocket("/mcp/register")
        async def register_websocket(websocket: WebSocket):
            logger.info("register websocet!")
            await self.handle_websocket(websocket)

        @app.post(self.settings.message_path)
        async def handle_post_message(request: Request):
            return await sse.handle_post_message(
                request.scope,
                request.receive,
                request._send,  # type: ignore[reportPrivateUsage]
            )

    def create_starlette_app(self):
        """Create Starlette application with integrated SSE and WebSocket"""
        if not self.settings:
            raise ValueError("Settings required to create Starlette application")

        # Create SSE transport
        sse = SseServerTransport(self.settings.message_path)

        # Function to handle SSE requests
        async def handle_sse(request: Request) -> None:
            # Check if the user is authenticated
            if not request.user.is_authenticated:
                # Return 401 Unauthorized
                return Response("Unauthorized", status_code=401)
            async with sse.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,  # type: ignore[reportPrivateUsage]
            ) as streams:
                await self.gateway_mcp._mcp_server.run(
                    streams[0],
                    streams[1],
                    self.gateway_mcp._mcp_server.create_initialization_options(),
                )

        # Create Starlette application with SSE and WebSocket routes
        app = Starlette(
            debug=self.settings.debug,
            routes=[
                # Original SSE route
                Route(self.settings.sse_path, endpoint=handle_sse),
                Mount(self.settings.message_path, app=sse.handle_post_message),
                # Add WebSocket route for MCP server registration
                WebSocketRoute("/register", endpoint=self.handle_websocket),
            ],
            middleware=[
                Middleware(
                    AuthenticationMiddleware,
                    backend=BearerAuthBackend(self.auth_tokens),
                )
            ],
        )

        return app

    async def run_server(self):
        """Start server with integrated SSE and WebSocket"""
        app = self.create_starlette_app()

        ssl_config = {}
        if self.settings.ssl_enabled:
            import ssl

            ssl_config = {
                "ssl_keyfile": self.settings.ssl_keyfile,
                "ssl_certfile": self.settings.ssl_certfile,
            }
            if self.settings.ssl_ca_certs:
                ssl_config["ssl_ca_certs"] = self.settings.ssl_ca_certs
                ssl_config["ssl_cert_reqs"] = ssl.CERT_REQUIRED
        config = uvicorn.Config(
            app,
            host=self.settings.host,
            port=self.settings.port,
            log_level=self.settings.log_level.lower(),
            **ssl_config,
        )
        # Add IPv6 dual-stack configuration
        if hasattr(self.settings, "ipv6") and self.settings.ipv6:
            # Enable dual-stack sockets
            socket_config = {
                "socket_kwargs": {"family": socket.AF_INET6, "dualstack_ipv6": True}
            }
            for key, value in socket_config.items():
                setattr(config, key, value)

        server = uvicorn.Server(config)
        await server.serve()


class McpserverParam(BaseModel):
    host: str = Field(default="0.0.0.0",
                      description="Host address to bind (default: '0.0.0.0'), You can set '::' for both IPv6 and IPv4", )
    port: int = Field(default=8765, description="Port to bind (default: 8765)", )
    debug: bool = Field(default=True, description="Enable debug mode (default: True", )
    log_level: str = Field(default="INFO", description="Logging level (default: INFO)", )
    ipv6: bool = Field(default=True, description="Enable dual-stack IPv6/IPv4 support (default: True)", )
    timeout_rpc: int = Field(default=10, description="Timeout for RPC calls in seconds (default: 10)", )
    timeout_run_tool: int = Field(default=300, description="Timeout for tool execution in seconds (default: 120)", )
    sse_path: str = Field(default="/mcp/sse", description="SSE endpoint path (default: /mcp/sse)", )
    message_path: str = Field(default="/mcp/messages", description="Message endpoint path (default:/mcp/messages)", )
    auth_tokens: Optional[str] = Field(default=None,
                                       description="Add authorization token (can be used multiple times)", )
    ssl_enabled: bool = Field(default=False, description="Enable SSL (default: False)", )
    ssl_keyfile: Optional[str] = Field(default=None,
                                       description="Path to SSL private key file (required if --ssl-enabled is set)", )
    ssl_certfile: Optional[str] = Field(default=None,
                                        description="Path to SSL certificate file (required if --ssl-enabled is set)", )
    ssl_ca_certs: Optional[str] = Field(default=None, description="Path to CA certificates file (optional)", )


def run_mcp_port(app: FastAPI, args: McpserverParam):
    logger.info(f"run_mcp_port:{args.host},{args.port}")
    settings = ServerSettings(
        host=args.host,
        port=args.port,
        debug=args.debug,
        log_level=args.log_level,
        sse_path=args.sse_path,
        message_path=args.message_path,
        ipv6=args.ipv6,
        timeout_rpc=args.timeout_rpc,
        timeout_run_tool=args.timeout_run_tool,
        ssl_enabled=args.ssl_enabled,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
        ssl_ca_certs=args.ssl_ca_certs,
    )

    env_tokens = os.environ.get("MCP_GATEWAY_AUTH_TOKENS", "").split(",")
    env_tokens = [token.strip() for token in env_tokens if token.strip()]
    auth_tokens = args.auth_tokens or []
    auth_tokens.extend(env_tokens)

    if not auth_tokens:
        logger.warning(
            "Warning: No authentication tokens provided. Gateway will accept any token!"
        )

    # Create the MCP gateway
    gateway = MCPGateway(
        gateway_host=settings.host,
        gateway_port=settings.port,
        settings=settings,
        auth_tokens=auth_tokens,
    )

    # Start the server (supports both SSE and WebSocket)
    asyncio.run(gateway.attach_exsit_app(app))
