import json
from datetime import datetime
from typing import Union, Dict, Any

from sqlalchemy import Column, DateTime, Integer, String, Text

from derisk.storage.metadata import BaseDao, Model
from derisk_serve.rag.api.rag_flow_schema import RagFlowSpanResponse, RagFlowSpanRequest


class RagFlowSpan(Model):
    __tablename__ = "rag_flow_span"
    id = Column(Integer, primary_key=True)
    span_id = Column(String(100))
    span_type = Column(String(100))
    trace_id = Column(String(100))
    app_code = Column(String(100))
    conv_id = Column(String(100))
    message_id = Column(String(100))
    input = Column(Text)
    output = Column(Text)
    start_time = Column(String(500))
    end_time = Column(String(500))
    node_name = Column(String(500))
    node_type = Column(String(500))
    gmt_create = Column(DateTime, default=datetime.now)
    gmt_modified = Column(DateTime, default=datetime.now)


class RagFlowSpanDao(BaseDao):
    """RagFlowSpanDao class for managing RAG flow spans."""

    def from_request(
        self, request: Union[RagFlowSpanRequest, Dict[str, Any]]
    ) -> RagFlowSpan:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        request_dict = (
            request.dict() if isinstance(request, RagFlowSpanRequest) else request
        )
        if request_dict.get("input") is not None:
            request_dict["input"] = json.dumps(
                request_dict["input"], ensure_ascii=False
            )
        if request_dict.get("output") is not None:
            request_dict["output"] = json.dumps(
                request_dict["output"], ensure_ascii=False
            )
        entity = RagFlowSpan(**request_dict)
        return entity

    def to_request(self, entity: RagFlowSpan) -> RagFlowSpanRequest:
        """Convert the entity to a request

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return RagFlowSpanRequest(
            id=entity.id,
            span_id=entity.span_id,
            span_type=entity.span_type,
            trace_id=entity.trace_id,
            app_code=entity.app_code,
            conv_id=entity.conv_id,
            message_id=entity.message_id,
            node_type=entity.node_type,
            node_name=entity.node_name,
            input=json.loads(entity.input) if entity.input else None,
            output=json.loads(entity.output) if entity.output else None,
            start_time=entity.start_time,
            end_time=entity.end_time,
        )

    def to_response(self, entity: RagFlowSpan) -> RagFlowSpanResponse:
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            REQ: The request
        """
        return RagFlowSpanResponse(
            id=entity.id,
            span_id=entity.span_id,
            span_type=entity.span_type,
            trace_id=entity.trace_id,
            conv_id=entity.conv_id,
            app_code=entity.app_code,
            message_id=entity.message_id,
            node_type=entity.node_type,
            node_name=entity.node_name,
            input=json.loads(entity.input) if entity.input else None,
            output=json.loads(entity.output) if entity.output else None,
            start_time=entity.start_time,
            end_time=entity.end_time,
        )

    def from_response(
        self, response: Union[RagFlowSpanResponse, Dict[str, Any]]
    ) -> RagFlowSpan:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """
        response_dict = (
            response.dict() if isinstance(response, RagFlowSpanResponse) else response
        )
        response_dict["input"] = json.dumps(response_dict["input"], ensure_ascii=False)
        response_dict["output"] = json.dumps(
            response_dict["output"], ensure_ascii=False
        )
        entity = RagFlowSpan(**response_dict)
        return entity
