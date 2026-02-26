import dataclasses
import json
import logging
import ssl
import uuid
from functools import partial
from typing import Any, List, Optional, Type, Union, cast, Dict
from derisk._private.config import Config
from derisk.agent.resource.tool.pack import json_parse_execute_args_func
from derisk_app.config import ApplicationConfig
from derisk_serve.agent.resource.tool.mcp_utils import (
    get_mcp_tool_list,
    switch_mcp_input_schema,
    call_mcp_tool,
)

from tenacity import retry, stop_after_attempt, wait_fixed, after_log, before_sleep_log
from mcp.types import Tool
from derisk.util.global_helper import truncate_text
from derisk.agent.resource import PackResourceParameters, ToolPack, BaseTool
from derisk.util import ParameterDescription
from derisk.util.i18n_utils import _

from derisk_serve.agent.db.gpts_tool import GptsToolDao
from derisk_serve.agent.db.gpts_tool_messages import (
    GptsToolMessagesDao,
    GptsToolMessages,
)

logger = logging.getLogger(__name__)
CFG = Config()
gpts_tool_messages_dao = GptsToolMessagesDao()
gpts_tool_dao = GptsToolDao()


@dataclasses.dataclass
class MCPPackResourceParameters(PackResourceParameters):
    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
        cls,
        parameters: Type["MCPPackResourceParameters"],
        version: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Convert the parameters to configurations."""
        conf: List[ParameterDescription] = cast(
            List[ParameterDescription], super().to_configurations(parameters)
        )
        version = version or cls._resource_version()
        if version != "v1":
            return conf
        # Compatible with old version
        for param in conf:
            if param.param_name == "tool_name":
                return param.valid_values or []
        return []

    @classmethod
    def from_dict(
        cls, data: dict, ignore_extra_fields: bool = True
    ) -> "MCPPackResourceParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()
        if "mcp_server" not in copied_data and "value" in copied_data:
            copied_data["mcp_server"] = copied_data.pop("value")
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


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
        from derisk.util.log_util import MCP_LOGGER as LOGGER

        super().__init__([], **kwargs)
        self._mcp_servers = mcp_servers
        self._loaded = False
        self.tool_server_map = {}
        self._headers = {}
        if isinstance(headers, str) and headers:
            try:
                self._headers = json.loads(headers)
            except Exception as e:
                raise ValueError("Unable to parse MCP service header parameters！")
        else:
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
        self._allow_tools = kwargs["allow_tools"] if "allow_tools" in kwargs else None
        self._requires_approval_tools = (
            kwargs["requires_approval_tools"]
            if "requires_approval_tools" in kwargs
            else None
        )
        self._source = (
            kwargs["source"] if "source" in kwargs and kwargs["source"] else "faas"
        )
        self._timeout = (
            kwargs["timeout"] if "timeout" in kwargs and kwargs["timeout"] else 60
        )
        self._tool_id = (
            kwargs["tool_id"] if "tool_id" in kwargs and kwargs["tool_id"] else None
        )
        self._mcp_name = self.name

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

    def _prepare_server_config(self, server: str, trace_id: str):
        """Prepare server configuration including headers and SSL verification"""
        server_headers = self._headers_map.get(server, self._default_headers).copy()
        server_headers.update(
            {
                "SOFA-TraceId": trace_id,
                "SOFA-RpcId": "0.1",
                "x-mcp-hash-key": str(uuid.uuid4()),
            }
        )
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
        agent_id = root_tracer.get_context_agent_id()
        user_id = root_tracer.get_context_user_id()
        server_list = (
            self._mcp_servers.copy()
            if isinstance(self._mcp_servers, List)
            else self._mcp_servers.split(";")
        )
        system_app = CFG.SYSTEM_APP
        app_config = system_app.config.configs.get("app_config")
        mode = "origin"
        if isinstance(app_config, ApplicationConfig):
            mode = app_config.mcp.mode
        is_special_code = root_tracer.get_context_entrance() == "async" and (
            self._mcp_name == "mcp-code" or self._mcp_name == "mcp-code-full"
        )

        if self._tool_id:
            gpts_tool = gpts_tool_dao.get_tool_by_tool_id(self._tool_id)
        else:
            gpts_tool = gpts_tool_dao.get_tool_by_name(self._mcp_name)

        if gpts_tool and gpts_tool.type == "MCP":
            # Set default tool_id
            if not gpts_tool.tool_id:
                gpts_tool.tool_id = str(uuid.uuid4())

            self._tool_id = gpts_tool.tool_id
            self._mcp_name = gpts_tool.tool_name
            config = json.loads(gpts_tool.config)
            self._source = config.get("source", self._source)
            self._timeout = config.get("timeout", self._timeout)
            if config.get("headers", None):
                if isinstance(config.get("headers"), str):
                    self._headers = json.loads(config.get("headers"))
                else:
                    self._headers = config.get("headers")
            server_list = [config.get("url", None)]

        else:
            self._tool_id = str(uuid.uuid4())
            # TODO Get MCP Tool name, Temp solve
            self._mcp_name = str(uuid.uuid4())

        for server in server_list:
            try:

                def log_final_retry(retry_state):
                    raise Exception(
                        f"{self._mcp_name} tool/list final retry failed: {retry_state.outcome.exception()}"
                    )

                @retry(
                    stop=stop_after_attempt(3),
                    wait=wait_fixed(1),
                    reraise=True,
                    after=after_log(LOGGER, logging.WARN),
                    retry_error_callback=log_final_retry,
                )
                async def _get_tool_list():
                    return await get_mcp_tool_list(
                        self._mcp_name,
                        server,
                        headers=self._headers,
                        allow_tools=self._allow_tools,
                        tool_id=self._tool_id,
                    )

                gpts_tool_messages = GptsToolMessages(
                    tool_id=self._tool_id,
                    name=self._mcp_name,
                    type="MCP",
                    input="tool/list",
                    trace_id=trace_id,
                    success=1,
                )
                try:
                    result = await _get_tool_list()
                    gpts_tool_messages.output = truncate_text(
                        json.dumps(result.model_dump(), ensure_ascii=False), 65535
                    )
                except Exception as e:
                    gpts_tool_messages.success = 0
                    gpts_tool_messages.error = str(e)
                    raise e
                finally:
                    gpts_tool_messages_dao.create(gpts_tool_messages)
                for tool in result.tools:
                    tool_name = tool.name
                    self.tool_server_map[tool_name] = server
                    args = switch_mcp_input_schema(tool.inputSchema)

                    # 使用偏函数绑定固定参数
                    bound_call = partial(
                        call_mcp_tool,
                        mcp_name=self._mcp_name,
                        tool_name=tool_name,
                        server=server,
                        trace_id=trace_id,
                        headers=self._headers,
                        timeout=self._timeout,
                        tool_id=self._tool_id,
                    )
                    self.add_command(
                        tool.description,
                        tool_name,
                        args,
                        bound_call,
                        parse_execute_args_func=json_parse_execute_args_func,
                        overwrite=self._overwrite_same_tool,
                        ask_user=is_tool_ask_user(tool, self),
                    )

            except Exception as e:
                LOGGER.exception(f"Failed to load tools from {server}: {e}")
                raise e

        self._loaded = True

    @property
    def requires_approval_tools(self):
        return self._requires_approval_tools


def is_tool_ask_user(tool: Tool, tool_pack: MCPToolPack) -> bool:
    return (
        tool.annotations
        and tool.annotations.model_config
        and tool.annotations.model_config.get("requires_approval", False)
    ) or (
        tool_pack
        and tool_pack.requires_approval_tools
        and tool.name in tool_pack.requires_approval_tools
    )


class MCPSSEToolPack(MCPToolPack):
    def __init__(self, mcp_servers: Union[str, List[str]], **kwargs):
        super().__init__(mcp_servers=mcp_servers, **kwargs)

    @classmethod
    def type_alias(cls) -> str:
        return "tool(mcp)"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[MCPPackResourceParameters]:
        logger.info(f"resource_parameters_class:{kwargs}")

        @dataclasses.dataclass
        class _DynMCPSSEPackResourceParameters(MCPPackResourceParameters):
            mcp_servers: str = dataclasses.field(
                default="http://127.0.0.1:8000/sse",
                metadata={
                    "help": _("MCP SSE Server URL, split by ':'"),
                },
            )
            headers: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _(
                        'MCP SSE Server Headers, use josn like \'{"token":"T123","Cookie":"xxx"}\''
                    ),
                },
            )
            allow_tools: Optional[List[str]] = dataclasses.field(
                default=None,
                metadata={
                    "help": _(
                        "Allow tools, use ':' to split multiple tools, default is all"
                    ),
                },
            )
            source: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _(
                        "Source of the tool, use ':' to split multiple sources, default is all"
                    ),
                },
            )
            timeout: Optional[int] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Timeout of the mcp"),
                },
            )
            tool_id: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("Tool ID of the mcp"),
                },
            )
            name: Optional[str] = dataclasses.field(
                default=None,
                metadata={
                    "help": _("MCP Tool Name"),
                },
            )

        return _DynMCPSSEPackResourceParameters
