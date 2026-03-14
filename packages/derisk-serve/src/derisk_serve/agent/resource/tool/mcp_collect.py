import dataclasses
import json
import logging
import ssl
import uuid
from functools import partial
from typing import Any, List, Optional, Type, Union, cast, Dict
from derisk._private.config import Config
from derisk.agent import ResourceType
from derisk.agent.resource.tool.pack import json_parse_execute_args_func
from derisk_app.config import ApplicationConfig
from derisk_serve.agent.resource.tool.mcp import MCPToolPack
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
from derisk_serve.mcp.api.schemas import (
    ServerResponse as MCPResponse,
    ServeRequest as MCPRequest,
)


logger = logging.getLogger(__name__)
CFG = Config()


def get_mcp_list(**kwargs) -> List[Dict]:
    logger.info(f"get_mcp_list:{kwargs}")
    from derisk_serve.mcp.service.service import Service as McpService

    mcp_service = McpService.get_instance(CFG.SYSTEM_APP)
    mcp_list: List[MCPResponse] = mcp_service.get_list(MCPRequest())

    results = [
        {
            "label": mcp.name + f"-[{mcp.description}]",
            "key": mcp.mcp_code,
            "value": mcp.mcp_code,
            "description": mcp.description,
        }
        for mcp in mcp_list
    ]
    return results


def get_mcp_info(mcp_code: str) -> Optional[MCPResponse]:
    logger.info(f"get_mcp_info:{mcp_code}")
    from derisk_serve.mcp.service.service import Service as McpService

    mcp_service = McpService.get_instance(CFG.SYSTEM_APP)
    mcp_resp: MCPResponse = mcp_service.get(MCPRequest(mcp_code=mcp_code))
    return mcp_resp


@dataclasses.dataclass
class MCPResourceParameters(PackResourceParameters):
    mcp_servers: str = dataclasses.field(
        default="mcp code",
        metadata={
            "help": _("MCP SSE Server Code."),
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
            "help": _("Allow tools, use ':' to split multiple tools, default is all"),
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

    @classmethod
    def _resource_version(cls) -> str:
        """Return the resource version."""
        return "v1"

    @classmethod
    def to_configurations(
        cls,
        parameters: Type["MCPResourceParameters"],
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
    ) -> "MCPResourceParameters":
        """Create a new instance from a dictionary."""
        copied_data = data.copy()

        if "value" in copied_data:
            value = copied_data.pop("value")
            if isinstance(value, str):
                try:
                    value_data = json.loads(value)
                except json.JSONDecodeError:
                    value_data = {"mcp_code": value}
            else:
                value_data = value
        else:
            value_data = copied_data

        mcp_code = (
            value_data.get("mcp_code") if isinstance(value_data, dict) else value_data
        )
        if not mcp_code:
            raise ValueError(f"无法从数据中提取mcp_code: {data}")

        mcp_info: Optional[MCPResponse] = get_mcp_info(mcp_code)
        if not mcp_info:
            raise ValueError(f"无法找到当前mcp服务[{mcp_code}].")

        copied_data["mcp_servers"] = mcp_info.sse_url
        copied_data["headers"] = mcp_info.sse_headers
        if (
            "name" not in copied_data
            and isinstance(value_data, dict)
            and value_data.get("name")
        ):
            copied_data["name"] = value_data.get("name")
        return super().from_dict(copied_data, ignore_extra_fields=ignore_extra_fields)


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


class MCPCollectSSEToolPack(MCPToolPack):
    def __init__(self, mcp_servers: Union[str, List[str]], **kwargs):
        super().__init__(mcp_servers=mcp_servers, **kwargs)

    @classmethod
    def type(cls) -> Union[ResourceType, str]:
        return "mcp(derisk)"

    @classmethod
    def type_alias(cls) -> str:
        return "mcp(derisk)"

    @classmethod
    def resource_parameters_class(cls, **kwargs) -> Type[MCPResourceParameters]:
        logger.info(f"resource_parameters_class:{kwargs}")
        result = get_mcp_list(**kwargs)

        @dataclasses.dataclass
        class _DynMCPResourceParameters(MCPResourceParameters):
            mcp_server: str = dataclasses.field(
                default="mcp code",
                metadata={
                    "help": _("MCP SSE Server Code."),
                    "valid_values": result,
                },
            )

        return _DynMCPResourceParameters
