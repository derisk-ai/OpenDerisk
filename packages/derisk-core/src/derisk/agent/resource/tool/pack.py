"""Tool resource pack module."""

import asyncio
import json
import logging
import os
import uuid
import ssl
from datetime import datetime
from functools import partial

from cachetools import TTLCache
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union, cast

from mcp import ClientSession

from derisk import SystemApp
from derisk.util.json_utils import parse_or_raise_error
from .mcp.mcp_utils import get_mcp_tool_list, call_mcp_tool, switch_mcp_input_schema

from ...util.mcp_utils import sse_client
from ..base import EXECUTE_ARGS_TYPE, PARSE_EXECUTE_ARGS_FUNCTION, ResourceType, T
from ..pack import Resource, ResourcePack
from .base import DERISK_TOOL_IDENTIFIER, BaseTool, FunctionTool, ToolFunc
from .exceptions import ToolExecutionException, ToolNotFoundException

ToolResourceType = Union[Resource, BaseTool, List[BaseTool], ToolFunc, List[ToolFunc]]

logger = logging.getLogger(__name__)
tool_cache = TTLCache(maxsize=200, ttl=300)


def _is_function_tool(resources: Any) -> bool:
    return (
            callable(resources)
            and hasattr(resources, DERISK_TOOL_IDENTIFIER)
            and getattr(resources, DERISK_TOOL_IDENTIFIER)
            and hasattr(resources, "_tool")
            and isinstance(getattr(resources, "_tool"), BaseTool)
    )


def _is_tool(resources: Any) -> bool:
    return isinstance(resources, BaseTool) or _is_function_tool(resources)


def _to_tool_list(
        resources: ToolResourceType, unpack: bool = False, ignore_error: bool = False
) -> List[Resource]:
    def parse_tool(r):
        if isinstance(r, BaseTool):
            return [r]
        elif _is_function_tool(r):
            return [cast(FunctionTool, getattr(r, "_tool"))]
        elif isinstance(r, ResourcePack):
            if not unpack:
                return [r]
            new_list = []
            for p in r.sub_resources:
                new_list.extend(parse_tool(p))
            return new_list
        elif isinstance(r, Sequence):
            new_list = []
            for t in r:
                new_list.extend(parse_tool(t))
            return new_list
        elif ignore_error:
            return []
        else:
            raise ValueError("Invalid tool resource type")

    return parse_tool(resources)


def json_parse_execute_args_func(input_str: str) -> Optional[EXECUTE_ARGS_TYPE]:
    """Parse the execute arguments."""
    # The position arguments is empty
    args = ()
    kwargs = parse_or_raise_error(input_str)
    if kwargs is not None and isinstance(kwargs, list) and len(kwargs) == 0:
        kwargs = {}
    return args, kwargs


