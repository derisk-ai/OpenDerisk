#!/usr/bin/env python3
"""
MCP (Model Context Protocol) stdio-to-ws Gateway - Modified Version

This program creates a gateway that converts MCP services based on standard input/output to a WebSocket interface.
It starts a subprocess to handle stdio communication and multiplexes WebSocket connections with the upstream gateway for message forwarding.
Suitable for environments without public IP, achieving bidirectional communication through a single connection.

Usage example:
    python mcp_stdio_to_ws.py \
        --stdio-cmd="python my_mcp_server.py" \
        --gateway-url="ws://gateway:9000/ws" \
        --server-name="my-client"
"""

import asyncio
import json
import logging
import signal
import ssl
import sys
import threading
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from websockets.legacy.client import WebSocketClientProtocol
from werkzeug.serving import make_server

from .types import StdioToWsArgs

logger = logging.getLogger(__name__)


def on_signals(cleanup_func: Callable[[], None]) -> None:
    """Setup signal handlers"""

    def signal_handler(sig, frame):
        logger.info(f"Received signal: {sig}")
        if cleanup_func:
            cleanup_func()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


class GatewayClient:
    """Gateway client that handles communication with the upstream gateway"""

    def __init__(
        self,
        gateway_url: str,
        server_name: str,
        server_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
    ):
        self.gateway_url = gateway_url
        self.server_name = server_name
        self.server_id = server_id or str(uuid.uuid4())
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.message_handlers: Dict[
            str, Callable[[Any, Optional[str]], Awaitable[None]]
        ] = {}
        self.is_connected = False
        self.headers = headers or {}
        self.ssl_context = ssl_context

    def add_message_handler(
        self, name: str, handler: Callable[[Any, Optional[str]], Awaitable[None]]
    ):
        """Add message handler"""
        self.message_handlers[name] = handler

    async def send(self, message: Any) -> None:
        """Send message to gateway"""
        if not self.websocket or not self.is_connected:
            logger.error("Not connected to gateway, unable to send message")
            return

        message_str = json.dumps(message)
        try:
            await self.websocket.send(message_str)
            logger.debug(f"Message sent to gateway: {message_str[:100]}...")
        except Exception as e:
            logger.error(f"Failed to send message to gateway: {str(e)}")
            self.is_connected = False

    async def close(self) -> None:
        """Close connection"""
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("Closed connection to gateway")
            except Exception as e:
                logger.error(f"Error closing gateway connection: {str(e)}")
            finally:
                self.websocket = None
                self.is_connected = False

        self.message_handlers.clear()

    async def connect_and_listen(self):
        """Connect to gateway and listen for messages"""
        try:
            logger.info(f"Connecting to gateway: {self.gateway_url}")

            # Use ping_interval and ping_timeout to keep the connection active
            async with websockets.connect(
                self.gateway_url,
                ping_interval=5,
                ping_timeout=10,
                close_timeout=10,
                additional_headers=self.headers,
                ssl=self.ssl_context,
            ) as websocket:
                logger.info("Connected to gateway")
                self.websocket = websocket
                self.is_connected = True

                # Prepare registration info
                registration_info = {
                    "jsonrpc": "2.0",
                    "id": self.server_id,
                    "method": "register",
                    "params": {
                        "name": self.server_name,
                        "version": "1.0.0",
                        "capabilities": {},
                    },
                }

                # Send registration request
                registration_msg = json.dumps(registration_info)
                logger.info(f"Sending registration request: {registration_msg}")
                await self.websocket.send(registration_msg)

                # Wait for registration response
                response = await self.websocket.recv()
                logger.info(f"Received gateway message: {response}")

                if response:
                    logger.info(
                        f"Successfully registered to gateway, server ID: {self.server_id}"
                    )
                else:
                    logger.error(f"Failed to register to gateway, response: {response}")
                    return False

                # Continuously listen for messages
                try:
                    while True:
                        message = await self.websocket.recv()
                        logger.info(f"Received gateway message: {message}")

                        try:
                            msg = json.loads(message)

                            msg_id = msg.get("id") if isinstance(msg, dict) else None
                            for handler in self.message_handlers.values():
                                await handler(msg, msg_id)

                        except json.JSONDecodeError:
                            logger.error(f"Received invalid JSON message: {message}")
                        except Exception as e:
                            logger.error(f"Error processing gateway message: {str(e)}")

                except websockets.exceptions.ConnectionClosed:
                    logger.error("Gateway connection closed")
                    self.is_connected = False

                return True

        except Exception as e:
            logger.error(f"Error connecting to gateway: {str(e)}")
            import traceback

            logger.error(traceback.format_exc())
            self.websocket = None
            self.is_connected = False
            return False


