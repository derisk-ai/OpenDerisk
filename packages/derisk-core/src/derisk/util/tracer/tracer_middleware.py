import logging
from contextvars import ContextVar, Token
from typing import Optional

from derisk.util.tracer import Tracer, TracerContext
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from .base import _parse_span_id
from ..date_utils import current_ms
from ..logger import digest

# _DEFAULT_EXCLUDE_PATHS = ["/api/controller/heartbeat", "/api/health", "/api/v1/test"]
_DIGEST_EXCLUDE_PATHS = ["/api/controller/heartbeat", "/api/v1/test"]
_DEFAULT_EXCLUDE_PATHS = _DIGEST_EXCLUDE_PATHS + ["/api/health"]
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

    async def dispatch(self, request: Request, call_next):
        # Read trace_id from request headers
        span_id = _parse_span_id(request)
        logger.info(
            f"TraceIDMiddleware: span_id={span_id}, schema={request.url.scheme}, path={request.url.path}, "
            # f"headers={request.headers}"
        ) if request.url.path not in _DEFAULT_EXCLUDE_PATHS else None
        token: Optional[Token[TracerContext]] = None
        succeed = True
        start_ms = current_ms()
        req_len = request.headers.get("content-length", 0) if request.headers else 0
        resp_len = 0
        try:
            token = self.trace_context_var.set(TracerContext(span_id=span_id, entrance_ms=current_ms()))
            with self.tracer.start_span(
                self.root_operation_name, span_id=span_id, metadata={"path": request.url.path}
            ):
                response = await call_next(request)
                length = response.headers.get("content-length") if response and response.headers else 0
                resp_len = length or resp_len
            return response
        except:
            succeed = False
            raise
        finally:
            if request.url.path not in _DIGEST_EXCLUDE_PATHS:
                digest(None, "trace", succeed=succeed, cost_ms=current_ms() - start_ms,
                       methon=request.method, url=request.url.path, resp_len=resp_len, req_len=req_len)
            if token:
                # 清除线程变量中的trace信息 必须放在最后
                self.trace_context_var.reset(token)
