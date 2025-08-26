# Define your Pydantic schemas here
from typing import Any, Dict, Optional, List
from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict, Field
from .schema_app import GptsApp

from ..config import SERVE_APP_NAME_HUMP


class ServeRequest(GptsApp):
    """App request model"""

    model_config = ConfigDict(title=f"ServeRequest for {SERVE_APP_NAME_HUMP}")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


ServerResponse = ServeRequest

class AppConfigPubilsh(BaseModel):
    app_code: str = Field(..., max_length=255, description="应用代码")
    config_code: str = Field(..., max_length=255, description="要发布配置的代码")
    operator: Optional[str] = Field(None, max_length=255, description="发布配置的操作人")
    description: Optional[str] = Field(None, max_length=255, description="本次发布备注")


    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)

