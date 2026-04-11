from typing import Any, Dict, List, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field

from ..config import SERVE_APP_NAME_HUMP


class DatasourceServeRequest(BaseModel):
    """name: knowledge space name"""

    """vector_type: vector type"""
    id: Optional[int] = Field(None, description="The datasource id")
    db_type: str = Field(..., description="Database type, e.g. sqlite, mysql, etc.")
    db_name: str = Field(..., description="Database name.")
    db_path: Optional[str] = Field("", description="File path for file-based database.")
    db_host: Optional[str] = Field("", description="Database host.")
    db_port: Optional[int] = Field(0, description="Database port.")
    db_user: Optional[str] = Field("", description="Database user.")
    db_pwd: Optional[str] = Field("", description="Database password.")
    comment: Optional[str] = Field("", description="Comment for the database.")
    ext_config: Optional[Dict[str, Any]] = Field(
        None, description="Extra configuration for the datasource."
    )


class DatasourceServeResponse(BaseModel):
    """Flow response model"""

    model_config = ConfigDict(title=f"ServeResponse for {SERVE_APP_NAME_HUMP}")

    """name: knowledge space name"""

    """vector_type: vector type"""
    id: int = Field(None, description="The datasource id")
    db_type: str = Field(..., description="Database type, e.g. sqlite, mysql, etc.")
    db_name: str = Field(..., description="Database name.")
    db_path: Optional[str] = Field("", description="File path for file-based database.")
    db_host: Optional[str] = Field("", description="Database host.")
    db_port: Optional[int] = Field(0, description="Database port.")
    db_user: Optional[str] = Field("", description="Database user.")
    db_pwd: Optional[str] = Field("", description="Database password.")
    comment: Optional[str] = Field("", description="Comment for the database.")
    ext_config: Optional[Dict[str, Any]] = Field(
        None, description="Extra configuration for the datasource."
    )

    gmt_created: Optional[str] = Field(
        None,
        description="The datasource created time.",
        examples=["2021-08-01 12:00:00", "2021-08-01 12:00:01", "2021-08-01 12:00:02"],
    )
    gmt_modified: Optional[str] = Field(
        None,
        description="The datasource modified time.",
        examples=["2021-08-01 12:00:00", "2021-08-01 12:00:01", "2021-08-01 12:00:02"],
    )


class DatasourceCreateRequest(BaseModel):
    """Request model for datasource connection

    Attributes:
        type (str): The type of datasource (e.g., "mysql", "tugraph")
        params (Dict[str, Any]): Dynamic parameters for the datasource connection.
            The keys should match the param_name defined in the datasource type
            configuration.
    """

    type: str = Field(
        ..., description="The type of datasource (e.g., 'mysql', 'tugraph')"
    )
    params: Dict[str, Any] = Field(
        ..., description="Dynamic parameters for the datasource connection."
    )
    description: Optional[str] = Field(
        None, description="Optional description of the datasource."
    )
    id: Optional[int] = Field(None, description="The datasource id")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "tugraph",
                "params": {
                    "host": "localhost",
                    "user": "test_user",
                    "password": "test_password",
                    "port": 7687,
                    "database": "default",
                },
            }
        }


class DatasourceQueryResponse(DatasourceCreateRequest):
    """Response model for datasource query"""

    db_name: Optional[str] = Field(
        None,
        description="The unique database name stored in connect_config.",
    )
    gmt_created: Optional[str] = Field(
        None,
        description="The datasource created time.",
        examples=["2021-08-01 12:00:00", "2021-08-01 12:00:01", "2021-08-01 12:00:02"],
    )
    gmt_modified: Optional[str] = Field(
        None,
        description="The datasource modified time.",
        examples=["2021-08-01 12:00:00", "2021-08-01 12:00:01", "2021-08-01 12:00:02"],
    )


# ============================================================
# Database Spec & Learning API Schemas
# ============================================================


class LearningTaskRequest(BaseModel):
    """Request to trigger a database schema learning task."""

    task_type: str = Field(
        "full_learn",
        description="Task type: 'full_learn', 'incremental', or 'single_table'.",
    )
    table_name: Optional[str] = Field(
        None,
        description="Table name (required when task_type is 'single_table').",
    )


class LearningTaskResponse(BaseModel):
    """Response for a learning task status."""

    id: int = Field(..., description="Learning task ID")
    datasource_id: int = Field(..., description="Datasource ID")
    task_type: str = Field(..., description="Task type")
    status: str = Field(
        ..., description="Status: pending, running, completed, failed"
    )
    progress: int = Field(0, description="Progress percentage 0-100")
    total_tables: Optional[int] = Field(None, description="Total tables to process")
    processed_tables: int = Field(0, description="Tables processed so far")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    trigger_type: str = Field("manual", description="How the task was triggered")
    gmt_created: Optional[str] = Field(None, description="Task creation time")
    gmt_modified: Optional[str] = Field(None, description="Task last modified time")


