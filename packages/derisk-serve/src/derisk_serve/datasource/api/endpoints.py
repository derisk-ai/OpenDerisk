from functools import cache
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import ResourceTypes, Result, blocking_func_to_async
from derisk_serve.datasource.api.schemas import (
    BatchTableRequest,
    DatasourceCreateRequest,
    DatasourceQueryResponse,
    DatasourceServeRequest,
    DbSpecResponse,
    LearningTaskRequest,
    LearningTaskResponse,
    TableDataPreviewResponse,
    TableSpecDetailResponse,
    TableSpecSummaryResponse,
)
from derisk_serve.datasource.config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from derisk_serve.datasource.service.service import Service

router = APIRouter()

# Add your API endpoints here

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance"""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


@cache
def _parse_api_keys(api_keys: str) -> List[str]:
    """Parse the string api keys to a list

    Args:
        api_keys (str): The string api keys

    Returns:
        List[str]: The list of api keys
    """
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    service: Service = Depends(get_service),
) -> Optional[str]:
    """Check the api key

    If the api key is not set, allow all.

    Your can pass the token in you request header like this:

    .. code-block:: python

        import requests

        client_api_key = "your_api_key"
        headers = {"Authorization": "Bearer " + client_api_key}
        res = requests.get("http://test/hello", headers=headers)
        assert res.status_code == 200

    """
    if service.config.api_keys:
        api_keys = _parse_api_keys(service.config.api_keys)
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "message": "",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                },
            )
        return token
    else:
        # api_keys not set; allow all
        return None


@router.get("/health", dependencies=[Depends(check_api_key)])
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


@router.get("/test_auth", dependencies=[Depends(check_api_key)])
async def test_auth():
    """Test auth endpoint"""
    return {"status": "ok"}


@router.post(
    "/datasources/upload-db",
    response_model=Result[dict],
    dependencies=[Depends(check_api_key)],
)
async def upload_db_file(
    file: UploadFile,
    service: Service = Depends(get_service),
) -> Result[dict]:
    """Upload a database file and return the server-side storage path.

    Used for file-based databases (SQLite, DuckDB, etc.) where the browser
    cannot provide the server-side file path.
    """
    result = await blocking_func_to_async(
        global_system_app, service.upload_db_file, file
    )
    return Result.succ(result)


@router.post(
    "/datasources",
    response_model=Result[DatasourceQueryResponse],
    dependencies=[Depends(check_api_key)],
)
async def create(
    request: Union[DatasourceCreateRequest, DatasourceServeRequest],
    service: Service = Depends(get_service),
) -> Result[DatasourceQueryResponse]:
    """Create a new Space entity

    Args:
        request (Union[DatasourceCreateRequest, DatasourceServeRequest]): The request
            to create a datasource. DatasourceServeRequest is deprecated.
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.create(request))


@router.put(
    "/datasources",
    response_model=Result[DatasourceQueryResponse],
    dependencies=[Depends(check_api_key)],
)
async def update(
    request: Union[DatasourceCreateRequest, DatasourceServeRequest],
    service: Service = Depends(get_service),
) -> Result[DatasourceQueryResponse]:
    """Update a Space entity

    Args:
        request (DatasourceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    return Result.succ(service.update(request))


@router.delete(
    "/datasources/{datasource_id}",
    response_model=Result[None],
    dependencies=[Depends(check_api_key)],
)
async def delete(
    datasource_id: str, service: Service = Depends(get_service)
) -> Result[None]:
    """Delete a Space entity

    Args:
        request (DatasourceServeRequest): The request
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    service.delete(datasource_id)
    return Result.succ(None)


@router.get(
    "/datasources/{datasource_id}",
    dependencies=[Depends(check_api_key)],
    response_model=Result[DatasourceQueryResponse],
)
async def query(
    datasource_id: str, service: Service = Depends(get_service)
) -> Result[DatasourceQueryResponse]:
    """Query Space entities

    Args:
        request (DatasourceServeRequest): The request
        service (Service): The service
    Returns:
        List[ServeResponse]: The response
    """
    return Result.succ(service.get(datasource_id))


@router.get(
    "/datasources",
    dependencies=[Depends(check_api_key)],
    response_model=Result[List[DatasourceQueryResponse]],
)
async def query_page(
    db_type: Optional[str] = Query(
        None, description="Database type, e.g. sqlite, mysql, etc."
    ),
    service: Service = Depends(get_service),
) -> Result[List[DatasourceQueryResponse]]:
    """Query Space entities

    Args:
        service (Service): The service
    Returns:
        ServerResponse: The response
    """
    res = service.get_list(db_type=db_type)
    return Result.succ(res)


@router.get(
    "/datasource-types",
    dependencies=[Depends(check_api_key)],
    response_model=Result[ResourceTypes],
)
async def get_datasource_types(
    service: Service = Depends(get_service),
) -> Result[ResourceTypes]:
    """Get the datasource types."""
    return Result.succ(service.datasource_types())


@router.post(
    "/datasources/test-connection",
    dependencies=[Depends(check_api_key)],
    response_model=Result[bool],
)
async def test_connection(
    request: DatasourceCreateRequest, service: Service = Depends(get_service)
) -> Result[bool]:
    """Test the connection using datasource configuration before creating it

    Args:
        request (DatasourceServeRequest): The datasource configuration to test
        service (Service): The service instance

    Returns:
        Result[bool]: The test result, True if connection is successful

    Raises:
        HTTPException: When the connection test fails
    """
    res = await blocking_func_to_async(
        global_system_app, service.test_connection, request
    )
    return Result.succ(res)


