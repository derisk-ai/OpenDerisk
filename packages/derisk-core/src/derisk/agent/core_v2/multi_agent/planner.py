"""
Task Planner - 任务规划器

实现任务的分解、依赖分析和执行计划生成：
1. 目标分解 - 将复杂目标分解为子任务
2. 依赖分析 - 分析任务间依赖关系
3. 优先级排序 - 基于依赖关系确定执行顺序
4. 策略选择 - 选择合适的执行策略

@see ARCHITECTURE.md#12.3-taskplanner-任务规划器
"""

from typing import Any, Callable, Dict, List, Optional, Set, Awaitable
from datetime import datetime
from enum import Enum
import json
import logging
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DecompositionStrategy(str, Enum):
    """任务分解策略"""
    SEQUENTIAL = "sequential"          # 顺序分解
    PARALLEL = "parallel"              # 并行分解
    HIERARCHICAL = "hierarchical"      # 层次分解
    ADAPTIVE = "adaptive"              # 自适应分解


class TaskPriority(str, Enum):
    """任务优先级"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    READY = "ready"           # 依赖已满足
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskDependency(BaseModel):
    """任务依赖关系"""
    task_id: str
    depends_on: List[str] = Field(default_factory=list)  # 依赖的任务ID
    dependency_type: str = "hard"  # hard, soft
    condition: Optional[str] = None  # 可选的条件表达式


class TaskDefinition(BaseModel):
    """任务定义"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:8])
    name: str
    description: str
    goal: str
    
    required_capabilities: List[str] = Field(default_factory=list)  # 所需能力
    required_resources: List[str] = Field(default_factory=list)     # 所需资源类型
    estimated_steps: int = 3
    timeout: int = 600
    
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: TaskDependency = Field(default_factory=lambda: TaskDependency(task_id=""))
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DecomposedTask(BaseModel):
    """分解后的任务"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:8])
    name: str
    description: str
    parent_task_id: Optional[str] = None
    level: int = 0                            # 层次深度
    
    assigned_agent: Optional[str] = None      # 分配的Agent类型
    assigned_agent_id: Optional[str] = None   # 分配的Agent实例ID
    
    required_capabilities: List[str] = Field(default_factory=list)
    required_resources: List[str] = Field(default_factory=list)
    
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    
    dependencies: List[str] = Field(default_factory=list)
    dependents: List[str] = Field(default_factory=list)  # 依赖此任务的任务
    
    result: Optional[str] = None
    error: Optional[str] = None
    
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def is_ready(self, completed_tasks: Set[str]) -> bool:
        """检查任务是否就绪"""
        if self.status != TaskStatus.PENDING:
            return False
        return all(dep in completed_tasks for dep in self.dependencies)


class ExecutionPlan(BaseModel):
    """执行计划"""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:8])
    goal: str
    
    tasks: List[DecomposedTask] = Field(default_factory=list)
    task_index: Dict[str, DecomposedTask] = Field(default_factory=dict)
    
    execution_strategy: DecompositionStrategy = DecompositionStrategy.ADAPTIVE
    max_parallelism: int = 3
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    def add_task(self, task: DecomposedTask) -> None:
        """添加任务"""
        self.tasks.append(task)
        self.task_index[task.id] = task
    
    def get_task(self, task_id: str) -> Optional[DecomposedTask]:
        """获取任务"""
        return self.task_index.get(task_id)
    
    def get_ready_tasks(self) -> List[DecomposedTask]:
        """获取就绪任务"""
        completed = self._get_completed_task_ids()
        ready = []
        
        for task in self.tasks:
            if task.is_ready(completed):
                ready.append(task)
        
        return sorted(ready, key=lambda t: (t.level, -self._priority_value(t.priority)))
    
    def get_pending_tasks(self) -> List[DecomposedTask]:
        """获取待执行任务"""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]
    
    def get_running_tasks(self) -> List[DecomposedTask]:
        """获取执行中任务"""
        return [t for t in self.tasks if t.status == TaskStatus.RUNNING]
    
    def get_execution_layers(self) -> List[List[DecomposedTask]]:
        """按执行层次分组任务"""
        layers: Dict[int, List[DecomposedTask]] = {}
        
        for task in self.tasks:
            layer_idx = self._compute_layer(task)
            if layer_idx not in layers:
                layers[layer_idx] = []
            layers[layer_idx].append(task)
        
        return [layers[i] for i in sorted(layers.keys())]
    
    def _get_completed_task_ids(self) -> Set[str]:
        """获取已完成任务ID集合"""
        return {t.id for t in self.tasks if t.status == TaskStatus.COMPLETED}
    
    def _compute_layer(self, task: DecomposedTask) -> int:
        """计算任务执行层次"""
        if not task.dependencies:
            return 0
        
        max_dep_layer = 0
        for dep_id in task.dependencies:
            dep_task = self.get_task(dep_id)
            if dep_task:
                max_dep_layer = max(max_dep_layer, self._compute_layer(dep_task) + 1)
        
        return max_dep_layer
    
    def _priority_value(self, priority: TaskPriority) -> int:
        """优先级数值"""
        values = {
            TaskPriority.CRITICAL: 4,
            TaskPriority.HIGH: 3,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 1,
        }
        return values.get(priority, 2)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        status_count = {}
        for status in TaskStatus:
            status_count[status.value] = len([t for t in self.tasks if t.status == status])
        
        return {
            "plan_id": self.plan_id,
            "total_tasks": len(self.tasks),
            "status_distribution": status_count,
            "execution_layers": len(self.get_execution_layers()),
        }


class TaskPlanner:
    """
    任务规划器
    
    负责任务的分解、依赖分析和执行计划生成。
    
    @example
    ```python
    planner = TaskPlanner(llm_client=client)
    
    # 规划任务
    plan = await planner.plan(
        goal="开发用户登录模块",
        team_capabilities={"analysis", "coding", "testing"},
        context={"language": "python"}
    )
    
    # 获取可执行任务
    ready_tasks = plan.get_ready_tasks()
    
    # 获取执行层次
    layers = plan.get_execution_layers()
    ```
    """
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        on_task_created: Optional[Callable[[DecomposedTask], Awaitable[None]]] = None,
    ):
        self._llm_client = llm_client
        self._on_task_created = on_task_created
    
    async def plan(
        self,
        goal: str,
        team_capabilities: Optional[Set[str]] = None,
        available_agents: Optional[Dict[str, List[str]]] = None,
        context: Optional[Dict[str, Any]] = None,
        strategy: DecompositionStrategy = DecompositionStrategy.ADAPTIVE,
        max_depth: int = 3,
    ) -> ExecutionPlan:
        """
        生成执行计划
        
        Args:
            goal: 目标描述
            team_capabilities: 团队能力集合
            available_agents: 可用Agent映射 {agent_type: [capability]}
            context: 执行上下文
            strategy: 分解策略
            max_depth: 最大分解深度
        
        Returns:
            ExecutionPlan: 执行计划
        """
        plan = ExecutionPlan(goal=goal, execution_strategy=strategy)
        
        if self._llm_client:
            tasks = await self._decompose_with_llm(
                goal=goal,
                team_capabilities=team_capabilities or set(),
                available_agents=available_agents or {},
                context=context or {},
                strategy=strategy,
                max_depth=max_depth,
            )
        else:
            tasks = self._decompose_rule_based(
                goal=goal,
                team_capabilities=team_capabilities or set(),
                strategy=strategy,
            )
        
        for task in tasks:
            plan.add_task(task)
            if self._on_task_created:
                await self._on_task_created(task)
        
        self._resolve_dependencies(plan)
        
        logger.info(f"[TaskPlanner] Created plan {plan.plan_id} with {len(tasks)} tasks")
        return plan
    
    async def _decompose_with_llm(
        self,
        goal: str,
        team_capabilities: Set[str],
        available_agents: Dict[str, List[str]],
        context: Dict[str, Any],
        strategy: DecompositionStrategy,
        max_depth: int,
    ) -> List[DecomposedTask]:
        """使用LLM分解任务"""
        
        agent_info = "\n".join([
            f"- {agent_type}: {', '.join(caps)}"
            for agent_type, caps in available_agents.items()
        ])
        
        prompt = f"""请将以下目标分解为具体可执行的子任务。

