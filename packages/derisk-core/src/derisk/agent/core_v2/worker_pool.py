"""
Worker Process Pool - 分布式工作进程池

实现真正的分布式Worker进程支持:
1. 多进程Worker池管理
2. 任务分发和负载均衡
3. Worker健康监控
4. 故障恢复和重启
5. 动态扩缩容

此模块实现 P1 改进方案。
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import os
import signal
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Generic
from concurrent.futures import ProcessPoolExecutor, Future
import threading

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class WorkerStatus(Enum):
    """Worker状态"""

    IDLE = "idle"  # 空闲
    BUSY = "busy"  # 繁忙
    STOPPING = "stopping"  # 停止中
    STOPPED = "stopped"  # 已停止
    ERROR = "error"  # 错误


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"  # 等待中
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    TIMEOUT = "timeout"  # 超时
    CANCELLED = "cancelled"  # 已取消


class LoadBalanceStrategy(Enum):
    """负载均衡策略"""

    ROUND_ROBIN = "round_robin"  # 轮询
    LEAST_LOADED = "least_loaded"  # 最少负载
    RANDOM = "random"  # 随机
    WEIGHTED = "weighted"  # 加权


@dataclass
class WorkerConfig:
    """Worker配置"""

    worker_id: str
    max_tasks: int = 10  # 最大并行任务数
    task_timeout: int = 3600  # 任务超时(秒)
    heartbeat_interval: int = 30  # 心跳间隔(秒)
    restart_on_failure: bool = True  # 失败时是否重启
    max_restart_count: int = 3  # 最大重启次数
    weight: int = 1  # 权重(用于加权负载均衡)


@dataclass
class WorkerInfo:
    """Worker信息"""

    worker_id: str
    status: WorkerStatus = WorkerStatus.IDLE
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

    # 重启计数
    restart_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "status": self.status.value,
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
            "restart_count": self.restart_count,
        }


@dataclass
class WorkerTask(Generic[T, R]):
    """Worker任务"""

    task_id: str
    func: Callable[[T], R]
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)

    status: TaskStatus = TaskStatus.PENDING
    result: Optional[R] = None
    error: Optional[Exception] = None

    # 时间信息
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 分配信息
    assigned_worker: Optional[str] = None
    priority: int = 0

    @property
    def duration_ms(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None


@dataclass
class WorkerPoolConfig:
    """Worker池配置"""

    min_workers: int = 2  # 最小Worker数
    max_workers: int = 10  # 最大Worker数
    max_tasks_per_worker: int = 10  # 每个Worker最大任务数
    task_timeout: int = 3600  # 任务超时(秒)
    worker_timeout: int = 300  # Worker超时(秒)
    heartbeat_interval: int = 30  # 心跳间隔(秒)
    load_balance: LoadBalanceStrategy = LoadBalanceStrategy.LEAST_LOADED
    auto_scale: bool = True  # 自动扩缩容
    scale_up_threshold: float = 0.8  # 扩容阈值(负载率)
    scale_down_threshold: float = 0.3  # 缩容阈值(负载率)


class WorkerProcess:
    """
    Worker进程

    运行在独立进程中执行任务
    """

    def __init__(self, config: WorkerConfig):
        self.config = config
        self.info = WorkerInfo(worker_id=config.worker_id)
        self._process: Optional[mp.Process] = None
        self._task_queue: mp.Queue = mp.Queue()
        self._result_queue: mp.Queue = mp.Queue()
        self._stop_event = mp.Event()
        self._lock = threading.Lock()

    def start(self) -> bool:
        """启动Worker进程"""
        if self._process and self._process.is_alive():
            return True

        try:
            self._stop_event.clear()
            self._process = mp.Process(
                target=self._run_worker_process,
                args=(
                    self.config,
                    self._task_queue,
                    self._result_queue,
                    self._stop_event,
                ),
                daemon=True,
            )
            self._process.start()

            self.info.pid = self._process.pid
            self.info.status = WorkerStatus.IDLE
            self.info.started_at = datetime.now()
            self.info.last_heartbeat = datetime.now()

            logger.info(
                f"[WorkerProcess] Started worker {self.config.worker_id} "
                f"(pid={self.info.pid})"
            )
            return True

        except Exception as e:
            logger.error(f"[WorkerProcess] Failed to start worker: {e}")
            self.info.status = WorkerStatus.ERROR
            return False

    def stop(self, timeout: int = 30) -> bool:
        """停止Worker进程"""
        if not self._process or not self._process.is_alive():
            return True

        try:
            self.info.status = WorkerStatus.STOPPING
            self._stop_event.set()

            self._process.join(timeout=timeout)

            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=5)

                if self._process.is_alive():
                    self._process.kill()

            self.info.status = WorkerStatus.STOPPED
            logger.info(f"[WorkerProcess] Stopped worker {self.config.worker_id}")
            return True

        except Exception as e:
            logger.error(f"[WorkerProcess] Failed to stop worker: {e}")
            return False

    def submit_task(self, task: WorkerTask) -> bool:
        """提交任务"""
        if self.info.status not in [WorkerStatus.IDLE, WorkerStatus.BUSY]:
            return False

        if self.info.current_tasks >= self.config.max_tasks:
            return False

        try:
            self._task_queue.put(task, timeout=5)
            self.info.current_tasks += 1
            self.info.total_tasks += 1
            self.info.status = WorkerStatus.BUSY
            return True
        except Exception as e:
            logger.error(f"[WorkerProcess] Failed to submit task: {e}")
            return False

    def get_results(self) -> List[WorkerTask]:
        """获取完成的任务结果"""
        results = []
        try:
            while not self._result_queue.empty():
                task = self._result_queue.get_nowait()
                results.append(task)

                with self._lock:
                    self.info.current_tasks -= 1
                    if task.status == TaskStatus.COMPLETED:
                        self.info.completed_tasks += 1
                    else:
                        self.info.failed_tasks += 1

                    if self.info.current_tasks == 0:
                        self.info.status = WorkerStatus.IDLE

        except Exception as e:
            logger.error(f"[WorkerProcess] Failed to get results: {e}")

        return results

    def is_alive(self) -> bool:
        """检查Worker是否存活"""
        return self._process is not None and self._process.is_alive()

    def update_heartbeat(self):
        """更新心跳"""
        self.info.last_heartbeat = datetime.now()

    @staticmethod
    def _run_worker_process(
        config: WorkerConfig,
        task_queue: mp.Queue,
        result_queue: mp.Queue,
        stop_event: mp.Event,
    ):
        """Worker进程主循环"""
        logger.info(f"[WorkerProcess] Worker {config.worker_id} started")

        while not stop_event.is_set():
            try:
                # 获取任务
                task = task_queue.get(timeout=1.0)
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()

                try:
                    # 执行任务
                    result = task.func(*task.args, **task.kwargs)
                    task.result = result
                    task.status = TaskStatus.COMPLETED

                except Exception as e:
                    task.error = e
                    task.status = TaskStatus.FAILED

                finally:
                    task.completed_at = datetime.now()
                    result_queue.put(task)

            except Exception:
                # 超时，继续循环
                pass

        logger.info(f"[WorkerProcess] Worker {config.worker_id} stopped")


class WorkerPool:
    """
    Worker进程池

    管理多个Worker进程,提供任务分发和负载均衡
    """

    def __init__(self, config: WorkerPoolConfig):
        self.config = config
        self._workers: Dict[str, WorkerProcess] = {}
        self._pending_tasks: asyncio.Queue = asyncio.Queue()
        self._completed_tasks: asyncio.Queue = asyncio.Queue()

        self._running = False
        self._lock = threading.Lock()
        self._task_counter = 0

        # 负载均衡
        self._round_robin_index = 0

        logger.info(
            f"[WorkerPool] Initialized with min={config.min_workers}, "
            f"max={config.max_workers}"
        )

    async def start(self) -> bool:
        """启动Worker池"""
        if self._running:
            return True

        self._running = True

        # 创建初始Worker
        for i in range(self.config.min_workers):
            await self._add_worker(f"worker-{i}")

        # 启动任务分发循环
        asyncio.create_task(self._dispatch_loop())
        asyncio.create_task(self._result_collection_loop())
        asyncio.create_task(self._health_check_loop())

        if self.config.auto_scale:
            asyncio.create_task(self._auto_scale_loop())

        logger.info(f"[WorkerPool] Started with {len(self._workers)} workers")
        return True

    async def stop(self) -> bool:
        """停止Worker池"""
        self._running = False

        # 停止所有Worker
        for worker in self._workers.values():
            worker.stop()

        self._workers.clear()
        logger.info("[WorkerPool] Stopped")
        return True

    async def submit_task(
        self,
        func: Callable,
        *args,
        priority: int = 0,
        **kwargs,
    ) -> str:
        """
        提交任务

        Args:
            func: 要执行的函数
            *args: 函数参数
            priority: 任务优先级
            **kwargs: 函数关键字参数

        Returns:
            任务ID
        """
        self._task_counter += 1
        task_id = f"task-{int(time.time() * 1000)}-{self._task_counter}"

        task = WorkerTask(
            task_id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
        )

        await self._pending_tasks.put(task)
        logger.debug(f"[WorkerPool] Submitted task {task_id}")
        return task_id

    async def get_result(self, task_id: str, timeout: float = None) -> Optional[Any]:
        """
        获取任务结果

        Args:
            task_id: 任务ID
            timeout: 超时时间(秒)

        Returns:
            任务结果
        """
        start_time = time.time()

        while True:
            # 检查完成的任务队列
            try:
                while True:
                    task = self._completed_tasks.get_nowait()
                    if task.task_id == task_id:
                        if task.status == TaskStatus.COMPLETED:
                            return task.result
                        else:
                            raise task.error or Exception("Task failed")

                    # 放回队列
                    await self._completed_tasks.put(task)
            except asyncio.QueueEmpty:
                pass

            # 检查超时
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task {task_id} timeout")

            await asyncio.sleep(0.1)

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_workers = len(self._workers)
        active_workers = sum(1 for w in self._workers.values() if w.is_alive())

        total_tasks = sum(w.info.total_tasks for w in self._workers.values())
        completed_tasks = sum(w.info.completed_tasks for w in self._workers.values())
        failed_tasks = sum(w.info.failed_tasks for w in self._workers.values())
        current_tasks = sum(w.info.current_tasks for w in self._workers.values())

        return {
            "total_workers": total_workers,
            "active_workers": active_workers,
            "idle_workers": total_workers - active_workers,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "current_tasks": current_tasks,
            "pending_tasks": self._pending_tasks.qsize(),
            "load_rate": current_tasks
            / (total_workers * self.config.max_tasks_per_worker)
            if total_workers > 0
            else 0,
        }

    async def _add_worker(self, worker_id: str) -> bool:
        """添加Worker"""
        if worker_id in self._workers:
            return False

        config = WorkerConfig(
            worker_id=worker_id,
            max_tasks=self.config.max_tasks_per_worker,
            task_timeout=self.config.task_timeout,
            heartbeat_interval=self.config.heartbeat_interval,
        )

        worker = WorkerProcess(config)
        if worker.start():
            self._workers[worker_id] = worker
            return True
        return False

    async def _remove_worker(self, worker_id: str) -> bool:
        """移除Worker"""
        worker = self._workers.get(worker_id)
        if not worker:
            return False

        if worker.stop():
            del self._workers[worker_id]
            return True
        return False

    def _select_worker(self) -> Optional[WorkerProcess]:
        """选择Worker(负载均衡)"""
        alive_workers = [w for w in self._workers.values() if w.is_alive()]

        if not alive_workers:
            return None

        if self.config.load_balance == LoadBalanceStrategy.ROUND_ROBIN:
            # 轮询
            self._round_robin_index = (self._round_robin_index + 1) % len(alive_workers)
            return alive_workers[self._round_robin_index]

        elif self.config.load_balance == LoadBalanceStrategy.LEAST_LOADED:
            # 最少负载
            return min(alive_workers, key=lambda w: w.info.current_tasks)

        elif self.config.load_balance == LoadBalanceStrategy.RANDOM:
            # 随机
            import random

            return random.choice(alive_workers)

        elif self.config.load_balance == LoadBalanceStrategy.WEIGHTED:
            # 加权
            weighted = []
            for w in alive_workers:
                weight = w.config.weight
                weighted.extend([w] * weight)
            import random

            return random.choice(weighted) if weighted else None

        return alive_workers[0]

    async def _dispatch_loop(self):
        """任务分发循环"""
        while self._running:
            try:
                # 获取待处理任务
                task = await asyncio.wait_for(self._pending_tasks.get(), timeout=1.0)

                # 选择Worker
                worker = self._select_worker()
                if not worker:
                    # 没有可用Worker,放回队列
                    await self._pending_tasks.put(task)
                    await asyncio.sleep(0.1)
                    continue

                # 提交任务
                if not worker.submit_task(task):
                    # Worker已满,放回队列
                    await self._pending_tasks.put(task)
                    await asyncio.sleep(0.1)

            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"[WorkerPool] Dispatch error: {e}")
                await asyncio.sleep(0.1)

    async def _result_collection_loop(self):
        """结果收集循环"""
        while self._running:
            try:
                for worker in self._workers.values():
                    results = worker.get_results()
                    for task in results:
                        await self._completed_tasks.put(task)

                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"[WorkerPool] Result collection error: {e}")
                await asyncio.sleep(0.1)

    async def _health_check_loop(self):
        """健康检查循环"""
        while self._running:
            try:
                now = datetime.now()

                for worker_id, worker in list(self._workers.items()):
                    if not worker.is_alive():
                        logger.warning(
                            f"[WorkerPool] Worker {worker_id} died, restarting..."
                        )

                        if worker.config.restart_on_failure:
                            if (
                                worker.info.restart_count
                                < worker.config.max_restart_count
                            ):
                                worker.info.restart_count += 1
                                worker.start()
                            else:
                                logger.error(
                                    f"[WorkerPool] Worker {worker_id} "
                                    f"exceeded max restart count"
                                )

                    elif worker.info.last_heartbeat:
                        # 检查心跳超时
                        elapsed = (now - worker.info.last_heartbeat).total_seconds()
                        if elapsed > self.config.worker_timeout:
                            logger.warning(
                                f"[WorkerPool] Worker {worker_id} heartbeat timeout"
                            )

                await asyncio.sleep(self.config.heartbeat_interval)

            except Exception as e:
                logger.error(f"[WorkerPool] Health check error: {e}")
                await asyncio.sleep(1)

    async def _auto_scale_loop(self):
        """自动扩缩容循环"""
        while self._running:
            try:
                stats = await self.get_stats()
                load_rate = stats["load_rate"]

                current_workers = len(self._workers)

                # 扩容
                if (
                    load_rate > self.config.scale_up_threshold
                    and current_workers < self.config.max_workers
                ):
                    new_worker_id = f"worker-{int(time.time())}"
                    await self._add_worker(new_worker_id)
                    logger.info(f"[WorkerPool] Scaling up: added {new_worker_id}")

                # 缩容
                elif (
                    load_rate < self.config.scale_down_threshold
                    and current_workers > self.config.min_workers
                ):
                    # 找到最空闲的Worker
                    idle_worker = min(
                        self._workers.values(),
                        key=lambda w: w.info.current_tasks,
                    )
                    if idle_worker.info.current_tasks == 0:
                        await self._remove_worker(idle_worker.config.worker_id)
                        logger.info(
                            f"[WorkerPool] Scaling down: removed "
                            f"{idle_worker.config.worker_id}"
                        )

                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"[WorkerPool] Auto scale error: {e}")
                await asyncio.sleep(5)


# =============================================================================
# 便捷函数
# =============================================================================


def create_worker_pool(
    min_workers: int = 2,
    max_workers: int = 10,
    max_tasks_per_worker: int = 10,
    auto_scale: bool = True,
) -> WorkerPool:
    """创建Worker池"""
    config = WorkerPoolConfig(
        min_workers=min_workers,
        max_workers=max_workers,
        max_tasks_per_worker=max_tasks_per_worker,
        auto_scale=auto_scale,
    )
    return WorkerPool(config)


# =============================================================================
# 使用示例
# =============================================================================


async def example_worker_pool():
    """Worker池使用示例"""

    # 创建Worker池
    pool = create_worker_pool(
        min_workers=2,
        max_workers=5,
        max_tasks_per_worker=10,
    )

    # 启动
    await pool.start()

    # 提交任务
    def my_task(x):
        import time

        time.sleep(1)
        return x * 2

    task_ids = []
    for i in range(10):
        task_id = await pool.submit_task(my_task, i)
        task_ids.append(task_id)

    # 获取结果
    for task_id in task_ids:
        result = await pool.get_result(task_id, timeout=30)
        print(f"Task {task_id}: {result}")

    # 获取统计
    stats = await pool.get_stats()
    print(f"Stats: {stats}")

    # 停止
    await pool.stop()
