"""
AgentHarness - Agent执行框架

实现完整的Agent执行基础设施：
- Durable Execution: 持久化执行，重启后恢复
- Checkpointing: 检查点机制，状态快照
- Pause/Resume: 暂停和恢复
- State Compression: 智能状态压缩
- Circuit Breaker: 熔断机制
- Task Queue: 异步任务队列
- Context Lifecycle: 上下文生命周期管理（增强）

专为超长任务设计
"""

from typing import Dict, Any, List, Optional, Callable, Awaitable, AsyncIterator, TYPE_CHECKING
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import uuid
import json
import asyncio
import logging
import pickle
import hashlib
from pathlib import Path
from dataclasses import dataclass, field as dataclass_field

if TYPE_CHECKING:
    from derisk.agent.core_v2.context_lifecycle import (
        ContextLifecycleOrchestrator,
        ExitTrigger,
        SkillExitResult,
    )

logger = logging.getLogger(__name__)


class ExecutionState(str, Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CheckpointType(str, Enum):
    """检查点类型"""
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    TASK_START = "task_start"
    TASK_END = "task_end"
    ERROR = "error"
    MILESTONE = "milestone"


class ContextLayer(str, Enum):
    """上下文层级"""
    SYSTEM = "system"
    TASK = "task"
    TOOL = "tool"
    MEMORY = "memory"
    TEMPORARY = "temporary"


@dataclass
class ExecutionContext:
    """分层上下文"""
    system_layer: Dict[str, Any] = dataclass_field(default_factory=dict)
    task_layer: Dict[str, Any] = dataclass_field(default_factory=dict)
    tool_layer: Dict[str, Any] = dataclass_field(default_factory=dict)
    memory_layer: Dict[str, Any] = dataclass_field(default_factory=dict)
    temporary_layer: Dict[str, Any] = dataclass_field(default_factory=dict)
    
    def get_layer(self, layer: ContextLayer) -> Dict[str, Any]:
        layers = {
            ContextLayer.SYSTEM: self.system_layer,
            ContextLayer.TASK: self.task_layer,
            ContextLayer.TOOL: self.tool_layer,
            ContextLayer.MEMORY: self.memory_layer,
            ContextLayer.TEMPORARY: self.temporary_layer,
        }
        return layers.get(layer, {})
    
    def set_layer(self, layer: ContextLayer, data: Dict[str, Any]):
        if layer == ContextLayer.SYSTEM:
            self.system_layer = data
        elif layer == ContextLayer.TASK:
            self.task_layer = data
        elif layer == ContextLayer.TOOL:
            self.tool_layer = data
        elif layer == ContextLayer.MEMORY:
            self.memory_layer = data
        elif layer == ContextLayer.TEMPORARY:
            self.temporary_layer = data
    
    def merge_all(self) -> Dict[str, Any]:
        merged = {}
        merged.update(self.system_layer)
        merged.update(self.task_layer)
        merged.update(self.tool_layer)
        merged.update(self.memory_layer)
        merged.update(self.temporary_layer)
        return merged
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_layer": self.system_layer,
            "task_layer": self.task_layer,
            "tool_layer": self.tool_layer,
            "memory_layer": self.memory_layer,
            "temporary_layer": self.temporary_layer,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionContext":
        return cls(
            system_layer=data.get("system_layer", {}),
            task_layer=data.get("task_layer", {}),
            tool_layer=data.get("tool_layer", {}),
            memory_layer=data.get("memory_layer", {}),
            temporary_layer=data.get("temporary_layer", {}),
        )


class Checkpoint(BaseModel):
    """检查点"""
    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    execution_id: str
    checkpoint_type: CheckpointType
    timestamp: datetime = Field(default_factory=datetime.now)
    
    state: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    
    step_index: int = 0
    message: Optional[str] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    checksum: Optional[str] = None
    
    class Config:
        use_enum_values = True
    
    def compute_checksum(self) -> str:
        data = json.dumps({
            "state": self.state,
            "context": self.context,
            "step_index": self.step_index
        }, sort_keys=True, default=str)
        return hashlib.md5(data.encode()).hexdigest()


class ExecutionSnapshot(BaseModel):
    """执行快照 - 完整的执行状态"""
    execution_id: str
    agent_name: str
    status: ExecutionState
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    current_step: int = 0
    total_steps: int = 0
    
    context: Dict[str, Any] = Field(default_factory=dict)
    variables: Dict[str, Any] = Field(default_factory=dict)
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    
    goals: List[Dict[str, Any]] = Field(default_factory=list)
    completed_goals: List[str] = Field(default_factory=list)
    
    tool_history: List[Dict[str, Any]] = Field(default_factory=list)
    decision_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    checkpoints: List[str] = Field(default_factory=list)
    
    error: Optional[str] = None
    error_stack: Optional[str] = None
    retry_count: int = 0
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


class StateStore(ABC):
    """状态存储基类"""
    
    @abstractmethod
    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        pass
    
    @abstractmethod
    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    async def list_keys(self, prefix: str) -> List[str]:
        pass


class FileStateStore(StateStore):
    """文件系统状态存储"""
    
    def __init__(self, base_dir: str = ".agent_state"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        try:
            file_path = self.base_dir / f"{key}.json"
            file_path.write_text(json.dumps(data, default=str, indent=2))
            return True
        except Exception as e:
            logger.error(f"[FileStateStore] Save failed: {e}")
            return False
    
    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            file_path = self.base_dir / f"{key}.json"
            if file_path.exists():
                return json.loads(file_path.read_text())
            return None
        except Exception as e:
            logger.error(f"[FileStateStore] Load failed: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        try:
            file_path = self.base_dir / f"{key}.json"
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"[FileStateStore] Delete failed: {e}")
            return False
    
    async def list_keys(self, prefix: str) -> List[str]:
        keys = []
        for file_path in self.base_dir.glob(f"{prefix}*.json"):
            keys.append(file_path.stem)
        return keys


class MemoryStateStore(StateStore):
    """内存状态存储"""
    
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
    
    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        self._store[key] = data
        return True
    
    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)
    
    async def delete(self, key: str) -> bool:
        self._store.pop(key, None)
        return True
    
    async def list_keys(self, prefix: str) -> List[str]:
        return [k for k in self._store.keys() if k.startswith(prefix)]


class CheckpointManager:
    """
    检查点管理器
    
    职责:
    1. 创建和管理检查点
    2. 自动检查点策略
    3. 检查点恢复
    4. 状态压缩
    
    示例:
        manager = CheckpointManager(store)
        
        # 创建检查点
        checkpoint = await manager.create_checkpoint(
            execution_id="exec-1",
            checkpoint_type=CheckpointType.MILESTONE,
            state=current_state
        )
        
        # 恢复检查点
        snapshot = await manager.restore_checkpoint(checkpoint.checkpoint_id)
    """
    
    def __init__(
        self,
        store: StateStore,
        auto_checkpoint_interval: int = 10,
        max_checkpoints: int = 20
    ):
        self.store = store
        self.auto_checkpoint_interval = auto_checkpoint_interval
        self.max_checkpoints = max_checkpoints
        self._checkpoints: Dict[str, Checkpoint] = {}
        self._step_counter: Dict[str, int] = {}
    
    async def create_checkpoint(
        self,
        execution_id: str,
        checkpoint_type: CheckpointType,
        state: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
        step_index: int = 0,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Checkpoint:
        """创建检查点"""
        checkpoint = Checkpoint(
            execution_id=execution_id,
            checkpoint_type=checkpoint_type,
            state=state,
            context=context.to_dict() if context else {},
            step_index=step_index,
            message=message,
            metadata=metadata or {}
        )
        
        checkpoint.checksum = checkpoint.compute_checksum()
        
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        
        await self.store.save(
            f"checkpoint_{checkpoint.checkpoint_id}",
            checkpoint.dict()
        )
        
        await self._cleanup_old_checkpoints(execution_id)
        
        logger.info(
            f"[CheckpointManager] 创建检查点: {checkpoint.checkpoint_id[:8]} "
            f"类型={checkpoint_type} 步骤={step_index}"
        )
        
        return checkpoint
    
    async def should_auto_checkpoint(self, execution_id: str, step_index: int) -> bool:
        """判断是否应该自动创建检查点"""
        last_step = self._step_counter.get(execution_id, 0)
        
        if step_index - last_step >= self.auto_checkpoint_interval:
            self._step_counter[execution_id] = step_index
            return True
        
        return False
    
    async def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """获取检查点"""
        if checkpoint_id in self._checkpoints:
            return self._checkpoints[checkpoint_id]
        
        data = await self.store.load(f"checkpoint_{checkpoint_id}")
        if data:
            checkpoint = Checkpoint(**data)
            self._checkpoints[checkpoint_id] = checkpoint
            return checkpoint
        
        return None
    
    async def get_latest_checkpoint(self, execution_id: str) -> Optional[Checkpoint]:
        """获取最新检查点"""
        keys = await self.store.list_keys(f"checkpoint_")
        
        checkpoints = []
        for key in keys:
            data = await self.store.load(key)
            if data and data.get("execution_id") == execution_id:
                checkpoints.append(Checkpoint(**data))
        
        if not checkpoints:
            return None
        
        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        return checkpoints[0]
    
    async def restore_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """恢复检查点"""
        checkpoint = await self.get_checkpoint(checkpoint_id)
        
        if not checkpoint:
            logger.error(f"[CheckpointManager] 检查点不存在: {checkpoint_id}")
            return None
        
        if checkpoint.checksum != checkpoint.compute_checksum():
            logger.error(f"[CheckpointManager] 检查点校验失败: {checkpoint_id}")
            return None
        
        logger.info(f"[CheckpointManager] 恢复检查点: {checkpoint_id[:8]}")
        
        return {
            "state": checkpoint.state,
            "context": ExecutionContext.from_dict(checkpoint.context),
            "step_index": checkpoint.step_index,
        }
    
    async def list_checkpoints(self, execution_id: str) -> List[Checkpoint]:
        """列出所有检查点"""
        keys = await self.store.list_keys(f"checkpoint_")
        
        checkpoints = []
        for key in keys:
            data = await self.store.load(key)
            if data and data.get("execution_id") == execution_id:
                checkpoints.append(Checkpoint(**data))
        
        checkpoints.sort(key=lambda c: c.timestamp)
        return checkpoints
    
    async def _cleanup_old_checkpoints(self, execution_id: str):
        """清理旧检查点"""
        checkpoints = await self.list_checkpoints(execution_id)
        
        if len(checkpoints) > self.max_checkpoints:
            to_remove = checkpoints[:-self.max_checkpoints]
            
            for cp in to_remove:
                await self.store.delete(f"checkpoint_{cp.checkpoint_id}")
                self._checkpoints.pop(cp.checkpoint_id, None)
            
            logger.info(f"[CheckpointManager] 清理了 {len(to_remove)} 个旧检查点")


class CircuitBreaker:
    """
    熔断器
    
    防止级联失败，实现快速失败
    
    示例:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        
        if breaker.can_execute():
            try:
                result = await operation()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
        else:
            raise CircuitBreakerOpenError()
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_requests: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests
        
        self._state = "closed"
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_count = 0
    
    def can_execute(self) -> bool:
        """是否可以执行"""
        if self._state == "closed":
            return True
        
        if self._state == "open":
            if self._should_attempt_recovery():
                self._state = "half_open"
                self._half_open_count = 0
                return True
            return False
        
        if self._state == "half_open":
            if self._half_open_count < self.half_open_requests:
                self._half_open_count += 1
                return True
            return False
        
        return False
    
    def record_success(self):
        """记录成功"""
        if self._state == "half_open":
            self._success_count += 1
            if self._success_count >= self.half_open_requests:
                self._reset()
        else:
            self._failure_count = 0
    
    def record_failure(self):
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = datetime.now()
        
        if self._state == "half_open":
            self._state = "open"
            self._success_count = 0
        
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
    
    def _should_attempt_recovery(self) -> bool:
        """是否应该尝试恢复"""
        if not self._last_failure_time:
            return False
        
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
    
    def _reset(self):
        """重置"""
        self._state = "closed"
        self._failure_count = 0
        self._success_count = 0
        self._half_open_count = 0
    
    @property
    def state(self) -> str:
        return self._state
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "state": self._state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
        }


class TaskQueue:
    """
    任务队列
    
    支持优先级、延时执行、重试
    
    示例:
        queue = TaskQueue()
        
        await queue.enqueue("task-1", {"action": "search"}, priority=1)
        
        task = await queue.dequeue()
        await queue.process(task, handler)
    """
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._processing: Dict[str, Dict[str, Any]] = {}
        self._completed: Dict[str, Dict[str, Any]] = {}
        self._failed: Dict[str, Dict[str, Any]] = {}
    
    async def enqueue(
        self,
        task_id: str,
        task_data: Dict[str, Any],
        priority: int = 0,
        delay_seconds: int = 0,
        max_retries: int = 3
    ) -> bool:
        """入队"""
        if self._queue.full():
            raise RuntimeError("Task queue is full")
        
        task = {
            "task_id": task_id,
            "data": task_data,
            "priority": priority,
            "delay_seconds": delay_seconds,
            "max_retries": max_retries,
            "retry_count": 0,
            "created_at": datetime.now().isoformat(),
            "status": "pending",
        }
        
        self._pending[task_id] = task
        
        await self._queue.put((priority, task_id, task))
        
        logger.debug(f"[TaskQueue] 入队: {task_id}")
        return True
    
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """出队"""
        try:
            if timeout:
                priority, task_id, task = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=timeout
                )
            else:
                priority, task_id, task = await self._queue.get()
            
            task["status"] = "processing"
            task["started_at"] = datetime.now().isoformat()
            
            self._pending.pop(task_id, None)
            self._processing[task_id] = task
            
            return task
            
        except asyncio.TimeoutError:
            return None
    
    async def complete(self, task_id: str, result: Any = None):
        """完成任务"""
        task = self._processing.pop(task_id, None)
        if task:
            task["status"] = "completed"
            task["result"] = result
            task["completed_at"] = datetime.now().isoformat()
            self._completed[task_id] = task
            logger.debug(f"[TaskQueue] 完成: {task_id}")
    
    async def fail(self, task_id: str, error: str, retry: bool = True):
        """任务失败"""
        task = self._processing.pop(task_id, None)
        if task:
            task["error"] = error
            task["failed_at"] = datetime.now().isoformat()
            
            if retry and task["retry_count"] < task["max_retries"]:
                task["retry_count"] += 1
                task["status"] = "pending"
                self._pending[task_id] = task
                await self._queue.put((task["priority"], task_id, task))
                logger.info(f"[TaskQueue] 重试: {task_id} ({task['retry_count']}/{task['max_retries']})")
            else:
                task["status"] = "failed"
                self._failed[task_id] = task
                logger.error(f"[TaskQueue] 失败: {task_id} - {error}")
    
    async def requeue_pending(self):
        """重新入队所有待处理任务"""
        for task_id, task in list(self._processing.items()):
            task["status"] = "pending"
            self._pending[task_id] = task
            await self._queue.put((task["priority"], task_id, task))
        
        self._processing.clear()
        logger.info("[TaskQueue] 已重新入队所有待处理任务")
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "queue_size": self._queue.qsize(),
            "pending": len(self._pending),
            "processing": len(self._processing),
            "completed": len(self._completed),
            "failed": len(self._failed),
        }


class StateCompressor:
    """
    状态压缩器
    
    智能压缩上下文以适应长任务
    
    策略:
    1. 移除过期的临时数据
    2. 压缩历史消息
    3. 合并重复信息
    4. 提取关键信息摘要
    """
    
    def __init__(
        self,
        max_messages: int = 50,
        max_tool_history: int = 30,
        max_decision_history: int = 20,
        llm_client: Optional[Any] = None
    ):
        self.max_messages = max_messages
        self.max_tool_history = max_tool_history
        self.max_decision_history = max_decision_history
        self.llm_client = llm_client
    
    async def compress(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
        """压缩执行快照"""
        compressed = snapshot.copy(deep=True)
        
        compressed.messages = await self._compress_messages(compressed.messages)
        compressed.tool_history = self._compress_list(
            compressed.tool_history, 
            self.max_tool_history
        )
        compressed.decision_history = self._compress_list(
            compressed.decision_history,
            self.max_decision_history
        )
        
        compressed.context = await self._compress_context(compressed.context)
        
        return compressed
    
    async def _compress_messages(
        self, 
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """压缩消息列表"""
        if len(messages) <= self.max_messages:
            return messages
        
        keep_recent = messages[-int(self.max_messages * 0.6):]
        
        to_summarize = messages[:-len(keep_recent)]
        
        if to_summarize and self.llm_client:
            summary = await self._summarize_messages(to_summarize)
            summary_msg = {
                "role": "system",
                "content": f"[历史消息摘要]\n{summary}",
                "metadata": {"compressed": True, "original_count": len(to_summarize)}
            }
            return [summary_msg] + keep_recent
        
        return keep_recent
    
    async def _summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        """生成消息摘要"""
        if not self.llm_client:
            return f"已压缩 {len(messages)} 条历史消息"
        
        try:
            content = "\n".join([
                f"{m.get('role', 'unknown')}: {str(m.get('content', ''))[:200]}"
                for m in messages[-20:]
            ])
            
            prompt = f"请简洁总结以下对话的关键信息（2-3句话）:\n\n{content}"
            
            from .llm_utils import call_llm
            result = await call_llm(self.llm_client, prompt)
            if result:
                return result
            
        except Exception as e:
            logger.error(f"[StateCompressor] 生成摘要失败: {e}")
        
        return f"已压缩 {len(messages)} 条历史消息"
    
    def _compress_list(
        self, 
        items: List[Dict[str, Any]], 
        max_items: int
    ) -> List[Dict[str, Any]]:
        """压缩列表"""
        if len(items) <= max_items:
            return items
        return items[-max_items:]
    
    async def _compress_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """压缩上下文"""
        compressed = context.copy()
        
        if "temporary" in compressed:
            del compressed["temporary"]
        
        return compressed


class AgentHarness:
    """
    Agent Harness - 完整的Agent执行框架
    
    集成所有组件，提供统一的执行环境：
    - 持久化执行
    - 检查点管理
    - 熔断保护
    - 任务队列
    - 状态压缩
    - 暂停/恢复
    - 上下文生命周期管理（增强）
    
    示例:
        harness = AgentHarness(agent, config)
        
        # 执行任务
        execution_id = await harness.start_execution("研究AI发展")
        
        # 暂停
        await harness.pause_execution(execution_id)
        
        # 恢复
        await harness.resume_execution(execution_id)
        
        # 从检查点恢复
        await harness.restore_from_checkpoint(checkpoint_id)
        
        # Skill生命周期管理
        await harness.prepare_skill("code_review", skill_content)
        result = await harness.complete_skill("code_review", summary)
    """
    
    def __init__(
        self,
        agent: Any,
        state_store: Optional[StateStore] = None,
        checkpoint_interval: int = 10,
        max_checkpoints: int = 20,
        circuit_breaker_config: Optional[Dict[str, Any]] = None,
        llm_client: Optional[Any] = None,
        context_lifecycle: Optional["ContextLifecycleOrchestrator"] = None,
    ):
        self.agent = agent
        
        self.store = state_store or MemoryStateStore()
        self.checkpoint_manager = CheckpointManager(
            self.store,
            auto_checkpoint_interval=checkpoint_interval,
            max_checkpoints=max_checkpoints
        )
        
        self.circuit_breaker = CircuitBreaker(
            **(circuit_breaker_config or {})
        )
        
        self.task_queue = TaskQueue()
        self.state_compressor = StateCompressor(llm_client=llm_client)
        
        self._context_lifecycle = context_lifecycle
        self._current_skill: Optional[str] = None
        
        self._executions: Dict[str, ExecutionSnapshot] = {}
        self._paused_executions: Dict[str, datetime] = {}
    
    @property
    def context_lifecycle(self) -> Optional["ContextLifecycleOrchestrator"]:
        """获取上下文生命周期管理器"""
        return self._context_lifecycle
    
    def set_context_lifecycle(
        self, 
        context_lifecycle: "ContextLifecycleOrchestrator"
    ) -> "AgentHarness":
        """设置上下文生命周期管理器"""
        self._context_lifecycle = context_lifecycle
        return self
    
    async def start_execution(
        self,
        task: str,
        context: Optional[ExecutionContext] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """开始执行"""
        execution_id = str(uuid.uuid4().hex)
        
        snapshot = ExecutionSnapshot(
            execution_id=execution_id,
            agent_name=self.agent.info.name if hasattr(self.agent, "info") else "agent",
            status=ExecutionState.RUNNING,
            context=context.to_dict() if context else {},
            metadata=metadata or {}
        )
        
        self._executions[execution_id] = snapshot
        
        await self._save_snapshot(snapshot)
        
        await self.checkpoint_manager.create_checkpoint(
            execution_id=execution_id,
            checkpoint_type=CheckpointType.TASK_START,
            state=snapshot.dict(),
            message=f"开始执行: {task[:100]}"
        )
        
        logger.info(f"[AgentHarness] 开始执行: {execution_id[:8]}")
        
        asyncio.create_task(self._run_execution(execution_id, task))
        
        return execution_id
    
    async def _run_execution(self, execution_id: str, task: str):
        """执行任务"""
        snapshot = self._executions.get(execution_id)
        if not snapshot:
            return
        
        try:
            if not self.circuit_breaker.can_execute():
                raise RuntimeError("Circuit breaker is open")
            
            snapshot.status = ExecutionState.RUNNING
            
            if hasattr(self.agent, "run"):
                async for chunk in self.agent.run(task):
                    if execution_id in self._paused_executions:
                        await self._wait_for_resume(execution_id)
                    
                    snapshot.current_step += 1
                    snapshot.messages.append({
                        "type": "chunk",
                        "content": chunk,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    if await self.checkpoint_manager.should_auto_checkpoint(
                        execution_id, snapshot.current_step
                    ):
                        await self.checkpoint_manager.create_checkpoint(
                            execution_id=execution_id,
                            checkpoint_type=CheckpointType.AUTOMATIC,
                            state=snapshot.dict(),
                            step_index=snapshot.current_step
                        )
                    
                    await self._save_snapshot(snapshot)
            
            snapshot.status = ExecutionState.COMPLETED
            self.circuit_breaker.record_success()
            
            await self.checkpoint_manager.create_checkpoint(
                execution_id=execution_id,
                checkpoint_type=CheckpointType.TASK_END,
                state=snapshot.dict(),
                message="执行完成"
            )
            
            logger.info(f"[AgentHarness] 执行完成: {execution_id[:8]}")
            
        except Exception as e:
            snapshot.status = ExecutionState.FAILED
            snapshot.error = str(e)
            self.circuit_breaker.record_failure()
            
            await self.checkpoint_manager.create_checkpoint(
                execution_id=execution_id,
                checkpoint_type=CheckpointType.ERROR,
                state=snapshot.dict(),
                message=f"执行失败: {str(e)}"
            )
            
            logger.error(f"[AgentHarness] 执行失败: {execution_id[:8]} - {e}")
        
        finally:
            snapshot.updated_at = datetime.now()
            await self._save_snapshot(snapshot)
    
    async def pause_execution(self, execution_id: str):
        """暂停执行"""
        snapshot = self._executions.get(execution_id)
        if snapshot and snapshot.status == ExecutionState.RUNNING:
            snapshot.status = ExecutionState.PAUSED
            self._paused_executions[execution_id] = datetime.now()
            
            await self.checkpoint_manager.create_checkpoint(
                execution_id=execution_id,
                checkpoint_type=CheckpointType.MANUAL,
                state=snapshot.dict(),
                message="用户暂停"
            )
            
            logger.info(f"[AgentHarness] 已暂停: {execution_id[:8]}")
    
    async def resume_execution(self, execution_id: str):
        """恢复执行"""
        if execution_id in self._paused_executions:
            del self._paused_executions[execution_id]
            
            snapshot = self._executions.get(execution_id)
            if snapshot:
                snapshot.status = ExecutionState.RUNNING
                snapshot.updated_at = datetime.now()
                await self._save_snapshot(snapshot)
            
            logger.info(f"[AgentHarness] 已恢复: {execution_id[:8]}")
    
    async def cancel_execution(self, execution_id: str):
        """取消执行"""
        snapshot = self._executions.get(execution_id)
        if snapshot:
            snapshot.status = ExecutionState.CANCELLED
            snapshot.updated_at = datetime.now()
            await self._save_snapshot(snapshot)
            
            self._paused_executions.pop(execution_id, None)
            
            logger.info(f"[AgentHarness] 已取消: {execution_id[:8]}")
    
    async def restore_from_checkpoint(self, checkpoint_id: str) -> Optional[str]:
        """从检查点恢复"""
        restored = await self.checkpoint_manager.restore_checkpoint(checkpoint_id)
        
        if not restored:
            return None
        
        snapshot_data = restored["state"]
        snapshot = ExecutionSnapshot(**snapshot_data)
        snapshot.status = ExecutionState.RUNNING
        snapshot.current_step = restored["step_index"]
        
        execution_id = snapshot.execution_id
        self._executions[execution_id] = snapshot
        
        await self._save_snapshot(snapshot)
        
        logger.info(
            f"[AgentHarness] 从检查点恢复: {checkpoint_id[:8]} -> "
            f"执行 {execution_id[:8]} 步骤 {snapshot.current_step}"
        )
        
        return execution_id
    
    async def _wait_for_resume(self, execution_id: str):
        """等待恢复"""
        while execution_id in self._paused_executions:
            await asyncio.sleep(1)
    
    async def _save_snapshot(self, snapshot: ExecutionSnapshot):
        """保存快照"""
        compressed = await self.state_compressor.compress(snapshot)
        await self.store.save(
            f"execution_{snapshot.execution_id}",
            compressed.dict()
        )
    
    async def _load_snapshot(self, execution_id: str) -> Optional[ExecutionSnapshot]:
        """加载快照"""
        data = await self.store.load(f"execution_{execution_id}")
        if data:
            return ExecutionSnapshot(**data)
        return None
    
    def get_execution(self, execution_id: str) -> Optional[ExecutionSnapshot]:
        """获取执行状态"""
        return self._executions.get(execution_id)
    
    async def list_executions(self) -> List[Dict[str, Any]]:
        """列出所有执行"""
        keys = await self.store.list_keys("execution_")
        
        executions = []
        for key in keys:
            data = await self.store.load(key)
            if data:
                executions.append({
                    "execution_id": data.get("execution_id"),
                    "status": data.get("status"),
                    "agent_name": data.get("agent_name"),
                    "current_step": data.get("current_step"),
                    "created_at": data.get("created_at"),
                })
        
        return executions
    
    async def prepare_skill(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
    ) -> bool:
        """
        准备Skill执行上下文
        
        加载Skill和所需工具到上下文中
        """
        if not self._context_lifecycle:
            logger.warning("[AgentHarness] Context lifecycle not configured")
            return False
        
        try:
            await self._context_lifecycle.prepare_skill_context(
                skill_name=skill_name,
                skill_content=skill_content,
                required_tools=required_tools,
            )
            
            self._current_skill = skill_name
            
            logger.info(f"[AgentHarness] Prepared skill: {skill_name}")
            return True
            
        except Exception as e:
            logger.error(f"[AgentHarness] Failed to prepare skill {skill_name}: {e}")
            return False
    
    async def complete_skill(
        self,
        skill_name: Optional[str] = None,
        summary: str = "",
        key_outputs: Optional[List[str]] = None,
    ) -> Optional["SkillExitResult"]:
        """
        完成Skill执行并退出上下文
        
        清除Skill详细内容，只保留摘要
        """
        if not self._context_lifecycle:
            return None
        
        target_skill = skill_name or self._current_skill
        if not target_skill:
            return None
        
        try:
            result = await self._context_lifecycle.complete_skill(
                skill_name=target_skill,
                task_summary=summary,
                key_outputs=key_outputs,
            )
            
            if target_skill == self._current_skill:
                self._current_skill = None
            
            logger.info(
                f"[AgentHarness] Completed skill: {target_skill}, "
                f"tokens freed: {result.tokens_freed}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[AgentHarness] Failed to complete skill {target_skill}: {e}")
            return None
    
    async def activate_skill(self, skill_name: str) -> bool:
        """激活休眠的Skill"""
        if not self._context_lifecycle:
            return False
        
        slot = await self._context_lifecycle.activate_skill(skill_name)
        if slot:
            self._current_skill = skill_name
            logger.info(f"[AgentHarness] Reactivated skill: {skill_name}")
            return True
        return False
    
    async def ensure_tools_loaded(
        self,
        tool_names: List[str],
    ) -> Dict[str, bool]:
        """确保工具已加载"""
        if not self._context_lifecycle:
            return {name: False for name in tool_names}
        
        return await self._context_lifecycle.ensure_tools_loaded(tool_names)
    
    async def unload_tools(
        self,
        tool_names: List[str],
    ) -> List[str]:
        """卸载工具"""
        if not self._context_lifecycle:
            return []
        
        return await self._context_lifecycle.unload_tools(tool_names)
    
    async def check_context_pressure(self) -> Optional[Dict[str, Any]]:
        """
        检查上下文压力
        
        如果压力过高会自动处理
        """
        if not self._context_lifecycle:
            return None
        
        pressure = self._context_lifecycle.check_context_pressure()
        
        if pressure > 0.8:
            result = await self._context_lifecycle.handle_context_pressure()
            logger.warning(
                f"[AgentHarness] Context pressure {pressure:.2%}, "
                f"actions: {result['actions_taken']}"
            )
            return result
        
        return {"pressure_level": pressure, "actions_taken": []}
    
    def get_context_report(self) -> Optional[Dict[str, Any]]:
        """获取上下文报告"""
        if not self._context_lifecycle:
            return None
        
        return self._context_lifecycle.get_context_report()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "active_executions": len(self._executions),
            "paused_executions": len(self._paused_executions),
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "task_queue": self.task_queue.get_stats(),
            "checkpoints": len(self.checkpoint_manager._checkpoints),
        }
        
        if self._context_lifecycle:
            report = self._context_lifecycle.get_context_report()
            stats["context_lifecycle"] = {
                "slot_stats": report.get("slot_stats", {}),
                "skill_stats": report.get("skill_stats", {}),
                "tool_stats": report.get("tool_stats", {}),
            }
        
        return stats


agent_harness = AgentHarness