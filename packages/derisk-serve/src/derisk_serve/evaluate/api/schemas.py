# Define your Pydantic schemas here
from enum import Enum
from typing import Any, Dict, Optional, List
from derisk._private.pydantic import BaseModel, Field

from derisk._private.pydantic import BaseModel, model_to_dict

from ..config import SERVE_APP_NAME_HUMP

class EvaluationScene(Enum):
    OPENRCA = "openrca" 
    RECALL = "recall"

class ServeRequest(BaseModel):
    """Evaluate request model"""

    # TODO define your own fields here
    evaluate_code: Optional[str] = Field(None, description="Evaluation code") 
    scene_key: Optional[str] = Field(None, description="evaluation scene key")
    scene_value: Optional[str] = Field(None, description="evaluation scene value")
    datasets_name: Optional[str] = Field(None, description="evaluation datasets name")
    datasets: Optional[List[dict]] = Field(None, description="evaluation datasets")
    evaluate_metrics: Optional[List[str]] = Field(
        None, description="evaluation metrics to use"
    )
    context: Optional[dict] = Field(None, description="The context of the evaluate")
    user_name: Optional[str] = Field(None, description="user name")
    user_id: Optional[str] = Field(None, description="user id")
    sys_code: Optional[str] = Field(None, description="system code")
    parallel_num: Optional[int] = Field(None, description="parallel number for evaluation")
    state: Optional[str] = Field(None, description="state of the evaluation")
    result: Optional[List[dict]] = Field(None, description="evaluation result")
    storage_type: Optional[str] = Field(None, description="datasets storage type")
    average_score: Optional[float] = Field(None, description="average score of the evaluation")
    log_info: Optional[str] = Field(None, description="evaluation log info")
    gmt_create: Optional[str] = Field(None, description="record creation time")
    gmt_modified: Optional[str] = Field(None, description="record update time") 

    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)


class ServerResponse(ServeRequest):
    """Evaluate response model"""

    # TODO define your own fields here
    
    class Config:
        title = f"Server Response for {SERVE_APP_NAME_HUMP}"
    
    def to_dict(self, **kwargs) -> Dict[str, Any]:
        """Convert the model to a dictionary"""
        return model_to_dict(self, **kwargs)
