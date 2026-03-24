"""
AsyncTaskManager - 异步任务管理器

实现类似 Claude Code Agent Tool 的异步任务能力：
1. 主 Agent 通过 Tool 启动后台子 Agent 任务
2. 主 Agent 继续自身工作，不被阻塞
3. 随时查询/等待任务结果
4. 完成的结果自动注入到下一轮推理上下文

核心设计：
- 复用 SubagentManager.delegate() 进行实际执行
- asyncio.Semaphore 控制并发
- asyncio.Future per task 实现 wait 和依赖
- asyncio.Event 实现 wait_any 通知

@see docs/ASYNC_TASK_SYSTEM.md
"""

from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime
from enum import Enum
import asyncio
import logging
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================


class AsyncTaskStatus(str, Enum):
    """异步任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class AsyncTaskSpec(BaseModel):
    """
    异步任务规格 - 由 spawn_agent_task Tool 创建

    Attributes:
        task_id: 唯一任务 ID，自动生成
        agent_name: 目标子 Agent 名称
        task_description: 任务描述（传递给子 Agent 的 prompt）
        context: 上下文信息
        timeout: 超时秒数
        depend_on: 依赖的 task_id 列表（DAG 编排）
    """
    task_id: str = Field(default_factory=lambda: f"atask_{uuid.uuid4().hex[:8]}")
    agent_name: str
    task_description: str
    context: Dict[str, Any] = Field(default_factory=dict)
    timeout: int = 300
    depend_on: List[str] = Field(default_factory=list)


class AsyncTaskState(BaseModel):
    """
    异步任务运行状态 - AsyncTaskManager 内部维护

    Attributes:
        spec: 任务规格
        status: 当前状态
        created_at: 创建时间
        started_at: 开始执行时间
        completed_at: 完成时间
        result: 成功时的结果文本
        error: 失败时的错误信息
        artifacts: 产出物字典
        consumed: 结果是否已被主 Agent 消费
    """
    spec: AsyncTaskSpec
    status: AsyncTaskStatus = AsyncTaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    consumed: bool = False

    class Config:
        arbitrary_types_allowed = True

    def is_terminal(self) -> bool:
        """是否为终态"""
        return self.status in (
            AsyncTaskStatus.COMPLETED,
            AsyncTaskStatus.FAILED,
            AsyncTaskStatus.TIMEOUT,
            AsyncTaskStatus.CANCELLED,
        )

    def elapsed_seconds(self) -> float:
        """已用时间（秒）"""
        if not self.started_at:
            return 0.0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_summary(self) -> Dict[str, Any]:
        """生成摘要字典"""
        return {
            "task_id": self.spec.task_id,
            "agent_name": self.spec.agent_name,
            "description": self.spec.task_description[:120],
            "status": self.status.value,
            "elapsed": round(self.elapsed_seconds(), 1),
            "result_preview": (self.result or "")[:300] if self.result else None,
            "error": self.error,
        }


# ==================== 核心管理器 ====================


class AsyncTaskManager:
    """
    异步任务管理器

    管理后台 Agent 任务的完整生命周期：提交、执行、查询、等待、取消。

    Usage:
        manager = AsyncTaskManager(
            subagent_manager=subagent_mgr,
            max_concurrent=5,
            parent_session_id="session_abc",
        )

        # 提交任务
        task_id = await manager.spawn(AsyncTaskSpec(
            agent_name="code_reviewer",
            task_description="Review the auth module",
        ))

        # 查询状态
        status = manager.get_all_status()

        # 等待完成
        results = await manager.wait_all([task_id], timeout=120)

    Args:
        subagent_manager: SubagentManager 实例，复用其 delegate() 方法
        max_concurrent: 最大并发任务数
        parent_session_id: 父会话 ID
        on_task_complete: 任务完成回调
        on_task_failed: 任务失败回调
    """

    def __init__(
        self,
        subagent_manager: Any,
        max_concurrent: int = 5,
        parent_session_id: str = "",
        on_task_complete: Optional[Callable[["AsyncTaskState"], Awaitable[None]]] = None,
        on_task_failed: Optional[Callable[["AsyncTaskState"], Awaitable[None]]] = None,
    ):
        self._subagent_manager = subagent_manager
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._parent_session_id = parent_session_id
        self._max_concurrent = max_concurrent

        # 任务存储
        self._tasks: Dict[str, AsyncTaskState] = {}
        self._futures: Dict[str, asyncio.Future] = {}
        self._bg_tasks: Dict[str, asyncio.Task] = {}

        # 通知机制
        self._completion_event = asyncio.Event()

        # 回调
        self._on_complete = on_task_complete
        self._on_failed = on_task_failed

        # 统计
        self._total_spawned = 0
        self._total_completed = 0
        self._total_failed = 0

    # ==================== 任务提交 ====================

    async def spawn(self, spec: AsyncTaskSpec) -> str:
        """
        提交异步任务，立即返回 task_id。

        任务在后台异步执行，不阻塞调用方。

        Args:
            spec: 任务规格

        Returns:
            task_id: 任务唯一标识

        Raises:
            ValueError: 如果 task_id 重复
        """
        if spec.task_id in self._tasks:
            raise ValueError(f"Task ID '{spec.task_id}' already exists")

        state = AsyncTaskState(spec=spec)
        self._tasks[spec.task_id] = state

        # 创建 Future 用于等待
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._futures[spec.task_id] = future

        # 验证依赖是否存在
        for dep_id in spec.depend_on:
            if dep_id not in self._tasks:
                logger.warning(
                    f"[AsyncTaskManager] Task {spec.task_id} depends on "
                    f"unknown task {dep_id}, will proceed anyway"
                )

        # 启动后台执行
        if spec.depend_on:
            bg_task = asyncio.create_task(
                self._wait_deps_then_run(state),
                name=f"async_task_{spec.task_id}",
            )
        else:
            bg_task = asyncio.create_task(
                self._run_task(state),
                name=f"async_task_{spec.task_id}",
            )
        self._bg_tasks[spec.task_id] = bg_task

        self._total_spawned += 1

        logger.info(
            f"[AsyncTaskManager] Spawned task {spec.task_id}: "
            f"agent={spec.agent_name}, "
            f"deps={spec.depend_on or 'none'}"
        )

        return spec.task_id

    # ==================== 任务执行 ====================

    async def _wait_deps_then_run(self, state: AsyncTaskState) -> None:
        """等待依赖任务完成后再执行"""
        task_id = state.spec.task_id

        for dep_id in state.spec.depend_on:
            dep_future = self._futures.get(dep_id)
            if dep_future and not dep_future.done():
                logger.debug(
                    f"[AsyncTaskManager] Task {task_id} waiting for dependency {dep_id}"
                )
                try:
                    await asyncio.wait_for(
                        asyncio.shield(dep_future),
                        timeout=state.spec.timeout,
                    )
                except asyncio.TimeoutError:
                    state.status = AsyncTaskStatus.TIMEOUT
                    state.completed_at = datetime.now()
                    state.error = f"等待依赖任务 {dep_id} 超时"
                    self._resolve_future(task_id, state)
                    return
                except asyncio.CancelledError:
                    state.status = AsyncTaskStatus.CANCELLED
                    state.completed_at = datetime.now()
                    state.error = f"依赖任务 {dep_id} 被取消"
                    self._resolve_future(task_id, state)
                    return

            # 检查依赖是否成功
            dep_state = self._tasks.get(dep_id)
            if dep_state and dep_state.status != AsyncTaskStatus.COMPLETED:
                state.status = AsyncTaskStatus.FAILED
                state.completed_at = datetime.now()
                state.error = (
                    f"依赖任务 {dep_id} 未成功完成 "
                    f"(status={dep_state.status.value})"
                )
                self._resolve_future(task_id, state)
                return

        # 所有依赖完成，开始执行
        await self._run_task(state)

    async def _run_task(self, state: AsyncTaskState) -> None:
        """实际执行任务（受 semaphore 并发控制）"""
        task_id = state.spec.task_id

        # 如果任务已被取消
        if state.status == AsyncTaskStatus.CANCELLED:
            self._resolve_future(task_id, state)
            return

        async with self._semaphore:
            state.status = AsyncTaskStatus.RUNNING
            state.started_at = datetime.now()

            logger.info(
                f"[AsyncTaskManager] Running task {task_id}: "
                f"agent={state.spec.agent_name}"
            )

            try:
                result = await asyncio.wait_for(
                    self._subagent_manager.delegate(
                        subagent_name=state.spec.agent_name,
                        task=state.spec.task_description,
                        parent_session_id=self._parent_session_id,
                        context=state.spec.context,
                        sync=True,
                    ),
                    timeout=state.spec.timeout,
                )

                if result.success:
                    state.status = AsyncTaskStatus.COMPLETED
                    state.result = result.output
                    state.artifacts = getattr(result, "artifacts", {}) or {}
                    self._total_completed += 1

                    if self._on_complete:
                        try:
                            await self._on_complete(state)
                        except Exception as e:
                            logger.warning(f"[AsyncTaskManager] on_complete callback failed: {e}")
                else:
                    state.status = AsyncTaskStatus.FAILED
                    state.error = result.error or "子 Agent 执行失败"
                    self._total_failed += 1

                    if self._on_failed:
                        try:
                            await self._on_failed(state)
                        except Exception as e:
                            logger.warning(f"[AsyncTaskManager] on_failed callback failed: {e}")

            except asyncio.TimeoutError:
                state.status = AsyncTaskStatus.TIMEOUT
                state.error = f"执行超时（{state.spec.timeout}秒）"
                self._total_failed += 1
                logger.warning(f"[AsyncTaskManager] Task {task_id} timed out")

            except asyncio.CancelledError:
                state.status = AsyncTaskStatus.CANCELLED
                state.error = "任务被取消"
                logger.info(f"[AsyncTaskManager] Task {task_id} cancelled")

            except Exception as e:
                state.status = AsyncTaskStatus.FAILED
                state.error = str(e)
                self._total_failed += 1
                logger.error(f"[AsyncTaskManager] Task {task_id} failed: {e}")

            finally:
                state.completed_at = datetime.now()
                self._resolve_future(task_id, state)

                logger.info(
                    f"[AsyncTaskManager] Task {task_id} finished: "
                    f"status={state.status.value}, "
                    f"elapsed={state.elapsed_seconds():.1f}s"
                )

    def _resolve_future(self, task_id: str, state: AsyncTaskState) -> None:
        """完成 Future 并触发通知"""
        future = self._futures.get(task_id)
        if future and not future.done():
            future.set_result(state)
        self._completion_event.set()

    # ==================== 状态查询 ====================

    def get_status(self, task_id: str) -> Optional[AsyncTaskState]:
        """获取指定任务状态"""
        return self._tasks.get(task_id)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务的摘要状态"""
        return {
            tid: state.to_summary()
            for tid, state in self._tasks.items()
        }

    def get_completed_results(self, consume: bool = True) -> List[AsyncTaskState]:
        """
        获取已完成但未消费的任务结果。

        Args:
            consume: 是否标记为已消费（下次不再返回）

        Returns:
            已完成的任务状态列表
        """
        results = []
        for state in self._tasks.values():
            if state.is_terminal() and not state.consumed:
                results.append(state)
                if consume:
                    state.consumed = True
        return results

    def has_pending_tasks(self) -> bool:
        """是否有未完成的任务"""
        return any(
            not state.is_terminal()
            for state in self._tasks.values()
        )

    # ==================== 等待机制 ====================

    async def wait_any(self, timeout: float = 30) -> List[AsyncTaskState]:
        """
        等待任意任务完成，返回新完成的任务。

        如果已有未消费的完成结果，立即返回。
        否则阻塞直到有任务完成或超时。

        Args:
            timeout: 最大等待秒数

        Returns:
            新完成的任务状态列表
        """
        # 先检查是否有未消费结果
        existing = self.get_completed_results(consume=True)
        if existing:
            return existing

        # 等待新完成
        self._completion_event.clear()
        try:
            await asyncio.wait_for(self._completion_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        return self.get_completed_results(consume=True)

    async def wait_all(
        self,
        task_ids: List[str],
        timeout: float = 300,
    ) -> List[AsyncTaskState]:
        """
        等待指定任务全部完成。

        Args:
            task_ids: 需要等待的 task_id 列表
            timeout: 最大等待秒数

        Returns:
            指定任务的状态列表
        """
        futures = []
        for tid in task_ids:
            future = self._futures.get(tid)
            if future and not future.done():
                futures.append(future)

        if futures:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*[asyncio.shield(f) for f in futures], return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[AsyncTaskManager] wait_all timed out after {timeout}s, "
                    f"some tasks may not be complete"
                )

        results = []
        for tid in task_ids:
            state = self._tasks.get(tid)
            if state:
                if not state.consumed:
                    state.consumed = True
                results.append(state)
        return results

    # ==================== 取消 ====================

    async def cancel(self, task_id: str) -> bool:
        """
        取消指定任务。

        Args:
            task_id: 要取消的任务 ID

        Returns:
            是否成功取消
        """
        state = self._tasks.get(task_id)
        if not state:
            return False

        if state.is_terminal():
            return False

        state.status = AsyncTaskStatus.CANCELLED
        state.completed_at = datetime.now()
        state.error = "任务被用户取消"

        # 取消后台协程
        bg_task = self._bg_tasks.get(task_id)
        if bg_task and not bg_task.done():
            bg_task.cancel()

        self._resolve_future(task_id, state)

        logger.info(f"[AsyncTaskManager] Task {task_id} cancelled by user")
        return True

    # ==================== 格式化输出 ====================

    def format_status_table(self, task_ids: Optional[List[str]] = None) -> str:
        """
        格式化任务状态为 LLM 友好的文本。

        Args:
            task_ids: 指定任务 ID 列表，为空则显示全部

        Returns:
            格式化的状态文本
        """
        STATUS_ICONS = {
            AsyncTaskStatus.COMPLETED: "✓",
            AsyncTaskStatus.RUNNING: "⟳",
            AsyncTaskStatus.FAILED: "✗",
            AsyncTaskStatus.PENDING: "○",
            AsyncTaskStatus.TIMEOUT: "⏰",
            AsyncTaskStatus.CANCELLED: "⊘",
        }

        targets = task_ids or list(self._tasks.keys())
        if not targets:
            return "没有后台任务"

        lines = [f"共 {len(targets)} 个任务:\n"]
        for tid in targets:
            state = self._tasks.get(tid)
            if not state:
                lines.append(f"  [?] {tid}: 未找到")
                continue

            icon = STATUS_ICONS.get(state.status, "?")
            line = f"  [{icon}] {tid} ({state.spec.agent_name}): {state.status.value}"
            if state.started_at:
                line += f"  [{state.elapsed_seconds():.1f}s]"
            lines.append(line)

            desc = state.spec.task_description[:80]
            lines.append(f"      任务: {desc}")

            if state.result:
                preview = state.result[:200].replace("\n", " ")
                lines.append(f"      结果: {preview}")
            if state.error:
                lines.append(f"      错误: {state.error}")

        return "\n".join(lines)

    def format_results(self, states: List["AsyncTaskState"]) -> str:
        """格式化任务结果为详细文本"""
        if not states:
            return "没有任务结果"

        lines = []
        for state in states:
            lines.append(f"## Task: {state.spec.task_id}")
            lines.append(f"- Agent: {state.spec.agent_name}")
            lines.append(f"- 状态: {state.status.value}")
            lines.append(f"- 耗时: {state.elapsed_seconds():.1f}s")

            if state.result:
                lines.append(f"- 结果:\n{state.result}")
            if state.error:
                lines.append(f"- 错误: {state.error}")
            if state.artifacts:
                lines.append(f"- 产出物: {list(state.artifacts.keys())}")
            lines.append("")

        return "\n".join(lines)

    def format_notifications(self, states: List["AsyncTaskState"]) -> str:
        """
        格式化完成通知，用于注入到 LLM 上下文。

        Args:
            states: 已完成的任务状态列表

        Returns:
            格式化的通知文本
        """
        if not states:
            return ""

        lines = ["[异步任务完成通知]\n以下后台任务已完成，请根据结果继续工作：\n"]
        for state in states:
            lines.append(f"### Task {state.spec.task_id} ({state.spec.agent_name})")
            lines.append(f"状态: {state.status.value}")
            if state.result:
                lines.append(f"结果:\n{state.result}")
            if state.error:
                lines.append(f"错误: {state.error}")
            lines.append("")

        return "\n".join(lines)

    # ==================== 统计 ====================

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_spawned": self._total_spawned,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "currently_running": sum(
                1 for s in self._tasks.values()
                if s.status == AsyncTaskStatus.RUNNING
            ),
            "currently_pending": sum(
                1 for s in self._tasks.values()
                if s.status == AsyncTaskStatus.PENDING
            ),
            "max_concurrent": self._max_concurrent,
        }


__all__ = [
    "AsyncTaskStatus",
    "AsyncTaskSpec",
    "AsyncTaskState",
    "AsyncTaskManager",
]
