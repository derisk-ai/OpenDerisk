"""
Monitoring Dashboard API - 任务进度可视化监控

提供任务进度实时监控和可视化:
1. 实时进度追踪
2. WebSocket实时推送
3. 任务历史查询
4. 统计分析API
5. 健康状态监控

此模块实现 P1 改进方案。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import json

logger = logging.getLogger(__name__)


class DashboardEventType(Enum):
    """仪表盘事件类型"""

    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    SUBAGENT_STARTED = "subagent_started"
    SUBAGENT_COMPLETED = "subagent_completed"
    AGENT_SLEEP = "agent_sleep"
    AGENT_WAKEUP = "agent_wakeup"
    WORKER_STATUS = "worker_status"
    HEALTH_ALERT = "health_alert"


@dataclass
class DashboardEvent:
    """仪表盘事件"""

    event_type: DashboardEventType
    timestamp: datetime = field(default_factory=datetime.now)
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    subagent_name: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "subagent_name": self.subagent_name,
            "data": self.data,
        }


@dataclass
class TaskProgress:
    """任务进度"""

    task_id: str
    goal: str
    status: str = "pending"

    # 进度信息
    total_steps: int = 0
    current_step: int = 0
    progress_percent: float = 0.0

    # 子任务信息
    total_subtasks: int = 0
    completed_subtasks: int = 0
    failed_subtasks: int = 0

    # 时间信息
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 资源使用
    tokens_used: int = 0
    llm_calls: int = 0

    # 错误信息
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "total_steps": self.total_steps,
            "current_step": self.current_step,
            "progress_percent": self.progress_percent,
            "total_subtasks": self.total_subtasks,
            "completed_subtasks": self.completed_subtasks,
            "failed_subtasks": self.failed_subtasks,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "tokens_used": self.tokens_used,
            "llm_calls": self.llm_calls,
            "errors": self.errors,
        }


@dataclass
class SubagentProgress:
    """子Agent进度"""

    conversation_id: str
    subagent_name: str
    parent_task_id: str
    status: str = "pending"

    # 时间信息
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 结果
    result: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "subagent_name": self.subagent_name,
            "parent_task_id": self.parent_task_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": self.result[:500] if self.result else None,
            "error": self.error,
        }


@dataclass
class WorkerProgress:
    """Worker进度"""

    worker_id: str
    status: str = "idle"
    pid: Optional[int] = None

    # 任务统计
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    current_tasks: int = 0

    # 资源使用
    cpu_percent: float = 0.0
    memory_mb: float = 0.0

    # 时间信息
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": self.status,
            "pid": self.pid,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "current_tasks": self.current_tasks,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat()
            if self.last_heartbeat
            else None,
        }


@dataclass
class HealthAlert:
    """健康告警"""

    alert_id: str
    alert_type: str
    severity: str  # info, warning, error, critical
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class MonitoringDashboard:
    """
    监控仪表盘

    提供实时任务进度监控和可视化API
    """

    def __init__(
        self,
        max_history_events: int = 1000,
        max_history_tasks: int = 100,
    ):
        self.max_history_events = max_history_events
        self.max_history_tasks = max_history_tasks

        # 状态存储
        self._tasks: Dict[str, TaskProgress] = {}
        self._subagents: Dict[str, SubagentProgress] = {}
        self._workers: Dict[str, WorkerProgress] = {}
        self._alerts: List[HealthAlert] = []
        self._events: List[DashboardEvent] = []

        # WebSocket订阅者
        self._subscribers: Set[asyncio.Queue] = set()

        # 统计
        self._total_tasks_created = 0
        self._total_tasks_completed = 0
        self._total_tasks_failed = 0

        self._lock = asyncio.Lock()

        logger.info("[MonitoringDashboard] Initialized")

    # =========================================================================
    # 事件记录
    # =========================================================================

    async def record_event(
        self,
        event_type: DashboardEventType,
        task_id: str = None,
        agent_id: str = None,
        subagent_name: str = None,
        data: Dict[str, Any] = None,
    ) -> DashboardEvent:
        """记录事件"""
        event = DashboardEvent(
            event_type=event_type,
            task_id=task_id,
            agent_id=agent_id,
            subagent_name=subagent_name,
            data=data or {},
        )

        async with self._lock:
            self._events.append(event)

            # 限制历史记录大小
            if len(self._events) > self.max_history_events:
                self._events = self._events[-self.max_history_events :]

        # 广播给订阅者
        await self._broadcast_event(event)

        logger.debug(
            f"[MonitoringDashboard] Event: {event_type.value}, "
            f"task={task_id}, agent={agent_id}"
        )

        return event

    # =========================================================================
    # 任务管理
    # =========================================================================

    async def create_task(
        self,
        task_id: str,
        goal: str,
    ) -> TaskProgress:
        """创建任务"""
        task = TaskProgress(
            task_id=task_id,
            goal=goal,
            status="created",
        )

        async with self._lock:
            self._tasks[task_id] = task
            self._total_tasks_created += 1

        await self.record_event(
            DashboardEventType.TASK_CREATED,
            task_id=task_id,
            data={"goal": goal},
        )

        return task

    async def update_task_progress(
        self,
        task_id: str,
        current_step: int = None,
        total_steps: int = None,
        status: str = None,
        tokens_used: int = None,
        llm_calls: int = None,
        error: str = None,
    ) -> Optional[TaskProgress]:
        """更新任务进度"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            if current_step is not None:
                task.current_step = current_step
            if total_steps is not None:
                task.total_steps = total_steps
            if status is not None:
                task.status = status
                if status == "running" and not task.started_at:
                    task.started_at = datetime.now()
                elif status in ["completed", "failed"]:
                    task.completed_at = datetime.now()
                    if status == "completed":
                        self._total_tasks_completed += 1
                    else:
                        self._total_tasks_failed += 1
            if tokens_used is not None:
                task.tokens_used = tokens_used
            if llm_calls is not None:
                task.llm_calls = llm_calls
            if error is not None:
                task.errors.append(error)

            # 计算进度百分比
            if task.total_steps > 0:
                task.progress_percent = (task.current_step / task.total_steps) * 100

        # 记录进度事件
        await self.record_event(
            DashboardEventType.TASK_PROGRESS,
            task_id=task_id,
            data={
                "current_step": task.current_step,
                "total_steps": task.total_steps,
                "progress_percent": task.progress_percent,
                "status": task.status,
            },
        )

        return task

    async def update_subtask_progress(
        self,
        task_id: str,
        total: int = None,
        completed: int = None,
        failed: int = None,
    ) -> Optional[TaskProgress]:
        """更新子任务进度"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            if total is not None:
                task.total_subtasks = total
            if completed is not None:
                task.completed_subtasks = completed
            if failed is not None:
                task.failed_subtasks = failed

        return task

    async def complete_task(
        self,
        task_id: str,
        success: bool = True,
    ) -> Optional[TaskProgress]:
        """完成任务"""
        return await self.update_task_progress(
            task_id=task_id,
            status="completed" if success else "failed",
        )

    # =========================================================================
    # 子Agent管理
    # =========================================================================

    async def create_subagent(
        self,
        conversation_id: str,
        subagent_name: str,
        parent_task_id: str,
    ) -> SubagentProgress:
        """创建子Agent"""
        subagent = SubagentProgress(
            conversation_id=conversation_id,
            subagent_name=subagent_name,
            parent_task_id=parent_task_id,
            status="created",
        )

        async with self._lock:
            self._subagents[conversation_id] = subagent

        await self.record_event(
            DashboardEventType.SUBAGENT_STARTED,
            task_id=parent_task_id,
            subagent_name=subagent_name,
            data={"conversation_id": conversation_id},
        )

        return subagent

    async def update_subagent(
        self,
        conversation_id: str,
        status: str = None,
        result: str = None,
        error: str = None,
    ) -> Optional[SubagentProgress]:
        """更新子Agent状态"""
        async with self._lock:
            subagent = self._subagents.get(conversation_id)
            if not subagent:
                return None

            if status is not None:
                subagent.status = status
                if status == "running" and not subagent.started_at:
                    subagent.started_at = datetime.now()
                elif status in ["completed", "failed"]:
                    subagent.completed_at = datetime.now()
            if result is not None:
                subagent.result = result
            if error is not None:
                subagent.error = error

        if status in ["completed", "failed"]:
            await self.record_event(
                DashboardEventType.SUBAGENT_COMPLETED,
                task_id=subagent.parent_task_id,
                subagent_name=subagent.subagent_name,
                data={
                    "conversation_id": conversation_id,
                    "status": status,
                    "success": status == "completed",
                },
            )

        return subagent

    # =========================================================================
    # Worker管理
    # =========================================================================

    async def update_worker(
        self,
        worker_id: str,
        status: str = None,
        pid: int = None,
        total_tasks: int = None,
        completed_tasks: int = None,
        failed_tasks: int = None,
        current_tasks: int = None,
        cpu_percent: float = None,
        memory_mb: float = None,
    ) -> WorkerProgress:
        """更新Worker状态"""
        async with self._lock:
            worker = self._workers.get(worker_id)
            if not worker:
                worker = WorkerProgress(worker_id=worker_id)
                self._workers[worker_id] = worker

            if status is not None:
                worker.status = status
            if pid is not None:
                worker.pid = pid
            if total_tasks is not None:
                worker.total_tasks = total_tasks
            if completed_tasks is not None:
                worker.completed_tasks = completed_tasks
            if failed_tasks is not None:
                worker.failed_tasks = failed_tasks
            if current_tasks is not None:
                worker.current_tasks = current_tasks
            if cpu_percent is not None:
                worker.cpu_percent = cpu_percent
            if memory_mb is not None:
                worker.memory_mb = memory_mb

            worker.last_heartbeat = datetime.now()

        await self.record_event(
            DashboardEventType.WORKER_STATUS,
            agent_id=worker_id,
            data=worker.to_dict(),
        )

        return worker

    async def remove_worker(self, worker_id: str) -> bool:
        """移除Worker"""
        async with self._lock:
            if worker_id in self._workers:
                del self._workers[worker_id]
                return True
        return False

    # =========================================================================
    # 告警管理
    # =========================================================================

    async def create_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
    ) -> HealthAlert:
        """创建告警"""
        import uuid

        alert = HealthAlert(
            alert_id=f"alert_{uuid.uuid4().hex[:8]}",
            alert_type=alert_type,
            severity=severity,
            message=message,
        )

        async with self._lock:
            self._alerts.append(alert)

        await self.record_event(
            DashboardEventType.HEALTH_ALERT,
            data=alert.to_dict(),
        )

        logger.warning(f"[MonitoringDashboard] Alert: [{severity}] {message}")

        return alert

    async def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        async with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.resolved = True
                    alert.resolved_at = datetime.now()
                    return True
        return False

    # =========================================================================
    # WebSocket订阅
    # =========================================================================

    async def subscribe(self) -> asyncio.Queue:
        """订阅事件流"""
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        logger.info(
            f"[MonitoringDashboard] New subscriber, total={len(self._subscribers)}"
        )
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """取消订阅"""
        self._subscribers.discard(queue)
        logger.info(
            f"[MonitoringDashboard] Unsubscribed, total={len(self._subscribers)}"
        )

    async def _broadcast_event(self, event: DashboardEvent):
        """广播事件给所有订阅者"""
        event_data = json.dumps(event.to_dict())

        dead_queues = set()
        for queue in self._subscribers:
            try:
                queue.put_nowait(event_data)
            except asyncio.QueueFull:
                dead_queues.add(queue)

        # 清理满的队列
        for queue in dead_queues:
            self._subscribers.discard(queue)

    # =========================================================================
    # 查询API
    # =========================================================================

    async def get_task(self, task_id: str) -> Optional[TaskProgress]:
        """获取任务"""
        return self._tasks.get(task_id)

    async def get_all_tasks(self) -> List[TaskProgress]:
        """获取所有任务"""
        return list(self._tasks.values())

    async def get_active_tasks(self) -> List[TaskProgress]:
        """获取活跃任务"""
        return [t for t in self._tasks.values() if t.status in ["created", "running"]]

    async def get_subagents(self, task_id: str) -> List[SubagentProgress]:
        """获取任务的子Agent"""
        return [s for s in self._subagents.values() if s.parent_task_id == task_id]

    async def get_workers(self) -> List[WorkerProgress]:
        """获取所有Worker"""
        return list(self._workers.values())

    async def get_active_workers(self) -> List[WorkerProgress]:
        """获取活跃Worker"""
        return [w for w in self._workers.values() if w.status in ["idle", "busy"]]

    async def get_alerts(
        self,
        unresolved_only: bool = False,
        severity: str = None,
    ) -> List[HealthAlert]:
        """获取告警"""
        alerts = self._alerts

        if unresolved_only:
            alerts = [a for a in alerts if not a.resolved]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        return alerts

    async def get_events(
        self,
        event_type: DashboardEventType = None,
        task_id: str = None,
        limit: int = 100,
    ) -> List[DashboardEvent]:
        """获取事件"""
        events = self._events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if task_id:
            events = [e for e in events if e.task_id == task_id]

        return events[-limit:]

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        active_tasks = await self.get_active_tasks()
        active_workers = await self.get_active_workers()
        unresolved_alerts = [a for a in self._alerts if not a.resolved]

        return {
            "tasks": {
                "total_created": self._total_tasks_created,
                "total_completed": self._total_tasks_completed,
                "total_failed": self._total_tasks_failed,
                "active": len(active_tasks),
            },
            "subagents": {
                "total": len(self._subagents),
                "running": sum(
                    1 for s in self._subagents.values() if s.status == "running"
                ),
            },
            "workers": {
                "total": len(self._workers),
                "active": len(active_workers),
                "idle": sum(1 for w in self._workers.values() if w.status == "idle"),
                "busy": sum(1 for w in self._workers.values() if w.status == "busy"),
            },
            "alerts": {
                "total": len(self._alerts),
                "unresolved": len(unresolved_alerts),
                "critical": sum(
                    1 for a in unresolved_alerts if a.severity == "critical"
                ),
                "error": sum(1 for a in unresolved_alerts if a.severity == "error"),
                "warning": sum(1 for a in unresolved_alerts if a.severity == "warning"),
            },
            "events": {
                "total": len(self._events),
                "subscribers": len(self._subscribers),
            },
        }

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表盘完整数据"""
        return {
            "tasks": [t.to_dict() for t in await self.get_all_tasks()],
            "active_tasks": [t.to_dict() for t in await self.get_active_tasks()],
            "workers": [w.to_dict() for w in await self.get_workers()],
            "alerts": [
                a.to_dict() for a in await self.get_alerts(unresolved_only=True)
            ],
            "stats": await self.get_stats(),
            "timestamp": datetime.now().isoformat(),
        }


