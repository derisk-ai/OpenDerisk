"""McpService virtual builtin memory_case (no full derisk_serve DB fixture)."""

from unittest.mock import MagicMock

import pytest
from derisk.component import SystemApp
from derisk.util import AppConfig
from derisk.util.fastapi import create_app
from derisk.util.pagination_utils import PaginationResult
from derisk_serve.mcp.api.schemas import QueryFilter, ServeRequest
from derisk_serve.mcp.config import ServeConfig
from derisk_serve.mcp.service.service import Service


@pytest.fixture
def mcp_service() -> Service:
    system_app = SystemApp(create_app(), AppConfig(configs={}))
    svc = Service(system_app, ServeConfig(memory_plugin_enabled=True))
    svc.init_app(system_app)
    return svc


def test_builtin_memory_case_server_response_shape(mcp_service: Service) -> None:
    row = mcp_service._builtin_memory_case_server_response()
    assert row.mcp_code == "memory_case"
    assert row.is_builtin is True
    assert row.sse_url and "/mcp/sse" in row.sse_url


def test_builtin_memory_case_get_and_delete_guard(mcp_service: Service) -> None:
    row = mcp_service.get(ServeRequest(mcp_code="memory_case"))
    assert row is not None
    assert row.is_builtin is True
    row2 = mcp_service.get(ServeRequest(name="案例记忆"))
    assert row2 is not None
    assert row2.mcp_code == "memory_case"
    with pytest.raises(ValueError, match="不可删除"):
        mcp_service.delete(ServeRequest(mcp_code="memory_case"))
    with pytest.raises(ValueError, match="不可删除"):
        mcp_service.delete(ServeRequest(name="案例记忆"))


def test_filter_list_page_inserts_virtual_when_dao_empty(mcp_service: Service) -> None:
    empty = PaginationResult(
        items=[],
        total_count=0,
        total_pages=0,
        page=1,
        page_size=50,
    )
    mcp_service.dao.filter_list_page = MagicMock(return_value=empty)
    result = mcp_service.filter_list_page(QueryFilter(), page=1, page_size=50)
    assert len(result.items) == 1
    assert result.items[0].mcp_code == "memory_case"
    assert result.total_count == 1


def test_filter_list_page_skips_virtual_when_dao_has_row(mcp_service: Service) -> None:
    from derisk_serve.mcp.api.schemas import ServerResponse

    existing = ServerResponse(
        mcp_code="memory_case",
        name="案例记忆",
        description="from db",
        type="builtin",
        author="x",
        email=None,
        version="1",
        stdio_cmd=None,
        sse_url="http://localhost:9/mcp/sse",
        sse_headers=None,
        token=None,
        icon=None,
        category="builtin",
        installed=0,
        available=True,
        is_builtin=False,
        server_ips=None,
        gmt_created="2020-01-01T00:00:00",
        gmt_modified="2020-01-01T00:00:00",
    )
    page = PaginationResult(
        items=[existing],
        total_count=1,
        total_pages=1,
        page=1,
        page_size=50,
    )
    mcp_service.dao.filter_list_page = MagicMock(return_value=page)
    result = mcp_service.filter_list_page(QueryFilter(), page=1, page_size=50)
    assert len(result.items) == 1
    assert result.items[0].description == "from db"
