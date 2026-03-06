"""
Goal - 目标管理系统

实现任务目标的创建、分解、追踪、验证
支持多级目标依赖和自动验证
"""

from typing import List, Optional, Dict, Any, Callable, Awaitable
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import uuid
import asyncio
import logging

logger = logging.getLogger(__name__)


class GoalStatus(str, Enum):
    """目标状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class GoalPriority(str, Enum):
    """目标优先级"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CriterionType(str, Enum):
    """成功标准类型"""
    LLM_EVAL = "llm_eval"
    EXACT_MATCH = "exact_match"
    REGEX = "regex"
    THRESHOLD = "threshold"
    CUSTOM = "custom"


class SuccessCriterion(BaseModel):
    """成功标准"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:8])
    description: str
    type: CriterionType = CriterionType.LLM_EVAL
    config: Dict[str, Any] = Field(default_factory=dict)
    is_required: bool = True
    weight: float = 1.0

    class Config:
        use_enum_values = True


class Goal(BaseModel):
    """目标模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    name: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    priority: GoalPriority = GoalPriority.MEDIUM
    success_criteria: List[SuccessCriterion] = Field(default_factory=list)
    parent_goal_id: Optional[str] = None
    sub_goals: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[str] = None
    error: Optional[str] = None
    
    max_retries: int = 3
    retry_count: int = 0
    timeout: Optional[int] = None

    class Config:
        use_enum_values = True
        arbitrary_types_allowed = True

    def update_status(self, status: GoalStatus):
        """更新状态"""
        self.status = status
        self.updated_at = datetime.now()
        if status == GoalStatus.IN_PROGRESS and not self.started_at:
            self.started_at = datetime.now()
        elif status in [GoalStatus.COMPLETED, GoalStatus.FAILED, GoalStatus.CANCELLED]:
            self.completed_at = datetime.now()

    def add_sub_goal(self, goal_id: str):
        """添加子目标"""
        if goal_id not in self.sub_goals:
            self.sub_goals.append(goal_id)
            self.updated_at = datetime.now()

    def add_dependency(self, goal_id: str):
        """添加依赖"""
        if goal_id not in self.dependencies:
            self.dependencies.append(goal_id)
            self.updated_at = datetime.now()


class Task(BaseModel):
    """任务模型 - 目标的具体执行步骤"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    goal_id: str
    name: str
    description: str
    action: str
    action_params: Dict[str, Any] = Field(default_factory=dict)
    status: GoalStatus = GoalStatus.PENDING
    priority: GoalPriority = GoalPriority.MEDIUM
    
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2

    class Config:
        use_enum_values = True


class GoalDecompositionStrategy(str, Enum):
    """目标分解策略"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"


class GoalManager:
    """
    目标管理器
    
    职责:
    1. 目标创建和生命周期管理
    2. 目标分解
    3. 成功标准验证
    4. 依赖关系管理
    5. 进度追踪
    
    示例:
        manager = GoalManager(llm_client=client)
        
        goal = await manager.create_goal(
            name="完成代码重构",
            description="重构用户模块代码",
            criteria=[SuccessCriterion(description="所有测试通过")]
        )
        
        await manager.start_goal(goal.id)
        is_completed = await manager.evaluate_goal(goal.id, context)
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        on_status_change: Optional[Callable[[Goal], Awaitable[None]]] = None
    ):
        self._goals: Dict[str, Goal] = {}
        self._tasks: Dict[str, Task] = {}
        self._llm_client = llm_client
        self._on_status_change = on_status_change
        self._criterion_checkers: Dict[CriterionType, Callable] = {
            CriterionType.EXACT_MATCH: self._check_exact_match,
            CriterionType.REGEX: self._check_regex,
            CriterionType.THRESHOLD: self._check_threshold,
            CriterionType.CUSTOM: self._check_custom,
        }

    async def create_goal(
        self,
        name: str,
        description: str,
        criteria: Optional[List[SuccessCriterion]] = None,
        priority: GoalPriority = GoalPriority.MEDIUM,
        parent_goal_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Goal:
        """
        创建目标
        
        Args:
            name: 目标名称
            description: 目标描述
            criteria: 成功标准列表
            priority: 优先级
            parent_goal_id: 父目标ID
            metadata: 元数据
            
        Returns:
            Goal: 创建的目标
        """
        goal = Goal(
            name=name,
            description=description,
            success_criteria=criteria or [],
            priority=priority,
            parent_goal_id=parent_goal_id,
            metadata=metadata or {}
        )
        
        self._goals[goal.id] = goal
        
        if parent_goal_id and parent_goal_id in self._goals:
            parent = self._goals[parent_goal_id]
            parent.add_sub_goal(goal.id)
        
        logger.info(f"[GoalManager] 创建目标: {goal.id[:8]} - {name}")
        return goal

    async def decompose_goal(
        self,
        goal: Goal,
        strategy: GoalDecompositionStrategy = GoalDecompositionStrategy.HIERARCHICAL,
        max_depth: int = 3
    ) -> List[Goal]:
        """
        分解目标为子目标
        
        Args:
            goal: 要分解的目标
            strategy: 分解策略
            max_depth: 最大分解深度
            
        Returns:
            List[Goal]: 子目标列表
        """
        if max_depth <= 0:
            return []
        
        if not self._llm_client:
            logger.warning("[GoalManager] 没有LLM客户端，无法分解目标")
            return []
        
        try:
            prompt = f"""请将以下目标分解为具体可执行的子目标。

