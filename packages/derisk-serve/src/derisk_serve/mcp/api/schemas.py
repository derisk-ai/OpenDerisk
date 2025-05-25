import json
from datetime import datetime
from typing import Any, Dict, Optional, Union

from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_to_dict

from ..config import SERVE_APP_NAME_HUMP


# ------------------------ Request Model ------------------------
class ServeRequest(BaseModel):
    """Mcp request model"""

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="mcp name")
    description: Optional[str] = Field(None, min_length=1, description="mcp description")
    type: Optional[str] = Field(None, min_length=1, max_length=255, description="mcp type")
    author: Optional[str] = Field(None, max_length=255, description="mcp author")
    email: Optional[str] = Field(None, max_length=255, description="mcp author email")

    version: Optional[str] = Field(None, max_length=255, description="mcp version")
    stdio_cmd: Optional[str] = Field(None, description="mcp stdio cmd")
    sse_url: Optional[str] = Field(None, description="mcp sse connect url")
    sse_headers: Optional[Dict[str, str]] = Field(None, description="mcp sse connect headers (auto-convert to JSON)")
    token: Optional[str] = Field(None, description="mcp sse connect token")
    icon: Optional[str] = Field(None, description="mcp icon")
    category: Optional[str] = Field(None, description="mcp category")
    installed: Optional[int] = Field(None, ge=0, description="mcp installed count")
    available: Optional[bool] = Field(None, description="mcp availability status")

    model_config = ConfigDict(
        title=f"ServeRequest for {SERVE_APP_NAME_HUMP}",
        json_schema_extra={
            "example": {
                "name": "my-service",
                "description": "A sample microservice",
                "type": "cloud-native",
                "version": "1.0.0"
            }
        }
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary with JSON handling"""
        return model_to_dict(self, **kwargs)


# ------------------------ Response Model ------------------------
class ServerResponse(BaseModel):
    """Mcp response model"""

    id: int = Field(..., description="Auto increment id")
    name: str = Field(..., description="mcp name")
    description: str = Field(..., description="mcp description")
    type: str = Field(..., description="mcp type")
    author: Optional[str] = Field(None, description="mcp author")
    email: Optional[str] = Field(None, description="mcp author email")

    version: Optional[str] = Field(None, description="mcp version")
    stdio_cmd: Optional[str] = Field(None, description="mcp stdio cmd")
    sse_url: Optional[str] = Field(None, description="mcp sse connect url")
    sse_headers: Optional[Dict[str, str]] = Field(None, description="mcp sse connect headers")
    token: Optional[str] = Field(None, description="mcp sse connect token")
    icon: Optional[str] = Field(None, description="mcp icon")
    category: Optional[str] = Field(None, description="mcp category")
    installed: Optional[int] = Field(None, description="mcp installed count")
    available: Optional[bool] = Field(None, description="mcp availability status")
    server_ips: Optional[str] = Field(None, description="mcp server run machine ips")

    gmt_created: str = Field(..., description="ISO format creation time")
    gmt_modified: str = Field(..., description="ISO format modification time")

    model_config = ConfigDict(
        title=f"ServerResponse for {SERVE_APP_NAME_HUMP}",
        json_encoders={datetime: lambda dt: dt.isoformat()},
        from_attributes=True
    )

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a API-safe dictionary"""
        return model_to_dict(
            self,
            exclude_none=True,
            by_alias=True,
            **kwargs
        )

    @classmethod
    def parse_database_model(cls, entity: Any) -> 'ServerResponse':
        """Alternative constructor for database model conversion"""
        model_dict = entity.__dict__

        # Handle JSON fields
        model_dict['sse_headers'] = json.loads(model_dict['sse_headers'])

        # Convert datetime to ISO strings
        for time_field in ['gmt_created', 'gmt_modified']:
            if isinstance(model_dict.get(time_field), datetime):
                model_dict[time_field] = model_dict[time_field].isoformat()

        return cls(**model_dict)


class McpRunRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="mcp name")

    stdio_cmd: Optional[str] = Field(None, description="mcp stdio cmd")
    sse_url: Optional[str] = Field(None, description="mcp sse connect url")
    sse_headers: Optional[Dict[str, str]] = Field(None, description="mcp sse connect headers (auto-convert to JSON)")
    token: Optional[str] = Field(None, description="mcp sse connect token")

    method: Optional[str] = Field(None, description="mcp sse call method")
    params: Optional[dict[str, Any]] = Field(None, description="mcp tool call params")


class McpTool(BaseModel):
    name: str = Field(..., description="mcp tool name")
    description: str = Field(..., description="mcp tool description")
    param_schema: Optional[Any] = Field(None, description="mcp tool param schema")


class QueryFilter(BaseModel):
    filter: str = Field(None, description="mcp tool name")
