# Define your Pydantic schemas here
from typing import Any, Dict, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, Field, model_to_dict

from ..config import SERVE_APP_NAME_HUMP


class ServeRequest(BaseModel):
    """DerisksHub request model"""

    id: Optional[int] = Field(None, description="id")
    name: Optional[str] = Field(None, description="Derisks name")
    type: Optional[str] = Field(None, description="Derisks type")
    version: Optional[str] = Field(None, description="Derisks version")
    description: Optional[str] = Field(None, description="Derisks description")
    author: Optional[str] = Field(None, description="Derisks author")
    email: Optional[str] = Field(None, description="Derisks email")
    storage_channel: Optional[str] = Field(None, description="Derisks storage channel")
    storage_url: Optional[str] = Field(None, description="Derisks storage url")
    download_param: Optional[str] = Field(None, description="Derisks download param")
    installed: Optional[int] = Field(None, description="Derisks installed")

    model_config = ConfigDict(title=f"ServeRequest for {SERVE_APP_NAME_HUMP}")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class ServerResponse(ServeRequest):
    gmt_created: Optional[str] = Field(None, description="Derisks create time")
    gmt_modified: Optional[str] = Field(None, description="Derisks upload time")
