"""
Team Monitor - 团队监控

实现团队和Agent的监控能力：
1. 执行进度跟踪 - 跟踪任务执行进度
2. 性能指标收集 - 收集Agent性能指标
3. 资源使用监控 - 监控资源使用情况
4. 异常告警 - 异常情况告警

@see ARCHITECTURE.md#12.8-teammonitor-监控器
"""

from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime
from enum import Enum
import asyncio
import logging
import statistics
from collections import defaultdict

from pydantic import BaseModel, Field

from .team import AgentStatus
from .planner import TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


class ExecutionPhase(str, Enum):
    """执行阶段"""
    INITIALIZING = "initializing"
    PLANNING = "planning"
    EXECUTING = "executing"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionProgress(BaseModel):
    """执行进度"""
    execution_id: str
    phase: ExecutionPhase = ExecutionPhase.INITIALIZING
    progress: float = 0.0  # 0.0 - 1.0
    
    total_tasks: int = 0
    completed_tasks: int = 0
    running_tasks: int = 0
    pending_tasks: int = 0
    failed_tasks: int = 0
    
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    estimated_completion: Optional[datetime] = None
    
    current_task: Optional[str] = None
    
    def update_progress(self) -> None:
        """更新进度"""
        if self.total_tasks > 0:
            self.progress = self.completed_tasks / self.total_tasks
        self.updated_at = datetime.now()
    
    def get_elapsed_seconds(self) -> float:
        """获取已用时间（秒）"""
        return (datetime.now() - self.started_at).total_seconds()


class AgentMetrics(BaseModel):
    """Agent指标"""
    agent_id: str
    agent_type: str
    
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_running: int = 0
    
    total_execution_time_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    min_execution_time_ms: Optional[float] = None
    max_execution_time_ms: Optional[float] = None
    
    success_rate: float = 0.0
    utilization: float = 0.0  # 利用率 0-1
    
    last_task_at: Optional[datetime] = None
    last_error: Optional[str] = None
    
    execution_times: List[float] = Field(default_factory=list)
    
    def record_task(self, execution_time_ms: float, success: bool) -> None:
        """记录任务执行"""
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
        
        self.execution_times.append(execution_time_ms)
        self.total_execution_time_ms += execution_time_ms
        self.last_task_at = datetime.now()
        
        if len(self.execution_times) > 100:
            self.execution_times = self.execution_times[-100:]
        
        total_tasks = self.tasks_completed + self.tasks_failed
        if total_tasks > 0:
            self.success_rate = self.tasks_completed / total_tasks
            self.avg_execution_time_ms = self.total_execution_time_ms / total_tasks
        
        if self.min_execution_time_ms is None or execution_time_ms < self.min_execution_time_ms:
            self.min_execution_time_ms = execution_time_ms
        if self.max_execution_time_ms is None or execution_time_ms > self.max_execution_time_ms:
            self.max_execution_time_ms = execution_time_ms
    
    def get_p50_execution_time(self) -> Optional[float]:
        """获取P50执行时间"""
        if not self.execution_times:
            return None
        return statistics.median(self.execution_times)
    
    def get_p95_execution_time(self) -> Optional[float]:
        """获取P95执行时间"""
        if not self.execution_times:
            return None
        sorted_times = sorted(self.execution_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]


class TeamMetrics(BaseModel):
    """团队指标"""
    team_id: str
    team_name: str
    
    total_agents: int = 0
    active_agents: int = 0
    idle_agents: int = 0
    error_agents: int = 0
    
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    
    total_execution_time_ms: float = 0.0
    avg_task_time_ms: float = 0.0
    
    throughput: float = 0.0  # tasks per minute
    
    parallelism: float = 0.0  # 平均并行度
    
    started_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def update(
        self,
        agent_metrics: Dict[str, AgentMetrics],
    ) -> None:
        """更新团队指标"""
        self.total_agents = len(agent_metrics)
        self.active_agents = sum(1 for m in agent_metrics.values() if m.tasks_running > 0)
        self.error_agents = sum(1 for m in agent_metrics.values() if m.last_error is not None)
        self.idle_agents = self.total_agents - self.active_agents - self.error_agents
        
        self.completed_tasks = sum(m.tasks_completed for m in agent_metrics.values())
        self.failed_tasks = sum(m.tasks_failed for m in agent_metrics.values())
        self.total_tasks = self.completed_tasks + self.failed_tasks
        
        if self.completed_tasks > 0:
            self.total_execution_time_ms = sum(
                m.total_execution_time_ms for m in agent_metrics.values()
            )
            self.avg_task_time_ms = self.total_execution_time_ms / self.completed_tasks
        
        elapsed = (datetime.now() - self.started_at).total_seconds() / 60.0
        if elapsed > 0:
            self.throughput = self.completed_tasks / elapsed
        
        self.updated_at = datetime.now()