目标: {goal.name}
描述: {goal.description}

请以JSON格式返回子目标列表：
[
    {{"name": "子目标名称", "description": "详细描述", "priority": "high/medium/low"}},
    ...
]
"""
            from .llm_utils import call_llm
            response = await call_llm(self._llm_client, prompt)
            if response is None:
                logger.error("[GoalManager] LLM 调用失败")
                return []
            import json
            sub_goal_data = json.loads(response)
            
            sub_goals = []
            for data in sub_goal_data:
                sub_goal = await self.create_goal(
                    name=data["name"],
                    description=data["description"],
                    priority=GoalPriority(data.get("priority", "medium")),
                    parent_goal_id=goal.id
                )
                
                if strategy == GoalDecompositionStrategy.SEQUENTIAL and sub_goals:
                    sub_goal.add_dependency(sub_goals[-1].id)
                
                sub_goals.append(sub_goal)
                
                if max_depth > 1:
                    await self.decompose_goal(sub_goal, strategy, max_depth - 1)
            
            logger.info(f"[GoalManager] 分解目标 {goal.id[:8]} 为 {len(sub_goals)} 个子目标")
            return sub_goals
            
        except Exception as e:
            logger.error(f"[GoalManager] 目标分解失败: {e}")
            return []

    async def start_goal(self, goal_id: str) -> bool:
        """
        启动目标
        
        Args:
            goal_id: 目标ID
            
        Returns:
            bool: 是否成功启动
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        
        for dep_id in goal.dependencies:
            dep_goal = self._goals.get(dep_id)
            if dep_goal and dep_goal.status != GoalStatus.COMPLETED:
                logger.warning(f"[GoalManager] 目标 {goal_id[:8]} 的依赖 {dep_id[:8]} 未完成")
                return False
        
        goal.update_status(GoalStatus.IN_PROGRESS)
        
        if self._on_status_change:
            await self._on_status_change(goal)
        
        logger.info(f"[GoalManager] 启动目标: {goal_id[:8]}")
        return True

    async def complete_goal(self, goal_id: str, result: Optional[str] = None) -> bool:
        """
        完成目标
        
        Args:
            goal_id: 目标ID
            result: 结果描述
            
        Returns:
            bool: 是否成功
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        
        goal.result = result
        goal.update_status(GoalStatus.COMPLETED)
        
        if self._on_status_change:
            await self._on_status_change(goal)
        
        logger.info(f"[GoalManager] 完成目标: {goal_id[:8]}")
        return True

    async def fail_goal(self, goal_id: str, error: str) -> bool:
        """
        标记目标失败
        
        Args:
            goal_id: 目标ID
            error: 错误信息
            
        Returns:
            bool: 是否成功
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        
        goal.error = error
        goal.update_status(GoalStatus.FAILED)
        
        if self._on_status_change:
            await self._on_status_change(goal)
        
        logger.error(f"[GoalManager] 目标失败: {goal_id[:8]} - {error}")
        return True

    async def evaluate_goal(
        self,
        goal_id: str,
        context: Dict[str, Any]
    ) -> bool:
        """
        评估目标是否达成
        
        Args:
            goal_id: 目标ID
            context: 执行上下文
            
        Returns:
            bool: 是否达成
        """
        goal = self._goals.get(goal_id)
        if not goal:
            return False
        
        if not goal.success_criteria:
            return True
        
        total_weight = sum(c.weight for c in goal.success_criteria)
        achieved_weight = 0.0
        
        for criterion in goal.success_criteria:
            passed = await self._check_criterion(criterion, context)
            if passed:
                achieved_weight += criterion.weight
            
            logger.debug(
                f"[GoalManager] 标准 '{criterion.description}': {'通过' if passed else '未通过'}"
            )
        
        achievement_ratio = achieved_weight / total_weight if total_weight > 0 else 0
        
        if achievement_ratio >= 1.0:
            await self.complete_goal(goal_id, f"达成率: {achievement_ratio:.1%}")
            return True
        elif goal.retry_count < goal.max_retries:
            goal.retry_count += 1
            logger.info(f"[GoalManager] 目标 {goal_id[:8]} 重试 {goal.retry_count}/{goal.max_retries}")
            return False
        else:
            await self.fail_goal(goal_id, f"达成率不足: {achievement_ratio:.1%}")
            return False

    async def _check_criterion(
        self,
        criterion: SuccessCriterion,
        context: Dict[str, Any]
    ) -> bool:
        """检查单个成功标准"""
        checker = self._criterion_checkers.get(criterion.type)
        
        if checker:
            return await checker(criterion, context)
        
        if criterion.type == CriterionType.LLM_EVAL and self._llm_client:
            return await self._check_llm_eval(criterion, context)
        
        return True

    async def _check_exact_match(
        self,
        criterion: SuccessCriterion,
        context: Dict[str, Any]
    ) -> bool:
        """精确匹配检查"""
        expected = criterion.config.get("expected")
        actual = context.get(criterion.config.get("field", "result"))
        return expected == actual

    async def _check_regex(
        self,
        criterion: SuccessCriterion,
        context: Dict[str, Any]
    ) -> bool:
        """正则表达式检查"""
        import re
        pattern = criterion.config.get("pattern")
        text = str(context.get(criterion.config.get("field", "result")))
        return bool(re.search(pattern, text))

    async def _check_threshold(
        self,
        criterion: SuccessCriterion,
        context: Dict[str, Any]
    ) -> bool:
        """阈值检查"""
        threshold = criterion.config.get("threshold")
        value = context.get(criterion.config.get("field", "value"))
        operator = criterion.config.get("operator", ">=")
        
        if value is None:
            return False
        
        if operator == ">=":
            return value >= threshold
        elif operator == ">":
            return value > threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "<":
            return value < threshold
        elif operator == "==":
            return value == threshold
        
        return False

    async def _check_custom(
        self,
        criterion: SuccessCriterion,
        context: Dict[str, Any]
    ) -> bool:
        """自定义检查"""
        checker_func = criterion.config.get("checker_func")
        if callable(checker_func):
            if asyncio.iscoroutinefunction(checker_func):
                return await checker_func(criterion, context)
            else:
                return checker_func(criterion, context)
        return True

    async def _check_llm_eval(
        self,
        criterion: SuccessCriterion,
        context: Dict[str, Any]
    ) -> bool:
        """LLM评估检查"""
        try:
            prompt = f"""请评估以下内容是否满足要求。

要求: {criterion.description}

内容: {context.get('result', '')}

请只回答 "是" 或 "否"。
"""
            from .llm_utils import call_llm
            response = await call_llm(self._llm_client, prompt)
            if response is None:
                logger.error("[GoalManager] LLM评估失败")
                return False
            return "是" in response or "yes" in response.lower()
        except Exception as e:
            logger.error(f"[GoalManager] LLM评估失败: {e}")
            return False

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """获取目标"""
        return self._goals.get(goal_id)

    def get_sub_goals(self, goal_id: str) -> List[Goal]:
        """获取子目标"""
        goal = self._goals.get(goal_id)
        if not goal:
            return []
        return [self._goals[gid] for gid in goal.sub_goals if gid in self._goals]

    def get_all_goals(self) -> List[Goal]:
        """获取所有目标"""
        return list(self._goals.values())

    def get_goals_by_status(self, status: GoalStatus) -> List[Goal]:
        """按状态获取目标"""
        return [g for g in self._goals.values() if g.status == status]

    def get_ready_goals(self) -> List[Goal]:
        """获取可执行的目标（依赖已满足）"""
        ready = []
        for goal in self._goals.values():
            if goal.status != GoalStatus.PENDING:
                continue
            
            dependencies_met = all(
                self._goals.get(dep_id, Goal(name="", description="")).status == GoalStatus.COMPLETED
                for dep_id in goal.dependencies
            )
            
            if dependencies_met:
                ready.append(goal)
        
        return ready

    async def create_task(
        self,
        goal_id: str,
        name: str,
        description: str,
        action: str,
        action_params: Optional[Dict[str, Any]] = None,
        priority: GoalPriority = GoalPriority.MEDIUM
    ) -> Task:
        """创建任务"""
        task = Task(
            goal_id=goal_id,
            name=name,
            description=description,
            action=action,
            action_params=action_params or {},
            priority=priority
        )
        self._tasks[task.id] = task
        logger.info(f"[GoalManager] 创建任务: {task.id[:8]} - {name}")
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self._tasks.get(task_id)

    def get_tasks_by_goal(self, goal_id: str) -> List[Task]:
        """获取目标的所有任务"""
        return [t for t in self._tasks.values() if t.goal_id == goal_id]

    async def execute_task(self, task: Task, executor: Callable) -> Any:
        """执行任务"""
        task.status = GoalStatus.IN_PROGRESS
        task.started_at = datetime.now()
        
        try:
            result = await executor(task.action, task.action_params)
            task.result = str(result)
            task.status = GoalStatus.COMPLETED
            task.completed_at = datetime.now()
            logger.info(f"[GoalManager] 任务完成: {task.id[:8]}")
            return result
        except Exception as e:
            task.error = str(e)
            task.retry_count += 1
            
            if task.retry_count >= task.max_retries:
                task.status = GoalStatus.FAILED
                logger.error(f"[GoalManager] 任务失败: {task.id[:8]} - {e}")
            else:
                task.status = GoalStatus.PENDING
                logger.warning(f"[GoalManager] 任务重试: {task.id[:8]} - {e}")
            
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        goals = list(self._goals.values())
        tasks = list(self._tasks.values())
        
        return {
            "total_goals": len(goals),
            "goals_by_status": {
                status.value: len([g for g in goals if g.status == status])
                for status in GoalStatus
            },
            "total_tasks": len(tasks),
            "tasks_by_status": {
                status.value: len([t for t in tasks if t.status == status])
                for status in GoalStatus
            },
        }


