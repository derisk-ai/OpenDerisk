"""
Agent Metrics - Agent 监控指标

实现 Agent 运行时健康监控，提供：
- 步骤耗时追踪
- 状态转换监控
- 检查点大小监控
- 内存使用监控
- 健康分数计算

此模块支持 P4 集成改进。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .state_machine import AgentState

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""

    EXCELLENT = "excellent"  # 优秀 (90-100)
    GOOD = "good"  # 良好 (70-89)
    FAIR = "fair"  # 一般 (50-69)
    POOR = "poor"  # 较差 (30-49)
    CRITICAL = "critical"  # 危险 (0-29)


@dataclass
class StepMetric:
    """步骤指标"""

    step_index: int
    state: str
    duration_ms: float
    success: bool
    timestamp: datetime
    tokens_used: int = 0
    error: Optional[str] = None


@dataclass
class StateTransitionMetric:
    """状态转换指标"""

    from_state: str
    to_state: str
    duration_ms: float
    timestamp: datetime
    is_valid: bool = True


@dataclass
class CheckpointMetric:
    """检查点指标"""

    checkpoint_id: str
    size_bytes: int
    creation_time_ms: float
    timestamp: datetime


@dataclass
class MemoryUsageMetric:
    """内存使用指标"""

    layer: str
    tokens_used: int
    tokens_limit: int
    usage_percent: float
    timestamp: datetime


@dataclass
class AgentHealthReport:
    """Agent 健康报告"""

    health_score: float
    health_status: HealthStatus

    # 步骤统计
    total_steps: int
    successful_steps: int
    failed_steps: int
    avg_step_duration_ms: float
    max_step_duration_ms: float

    # 状态转换统计
    total_transitions: int
    invalid_transitions: int

    # 检查点统计
    total_checkpoints: int
    avg_checkpoint_size_bytes: float
    total_checkpoint_size_bytes: int

    # 内存统计
    avg_memory_usage_percent: float
    peak_memory_usage_percent: float

    # 问题诊断
    issues: List[str]
    recommendations: List[str]


class AgentMetrics:
    """
    Agent 监控指标

    收集并分析 Agent 运行时指标，计算健康分数。

    示例:
        metrics = AgentMetrics()

        # 记录步骤
        metrics.record_step(0, "THINKING", 150.5, True, 100)

        # 记录状态转换
        metrics.record_transition("THINKING", "ACTING", 10.5)

        # 计算健康分数
        report = metrics.get_health_report()
        print(f"Health Score: {report.health_score}")
    """

    # 健康分数权重
    WEIGHT_STEP_DURATION = 0.25
    WEIGHT_INVALID_TRANSITIONS = 0.20
    WEIGHT_CHECKPOINT_SIZE = 0.15
    WEIGHT_MEMORY_USAGE = 0.20
    WEIGHT_ERROR_RATE = 0.20

    # 阈值配置
    MAX_STEP_DURATION_WARNING_MS = 30000  # 30秒
    MAX_STEP_DURATION_CRITICAL_MS = 60000  # 60秒
    MAX_CHECKPOINT_SIZE_WARNING_MB = 10
    MAX_CHECKPOINT_SIZE_CRITICAL_MB = 50
    MAX_MEMORY_USAGE_WARNING_PERCENT = 80
    MAX_MEMORY_USAGE_CRITICAL_PERCENT = 95

    def __init__(
        self,
        max_history_steps: int = 100,
        max_history_transitions: int = 200,
        max_history_checkpoints: int = 50,
    ):
        """
        初始化 Agent 指标收集器

        Args:
            max_history_steps: 最大保存步骤数
            max_history_transitions: 最大保存转换数
            max_history_checkpoints: 最大保存检查点数
        """
        self.max_history_steps = max_history_steps
        self.max_history_transitions = max_history_transitions
        self.max_history_checkpoints = max_history_checkpoints

        # 指标历史
        self._step_metrics: deque = deque(maxlen=max_history_steps)
        self._transition_metrics: deque = deque(maxlen=max_history_transitions)
        self._checkpoint_metrics: deque = deque(maxlen=max_history_checkpoints)
        self._memory_metrics: deque = deque(maxlen=max_history_steps)

        # 累计统计
        self._total_steps = 0
        self._successful_steps = 0
        self._failed_steps = 0
        self._total_tokens = 0

        logger.info(
            f"[AgentMetrics] Initialized with max_history_steps={max_history_steps}"
        )

    def record_step(
        self,
        step_index: int,
        state: str,
        duration_ms: float,
        success: bool,
        tokens_used: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """
        记录步骤指标

        Args:
            step_index: 步骤索引
            state: 状态名称
            duration_ms: 耗时（毫秒）
            success: 是否成功
            tokens_used: 使用的 token 数
            error: 错误信息（如果有）
        """
        metric = StepMetric(
            step_index=step_index,
            state=state,
            duration_ms=duration_ms,
            success=success,
            timestamp=datetime.now(),
            tokens_used=tokens_used,
            error=error,
        )

        self._step_metrics.append(metric)

        # 更新累计统计
        self._total_steps += 1
        if success:
            self._successful_steps += 1
        else:
            self._failed_steps += 1
        self._total_tokens += tokens_used

        logger.debug(
            f"[AgentMetrics] Recorded step {step_index}: state={state}, "
            f"duration={duration_ms:.2f}ms, success={success}"
        )

    def record_transition(
        self,
        from_state: str,
        to_state: str,
        duration_ms: float,
        is_valid: bool = True,
    ) -> None:
        """
        记录状态转换指标

        Args:
            from_state: 源状态
            to_state: 目标状态
            duration_ms: 转换耗时（毫秒）
            is_valid: 转换是否有效
        """
        metric = StateTransitionMetric(
            from_state=from_state,
            to_state=to_state,
            duration_ms=duration_ms,
            timestamp=datetime.now(),
            is_valid=is_valid,
        )

        self._transition_metrics.append(metric)

        logger.debug(
            f"[AgentMetrics] Recorded transition: {from_state} -> {to_state} "
            f"({duration_ms:.2f}ms, valid={is_valid})"
        )

    def record_checkpoint(
        self,
        checkpoint_id: str,
        size_bytes: int,
        creation_time_ms: float,
    ) -> None:
        """
        记录检查点指标

        Args:
            checkpoint_id: 检查点ID
            size_bytes: 大小（字节）
            creation_time_ms: 创建耗时（毫秒）
        """
        metric = CheckpointMetric(
            checkpoint_id=checkpoint_id,
            size_bytes=size_bytes,
            creation_time_ms=creation_time_ms,
            timestamp=datetime.now(),
        )

        self._checkpoint_metrics.append(metric)

        logger.debug(
            f"[AgentMetrics] Recorded checkpoint {checkpoint_id[:8]}: "
            f"size={size_bytes}bytes, time={creation_time_ms:.2f}ms"
        )

    def record_memory_usage(
        self,
        layer: str,
        tokens_used: int,
        tokens_limit: int,
    ) -> None:
        """
        记录内存使用指标

        Args:
            layer: 内存层级
            tokens_used: 已使用 tokens
            tokens_limit: 限制 tokens
        """
        usage_percent = (tokens_used / tokens_limit * 100) if tokens_limit > 0 else 0

        metric = MemoryUsageMetric(
            layer=layer,
            tokens_used=tokens_used,
            tokens_limit=tokens_limit,
            usage_percent=usage_percent,
            timestamp=datetime.now(),
        )

        self._memory_metrics.append(metric)

        logger.debug(
            f"[AgentMetrics] Recorded memory usage for {layer}: "
            f"{tokens_used}/{tokens_limit} ({usage_percent:.1f}%)"
        )

    def calculate_health_score(self) -> float:
        """
        计算健康分数 (0-100)

        综合考虑：
        1. 步骤耗时是否正常
        2. 状态转换是否有效
        3. 检查点大小是否合理
        4. 内存使用是否健康
        5. 错误率是否可接受
        """
        score = 100.0

        # 1. 步骤耗时检查
        step_score = self._calculate_step_score()
        score -= (100 - step_score) * self.WEIGHT_STEP_DURATION

        # 2. 无效转换惩罚
        transition_penalty = self._calculate_transition_penalty()
        score -= transition_penalty * self.WEIGHT_INVALID_TRANSITIONS

        # 3. 检查点大小检查
        checkpoint_penalty = self._calculate_checkpoint_penalty()
        score -= checkpoint_penalty * self.WEIGHT_CHECKPOINT_SIZE

        # 4. 内存使用检查
        memory_penalty = self._calculate_memory_penalty()
        score -= memory_penalty * self.WEIGHT_MEMORY_USAGE

        # 5. 错误率检查
        error_penalty = self._calculate_error_penalty()
        score -= error_penalty * self.WEIGHT_ERROR_RATE

        return max(0.0, min(100.0, score))

    def _calculate_step_score(self) -> float:
        """计算步骤得分"""
        if not self._step_metrics:
            return 100.0

        durations = [m.duration_ms for m in self._step_metrics]
        avg_duration = sum(durations) / len(durations)
        max_duration = max(durations)

        score = 100.0

        # 平均耗时过长
        if avg_duration > self.MAX_STEP_DURATION_WARNING_MS:
            score -= 10

        # 最大耗时过长
        if max_duration > self.MAX_STEP_DURATION_CRITICAL_MS:
            score -= 20
        elif max_duration > self.MAX_STEP_DURATION_WARNING_MS:
            score -= 10

        return max(0, score)

    def _calculate_transition_penalty(self) -> float:
        """计算无效转换惩罚"""
        if not self._transition_metrics:
            return 0.0

        invalid_count = sum(1 for m in self._transition_metrics if not m.is_valid)

        # 每个无效转换扣 5 分
        return min(100, invalid_count * 5)

    def _calculate_checkpoint_penalty(self) -> float:
        """计算检查点惩罚"""
        if not self._checkpoint_metrics:
            return 0.0

        sizes = [m.size_bytes for m in self._checkpoint_metrics]
        avg_size = sum(sizes) / len(sizes)

        avg_size_mb = avg_size / (1024 * 1024)

        if avg_size_mb > self.MAX_CHECKPOINT_SIZE_CRITICAL_MB:
            return 20
        elif avg_size_mb > self.MAX_CHECKPOINT_SIZE_WARNING_MB:
            return 10

        return 0

    def _calculate_memory_penalty(self) -> float:
        """计算内存使用惩罚"""
        if not self._memory_metrics:
            return 0.0

        usages = [m.usage_percent for m in self._memory_metrics]
        avg_usage = sum(usages) / len(usages)
        peak_usage = max(usages)

        penalty = 0.0

        if avg_usage > self.MAX_MEMORY_USAGE_WARNING_PERCENT:
            penalty += 10

        if peak_usage > self.MAX_MEMORY_USAGE_CRITICAL_PERCENT:
            penalty += 15
        elif peak_usage > self.MAX_MEMORY_USAGE_WARNING_PERCENT:
            penalty += 8

        return penalty

    def _calculate_error_penalty(self) -> float:
        """计算错误率惩罚"""
        if self._total_steps == 0:
            return 0.0

        error_rate = self._failed_steps / self._total_steps

        # 错误率越高，惩罚越大
        if error_rate > 0.5:
            return 50
        elif error_rate > 0.3:
            return 30
        elif error_rate > 0.1:
            return 15
        elif error_rate > 0.05:
            return 5

        return 0

    def get_health_status(self, score: Optional[float] = None) -> HealthStatus:
        """根据分数获取健康状态"""
        score = score or self.calculate_health_score()

        if score >= 90:
            return HealthStatus.EXCELLENT
        elif score >= 70:
            return HealthStatus.GOOD
        elif score >= 50:
            return HealthStatus.FAIR
        elif score >= 30:
            return HealthStatus.POOR
        else:
            return HealthStatus.CRITICAL

    def get_health_report(self) -> AgentHealthReport:
        """
        生成完整健康报告
        """
        health_score = self.calculate_health_score()
        health_status = self.get_health_status(health_score)

        # 步骤统计
        step_durations = [m.duration_ms for m in self._step_metrics]
        avg_step_duration = (
            sum(step_durations) / len(step_durations) if step_durations else 0
        )
        max_step_duration = max(step_durations) if step_durations else 0

        # 状态转换统计
        invalid_transitions = sum(1 for m in self._transition_metrics if not m.is_valid)

        # 检查点统计
        checkpoint_sizes = [m.size_bytes for m in self._checkpoint_metrics]
        total_checkpoint_size = sum(checkpoint_sizes)
        avg_checkpoint_size = (
            total_checkpoint_size / len(checkpoint_sizes) if checkpoint_sizes else 0
        )

        # 内存统计
        memory_usages = [m.usage_percent for m in self._memory_metrics]
        avg_memory_usage = (
            sum(memory_usages) / len(memory_usages) if memory_usages else 0
        )
        peak_memory_usage = max(memory_usages) if memory_usages else 0

        # 诊断问题和建议
        issues = self._diagnose_issues()
        recommendations = self._generate_recommendations(issues)

        return AgentHealthReport(
            health_score=health_score,
            health_status=health_status,
            total_steps=self._total_steps,
            successful_steps=self._successful_steps,
            failed_steps=self._failed_steps,
            avg_step_duration_ms=avg_step_duration,
            max_step_duration_ms=max_step_duration,
            total_transitions=len(self._transition_metrics),
            invalid_transitions=invalid_transitions,
            total_checkpoints=len(self._checkpoint_metrics),
            avg_checkpoint_size_bytes=avg_checkpoint_size,
            total_checkpoint_size_bytes=total_checkpoint_size,
            avg_memory_usage_percent=avg_memory_usage,
            peak_memory_usage_percent=peak_memory_usage,
            issues=issues,
            recommendations=recommendations,
        )

    def _diagnose_issues(self) -> List[str]:
        """诊断问题"""
        issues = []

        # 步骤耗时问题
        step_durations = [m.duration_ms for m in self._step_metrics]
        if step_durations:
            avg_duration = sum(step_durations) / len(step_durations)
            if avg_duration > self.MAX_STEP_DURATION_WARNING_MS:
                issues.append(f"High average step duration: {avg_duration:.1f}ms")

        # 无效转换问题
        invalid_count = sum(1 for m in self._transition_metrics if not m.is_valid)
        if invalid_count > 0:
            issues.append(f"Invalid state transitions detected: {invalid_count}")

        # 检查点大小问题
        checkpoint_sizes = [m.size_bytes for m in self._checkpoint_metrics]
        if checkpoint_sizes:
            avg_size_mb = (sum(checkpoint_sizes) / len(checkpoint_sizes)) / (
                1024 * 1024
            )
            if avg_size_mb > self.MAX_CHECKPOINT_SIZE_WARNING_MB:
                issues.append(f"Large checkpoint size: {avg_size_mb:.1f}MB")

        # 内存使用问题
        memory_usages = [m.usage_percent for m in self._memory_metrics]
        if memory_usages:
            peak_usage = max(memory_usages)
            if peak_usage > self.MAX_MEMORY_USAGE_WARNING_PERCENT:
                issues.append(f"High memory usage: {peak_usage:.1f}%")

        # 错误率问题
        if self._total_steps > 0:
            error_rate = self._failed_steps / self._total_steps
            if error_rate > 0.1:
                issues.append(f"High error rate: {error_rate:.1%}")

        return issues

    def _generate_recommendations(self, issues: List[str]) -> List[str]:
        """根据问题生成建议"""
        recommendations = []

        for issue in issues:
            if "step duration" in issue.lower():
                recommendations.append(
                    "Consider optimizing step execution or increasing timeout"
                )

            if "invalid state transition" in issue.lower():
                recommendations.append(
                    "Review state machine configuration and transition rules"
                )

            if "checkpoint size" in issue.lower():
                recommendations.append(
                    "Enable checkpoint compression or reduce state size"
                )

            if "memory usage" in issue.lower():
                recommendations.append(
                    "Increase memory limits or enable memory compaction"
                )

            if "error rate" in issue.lower():
                recommendations.append(
                    "Review error handling and implement retry mechanisms"
                )

        return list(set(recommendations))  # 去重

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        health_score = self.calculate_health_score()

        return {
            "health_score": health_score,
            "health_status": self.get_health_status(health_score).value,
            "total_steps": self._total_steps,
            "successful_steps": self._successful_steps,
            "failed_steps": self._failed_steps,
            "success_rate": (
                self._successful_steps / self._total_steps
                if self._total_steps > 0
                else 0
            ),
            "total_tokens": self._total_tokens,
            "history_sizes": {
                "steps": len(self._step_metrics),
                "transitions": len(self._transition_metrics),
                "checkpoints": len(self._checkpoint_metrics),
                "memory": len(self._memory_metrics),
            },
        }

    def reset(self) -> None:
        """重置所有指标"""
        self._step_metrics.clear()
        self._transition_metrics.clear()
        self._checkpoint_metrics.clear()
        self._memory_metrics.clear()

        self._total_steps = 0
        self._successful_steps = 0
        self._failed_steps = 0
        self._total_tokens = 0

        logger.info("[AgentMetrics] Metrics reset")

    def export_metrics(self) -> Dict[str, Any]:
        """导出所有指标数据"""
        return {
            "steps": [
                {
                    "step_index": m.step_index,
                    "state": m.state,
                    "duration_ms": m.duration_ms,
                    "success": m.success,
                    "tokens_used": m.tokens_used,
                    "error": m.error,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self._step_metrics
            ],
            "transitions": [
                {
                    "from_state": m.from_state,
                    "to_state": m.to_state,
                    "duration_ms": m.duration_ms,
                    "is_valid": m.is_valid,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self._transition_metrics
            ],
            "checkpoints": [
                {
                    "checkpoint_id": m.checkpoint_id,
                    "size_bytes": m.size_bytes,
                    "creation_time_ms": m.creation_time_ms,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self._checkpoint_metrics
            ],
            "memory": [
                {
                    "layer": m.layer,
                    "tokens_used": m.tokens_used,
                    "tokens_limit": m.tokens_limit,
                    "usage_percent": m.usage_percent,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in self._memory_metrics
            ],
            "summary": self.get_summary(),
        }
