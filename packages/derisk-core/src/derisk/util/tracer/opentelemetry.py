"""Enhanced OpenTelemetry span storage for OpenDerisk.

Converts internal Derisk spans into OpenTelemetry spans with:
- Semantic conventions (HTTP, GenAI/LLM, Agent)
- Proper SpanKind mapping (SERVER, CLIENT, INTERNAL)
- Span Events for errors and key lifecycle moments
- Span Status (OK / ERROR)
- Rich Resource attributes (service.name, service.version, etc.)
- Support for both OTLP/gRPC and OTLP/HTTP exporters
- Console exporter for local development
- Stale span cleanup to prevent memory leaks
"""

import logging
import os
import platform
import threading
import time
from typing import Dict, List, Optional

from .base import Span, SpanStorage, SpanType, SpanTypeRunName, _split_span_id

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as OTLPGrpcExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import Span as OTSpan
    from opentelemetry.sdk.trace import StatusCode, TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.trace import SpanContext, SpanKind

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Try to import HTTP exporter as an alternative
OTEL_HTTP_AVAILABLE = False
if OTEL_AVAILABLE:
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as OTLPHttpExporter,
        )

        OTEL_HTTP_AVAILABLE = True
    except ImportError:
        pass

# ---------------------------------------------------------------------------
# Semantic convention attribute names
# Following OpenTelemetry Semantic Conventions:
# https://opentelemetry.io/docs/specs/semconv/
# ---------------------------------------------------------------------------

# HTTP semantic conventions
_HTTP_METHOD = "http.request.method"
_HTTP_ROUTE = "http.route"
_HTTP_STATUS_CODE = "http.response.status_code"
_URL_PATH = "url.path"

# GenAI / LLM semantic conventions (experimental)
# https://opentelemetry.io/docs/specs/semconv/gen-ai/
_GEN_AI_SYSTEM = "gen_ai.system"
_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
_GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
_GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
_GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
_GEN_AI_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"

# Derisk-specific attributes (prefixed with derisk.*)
_DERISK_TRACE_ID = "derisk.trace_id"
_DERISK_SPAN_ID = "derisk.span_id"
_DERISK_PARENT_SPAN_ID = "derisk.parent_span_id"
_DERISK_SPAN_TYPE = "derisk.span_type"
_DERISK_CONV_UID = "derisk.conversation.uid"
_DERISK_AGENT_NAME = "derisk.agent.name"
_DERISK_TOOL_NAME = "derisk.tool.name"
_DERISK_MODEL_PATH = "derisk.model.path"
_DERISK_MODEL_TYPE = "derisk.model.type"
_DERISK_LLM_LATENCY_MS = "derisk.llm.latency_ms"
_DERISK_LLM_FIRST_TOKEN_MS = "derisk.llm.first_token_latency_ms"
_DERISK_LLM_SPEED = "derisk.llm.speed_per_second"

# Stale span TTL: spans older than this are cleaned up (seconds)
_STALE_SPAN_TTL = 600


