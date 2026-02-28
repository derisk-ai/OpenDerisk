"""
Multi-Agent Orchestrator - 多Agent编排器

实现多Agent协作的核心编排逻辑：
1. 任务规划 - 调用TaskPlanner生成执行计划
2. Agent路由 - 调用AgentRouter分配任务
3. 执行调度 - 管理Agent团队的执行
4. 结果合并 - 整合各Agent的执行结果

@see ARCHITECTURE.md#12.2-multiagentorchestrator-编排器
"""

from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime
from enum import Enum
import asyncio
import logging
import uuid

from pydantic import BaseModel, Field

from .shared_context import SharedContext, Artifact
from .planner import (
    TaskPlanner,
    ExecutionPlan,
    DecomposedTask,
    TaskStatus,
    DecompositionStrategy,
    TaskPriority,
)

logger = logging.getLogger(__name__)


class ExecutionStrategy(str, Enum):
    """执行策略"""
    SEQUENTIAL = "sequential"          # 顺序执行
    PARALLEL = "parallel"              # 并行执行
    HIERARCHICAL = "hierarchical"      # 层次执行
    ADAPTIVE = "adaptive"              # 自适应执行


class TaskResult(BaseModel):
    """任务执行结果"""
    task_id: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    execution_time_ms: Optional[float] = None
    agent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    """执行结果"""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:12])
    plan_id: str
    goal: str
    
    success: bool = False
    task_results: List[TaskResult] = Field(default_factory=list)
    
    final_output: Optional[str] = None
    artifacts: Dict[str, Artifact] = Field(default_factory=dict)
    
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    
    total_time_ms: Optional[float] = None
    
    statistics: Dict[str, Any] = Field(default_factory=dict)
    
    def add_result(self, result: TaskResult) -> None:
        """添加任务结果"""
        self.task_results.append(result)
        if result.success:
            self.completed_tasks += 1
        else:
            self.failed_tasks += 1
        
        if result.artifacts:
            for name, content in result.artifacts.items():
                self.artifacts[f"{result.task_id}:{name}"] = Artifact(
                    name=name,
                    content=content,
                    produced_by=result.task_id,
                )
    
    def get_summary(self) -> str:
        """获取执行摘要"""
        status = "成功" if self.success else "失败"
        return (
            f"执行{status} - "
            f"完成: {self.completed_tasks}/{self.total_tasks}, "
            f"失败: {self.failed_tasks}, "
            f"耗时: {self.total_time_ms:.1f}ms" if self.total_time_ms else ""
        )


class SubTask(BaseModel):
    """子任务（向后兼容别名）"""
    task_id: str
    description: str
    assigned_agent: Optional[str] = None
    required_resources: List[str] = Field(default_factory=list)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """任务计划（向后兼容别名）"""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:8])
    goal: str
    sub_tasks: List[SubTask] = Field(default_factory=list)
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    execution_strategy: ExecutionStrategy = ExecutionStrategy.ADAPTIVE


class AgentFactory:
    """Agent工厂接口"""
    
    async def create_agent(
        self,
        agent_type: str,
        config: Optional[Dict[str, Any]] = None,
        shared_context: Optional[SharedContext] = None,
    ) -> Any:
        """创建Agent实例"""
        raise NotImplementedError


class ResultMerger:
    """结果合并器"""
    
    async def merge(
        self,
        execution_result: ExecutionResult,
        context: SharedContext,
    ) -> ExecutionResult:
        """合并执行结果"""
        
        all_outputs = []
        for task_result in execution_result.task_results:
            if task_result.success and task_result.output:
                all_outputs.append(f"## {task_result.task_id}\n{task_result.output}")
        
        if all_outputs:
            execution_result.final_output = "\n\n".join(all_outputs)
        
        total = len(execution_result.task_results)
        success = sum(1 for r in execution_result.task_results if r.success)
        
        execution_result.success = success == total
        execution_result.completed_at = datetime.now()
        
        if execution_result.started_at:
            execution_result.total_time_ms = (
                execution_result.completed_at - execution_result.started_at
            ).total_seconds() * 1000
        
        execution_result.statistics = {
            "total_tasks": total,
            "successful_tasks": success,
            "failed_tasks": total - success,
            "artifacts_count": len(execution_result.artifacts),
        }
        
        return execution_result