async def stdio_to_ws(args: StdioToWsArgs) -> None:
    """Main function that implements stdio to WebSocket forwarding"""
    import ssl

    # Destructure arguments
    stdio_cmd = args.stdio_cmd
    port = args.port
    gateway_url = args.gateway_url
    server_name = args.server_name
    server_id = args.server_id
    auth_headers = {}
    ssl_context = None

    if not args.ssl_verify:
        # Create an SSL context that does not verify certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        logger.info("SSL certificate verification disabled")
    elif args.ssl_ca_cert:
        # Use custom CA certificate for verification
        ssl_context = ssl.create_default_context(cafile=args.ssl_ca_cert)
        logger.info(f"Using custom CA certificate: {args.ssl_ca_cert}")
    elif args.gateway_url.startswith("wss://"):
        # Use default SSL context for wss:// connections
        ssl_context = ssl.create_default_context()
        logger.info("Using default SSL context")

    if hasattr(args, "headers") and args.headers:
        for header in args.headers:
            if ":" in header:
                key, value = header.split(":", 1)
                auth_headers[key.strip()] = value.strip()
                logger.info(f"Added header: {key.strip()} = {value.strip()}")

    # Log configuration information
    logger.info("Starting MCP stdio-to-ws Gateway (Modified Version):")
    logger.info(f"  - Subprocess command: {stdio_cmd}")
    logger.info(f"  - Gateway URL: {gateway_url}")
    logger.info(f"  - Service name: {server_name}")
    logger.info(f"  - Service ID: {server_id or 'auto-generated'}")
    if auth_headers:
        logger.info(f"  - Auth headers: {', '.join(auth_headers.keys())}")

    if port > 0:
        logger.info(f"  - Local port: {port}")
        logger.info(f"  - CORS enabled: {args.enable_cors}")
        logger.info(
            f"  - Health check endpoints: {', '.join(args.health_endpoints) if args.health_endpoints else '(none)'}"
        )

    gateway_client = GatewayClient(
        gateway_url=gateway_url,
        server_name=server_name,
        server_id=server_id,
        headers=auth_headers,
        ssl_context=ssl_context,
    )

    # Create async subprocess
    proc = None
    is_ready = False
    child_queue = asyncio.Queue()  # For storing output read from subprocess

    async def cleanup():
        """Function to clean up resources"""
        if proc:
            try:
                proc.terminate()
                await proc.wait()
                logger.info("Subprocess terminated")
            except Exception as err:
                logger.error(f"Error terminating subprocess: {str(err)}")

        await gateway_client.close()

    # Set up signal handling
    on_signals(lambda: asyncio.run(cleanup()))

    try:
        # 1. Start subprocess using asyncio
        logger.info(f"Starting subprocess: {stdio_cmd}")

        # Use async subprocess
        proc = await asyncio.create_subprocess_shell(
            stdio_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
        )

        logger.info(f"Subprocess started, PID: {proc.pid}")

        # 2. Define subprocess to gateway forwarding function
        async def read_stdout():
            """Read from subprocess stdout and parse JSON messages"""
            logger.info("Starting to read from subprocess stdout...")

            buffer = b""  # Use bytes buffer instead of string
            while True:
                try:
                    # Non-blocking read from subprocess output
                    chunk = await proc.stdout.read(1024)
                    if not chunk:  # EOF
                        if proc.returncode is not None:
                            logger.info(
                                f"Subprocess terminated, return code: {proc.returncode}"
                            )
                        else:
                            logger.info(
                                "Subprocess stdout closed but process still running"
                            )
                        break

                    buffer += chunk

                    # Process complete lines
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line:
                            continue

                        # Try to decode with error handling
                        try:
                            line_str = line.decode("utf-8", errors="replace")
                            line_str = line_str.strip()

                            logger.debug(f"Subprocess raw output: {line_str}")

                            if line_str:
                                try:
                                    json_msg = json.loads(line_str)
                                    logger.info(
                                        f"Subprocess → Gateway: {json.dumps(json_msg)[:100]}..."
                                    )
                                    await child_queue.put(json_msg)
                                except json.JSONDecodeError:
                                    logger.error(
                                        f"Subprocess non-JSON output: {line_str}"
                                    )
                        except UnicodeDecodeError as ude:
                            logger.warning(
                                f"Cannot decode as UTF-8: {str(ude)}. Skipping binary data."
                            )

                except Exception as e:
                    logger.error(f"Error reading subprocess output: {str(e)}")
                    await asyncio.sleep(0.1)

            logger.info("Subprocess stdout reading task ended")

        # 3. Monitor subprocess error output
        async def read_stderr():
            """Read content from subprocess stderr"""
            logger.info("Starting to monitor subprocess error output...")

            while True:
                try:
                    chunk = await proc.stderr.read(1024)
                    if not chunk:  # EOF
                        if proc.returncode is not None:
                            logger.info(
                                f"Subprocess terminated, return code: {proc.returncode}"
                            )
                        else:
                            logger.info(
                                "Subprocess stderr closed but process still running"
                            )
                        break

                    # Use error handling when decoding
                    text = chunk.decode("utf-8", errors="replace").strip()
                    if text:
                        for line in text.split("\n"):
                            if line.strip():
                                logger.info(f"Subprocess stderr: {line.strip()}")

                except Exception as e:
                    logger.error(f"Error reading subprocess error output: {str(e)}")
                    await asyncio.sleep(0.1)

            logger.info("Subprocess error output monitoring task ended")

        # 4. Process subprocess output in queue and forward to gateway
        async def process_child_output():
            """Process subprocess output in queue and forward to gateway"""
            logger.info("Starting to process subprocess output queue...")

            while True:
                try:
                    json_msg = await child_queue.get()
                    logger.info(
                        f"Processing subprocess queue message: {json.dumps(json_msg)}..."
                    )

                    await gateway_client.send(json_msg)
                    child_queue.task_done()
                except Exception as e:
                    logger.error(f"Error processing subprocess output queue: {str(e)}")
                    await asyncio.sleep(0.1)

        # 5. Define gateway to subprocess message handling
        async def forward_gateway_to_child(message: Any, _: Optional[str]):
            """Forward gateway messages to subprocess"""
            if proc and proc.stdin:
                message_str = json.dumps(message)
                logger.info(f"Gateway → Subprocess: {message_str}...")
                try:
                    # Ensure message ends with newline
                    if not message_str.endswith("\n"):
                        message_str += "\n"

                    proc.stdin.write(message_str.encode("utf-8"))
                    await proc.stdin.drain()
                    logger.debug("Message successfully written to subprocess stdin")
                except Exception as e:
                    logger.error(f"Error writing message to subprocess: {str(e)}")

        # 6. Register message handler
        gateway_client.add_message_handler("forward_to_child", forward_gateway_to_child)

        # 7. Start subprocess I/O handling tasks
        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())
        queue_task = asyncio.create_task(process_child_output())

        # 8. If local WebSocket server needs to be started
        if port > 0:
            from flask import Flask, Response
            from flask_cors import CORS

            # Create HTTP server and health check endpoints
            app = Flask(__name__)

            if args.enable_cors:
                CORS(app)

            # Add health check endpoints
            @app.route("/health")
            def default_health_check():
                if proc and proc.returncode is not None:
                    return Response("Subprocess terminated", status=500)

                if not is_ready:
                    return Response("Server not ready", status=500)

                if not gateway_client.is_connected and args.require_gateway:
                    return Response("Not connected to gateway", status=500)

                return "ok"

            for ep in args.health_endpoints:
                app.route(ep)(default_health_check)

            # Start HTTP server
            server = make_server("0.0.0.0", port, app, threaded=True)
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            logger.info(f"HTTP service started: http://localhost:{port}")

        # 9. Set server state to ready
        is_ready = True

        # 10. Connect and listen to gateway - this method will block until connection is closed
        gateway_connected = await gateway_client.connect_and_listen()

        if not gateway_connected and args.require_gateway:
            logger.error("Gateway connection failed or closed, program will exit")

        # 11. After gateway connection ends, cancel all subtasks
        for task in [stdout_task, stderr_task, queue_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info(f"Task cancelled: {task.get_name()}")

        # 12. Clean up resources
        await cleanup()

    except Exception as err:
        logger.error(f"Startup failed: {str(err)}")
        import traceback

        logger.error(traceback.format_exc())
        await cleanup()
        sys.exit(1)


def main(args: StdioToWsArgs) -> None:
    # Run main function
    asyncio.run(stdio_to_ws(args))
