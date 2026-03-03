"""
SubagentManager - 子Agent管理器

实现子Agent的注册、查找、委派和执行:
1. Agent注册 - 注册可用的子Agent
2. 任务委派 - 将任务委派给合适的子Agent
3. 会话隔离 - 为子Agent创建独立的执行上下文
4. 结果收集 - 收集子Agent的执行结果

参考OpenCode的Task工具设计,实现简洁的子Agent调用模式
"""

from typing import Any, Callable, Dict, List, Optional, Awaitable, AsyncIterator, Type, Union, TYPE_CHECKING
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
import asyncio
import logging
import uuid
import copy

from pydantic import BaseModel, Field

from .agent_info import AgentInfo, AgentMode, PermissionRuleset, PermissionAction
from .permission import PermissionChecker, PermissionResponse

# Type hints for context isolation
if TYPE_CHECKING:
    from .context_isolation import (
        ContextIsolationManager,
        ContextIsolationMode,
        SubagentContextConfig,
        IsolatedContext,
        ContextWindow,
    )

logger = logging.getLogger(__name__)


class SubagentStatus(str, Enum):
    """子Agent状态"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TaskPermission(str, Enum):
    """任务权限 - 控制子Agent调用"""
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class SubagentSession:
    """子Agent会话 - 隔离的执行上下文"""
    session_id: str
    parent_session_id: str
    subagent_name: str
    task: str
    status: SubagentStatus = SubagentStatus.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    result: Optional[str] = None
    error: Optional[str] = None
    
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    
    tokens_used: int = 0
    steps_taken: int = 0
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_session_id": self.parent_session_id,
            "subagent_name": self.subagent_name,
            "task": self.task,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "steps_taken": self.steps_taken,
        }


class SubagentResult(BaseModel):
    """子Agent执行结果"""
    success: bool
    subagent_name: str
    task: str
    output: Optional[str] = None
    error: Optional[str] = None
    session_id: str
    
    tokens_used: int = 0
    steps_taken: int = 0
    execution_time_ms: float = 0.0
    
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_llm_message(self) -> str:
        """生成给LLM的消息"""
        if self.success:
            return f"[子Agent {self.subagent_name}] 任务完成:\n{self.output}"
        else:
            return f"[子Agent {self.subagent_name}] 任务失败: {self.error}"


class TaskPermissionRule(BaseModel):
    """任务权限规则 - 控制哪些子Agent可以被调用"""
    pattern: str
    action: TaskPermission
    description: Optional[str] = None


class TaskPermissionConfig(BaseModel):
    """任务权限配置"""
    rules: List[TaskPermissionRule] = Field(default_factory=list)
    default_action: TaskPermission = TaskPermission.ALLOW
    
    def check(self, subagent_name: str) -> TaskPermission:
        """检查子Agent调用权限"""
        import fnmatch
        for rule in self.rules:
            if fnmatch.fnmatch(subagent_name, rule.pattern):
                return rule.action
        return self.default_action
    
    @classmethod
    def from_dict(cls, config: Dict[str, str]) -> "TaskPermissionConfig":
        """从字典创建"""
        rules = []
        for pattern, action_str in config.items():
            action = TaskPermission(action_str)
            rules.append(TaskPermissionRule(pattern=pattern, action=action))
        return cls(rules=rules)


class SubagentInfo(BaseModel):
    """子Agent信息 - 用于注册和发现"""
    name: str
    description: str
    mode: AgentMode = AgentMode.SUBAGENT
    hidden: bool = False
    
    capabilities: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    
    model_id: Optional[str] = None
    max_steps: int = 10
    timeout: int = 300
    
    system_prompt: Optional[str] = None
    
    task_permission: Optional[TaskPermissionConfig] = None


class SubagentRegistry:
    """
    子Agent注册表
    
    管理所有可用的子Agent配置
    """
    
    def __init__(self):
        self._agents: Dict[str, SubagentInfo] = {}
        self._agent_classes: Dict[str, Type] = {}
        self._factories: Dict[str, Callable] = {}
    
    def register(
        self,
        info: SubagentInfo,
        agent_class: Optional[Type] = None,
        factory: Optional[Callable] = None,
    ) -> None:
        """注册子Agent"""
        self._agents[info.name] = info
        if agent_class:
            self._agent_classes[info.name] = agent_class
        if factory:
            self._factories[info.name] = factory
        logger.info(f"[SubagentRegistry] Registered subagent: {info.name}")
    
    def unregister(self, name: str) -> bool:
        """注销子Agent"""
        if name in self._agents:
            del self._agents[name]
            self._agent_classes.pop(name, None)
            self._factories.pop(name, None)
            return True
        return False
    
    def get(self, name: str) -> Optional[SubagentInfo]:
        """获取子Agent信息"""
        return self._agents.get(name)
    
    def get_factory(self, name: str) -> Optional[Callable]:
        """获取子Agent工厂"""
        return self._factories.get(name)
    
    def get_agent_class(self, name: str) -> Optional[Type]:
        """获取子Agent类"""
        return self._agent_classes.get(name)
    
    def list_all(self, include_hidden: bool = False) -> List[SubagentInfo]:
        """列出所有子Agent"""
        agents = list(self._agents.values())
        if not include_hidden:
            agents = [a for a in agents if not a.hidden]
        return agents
    
    def list_for_llm(self) -> List[Dict[str, Any]]:
        """生成给LLM的子Agent列表"""
        return [
            {
                "name": agent.name,
                "description": agent.description,
                "capabilities": agent.capabilities,
            }
            for agent in self.list_all(include_hidden=False)
        ]
    
    def get_tools_description(self) -> str:
        """生成工具描述给LLM"""
        agents = self.list_all(include_hidden=False)
        if not agents:
            return "没有可用的子Agent"
        
        lines = ["可用子Agent:"]
        for agent in agents:
            lines.append(f"- {agent.name}: {agent.description}")
            if agent.capabilities:
                lines.append(f"  能力: {', '.join(agent.capabilities)}")
        return "\n".join(lines)


class SubagentManager:
    """
    子Agent管理器
    
    核心职责:
    1. 管理子Agent注册表
    2. 处理任务委派请求
    3. 创建隔离的执行会话
    4. 收集和返回执行结果
    
    参考 OpenCode 的 Task 工具设计
    
    @example
    ```python
    manager = SubagentManager()
    
    # 注册子Agent
    manager.register(SubagentInfo(
        name="code-reviewer",
        description="代码审查Agent",
        capabilities=["code-review", "security-audit"],
    ), factory=create_code_reviewer)
    
    # 委派任务
    result = await manager.delegate(
        subagent_name="code-reviewer",
        task="审查 authentication.py 的安全性",
        parent_session_id="parent-123",
    )
    ```
    """
    
    def __init__(
        self,
        registry: Optional[SubagentRegistry] = None,
        on_session_start: Optional[Callable[[SubagentSession], Awaitable[None]]] = None,
        on_session_complete: Optional[Callable[[SubagentSession, SubagentResult], Awaitable[None]]] = None,
        ask_permission_callback: Optional[Callable[[str, str], Awaitable[bool]]] = None,
        # 新增: 上下文隔离管理器
        context_isolation_manager: Optional["ContextIsolationManager"] = None,
    ):
        self._registry = registry or SubagentRegistry()
        self._on_session_start = on_session_start
        self._on_session_complete = on_session_complete
        self._ask_permission_callback = ask_permission_callback

        # 上下文隔离管理器
        self._context_isolation_manager = context_isolation_manager

        self._sessions: Dict[str, SubagentSession] = {}
        self._active_executions: Dict[str, asyncio.Task] = {}
    
    @property
    def registry(self) -> SubagentRegistry:
        return self._registry
    
    def register(
        self,
        info: SubagentInfo,
        agent_class: Optional[Type] = None,
        factory: Optional[Callable] = None,
    ) -> None:
        """注册子Agent"""
        self._registry.register(info, agent_class, factory)
    
    def get_available_subagents(self) -> List[SubagentInfo]:
        """获取可用的子Agent列表"""
        return self._registry.list_all(include_hidden=False)
    
    def get_subagent_description(self) -> str:
        """获取子Agent描述（给LLM）"""
        return self._registry.get_tools_description()
    
    async def can_delegate(
        self,
        subagent_name: str,
        task: str,
        caller_permission: Optional[TaskPermissionConfig] = None,
    ) -> bool:
        """
        检查是否可以委派任务给子Agent
        
        Args:
            subagent_name: 子Agent名称
            task: 任务内容
            caller_permission: 调用者的任务权限配置
        
        Returns:
            是否允许委派
        """
        subagent = self._registry.get(subagent_name)
        if not subagent:
            logger.warning(f"[SubagentManager] Subagent not found: {subagent_name}")
            return False
        
        if caller_permission:
            permission = caller_permission.check(subagent_name)
            if permission == TaskPermission.DENY:
                return False
            elif permission == TaskPermission.ASK:
                if self._ask_permission_callback:
                    return await self._ask_permission_callback(subagent_name, task)
                return False
        
        return True
    
    async def delegate(
        self,
        subagent_name: str,
        task: str,
        parent_session_id: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        sync: bool = True,
    ) -> SubagentResult:
        """
        委派任务给子Agent
        
        Args:
            subagent_name: 子Agent名称
            task: 任务内容
            parent_session_id: 父会话ID
            context: 上下文信息
            timeout: 超时时间（秒）
            sync: 是否同步等待结果
        
        Returns:
            SubagentResult: 执行结果
        """
        subagent_info = self._registry.get(subagent_name)
        if not subagent_info:
            return SubagentResult(
                success=False,
                subagent_name=subagent_name,
                task=task,
                error=f"子Agent '{subagent_name}' 不存在",
                session_id="",
            )
        
        session = SubagentSession(
            session_id=f"sub_{uuid.uuid4().hex[:8]}",
            parent_session_id=parent_session_id,
            subagent_name=subagent_name,
            task=task,
            metadata={"context": context or {}},
        )
        
        self._sessions[session.session_id] = session
        
        if self._on_session_start:
            await self._on_session_start(session)
        
        timeout = timeout or subagent_info.timeout
        
        if sync:
            return await self._execute_sync(session, subagent_info, context, timeout)
        else:
            asyncio.create_task(self._execute_async(session, subagent_info, context, timeout))
            return SubagentResult(
                success=True,
                subagent_name=subagent_name,
                task=task,
                output="任务已异步提交",
                session_id=session.session_id,
            )
    
    async def _execute_sync(
        self,
        session: SubagentSession,
        subagent_info: SubagentInfo,
        context: Optional[Dict[str, Any]],
        timeout: int,
    ) -> SubagentResult:
        """同步执行"""
        start_time = datetime.now()
        session.status = SubagentStatus.RUNNING
        session.started_at = start_time
        
        try:
            result = await asyncio.wait_for(
                self._run_subagent(session, subagent_info, context),
                timeout=timeout,
            )
            
            session.completed_at = datetime.now()
            session.status = SubagentStatus.COMPLETED
            session.result = result.output
            
            execution_time = (session.completed_at - start_time).total_seconds() * 1000
            result.execution_time_ms = execution_time
            result.session_id = session.session_id
            
            if self._on_session_complete:
                await self._on_session_complete(session, result)
            
            return result
            
        except asyncio.TimeoutError:
            session.status = SubagentStatus.TIMEOUT
            session.completed_at = datetime.now()
            session.error = f"执行超时（{timeout}秒）"
            
            result = SubagentResult(
                success=False,
                subagent_name=session.subagent_name,
                task=session.task,
                error=session.error,
                session_id=session.session_id,
            )
            
            if self._on_session_complete:
                await self._on_session_complete(session, result)
            
            return result
            
        except Exception as e:
            session.status = SubagentStatus.FAILED
            session.completed_at = datetime.now()
            session.error = str(e)
            
            result = SubagentResult(
                success=False,
                subagent_name=session.subagent_name,
                task=session.task,
                error=str(e),
                session_id=session.session_id,
            )
            
            if self._on_session_complete:
                await self._on_session_complete(session, result)
            
            return result
    
    async def _execute_async(
        self,
        session: SubagentSession,
        subagent_info: SubagentInfo,
        context: Optional[Dict[str, Any]],
        timeout: int,
    ) -> None:
        """异步执行"""
        result = await self._execute_sync(session, subagent_info, context, timeout)
        logger.info(f"[SubagentManager] Async execution completed: {session.session_id}")
    
    async def _run_subagent(
        self,
        session: SubagentSession,
        subagent_info: SubagentInfo,
        context: Optional[Dict[str, Any]],
    ) -> SubagentResult:
        """
        运行子Agent
        
        这里可以:
        1. 使用工厂创建Agent实例
        2. 调用Agent的run方法
        3. 收集结果
        """
        factory = self._registry.get_factory(session.subagent_name)
        
        if factory:
            try:
                agent = await self._create_agent_from_factory(factory, subagent_info, context)
                output = await self._run_agent(agent, session.task, context)
                
                return SubagentResult(
                    success=True,
                    subagent_name=session.subagent_name,
                    task=session.task,
                    output=output,
                    session_id=session.session_id,
                    steps_taken=session.steps_taken,
                    tokens_used=session.tokens_used,
                )
            except Exception as e:
                logger.error(f"[SubagentManager] Factory execution failed: {e}")
        
        agent_class = self._registry.get_agent_class(session.subagent_name)
        if agent_class:
            try:
                agent = await self._create_agent_from_class(agent_class, subagent_info, context)
                output = await self._run_agent(agent, session.task, context)
                
                return SubagentResult(
                    success=True,
                    subagent_name=session.subagent_name,
                    task=session.task,
                    output=output,
                    session_id=session.session_id,
                )
            except Exception as e:
                logger.error(f"[SubagentManager] Class execution failed: {e}")
        
        return SubagentResult(
            success=False,
            subagent_name=session.subagent_name,
            task=session.task,
            error="无法创建子Agent实例",
            session_id=session.session_id,
        )
    
    async def _create_agent_from_factory(
        self,
        factory: Callable,
        subagent_info: SubagentInfo,
        context: Optional[Dict[str, Any]],
    ) -> Any:
        """从工厂创建Agent"""
        if asyncio.iscoroutinefunction(factory):
            return await factory(subagent_info=subagent_info, context=context)
        else:
            return factory(subagent_info=subagent_info, context=context)
    
    async def _create_agent_from_class(
        self,
        agent_class: Type,
        subagent_info: SubagentInfo,
        context: Optional[Dict[str, Any]],
    ) -> Any:
        """从类创建Agent"""
        return agent_class(info=subagent_info)
    
    async def _run_agent(
        self,
        agent: Any,
        task: str,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """运行Agent"""
        if hasattr(agent, 'run'):
            if asyncio.iscoroutinefunction(agent.run):
                result = agent.run(task, context=context)
                if hasattr(result, '__aiter__'):
                    chunks = []
                    async for chunk in result:
                        chunks.append(chunk)
                    return "".join(chunks)
                else:
                    result = await result
                    return result.content if hasattr(result, 'content') else str(result)
            else:
                result = agent.run(task, context=context)
                return result.content if hasattr(result, 'content') else str(result)
        elif hasattr(agent, 'execute'):
            result = await agent.execute(task, context=context)
            return str(result)
        else:
            raise ValueError("Agent没有可执行的run或execute方法")
    
    def get_session(self, session_id: str) -> Optional[SubagentSession]:
        """获取会话"""
        return self._sessions.get(session_id)
    
    def get_child_sessions(self, parent_session_id: str) -> List[SubagentSession]:
        """获取子会话列表"""
        return [
            s for s in self._sessions.values()
            if s.parent_session_id == parent_session_id
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self._sessions)
        by_status = {}
        for session in self._sessions.values():
            status = session.status.value
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_sessions": total,
            "by_status": by_status,
            "registered_subagents": len(self._registry.list_all()),
        }

    # ========== 上下文隔离相关方法 ==========

    def set_context_isolation_manager(
        self,
        manager: "ContextIsolationManager",
    ) -> "SubagentManager":
        """
        设置上下文隔离管理器

        Args:
            manager: ContextIsolationManager 实例

        Returns:
            self: 支持链式调用
        """
        self._context_isolation_manager = manager
        return self

    def register_with_context(
        self,
        info: SubagentInfo,
        agent_class: Optional[Type] = None,
        factory: Optional[Callable] = None,
        context_config: Optional["SubagentContextConfig"] = None,
    ) -> None:
        """
        注册带上下文配置的子Agent

        Args:
            info: 子Agent信息
            agent_class: Agent类
            factory: Agent工厂函数
            context_config: 上下文隔离配置
        """
        # 存储上下文配置到 metadata
        if context_config:
            info.metadata = info.metadata or {}
            info.metadata["context_isolation_config"] = context_config.dict()

        self._registry.register(info, agent_class, factory)
        logger.info(f"[SubagentManager] Registered subagent with context config: {info.name}")

    async def delegate_with_isolation(
        self,
        subagent_name: str,
        task: str,
        parent_session_id: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        isolation_mode: Optional["ContextIsolationMode"] = None,
        context_config: Optional["SubagentContextConfig"] = None,
    ) -> SubagentResult:
        """
        使用上下文隔离委派任务给子Agent

        Args:
            subagent_name: 子Agent名称
            task: 任务内容
            parent_session_id: 父会话ID
            context: 上下文信息
            timeout: 超时时间（秒）
            isolation_mode: 隔离模式 (ISOLATED, SHARED, FORK)
            context_config: 完整的上下文配置

        Returns:
            SubagentResult: 执行结果
        """
        from .context_isolation import (
            ContextIsolationManager,
            ContextIsolationMode,
            SubagentContextConfig,
            ContextWindow,
        )

        # 如果没有提供隔离管理器，使用普通委派
        if not self._context_isolation_manager:
            logger.warning("ContextIsolationManager not set, using regular delegate")
            return await self.delegate(
                subagent_name=subagent_name,
                task=task,
                parent_session_id=parent_session_id,
                context=context,
                timeout=timeout,
                sync=True,
            )

        # 创建或使用提供的上下文配置
        if context_config is None:
            context_config = SubagentContextConfig(
                isolation_mode=isolation_mode or ContextIsolationMode.FORK,
            )

        # 创建父上下文窗口（如果有）
        parent_context_window = None
        if context and "context_window" in context:
            parent_context_window = context["context_window"]

        # 创建隔离上下文
        isolated_context = await self._context_isolation_manager.create_isolated_context(
            parent_context=parent_context_window,
            config=context_config,
        )

        # 委派任务
        result = await self.delegate(
            subagent_name=subagent_name,
            task=task,
            parent_session_id=parent_session_id,
            context={
                **(context or {}),
                "isolated_context_id": isolated_context.context_id,
            },
            timeout=timeout,
            sync=True,
        )

        # 合并结果回父上下文
        if context_config.memory_scope.propagate_up:
            merge_data = await self._context_isolation_manager.merge_context_back(
                isolated_context,
                {"output": result.output, "success": result.success},
            )
            # 可以将 merge_data 传递给父 Agent

        # 清理隔离上下文
        await self._context_isolation_manager.cleanup_context(isolated_context.context_id)

        return result

    def get_context_isolation_stats(self) -> Dict[str, Any]:
        """
        获取上下文隔离统计信息

        Returns:
            统计信息字典
        """
        if not self._context_isolation_manager:
            return {"enabled": False, "message": "ContextIsolationManager not configured"}

        return {
            "enabled": True,
            **self._context_isolation_manager.get_stats(),
        }

    async def create_isolated_subagent_context(
        self,
        parent_context: Optional["ContextWindow"],
        isolation_mode: "ContextIsolationMode",
        max_tokens: int = 32000,
    ) -> "IsolatedContext":
        """
        创建隔离的子Agent上下文

        这是一个便捷方法，用于在委派前创建上下文。

        Args:
            parent_context: 父Agent的上下文窗口
            isolation_mode: 隔离模式
            max_tokens: 最大token数

        Returns:
            创建的 IsolatedContext
        """
        from .context_isolation import (
            ContextIsolationManager,
            ContextIsolationMode,
            SubagentContextConfig,
        )

        if not self._context_isolation_manager:
            raise RuntimeError("ContextIsolationManager not configured")

        config = SubagentContextConfig(
            isolation_mode=isolation_mode,
            max_context_tokens=max_tokens,
        )

        return await self._context_isolation_manager.create_isolated_context(
            parent_context=parent_context,
            config=config,
        )


subagent_manager = SubagentRegistry()

DEFAULT_SUBAGENTS = [
    SubagentInfo(
        name="general",
        description="通用子Agent - 用于研究复杂问题和执行多步骤任务",
        capabilities=["research", "multi-step-tasks"],
        max_steps=15,
    ),
    SubagentInfo(
        name="explore",
        description="代码库探索Agent - 快速搜索文件和代码",
        capabilities=["code-search", "file-search", "codebase-exploration"],
        max_steps=10,
    ),
    SubagentInfo(
        name="code-reviewer",
        description="代码审查Agent - 检查代码质量和安全问题",
        capabilities=["code-review", "security-audit", "best-practices"],
        max_steps=10,
    ),
]


def register_default_subagents():
    """注册默认子Agent"""
    for info in DEFAULT_SUBAGENTS:
        subagent_manager.register(info)


register_default_subagents()