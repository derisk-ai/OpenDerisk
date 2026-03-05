"""
ModelMonitor - 模型调用监控追踪

实现Token统计、成本追踪、调用链路追踪
支持多种导出和存储后端
"""

from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import uuid
import asyncio
import logging
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field as dataclass_field

logger = logging.getLogger(__name__)


class CallStatus(str, Enum):
    """调用状态"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


class SpanKind(str, Enum):
    """Span类型"""
    CHAT = "chat"
    EMBEDDING = "embedding"
    COMPLETION = "completion"
    FUNCTION_CALL = "function_call"
    TOOL_CALL = "tool_call"


@dataclass
class ModelCallSpan:
    """模型调用Span"""
    span_id: str = dataclass_field(default_factory=lambda: str(uuid.uuid4().hex)[:16])
    trace_id: str = dataclass_field(default_factory=lambda: str(uuid.uuid4().hex)[:16])
    parent_span_id: Optional[str] = None
    
    kind: SpanKind = SpanKind.CHAT
    name: str = ""
    
    model_id: str = ""
    provider: str = ""
    
    start_time: datetime = dataclass_field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    status: CallStatus = CallStatus.PENDING
    
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    cost: float = 0.0
    latency: float = 0.0
    
    input_messages: List[Dict[str, Any]] = dataclass_field(default_factory=list)
    output_content: str = ""
    
    metadata: Dict[str, Any] = dataclass_field(default_factory=dict)
    tags: Dict[str, str] = dataclass_field(default_factory=dict)
    
    error_message: Optional[str] = None
    error_stack: Optional[str] = None
    
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

    def finish(self, status: CallStatus = CallStatus.SUCCESS):
        """结束Span"""
        self.end_time = datetime.now()
        self.status = status
        
        if self.start_time and self.end_time:
            self.latency = (self.end_time - self.start_time).total_seconds()


class TokenUsage(BaseModel):
    """Token使用统计"""
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    
    total_cost: float = 0.0
    avg_latency: float = 0.0
    
    time_window: str = "all"
    last_updated: datetime = Field(default_factory=datetime.now)


@dataclass
class TokenUsageTracker:
    """Token使用追踪器"""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    
    by_provider: Dict[str, TokenUsage] = dataclass_field(default_factory=lambda: {})
    by_model: Dict[str, TokenUsage] = dataclass_field(default_factory=lambda: {})
    by_agent: Dict[str, TokenUsage] = dataclass_field(default_factory=lambda: {})
    
    def record_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        agent_name: Optional[str] = None,
        success: bool = True
    ):
        """记录使用"""
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost += cost
        
        self.call_count += 1
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
        
        if provider not in self.by_provider:
            self.by_provider[provider] = TokenUsage(provider=provider, model="*")
        self.by_provider[provider].prompt_tokens += prompt_tokens
        self.by_provider[provider].completion_tokens += completion_tokens
        self.by_provider[provider].total_tokens += prompt_tokens + completion_tokens
        self.by_provider[provider].total_cost += cost
        self.by_provider[provider].call_count += 1
        if success:
            self.by_provider[provider].success_count += 1
        else:
            self.by_provider[provider].error_count += 1
        
        model_key = f"{provider}/{model}"
        if model_key not in self.by_model:
            self.by_model[model_key] = TokenUsage(provider=provider, model=model)
        self.by_model[model_key].prompt_tokens += prompt_tokens
        self.by_model[model_key].completion_tokens += completion_tokens
        self.by_model[model_key].total_tokens += prompt_tokens + completion_tokens
        self.by_model[model_key].total_cost += cost
        self.by_model[model_key].call_count += 1
        if success:
            self.by_model[model_key].success_count += 1
        else:
            self.by_model[model_key].error_count += 1
        
        if agent_name:
            if agent_name not in self.by_agent:
                self.by_agent[agent_name] = TokenUsage(provider="*", model="*")
            self.by_agent[agent_name].prompt_tokens += prompt_tokens
            self.by_agent[agent_name].completion_tokens += completion_tokens
            self.by_agent[agent_name].total_tokens += prompt_tokens + completion_tokens
            self.by_agent[agent_name].total_cost += cost
            self.by_agent[agent_name].call_count += 1


class CallTrace(BaseModel):
    """调用链路"""
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:16])
    spans: List[Dict[str, Any]] = Field(default_factory=list)
    
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    agent_name: Optional[str] = None
    
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    total_tokens: int = 0
    total_cost: float = 0.0
    total_latency: float = 0.0
    
    status: CallStatus = CallStatus.PENDING
    error_message: Optional[str] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelMonitor:
    """
    模型监控器
    
    职责：
    1. Token使用统计
    2. 成本追踪
    3. 调用链路追踪
    4. 性能监控
    5. 异常告警
    
    示例:
        monitor = ModelMonitor()
        
        span = monitor.start_span(
            kind=SpanKind.CHAT,
            model_id="gpt-4",
            provider="openai"
        )
        
        span.prompt_tokens = 100
        span.completion_tokens = 50
        span.finish()
        
        monitor.end_span(span)
        
        stats = monitor.get_usage_stats()
    """
    
    def __init__(
        self,
        storage_backend: str = "memory",
        db_path: str = ":memory:",
        on_alert: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.storage_backend = storage_backend
        self.db_path = db_path
        self.on_alert = on_alert
        
        self._usage_tracker = TokenUsageTracker()
        self._active_spans: Dict[str, ModelCallSpan] = {}
        self._completed_traces: Dict[str, CallTrace] = {}
        
        self._alert_thresholds = {
            "cost_per_hour": 100.0,
            "tokens_per_hour": 100000,
            "error_rate": 0.1,
            "latency_p99": 10.0,
        }
        
        self._hourly_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "tokens": 0,
            "cost": 0.0,
            "calls": 0,
            "errors": 0,
        })
        
        if storage_backend == "sqlite":
            self._init_sqlite()
    
    def _init_sqlite(self):
        """初始化SQLite存储"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS call_spans (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT,
                parent_span_id TEXT,
                kind TEXT,
                name TEXT,
                model_id TEXT,
                provider TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                latency REAL,
                metadata TEXT,
                error_message TEXT,
                agent_name TEXT,
                session_id TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT,
                model TEXT,
                time_window TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                total_cost REAL,
                call_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def start_span(
        self,
        kind: SpanKind = SpanKind.CHAT,
        name: str = "",
        model_id: str = "",
        provider: str = "",
        parent_span_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ModelCallSpan:
        """
        开始一个Span
        
        Args:
            kind: Span类型
            name: Span名称
            model_id: 模型ID
            provider: 供应商
            parent_span_id: 父Span ID
            trace_id: Trace ID
            agent_name: Agent名称
            session_id: Session ID
            conversation_id: 对话ID
            tags: 标签
            metadata: 元数据
            
        Returns:
            ModelCallSpan: Span对象
        """
        span = ModelCallSpan(
            kind=kind,
            name=name,
            model_id=model_id,
            provider=provider,
            parent_span_id=parent_span_id,
            agent_name=agent_name,
            session_id=session_id,
            conversation_id=conversation_id,
            tags=tags or {},
            metadata=metadata or {}
        )
        
        if trace_id:
            span.trace_id = trace_id
        
        self._active_spans[span.span_id] = span
        
        logger.debug(f"[ModelMonitor] 开始Span: {span.span_id} - {name}")
        return span
    
    def end_span(
        self,
        span: ModelCallSpan,
        status: CallStatus = CallStatus.SUCCESS,
        output_content: str = "",
        error_message: Optional[str] = None
    ):
        """
        结束Span
        
        Args:
            span: Span对象
            status: 状态
            output_content: 输出内容
            error_message: 错误信息
        """
        span.output_content = output_content
        span.error_message = error_message
        span.finish(status)
        
        cost = self._calculate_cost(span)
        span.cost = cost
        
        self._usage_tracker.record_usage(
            provider=span.provider,
            model=span.model_id,
            prompt_tokens=span.prompt_tokens,
            completion_tokens=span.completion_tokens,
            cost=cost,
            agent_name=span.agent_name,
            success=(status == CallStatus.SUCCESS)
        )
        
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        self._hourly_stats[hour_key]["tokens"] += span.total_tokens
        self._hourly_stats[hour_key]["cost"] += cost
        self._hourly_stats[hour_key]["calls"] += 1
        if status != CallStatus.SUCCESS:
            self._hourly_stats[hour_key]["errors"] += 1
        
        if self.storage_backend == "sqlite":
            self._save_span_to_sqlite(span)
        
        self._check_alerts(span)
        
        if span.span_id in self._active_spans:
            del self._active_spans[span.span_id]
        
        logger.debug(
            f"[ModelMonitor] 结束Span: {span.span_id}, "
            f"tokens={span.total_tokens}, cost=${cost:.4f}, latency={span.latency:.2f}s"
        )
    
    def _calculate_cost(self, span: ModelCallSpan) -> float:
        """计算成本"""
        cost_configs = {
            ("openai", "gpt-4"): (0.03, 0.06),
            ("openai", "gpt-4-turbo"): (0.01, 0.03),
            ("openai", "gpt-3.5-turbo"): (0.001, 0.002),
            ("anthropic", "claude-3-opus"): (0.015, 0.075),
            ("anthropic", "claude-3-sonnet"): (0.003, 0.015),
        }
        
        key = (span.provider, span.model_id)
        
        if key in cost_configs:
            prompt_cost_per_1k, completion_cost_per_1k = cost_configs[key]
            prompt_cost = (span.prompt_tokens / 1000) * prompt_cost_per_1k
            completion_cost = (span.completion_tokens / 1000) * completion_cost_per_1k
            return prompt_cost + completion_cost
        
        return span.metadata.get("cost", 0.0)
    
    def _save_span_to_sqlite(self, span: ModelCallSpan):
        """保存Span到SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT INTO call_spans VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                span.span_id,
                span.trace_id,
                span.parent_span_id,
                span.kind.value,
                span.name,
                span.model_id,
                span.provider,
                span.start_time,
                span.end_time,
                span.status.value,
                span.prompt_tokens,
                span.completion_tokens,
                span.total_tokens,
                span.cost,
                span.latency,
                json.dumps(span.metadata),
                span.error_message,
                span.agent_name,
                span.session_id
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[ModelMonitor] 保存Span失败: {e}")
    
    def _check_alerts(self, span: ModelCallSpan):
        """检查告警"""
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
        hourly = self._hourly_stats.get(hour_key, {})
        
        alerts = []
        
        if hourly.get("cost", 0) > self._alert_thresholds["cost_per_hour"]:
            alerts.append({
                "type": "cost_exceeded",
                "message": f"每小时成本超过阈值: ${hourly['cost']:.2f}",
                "threshold": self._alert_thresholds["cost_per_hour"],
                "current": hourly["cost"],
            })
        
        if hourly.get("tokens", 0) > self._alert_thresholds["tokens_per_hour"]:
            alerts.append({
                "type": "tokens_exceeded",
                "message": f"每小时Token超过阈值: {hourly['tokens']}",
                "threshold": self._alert_thresholds["tokens_per_hour"],
                "current": hourly["tokens"],
            })
        
        total_calls = self._usage_tracker.call_count
        error_calls = self._usage_tracker.error_count
        if total_calls > 10 and (error_calls / total_calls) > self._alert_thresholds["error_rate"]:
            alerts.append({
                "type": "error_rate_high",
                "message": f"错误率过高: {error_calls/total_calls:.1%}",
                "threshold": self._alert_thresholds["error_rate"],
                "current": error_calls / total_calls,
            })
        
        for alert in alerts:
            logger.warning(f"[ModelMonitor] 告警: {alert['message']}")
            if self.on_alert:
                self.on_alert(alert)
    
    def get_usage_stats(
        self,
        by: str = "provider",
        time_window: str = "all"
    ) -> Dict[str, Any]:
        """
        获取使用统计
        
        Args:
            by: 统计维度 (provider/model/agent)
            time_window: 时间窗口 (all/hour/day/week)
            
        Returns:
            Dict[str, Any]: 统计数据
        """
        if by == "provider":
            return {
                k: v.dict() for k, v in self._usage_tracker.by_provider.items()
            }
        elif by == "model":
            return {
                k: v.dict() for k, v in self._usage_tracker.by_model.items()
            }
        elif by == "agent":
            return {
                k: v.dict() for k, v in self._usage_tracker.by_agent.items()
            }
        
        return {
            "total_prompt_tokens": self._usage_tracker.total_prompt_tokens,
            "total_completion_tokens": self._usage_tracker.total_completion_tokens,
            "total_tokens": self._usage_tracker.total_tokens,
            "total_cost": self._usage_tracker.total_cost,
            "call_count": self._usage_tracker.call_count,
            "success_count": self._usage_tracker.success_count,
            "error_count": self._usage_tracker.error_count,
            "success_rate": (
                self._usage_tracker.success_count / self._usage_tracker.call_count
                if self._usage_tracker.call_count > 0 else 0
            ),
        }
    
    def get_hourly_stats(self, hours: int = 24) -> List[Dict[str, Any]]:
        """获取小时级统计"""
        stats = []
        now = datetime.now()
        
        for i in range(hours):
            hour = now.replace(minute=0, second=0, microsecond=0)
            hour_key = hour.strftime("%Y-%m-%d-%H")
            
            if hour_key in self._hourly_stats:
                stats.append({
                    "hour": hour_key,
                    **self._hourly_stats[hour_key]
                })
        
        return stats
    
    def get_span(self, span_id: str) -> Optional[ModelCallSpan]:
        """获取Span"""
        return self._active_spans.get(span_id)
    
    def get_active_spans(self) -> List[ModelCallSpan]:
        """获取所有活跃Span"""
        return list(self._active_spans.values())
    
    def set_alert_threshold(self, metric: str, threshold: float):
        """设置告警阈值"""
        if metric in self._alert_thresholds:
            self._alert_thresholds[metric] = threshold
            logger.info(f"[ModelMonitor] 设置告警阈值: {metric}={threshold}")
    
    def export_metrics(self, format: str = "json") -> str:
        """导出指标"""
        metrics = {
            "usage": self.get_usage_stats(),
            "hourly": self.get_hourly_stats(24),
            "active_spans": len(self._active_spans),
            "thresholds": self._alert_thresholds,
        }
        
        if format == "json":
            return json.dumps(metrics, default=str, indent=2)
        else:
            return str(metrics)
    
    def reset(self):
        """重置统计"""
        self._usage_tracker = TokenUsageTracker()
        self._active_spans.clear()
        self._completed_traces.clear()
        self._hourly_stats.clear()
        logger.info("[ModelMonitor] 统计已重置")


class CostBudget:
    """
    成本预算管理
    
    示例:
        budget = CostBudget(daily_limit=10.0, monthly_limit=200.0)
        
        if budget.can_spend(estimated_cost=0.5):
            response = await model.generate(...)
            budget.record_cost(response.cost)
    """
    
    def __init__(
        self,
        daily_limit: float = 100.0,
        monthly_limit: float = 3000.0,
        per_call_limit: float = 1.0,
        on_limit_reached: Optional[Callable[[str], None]] = None
    ):
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self.per_call_limit = per_call_limit
        self.on_limit_reached = on_limit_reached
        
        self._daily_spend: Dict[str, float] = defaultdict(float)
        self._monthly_spend: Dict[str, float] = defaultdict(float)
    
    def can_spend(self, amount: float) -> bool:
        """是否可以支出"""
        if amount > self.per_call_limit:
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_spend[today] + amount > self.daily_limit:
            if self.on_limit_reached:
                self.on_limit_reached("daily")
            return False
        
        month = datetime.now().strftime("%Y-%m")
        if self._monthly_spend[month] + amount > self.monthly_limit:
            if self.on_limit_reached:
                self.on_limit_reached("monthly")
            return False
        
        return True
    
    def record_cost(self, amount: float, agent_name: Optional[str] = None):
        """记录成本"""
        today = datetime.now().strftime("%Y-%m-%d")
        self._daily_spend[today] += amount
        
        month = datetime.now().strftime("%Y-%m")
        self._monthly_spend[month] += amount
        
        logger.info(
            f"[CostBudget] 记录成本: ${amount:.4f}, "
            f"今日: ${self._daily_spend[today]:.2f}, "
            f"本月: ${self._monthly_spend[month]:.2f}"
        )
    
    def get_daily_spend(self) -> float:
        """获取今日支出"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self._daily_spend[today]
    
    def get_monthly_spend(self) -> float:
        """获取本月支出"""
        month = datetime.now().strftime("%Y-%m")
        return self._monthly_spend[month]
    
    def get_remaining_budget(self) -> Dict[str, float]:
        """获取剩余预算"""
        return {
            "daily": self.daily_limit - self.get_daily_spend(),
            "monthly": self.monthly_limit - self.get_monthly_spend(),
            "per_call": self.per_call_limit,
        }


model_monitor = ModelMonitor()