class TaskTracker:
    """
    任务追踪器 - 追踪任务执行进度
    
    示例:
        tracker = TaskTracker()
        tracker.start_tracking("task-1")
        tracker.update_progress("task-1", 50, "处理中")
        tracker.complete_tracking("task-1", "task-1 completed")
    """
    
    def __init__(self):
        self._tracking: Dict[str, Dict[str, Any]] = {}
    
    def start_tracking(self, task_id: str, metadata: Optional[Dict] = None):
        """开始追踪"""
        self._tracking[task_id] = {
            "started_at": datetime.now(),
            "status": "in_progress",
            "progress": 0,
            "message": "",
            "metadata": metadata or {}
        }
    
    def update_progress(self, task_id: str, progress: int, message: str = ""):
        """更新进度"""
        if task_id in self._tracking:
            self._tracking[task_id]["progress"] = min(100, max(0, progress))
            self._tracking[task_id]["message"] = message
            self._tracking[task_id]["updated_at"] = datetime.now()
    
    def complete_tracking(self, task_id: str, result: str = ""):
        """完成追踪"""
        if task_id in self._tracking:
            self._tracking[task_id]["completed_at"] = datetime.now()
            self._tracking[task_id]["status"] = "completed"
            self._tracking[task_id]["progress"] = 100
            self._tracking[task_id]["result"] = result
    
    def fail_tracking(self, task_id: str, error: str):
        """失败追踪"""
        if task_id in self._tracking:
            self._tracking[task_id]["completed_at"] = datetime.now()
            self._tracking[task_id]["status"] = "failed"
            self._tracking[task_id]["error"] = error
    
    def get_tracking(self, task_id: str) -> Optional[Dict]:
        """获取追踪信息"""
        return self._tracking.get(task_id)


goal_manager = GoalManager()