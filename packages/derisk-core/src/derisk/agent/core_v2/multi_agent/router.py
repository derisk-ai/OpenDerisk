"""
Agent Router - Agent路由器

实现任务到Agent的智能路由：
1. 能力匹配 - 根据任务需求匹配Agent能力
2. 负载均衡 - 平衡Agent工作负载
3. 策略选择 - 支持多种路由策略

@see ARCHITECTURE.md#12.6-agentrouter-路由器
"""

from typing import Any, Dict, List, Optional, Set
from enum import Enum
import logging

from pydantic import BaseModel, Field

from .team import WorkerAgent, AgentStatus
from .planner import DecomposedTask

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """路由策略"""
    CAPABILITY_BASED = "capability_based"    # 基于能力匹配
    LOAD_BALANCED = "load_balanced"          # 负载均衡
    ROUND_ROBIN = "round_robin"              # 轮询
    LEAST_LOADED = "least_loaded"            # 最少负载
    BEST_FIT = "best_fit"                    # 最佳匹配
    RANDOM = "random"                        # 随机


class AgentCapability(BaseModel):
    """Agent能力"""
    name: str
    description: str = ""
    proficiency: float = 0.8
    categories: List[str] = Field(default_factory=list)
    
    def matches(self, required: str) -> bool:
        """检查是否匹配"""
        return (
            self.name.lower() == required.lower() or
            required.lower() in self.name.lower() or
            any(required.lower() in cat.lower() for cat in self.categories)
        )


class AgentSelectionResult(BaseModel):
    """Agent选择结果"""
    selected_agent_id: str
    selected_agent_type: str
    score: float
    strategy: RoutingStrategy
    reason: str
    alternatives: List[str] = Field(default_factory=list)


