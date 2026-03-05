"""
Observability - 可观测性系统

实现Metrics、Tracing、Logging的统一管理
支持多种导出后端
"""

from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field as dataclass_field
from collections import defaultdict
import json
import asyncio
import logging
import time
import uuid

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """指标类型"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SpanStatus(str, Enum):
    """Span状态"""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class Metric:
    """指标"""
    name: str
    metric_type: MetricType
    value: float
    labels: Dict[str, str] = dataclass_field(default_factory=dict)
    timestamp: datetime = dataclass_field(default_factory=datetime.now)


@dataclass
class Span:
    """追踪Span"""
    trace_id: str
    span_id: str
    operation_name: str
    parent_span_id: Optional[str] = None
    start_time: datetime = dataclass_field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.UNSET
    tags: Dict[str, Any] = dataclass_field(default_factory=dict)
    logs: List[Dict[str, Any]] = dataclass_field(default_factory=list)
    duration_ms: float = 0.0

    def finish(self, status: SpanStatus = SpanStatus.OK):
        """结束Span"""
        self.end_time = datetime.now()
        self.status = status
        if self.start_time and self.end_time:
            self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """添加事件"""
        self.logs.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "attributes": attributes or {}
        })

    def set_tag(self, key: str, value: Any):
        """设置标签"""
        self.tags[key] = value


class LogEntry(BaseModel):
    """日志条目"""
    timestamp: datetime = Field(default_factory=datetime.now)
    level: LogLevel
    message: str
    
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    
    extra: Dict[str, Any] = Field(default_factory=dict)


class MetricsCollector:
    """
    指标收集器
    
    示例:
        metrics = MetricsCollector()
        
        metrics.counter("requests_total", labels={"method": "GET"})
        metrics.gauge("active_sessions", 10)
        metrics.histogram("request_duration_ms", 150)
    """
    
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._summaries: Dict[str, List[float]] = defaultdict(list)
    
    def _get_metric_name(self, name: str) -> str:
        return f"{self.prefix}{name}" if self.prefix else name
    
    def counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None
    ):
        """计数器"""
        metric_name = self._get_metric_name(name)
        key = self._make_key(metric_name, labels)
        self._counters[key] += value
    
    def gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ):
        """仪表"""
        metric_name = self._get_metric_name(name)
        key = self._make_key(metric_name, labels)
        self._gauges[key] = value
    
    def histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ):
        """直方图"""
        metric_name = self._get_metric_name(name)
        key = self._make_key(metric_name, labels)
        self._histograms[key].append(value)
    
    def summary(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ):
        """摘要"""
        metric_name = self._get_metric_name(name)
        key = self._make_key(metric_name, labels)
        self._summaries[key].append(value)
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_counts(self, name: str) -> Optional[float]:
        """获取计数器值"""
        metric_name = self._get_metric_name(name)
        for key, value in self._counters.items():
            if key.startswith(metric_name):
                return value
        return None
    
    def get_gauge(self, name: str) -> Optional[float]:
        """获取仪表值"""
        metric_name = self._get_metric_name(name)
        for key, value in self._gauges.items():
            if key.startswith(metric_name):
                return value
        return None
    
    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """获取直方图统计"""
        metric_name = self._get_metric_name(name)
        
        for key, values in self._histograms.items():
            if key.startswith(metric_name):
                if not values:
                    continue
                sorted_values = sorted(values)
                return {
                    "count": len(values),
                    "sum": sum(values),
                    "min": sorted_values[0],
                    "max": sorted_values[-1],
                    "mean": sum(values) / len(values),
                    "p50": sorted_values[int(len(values) * 0.5)],
                    "p90": sorted_values[int(len(values) * 0.9)],
                    "p99": sorted_values[int(len(values) * 0.99)],
                }
        
        return {}
    
    def export_prometheus(self) -> str:
        """导出Prometheus格式"""
        lines = []
        
        for key, value in self._counters.items():
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")
        
        for key, value in self._gauges.items():
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")
        
        return "\n".join(lines)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "sum": sum(v),
                    "mean": sum(v) / len(v) if v else 0
                }
                for k, v in self._histograms.items()
            }
        }


class Tracer:
    """
    追踪器
    
    示例:
        tracer = Tracer()
        
        span = tracer.start_span("process_request")
        # ... do work ...
        span.finish()
        
        tracer.end_span(span)
    """
    
    def __init__(self, service_name: str = "agent"):
        self.service_name = service_name
        self._active_spans: Dict[str, Span] = {}
        self._completed_traces: Dict[str, List[Span]] = defaultdict(list)
        self._span_count = 0
    
    def start_span(
        self,
        operation_name: str,
        parent_span: Optional[Span] = None,
        tags: Optional[Dict[str, Any]] = None
    ) -> Span:
        """开始Span"""
        span = Span(
            trace_id=parent_span.trace_id if parent_span else str(uuid.uuid4().hex)[:16],
            span_id=str(uuid.uuid4().hex)[:16],
            parent_span_id=parent_span.span_id if parent_span else None,
            operation_name=operation_name,
            tags=tags or {}
        )
        
        self._active_spans[span.span_id] = span
        self._span_count += 1
        
        return span
    
    def end_span(self, span: Span, status: SpanStatus = SpanStatus.OK):
        """结束Span"""
        span.finish(status)
        
        self._completed_traces[span.trace_id].append(span)
        
        if span.span_id in self._active_spans:
            del self._active_spans[span.span_id]
    
    def get_span(self, span_id: str) -> Optional[Span]:
        """获取Span"""
        return self._active_spans.get(span_id)
    
    def get_trace(self, trace_id: str) -> List[Span]:
        """获取Trace"""
        return self._completed_traces.get(trace_id, [])
    
    def get_active_spans(self) -> List[Span]:
        """获取活跃Span"""
        return list(self._active_spans.values())
    
    def export_trace(self, trace_id: str) -> Dict[str, Any]:
        """导出Trace"""
        spans = self.get_trace(trace_id)
        
        return {
            "trace_id": trace_id,
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "operation_name": s.operation_name,
                    "start_time": s.start_time.isoformat(),
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "duration_ms": s.duration_ms,
                    "status": s.status.value,
                    "tags": s.tags,
                    "logs": s.logs
                }
                for s in spans
            ]
        }


class StructuredLogger:
    """
    结构化日志器
    
    示例:
        logger = StructuredLogger("agent")
        
        logger.info("Request processed", extra={"duration_ms": 100})
        logger.error("Failed to process", error=exc)
    """
    
    def __init__(
        self,
        name: str,
        session_id: Optional[str] = None,
        agent_name: Optional[str] = None
    ):
        self.name = name
        self.session_id = session_id
        self.agent_name = agent_name
        self._logger = logging.getLogger(name)
        self._entries: List[LogEntry] = []
        self._max_entries = 1000
    
    def _log(self, level: LogLevel, message: str, **kwargs):
        """记录日志"""
        entry = LogEntry(
            level=level,
            message=message,
            session_id=self.session_id,
            agent_name=self.agent_name,
            extra=kwargs
        )
        
        self._entries.append(entry)
        
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries // 2:]
        
        log_method = getattr(self._logger, level.value, self._logger.info)
        log_method(f"[{self.session_id[:8] if self.session_id else 'N/A'}] {message}", extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        if error:
            kwargs["error_type"] = type(error).__name__
            kwargs["error_message"] = str(error)
        self._log(LogLevel.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log(LogLevel.CRITICAL, message, **kwargs)
    
    def with_context(self, **kwargs) -> "StructuredLogger":
        """创建带上下文的日志器"""
        new_logger = StructuredLogger(
            self.name,
            session_id=kwargs.get("session_id", self.session_id),
            agent_name=kwargs.get("agent_name", self.agent_name)
        )
        new_logger._logger = self._logger
        return new_logger
    
    def get_entries(
        self,
        level: Optional[LogLevel] = None,
        limit: int = 100
    ) -> List[LogEntry]:
        """获取日志条目"""
        entries = self._entries
        
        if level:
            entries = [e for e in entries if e.level == level]
        
        return entries[-limit:]
    
    def export_json(self) -> str:
        """导出JSON"""
        return json.dumps(
            [e.dict() for e in self._entries],
            default=str,
            indent=2
        )


class ObservabilityManager:
    """
    可观测性管理器
    
    统一管理Metrics、Tracing、Logging
    
    示例:
        obs = ObservabilityManager("agent-service")
        
        # 开始追踪
        span = obs.start_span("process_request")
        
        # 记录日志
        obs.logger.info("Processing request")
        
        # 记录指标
        obs.metrics.counter("requests_total")
        
        # 结束追踪
        obs.end_span(span)
        
        # 导出
        print(obs.export_metrics())
    """
    
    def __init__(
        self,
        service_name: str = "agent",
        metrics_prefix: str = "",
        enable_console_logging: bool = True
    ):
        self.service_name = service_name
        
        self.tracer = Tracer(service_name)
        self.metrics = MetricsCollector(metrics_prefix)
        self.logger = StructuredLogger(service_name)
        
        self._default_tags: Dict[str, str] = {
            "service": service_name
        }
        
        self._setup_logging(enable_console_logging)
    
    def _setup_logging(self, enable_console: bool):
        """设置日志"""
        if enable_console:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
            ))
            logging.root.addHandler(handler)
            logging.root.setLevel(logging.INFO)
    
    def start_span(
        self,
        operation_name: str,
        parent_span: Optional[Span] = None,
        tags: Optional[Dict[str, Any]] = None
    ) -> Span:
        """开始追踪"""
        merged_tags = {**self._default_tags, **(tags or {})}
        return self.tracer.start_span(operation_name, parent_span, merged_tags)
    
    def end_span(self, span: Span, status: SpanStatus = SpanStatus.OK):
        """结束追踪"""
        self.tracer.end_span(span, status)
        
        self.metrics.histogram(
            "span_duration_ms",
            span.duration_ms,
            {"operation": span.operation_name}
        )
    
    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float
    ):
        """记录请求"""
        self.metrics.counter(
            "requests_total",
            labels={"method": method, "path": path, "status": str(status_code)}
        )
        
        self.metrics.histogram(
            "request_duration_ms",
            duration_ms,
            labels={"method": method, "path": path}
        )
    
    def with_session(self, session_id: str, agent_name: Optional[str] = None) -> "ObservabilityManager":
        """创建带会话上下文的管理器"""
        new_obs = ObservabilityManager(
            self.service_name,
            enable_console_logging=False
        )
        new_obs.tracer = self.tracer
        new_obs.metrics = self.metrics
        new_obs.logger = self.logger.with_context(
            session_id=session_id,
            agent_name=agent_name
        )
        return new_obs
    
    def export_metrics(self) -> str:
        """导出指标"""
        return self.metrics.export_prometheus()
    
    def export_trace(self, trace_id: str) -> Dict[str, Any]:
        """导出追踪"""
        return self.tracer.export_trace(trace_id)
    
    def export_logs(self) -> str:
        """导出日志"""
        return self.logger.export_json()
    
    def get_health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "service": self.service_name,
            "status": "healthy",
            "metrics": {
                "counters": len(self.metrics._counters),
                "gauges": len(self.metrics._gauges),
                "histograms": len(self.metrics._histograms)
            },
            "tracing": {
                "active_spans": len(self.tracer._active_spans),
                "total_spans": self.tracer._span_count
            },
            "logging": {
                "entries": len(self.logger._entries)
            }
        }


observability_manager = ObservabilityManager()