class OpenTelemetrySpanStorage(SpanStorage):
    """Enhanced OpenTelemetry span storage with semantic conventions.

    Converts internal Derisk spans into standards-compliant OpenTelemetry
    spans. Supports both auto-discovery via model_scan and manual
    instantiation.

    Key improvements over the original implementation:
    - SpanKind mapping: SERVER for HTTP entry, CLIENT for LLM calls,
      INTERNAL for agent/tool operations
    - Semantic conventions: standard attribute names for HTTP, GenAI/LLM
    - Span Events: error details, LLM token usage events
    - Span Status: OK for successful spans, ERROR for failed ones
    - Resource attributes: service.name, service.version,
      deployment.environment
    - Multiple exporter support: OTLP/gRPC, OTLP/HTTP, Console
    - Stale span cleanup: prevents memory leaks from orphaned spans
    """

    name = "opentelemetry_span_storage"

    def __init__(
        self,
        system_app=None,
        tracer_parameters=None,
        service_name: Optional[str] = None,
        otlp_endpoint: Optional[str] = None,
        otlp_insecure: Optional[bool] = None,
        otlp_timeout: Optional[int] = None,
    ):
        super().__init__(system_app)

        if not OTEL_AVAILABLE:
            logger.info(
                "opentelemetry packages not installed, "
                "OpenTelemetrySpanStorage will be disabled. "
                "Install via: pip install opentelemetry-api "
                "opentelemetry-sdk opentelemetry-exporter-otlp"
            )
            self._enabled = False
            return

        # Resolve configuration: explicit args > tracer_parameters > env
        resolved_endpoint = self._resolve_config(
            tracer_parameters, "otlp_endpoint", otlp_endpoint,
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        )
        resolved_insecure = self._resolve_config(
            tracer_parameters, "otlp_insecure", otlp_insecure,
            "OTEL_EXPORTER_OTLP_TRACES_INSECURE",
        )
        resolved_timeout = self._resolve_config(
            tracer_parameters, "otlp_timeout", otlp_timeout,
            "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT",
        )
        exporter_type = self._resolve_config(
            tracer_parameters, "exporter", None, "DERISK_OTEL_EXPORTER",
        )

        # Determine if OTel should be enabled
        if not resolved_endpoint and exporter_type != "console":
            use_telemetry = os.getenv(
                "TRACER_TO_OPEN_TELEMETRY", "false"
            ).lower() == "true"
            if not use_telemetry:
                logger.debug(
                    "OpenTelemetry endpoint not configured and "
                    "TRACER_TO_OPEN_TELEMETRY is not true, "
                    "OpenTelemetrySpanStorage disabled"
                )
                self._enabled = False
                return

        self._enabled = True
        resolved_service_name = (
            service_name
            or os.getenv("OTEL_SERVICE_NAME", "openderisk")
        )

        # Build Resource with standard attributes
        resource_attrs = {
            "service.name": resolved_service_name,
            "service.namespace": "openderisk",
            "deployment.environment": os.getenv(
                "DERISK_ENVIRONMENT", "production"
            ),
            "host.name": platform.node(),
            "process.runtime.name": "cpython",
            "process.runtime.version": platform.python_version(),
            "telemetry.sdk.language": "python",
        }
        service_version = os.getenv("DERISK_VERSION")
        if service_version:
            resource_attrs["service.version"] = service_version

        resource = Resource.create(resource_attrs)
        self.tracer_provider = TracerProvider(resource=resource)
        self.tracer = self.tracer_provider.get_tracer(
            "openderisk.tracer", schema_url=None
        )

        # Configure exporter
        self._setup_exporter(
            exporter_type, resolved_endpoint, resolved_insecure,
            resolved_timeout,
        )

        trace.set_tracer_provider(self.tracer_provider)

        # In-flight spans: span_id -> (OTSpan, creation_timestamp)
        self._spans: Dict[str, tuple] = {}
        self._lock = threading.Lock()

        # Start stale span cleanup daemon thread
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_stale_spans, daemon=True
        )
        self._cleanup_thread.start()

        logger.info(
            "OpenTelemetrySpanStorage initialized with service=%s, "
            "endpoint=%s, exporter=%s",
            resolved_service_name,
            resolved_endpoint or "(default)",
            exporter_type or "otlp-grpc",
        )

    # ------------------------------------------------------------------
    # Configuration resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_config(
        tracer_parameters, param_name: str, explicit_value, env_var: str
    ):
        """Resolve config: explicit arg > tracer_parameters > env var."""
        if explicit_value is not None:
            return explicit_value
        if tracer_parameters and hasattr(tracer_parameters, param_name):
            value = getattr(tracer_parameters, param_name)
            if value is not None:
                return value
        return os.getenv(env_var)

    def _setup_exporter(
        self, exporter_type, endpoint, insecure, timeout
    ):
        """Configure the span exporter based on type."""
        if exporter_type == "console":
            processor = BatchSpanProcessor(ConsoleSpanExporter())
        elif exporter_type == "otlp-http" and OTEL_HTTP_AVAILABLE:
            exporter_kwargs = {}
            if endpoint:
                exporter_kwargs["endpoint"] = endpoint
            if timeout:
                exporter_kwargs["timeout"] = int(timeout)
            processor = BatchSpanProcessor(
                OTLPHttpExporter(**exporter_kwargs)
            )
        else:
            # Default: OTLP/gRPC
            exporter_kwargs = {}
            if endpoint:
                exporter_kwargs["endpoint"] = endpoint
            if insecure is not None:
                exporter_kwargs["insecure"] = (
                    insecure if isinstance(insecure, bool)
                    else str(insecure).lower() == "true"
                )
            if timeout:
                exporter_kwargs["timeout"] = int(timeout)
            processor = BatchSpanProcessor(
                OTLPGrpcExporter(**exporter_kwargs)
            )

        self.tracer_provider.add_span_processor(processor)

    # ------------------------------------------------------------------
    # Core span processing
    # ------------------------------------------------------------------

    def append_span(self, span: Span):
        """Process a Derisk span and convert to an OpenTelemetry span."""
        if not self._enabled:
            return

        span_id = span.span_id

        with self._lock:
            if span_id in self._spans:
                # Second call: span is ending
                otel_span, _ = self._spans.pop(span_id)
                self._finalize_span(otel_span, span)
                return

        # First call: span is starting
        parent_context = self._create_parent_context(span)
        start_time = int(span.start_time.timestamp() * 1e9)
        span_kind = self._resolve_span_kind(span)

        otel_span = self.tracer.start_span(
            span.operation_name or "unknown",
            context=parent_context,
            kind=span_kind,
            start_time=start_time,
        )

        # Set identity attributes
        otel_span.set_attribute(_DERISK_TRACE_ID, span.trace_id)
        otel_span.set_attribute(_DERISK_SPAN_ID, span.span_id)
        if span.parent_span_id:
            otel_span.set_attribute(
                _DERISK_PARENT_SPAN_ID, span.parent_span_id
            )
        otel_span.set_attribute(_DERISK_SPAN_TYPE, span.span_type.value)

        # Set semantic attributes based on span type
        self._set_semantic_attributes(otel_span, span)

        if span.end_time:
            # Span already completed (single-shot)
            self._finalize_span(otel_span, span)
        else:
            with self._lock:
                self._spans[span_id] = (otel_span, time.monotonic())

    def append_span_batch(self, spans: List[Span]):
        """Process a batch of spans."""
        for span in spans:
            self.append_span(span)

    def _finalize_span(self, otel_span, span: Span):
        """Finalize an OTel span with end-time attributes, status, events."""
        metadata = span.metadata or {}

        # Set semantic attributes from final metadata
        self._set_semantic_attributes(otel_span, span)

        # Record error event and set status
        error = metadata.get("error")
        if error:
            otel_span.set_status(StatusCode.ERROR, str(error))
            otel_span.add_event(
                "exception",
                attributes={
                    "exception.message": str(error),
                    "exception.type": metadata.get(
                        "error_type", "Exception"
                    ),
                },
            )
        else:
            otel_span.set_status(StatusCode.OK)

        # Record LLM token usage as a span event
        if self._has_token_info(metadata):
            token_event_attrs = {}
            input_tokens = metadata.get(
                "input_tokens", metadata.get("prompt_tokens")
            )
            output_tokens = metadata.get(
                "output_tokens", metadata.get("completion_tokens")
            )
            total_tokens = metadata.get("total_tokens")
            if input_tokens is not None:
                token_event_attrs["gen_ai.usage.input_tokens"] = int(
                    input_tokens
                )
            if output_tokens is not None:
                token_event_attrs["gen_ai.usage.output_tokens"] = int(
                    output_tokens
                )
            if total_tokens is not None:
                token_event_attrs["gen_ai.usage.total_tokens"] = int(
                    total_tokens
                )
            if token_event_attrs:
                otel_span.add_event(
                    "gen_ai.usage", attributes=token_event_attrs
                )

        # End the span
        end_time = (
            int(span.end_time.timestamp() * 1e9) if span.end_time else None
        )
        if end_time:
            otel_span.end(end_time=end_time)
        else:
            otel_span.end()

    # ------------------------------------------------------------------
    # SpanKind resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_span_kind(span: Span):
        """Map Derisk span type to OpenTelemetry SpanKind.

        - WEBSERVER spans -> SERVER (HTTP entry point)
        - MODEL_WORKER / WORKER_MANAGER -> CLIENT (outgoing LLM call)
        - AGENT / CHAT / others -> INTERNAL
        """
        if span.span_type == SpanType.RUN:
            operation = span.operation_name or ""
            metadata = span.metadata or {}
            run_service = metadata.get("run_service")

            if (
                run_service == SpanTypeRunName.WEBSERVER
                or run_service == SpanTypeRunName.WEBSERVER.value
                or operation == SpanTypeRunName.WEBSERVER.value
            ):
                return SpanKind.SERVER
            if run_service in (
                SpanTypeRunName.MODEL_WORKER,
                SpanTypeRunName.MODEL_WORKER.value,
                SpanTypeRunName.WORKER_MANAGER,
                SpanTypeRunName.WORKER_MANAGER.value,
                SpanTypeRunName.EMBEDDING_MODEL,
                SpanTypeRunName.EMBEDDING_MODEL.value,
            ) or operation in (
                SpanTypeRunName.MODEL_WORKER.value,
                SpanTypeRunName.WORKER_MANAGER.value,
                SpanTypeRunName.EMBEDDING_MODEL.value,
            ):
                return SpanKind.CLIENT

        return SpanKind.INTERNAL

    # ------------------------------------------------------------------
    # Semantic attribute mapping
    # ------------------------------------------------------------------

    def _set_semantic_attributes(self, otel_span, span: Span):
        """Set OpenTelemetry semantic convention attributes."""
        metadata = span.metadata or {}

        if span.span_type == SpanType.RUN:
            self._set_run_attributes(otel_span, span, metadata)
        elif span.span_type == SpanType.CHAT:
            self._set_chat_attributes(otel_span, metadata)
        elif span.span_type == SpanType.AGENT:
            self._set_agent_attributes(otel_span, metadata)

        # Set remaining metadata as raw attributes
        self._set_raw_attributes(otel_span, metadata)

    def _set_run_attributes(self, otel_span, span: Span, metadata: Dict):
        """Set attributes for RUN type spans (HTTP, LLM)."""
        run_service = metadata.get("run_service")
        operation = span.operation_name or ""

        is_http = (
            run_service == SpanTypeRunName.WEBSERVER
            or run_service == SpanTypeRunName.WEBSERVER.value
            or operation == SpanTypeRunName.WEBSERVER.value
        )
        is_llm = run_service in (
            SpanTypeRunName.MODEL_WORKER,
            SpanTypeRunName.MODEL_WORKER.value,
            SpanTypeRunName.WORKER_MANAGER,
            SpanTypeRunName.WORKER_MANAGER.value,
            SpanTypeRunName.EMBEDDING_MODEL,
            SpanTypeRunName.EMBEDDING_MODEL.value,
        )

        if is_http:
            self._set_http_attributes(otel_span, metadata)
        elif is_llm:
            self._set_llm_attributes(otel_span, metadata)

    @staticmethod
    def _set_http_attributes(otel_span, metadata: Dict):
        """Set HTTP semantic convention attributes."""
        method = metadata.get("req_method")
        if method:
            otel_span.set_attribute(_HTTP_METHOD, method)

        path = metadata.get("req_path") or metadata.get("path")
        if path:
            otel_span.set_attribute(_HTTP_ROUTE, path)
            otel_span.set_attribute(_URL_PATH, path)

        status = metadata.get("resp_status")
        if status is not None:
            otel_span.set_attribute(_HTTP_STATUS_CODE, int(status))

    @staticmethod
    def _set_llm_attributes(otel_span, metadata: Dict):
        """Set GenAI/LLM semantic convention attributes."""
        otel_span.set_attribute(_GEN_AI_SYSTEM, "openderisk")

        model = metadata.get("model_name") or metadata.get("model")
        if model:
            otel_span.set_attribute(_GEN_AI_REQUEST_MODEL, model)
            otel_span.set_attribute(_GEN_AI_RESPONSE_MODEL, model)

        model_path = metadata.get("model_path")
        if model_path:
            otel_span.set_attribute(_DERISK_MODEL_PATH, str(model_path))

        model_type = metadata.get("model_type")
        if model_type:
            otel_span.set_attribute(_DERISK_MODEL_TYPE, str(model_type))

        # Token usage
        input_tokens = metadata.get(
            "input_tokens"
        ) or metadata.get("prompt_tokens")
        if input_tokens is not None:
            otel_span.set_attribute(
                _GEN_AI_USAGE_INPUT_TOKENS, int(input_tokens)
            )

        output_tokens = metadata.get(
            "output_tokens"
        ) or metadata.get("completion_tokens")
        if output_tokens is not None:
            otel_span.set_attribute(
                _GEN_AI_USAGE_OUTPUT_TOKENS, int(output_tokens)
            )

        total_tokens = metadata.get("total_tokens")
        if total_tokens is not None:
            otel_span.set_attribute(
                _GEN_AI_USAGE_TOTAL_TOKENS, int(total_tokens)
            )

        # Latency metrics
        latency_ms = metadata.get("latency_ms")
        if latency_ms is not None:
            otel_span.set_attribute(
                _DERISK_LLM_LATENCY_MS, int(latency_ms)
            )

        first_token_ms = metadata.get("first_token_latency_ms")
        if first_token_ms is not None:
            otel_span.set_attribute(
                _DERISK_LLM_FIRST_TOKEN_MS, int(first_token_ms)
            )

        speed = metadata.get("speed_per_second")
        if speed is not None:
            otel_span.set_attribute(_DERISK_LLM_SPEED, float(speed))

    @staticmethod
    def _set_chat_attributes(otel_span, metadata: Dict):
        """Set attributes for CHAT type spans."""
        conv_uid = metadata.get("conv_uid")
        if conv_uid:
            otel_span.set_attribute(_DERISK_CONV_UID, conv_uid)

    @staticmethod
    def _set_agent_attributes(otel_span, metadata: Dict):
        """Set attributes for AGENT type spans."""
        agent_name = (
            metadata.get("sender")
            or metadata.get("agent_name")
            or metadata.get("cls")
        )
        if agent_name:
            otel_span.set_attribute(_DERISK_AGENT_NAME, str(agent_name))

        recipient = metadata.get("recipient")
        if recipient:
            otel_span.set_attribute(
                "derisk.agent.recipient", str(recipient)
            )

        tool_name = metadata.get("tool_name") or metadata.get("action")
        if tool_name:
            otel_span.set_attribute(_DERISK_TOOL_NAME, str(tool_name))

    @staticmethod
    def _set_raw_attributes(otel_span, metadata: Dict):
        """Set remaining metadata as raw OTel attributes.

        Skips complex objects (sys_infos) and error fields already handled
        by span events.
        """
        skip_keys = {"run_service", "sys_infos", "error", "error_type"}
        for key, value in metadata.items():
            if key in skip_keys:
                continue
            if isinstance(value, (bool, str, bytes, int, float)):
                otel_span.set_attribute(key, value)
            elif isinstance(value, list) and all(
                isinstance(item, (bool, str, bytes, int, float))
                for item in value
            ):
                otel_span.set_attribute(key, value)

    # ------------------------------------------------------------------
    # Parent context creation
    # ------------------------------------------------------------------

    @staticmethod
    def _create_parent_context(span: Span):
        """Create an OTel parent context from Derisk parent span ID."""
        if not span.parent_span_id:
            return trace.set_span_in_context(trace.INVALID_SPAN)

        trace_id, parent_span_id = _split_span_id(span.parent_span_id)
        if not trace_id:
            return trace.set_span_in_context(trace.INVALID_SPAN)

        span_context = SpanContext(
            trace_id=trace_id,
            span_id=parent_span_id,
            is_remote=True,
            trace_flags=trace.TraceFlags(0x01),
        )
        return trace.set_span_in_context(
            trace.NonRecordingSpan(span_context)
        )

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def _has_token_info(metadata: Dict) -> bool:
        """Check if metadata contains token usage information."""
        token_keys = {
            "input_tokens", "output_tokens", "total_tokens",
            "prompt_tokens", "completion_tokens",
        }
        return bool(token_keys & metadata.keys())

    def _cleanup_stale_spans(self):
        """Periodically clean up spans that were never ended.

        Runs in a daemon thread. Spans older than _STALE_SPAN_TTL seconds
        are force-ended to prevent memory leaks.
        """
        while True:
            time.sleep(_STALE_SPAN_TTL / 2)
            now = time.monotonic()
            stale_ids = []

            with self._lock:
                for span_id, (_, created_at) in self._spans.items():
                    if now - created_at > _STALE_SPAN_TTL:
                        stale_ids.append(span_id)

                for span_id in stale_ids:
                    otel_span, _ = self._spans.pop(span_id)
                    try:
                        otel_span.set_status(
                            StatusCode.ERROR, "Span timed out (stale)"
                        )
                        otel_span.add_event(
                            "derisk.span_timeout",
                            attributes={
                                "derisk.timeout_seconds": _STALE_SPAN_TTL
                            },
                        )
                        otel_span.end()
                    except Exception:
                        pass

            if stale_ids:
                logger.warning(
                    "Cleaned up %d stale OpenTelemetry spans",
                    len(stale_ids),
                )

    def close(self):
        """Shutdown the tracer provider and flush pending spans."""
        if self._enabled:
            # End any remaining in-flight spans
            with self._lock:
                for span_id, (otel_span, _) in self._spans.items():
                    try:
                        otel_span.set_status(
                            StatusCode.ERROR, "Span ended by shutdown"
                        )
                        otel_span.end()
                    except Exception:
                        pass
                self._spans.clear()

            self.tracer_provider.shutdown()