class DbSpecResponse(BaseModel):
    """Response for a database-level spec document."""

    datasource_id: int = Field(..., description="Datasource ID")
    db_name: str = Field(..., description="Database name")
    db_type: str = Field(..., description="Database type")
    table_count: Optional[int] = Field(None, description="Total number of tables")
    spec_content: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Table index: list of {table_name, summary, row_count, group}",
    )
    group_config: Optional[Dict[str, Any]] = Field(
        None, description="Table grouping configuration"
    )
    status: str = Field(..., description="Status: ready, generating, failed")
    gmt_created: Optional[str] = Field(None, description="Spec creation time")
    gmt_modified: Optional[str] = Field(None, description="Spec last modified time")


class TableSpecSummaryResponse(BaseModel):
    """Summary response for a table spec (used in list views)."""

    table_name: str = Field(..., description="Table name")
    table_comment: Optional[str] = Field(None, description="Table comment")
    row_count: Optional[int] = Field(None, description="Approximate row count")
    column_count: int = Field(0, description="Number of columns")
    group_name: Optional[str] = Field(None, description="Group name")


class TableSpecDetailResponse(BaseModel):
    """Detailed response for a single table spec."""

    table_name: str = Field(..., description="Table name")
    table_comment: Optional[str] = Field(None, description="Table comment")
    row_count: Optional[int] = Field(None, description="Approximate row count")
    columns: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Column definitions: name, type, nullable, default, comment, pk",
    )
    indexes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Index definitions: name, columns, unique",
    )
    foreign_keys: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Foreign key definitions: constrained_columns, referred_table, referred_columns",
    )
    create_ddl: Optional[str] = Field(None, description="CREATE TABLE DDL statement")
    group_name: Optional[str] = Field(None, description="Group name")
    gmt_created: Optional[str] = Field(None, description="Spec creation time")
    gmt_modified: Optional[str] = Field(None, description="Spec last modified time")


class BatchTableRequest(BaseModel):
    """Request to fetch multiple table specs at once."""

    table_names: List[str] = Field(
        ..., description="List of table names to retrieve."
    )


class TableDataPreviewResponse(BaseModel):
    """Response for table data preview (first 5 + last 5 rows)."""

    columns: List[str] = Field(default_factory=list, description="Column names")
    first_rows: List[List[Any]] = Field(default_factory=list, description="First 5 rows")
    last_rows: List[List[Any]] = Field(default_factory=list, description="Last 5 rows")
    total: int = Field(0, description="Total row count")


# ==============================================================
# File Learning Schemas
# ==============================================================


class SchemaFileUploadResponse(BaseModel):
    """Response for schema file upload."""

    file_id: str = Field(..., description="Unique file identifier")
    file_path: str = Field(..., description="Server-side file path")
    file_type: str = Field(..., description="Detected file type (pdm, ddl, pdman)")
    original_name: str = Field(..., description="Original filename")


class ParsedTablePreview(BaseModel):
    """Preview info for a parsed table."""

    name: str = Field(..., description="Table name")
    comment: Optional[str] = Field(None, description="Table comment")
    column_count: int = Field(0, description="Number of columns")
    has_fk: bool = Field(False, description="Has foreign keys")


class SchemaFilePreviewResponse(BaseModel):
    """Response for schema file preview."""

    tables: List[ParsedTablePreview] = Field(
        default_factory=list, description="Parsed tables"
    )
    views: List[ParsedTablePreview] = Field(
        default_factory=list, description="Parsed views"
    )
    source_type: str = Field(..., description="Source file type")
    total_count: int = Field(0, description="Total tables/views count")


class FileLearningRequest(BaseModel):
    """Request for file-based schema learning."""

    datasource_id: int = Field(
        ..., description="ID of datasource to link for sample data"
    )
    file_type: Optional[str] = Field(
        None, description="Override file type detection"
    )
    options: Optional[Dict[str, Any]] = Field(
        None, description="Additional learning options"
    )


class FailedTableInfo(BaseModel):
    """Info about a failed table during learning."""

    table_name: str = Field(..., description="Table name")
    error: str = Field(..., description="Error message")


class FileLearningResponse(BaseModel):
    """Response for file-based schema learning."""

    datasource_id: int = Field(..., description="Linked datasource ID")
    source_file: str = Field(..., description="Source file path")
    source_type: str = Field(..., description="Source file type")
    total_tables: int = Field(0, description="Total tables in file")
    processed_tables: int = Field(0, description="Successfully processed tables")
    failed_tables: List[FailedTableInfo] = Field(
        default_factory=list, description="Failed tables"
    )
    status: str = Field(
        ..., description="Learning status: completed, partial, or failed"
    )


class SupportedFileType(BaseModel):
    """Info about a supported file type."""

    type: str = Field(..., description="Type identifier")
    description: str = Field(..., description="Human-readable description")
    extensions: List[str] = Field(
        default_factory=list, description="Supported file extensions"
    )