class ToolPack(ResourcePack):
    """Tool resource pack class."""

    def __init__(
            self, resources: ToolResourceType, name: str = "Tool Resource Pack", **kwargs
    ):
        """Initialize the tool resource pack."""
        tools = cast(List[Resource], _to_tool_list(resources))
        super().__init__(resources=tools, name=name, **kwargs)

    @classmethod
    def from_resource(
            cls: Type[T],
            resource: Optional[Resource],
            expected_type: Optional[ResourceType] = None,
    ) -> List[T]:
        """Create a resource from another resource."""
        if not resource:
            return []
        tools = _to_tool_list(resource, unpack=True, ignore_error=True)
        typed_tools = [cast(BaseTool, t) for t in tools]
        return [ToolPack(typed_tools)]  # type: ignore

    def add_command(
            self,
            command_label: str,
            command_name: str,
            args: Optional[Dict[str, Any]] = None,
            function: Optional[Callable] = None,
            parse_execute_args_func: Optional[PARSE_EXECUTE_ARGS_FUNCTION] = None,
            overwrite: bool = False,
    ) -> None:
        """Add a command to the commands.

        Compatible with the Auto-GPT old plugin system.

        Add a command to the commands list with a label, name, and optional arguments.

        Args:
            command_label (str): The label of the command.
            command_name (str): The name of the command.
            args (dict, optional): A dictionary containing argument names and their
              values. Defaults to None.
            function (callable, optional): A callable function to be called when
                the command is executed. Defaults to None.
            parse_execute_args (callable, optional): A callable function to parse the
                execute arguments. Defaults to None.
            overwrite (bool, optional): Whether to overwrite the command if it already
                exists. Defaults to False.
        """
        if args is not None:
            tool_args = {}
            for name, value in args.items():
                if isinstance(value, dict):
                    tool_args[name] = {
                        "name": name,
                        "type": value.get("type", "str"),
                        "description": value.get("description", str(value)),
                        "required": value.get("required", False),
                    }
                    if "title" in value:
                        tool_args[name]["title"] = value["title"]
                    if "default" in value:
                        tool_args[name]["default"] = value["default"]
                else:
                    tool_args[name] = {
                        "name": name,
                        "type": "str",
                        "description": value,
                    }
        else:
            tool_args = {}
        if not function:
            raise ValueError("Function must be provided")

        ft = FunctionTool(
            name=command_name,
            func=function,
            args=tool_args,
            description=command_label,
            parse_execute_args_func=parse_execute_args_func,
        )
        self.append(ft, overwrite=overwrite)

    def _get_execution_tool(
            self,
            name: Optional[str] = None,
    ) -> BaseTool:
        if not name and name not in self._resources:
            raise ToolNotFoundException("No tool found for execution")
        return cast(BaseTool, self._resources[name])

    def _get_call_args(self, arguments: Dict[str, Any], tl: BaseTool) -> Dict[str, Any]:
        """Get the call arguments."""
        # Delete non-defined parameters
        diff_args = list(set(arguments.keys()).difference(set(tl.args.keys())))
        for arg_name in diff_args:
            del arguments[arg_name]
        return arguments

    def parse_execute_args(
            self, resource_name: Optional[str] = None, input_str: Optional[str] = None
    ) -> Optional[EXECUTE_ARGS_TYPE]:
        """Parse the execute arguments."""
        try:
            tl = self._get_execution_tool(resource_name)
            return tl.parse_execute_args(input_str=input_str)
        except ToolNotFoundException:
            return None

    def execute(
            self,
            *args,
            resource_name: Optional[str] = None,
            **kwargs,
    ) -> Any:
        """Execute the tool.

        Args:
            *args: The positional arguments.
            resource_name (str, optional): The tool name to be executed.
            **kwargs: The keyword arguments.

        Returns:
            Any: The result of the tool execution.
        """
        tl = self._get_execution_tool(resource_name)
        try:
            arguments = {k: v for k, v in kwargs.items()}
            arguments = self._get_call_args(arguments, tl)
            if tl.is_async:
                raise ToolExecutionException("Async execution is not supported")
            else:
                return tl.execute(**arguments)
        except Exception as e:
            raise ToolExecutionException(f"Execution error: {str(e)}")

    async def get_resources_info(
            self,
            resource_name: Optional[str] = None,
            **kwargs,
    ):
        return self._get_execution_tool(resource_name)

    async def async_execute(
            self,
            *args,
            resource_name: Optional[str] = None,
            **kwargs,
    ) -> Any:
        """Execute the tool asynchronously.

        Args:
            *args: The positional arguments.
            resource_name (str, optional): The tool name to be executed.
            **kwargs: The keyword arguments.

        Returns:
            Any: The result of the tool execution.
        """
        tl = self._get_execution_tool(resource_name)
        try:
            arguments = {k: v for k, v in kwargs.items()}
            arguments = self._get_call_args(arguments, tl)
            if tl.is_async:
                return await tl.async_execute(**arguments)
            else:
                # TODO: Execute in a separate executor
                return tl.execute(**arguments)
        except Exception as e:
            raise ToolExecutionException(f"Execution error: {str(e)}")

    def is_terminal(self, resource_name: Optional[str] = None) -> bool:
        """Check if the tool is terminal."""
        from ...expand.actions.react_action import Terminate

        if not resource_name:
            return False
        tl = self._get_execution_tool(resource_name)
        return isinstance(tl, Terminate)


class AutoGPTPluginToolPack(ToolPack):
    """Auto-GPT plugin tool pack class."""

    def __init__(self, plugin_path: Union[str, List[str]], **kwargs):
        """Create an Auto-GPT plugin tool pack."""
        super().__init__([], **kwargs)
        self._plugin_path = plugin_path
        self._loaded = False

    async def preload_resource(self):
        """Preload the resource."""
        from .autogpt.plugins_util import scan_plugin_file, scan_plugins

        if self._loaded:
            return
        paths = (
            [self._plugin_path]
            if isinstance(self._plugin_path, str)
            else self._plugin_path
        )
        plugins = []
        for path in paths:
            if os.path.isabs(path):
                if not os.path.exists(path):
                    raise ValueError(f"Wrong plugin path configured {path}!")
                if os.path.isfile(path):
                    plugins.extend(scan_plugin_file(path))
                else:
                    plugins.extend(scan_plugins(path))
        for plugin in plugins:
            if not plugin.can_handle_post_prompt():
                continue
            plugin.post_prompt(self)
        self._loaded = True


