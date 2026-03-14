"""
Task Orchestrator - 任务编排框架

实现 DAG（有向无环图）模式的任务编排，提供：
- 依赖管理
- 并行执行
- 重试策略
- 补偿机制
- 超时控制

此模块实现 P3 改进方案。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Generic,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TaskPriority(Enum):
    """任务优先级"""

    CRITICAL = 0  # 关键任务 - 失败会停止整个工作流
    HIGH = 1  # 高优先级
    MEDIUM = 2  # 中优先级
    LOW = 3  # 低优先级


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"  # 等待中
    WAITING_DEPS = "waiting_deps"  # 等待依赖
    RUNNING = "running"  # 执行中
    PAUSED = "paused"  # 暂停
    COMPLETED = "completed"  # 完成
    FAILED = "failed"  # 失败
    COMPENSATING = "compensating"  # 补偿中
    COMPENSATED = "compensated"  # 已补偿
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"  # 超时


class RetryPolicy(Enum):
    """重试策略"""

    NONE = "none"  # 不重试
    FIXED = "fixed"  # 固定间隔重试
    EXPONENTIAL = "exponential"  # 指数退避重试
    LINEAR = "linear"  # 线性退避重试


class TaskError(Exception):
    """任务错误基类"""

    pass


class TaskNotFoundError(TaskError):
    """任务未找到"""

    pass


class DependencyNotMetError(TaskError):
    """依赖未满足"""

    pass


class CircularDependencyError(TaskError):
    """循环依赖"""

    pass


class MaxRetriesExceededError(TaskError):
    """超过最大重试次数"""

    pass


@dataclass
class RetryConfig:
    """重试配置"""

    policy: RetryPolicy = RetryPolicy.EXPONENTIAL
    max_retries: int = 3
    base_delay: float = 1.0  # 基础延迟（秒）
    max_delay: float = 60.0  # 最大延迟（秒）
    retryable_errors: Optional[List[type]] = None  # 可重试的错误类型

    def get_backoff(self, retry_count: int) -> float:
        """计算退避时间"""
        if self.policy == RetryPolicy.NONE:
            return 0

        if self.policy == RetryPolicy.FIXED:
            return min(self.base_delay, self.max_delay)

        if self.policy == RetryPolicy.LINEAR:
            delay = self.base_delay * retry_count
            return min(delay, self.max_delay)

        if self.policy == RetryPolicy.EXPONENTIAL:
            delay = self.base_delay * (2 ** (retry_count - 1))
            return min(delay, self.max_delay)

        return self.base_delay

    def is_retryable(self, error: Exception) -> bool:
        """判断错误是否可重试"""
        if not self.retryable_errors:
            # 默认所有错误都可重试
            return True
        return isinstance(error, tuple(self.retryable_errors))


@dataclass
class TaskResult:
    """任务执行结果"""

    task_id: str
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    retry_count: int = 0

    @property
    def duration_ms(self) -> Optional[float]:
        """执行时长（毫秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None


@dataclass
class Task(Generic[T]):
    """
    任务定义

    包含：
    - 执行函数
    - 依赖关系
    - 重试策略
    - 补偿处理
    """

    task_id: str
    name: str
    execute_func: Callable[[], T]

    # 优先级和依赖
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: List[str] = field(default_factory=list)

    # 执行配置
    timeout: int = 3600  # 秒
    retry_config: RetryConfig = field(default_factory=RetryConfig)

    # 补偿处理
    compensation_handler: Optional[Callable[[Any, Optional[Exception]], Any]] = None

    # 状态
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[Exception] = None

    # 执行信息
    retry_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.task_id)

    def __eq__(self, other):
        if isinstance(other, Task):
            return self.task_id == other.task_id
        return False

    def mark_running(self) -> None:
        """标记为运行中"""
        self.status = TaskStatus.RUNNING
        self.start_time = datetime.now()

    def mark_completed(self, result: Any) -> None:
        """标记为完成"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.end_time = datetime.now()

    def mark_failed(self, error: Exception) -> None:
        """标记为失败"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.end_time = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error": str(self.error) if self.error else None,
        }


