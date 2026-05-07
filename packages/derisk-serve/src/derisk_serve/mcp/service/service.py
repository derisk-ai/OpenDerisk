import json
import logging
from datetime import datetime
from typing import Any, List, Optional

from derisk._private.config import Config
from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk.util.pagination_utils import PaginationResult
from derisk_ext.plugin.memory_case import (
    BUILTIN_MEMORY_MCP,
    BUILTIN_MEMORY_MCP_NAME,
    MemoryCasePluginService,
    MemoryPluginError,
)
from derisk_ext.plugin.memory_case.integration import (
    ensure_memory_case_resource_resolver_registered,
)
from derisk_ext.plugin.memory_case.plugin_resolver import (
    register_memory_case_plugin_resolver,
)
from derisk_serve.core import BaseService

from ...agent.resource.tool.mcp_utils import call_mcp_tool, switch_mcp_input_schema
from ...rag.storage_manager import StorageManager
from ..api.schemas import McpTool, QueryFilter, ServeRequest, ServerResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from derisk_ext.plugin.memory_case.vector_index import build_vector_index
from derisk_ext.plugin.memory_case.sqlalchemy_dao import MemoryCaseDao
from ..models.models import ServeDao, ServeEntity

logger = logging.getLogger(__name__)


class Service(BaseService[ServeEntity, ServeRequest, ServerResponse]):
    """The service class for Mcp"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
            self, system_app: SystemApp, config: ServeConfig, dao: Optional[ServeDao] = None
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: ServeDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        ensure_memory_case_resource_resolver_registered()
        self._dao = self._dao or ServeDao(self._serve_config)
        self._system_app = system_app
        storage_manager: Optional[StorageManager] = None
        try:
            storage_manager = StorageManager.get_instance(system_app)
        except Exception:
            logger.debug(
                "StorageManager unavailable for memory_case vector index",
                exc_info=True,
            )
        vector_index = build_vector_index(storage_manager)
        self._memory_plugin = MemoryCasePluginService(
            system_app,
            dao=MemoryCaseDao(),
            enabled=self._serve_config.memory_plugin_enabled,
            timeout_seconds=self._serve_config.memory_plugin_timeout,
            vector_index=vector_index,
        )
        plugin = self._memory_plugin
        register_memory_case_plugin_resolver(lambda _app: plugin)

    @property
    def dao(self) -> BaseDao[ServeEntity, ServeRequest, ServerResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    def update(self, request: ServeRequest) -> ServerResponse:
        """Update a Mcp entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = {
            "mcp_code": request.mcp_code
        }
        request_dict = (
            request.dict() if isinstance(request, ServeRequest) else request
        )

        # 处理 JSON 字段序列化
        if 'sse_headers' in request_dict and isinstance(request_dict['sse_headers'], dict):
            request_dict['sse_headers'] = json.dumps(request_dict['sse_headers'])

        if 'available' in request_dict:
            # 将None转换为False，或保持原值
            request_dict['available'] = request_dict['available'] if request_dict['available'] is not None else False
        # 过滤掉只读字段（如自动生成的 id 和时间戳）
        request_dict.pop('mcp_code', None)
        request_dict.pop('gmt_created', None)
        request_dict.pop('gmt_modified', None)
        # 过滤掉虚拟字段（不存在于 DB 表中，仅用于 API 响应）
        request_dict.pop('is_builtin', None)

        return self.dao.update(query_request, request_dict)

    def get(self, request: ServeRequest) -> Optional[ServerResponse]:
        """Get a Mcp entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        code_or_name = (request.mcp_code or request.name or "").strip()
        memory_plugin = getattr(self, "_memory_plugin", None)
        if (
            code_or_name
            and memory_plugin
            and memory_plugin.enabled
            and self._is_builtin_memory_mcp(code_or_name)
        ):
            return self._builtin_memory_case_server_response()

        query_request = request
        return self.dao.get_one(query_request)

    def _builtin_memory_case_server_response(self) -> ServerResponse:
        """Single factory for the built-in memory_case MCP row (not in DB).

        All display fields and sse_url are defined only here; callers only gate
        plugin enabled / filter / dedupe.
        """
        port = int(Config().DERISK_WEBSERVER_PORT)
        sse_url = f"http://localhost:{port}/mcp/sse"
        now = datetime.now().isoformat()
        return ServerResponse(
            mcp_code=BUILTIN_MEMORY_MCP,
            name=BUILTIN_MEMORY_MCP_NAME,
            description="内置案例记忆插件，提供案例搜索、新增、反馈和渲染能力",
            type="builtin",
            author="Derisk",
            version="1.0.0",
            sse_url=sse_url,
            sse_headers=None,
            token=None,
            icon="",
            category="builtin",
            installed=0,
            available=True,
            is_builtin=True,
            server_ips=None,
            gmt_created=now,
            gmt_modified=now,
        )

    def delete(self, request: ServeRequest) -> None:
        """Delete a Mcp entity

        Args:
            request (ServeRequest): The request
        """

        code = (request.mcp_code or "").strip()
        name = (request.name or "").strip()
        if (code and self._is_builtin_memory_mcp(code)) or (
            name and self._is_builtin_memory_mcp(name)
        ):
            raise ValueError(
                f"内置 MCP[{BUILTIN_MEMORY_MCP}] 不可删除，请在界面中关闭案例记忆插件配置。"
            )
        query_request = request
        self.dao.delete(query_request)

    def get_list(self, request: ServeRequest) -> List[ServerResponse]:
        """Get a list of Mcp entities

        Args:
            request (ServeRequest): The request

        Returns:
            List[ServerResponse]: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self.dao.get_list(query_request)

    def get_list_by_page(
            self, request: ServeRequest, page: int, page_size: int
    ) -> PaginationResult[ServerResponse]:
        """Get a list of Mcp entities by page

        Args:
            request (ServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[ServerResponse]: The response
        """
        query_request = request
        return self.dao.get_list_page(query_request, page, page_size)

    def filter_list_page(
            self,
            query_request: QueryFilter,
            page: int,
            page_size: int,
            desc_order_column: Optional[str] = None,
    ) -> PaginationResult[ServerResponse]:
        """Get a page of entity objects, with built-in MCP entries injected.

        Args:
            query_request (REQ): The request schema object or dict for query.
            page (int): The page number.
            page_size (int): The page size.

        Returns:
            PaginationResult: The pagination result.
        """
        result = self.dao.filter_list_page(query_request, page, page_size, desc_order_column)

        memory_plugin = getattr(self, "_memory_plugin", None)
        if memory_plugin and memory_plugin.enabled:
            if any(getattr(i, "mcp_code", None) == BUILTIN_MEMORY_MCP for i in result.items):
                return result
            virtual_entry = self._builtin_memory_case_server_response()
            filter_text = (query_request.filter or "").lower()
            matches_filter = (
                not filter_text
                or filter_text in virtual_entry.name.lower()
                or filter_text in virtual_entry.description.lower()
                or filter_text in virtual_entry.mcp_code.lower()
                or filter_text in "memory case"
            )
            if matches_filter and page == 1:
                result.items.insert(0, virtual_entry)
                result.total_count += 1

        return result

    def _is_builtin_memory_mcp(self, mcp_name: str) -> bool:
        """Check if the given name refers to the built-in memory_case MCP.

        Accepts either the mcp_code ('memory_case') or display name ('案例记忆').
        """
        return mcp_name in (BUILTIN_MEMORY_MCP, BUILTIN_MEMORY_MCP_NAME)

    async def connect_mcp(self, mcp_name: str, headers: Optional[dict], timeout: Optional[int] = None):
        logger.info(f"connect_mcp:{mcp_name},{headers}")
        if self._is_builtin_memory_mcp(mcp_name):
            return self._memory_plugin.enabled
        mcp_resp = self.get(ServeRequest(name=mcp_name))
        if not mcp_resp:
            raise ValueError(f"不存在的mcp[{mcp_name}]!")
        
        mcp_headers = self._build_headers(mcp_resp, headers)
        from derisk.agent.resource.tool.mcp.mcp_utils import connect_mcp
        return await connect_mcp(mcp_name, mcp_resp.sse_url, mcp_headers, timeout=timeout)

    async def list_tools(self, mcp_name: str, mcp_sse_url: Optional[str], headers: Optional[dict[str, Any]] = None,
                         timeout: Optional[int] = None) -> \
    Optional[List[McpTool]]:
        logger.info(f"mcp list tools:{mcp_name},{mcp_sse_url},{headers}")
        if self._is_builtin_memory_mcp(mcp_name):
            return [
                McpTool(
                    name=tool.name,
                    description=tool.description,
                    param_schema=switch_mcp_input_schema(tool.inputSchema),
                    raw_input_schema=tool.inputSchema,
                )
                for tool in self._memory_plugin.list_tools()
            ]
        tool_list = []
        mcp_resp = self.get(ServeRequest(name=mcp_name))
        if not mcp_resp:
            raise ValueError(f"不存在的mcp[{mcp_name}]!")

        from derisk.agent.resource.tool.mcp.mcp_utils import get_mcp_tool_list
        mcp_headers = self._build_headers(mcp_resp, headers)
        result = await get_mcp_tool_list(mcp_name, mcp_sse_url if mcp_sse_url else mcp_resp.sse_url, mcp_headers,
                                         timeout=timeout)
        for tool in result.tools:
            tool_list.append(McpTool(name=tool.name, description=tool.description,
                                     param_schema=switch_mcp_input_schema(tool.inputSchema)))
        return tool_list

    async def call_tool(self, mcp_name: str, tool_name: str, mcp_sse_url: Optional[str] = None,
                        arguments: dict[str, Any] | None = None,
                        headers: Optional[dict] = None,
                        timeout: Optional[int] = None):
        logger.info(f"call mcp tool:{mcp_name},{mcp_sse_url}")
        if self._is_builtin_memory_mcp(mcp_name):
            try:
                return await self._memory_plugin.call_tool(tool_name=tool_name, arguments=arguments)
            except MemoryPluginError as exc:
                return {"code": exc.code, "message": exc.message}

        mcp_resp = self.get(ServeRequest(name=mcp_name))
        if not mcp_resp:
            raise ValueError(f"不存在的mcp[{mcp_name}]!")

        mcp_headers = self._build_headers(mcp_resp, headers)
        call_args = arguments or {}
        return await call_mcp_tool(mcp_name=mcp_name, tool_name=tool_name,
                                   server=mcp_sse_url if mcp_sse_url else mcp_resp.sse_url, headers=mcp_headers,
                                   timeout=timeout,
                                   **call_args)

    def _build_headers(
        self, mcp_resp: ServerResponse, extra_headers: Optional[dict] = None
    ) -> dict:
        """Build merged headers from DB sse_headers, token and extra request headers.

        Priority (low -> high):
          1. sse_headers stored in DB
          2. token field auto-converted to Authorization Bearer header
             (only if Authorization is not already set by sse_headers)
          3. extra_headers passed at request time (highest priority override)
        """
        mcp_headers: dict[str, str] = {}
        if mcp_resp.sse_headers:
            mcp_headers.update(**mcp_resp.sse_headers)
        # Auto-convert token to Authorization header when not explicitly set
        if mcp_resp.token and "Authorization" not in mcp_headers:
            mcp_headers["Authorization"] = f"Bearer {mcp_resp.token}"
        if extra_headers:
            mcp_headers.update(**extra_headers)
        return mcp_headers
