import asyncio
import json
import logging
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Optional, Any, List

import shortuuid
from cachetools import TTLCache
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

from derisk._private.config import Config
from derisk.util.async_executor_utils import safe_call_tool
from derisk.util.global_helper import truncate_text
from derisk.util.log_util import MCP_LOGGER as LOGGER
from derisk.util.tracer import root_tracer
from derisk_serve.agent.db.gpts_tool import GptsToolDao
from derisk_serve.agent.db.gpts_tool_messages import (
    GptsToolMessagesDao,
    GptsToolMessages,
)


def _make_json_serializable(obj: Any) -> Any:
    """将对象转换为 JSON 可序列化的格式。

    处理包括 AgentFileSystem 等非序列化对象，将其转换为字符串或字典表示。
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}

    # 处理 AgentFileSystem 和其他常见非序列化类型
    type_name = type(obj).__name__

    # AgentFileSystem 类型 - 转换为字符串表示
    if type_name == "AgentFileSystem":
        return f"<AgentFileSystem: {getattr(obj, 'root_path', str(obj))}>"

    # Pydantic 模型 - 使用 model_dump 或 dict
    if hasattr(obj, "model_dump"):
        return _make_json_serializable(obj.model_dump())
    if hasattr(obj, "dict"):
        return _make_json_serializable(obj.dict())

    # dataclass - 使用 asdict
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return _make_json_serializable(asdict(obj))

    # 其他对象 - 尝试转换为字符串
    try:
        return str(obj)
    except Exception:
        return f"<{type_name}: unserializable>"

logger = logging.getLogger(__name__)
tool_cache = TTLCache(maxsize=200, ttl=300)
gpts_tool_messages_dao = GptsToolMessagesDao()
gpts_tool_dao = GptsToolDao()

CFG = Config()


def switch_mcp_input_schema(input_schema: dict):
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


async def get_mcp_tool_list(
    mcp_name: str,
    server: str,
    headers: Optional[dict] = None,
    allow_tools: Optional[List[str]] = None,
    server_ssl_verify: Optional[Any] = None,
    use_cache: bool = True,
    tool_id: Optional[str] = None,
    timeout: Optional[int] = None,
):
    trace_id = (
        root_tracer.get_current_span().trace_id
        if root_tracer.get_current_span().trace_id is not None
        else str(uuid.uuid4())
    )
    rpc_id = (
        root_tracer.get_context_rpc_id() + "." + shortuuid.ShortUUID().random(length=8)
    )
    cookie = root_tracer.get_context_cookie()

    if headers is None:
        headers = {}

    async def mcp_tool_list(server: str):
        try:
            cache_result = tool_cache.get(mcp_name)
            if cache_result and cache_result.tools and len(cache_result.tools) > 0:
                LOGGER.info(
                    f"mcp_server:{mcp_name}, hit tool list cache:{cache_result}"
                )
                result = cache_result
            else:
                start_time = int(datetime.now().timestamp() * 1000)
                (
                    headers["SOFA-TraceId"],
                    headers["SOFA-RpcId"],
                    headers["x-mcp-hash-key"],
                    headers["cookie"],
                ) = trace_id, rpc_id, str(uuid.uuid4()), cookie
                async with sse_client(url=server, headers=headers) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        list_tools = await session.list_tools()
                        end_time = int(datetime.now().timestamp() * 1000)
                        LOGGER.info(
                            f"mcp_server:{mcp_name},sse:{server},header:{headers},list_tools:[{list_tools}],costMs:[{end_time - start_time}]"
                        )
                        if use_cache:
                            tool_cache[mcp_name] = list_tools
                        result = deepcopy(list_tools)
            if allow_tools and len(allow_tools) > 0:
                tools = [tool for tool in result.tools if tool.name in allow_tools]
                result.tools = tools
            return result
        except Exception as e:
            LOGGER.exception(
                f"[DIGEST][tools/list]mcp_server=[{mcp_name}],sse=[{server}],success=[N],err_msg=[{str(e)}]"
            )
            raise e

    try:
        time_out = timeout if timeout else 60
        if CFG.debug_mode:
            logger.info("MCP Enter DebugMode, Use local mcp gateways!")
            server = f"http://localhost:{CFG.DERISK_WEBSERVER_PORT}/mcp/sse"
            time_out = 180
        return await safe_call_tool(
            mcp_tool_list,  # 可能是阻塞的函数
            server,
            time_out=time_out,
        )
    except asyncio.TimeoutError as e:
        raise ValueError(f"MCP服务{server}工具列表调用超时!")
    except Exception as e:
        raise ValueError(f"MCP服务{server}工具列表调用异常!", e)


async def call_mcp_tool(
    mcp_name: str,
    tool_name: str,
    server: str,
    headers: Optional[dict[str, str]] = None,
    server_ssl_verify: Optional[Any] = None,
    timeout: Optional[int] = None,
    tool_id: Optional[str] = None,
    **kwargs,
):
    logger.info(f"call_mcp_tool:{mcp_name},{tool_name},{server},{timeout}")
    trace_id = (
        root_tracer.get_current_span().trace_id
        if root_tracer.get_current_span().trace_id is not None
        else str(uuid.uuid4())
    )
    rpc_id = (
        root_tracer.get_context_rpc_id() + "." + shortuuid.ShortUUID().random(length=8)
    )
    cookie = root_tracer.get_context_cookie()

    if headers is None:
        headers = {}

    arguments = kwargs.get("arguments", kwargs)
    if isinstance(arguments, dict):
        arguments = {
            k: v
            for k, v in arguments.items()
            if k
            not in (
                "time_out",
                "timeout",
                "tool_id",
                "server_ssl_verify",
                "headers",
                "server",
                "tool_name",
                "mcp_name",
            )
        }

    if not tool_id:
        tool_id = str(uuid.uuid4())

    async def call_tool(server: str, arguments: dict):
        # 将参数转换为 JSON 可序列化格式，处理 AgentFileSystem 等对象
        serializable_arguments = _make_json_serializable(arguments)

        gpts_tool_messages = GptsToolMessages(
            tool_id=tool_id,
            name=mcp_name,
            sub_name=tool_name,
            type="MCP",
            input=json.dumps(serializable_arguments, ensure_ascii=False),
            success=1,
            trace_id=trace_id,
        )

        try:
            start_time = int(datetime.now().timestamp() * 1000)
            (
                headers["SOFA-TraceId"],
                headers["SOFA-RpcId"],
                headers["x-mcp-hash-key"],
                headers["cookie"],
            ) = trace_id, rpc_id, str(uuid.uuid4()), cookie

            if CFG.debug_mode:
                logger.info("MCP Enter DebugMode, Use local mcp gateways!")
                mcp_server = f"http://localhost:{CFG.DERISK_WEBSERVER_PORT}/mcp/sse"
            else:
                mcp_server = server
            async with sse_client(
                url=mcp_server, headers=headers, sse_read_timeout=timeout
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=serializable_arguments)
                    end_time = int(datetime.now().timestamp() * 1000)
                    LOGGER.info(
                        f"[DIGEST][tools/call]mcp_server=[{mcp_name}],sse=[{mcp_server}],success=[Y],err_msg=[],tool=[{tool_name}],costMs=[{end_time - start_time}],result_length=[{len(str(result.json()))}],headers=[{headers}],result:[{result.json()}]"
                    )
                    gpts_tool_messages.output = truncate_text(
                        json.dumps(result.model_dump(), ensure_ascii=False), 65535
                    )
                    return result
        except Exception as e:
            gpts_tool_messages.error = str(e)
            gpts_tool_messages.success = 0
            LOGGER.exception(
                f"[DIGEST][tools/call]mcp_server=[{mcp_name}],sse=[{server}],success=[N],err_msg=[{str(e)}],tool=[{tool_name}],costMs=[],result_length=[],headers=[{headers}]"
            )
            raise e
        finally:
            try:
                gpts_tool_messages_dao.create(gpts_tool_messages)
            except Exception as m:
                logger.info(
                    f"call_mcp_tool: save message error: {m}, trace_id:{trace_id}"
                )

    try:
        return await call_tool(server, arguments)
    except asyncio.TimeoutError as e:
        raise ValueError(f"MCP服务{mcp_name}工具调用超时!")
    except Exception as e:
        raise ValueError(f"MCP服务{mcp_name}:{tool_name}工具调用异常!", e)


def get_im_token(cookie: str):
    if not cookie or cookie == "":
        return None

    # 按分号分割所有键值对
    pairs = cookie.split(";")

    # 用于保存最后出现的 im_token
    im_token = None

    for pair in pairs:
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            if key == "IAM_TOKEN":
                im_token = value

    return im_token
