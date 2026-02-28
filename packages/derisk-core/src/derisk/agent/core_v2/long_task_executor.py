"""
LongRunningTaskExecutor - 超长任务执行器

专为超长任务设计的执行器：
- 支持无限步骤执行
- 自动状态持久化
- 断点续执行
- 自动压缩上下文
- 进度追踪和报告
"""

from typing import Dict, Any, List, Optional, AsyncIterator, Callable, Awaitable
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import logging
import uuid
from dataclasses import dataclass, field as dataclass_field

from .agent_harness import (
    AgentHarness,
    ExecutionContext,
    CheckpointManager,
    CheckpointType,
    StateCompressor,
    CircuitBreaker,
    TaskQueue,
    ExecutionSnapshot,
    ExecutionState,
    StateStore,
    FileStateStore,
    MemoryStateStore,
)
from .execution_replay import ReplayManager, ReplayEventType
from .context_validation import ContextValidationManager, ValidationResult

logger = logging.getLogger(__name__)


class LongTaskStatus(str, Enum):
    """超长任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProgressPhase(str, Enum):
    """进度阶段"""
    INITIALIZATION = "initialization"
    PLANNING = "planning"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    COMPLETION = "completion"


@dataclass
class ProgressReport:
    """进度报告"""
    phase: ProgressPhase
    current_step: int
    total_steps: int
    current_goal: str
    completed_goals: int
    total_goals: int
    
    elapsed_time: float
    estimated_remaining: float
    
    messages_processed: int
    tools_called: int
    tokens_used: int
    
    checkpoint_count: int
    last_checkpoint_time: Optional[datetime] = None
    
    status: LongTaskStatus = LongTaskStatus.RUNNING
    progress_percent: float = 0.0
    
    def __post_init__(self):
        if self.total_steps > 0:
            self.progress_percent = min(100.0, (self.current_step / self.total_steps) * 100)


class LongTaskConfig(BaseModel):
    """超长任务配置"""
    max_steps: int = Field(default=10000, description="最大步骤数")
    checkpoint_interval: int = Field(default=50, description="检查点间隔步数")
    auto_compress_interval: int = Field(default=100, description="自动压缩间隔步数")
    progress_report_interval: int = Field(default=10, description="进度报告间隔步数")
    
    timeout: int = Field(default=86400, description="超时时间(秒, 默认24小时)")
    auto_pause_on_error: bool = Field(default=True, description="错误时自动暂停")
    auto_resume_delay: int = Field(default=30, description="自动恢复延迟(秒)")
    
    enable_recording: bool = Field(default=True, description="是否启用录制")
    enable_validation: bool = Field(default=True, description="是否启用验证")
    
    storage_backend: str = Field(default="file", description="存储后端")
    storage_path: str = Field(default=".long_tasks", description="存储路径")


class LongRunningTaskExecutor:
    """
    超长任务执行器
    
    完整的超长任务解决方案：
    - 持久化执行：重启后继续
    - 检查点机制：stantial任意点恢复
    - 自动压缩：防止上下文溢出
    - 进度追踪：实时进度报告
    - 录制重放：完整执行记录
    - 上下文验证：确保状态正确
    
    示例:
        executor = LongRunningTaskExecutor(agent, config)
        
        # 执行任务
        execution_id = await executor.execute("完成研究任务")
        
        # 获取进度
        progress = executor.get_progress(execution_id)
        
        # 暂停/恢复
        await executor.pause(execution_id)
        await executor.resume(execution_id)
    """
    
    def __init__(
        self,
        agent: Any,
        config: LongTaskConfig = None,
        on_progress: Optional[Callable[[ProgressReport], Awaitable[None]]] = None,
        on_checkpoint: Optional[Callable[[str], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str, Exception], Awaitable[None]]] = None
    ):
        self.agent = agent
        self.config = config or LongTaskConfig()
        
        self.on_progress = on_progress
        self.on_checkpoint = on_checkpoint
        self.on_error = on_error
        
        if self.config.storage_backend == "file":
            self.store = FileStateStore(self.config.storage_path)
        else:
            self.store = MemoryStateStore()
        
        self.checkpoint_manager = CheckpointManager(
            self.store,
            auto_checkpoint_interval=self.config.checkpoint_interval
        )
        
        self.state_compressor = StateCompressor()
        
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=10,
            recovery_timeout=60
        )
        
        self.task_queue = TaskQueue()
        
        self.replay_manager = ReplayManager()
        
        self.validation_manager = ContextValidationManager()
        
        self._executions: Dict[str, ExecutionSnapshot] = {}
        self._progress: Dict[str, ProgressReport] = {}
        self._recordings: Dict[str, Any] = {}
        self._contexts: Dict[str, ExecutionContext] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
    
    async def execute(
        self,
        task: str,
        context: Optional[ExecutionContext] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """执行超长任务"""
        execution_id = str(uuid.uuid4().hex)
        
        context = context or ExecutionContext()
        
        if self.config.enable_validation:
            validation_results, context_dict = self.validation_manager.validate_and_fix(
                context.to_dict()
            )
            errors = [r for r in validation_results if not r.is_valid]
            if errors:
                logger.warning(f"[LongTaskExecutor] 上下文验证发现问题: {len(errors)}个")
        
        snapshot = ExecutionSnapshot(
            execution_id=execution_id,
            agent_name=self.agent.info.name if hasattr(self.agent, "info") else "agent",
            status=ExecutionState.RUNNING,
            context=context.to_dict(),
            metadata={
                **(metadata or {}),
                "task": task,
                "config": self.config.dict()
            }
        )
        
        self._executions[execution_id] = snapshot
        self._contexts[execution_id] = context
        
        has_goals = hasattr(self.agent, 'goal_manager')
        total_goals = len(snapshot.goals) if has_goals else 1
        
        progress = ProgressReport(
            phase=ProgressPhase.INITIALIZATION,
            current_step=0,
            total_steps=self.config.max_steps,
            current_goal=task[:100],
            completed_goals=0,
            total_goals=total_goals,
            elapsed_time=0.0,
            estimated_remaining=0.0,
            messages_processed=0,
            tools_called=0,
            tokens_used=0,
            checkpoint_count=0
        )
        self._progress[execution_id] = progress
        
        if self.config.enable_recording:
            recording = self.replay_manager.start_recording(execution_id)
            recording.record(
                ReplayEventType.STEP_START,
                {"task": task},
                step_index=0
            )
            self._recordings[execution_id] = recording
        
        await self._save_execution(execution_id)
        
        task_coro = asyncio.create_task(
            self._run_task(execution_id, task)
        )
        self._tasks[execution_id] = task_coro
        
        logger.info(f"[LongTaskExecutor] 开始执行: {execution_id[:8]}")
        
        return execution_id
    
    async def _run_task(self, execution_id: str, task: str):
        """运行任务"""
        snapshot = self._executions.get(execution_id)
        progress = self._progress.get(execution_id)
        recording = self._recordings.get(execution_id)
        context = self._contexts.get(execution_id)
        
        if not snapshot or not progress:
            return
        
        start_time = datetime.now()
        
        try:
            if not self.circuit_breaker.can_execute():
                raise RuntimeError("Circuit breaker is open")
            
            progress.phase = ProgressPhase.PLANNING
            await self._report_progress(execution_id)
            
            progress.phase = ProgressPhase.EXECUTION
            
            if hasattr(self.agent, "run"):
                async for chunk in self.agent.run(task):
                    if snapshot.status == ExecutionState.PAUSED:
                        await self._wait_for_resume(execution_id)
                    
                    if snapshot.status == ExecutionState.CANCELLED:
                        break
                    
                    snapshot.current_step += 1
                    progress.current_step = snapshot.current_step
                    
                    snapshot.messages.append({
                        "role": "assistant",
                        "content": chunk,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    if recording:
                        recording.record(
                            ReplayEventType.MESSAGE,
                            {"chunk": chunk[:200]},
                            step_index=snapshot.current_step
                        )
                    
                    if await self.checkpoint_manager.should_auto_checkpoint(
                        execution_id, snapshot.current_step
                    ):
                        await self._create_checkpoint(execution_id)
                    
                    if snapshot.current_step % self.config.auto_compress_interval == 0:
                        snapshot = await self.state_compressor.compress(snapshot)
                    
                    if snapshot.current_step % self.config.progress_report_interval == 0:
                        progress.elapsed_time = (datetime.now() - start_time).total_seconds()
                        if progress.current_step > 0:
                            avg_time_per_step = progress.elapsed_time / progress.current_step
                            progress.estimated_remaining = avg_time_per_step * (progress.total_steps - progress.current_step)
                        await self._report_progress(execution_id)
                    
                    await self._save_execution(execution_id)
            
            progress.phase = ProgressPhase.VERIFICATION
            await self._report_progress(execution_id)
            
            snapshot.status = ExecutionState.COMPLETED
            progress.phase = ProgressPhase.COMPLETION
            progress.status = LongTaskStatus.COMPLETED
            progress.progress_percent = 100.0
            
            self.circuit_breaker.record_success()
            
            await self._create_checkpoint(execution_id)
            
            if recording:
                recording.record(
                    ReplayEventType.STEP_END,
                    {"status": "completed"},
                    step_index=snapshot.current_step
                )
                self.replay_manager.end_recording(execution_id)
            
            logger.info(f"[LongTaskExecutor] 任务完成: {execution_id[:8]}")
            
        except Exception as e:
            snapshot.status = ExecutionState.FAILED
            snapshot.error = str(e)
            progress.status = LongTaskStatus.FAILED
            
            self.circuit_breaker.record_failure()
            
            if recording:
                recording.record(
                    ReplayEventType.ERROR,
                    {"error": str(e), "type": type(e).__name__},
                    step_index=snapshot.current_step
                )
            
            if self.on_error:
                await self.on_error(execution_id, e)
            
            logger.error(f"[LongTaskExecutor] 任务失败: {execution_id[:8]} - {e}")
        
        finally:
            snapshot.updated_at = datetime.now()
            progress.elapsed_time = (datetime.now() - start_time).total_seconds()
            await self._save_execution(execution_id)
            await self._report_progress(execution_id)
    
    async def _create_checkpoint(self, execution_id: str):
        """创建检查点"""
        snapshot = self._executions.get(execution_id)
        context = self._contexts.get(execution_id)
        progress = self._progress.get(execution_id)
        
        if not snapshot:
            return
        
        await self.checkpoint_manager.create_checkpoint(
            execution_id=execution_id,
            checkpoint_type=CheckpointType.AUTOMATIC,
            state=snapshot.dict(),
            context=context,
            step_index=snapshot.current_step,
            message=f"自动检查点 @ step {snapshot.current_step}"
        )
        
        progress.checkpoint_count += 1
        progress.last_checkpoint_time = datetime.now()
        
        if self.on_checkpoint:
            await self.on_checkpoint(execution_id)
    
    async def _save_execution(self, execution_id: str):
        """保存执行状态"""
        snapshot = self._executions.get(execution_id)
        if snapshot:
            await self.store.save(
                f"execution_{execution_id}",
                snapshot.dict()
            )
    
    async def _report_progress(self, execution_id: str):
        """报告进度"""
        if self.on_progress:
            progress = self._progress.get(execution_id)
            if progress:
                await self.on_progress(progress)
    
    async def _wait_for_resume(self, execution_id: str):
        """等待恢复"""
        while self._executions.get(execution_id, {}).get("status") == ExecutionState.PAUSED:
            await asyncio.sleep(1)
    
    async def pause(self, execution_id: str):
        """暂停任务"""
        snapshot = self._executions.get(execution_id)
        progress = self._progress.get(execution_id)
        
        if snapshot and snapshot.status == ExecutionState.RUNNING:
            snapshot.status = ExecutionState.PAUSED
            progress.status = LongTaskStatus.PAUSED
            
            await self._create_checkpoint(execution_id)
            await self._save_execution(execution_id)
            
            logger.info(f"[LongTaskExecutor] 已暂停: {execution_id[:8]}")
    
    async def resume(self, execution_id: str):
        """恢复任务"""
        snapshot = self._executions.get(execution_id)
        progress = self._progress.get(execution_id)
        
        if snapshot and snapshot.status == ExecutionState.PAUSED:
            snapshot.status = ExecutionState.RUNNING
            progress.status = LongTaskStatus.RUNNING
            
            await self._save_execution(execution_id)
            
            logger.info(f"[LongTaskExecutor] 已恢复: {execution_id[:8]}")
    
    async def cancel(self, execution_id: str):
        """取消任务"""
        snapshot = self._executions.get(execution_id)
        progress = self._progress.get(execution_id)
        
        if snapshot:
            snapshot.status = ExecutionState.CANCELLED
            progress.status = LongTaskStatus.CANCELLED
            
            if execution_id in self._tasks:
                self._tasks[execution_id].cancel()
            
            await self._save_execution(execution_id)
            
            logger.info(f"[LongTaskExecutor] 已取消: {execution_id[:8]}")
    
    async def restore_from_checkpoint(self, checkpoint_id: str) -> Optional[str]:
        """从检查点恢复"""
        restored = await self.checkpoint_manager.restore_checkpoint(checkpoint_id)
        
        if not restored:
            return None
        
        snapshot_data = restored["state"]
        snapshot = ExecutionSnapshot(**snapshot_data)
        snapshot.status = ExecutionState.RUNNING
        
        execution_id = snapshot.execution_id
        self._executions[execution_id] = snapshot
        
        if restored["context"]:
            if isinstance(restored["context"], dict):
                context = ExecutionContext.from_dict(restored["context"])
            else:
                context = restored["context"]
            self._contexts[execution_id] = context
        
        progress = ProgressReport(
            phase=ProgressPhase.EXECUTION,
            current_step=snapshot.current_step,
            total_steps=self.config.max_steps,
            current_goal="从检查点恢复",
            completed_goals=len(snapshot.completed_goals),
            total_goals=len(snapshot.goals),
            elapsed_time=0.0,
            estimated_remaining=0.0,
            messages_processed=len(snapshot.messages),
            tools_called=len(snapshot.tool_history),
            tokens_used=snapshot.metadata.get("tokens_used", 0),
            checkpoint_count=0
        )
        self._progress[execution_id] = progress
        
        await self._save_execution(execution_id)
        
        task_coro = asyncio.create_task(
            self._run_task(execution_id, "恢复执行")
        )
        self._tasks[execution_id] = task_coro
        
        logger.info(f"[LongTaskExecutor] 从检查点恢复: {checkpoint_id[:8]}")
        
        return execution_id
    
    def get_progress(self, execution_id: str) -> Optional[ProgressReport]:
        """获取进度"""
        return self._progress.get(execution_id)
    
    def get_snapshot(self, execution_id: str) -> Optional[ExecutionSnapshot]:
        """获取快照"""
        return self._executions.get(execution_id)
    
    async def list_executions(self) -> List[Dict[str, Any]]:
        """列出所有执行"""
        return [
            {
                "execution_id": e.execution_id,
                "status": e.status,
                "current_step": e.current_step,
                "created_at": e.created_at.isoformat(),
                "updated_at": e.updated_at.isoformat(),
                "error": e.error
            }
            for e in self._executions.values()
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "total_executions": len(self._executions),
            "running": sum(1 for e in self._executions.values() if e.status == ExecutionState.RUNNING),
            "paused": sum(1 for e in self._executions.values() if e.status == ExecutionState.PAUSED),
            "completed": sum(1 for e in self._executions.values() if e.status == ExecutionState.COMPLETED),
            "failed": sum(1 for e in self._executions.values() if e.status == ExecutionState.FAILED),
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "replay_manager": self.replay_manager.get_statistics()
        }


long_running_task_executor = LongRunningTaskExecutor