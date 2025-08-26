import logging
from contextvars import ContextVar, Token
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from derisk.util.tracer import Tracer, TracerContext

from .base import _parse_span_id

_DEFAULT_EXCLUDE_PATHS = ["/api/controller/heartbeat", "/api/health", "/api/v1/test"]

logger = logging.getLogger(__name__)


class TraceIDMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        trace_context_var: ContextVar[TracerContext],
        tracer: Tracer,
        root_operation_name: str = "DERISK-Web-Entry",
        # include_prefix: str = "/api",
        exclude_paths=_DEFAULT_EXCLUDE_PATHS,
    ):
        super().__init__(app)
        self.trace_context_var = trace_context_var
        self.tracer = tracer
        self.root_operation_name = root_operation_name
        # self.include_prefix = include_prefix
        self.exclude_paths = exclude_paths

    async def dispatch(self, request: Request, call_next):
        # Read trace_id from request headers
        span_id = _parse_span_id(request)
        logger.info(
            f"TraceIDMiddleware: span_id={span_id}, path={request.url.path}, "
            f"headers={request.headers}"
        ) if request.url.path not in self.exclude_paths else None
        token: Optional[Token[TracerContext]] = None
        try:
            token = self.trace_context_var.set(TracerContext(span_id=span_id))
            with self.tracer.start_span(
                self.root_operation_name, span_id, metadata={"path": request.url.path}
            ):
                response = await call_next(request)
            return response
        finally:
            if token:
                self.trace_context_var.reset(token)
