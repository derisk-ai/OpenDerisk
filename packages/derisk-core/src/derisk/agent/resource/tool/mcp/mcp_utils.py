import asyncio
import logging
from datetime import datetime
from typing import Optional, Any, List

from cachetools import TTLCache
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

from derisk._private.config import Config
from derisk.util.async_executor_utils import ServiceUnavailableError, safe_call_tool
from derisk.util.log_util import MCP_LOGGER as LOGGER
from derisk.util.tracer import root_tracer

logger = logging.getLogger(__name__)
tool_cache = TTLCache(maxsize=200, ttl=300)

CFG = Config()


def switch_mcp_input_schema( input_schema: dict):
    args = {}
    try:
        properties = input_schema["properties"]
        required = input_schema.get("required", [])
        for k, v in properties.items():
            arg = {}

            title = v.get("title", None)
            description = v.get("description", None)
            items = v.get("items", None)
            items_str = str(items) if items else None
            any_of = v.get("anyOf", None)
            any_of_str = str(any_of) if any_of else None

            default = v.get("default", None)
            type = v.get("type", "string")

            arg["type"] = type
            if title:
                arg["title"] = title
            arg["description"] = description or items_str or any_of_str or str(v)
            arg["required"] = True if k in required else False
            if default:
                arg["default"] = default
            args[k] = arg
        return args
    except Exception as e:
        raise ValueError(f"MCP input_schema can't parase!{str(e)},{input_schema}")



async def get_mcp_tool_list(mcp_name: str, server: str, headers: Optional[dict] = None,
                            allow_tools: Optional[List[str]] = None, server_ssl_verify: Optional[Any] = None, use_cache: bool = True):
    trace_id = root_tracer.get_current_span().trace_id

    async def mcp_tool_list(server: str):
        if tool_cache.get(mcp_name):
            LOGGER.info(f"[{trace_id}]mcp_server:{mcp_name}, hit tool list cache:{tool_cache.get(mcp_name)}")
            return tool_cache.get(mcp_name)
        from datetime import datetime
        start_time = int(datetime.now().timestamp() * 1000)
        async with sse_client(url=server, headers=headers) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()
                result = await session.list_tools()
                if allow_tools and len(allow_tools) > 0:
                    tools = [tool for tool in result.tools if tool.name in allow_tools]
                    result.tools = tools
                end_time = int(datetime.now().timestamp() * 1000)
                LOGGER.info(
                    f"[{trace_id}]mcp_server:{mcp_name},sse:{server},header:{headers},list_tools:[{result}],costMs:[{end_time - start_time}]"
                )
                if use_cache:
                    tool_cache[mcp_name] = result
                return result

    try:
        if CFG.debug_mode:
            logger.info("MCP Enter DebugMode, Use local mcp gateways!")
            server = f"http://localhost:{CFG.DERISK_WEBSERVER_PORT}/mcp/sse"
        return await safe_call_tool(
            mcp_tool_list,  # 可能是阻塞的函数
            server,
            time_out=30,
        )
    except ServiceUnavailableError as e:
        LOGGER.exception(
            f"[{trace_id}][DIGEST][tools/list]mcp_server=[{mcp_name}],sse=[{server}],success=[N],err_msg=[{str(e)}]"
        )
        raise ValueError(f"MCP服务{server}工具列表调用异常!", e)
    except asyncio.TimeoutError as e:
        LOGGER.exception(
            f"[{trace_id}][DIGEST][tools/list]mcp_server=[{mcp_name}],sse=[{server}],success=[N],err_msg=[{str(e)}]"
        )
        raise ValueError(f"MCP服务{server}工具列表调用超时!")


async def call_mcp_tool(mcp_name: str, tool_name: str, server: str, headers: Optional[dict[str, str]] = None,
                        server_ssl_verify: Optional[Any] = None, **kwargs):
    logger.info(f"call_mcp_tool:{mcp_name},{tool_name},{server}")
    trace_id = root_tracer.get_current_span().trace_id

    async def call_tool(**kwargs):
        start_time = int(datetime.now().timestamp() * 1000)
        try:
            async with sse_client(
                    url=server, headers=headers
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize the connection
                    await session.initialize()
                    result = await session.call_tool(
                        tool_name, arguments=kwargs
                    )
                    end_time = int(
                        datetime.now().timestamp() * 1000
                    )
                    LOGGER.info(
                        f"[{trace_id}][DIGEST][tools/call]mcp_server=[{mcp_name}],sse=[{server}],tool=[{tool_name}],success=[Y],err_msg=[None],costMs=[{end_time - start_time}],result_length=[{len(str(result.json()))}],headers=[{headers}]"
                    )
                    LOGGER.info(
                        f"[{trace_id}]mcp_server:{mcp_name},sse:[{server}],header:{headers},tool:{tool_name},result:[{result.json()}]"
                    )
                    return result.json()
        except Exception as e:
            LOGGER.exception(
                f"[{trace_id}][DIGEST][tools/call]mcp_server=[{mcp_name}],sse=[{server}],tool=[{tool_name}],success=[N],err_msg=[{str(e)}],costMs=[None],result_length=[None],headers=[{headers}]"
            )
            raise ValueError(f"MCP Call Exception! {str(e)}")

    try:
        return await safe_call_tool(
            call_tool,
            **kwargs,
            time_out=600,
        )
    except ServiceUnavailableError as e:
        raise ValueError(f"MCP服务{mcp_name}工具调用异常!", e)
    except asyncio.TimeoutError as e:
        raise ValueError(f"MCP服务{mcp_name}工具调用超时!")
    except Exception as e:
        raise ValueError(f"MCP服务{mcp_name}:{tool_name}工具调用异常!", e)