class AgentRouter:
    """
    Agent路由器
    
    根据任务需求和路由策略，选择最合适的Agent。
    
    @example
    ```python
    router = AgentRouter()
    router.register_agent("analyst", ["analysis", "research"])
    router.register_agent("coder", ["coding", "debugging"])
    
    result = router.route(
        task=task,
        strategy=RoutingStrategy.BEST_FIT,
    )
    print(f"Selected: {result.selected_agent_type}")
    ```
    """
    
    def __init__(
        self,
        default_strategy: RoutingStrategy = RoutingStrategy.BEST_FIT,
    ):
        self._default_strategy = default_strategy
        self._agent_capabilities: Dict[str, List[AgentCapability]] = {}
        self._agent_status: Dict[str, AgentStatus] = {}
        self._agent_load: Dict[str, int] = {}
        self._round_robin_index: Dict[str, int] = {}
    
    def register_agent(
        self,
        agent_type: str,
        capabilities: List[str],
        proficiency: float = 0.8,
    ) -> None:
        """注册Agent类型及其能力"""
        caps = [
            AgentCapability(name=cap, proficiency=proficiency)
            for cap in capabilities
        ]
        self._agent_capabilities[agent_type] = caps
        self._agent_status[agent_type] = AgentStatus.IDLE
        self._agent_load[agent_type] = 0
        
        logger.debug(f"[AgentRouter] Registered agent type: {agent_type} with capabilities: {capabilities}")
    
    def update_agent_status(
        self,
        agent_type: str,
        status: AgentStatus,
        current_tasks: int = 0,
    ) -> None:
        """更新Agent状态"""
        self._agent_status[agent_type] = status
        self._agent_load[agent_type] = current_tasks
    
    def route(
        self,
        task: DecomposedTask,
        available_agents: Optional[Dict[str, WorkerAgent]] = None,
        strategy: Optional[RoutingStrategy] = None,
        exclude: Optional[Set[str]] = None,
    ) -> Optional[AgentSelectionResult]:
        """
        为任务路由合适的Agent
        
        Args:
            task: 待路由的任务
            available_agents: 可用的Agent实例映射
            strategy: 路由策略
            exclude: 需排除的Agent类型
        
        Returns:
            AgentSelectionResult或None
        """
        strategy = strategy or self._default_strategy
        exclude = exclude or set()
        
        if strategy == RoutingStrategy.CAPABILITY_BASED:
            return self._route_by_capability(task, exclude)
        elif strategy == RoutingStrategy.LOAD_BALANCED:
            return self._route_load_balanced(task, exclude)
        elif strategy == RoutingStrategy.ROUND_ROBIN:
            return self._route_round_robin(task, exclude)
        elif strategy == RoutingStrategy.LEAST_LOADED:
            return self._route_least_loaded(task, exclude)
        elif strategy == RoutingStrategy.RANDOM:
            return self._route_random(task, exclude)
        else:
            return self._route_best_fit(task, exclude)
    
    def _route_by_capability(
        self,
        task: DecomposedTask,
        exclude: Set[str],
    ) -> Optional[AgentSelectionResult]:
        """基于能力匹配路由"""
        required_caps = set(task.required_capabilities)
        if not required_caps:
            return None
        
        best_agent = None
        best_score = 0.0
        
        for agent_type, capabilities in self._agent_capabilities.items():
            if agent_type in exclude:
                continue
            if self._agent_status.get(agent_type) == AgentStatus.BUSY:
                continue
            
            available_caps = {cap.name for cap in capabilities}
            matching = required_caps.intersection(available_caps)
            
            if matching:
                score = len(matching) / len(required_caps)
                
                proficiency_sum = sum(
                    self._get_proficiency(capabilities, cap)
                    for cap in matching
                )
                avg_proficiency = proficiency_sum / len(matching) if matching else 0
                score = score * 0.6 + avg_proficiency * 0.4
                
                if score > best_score:
                    best_score = score
                    best_agent = agent_type
        
        if best_agent:
            return AgentSelectionResult(
                selected_agent_id=best_agent,
                selected_agent_type=best_agent,
                score=best_score,
                strategy=RoutingStrategy.CAPABILITY_BASED,
                reason=f"Matched capabilities for task {task.id}",
            )
        
        return None
    
    def _route_load_balanced(
        self,
        task: DecomposedTask,
        exclude: Set[str],
    ) -> Optional[AgentSelectionResult]:
        """负载均衡路由"""
        candidates = [
            agent_type for agent_type, status in self._agent_status.items()
            if status != AgentStatus.BUSY and agent_type not in exclude
        ]
        
        if not candidates:
            return None
        
        min_load = min(self._agent_load.get(t, 0) for t in candidates)
        least_loaded = [t for t in candidates if self._agent_load.get(t, 0) == min_load]
        
        for agent_type in least_loaded:
            if self._can_handle(agent_type, task):
                return AgentSelectionResult(
                    selected_agent_id=agent_type,
                    selected_agent_type=agent_type,
                    score=1.0 - (min_load / 10.0),
                    strategy=RoutingStrategy.LOAD_BALANCED,
                    reason=f"Least loaded agent with load {min_load}",
                )
        
        selected = least_loaded[0] if least_loaded else candidates[0]
        return AgentSelectionResult(
            selected_agent_id=selected,
            selected_agent_type=selected,
            score=0.5,
            strategy=RoutingStrategy.LOAD_BALANCED,
            reason="Least loaded agent (capability not matched)",
        )
    
    def _route_round_robin(
        self,
        task: DecomposedTask,
        exclude: Set[str],
    ) -> Optional[AgentSelectionResult]:
        """轮询路由"""
        candidates = [
            agent_type for agent_type, status in self._agent_status.items()
            if status != AgentStatus.BUSY and agent_type not in exclude
        ]
        
        if not candidates:
            return None
        
        task_key = task.id[:4]
        if task_key not in self._round_robin_index:
            self._round_robin_index[task_key] = 0
        
        index = self._round_robin_index[task_key] % len(candidates)
        self._round_robin_index[task_key] += 1
        
        selected = candidates[index]
        
        return AgentSelectionResult(
            selected_agent_id=selected,
            selected_agent_type=selected,
            score=0.5,
            strategy=RoutingStrategy.ROUND_ROBIN,
            reason=f"Round robin selection (index {index})",
        )
    
    def _route_least_loaded(
        self,
        task: DecomposedTask,
        exclude: Set[str],
    ) -> Optional[AgentSelectionResult]:
        """选择最少负载的Agent"""
        candidates = []
        
        for agent_type, status in self._agent_status.items():
            if status != AgentStatus.BUSY and agent_type not in exclude:
                if self._can_handle(agent_type, task):
                    candidates.append((agent_type, self._agent_load.get(agent_type, 0)))
        
        if not candidates:
            for agent_type, status in self._agent_status.items():
                if status != AgentStatus.BUSY and agent_type not in exclude:
                    candidates.append((agent_type, self._agent_load.get(agent_type, 0)))
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x[1])
        selected, load = candidates[0]
        
        return AgentSelectionResult(
            selected_agent_id=selected,
            selected_agent_type=selected,
            score=1.0 - (load / 10.0),
            strategy=RoutingStrategy.LEAST_LOADED,
            reason=f"Least loaded with {load} tasks",
        )
    
    def _route_random(
        self,
        task: DecomposedTask,
        exclude: Set[str],
    ) -> Optional[AgentSelectionResult]:
        """随机路由"""
        import random
        
        candidates = [
            agent_type for agent_type, status in self._agent_status.items()
            if status != AgentStatus.BUSY and agent_type not in exclude
        ]
        
        if not candidates:
            return None
        
        selected = random.choice(candidates)
        
        return AgentSelectionResult(
            selected_agent_id=selected,
            selected_agent_type=selected,
            score=0.5,
            strategy=RoutingStrategy.RANDOM,
            reason="Random selection",
        )
    
    def _route_best_fit(
        self,
        task: DecomposedTask,
        exclude: Set[str],
    ) -> Optional[AgentSelectionResult]:
        """最佳匹配路由"""
        best_agent = None
        best_score = -1.0
        alternatives = []
        
        for agent_type, status in self._agent_status.items():
            if agent_type in exclude:
                continue
            if status == AgentStatus.BUSY:
                continue
            
            score = self._compute_fitness_score(agent_type, task)
            
            if score > best_score:
                best_score = score
                best_agent = agent_type
            elif score > 0:
                alternatives.append(agent_type)
        
        if best_agent:
            return AgentSelectionResult(
                selected_agent_id=best_agent,
                selected_agent_type=best_agent,
                score=best_score,
                strategy=RoutingStrategy.BEST_FIT,
                reason=f"Best fit with score {best_score:.2f}",
                alternatives=alternatives[:3],
            )
        
        return None
    
    def _compute_fitness_score(
        self,
        agent_type: str,
        task: DecomposedTask,
    ) -> float:
        """计算适配分数"""
        score = 0.0
        
        capabilities = self._agent_capabilities.get(agent_type, [])
        
        if task.required_capabilities:
            available = {cap.name for cap in capabilities}
            required = set(task.required_capabilities)
            matching = required.intersection(available)
            
            if matching:
                caps_score = len(matching) / len(required)
                
                proficiency = sum(
                    self._get_proficiency(capabilities, cap)
                    for cap in matching
                ) / len(matching)
                
                score += caps_score * 0.6 + proficiency * 0.4
        else:
            score += 0.5
        
        load = self._agent_load.get(agent_type, 0)
        load_factor = max(0, 1.0 - load / 10.0)
        score = score * 0.8 + load_factor * 0.2
        
        if task.assigned_agent and task.assigned_agent == agent_type:
            score += 0.3
        
        return score
    
    def _can_handle(
        self,
        agent_type: str,
        task: DecomposedTask,
    ) -> bool:
        """检查Agent是否能否处理任务"""
        if not task.required_capabilities:
            return True
        
        capabilities = self._agent_capabilities.get(agent_type, [])
        available = {cap.name for cap in capabilities}
        required = set(task.required_capabilities)
        
        return required.issubset(available)
    
    def _get_proficiency(
        self,
        capabilities: List[AgentCapability],
        capability_name: str,
    ) -> float:
        """获取能力熟练度"""
        for cap in capabilities:
            if cap.name == capability_name or cap.matches(capability_name):
                return cap.proficiency
        return 0.5
    
    def get_available_agents(self) -> List[str]:
        """获取可用Agent列表"""
        return [
            agent_type for agent_type, status in self._agent_status.items()
            if status != AgentStatus.BUSY
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取路由统计"""
        return {
            "registered_agents": len(self._agent_capabilities),
            "available_agents": sum(
                1 for s in self._agent_status.values() if s != AgentStatus.BUSY
            ),
            "load_distribution": dict(self._agent_load),
        }