class MCPToolPack(ToolPack):
    """MCP tool pack class.

    Wrap the MCP SSE server as a tool pack.

    Example:
        .. code-block:: python

            tools = MCPToolPack("http://127.0.0.1:8000/sse")

        If you want to pass the token to the server, you can use the headers parameter:
        .. code-block:: python

            tools = MCPToolPack(
                "http://127.0.0.1:8000/sse"
                default_headers={"Authorization": "Bearer your_token"}
            )
            # Set the default headers for ech server
            tools2 = MCPToolPack(
                "http://127.0.0.1:8000/sse"
                headers = {
                    "http://127.0.0.1:8000/sse": {
                        "Authorization": "Bearer your_token"
                    }
                }
            )

        If you want to set the ssl verify, you can use the ssl_verify parameter:
        .. code-block:: python

            # Default ssl_verify is True
            tools = MCPToolPack(
                "https://your_ssl_domain/sse",
            )

            # Set the default ssl_verify to False to disable ssl verify
            tools2 = MCPToolPack(
                "https://your_ssl_domain/sse", default_ssl_verify=False
            )

            # With Custom CA file
            tools3 = MCPToolPack(
                "https://your_ssl_domain/sse", default_ssl_cafile="/path/to/your/ca.crt"
            )

            # Set the ssl_verify for each server
            import ssl

            tools4 = MCPToolPack(
                "https://your_ssl_domain/sse",
                ssl_verify={
                    "https://your_ssl_domain/sse": ssl.create_default_context(
                        cafile="/path/to/your/ca.crt"
                    ),
                },
            )

    """

    def __init__(
            self,
            mcp_servers: Union[str, List[str]],
            headers: Optional[Dict[str, Dict[str, Any]]] = None,
            default_headers: Optional[Dict[str, Any]] = None,
            ssl_verify: Optional[Dict[str, Union[ssl.SSLContext, str, bool]]] = None,
            default_ssl_verify: Union[ssl.SSLContext, str, bool] = True,
            default_ssl_cafile: Optional[str] = None,
            overwrite_same_tool: bool = True,
            **kwargs,
    ):
        """Create an Auto-GPT plugin tool pack."""
        super().__init__([], **kwargs)
        self._mcp_servers = mcp_servers
        self._loaded = False
        self.tool_server_map = {}
        headers = {}
        if "headers" in kwargs:
            headers = kwargs["headers"]
            if isinstance(headers, str) and headers:
                try:
                    headers = json.loads(headers)
                except Exception as e:
                    raise ValueError("Unable to parse MCP service header parameters！")
        self._headers = headers if headers is not None else {}
        self._default_headers = default_headers or {}
        self._headers_map = headers or {}
        self.server_headers_map = {}
        if default_ssl_cafile and not ssl_verify and default_ssl_verify:
            default_ssl_verify = ssl.create_default_context(cafile=default_ssl_cafile)

        self._default_ssl_verify = default_ssl_verify
        self._ssl_verify_map = ssl_verify or {}
        self.server_ssl_verify_map = {}
        self._overwrite_same_tool = overwrite_same_tool

        self._allow_tools = None
        if "allow_tools" in kwargs:
            self._allow_tools = kwargs["allow_tools"]

    def _get_call_args(self, arguments: Dict[str, Any], tl: BaseTool) -> Dict[str, Any]:
        """Get the call arguments."""
        # Delete non-defined parameters
        diff_args = list(set(arguments.keys()).difference(set(tl.args.keys())))
        for arg_name in diff_args:
            del arguments[arg_name]

        # Rebuild derisk mcp call param
        return {
            "mcp_name": self.name,
            "server": self.tool_server_map[tl.name],
            "args": arguments,
            "tool_name": tl.name,
            "headers": self._headers,
        }

    # async def get_mcp_tool_list(self, server: str, headers: Optional[dict] = None, server_ssl_verify: Optional[Any] = None):
    #     from derisk.util.log_util import MCP_LOGGER as LOGGER
    #     from derisk.util.tracer import root_tracer
    #
    #     trace_id = root_tracer.get_current_span().trace_id
    #
    #     async def mcp_tool_list(server: str):
    #         if tool_cache.get(self.name):
    #             LOGGER.info(f"[{trace_id}]mcp_server:{self.name}, hit tool list cache:{tool_cache.get(self.name)}")
    #             return tool_cache.get(self.name)
    #         start_time = int(datetime.now().timestamp() * 1000)
    #         async with sse_client(url=server, headers=self._headers) as (read, write):
    #             async with ClientSession(read, write) as session:
    #                 # Initialize the connection
    #                 await session.initialize()
    #                 result = await session.list_tools()
    #                 if self._allow_tools and len(self._allow_tools) > 0:
    #                     tools = [tool for tool in result.tools if tool.name in self._allow_tools]
    #                     result.tools = tools
    #                 end_time = int(datetime.now().timestamp() * 1000)
    #                 LOGGER.info(
    #                     f"[{trace_id}]mcp_server:{self.name},sse:{server},header:{self._headers},list_tools:[{result}],costMs:[{end_time - start_time}]"
    #                 )
    #                 tool_cache[self.name] = result
    #                 return result
    #
    #     from derisk.util.async_executor_utils import ServiceUnavailableError
    #
    #     try:
    #         from derisk.util.async_executor_utils import safe_call_tool
    #
    #         return await safe_call_tool(
    #             mcp_tool_list,  # 可能是阻塞的函数
    #             server,
    #             time_out=30,
    #         )
    #     except ServiceUnavailableError as e:
    #         LOGGER.exception(
    #             f"[{trace_id}][DIGEST][tools/list]mcp_server=[{self.name}],sse=[{server}],success=[N],err_msg=[{str(e)}]"
    #         )
    #         raise ValueError(f"MCP服务{server}工具列表调用异常!", e)
    #     except asyncio.TimeoutError as e:
    #         LOGGER.exception(
    #             f"[{trace_id}][DIGEST][tools/list]mcp_server=[{self.name}],sse=[{server}],success=[N],err_msg=[{str(e)}]"
    #         )
    #         raise ValueError(f"MCP服务{server}工具列表调用超时!")

    def _prepare_server_config(self, server: str, trace_id: str):
        """Prepare server configuration including headers and SSL verification"""
        server_headers = self._headers_map.get(server, self._default_headers).copy()
        server_headers.update({
            "SOFA-TraceId": trace_id,
            "SOFA-RpcId": "0.1",
            "x-mcp-hash-key": str(uuid.uuid4())
        })
        server_headers.update(self._headers)

        self.server_headers_map[server] = server_headers
        self.server_ssl_verify_map[server] = self._ssl_verify_map.get(
            server, self._default_ssl_verify
        )

    async def preload_resource(self):
        """Preload the resource."""
        from derisk.util.log_util import MCP_LOGGER as LOGGER
        from derisk.util.tracer import root_tracer

        trace_id = root_tracer.get_current_span().trace_id
        server_list = self._mcp_servers.copy() if isinstance(self._mcp_servers, List) else self._mcp_servers.split(";")

        for server in server_list:
            self._prepare_server_config(server, trace_id)
            try:
                self._headers["x-mcp-hash-key"] = str(uuid.uuid4())
                result = await get_mcp_tool_list(
                    self.name, server,
                    headers=self._headers,
                    allow_tools=self._allow_tools
                )
                for tool in result.tools:
                    tool_name = tool.name
                    self.tool_server_map[tool_name] = server
                    args = switch_mcp_input_schema(tool.inputSchema)

                    # 使用偏函数绑定固定参数
                    bound_call = partial(
                        call_mcp_tool,
                        mcp_name=self.name,
                        tool_name=tool_name,
                        server=server,
                        trace_id=trace_id,
                        headers=self._headers,
                    )

                    self.add_command(
                        tool.description,
                        tool_name,
                        args,
                        bound_call,
                        parse_execute_args_func=json_parse_execute_args_func,
                        overwrite=self._overwrite_same_tool,
                    )

            except Exception as e:
                LOGGER.exception(
                    f"[{trace_id}][DIGEST][tools/list]mcp_server=[{self.name}],sse=[{server}],success=[N],err_msg=[{str(e)}]"
                )
        self._loaded = True

    #
    # async def preload_resource(self):
    #     """Preload the resource."""
    #     from derisk.util.log_util import MCP_LOGGER as LOGGER
    #     from derisk.util.tracer import root_tracer
    #
    #     trace_id = root_tracer.get_current_span().trace_id
    #     if isinstance(self._mcp_servers, List):
    #         server_list = self._mcp_servers.copy()
    #     else:
    #         server_list = self._mcp_servers.split(";")
    #
    #     for server in server_list:
    #         server_headers = self._headers_map.get(server, self._default_headers)
    #         server_headers["SOFA-TraceId"] = trace_id
    #         server_headers["SOFA-RpcId"] = "0.1"
    #         server_headers["x-mcp-hash-key"] = str(uuid.uuid4())
    #         server_headers.update(self._headers)
    #         self.server_headers_map[server] = server_headers
    #         server_ssl_verify = self._ssl_verify_map.get(
    #             server, self._default_ssl_verify
    #         )
    #         self.server_ssl_verify_map[server] = server_ssl_verify
    #
    #         try:
    #             self._headers["x-mcp-hash-key"] = str(uuid.uuid4())
    #             result = await get_mcp_tool_list(self.name, server, headers=self._headers, allow_tools=self._allow_tools)
    #             for tool in result.tools:
    #                 tool_name = tool.name
    #                 self.tool_server_map[tool_name] = server
    #                 args = self.switch_mcp_input_schema(tool.inputSchema)
    #
    #                 async def call_mcp_tool(
    #                     tool_name=tool_name, server=server, **kwargs
    #                 ):
    #                     async def call_tool(**kwargs):
    #                         start_time = int(datetime.now().timestamp() * 1000)
    #                         try:
    #                             headers_to_use = self.server_headers_map.get(server, {})
    #                             ssl_verify_to_use = self.server_ssl_verify_map.get(
    #                                 server, True
    #                             )
    #                             async with sse_client(
    #                                 url=server, headers=self._headers
    #                             ) as (read, write):
    #                                 async with ClientSession(read, write) as session:
    #                                     # Initialize the connection
    #                                     await session.initialize()
    #                                     result = await session.call_tool(
    #                                         tool_name, arguments=kwargs
    #                                     )
    #                                     end_time = int(
    #                                         datetime.now().timestamp() * 1000
    #                                     )
    #                                     LOGGER.info(
    #                                         f"[{trace_id}][DIGEST][tools/call]mcp_server=[{self.name}],sse=[{server}],tool=[{tool_name}],success=[Y],err_msg=[None],costMs=[{end_time - start_time}],result_length=[{len(str(result.json()))}],headers=[{self._headers}]"
    #                                     )
    #                                     LOGGER.info(
    #                                         f"[{trace_id}]mcp_server:{self.name},sse:[{server}],header:{self._headers},tool:{tool_name},result:[{result.json()}]"
    #                                     )
    #                                     return result.json()
    #                         except Exception as e:
    #                             LOGGER.exception(
    #                                 f"[{trace_id}][DIGEST][tools/call]mcp_server=[{self.name}],sse=[{server}],tool=[{tool_name}],success=[N],err_msg=[{str(e)}],costMs=[None],result_length=[None],headers=[{self._headers}]"
    #                             )
    #                             raise ValueError(f"MCP Call Exception! {str(e)}")
    #
    #                     from derisk.util.async_executor_utils import (
    #                         ServiceUnavailableError,
    #                     )
    #
    #                     try:
    #                         from derisk.util.async_executor_utils import safe_call_tool
    #
    #                         return await safe_call_tool(
    #                             call_tool,
    #                             **kwargs,
    #                             time_out=600,
    #                         )
    #                     except ServiceUnavailableError as e:
    #                         raise ValueError(f"MCP服务{self.name}工具调用异常!", e)
    #                     except asyncio.TimeoutError as e:
    #                         raise ValueError(f"MCP服务{self.name}工具调用超时!")
    #
    #                 self.add_command(
    #                     tool.description,
    #                     tool_name,
    #                     args,
    #                     call_mcp_tool,
    #                     parse_execute_args_func=json_parse_execute_args_func,
    #                     overwrite=self._overwrite_same_tool,
    #                 )
    #         except Exception as e:
    #             LOGGER.exception(
    #                 f"[{trace_id}][DIGEST][tools/list]mcp_server=[{self.name}],sse=[{server}],success=[N],err_msg=[{str(e)}]"
    #             )
    #     self._loaded = True
