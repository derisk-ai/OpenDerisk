# Define your Pydantic schemas here
from datetime import datetime
from typing import Any, Dict, Optional

from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict, Field

from ..config import SERVE_APP_NAME_HUMP


class ServeRequest(BaseModel):
    """Config request model"""
    id: Optional[int] = Field(
        None,
        description="The id of the variable",
        examples=[1],
    )
    name: str
    value: str
    type: Optional[str] = "string"
    valid_time: Optional[int] = None
    operator: Optional[str] = None
    creator: Optional[str] = None
    version: Optional[str] = None
    category: Optional[str] = None
    upload_cls: Optional[str] = None
    upload_instance: Optional[str] = None
    upload_stamp: Optional[int] = None
    upload_param: Optional[str] = None
    upload_retry: Optional[int] = None

    gmt_created: Optional[datetime] = None
    gmt_modified: Optional[datetime] = None

    model_config = ConfigDict(title=f"ServeRequest for {SERVE_APP_NAME_HUMP}")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


ServerResponse = ServeRequest
