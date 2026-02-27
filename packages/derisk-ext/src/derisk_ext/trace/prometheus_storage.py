"""Prometheus metrics exporter for OpenDerisk.

Implements a SpanStorage that extracts metrics from spans and exposes them
via a /metrics HTTP endpoint compatible with Prometheus scraping.

This module is automatically discovered by the tracer initialization
via model_scan("derisk_ext.trace", SpanStorage).
"""

import logging
import os
import platform
import threading
from typing import Dict, List, Optional, Set

from derisk.component import SystemApp
from derisk.util.tracer.base import Span, SpanStorage, SpanType, SpanTypeRunName

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.info(
        "prometheus_client is not installed, PrometheusSpanStorage will be "
        "disabled. Install it via: pip install prometheus_client"
    )


# ---------------------------------------------------------------------------
# Metric definitions (module-level singletons, created only when available)
# ---------------------------------------------------------------------------

if PROMETHEUS_AVAILABLE:
    HTTP_REQUESTS_TOTAL = Counter(
        "derisk_http_requests_total",
        "Total number of HTTP requests",
        ["method", "path", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "derisk_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    )

    LLM_REQUESTS_TOTAL = Counter(
        "derisk_llm_requests_total",
        "Total number of LLM inference requests",
        ["model"],
    )
    LLM_REQUEST_DURATION = Histogram(
        "derisk_llm_request_duration_seconds",
        "LLM inference request duration in seconds",
        ["model"],
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
    )
    LLM_TOKENS_TOTAL = Counter(
        "derisk_llm_tokens_total",
        "Total number of tokens processed",
        ["model", "type"],
    )
    LLM_FIRST_TOKEN_LATENCY = Histogram(
        "derisk_llm_first_token_latency_seconds",
        "Time to first token (TTFT) in seconds",
        ["model"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    LLM_TOKENS_PER_SECOND = Gauge(
        "derisk_llm_tokens_per_second",
        "Current token generation speed",
        ["model", "phase"],
    )

    AGENT_TASKS_TOTAL = Counter(
        "derisk_agent_tasks_total",
        "Total number of agent tasks",
        ["agent_name", "status"],
    )
    AGENT_TASK_DURATION = Histogram(
        "derisk_agent_task_duration_seconds",
        "Agent task duration in seconds",
        ["agent_name"],
        buckets=(0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
    )

    TOOL_CALLS_TOTAL = Counter(
        "derisk_tool_calls_total",
        "Total number of tool calls",
        ["tool_name", "status"],
    )

    ACTIVE_CONVERSATIONS = Gauge(
        "derisk_active_conversations",
        "Number of currently active conversations",
    )

    SYSTEM_INFO = Info(
        "derisk",
        "OpenDerisk system information",
    )


class PrometheusSpanStorage(SpanStorage):
    """SpanStorage that extracts metrics from spans for Prometheus.

    Automatically discovered by model_scan("derisk_ext.trace", SpanStorage)
    during tracer initialization. It intercepts completed spans, extracts
    relevant metrics, and updates Prometheus counters/histograms.

    The /metrics endpoint is mounted on the FastAPI app during init_app().
    """

    name = "prometheus_span_storage"

    def __init__(
        self,
        system_app: Optional[SystemApp] = None,
        tracer_parameters=None,
    ):
        super().__init__(system_app)
        self._enabled = PROMETHEUS_AVAILABLE and self._is_metrics_enabled()
        self._active_conversations: Set[str] = set()
        self._lock = threading.Lock()
        self._initialized = False

        if self._enabled:
            logger.info(
                "PrometheusSpanStorage initialized, "
                "metrics will be available at /metrics"
            )

    @staticmethod
    def _is_metrics_enabled() -> bool:
        """Check if Prometheus metrics are enabled via environment variable."""
        return os.getenv("DERISK_ENABLE_PROMETHEUS", "true").lower() in (
            "true",
            "1",
            "yes",
        )

    def init_app(self, system_app: SystemApp):
        """Initialize with the application context and mount /metrics."""
        self.system_app = system_app
        if not self._enabled:
            return

        self._set_system_info()

        if system_app and system_app.app:
            self._mount_metrics_endpoint(system_app.app)
            self._initialized = True

    def after_start(self):
        """Mount /metrics endpoint after app start if not already done."""
        if not self._enabled or self._initialized:
            return

        if self.system_app and self.system_app.app:
            self._mount_metrics_endpoint(self.system_app.app)
            self._initialized = True

    def _mount_metrics_endpoint(self, app):
        """Mount the /metrics endpoint on the FastAPI app."""
        try:
            from starlette.requests import Request
            from starlette.responses import Response

            async def metrics_endpoint(request: Request) -> Response:
                return Response(
                    content=generate_latest(REGISTRY),
                    media_type="text/plain; version=0.0.4; charset=utf-8",
                )

            app.add_route("/metrics", metrics_endpoint, methods=["GET"])
            logger.info("Prometheus /metrics endpoint mounted successfully")
        except Exception as error:
            logger.warning(f"Failed to mount /metrics endpoint: {error}")

    @staticmethod
    def _set_system_info():
        """Set static system information as Prometheus Info metric."""
        try:
            SYSTEM_INFO.info(
                {
                    "python_version": platform.python_version(),
                    "platform": platform.platform(),
                }
            )
        except Exception:
            pass

    def append_span(self, span: Span):
        """Process a completed span and update Prometheus metrics."""
        if not self._enabled:
            return

        try:
            span_type = span.span_type
            if span_type == SpanType.RUN:
                self._process_run_span(span)
            elif span_type == SpanType.CHAT:
                self._process_chat_span(span)
            elif span_type == SpanType.AGENT:
                self._process_agent_span(span)
        except Exception as error:
            logger.debug(f"Error processing span for metrics: {error}")

    def append_span_batch(self, spans: List[Span]):
        """Process a batch of spans."""
        for span in spans:
            self.append_span(span)

    # ------------------------------------------------------------------
    # Span type processors
    # ------------------------------------------------------------------

    def _process_run_span(self, span: Span):
        """Process RUN type spans (HTTP requests, LLM inference)."""
        operation = span.operation_name or ""
        metadata = span.metadata or {}
        duration = self._calculate_duration(span)

        if operation == SpanTypeRunName.WEBSERVER.value:
            self._record_http_metrics(metadata, duration)
        elif operation in (
            SpanTypeRunName.MODEL_WORKER.value,
            SpanTypeRunName.WORKER_MANAGER.value,
        ):
            self._record_llm_metrics(metadata, duration)

    def _process_chat_span(self, span: Span):
        """Process CHAT type spans (conversation tracking)."""
        metadata = span.metadata or {}
        conv_uid = metadata.get("conv_uid", "")

        if conv_uid:
            with self._lock:
                if span.end_time:
                    self._active_conversations.discard(conv_uid)
                else:
                    self._active_conversations.add(conv_uid)
                ACTIVE_CONVERSATIONS.set(len(self._active_conversations))

    def _process_agent_span(self, span: Span):
        """Process AGENT type spans (agent tasks, tool calls)."""
        metadata = span.metadata or {}
        duration = self._calculate_duration(span)
        agent_name = metadata.get(
            "agent_name", metadata.get("cls", "unknown")
        )
        status = "error" if metadata.get("error") else "success"

        AGENT_TASKS_TOTAL.labels(
            agent_name=agent_name, status=status
        ).inc()
        if duration is not None:
            AGENT_TASK_DURATION.labels(agent_name=agent_name).observe(duration)

        tool_name = metadata.get("tool_name") or metadata.get("action")
        if tool_name:
            tool_status = "error" if metadata.get("tool_error") else "success"
            TOOL_CALLS_TOTAL.labels(
                tool_name=tool_name, status=tool_status
            ).inc()

    # ------------------------------------------------------------------
    # Metric recording helpers
    # ------------------------------------------------------------------

    def _record_http_metrics(
        self, metadata: Dict, duration: Optional[float]
    ):
        """Record HTTP request metrics from Webserver span metadata."""
        method = metadata.get("req_method", "UNKNOWN")
        path = self._normalize_path(metadata.get("req_path", "/"))
        status = str(metadata.get("resp_status", "200"))

        HTTP_REQUESTS_TOTAL.labels(
            method=method, path=path, status=status
        ).inc()
        if duration is not None:
            HTTP_REQUEST_DURATION.labels(
                method=method, path=path
            ).observe(duration)

    def _record_llm_metrics(
        self, metadata: Dict, duration: Optional[float]
    ):
        """Record LLM inference metrics from ModelWorker span metadata."""
        model = metadata.get(
            "model", metadata.get("model_name", "unknown")
        )

        LLM_REQUESTS_TOTAL.labels(model=model).inc()
        if duration is not None:
            LLM_REQUEST_DURATION.labels(model=model).observe(duration)

        prompt_tokens = metadata.get("prompt_tokens")
        completion_tokens = metadata.get("completion_tokens")
        if prompt_tokens is not None:
            LLM_TOKENS_TOTAL.labels(
                model=model, type="prompt"
            ).inc(int(prompt_tokens))
        if completion_tokens is not None:
            LLM_TOKENS_TOTAL.labels(
                model=model, type="completion"
            ).inc(int(completion_tokens))

        start_time_ms = metadata.get("start_time_ms")
        first_token_time_ms = metadata.get("first_token_time_ms")
        if start_time_ms and first_token_time_ms:
            ttft_seconds = (
                int(first_token_time_ms) - int(start_time_ms)
            ) / 1000.0
            if ttft_seconds > 0:
                LLM_FIRST_TOKEN_LATENCY.labels(model=model).observe(
                    ttft_seconds
                )

        speed = metadata.get("speed_per_second")
        if speed is not None:
            LLM_TOKENS_PER_SECOND.labels(
                model=model, phase="overall"
            ).set(float(speed))

        prefill_speed = metadata.get("prefill_tokens_per_second")
        if prefill_speed is not None:
            LLM_TOKENS_PER_SECOND.labels(
                model=model, phase="prefill"
            ).set(float(prefill_speed))

        decode_speed = metadata.get("decode_tokens_per_second")
        if decode_speed is not None:
            LLM_TOKENS_PER_SECOND.labels(
                model=model, phase="decode"
            ).set(float(decode_speed))

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_duration(span: Span) -> Optional[float]:
        """Calculate span duration in seconds."""
        if span.start_time and span.end_time:
            return (span.end_time - span.start_time).total_seconds()
        return None

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize URL path to reduce cardinality.

        Replaces dynamic segments (UUIDs, numbers) with placeholders
        to prevent high-cardinality label explosion in Prometheus.
        """
        if not path:
            return "/"

        parts = path.strip("/").split("/")
        normalized = []
        for part in parts:
            if len(part) == 36 and part.count("-") == 4:
                normalized.append("{id}")
            elif part.isdigit():
                normalized.append("{id}")
            elif len(part) > 8 and all(
                c in "0123456789abcdef" for c in part.lower()
            ):
                normalized.append("{id}")
            else:
                normalized.append(part)

        return "/" + "/".join(normalized) if normalized else "/"