class MultiAgentOrchestrator:
    """
    多Agent编排器
    
    核心职责：
    1. 接收目标，调用TaskPlanner生成执行计划
    2. 根据计划调度Agent执行任务
    3. 管理SharedContext实现Agent间协作
    4. 合并结果并返回
    
    @example
    ```python
    orchestrator = MultiAgentOrchestrator(
        agent_factory=MyAgentFactory(),
        llm_client=llm_client,
    )
    
    result = await orchestrator.execute(
        goal="开发用户登录模块",
        team_capabilities={"analysis", "coding", "testing"},
        available_agents={
            "analyst": ["analysis"],
            "coder": ["coding"],
            "tester": ["testing"],
        },
        execution_strategy=ExecutionStrategy.HIERARCHICAL,
    )
    
    print(result.get_summary())
    ```
    """
    
    def __init__(
        self,
        agent_factory: Optional[AgentFactory] = None,
        llm_client: Optional[Any] = None,
        max_parallel_agents: int = 3,
        on_task_start: Optional[Callable[[DecomposedTask], Awaitable[None]]] = None,
        on_task_complete: Optional[Callable[[TaskResult], Awaitable[None]]] = None,
    ):
        self._agent_factory = agent_factory
        self._llm_client = llm_client
        self._max_parallel = max_parallel_agents
        self._on_task_start = on_task_start
        self._on_task_complete = on_task_complete
        
        self._task_planner = TaskPlanner(llm_client=llm_client)
        self._result_merger = ResultMerger()
        
        self._active_agents: Dict[str, Any] = {}
    
    async def execute(
        self,
        goal: str,
        team_capabilities: Optional[set] = None,
        available_agents: Optional[Dict[str, List[str]]] = None,
        context: Optional[SharedContext] = None,
        execution_strategy: ExecutionStrategy = ExecutionStrategy.ADAPTIVE,
        max_parallel: Optional[int] = None,
    ) -> ExecutionResult:
        """
        执行多Agent任务
        
        Args:
            goal: 目标描述
            team_capabilities: 团队能力集合
            available_agents: 可用Agent {agent_type: [capabilities]}
            context: 共享上下文（可选，会自动创建）
            execution_strategy: 执行策略
            max_parallel: 最大并行数
        
        Returns:
            ExecutionResult: 执行结果
        """
        start_time = datetime.now()
        
        if context is None:
            context = SharedContext(session_id=str(uuid.uuid4().hex)[:8])
        
        plan = await self._task_planner.plan(
            goal=goal,
            team_capabilities=team_capabilities or set(),
            available_agents=available_agents or {},
            strategy=self._map_strategy(execution_strategy),
        )
        
        execution_result = ExecutionResult(
            plan_id=plan.plan_id,
            goal=goal,
            total_tasks=len(plan.tasks),
        )
        
        logger.info(f"[Orchestrator] Starting execution: {plan.plan_id}, tasks: {len(plan.tasks)}")
        
        try:
            if execution_strategy == ExecutionStrategy.PARALLEL:
                results = await self._execute_parallel(plan, context, available_agents or {})
            elif execution_strategy == ExecutionStrategy.HIERARCHICAL:
                results = await self._execute_hierarchical(plan, context, available_agents or {})
            else:
                results = await self._execute_sequential(plan, context, available_agents or {})
            
            for result in results:
                execution_result.add_result(result)
            
            execution_result = await self._result_merger.merge(execution_result, context)
            
        except Exception as e:
            logger.error(f"[Orchestrator] Execution failed: {e}")
            execution_result.success = False
            execution_result.final_output = f"执行失败: {str(e)}"
            execution_result.completed_at = datetime.now()
        
        finally:
            await self._cleanup_agents()
        
        logger.info(f"[Orchestrator] Execution completed: {execution_result.get_summary()}")
        return execution_result
    
    async def _execute_sequential(
        self,
        plan: ExecutionPlan,
        context: SharedContext,
        available_agents: Dict[str, List[str]],
    ) -> List[TaskResult]:
        """顺序执行"""
        results = []
        
        for task in plan.tasks:
            result = await self._execute_task(task, context, available_agents)
            results.append(result)
            
            self._task_planner.update_task_status(
                plan, task.id,
                TaskStatus.COMPLETED if result.success else TaskStatus.FAILED,
                result.output,
                result.error,
            )
            
            if not result.success and task.priority == TaskPriority.CRITICAL:
                logger.error(f"[Orchestrator] Critical task {task.id} failed, stopping")
                break
        
        return results
    
    async def _execute_parallel(
        self,
        plan: ExecutionPlan,
        context: SharedContext,
        available_agents: Dict[str, List[str]],
    ) -> List[TaskResult]:
        """并行执行"""
        results = []
        semaphore = asyncio.Semaphore(self._max_parallel)
        
        async def execute_with_limit(task: DecomposedTask) -> TaskResult:
            async with semaphore:
                return await self._execute_task(task, context, available_agents)
        
        tasks = plan.get_ready_tasks()
        while tasks:
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
                
                status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                self._task_planner.update_task_status(plan, task.id, status)
            
            tasks = plan.get_ready_tasks()
            
            if any(not r.success for r in results):
                critical_failed = any(
                    not r.success and plan.get_task(r.task_id) and 
                    plan.get_task(r.task_id).priority == TaskPriority.CRITICAL
                    for r in results
                )
                if critical_failed:
                    break
        
        return results
    
    async def _execute_hierarchical(
        self,
        plan: ExecutionPlan,
        context: SharedContext,
        available_agents: Dict[str, List[str]],
    ) -> List[TaskResult]:
        """层次执行"""
        results = []
        layers = plan.get_execution_layers()
        
        for layer_idx, layer_tasks in enumerate(layers):
            logger.info(f"[Orchestrator] Executing layer {layer_idx} with {len(layer_tasks)} tasks")
            
            semaphore = asyncio.Semaphore(self._max_parallel)
            
            async def execute_with_limit(task: DecomposedTask) -> TaskResult:
                async with semaphore:
                    return await self._execute_task(task, context, available_agents)
            
            layer_results = await asyncio.gather(
                *[execute_with_limit(t) for t in layer_tasks],
                return_exceptions=True,
            )
            
            for task, result in zip(layer_tasks, layer_results):
                if isinstance(result, Exception):
                    result = TaskResult(
                        task_id=task.id,
                        success=False,
                        error=str(result),
                    )
                results.append(result)
                
                status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                self._task_planner.update_task_status(plan, task.id, status)
            
            if any(not r.success for r in layer_results if not isinstance(r, Exception)):
                logger.warning(f"[Orchestrator] Layer {layer_idx} had failures, checking if should continue")
        
        return results
    
    async def _execute_task(
        self,
        task: DecomposedTask,
        context: SharedContext,
        available_agents: Dict[str, List[str]],
    ) -> TaskResult:
        """执行单个任务"""
        start_time = datetime.now()
        
        if self._on_task_start:
            await self._on_task_start(task)
        
        try:
            agent_type = task.assigned_agent or self._select_agent_type(task, available_agents)
            
            if not agent_type:
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error="No suitable agent available",
                )
            
            if not self._agent_factory:
                output = await self._mock_execute(task, context)
                success = True
            else:
                agent = await self._agent_factory.create_agent(
                    agent_type=agent_type,
                    shared_context=context,
                )
                self._active_agents[task.id] = agent
                
                artifacts = context.get_artifacts_by_task(task.id)
                context_data = {
                    "task": task.description,
                    "artifacts": {a.name: a.content for a in artifacts},
                }
                
                result = await agent.run(task.description, context_data)
                output = result.content if hasattr(result, 'content') else str(result)
                success = True
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = TaskResult(
                task_id=task.id,
                success=success,
                output=output,
                execution_time_ms=execution_time,
                agent_id=agent_type,
            )
            
            if success:
                await context.update(
                    task_id=task.id,
                    result=output,
                    artifacts={"output": output},
                )
            
        except Exception as e:
            logger.error(f"[Orchestrator] Task {task.id} failed: {e}")
            result = TaskResult(
                task_id=task.id,
                success=False,
                error=str(e),
            )
        
        if self._on_task_complete:
            await self._on_task_complete(result)
        
        return result
    
    def _select_agent_type(
        self,
        task: DecomposedTask,
        available_agents: Dict[str, List[str]],
    ) -> Optional[str]:
        """选择Agent类型"""
        required_caps = set(task.required_capabilities)
        
        for agent_type, capabilities in available_agents.items():
            if required_caps.issubset(set(capabilities)):
                return agent_type
        
        if available_agents:
            return next(iter(available_agents.keys()))
        
        return None
    
    async def _mock_execute(
        self,
        task: DecomposedTask,
        context: SharedContext,
    ) -> str:
        """模拟执行（无Agent工厂时）"""
        await asyncio.sleep(0.1)
        return f"[Mock] Task '{task.name}' completed. Description: {task.description}"
    
    def _map_strategy(self, strategy: ExecutionStrategy) -> DecompositionStrategy:
        """映射执行策略到分解策略"""
        mapping = {
            ExecutionStrategy.SEQUENTIAL: DecompositionStrategy.SEQUENTIAL,
            ExecutionStrategy.PARALLEL: DecompositionStrategy.PARALLEL,
            ExecutionStrategy.HIERARCHICAL: DecompositionStrategy.HIERARCHICAL,
            ExecutionStrategy.ADAPTIVE: DecompositionStrategy.ADAPTIVE,
        }
        return mapping.get(strategy, DecompositionStrategy.ADAPTIVE)
    
    async def _cleanup_agents(self) -> None:
        """清理Agent"""
        for task_id, agent in list(self._active_agents.items()):
            try:
                if hasattr(agent, 'cleanup'):
                    await agent.cleanup()
            except Exception as e:
                logger.warning(f"[Orchestrator] Failed to cleanup agent for {task_id}: {e}")
        
        self._active_agents.clear()