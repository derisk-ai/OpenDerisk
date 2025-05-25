from typing import List

from derisk import SystemApp
from derisk.component import logger
from derisk.util.tracer import Span, MemorySpanStorage
from derisk_serve.rag.models.rag_span_db import RagFlowSpanDao


class RagFlowSpanStorage(MemorySpanStorage):
    """Derisk RAG flow span storage.

    This class is used to store the spans of the Derisk RAG flow.
    """

    def __init__(self, system_app=None):
        super().__init__(system_app)
        self.rag_flow_trace = {}
        self.rag_span_dao = RagFlowSpanDao()

    def init_app(self, system_app: SystemApp):
        """Initialize the app."""
        self.system_app = system_app

    def append_span(self, span: Span):
        """Append a span to the storage.

        Args:
            span (Span): The span to be appended.
        """
        if span.metadata:
            dag_spans = span.metadata.get("dag_tags")
            if dag_spans:
                print(span.metadata)

    def append_span_batch(self, spans: List[Span]):
        for span in spans:
            if span.metadata and span.end_time:
                if span.metadata.get("rag_span_type") == "knowledge_retrieve":
                    self.rag_flow_trace = {
                        "message_id": span.metadata.get("message_id"),
                        "conv_id": span.metadata.get("conv_id"),
                        "app_code": span.metadata.get("app_code"),
                        "trace_id": span.trace_id,
                    }
                if span.metadata.get("dag_tags"):
                    if not self.rag_flow_trace.get("message_id"):
                        dag_spans = span.metadata.get("dag_tags")
                        if dag_spans:
                            self.rag_flow_trace = {
                                "input": span.metadata.get("task_input"),
                                "output": span.metadata.get("task_output"),
                            }
                    else:
                        dag_spans = span.metadata.get("dag_tags")
                        if dag_spans:
                            previous_output = self.rag_flow_trace.get("output")
                            output = span.metadata.get("task_output")

                            from derisk_serve.rag.api.schemas import (
                                KnowledgeSearchResponse,
                            )

                            input_dict = (
                                previous_output.dict()
                                if isinstance(previous_output, KnowledgeSearchResponse)
                                else previous_output
                            )
                            output_dict = (
                                output.dict()
                                if isinstance(output, KnowledgeSearchResponse)
                                else output
                            )
                            self.rag_flow_trace.update(
                                {
                                    "input": input_dict,
                                    "output": output_dict,
                                    "span_id": span.span_id,
                                    "start_time": span.start_time.strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                    "end_time": span.end_time.strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                    "span_type": span.span_type,
                                    "node_name": span.metadata.get("awel_node_name"),
                                    "node_type": span.metadata.get("awel_node_type"),
                                }
                            )
                            rag_span = self.rag_span_dao.get_one(
                                {"span_id": span.span_id}
                            )
                            if not rag_span:
                                try:
                                    logger.info(
                                        f"knowledge rag_flow_trace:"
                                        f"{self.rag_flow_trace}"
                                    )
                                    self.rag_span_dao.create(self.rag_flow_trace)
                                    logger.info(
                                        f"knowledge rag_flow_span {span.span_id}"
                                        f"persist success"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"knowledge rag_flow_span {span.span_id}"
                                        f"persist error: {e}"
                                    )
