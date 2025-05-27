import logging
from typing import List, Optional, Any

from derisk.agent.resource.tool.mcp.mcp_utils import switch_mcp_input_schema, call_mcp_tool
from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk.util.pagination_utils import PaginationResult
from derisk_serve.core import BaseService

from ..api.schemas import ServeRequest, ServerResponse, McpTool, QueryFilter
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
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
        self._dao = self._dao or ServeDao(self._serve_config)
        self._system_app = system_app

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
            # "id": request.id
        }
        return self.dao.update(query_request, update_request=request)

    def get(self, request: ServeRequest) -> Optional[ServerResponse]:
        """Get a Mcp entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self.dao.get_one(query_request)

    def delete(self, request: ServeRequest) -> None:
        """Delete a Mcp entity

        Args:
            request (ServeRequest): The request
        """

        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = {
            "id": request.id
        }
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
        """Get a page of entity objects.

        Args:
            query_request (REQ): The request schema object or dict for query.
            page (int): The page number.
            page_size (int): The page size.

        Returns:
            PaginationResult: The pagination result.
        """
        return self.dao.filter_list_page(query_request, page, page_size, desc_order_column)

    async def connect_mcp(self, mcp_name: str, headers: Optional[dict]):
        logger.info(f"connect_mcp:{mcp_name},{headers}")
        mcp_resp = self.get(ServeRequest(mcp_name=mcp_name))
        if not mcp_resp:
            raise ValueError(f"不存在的mcp[{mcp_name}]!")

    async def list_tools(self, mcp_name: str, mcp_sse_url: Optional[str], headers: Optional[dict[str, Any]] = None) -> \
    Optional[List[McpTool]]:
        logger.info(f"mcp list tools:{mcp_name},{mcp_sse_url},{headers}")
        tool_list = []
        mcp_resp = self.get(ServeRequest(name=mcp_name))
        if not mcp_resp:
            raise ValueError(f"不存在的mcp[{mcp_name}]!")

        from derisk.agent.resource.tool.mcp.mcp_utils import get_mcp_tool_list
        mcp_headers = {}

        if mcp_resp.sse_headers:
            mcp_headers.update(**mcp_resp.sse_headers)
        if headers:
            mcp_headers.update(**headers)
        result = await get_mcp_tool_list(mcp_name, mcp_sse_url if mcp_sse_url else mcp_resp.sse_url, mcp_headers)
        for tool in result.tools:
            tool_list.append(McpTool(name=tool.name, description=tool.description,
                                     param_schema=switch_mcp_input_schema(tool.inputSchema)))
        return tool_list

    async def call_tool(self, mcp_name: str, tool_name: str, mcp_sse_url: Optional[str] = None,
                        arguments: dict[str, Any] | None = None,
                        headers: Optional[dict] = None):
        logger.info(f"call mcp tool:{mcp_name},{mcp_sse_url}")
        mcp_resp = self.get(ServeRequest(mcp_name=mcp_name))
        if not mcp_resp:
            raise ValueError(f"不存在的mcp[{mcp_name}]!")

        mcp_headers = {}
        if mcp_resp.sse_headers:
            mcp_headers.update(**mcp_resp.sse_headers)
        if headers:
            mcp_headers.update(**headers)
        return await call_mcp_tool(mcp_name=mcp_name, tool_name=tool_name,
                                   server=mcp_sse_url if mcp_sse_url else mcp_resp.sse_url, headers=mcp_headers,
                                   arguments=arguments)
