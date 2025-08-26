# Define your Pydantic schemas here
from datetime import datetime
from typing import Any, Dict, Optional, Union

from derisk._private.pydantic import BaseModel, ConfigDict, model_to_dict
from derisk._private.pydantic import BaseModel, Field
from ..config import SERVE_APP_NAME_HUMP




class ServeRequest(BaseModel):
    """Building/recommendQuestion request model"""

    id: Optional[int] = Field(None, description="id")
    app_code: Optional[str] = Field(None, description="The unique identify of app")
    question: Optional[str] = Field(None, description="The question you may ask")
    user_code: Optional[str] = Field(None, description="The user code")
    sys_code: Optional[str] = Field(None, description="The system code")
    gmt_create: datetime = datetime.now()
    gmt_modified: datetime = datetime.now()
    params: Optional[dict] = Field(default={}, description="The params of app")
    valid: Optional[Union[str, bool]] = Field(
        default=None, description="is the question valid to display, default is true"
    )
    chat_mode: Optional[str] = Field(
        default=None, description="is the question valid to display, default is true"
    )
    is_hot_question: Optional[str] = Field(default=None, description="is hot question.")

    model_config = ConfigDict(title=f"ServeRequest for {SERVE_APP_NAME_HUMP}")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(
            id=d["id"],
            app_code=d.get("app_code", None),
            question=d.get("question", None),
            user_code=str(d.get("user_code", None)),
            sys_code=d.get("sys_code", None),
            gmt_create=d.get("gmt_create", None),
            updated_at=d.get("updated_at", None),
            gmt_modified=d.get("gmt_modified", None),
            params=d.get("params", None),
            valid=d.get("valid", False),
            chat_mode=d.get("chat_mode", None),
            is_hot_question=d.get("is_hot_question", False),
        )


ServerResponse = ServeRequest
