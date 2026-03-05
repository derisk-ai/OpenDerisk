"""
Agent Team - Agent团队管理

实现Agent团队的创建、管理和执行：
1. Worker管理 - 管理团队中的工作者Agent
2. 任务分配 - 将任务分配给合适的Agent
3. 并行执行 - 支持多Agent并行工作
4. 状态同步 - 维护Agent状态一致性

@see ARCHITECTURE.md#12.5-agentteam-团队管理
"""

from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime
from enum import Enum
import asyncio
import logging
import uuid

from pydantic import BaseModel, Field

from .shared_context import SharedContext, ResourceBinding
from .planner import DecomposedTask, TaskStatus, TaskPriority
from .orchestrator import TaskResult

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Agent角色"""
    COORDINATOR = "coordinator"    # 协调者
    WORKER = "worker"              # 工作者
    SPECIALIST = "specialist"      # 专家
    REVIEWER = "reviewer"          # 审核者
    SUPERVISOR = "supervisor"      # 监督者


class AgentStatus(str, Enum):
    """Agent状态"""
    IDLE = "idle"                  # 空闲
    BUSY = "busy"                  # 忙碌
    ERROR = "error"                # 错误
    OFFLINE = "offline"            # 离线


class AgentCapability(BaseModel):
    """Agent能力描述"""
    name: str
    description: str = ""
    proficiency: float = 0.8       # 熟练度 0-1
    categories: List[str] = Field(default_factory=list)


class WorkerAgent(BaseModel):
    """工作者Agent"""
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:8])
    agent_type: str
    agent: Optional[Any] = None    # 实际Agent实例
    role: AgentRole = AgentRole.WORKER
    
    capabilities: List[AgentCapability] = Field(default_factory=list)
    current_task: Optional[str] = None
    status: AgentStatus = AgentStatus.IDLE
    
    max_concurrent_tasks: int = 1
    completed_tasks: int = 0
    failed_tasks: int = 0
    
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: Optional[datetime] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    def can_handle(self, required_capabilities: List[str]) -> bool:
        """检查是否能处理指定能力"""
        if not self.capabilities:
            return True
        
        available = {c.name for c in self.capabilities}
        return all(cap in available for cap in required_capabilities)
    
    def get_proficiency(self, capability: str) -> float:
        """获取特定能力的熟练度"""
        for cap in self.capabilities:
            if cap.name == capability:
                return cap.proficiency
        return 0.0
    
    def mark_busy(self, task_id: str) -> None:
        """标记为忙碌"""
        self.status = AgentStatus.BUSY
        self.current_task = task_id
        self.last_active = datetime.now()
    
    def mark_idle(self) -> None:
        """标记为空闲"""
        self.status = AgentStatus.IDLE
        self.current_task = None
        self.last_active = datetime.now()
    
    def mark_error(self, error: Optional[str] = None) -> None:
        """标记为错误"""
        self.status = AgentStatus.ERROR
        self.current_task = None
        self.last_active = datetime.now()


class TeamConfig(BaseModel):
    """团队配置"""
    team_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:8])
    team_name: str
    app_code: Optional[str] = None
    
    coordinator_type: Optional[str] = None
    worker_types: List[str] = Field(default_factory=list)
    
    max_parallel_workers: int = 3
    task_timeout: int = 600
    
    shared_resources: List[ResourceBinding] = Field(default_factory=list)
    
    execution_strategy: str = "adaptive"
    
    retry_policy: Dict[str, Any] = Field(default_factory=lambda: {
        "max_retries": 2,
        "retry_delay": 1.0,
        "backoff_factor": 2.0,
    })


class TaskAssignment(BaseModel):
    """任务分配"""
    task_id: str
    agent_id: str
    assigned_at: datetime = Field(default_factory=datetime.now)
    priority: TaskPriority = TaskPriority.MEDIUM
    estimated_time_ms: Optional[float] = None


class AgentTeam:
    """
    Agent团队
    
    管理一组协作Agent的执行。
    
    @example
    ```python
    config = TeamConfig(
        team_name="DevTeam",
        worker_types=["analyst", "coder", "tester"],
        max_parallel_workers=3,
    )
    
    team = AgentTeam(config=config, shared_context=context)
    await team.initialize()
    
    # 执行任务
    results = await team.execute_parallel(tasks)
    
    # 获取统计
    stats = team.get_statistics()
    ```
    """
    
    def __init__(
        self,
        config: TeamConfig,
        shared_context: SharedContext,
        agent_factory: Optional[Callable] = None,
        on_task_assign: Optional[Callable[[TaskAssignment], Awaitable[None]]] = None,
        on_task_complete: Optional[Callable[[TaskResult], Awaitable[None]]] = None,
    ):
        self._config = config
        self._shared_context = shared_context
        self._agent_factory = agent_factory
        self._on_task_assign = on_task_assign
        self._on_task_complete = on_task_complete
        
        self._workers: Dict[str, WorkerAgent] = {}
        self._coordinator: Optional[WorkerAgent] = None
        self._assignments: Dict[str, TaskAssignment] = {}
        
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """初始化团队"""
        if self._initialized:
            return
        
        if self._config.coordinator_type:
            self._coordinator = WorkerAgent(
                agent_type=self._config.coordinator_type,
                role=AgentRole.COORDINATOR,
            )
            self._workers[self._coordinator.agent_id] = self._coordinator
        
        for worker_type in self._config.worker_types:
            worker = WorkerAgent(
                agent_type=worker_type,
                role=AgentRole.WORKER,
            )
            self._workers[worker.agent_id] = worker
        
        self._initialized = True
        logger.info(f"[AgentTeam] Team '{self._config.team_name}' initialized with {len(self._workers)} workers")
    
    async def execute_parallel(
        self,
        tasks: List[DecomposedTask],
        max_concurrent: Optional[int] = None,
    ) -> List[TaskResult]:
        """并行执行任务"""
        if not self._initialized:
            await self.initialize()
        
        max_concurrent = max_concurrent or self._config.max_parallel_workers
        semaphore = asyncio.Semaphore(max_concurrent)
        
        results = []
        
        async def execute_with_limit(task: DecomposedTask) -> TaskResult:
            async with semaphore:
                return await self._execute_task(task)
        
        batch_results = await asyncio.gather(
            *[execute_with_limit(t) for t in tasks],
            return_exceptions=True,
        )
        
        for task, result in zip(tasks, batch_results):
            if isinstance(result, Exception):
                result = TaskResult(
                    task_id=task.id,
                    success=False,
                    error=str(result),
                )
            results.append(result)
        
        return results
    
    async def execute_sequential(
        self,
        tasks: List[DecomposedTask],
    ) -> List[TaskResult]:
        """顺序执行任务"""
        if not self._initialized:
            await self.initialize()
        
        results = []
        
        for task in tasks:
            result = await self._execute_task(task)
            results.append(result)
            
            if not result.success:
                if task.priority == TaskPriority.CRITICAL:
                    logger.error(f"[AgentTeam] Critical task {task.id} failed, stopping")
                    break
        
        return results
    
    async def _execute_task(
        self,
        task: DecomposedTask,
    ) -> TaskResult:
        """执行单个任务"""
        start_time = datetime.now()
        
        worker = await self._select_worker(task)
        if not worker:
            return TaskResult(
                task_id=task.id,
                success=False,
                error="No suitable worker available",
            )
        
        assignment = TaskAssignment(
            task_id=task.id,
            agent_id=worker.agent_id,
            priority=task.priority,
        )
        self._assignments[task.id] = assignment
        
        if self._on_task_assign:
            await self._on_task_assign(assignment)
        
        worker.mark_busy(task.id)
        
        try:
            result = await self._do_work(task, worker)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            result.execution_time_ms = execution_time
            result.agent_id = worker.agent_id
            
            worker.completed_tasks += 1
            worker.mark_idle()
            
        except Exception as e:
            logger.error(f"[AgentTeam] Task {task.id} failed on worker {worker.agent_id}: {e}")
            result = TaskResult(
                task_id=task.id,
                success=False,
                error=str(e),
                agent_id=worker.agent_id,
            )
            worker.failed_tasks += 1
            worker.mark_error(str(e))
        
        if self._on_task_complete:
            await self._on_task_complete(result)
        
        return result
    
    async def _select_worker(
        self,
        task: DecomposedTask,
    ) -> Optional[WorkerAgent]:
        """选择合适的Worker"""
        available = [
            w for w in self._workers.values()
            if w.status == AgentStatus.IDLE and w.role == AgentRole.WORKER
        ]
        
        if not available:
            available = [w for w in self._workers.values() if w.status == AgentStatus.IDLE]
        
        if not available:
            return None
        
        if task.required_capabilities:
            capable = [
                w for w in available
                if w.can_handle(task.required_capabilities)
            ]
            if capable:
                return max(capable, key=lambda w: min(
                    w.get_proficiency(cap) for cap in task.required_capabilities
                ))
        
        min_tasks = min(w.completed_tasks + w.failed_tasks for w in available)
        least_busy = [w for w in available if w.completed_tasks + w.failed_tasks == min_tasks]
        
        return least_busy[0] if least_busy else available[0]
    
    async def _do_work(
        self,
        task: DecomposedTask,
        worker: WorkerAgent,
    ) -> TaskResult:
        """执行工作"""
        artifacts = self._shared_context.get_artifacts_by_task(task.id)
        
        context_data = {
            "task_id": task.id,
            "task": task.description,
            "goal": task.goal if hasattr(task, 'goal') else task.description,
            "artifacts": {a.name: a.content for a in artifacts},
            "required_resources": task.required_resources,
        }
        
        if worker.agent and hasattr(worker.agent, 'run'):
            result = await worker.agent.run(task.description, context_data)
            output = result.content if hasattr(result, 'content') else str(result)
        else:
            output = await self._mock_work(task)
        
        await self._shared_context.update(
            task_id=task.id,
            result=output,
            artifacts={"output": output},
        )
        
        return TaskResult(
            task_id=task.id,
            success=True,
            output=output,
        )
    
    async def _mock_work(self, task: DecomposedTask) -> str:
        """模拟工作"""
        await asyncio.sleep(0.1)
        return f"[Mock] Task '{task.name}' completed by worker"
    
    def get_worker(self, agent_id: str) -> Optional[WorkerAgent]:
        """获取Worker"""
        return self._workers.get(agent_id)
    
    def get_idle_workers(self) -> List[WorkerAgent]:
        """获取空闲Worker"""
        return [w for w in self._workers.values() if w.status == AgentStatus.IDLE]
    
    def get_busy_workers(self) -> List[WorkerAgent]:
        """获取忙碌Worker"""
        return [w for w in self._workers.values() if w.status == AgentStatus.BUSY]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        workers = list(self._workers.values())
        
        return {
            "team_id": self._config.team_id,
            "team_name": self._config.team_name,
            "total_workers": len(workers),
            "idle_workers": len([w for w in workers if w.status == AgentStatus.IDLE]),
            "busy_workers": len([w for w in workers if w.status == AgentStatus.BUSY]),
            "error_workers": len([w for w in workers if w.status == AgentStatus.ERROR]),
            "total_completed_tasks": sum(w.completed_tasks for w in workers),
            "total_failed_tasks": sum(w.failed_tasks for w in workers),
            "active_assignments": len(self._assignments),
        }
    
    async def shutdown(self) -> None:
        """关闭团队"""
        for worker in self._workers.values():
            if worker.agent and hasattr(worker.agent, 'cleanup'):
                try:
                    await worker.agent.cleanup()
                except Exception as e:
                    logger.warning(f"[AgentTeam] Failed to cleanup worker: {e}")
            
            worker.status = AgentStatus.OFFLINE
        
        self._workers.clear()
        self._assignments.clear()
        
        logger.info(f"[AgentTeam] Team '{self._config.team_name}' shutdown")