from typing import Optional, Union, List

from derisk._private.pydantic import BaseModel, Field


class RagFlowSpanRequest(BaseModel):
    """Rag flow span request"""

    id: Optional[int] = Field(None, description="The primary id")
    span_id: Optional[str] = Field(None, description="The span id")
    span_type: Optional[str] = Field(None, description="The span type")
    trace_id: Optional[str] = Field(None, description="The trace id")
    conv_id: Optional[str] = Field(None, description="The conversation id")
    message_id: Optional[str] = Field(None, description="The message id")
    input: Optional[Union[str, List, dict]] = Field(None, description="The input")
    output: Optional[Union[str, List, dict]] = Field(None, description="The output")
    start_time: Optional[str] = Field(None, description="The start time")
    end_time: Optional[str] = Field(None, description="The end time")
    node_name: Optional[str] = Field(None, description="The node name")
    node_type: Optional[str] = Field(None, description="The node type")
    gmt_create: Optional[str] = Field(None, description="The created time")
    gmt_modified: Optional[str] = Field(None, description="The modified time")


class RagFlowSpanResponse(BaseModel):
    """Rag flow span response"""

    id: Optional[int] = Field(None, description="The primary id")
    span_id: Optional[str] = Field(None, description="The span id")
    span_type: Optional[str] = Field(None, description="The span type")
    trace_id: Optional[str] = Field(None, description="The trace id")
    conv_id: Optional[str] = Field(None, description="The conversation id")
    message_id: Optional[str] = Field(None, description="The message id")
    input: Optional[Union[str, List, dict]] = Field(None, description="The input")
    output: Optional[Union[str, List, dict]] = Field(None, description="The output")
    start_time: Optional[str] = Field(None, description="The start time")
    end_time: Optional[str] = Field(None, description="The end time")
    node_name: Optional[str] = Field(None, description="The node name")
    node_type: Optional[str] = Field(None, description="The node type")
    gmt_create: Optional[str] = Field(None, description="The created time")
    gmt_modified: Optional[str] = Field(None, description="The modified time")