@dataclass
class WorkflowResult:
    """工作流执行结果"""

    workflow_id: str
    success: bool
    task_results: Dict[str, TaskResult]
    total_time_ms: float
    completed_tasks: int
    failed_tasks: int
    compensated_tasks: int

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        return self.task_results.get(task_id)


class TaskOrchestrator:
    """
    任务编排器

    支持：
    - DAG 模式任务编排
    - 依赖自动解析
    - 拓扑排序执行
    - 并行执行独立任务
    - 重试和超时
    - 补偿机制

    示例:
        orchestrator = TaskOrchestrator()

        # 添加任务
        orchestrator.add_task(Task(
            task_id="fetch_data",
            name="Fetch Data",
            execute_func=fetch_data,
        ))

        orchestrator.add_task(Task(
            task_id="process_data",
            name="Process Data",
            execute_func=process_data,
            dependencies=["fetch_data"],
        ))

        # 执行工作流
        result = await orchestrator.execute()
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        default_timeout: int = 3600,
        default_retry_config: Optional[RetryConfig] = None,
    ):
        """
        初始化任务编排器

        Args:
            max_concurrent: 最大并发任务数
            default_timeout: 默认超时时间（秒）
            default_retry_config: 默认重试配置
        """
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self.default_retry_config = default_retry_config or RetryConfig()

        # 任务存储
        self.tasks: Dict[str, Task] = {}

        # 执行图
        self._dependency_graph: Dict[str, List[str]] = defaultdict(list)
        self._reverse_graph: Dict[str, List[str]] = defaultdict(list)

        # 执行状态
        self._running_tasks: Set[str] = set()
        self._completed_tasks: Set[str] = set()
        self._failed_tasks: Set[str] = set()

        # 结果
        self._results: Dict[str, TaskResult] = {}

        # 同步
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent)

        logger.info(
            f"[TaskOrchestrator] Initialized with max_concurrent={max_concurrent}"
        )

    def add_task(self, task: Task) -> None:
        """添加任务"""
        self.tasks[task.task_id] = task

        # 更新依赖图
        for dep_id in task.dependencies:
            self._dependency_graph[task.task_id].append(dep_id)
            self._reverse_graph[dep_id].append(task.task_id)

        logger.debug(
            f"[TaskOrchestrator] Added task {task.task_id} "
            f"with {len(task.dependencies)} dependencies"
        )

    def remove_task(self, task_id: str) -> bool:
        """移除任务"""
        if task_id not in self.tasks:
            return False

        task = self.tasks.pop(task_id)

        # 更新依赖图
        for dep_id in task.dependencies:
            self._dependency_graph[task_id].remove(dep_id)
            self._reverse_graph[dep_id].remove(task_id)

        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)

    def _topological_sort(self) -> List[str]:
        """
        拓扑排序

        Returns:
            排序后的任务ID列表

        Raises:
            CircularDependencyError: 存在循环依赖
        """
        # 计算入度
        in_degree: Dict[str, int] = defaultdict(int)
        for task_id in self.tasks:
            in_degree[task_id] = len(self._dependency_graph[task_id])

        # 找出入度为0的节点
        queue = [tid for tid, deg in in_degree.items() if deg == 0]

        # 按优先级排序
        queue.sort(key=lambda tid: self.tasks[tid].priority.value)

        result = []
        while queue:
            # 取出优先级最高的任务
            task_id = queue.pop(0)
            result.append(task_id)

            # 更新依赖该任务的节点
            for dependent in self._reverse_graph[task_id]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    # 按优先级插入
                    queue.append(dependent)
                    queue.sort(key=lambda tid: self.tasks[tid].priority.value)

        if len(result) != len(self.tasks):
            # 存在循环依赖
            remaining = set(self.tasks.keys()) - set(result)
            raise CircularDependencyError(
                f"Circular dependency detected among tasks: {remaining}"
            )

        return result

    def _check_dependencies(self, task: Task) -> bool:
        """检查任务依赖是否已满足"""
        for dep_id in task.dependencies:
            if dep_id not in self._completed_tasks:
                return False
        return True

    async def _execute_task(self, task: Task) -> TaskResult:
        """
        执行单个任务

        包含重试逻辑
        """
        result = TaskResult(
            task_id=task.task_id,
            success=False,
            start_time=datetime.now(),
        )

        retry_config = task.retry_config or self.default_retry_config

        while task.retry_count <= retry_config.max_retries:
            try:
                task.mark_running()

                # 执行任务（带超时）
                async with asyncio.timeout(task.timeout):
                    if asyncio.iscoroutinefunction(task.execute_func):
                        task_result = await task.execute_func()
                    else:
                        task_result = task.execute_func()

                task.mark_completed(task_result)

                result.success = True
                result.result = task_result
                result.retry_count = task.retry_count

                logger.info(
                    f"[TaskOrchestrator] Task {task.task_id} completed "
                    f"(retries: {task.retry_count})"
                )

                return result

            except asyncio.TimeoutError as e:
                logger.warning(
                    f"[TaskOrchestrator] Task {task.task_id} timeout "
                    f"after {task.timeout}s"
                )
                task.status = TaskStatus.TIMEOUT
                task.error = e
                result.error = e

            except Exception as e:
                logger.warning(f"[TaskOrchestrator] Task {task.task_id} failed: {e}")
                task.error = e
                result.error = e

                # 检查是否可重试
                if retry_config.is_retryable(e):
                    task.retry_count += 1
                    result.retry_count = task.retry_count

                    if task.retry_count <= retry_config.max_retries:
                        backoff = retry_config.get_backoff(task.retry_count)
                        logger.info(
                            f"[TaskOrchestrator] Retrying task {task.task_id} "
                            f"in {backoff}s (attempt {task.retry_count}/{retry_config.max_retries})"
                        )
                        await asyncio.sleep(backoff)
                        continue

                # 不可重试或超过重试次数
                task.mark_failed(e)
                return result

        # 超过最大重试次数
        task.mark_failed(
            MaxRetriesExceededError(
                f"Task {task.task_id} exceeded max retries ({retry_config.max_retries})"
            )
        )
        result.error = task.error

        return result

    async def _compensate_task(self, task: Task) -> bool:
        """
        执行任务补偿

        Args:
            task: 需要补偿的任务

        Returns:
            补偿是否成功
        """
        if not task.compensation_handler:
            return False

        task.status = TaskStatus.COMPENSATING

        try:
            logger.info(f"[TaskOrchestrator] Compensating task {task.task_id}")

            if asyncio.iscoroutinefunction(task.compensation_handler):
                await task.compensation_handler(task.result, task.error)
            else:
                task.compensation_handler(task.result, task.error)

            task.status = TaskStatus.COMPENSATED
            logger.info(f"[TaskOrchestrator] Task {task.task_id} compensated")
            return True

        except Exception as e:
            logger.error(
                f"[TaskOrchestrator] Compensation failed for task {task.task_id}: {e}"
            )
            task.status = TaskStatus.FAILED
            return False

    async def execute(self) -> WorkflowResult:
        """
        执行工作流

        Returns:
            工作流执行结果
        """
        start_time = datetime.now()
        workflow_id = f"workflow_{int(time.time() * 1000)}"

        logger.info(
            f"[TaskOrchestrator] Starting workflow {workflow_id} "
            f"with {len(self.tasks)} tasks"
        )

        # 拓扑排序
        execution_order = self._topological_sort()

        # 重置状态
        self._running_tasks.clear()
        self._completed_tasks.clear()
        self._failed_tasks.clear()
        self._results.clear()

        # 执行任务
        critical_failed = False

        for task_id in execution_order:
            if critical_failed:
                # 关键任务失败，停止执行
                break

            task = self.tasks[task_id]

            # 检查依赖
            if not self._check_dependencies(task):
                logger.warning(
                    f"[TaskOrchestrator] Task {task_id} dependencies not met"
                )
                task.status = TaskStatus.WAITING_DEPS
                self._failed_tasks.add(task_id)
                continue

            # 检查是否有依赖任务失败
            failed_deps = [
                dep for dep in task.dependencies if dep in self._failed_tasks
            ]
            if failed_deps:
                logger.warning(
                    f"[TaskOrchestrator] Task {task_id} has failed dependencies: {failed_deps}"
                )
                self._failed_tasks.add(task_id)
                continue

            # 执行任务
            async with self._semaphore:
                self._running_tasks.add(task_id)

                result = await self._execute_task(task)
                self._results[task_id] = result

                self._running_tasks.remove(task_id)

                if result.success:
                    self._completed_tasks.add(task_id)
                else:
                    self._failed_tasks.add(task_id)

                    # 触发补偿
                    await self._compensate_task(task)

                    # 关键任务失败，停止整个工作流
                    if task.priority == TaskPriority.CRITICAL:
                        logger.error(
                            f"[TaskOrchestrator] Critical task {task_id} failed, "
                            "stopping workflow"
                        )
                        critical_failed = True

        # 构建结果
        end_time = datetime.now()
        total_time_ms = (end_time - start_time).total_seconds() * 1000

        workflow_result = WorkflowResult(
            workflow_id=workflow_id,
            success=len(self._failed_tasks) == 0,
            task_results=self._results.copy(),
            total_time_ms=total_time_ms,
            completed_tasks=len(self._completed_tasks),
            failed_tasks=len(self._failed_tasks),
            compensated_tasks=sum(
                1 for t in self.tasks.values() if t.status == TaskStatus.COMPENSATED
            ),
        )

        logger.info(
            f"[TaskOrchestrator] Workflow {workflow_id} "
            f"{'completed' if workflow_result.success else 'failed'} "
            f"({workflow_result.completed_tasks}/{len(self.tasks)} tasks, "
            f"{total_time_ms:.2f}ms)"
        )

        return workflow_result

    def get_execution_graph(self) -> Dict[str, Any]:
        """获取执行图信息"""
        return {
            "tasks": {tid: task.to_dict() for tid, task in self.tasks.items()},
            "dependencies": dict(self._dependency_graph),
            "reverse_dependencies": dict(self._reverse_graph),
            "running": list(self._running_tasks),
            "completed": list(self._completed_tasks),
            "failed": list(self._failed_tasks),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_tasks": len(self.tasks),
            "running_tasks": len(self._running_tasks),
            "completed_tasks": len(self._completed_tasks),
            "failed_tasks": len(self._failed_tasks),
            "pending_tasks": sum(
                1 for t in self.tasks.values() if t.status == TaskStatus.PENDING
            ),
        }


class WorkflowBuilder:
    """
    工作流构建器

    提供流式 API 构建工作流

    示例:
        workflow = (WorkflowBuilder()
            .task("fetch", fetch_data)
            .task("process", process_data, dependencies=["fetch"])
            .task("save", save_result, dependencies=["process"])
            .build())

        result = await workflow.execute()
    """

    def __init__(self):
        self._tasks: List[Task] = []

    def task(
        self,
        task_id: str,
        name: str,
        execute_func: Callable,
        priority: TaskPriority = TaskPriority.MEDIUM,
        dependencies: Optional[List[str]] = None,
        timeout: int = 3600,
        retry_config: Optional[RetryConfig] = None,
        compensation_handler: Optional[Callable] = None,
    ) -> "WorkflowBuilder":
        """添加任务"""
        task = Task(
            task_id=task_id,
            name=name,
            execute_func=execute_func,
            priority=priority,
            dependencies=dependencies or [],
            timeout=timeout,
            retry_config=retry_config or RetryConfig(),
            compensation_handler=compensation_handler,
        )
        self._tasks.append(task)
        return self

    def build(self) -> TaskOrchestrator:
        """构建工作流"""
        orchestrator = TaskOrchestrator()
        for task in self._tasks:
            orchestrator.add_task(task)
        return orchestrator


# 便捷函数
def create_workflow() -> WorkflowBuilder:
    """创建工作流构建器"""
    return WorkflowBuilder()