目标: {goal}

可用Agent和能力:
{agent_info}

团队上下文:
{json.dumps(context, ensure_ascii=False, indent=2)}

请以JSON格式返回分解的任务列表:
{{
    "tasks": [
        {{
            "name": "任务名称",
            "description": "详细描述",
            "assigned_agent": "agent_type",
            "required_capabilities": ["cap1", "cap2"],
            "priority": "high/medium/low",
            "dependencies": ["依赖的任务名称"]
        }}
    ],
    "strategy": "sequential/parallel/hierarchical",
    "reasoning": "分解理由"
}}

要求:
1. 每个任务应该能够由单个Agent完成
2. 明确任务间的依赖关系
3. 根据任务性质选择合适的Agent
4. 优先级应反映任务重要性
"""
        
        try:
            response = await self._call_llm(prompt)
            result = json.loads(response)
            
            tasks = []
            task_name_map: Dict[str, str] = {}
            
            for task_data in result.get("tasks", []):
                task = DecomposedTask(
                    name=task_data["name"],
                    description=task_data["description"],
                    assigned_agent=task_data.get("assigned_agent"),
                    required_capabilities=task_data.get("required_capabilities", []),
                    priority=TaskPriority(task_data.get("priority", "medium")),
                    metadata={"original_data": task_data}
                )
                tasks.append(task)
                task_name_map[task.name] = task.id
            
            for i, task_data in enumerate(result.get("tasks", [])):
                task = tasks[i]
                for dep_name in task_data.get("dependencies", []):
                    if dep_name in task_name_map:
                        task.dependencies.append(task_name_map[dep_name])
            
            return tasks
            
        except Exception as e:
            logger.error(f"[TaskPlanner] LLM decomposition failed: {e}")
            return self._decompose_rule_based(goal, team_capabilities, strategy)
    
    def _decompose_rule_based(
        self,
        goal: str,
        team_capabilities: Set[str],
        strategy: DecompositionStrategy,
    ) -> List[DecomposedTask]:
        """基于规则的任务分解"""
        
        tasks = []
        goal_lower = goal.lower()
        
        if any(kw in goal_lower for kw in ["开发", "实现", "编写", "代码", "code"]):
            if "analysis" in team_capabilities:
                tasks.append(DecomposedTask(
                    name="需求分析",
                    description=f"分析目标 '{goal}' 的需求",
                    assigned_agent="analyst",
                    required_capabilities=["analysis"],
                    priority=TaskPriority.HIGH,
                ))
            
            if "design" in team_capabilities:
                tasks.append(DecomposedTask(
                    name="方案设计",
                    description="设计实现方案",
                    assigned_agent="architect",
                    required_capabilities=["design"],
                    priority=TaskPriority.HIGH,
                ))
            
            if "coding" in team_capabilities:
                task = DecomposedTask(
                    name="编码实现",
                    description="实现具体功能",
                    assigned_agent="coder",
                    required_capabilities=["coding"],
                    priority=TaskPriority.HIGH,
                )
                task.dependencies = [t.id for t in tasks]
                tasks.append(task)
            
            if "testing" in team_capabilities:
                task = DecomposedTask(
                    name="测试验证",
                    description="编写并执行测试",
                    assigned_agent="tester",
                    required_capabilities=["testing"],
                    priority=TaskPriority.MEDIUM,
                )
                task.dependencies = [tasks[-1].id] if tasks else []
                tasks.append(task)
        
        elif any(kw in goal_lower for kw in ["分析", "报告", "report", "analysis"]):
            tasks.append(DecomposedTask(
                name="数据收集",
                description="收集所需数据和信息",
                assigned_agent="analyst",
                required_capabilities=["analysis"],
                priority=TaskPriority.HIGH,
            ))
            
            task = DecomposedTask(
                name="分析处理",
                description="分析收集的数据",
                assigned_agent="analyst",
                required_capabilities=["analysis"],
                priority=TaskPriority.HIGH,
            )
            task.dependencies = [tasks[0].id]
            tasks.append(task)
            
            task = DecomposedTask(
                name="报告生成",
                description="生成分析报告",
                assigned_agent="reporter",
                required_capabilities=["writing"],
                priority=TaskPriority.MEDIUM,
            )
            task.dependencies = [tasks[1].id]
            tasks.append(task)
        
        else:
            tasks.append(DecomposedTask(
                name="执行任务",
                description=goal,
                required_capabilities=list(team_capabilities)[:3] if team_capabilities else [],
                priority=TaskPriority.MEDIUM,
            ))
        
        return tasks
    
    def _resolve_dependencies(self, plan: ExecutionPlan) -> None:
        """解析任务依赖关系"""
        for task in plan.tasks:
            for dep_id in task.dependencies:
                dep_task = plan.get_task(dep_id)
                if dep_task and task.id not in dep_task.dependents:
                    dep_task.dependents.append(task.id)
    
    async def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        if not self._llm_client:
            raise ValueError("LLM client not configured")
        
        from ..llm_utils import call_llm
        result = await call_llm(self._llm_client, prompt)
        if result is None:
            raise ValueError("LLM call failed")
        return result
    
    def update_task_status(
        self,
        plan: ExecutionPlan,
        task_id: str,
        status: TaskStatus,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        更新任务状态
        
        Args:
            plan: 执行计划
            task_id: 任务ID
            status: 新状态
            result: 任务结果
            error: 错误信息
        
        Returns:
            是否更新成功
        """
        task = plan.get_task(task_id)
        if not task:
            return False
        
        task.status = status
        
        if result:
            task.result = result
        if error:
            task.error = error
        
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            task.completed_at = datetime.now()
        
        logger.info(f"[TaskPlanner] Task {task_id} status: {status}")
        return True
    
    def get_next_tasks(
        self,
        plan: ExecutionPlan,
        running_count: int = 0,
        max_parallel: int = 3,
    ) -> List[DecomposedTask]:
        """
        获取下一批可执行任务
        
        Args:
            plan: 执行计划
            running_count: 当前运行中任务数
            max_parallel: 最大并行数
        
        Returns:
            可执行任务列表
        """
        ready_tasks = plan.get_ready_tasks()
        
        available_slots = max_parallel - running_count
        if available_slots <= 0:
            return []
        
        return ready_tasks[:available_slots]