# =============================================================================
# 全局单例
# =============================================================================

_dashboard: Optional[MonitoringDashboard] = None


def get_dashboard() -> MonitoringDashboard:
    """获取全局仪表盘实例"""
    global _dashboard
    if _dashboard is None:
        _dashboard = MonitoringDashboard()
    return _dashboard


# =============================================================================
# FastAPI集成
# =============================================================================


def create_dashboard_routes(dashboard: MonitoringDashboard = None):
    """
    创建FastAPI路由

    使用方式:
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(create_dashboard_routes())
    """
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse

    dashboard = dashboard or get_dashboard()
    router = APIRouter(prefix="/monitoring", tags=["monitoring"])

    @router.get("/stats")
    async def get_stats():
        """获取统计信息"""
        return await dashboard.get_stats()

    @router.get("/dashboard")
    async def get_dashboard_data_route():
        """获取仪表盘数据"""
        return await dashboard.get_dashboard_data()

    @router.get("/tasks")
    async def get_tasks(active_only: bool = False):
        """获取任务列表"""
        if active_only:
            tasks = await dashboard.get_active_tasks()
        else:
            tasks = await dashboard.get_all_tasks()
        return [t.to_dict() for t in tasks]

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str):
        """获取任务详情"""
        task = await dashboard.get_task(task_id)
        if not task:
            return JSONResponse({"error": "Task not found"}, status_code=404)
        return task.to_dict()

    @router.get("/tasks/{task_id}/subagents")
    async def get_task_subagents(task_id: str):
        """获取任务的子Agent"""
        subagents = await dashboard.get_subagents(task_id)
        return [s.to_dict() for s in subagents]

    @router.get("/workers")
    async def get_workers():
        """获取Worker列表"""
        workers = await dashboard.get_workers()
        return [w.to_dict() for w in workers]

    @router.get("/alerts")
    async def get_alerts(unresolved_only: bool = False, severity: str = None):
        """获取告警"""
        alerts = await dashboard.get_alerts(
            unresolved_only=unresolved_only,
            severity=severity,
        )
        return [a.to_dict() for a in alerts]

    @router.post("/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str):
        """解决告警"""
        success = await dashboard.resolve_alert(alert_id)
        if not success:
            return JSONResponse({"error": "Alert not found"}, status_code=404)
        return {"success": True}

    @router.get("/events")
    async def get_events(
        event_type: str = None,
        task_id: str = None,
        limit: int = 100,
    ):
        """获取事件历史"""
        from .monitoring_dashboard import DashboardEventType

        et = DashboardEventType(event_type) if event_type else None
        events = await dashboard.get_events(
            event_type=et,
            task_id=task_id,
            limit=limit,
        )
        return [e.to_dict() for e in events]

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket实时事件流"""
        await websocket.accept()
        queue = await dashboard.subscribe()

        try:
            while True:
                # 发送事件
                event_data = await queue.get()
                await websocket.send_text(event_data)
        except WebSocketDisconnect:
            await dashboard.unsubscribe(queue)

    return router


# =============================================================================
# 使用示例
# =============================================================================


async def example_dashboard():
    """仪表盘使用示例"""
    dashboard = get_dashboard()

    # 创建任务
    await dashboard.create_task("task-001", "分析系统日志")

    # 更新进度
    await dashboard.update_task_progress(
        "task-001",
        current_step=1,
        total_steps=10,
        status="running",
    )

    # 创建子Agent
    await dashboard.create_subagent(
        "conv-001",
        "analyzer",
        "task-001",
    )

    # 更新子Agent
    await dashboard.update_subagent(
        "conv-001",
        status="running",
    )

    # 创建告警
    await dashboard.create_alert(
        "memory_high",
        "warning",
        "Memory usage exceeds 80%",
    )

    # 获取统计
    stats = await dashboard.get_stats()
    print(f"Stats: {stats}")

    # 获取仪表盘数据
    data = await dashboard.get_dashboard_data()
    print(f"Dashboard: {data}")