@router.post(
    "/datasources/{datasource_id}/refresh",
    dependencies=[Depends(check_api_key)],
    response_model=Result[bool],
)
async def refresh_datasource(
    datasource_id: str, service: Service = Depends(get_service)
) -> Result[bool]:
    """Refresh a datasource by its ID

    Args:
        datasource_id (str): The ID of the datasource to refresh
        service (Service): The service instance

    Returns:
        Result[bool]: The refresh result, True if the refresh was successful

    Raises:
        HTTPException: When the refresh operation fails
    """
    res = await blocking_func_to_async(
        global_system_app, service.refresh, datasource_id
    )
    return Result.succ(res)


# ============================================================
# Database Spec & Learning Endpoints
# ============================================================


@router.post(
    "/datasources/{datasource_id}/learn",
    dependencies=[Depends(check_api_key)],
    response_model=Result[LearningTaskResponse],
)
async def trigger_learning(
    datasource_id: str,
    request: Optional[LearningTaskRequest] = None,
    service: Service = Depends(get_service),
) -> Result[LearningTaskResponse]:
    """Trigger a schema learning task for a datasource.

    Args:
        datasource_id: The datasource ID.
        request: Optional learning task parameters.
        service: The service instance.
    """
    task_type = request.task_type if request else "full_learn"
    table_name = request.table_name if request else None

    result = await blocking_func_to_async(
        global_system_app,
        service.trigger_learning,
        datasource_id,
        task_type,
        table_name,
    )
    return Result.succ(LearningTaskResponse(**result))


@router.get(
    "/datasources/{datasource_id}/learn/status",
    dependencies=[Depends(check_api_key)],
    response_model=Result[Optional[LearningTaskResponse]],
)
async def get_learning_status(
    datasource_id: str,
    service: Service = Depends(get_service),
) -> Result[Optional[LearningTaskResponse]]:
    """Get the current learning task status for a datasource."""
    result = service.get_learning_status(datasource_id)
    if result:
        return Result.succ(LearningTaskResponse(**result))
    return Result.succ(None)


@router.get(
    "/datasources/{datasource_id}/spec",
    dependencies=[Depends(check_api_key)],
    response_model=Result[Optional[DbSpecResponse]],
)
async def get_db_spec(
    datasource_id: str,
    service: Service = Depends(get_service),
) -> Result[Optional[DbSpecResponse]]:
    """Get the database-level spec document for a datasource."""
    result = service.get_db_spec(datasource_id)
    if result:
        return Result.succ(DbSpecResponse(**result))
    return Result.succ(None)


@router.get(
    "/datasources/{datasource_id}/tables",
    dependencies=[Depends(check_api_key)],
    response_model=Result[List[TableSpecSummaryResponse]],
)
async def get_table_specs(
    datasource_id: str,
    service: Service = Depends(get_service),
) -> Result[List[TableSpecSummaryResponse]]:
    """Get all table spec summaries for a datasource."""
    results = service.get_all_table_specs(datasource_id)
    summaries = []
    for r in results:
        columns = r.get("columns", [])
        summaries.append(
            TableSpecSummaryResponse(
                table_name=r.get("table_name", ""),
                table_comment=r.get("table_comment"),
                row_count=r.get("row_count"),
                column_count=len(columns) if columns else 0,
                group_name=r.get("group_name"),
            )
        )
    return Result.succ(summaries)


@router.get(
    "/datasources/{datasource_id}/tables/{table_name}",
    dependencies=[Depends(check_api_key)],
    response_model=Result[Optional[TableSpecDetailResponse]],
)
async def get_table_spec_detail(
    datasource_id: str,
    table_name: str,
    service: Service = Depends(get_service),
) -> Result[Optional[TableSpecDetailResponse]]:
    """Get detailed table spec for a specific table."""
    result = service.get_table_spec(datasource_id, table_name)
    if result:
        return Result.succ(TableSpecDetailResponse(**result))
    return Result.succ(None)


@router.post(
    "/datasources/{datasource_id}/tables/batch",
    dependencies=[Depends(check_api_key)],
    response_model=Result[List[TableSpecDetailResponse]],
)
async def get_table_specs_batch(
    datasource_id: str,
    request: BatchTableRequest,
    service: Service = Depends(get_service),
) -> Result[List[TableSpecDetailResponse]]:
    """Get multiple table specs at once."""
    results = service.get_table_specs_batch(datasource_id, request.table_names)
    return Result.succ([TableSpecDetailResponse(**r) for r in results])


@router.get(
    "/datasources/{datasource_id}/tables/{table_name}/data",
    dependencies=[Depends(check_api_key)],
    response_model=Result[TableDataPreviewResponse],
)
async def preview_table_data(
    datasource_id: str,
    table_name: str,
    service: Service = Depends(get_service),
) -> Result[TableDataPreviewResponse]:
    """Preview table  first 5 rows + last 5 rows."""
    result = await blocking_func_to_async(
        global_system_app,
        service.preview_table_data,
        datasource_id,
        table_name,
    )
    return Result.succ(TableDataPreviewResponse(**result))


def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints"""
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app