class AlertLevel(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Alert(BaseModel):
    """告警"""
    id: str = Field(default_factory=lambda: str(hash(datetime.now().isoformat()))[:8])
    level: AlertLevel
    source: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    acknowledged: bool = False


class TeamMonitor:
    """
    团队监控器
    
    提供对Agent团队执行过程的全面监控。
    
    @example
    ```python
    monitor = TeamMonitor()
    monitor.start_execution("exec-123")
    
    # 跟踪任务
    monitor.update_task_progress("exec-123", "task-1", TaskStatus.RUNNING)
    monitor.update_task_progress("exec-123", "task-1", TaskStatus.COMPLETED)
    
    # 记录Agent指标
    monitor.record_agent_task("agent-1", 150.0, success=True)
    
    # 获取进度
    progress = monitor.get_execution_progress("exec-123")
    print(f"Progress: {progress.progress:.1%}")
    
    # 获取指标
    metrics = monitor.get_team_metrics()
    print(f"Throughput: {metrics.throughput:.2f} tasks/min")
    ```
    """
    
    def __init__(
        self,
        alert_handlers: Optional[List[Callable[[Alert], Awaitable[None]]]] = None,
        metrics_retention_minutes: int = 60,
    ):
        self._alert_handlers = alert_handlers or []
        self._retention_minutes = metrics_retention_minutes
        
        self._execution_progress: Dict[str, ExecutionProgress] = {}
        self._agent_metrics: Dict[str, AgentMetrics] = {}
        self._team_metrics: Dict[str, TeamMetrics] = {}
        self._alerts: List[Alert] = []
        
        self._lock = asyncio.Lock()
    
    def start_execution(
        self,
        execution_id: str,
        total_tasks: int = 0,
    ) -> ExecutionProgress:
        """开始执行"""
        progress = ExecutionProgress(
            execution_id=execution_id,
            total_tasks=total_tasks,
            phase=ExecutionPhase.INITIALIZING,
        )
        self._execution_progress[execution_id] = progress
        logger.info(f"[Monitor] Started execution: {execution_id}")
        return progress
    
    def update_execution_phase(
        self,
        execution_id: str,
        phase: ExecutionPhase,
    ) -> Optional[ExecutionProgress]:
        """更新执行阶段"""
        progress = self._execution_progress.get(execution_id)
        if progress:
            progress.phase = phase
            progress.updated_at = datetime.now()
        return progress
    
    def update_task_progress(
        self,
        execution_id: str,
        task_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
    ) -> Optional[ExecutionProgress]:
        """更新任务进度"""
        progress = self._execution_progress.get(execution_id)
        if not progress:
            return None
        
        if status == TaskStatus.RUNNING:
            progress.running_tasks += 1
            progress.pending_tasks -= 1
            progress.current_task = task_id
        elif status == TaskStatus.COMPLETED:
            progress.completed_tasks += 1
            progress.running_tasks -= 1
            progress.current_task = None
        elif status == TaskStatus.FAILED:
            progress.failed_tasks += 1
            progress.running_tasks -= 1
            progress.current_task = None
        
        progress.update_progress()
        
        if progress.progress >= 1.0:
            progress.phase = ExecutionPhase.COMPLETED
        
        return progress
    
    def get_execution_progress(
        self,
        execution_id: str,
    ) -> Optional[ExecutionProgress]:
        """获取执行进度"""
        return self._execution_progress.get(execution_id)
    
    def register_agent(
        self,
        agent_id: str,
        agent_type: str,
    ) -> AgentMetrics:
        """注册Agent"""
        metrics = AgentMetrics(
            agent_id=agent_id,
            agent_type=agent_type,
        )
        self._agent_metrics[agent_id] = metrics
        logger.debug(f"[Monitor] Registered agent: {agent_id} ({agent_type})")
        return metrics
    
    def record_agent_task(
        self,
        agent_id: str,
        execution_time_ms: float,
        success: bool,
        error: Optional[str] = None,
    ) -> Optional[AgentMetrics]:
        """记录Agent任务执行"""
        metrics = self._agent_metrics.get(agent_id)
        if not metrics:
            return None
        
        metrics.record_task(execution_time_ms, success)
        
        if not success and error:
            metrics.last_error = error
            if len(error) > 200:
                error = error[:200] + "..."
            self._create_alert(
                level=AlertLevel.WARNING,
                source=f"agent:{agent_id}",
                message=f"Task failed: {error}",
                details={"execution_time_ms": execution_time_ms},
            )
        
        return metrics
    
    def get_agent_metrics(
        self,
        agent_id: str,
    ) -> Optional[AgentMetrics]:
        """获取Agent指标"""
        return self._agent_metrics.get(agent_id)
    
    def get_all_agent_metrics(self) -> Dict[str, AgentMetrics]:
        """获取所有Agent指标"""
        return dict(self._agent_metrics)
    
    def update_team_metrics(
        self,
        team_id: str,
        team_name: str = "default",
    ) -> TeamMetrics:
        """更新团队指标"""
        if team_id not in self._team_metrics:
            self._team_metrics[team_id] = TeamMetrics(
                team_id=team_id,
                team_name=team_name,
            )
        
        metrics = self._team_metrics[team_id]
        metrics.update(self._agent_metrics)
        return metrics
    
    def get_team_metrics(
        self,
        team_id: str = "default",
    ) -> Optional[TeamMetrics]:
        """获取团队指标"""
        return self._team_metrics.get(team_id)
    
    def record_alert(
        self,
        level: AlertLevel,
        source: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Alert:
        """记录告警"""
        return self._create_alert(level, source, message, details or {})
    
    def _create_alert(
        self,
        level: AlertLevel,
        source: str,
        message: str,
        details: Dict[str, Any],
    ) -> Alert:
        """创建告警"""
        alert = Alert(
            level=level,
            source=source,
            message=message,
            details=details,
        )
        self._alerts.append(alert)
        
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]
        
        if level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
            logger.error(f"[Monitor] Alert [{level.value}]: {message}")
        elif level == AlertLevel.WARNING:
            logger.warning(f"[Monitor] Alert [{level.value}]: {message}")
        
        for handler in self._alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(alert))
                else:
                    handler(alert)
            except Exception as e:
                logger.error(f"[Monitor] Alert handler error: {e}")
        
        return alert
    
    def get_alerts(
        self,
        level: Optional[AlertLevel] = None,
        acknowledged: Optional[bool] = None,
        limit: int = 20,
    ) -> List[Alert]:
        """获取告警"""
        alerts = self._alerts
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        
        return alerts[-limit:]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        return {
            "total_executions": len(self._execution_progress),
            "active_executions": sum(
                1 for p in self._execution_progress.values()
                if p.phase not in [ExecutionPhase.COMPLETED, ExecutionPhase.FAILED]
            ),
            "total_agents": len(self._agent_metrics),
            "active_agents": sum(
                1 for m in self._agent_metrics.values()
                if m.tasks_running > 0
            ),
            "total_alerts": len(self._alerts),
            "unacknowledged_alerts": sum(
                1 for a in self._alerts if not a.acknowledged
            ),
            "teams": len(self._team_metrics),
        }
    
    def get_detailed_report(self) -> Dict[str, Any]:
        """获取详细报告"""
        return {
            "summary": self.get_summary(),
            "executions": {
                exec_id: {
                    "phase": progress.phase.value,
                    "progress": progress.progress,
                    "total_tasks": progress.total_tasks,
                    "completed_tasks": progress.completed_tasks,
                    "failed_tasks": progress.failed_tasks,
                    "elapsed_seconds": progress.get_elapsed_seconds(),
                }
                for exec_id, progress in self._execution_progress.items()
            },
            "agents": {
                agent_id: {
                    "type": metrics.agent_type,
                    "tasks_completed": metrics.tasks_completed,
                    "tasks_failed": metrics.tasks_failed,
                    "success_rate": metrics.success_rate,
                    "avg_execution_time_ms": metrics.avg_execution_time_ms,
                    "p50_execution_time_ms": metrics.get_p50_execution_time(),
                    "p95_execution_time_ms": metrics.get_p95_execution_time(),
                }
                for agent_id, metrics in self._agent_metrics.items()
            },
            "recent_alerts": [
                {
                    "id": alert.id,
                    "level": alert.level.value,
                    "source": alert.source,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "acknowledged": alert.acknowledged,
                }
                for alert in self._alerts[-10:]
            ],
        }
    
    def cleanup_old_metrics(self) -> int:
        """清理旧指标"""
        cleanup_count = 0
        
        cutoff = datetime.now()
        
        completed_executions = [
            exec_id for exec_id, progress in self._execution_progress.items()
            if progress.phase in [ExecutionPhase.COMPLETED, ExecutionPhase.FAILED]
        ]
        
        for exec_id in completed_executions:
            progress = self._execution_progress[exec_id]
            if progress.updated_at:
                elapsed = (cutoff - progress.updated_at).total_seconds() / 60
                if elapsed > self._retention_minutes:
                    del self._execution_progress[exec_id]
                    cleanup_count += 1
        
        if cleanup_count > 0:
            logger.debug(f"[Monitor] Cleaned up {cleanup_count} old metrics")
        
        return cleanup_count