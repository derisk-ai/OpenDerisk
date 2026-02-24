from typing import Dict, Any

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_to_json,
    model_validator,
    model_to_dict,
    Extra
)


class DrskVisBase(BaseModel):
    class Config:
        extra = Extra.ignore

    uid: str = Field(..., description="drsk drsk_vis compent uid")
    type: str = Field(..., description="drsk drsk_vis data update type")
    dynamic: bool = Field(False, description="is a dynamic  compontent")

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)
