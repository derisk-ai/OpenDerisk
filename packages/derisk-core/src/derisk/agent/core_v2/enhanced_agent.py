"""
Enhanced Agent Module for Derisk Core_v2.

This module provides a complete agent implementation with:
1. AgentBase with think/decide/act pattern
2. SubagentManager for hierarchical delegation
3. TeamManager for Agent Teams coordination
4. AutoCompactionManager for automatic context management
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Set
import asyncio
import logging
import uuid

from derisk.core import LLMClient

from .improved_compaction import ImprovedSessionCompaction, CompactionConfig
from .llm_utils import call_llm, LLMCaller

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    """Agent状态"""

    IDLE = "idle"
    THINKING = "thinking"
    DECIDING = "deciding"
    ACTING = "acting"
    RESPONDING = "responding"
    WAITING = "waiting"
    ERROR = "error"
    TERMINATED = "terminated"


class DecisionType(str, Enum):
    """决策类型"""

    RESPONSE = "response"
    TOOL_CALL = "tool_call"
    SUBAGENT = "subagent"
    TEAM_TASK = "team_task"
    TERMINATE = "terminate"
    WAIT = "wait"
    CLARIFY = "clarify"


@dataclass
class Decision:
    """决策结果"""

    type: DecisionType
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    subagent_name: Optional[str] = None
    subagent_task: Optional[str] = None
    team_task: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    confidence: float = 1.0


@dataclass
class ActionResult:
    """执行结果"""

    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """Agent消息"""

    role: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AgentInfo:
    """Agent配置信息"""

    name: str
    description: str
    role: str = "assistant"

    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)

    max_steps: int = 50  # Increased from 10 to support long-running tasks like RCA
    timeout: int = 300

    model: str = "inherit"

    permission_ruleset: Optional[Dict[str, Any]] = None

    memory_enabled: bool = True
    memory_scope: str = "session"

    subagents: List[str] = field(default_factory=list)

    can_spawn_team: bool = False
    team_role: str = "worker"


class PermissionChecker:
    """权限检查器"""

    def __init__(self, ruleset: Optional[Dict[str, Any]] = None):
        self.ruleset = ruleset or {}

    async def check_async(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """检查权限"""
        rules = self.ruleset.get("rules", [])

        for rule in rules:
            pattern = rule.get("pattern", "")
            action = rule.get("action", "ask")

            if self._match_pattern(tool_name, pattern):
                if action == "allow":
                    return True
                elif action == "deny":
                    return False

        default = self.ruleset.get("default", "allow")
        return default == "allow"

    def _match_pattern(self, tool_name: str, pattern: str) -> bool:
        import fnmatch

        return fnmatch.fnmatch(tool_name, pattern)


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: Dict[str, Any] = {}

    def register(self, tool: Any) -> "ToolRegistry":
        # 优先使用 metadata.name，其次使用 name 属性
        if hasattr(tool, "metadata") and hasattr(tool.metadata, "name"):
            name = tool.metadata.name
        elif hasattr(tool, "name"):
            name = tool.name
        else:
            name = str(tool)
        self._tools[name] = tool
        logger.debug(f"[ToolRegistry] 注册工具: {name}")
        return self

    def get(self, name: str) -> Optional[Any]:
        return self._tools.get(name)

    async def execute(
        self, name: str, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> "ToolResult":
        """执行工具"""
        from .tools_v2 import ToolResult

        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, output="", error=f"工具不存在: {name}")

        try:
            if hasattr(tool, "execute"):
                result = await tool.execute(args, context)
                return result
            elif callable(tool):
                result = tool(**args)
                if hasattr(result, "__await__"):
                    result = await result
                if isinstance(result, ToolResult):
                    return result
                return ToolResult(
                    success=True,
                    output=str(result) if result else "",
                )
            else:
                return ToolResult(
                    success=False, output="", error=f"工具不可执行: {name}"
                )
        except Exception as e:
            logger.exception(f"[ToolRegistry] 工具执行异常: {name}")
            return ToolResult(success=False, output="", error=str(e))

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def list_all(self) -> List[Any]:
        """列出所有工具对象"""
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        result = []
        for name, tool in self._tools.items():
            if hasattr(tool, "get_openai_spec"):
                result.append(tool.get_openai_spec())
            else:
                result.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": getattr(tool, "description", ""),
                        },
                    }
                )
        return result


@dataclass
class SubagentSession:
    """子代理会话"""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subagent_name: str = ""
    task: str = ""
    parent_context: Optional[List[Dict]] = None
    context: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    output_chunks: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SubagentResult:
    """子代理结果"""

    success: bool
    output: str
    error: Optional[str] = None
    session_id: Optional[str] = None
    status: str = "completed"


class SubagentManager:
    """子代理管理器 - 借鉴Claude Code"""

    def __init__(
        self,
        memory: Optional[Any] = None,
    ):
        self.memory = memory
        self._agent_factory: Dict[str, Callable] = {}
        self._active_subagents: Dict[str, SubagentSession] = {}

    def register_agent_factory(
        self,
        name: str,
        factory: Callable,
    ):
        """注册代理工厂"""
        self._agent_factory[name] = factory

    async def delegate(
        self,
        subagent_name: str,
        task: str,
        parent_messages: Optional[List[Dict]] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        background: bool = False,
    ) -> SubagentResult:
        """委托任务给子代理"""
        if subagent_name not in self._agent_factory:
            raise ValueError(f"Subagent '{subagent_name}' not found")

        session = SubagentSession(
            subagent_name=subagent_name,
            task=task,
            parent_context=parent_messages,
            context=context or {},
        )

        self._active_subagents[session.session_id] = session

        try:
            factory = self._agent_factory[subagent_name]
            subagent = (
                await factory() if asyncio.iscoroutinefunction(factory) else factory()
            )

            if background:
                asyncio.create_task(self._run_subagent(session, subagent))
                return SubagentResult(
                    success=True,
                    output="",
                    session_id=session.session_id,
                    status="running",
                )
            else:
                if timeout:
                    result = await asyncio.wait_for(
                        self._run_subagent(session, subagent),
                        timeout=timeout,
                    )
                else:
                    result = await self._run_subagent(session, subagent)
                return result

        except asyncio.TimeoutError:
            return SubagentResult(
                success=False,
                output="",
                error="Timeout",
                session_id=session.session_id,
                status="timeout",
            )
        except Exception as e:
            return SubagentResult(
                success=False,
                output="",
                error=str(e),
                session_id=session.session_id,
                status="failed",
            )

    async def _run_subagent(
        self,
        session: SubagentSession,
        subagent: "AgentBase",
    ) -> SubagentResult:
        """运行子代理"""
        output_parts = []

        try:
            async for chunk in subagent.run(session.task):
                output_parts.append(chunk)
                session.output_chunks.append(chunk)

            session.status = "completed"
            return SubagentResult(
                success=True,
                output="".join(output_parts),
                session_id=session.session_id,
                status="completed",
            )
        except Exception as e:
            session.status = "failed"
            return SubagentResult(
                success=False,
                output="".join(output_parts),
                error=str(e),
                session_id=session.session_id,
                status="failed",
            )

    async def resume(self, session_id: str) -> SubagentResult:
        """恢复子代理会话"""
        session = self._active_subagents.get(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        # 继续执行...
        return SubagentResult(
            success=True,
            output="".join(session.output_chunks),
            session_id=session_id,
            status=session.status,
        )

    def get_available_subagents(self) -> List[str]:
        return list(self._agent_factory.keys())


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    """任务"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    assigned_to: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)
    result: Optional[Any] = None
    created_at: datetime = field(default_factory=datetime.now)


class TaskList:
    """任务列表"""

    def __init__(self):
        self._tasks: Dict[str, Task] = {}

    def add_task(self, task: Task) -> None:
        self._tasks[task.id] = task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def get_dependent_tasks(self, task_id: str) -> List[Task]:
        return [t for t in self._tasks.values() if task_id in t.dependencies]

    def get_pending_tasks(self) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]


class TeamManager:
    """团队管理器 - 借鉴Claude Code Agent Teams"""

    def __init__(
        self,
        coordinator: Optional["AgentBase"] = None,
        memory: Optional[Any] = None,
    ):
        self.coordinator = coordinator
        self.memory = memory

        self._workers: Dict[str, "AgentBase"] = {}
        self._task_list = TaskList()
        self._task_file_lock = asyncio.Lock()
        self._mailbox: Dict[str, asyncio.Queue] = {}

    def set_coordinator(self, coordinator: "AgentBase") -> None:
        self.coordinator = coordinator

    async def spawn_teammate(
        self,
        name: str,
        role: str,
        agent: "AgentBase",
    ) -> "AgentBase":
        """生成队友"""
        self._workers[name] = agent
        self._mailbox[name] = asyncio.Queue()
        return agent

    async def assign_task(self, task_config: Dict[str, Any]) -> ActionResult:
        """分配任务"""
        task = Task(
            description=task_config.get("description", ""),
            assigned_to=task_config.get("assigned_to"),
            dependencies=task_config.get("dependencies", []),
        )

        async with self._task_file_lock:
            self._task_list.add_task(task)

        return ActionResult(
            success=True,
            output=f"Task {task.id} created",
            metadata={"task_id": task.id},
        )

    async def broadcast(
        self,
        message: str,
        exclude: Optional[Set[str]] = None,
    ):
        """广播消息给所有队友"""
        exclude = exclude or set()
        for name, queue in self._mailbox.items():
            if name not in exclude:
                await queue.put(
                    {
                        "type": "broadcast",
                        "from": "coordinator",
                        "content": message,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    async def direct_message(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
    ):
        """直接消息"""
        if to_agent not in self._mailbox:
            raise ValueError(f"Unknown agent: {to_agent}")

        await self._mailbox[to_agent].put(
            {
                "type": "direct",
                "from": from_agent,
                "content": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def claim_task(
        self,
        agent_name: str,
        task_id: str,
    ) -> bool:
        """认领任务"""
        async with self._task_file_lock:
            task = self._task_list.get_task(task_id)
            if not task or task.status != TaskStatus.PENDING:
                return False

            for dep_id in task.dependencies:
                dep = self._task_list.get_task(dep_id)
                if dep and dep.status != TaskStatus.COMPLETED:
                    task.status = TaskStatus.BLOCKED
                    return False

            task.status = TaskStatus.IN_PROGRESS
            task.assigned_to = agent_name
            return True

    async def complete_task(
        self,
        agent_name: str,
        task_id: str,
        result: Any,
    ):
        """完成任务"""
        async with self._task_file_lock:
            task = self._task_list.get_task(task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.result = result

                for dependent in self._task_list.get_dependent_tasks(task_id):
                    if dependent.assigned_to and dependent.status == TaskStatus.BLOCKED:
                        all_deps_done = all(
                            self._task_list.get_task(d).status == TaskStatus.COMPLETED
                            for d in dependent.dependencies
                            if self._task_list.get_task(d)
                        )
                        if all_deps_done:
                            dependent.status = TaskStatus.PENDING
                            await self.direct_message(
                                "system",
                                dependent.assigned_to,
                                f"Dependency {task_id} completed. Task is now available.",
                            )

    async def cleanup(self):
        """清理团队资源"""
        for name, agent in self._workers.items():
            if hasattr(agent, "shutdown"):
                await agent.shutdown()

        self._workers.clear()
        self._mailbox.clear()
        self._task_list = TaskList()


class AutoCompactionManager:
    """自动压缩管理器"""

    def __init__(
        self,
        compaction: ImprovedSessionCompaction,
        memory: Optional[Any] = None,
        trigger: str = "threshold",
    ):
        self.compaction = compaction
        self.memory = memory
        self.trigger = trigger

        self._message_count = 0
        self._last_compaction_tokens = 0

    async def check_and_compact(
        self,
        messages: List[AgentMessage],
        force: bool = False,
    ):
        """检查并执行压缩"""
        if self.trigger == "threshold":
            return await self._threshold_compact(messages, force)
        elif self.trigger == "adaptive":
            return await self._adaptive_compact(messages, force)

        return None

    async def _threshold_compact(
        self,
        messages: List[AgentMessage],
        force: bool,
    ):
        """阈值触发压缩"""
        return await self.compaction.compact(
            [self._convert_message(m) for m in messages],
            force=force,
        )

    async def _adaptive_compact(
        self,
        messages: List[AgentMessage],
        force: bool,
    ):
        """自适应触发压缩"""
        self._message_count += 1
        config = CompactionConfig()

        if self._message_count % config.ADAPTIVE_CHECK_INTERVAL != 0:
            return None

        from derisk.agent import AgentMessage as DAgentMessage

        converted = [self._convert_message(m) for m in messages]

        should, reason = self.compaction.should_compact_adaptive(converted)

        if should or force:
            result = await self.compaction.compact(converted, force=force)
            if result.success:
                self._last_compaction_tokens = (
                    self.compaction.token_estimator.estimate_messages(
                        result.compacted_messages
                    ).total_tokens
                )
            return result

        return None

    def _convert_message(self, msg: AgentMessage) -> "DAgentMessage":
        """转换消息格式"""
        from derisk.agent import AgentMessage as DAgentMessage

        converted = DAgentMessage(
            content=msg.content,
            role=msg.role,
        )
        converted.context = msg.metadata
        if msg.metadata and msg.metadata.get("tool_calls"):
            converted.tool_calls = msg.metadata["tool_calls"]
        return converted


class AgentBase(ABC):
    """Agent基类 - think/decide/act三阶段"""

    def __init__(
        self,
        info: AgentInfo,
        memory: Optional[Any] = None,
        tools: Optional[ToolRegistry] = None,
        permission_checker: Optional[PermissionChecker] = None,
        llm_client: Optional[Any] = None,
    ):
        self.info = info
        self.memory = memory
        self.tools = tools or ToolRegistry()
        self.permission_checker = permission_checker or PermissionChecker()
        self.llm_client = llm_client
        self._llm_caller: Optional[LLMCaller] = None

        self._state = AgentState.IDLE
        self._current_step = 0
        self._messages: List[AgentMessage] = []
        self._context: Optional[Any] = None

        self._subagent_manager: Optional[SubagentManager] = None
        self._team_manager: Optional[TeamManager] = None
        self._auto_compaction: Optional[AutoCompactionManager] = None

    async def initialize(self, context: Optional[Any] = None) -> None:
        """
        初始化Agent运行时状态

        Args:
            context: 运行时上下文，包含session_id, conv_id, user_id等信息
        """
        self._context = context
        self._current_step = 0
        self._state = AgentState.IDLE

        # 初始化memory（如果有initialize方法）
        if self.memory and hasattr(self.memory, "initialize"):
            try:
                await self.memory.initialize()
            except Exception as e:
                logger.warning(f"[AgentBase] Memory initialization failed: {e}")

    def set_llm_client(self, llm_client: Any) -> None:
        """设置 LLM 客户端或 LLMConfig"""
        self.llm_client = llm_client
        self._llm_caller = LLMCaller(llm_client) if llm_client else None

    def get_llm_caller(self) -> Optional[LLMCaller]:
        """获取 LLM 调用器"""
        if not self._llm_caller and self.llm_client:
            self._llm_caller = LLMCaller(self.llm_client)
        return self._llm_caller

    def set_subagent_manager(self, manager: SubagentManager) -> None:
        self._subagent_manager = manager

    def set_team_manager(self, manager: TeamManager) -> None:
        self._team_manager = manager

    def setup_auto_compaction(
        self,
        context_window: int = 128000,
        threshold_ratio: float = 0.80,
    ) -> None:
        """设置自动压缩"""
        compaction = ImprovedSessionCompaction(
            context_window=context_window,
            threshold_ratio=threshold_ratio,
            llm_client=self.llm_client,
            shared_memory_loader=self._load_shared_memory if self.memory else None,
        )
        self._auto_compaction = AutoCompactionManager(
            compaction=compaction,
            memory=self.memory,
        )

    async def _load_shared_memory(self) -> str:
        """加载共享记忆"""
        if not self.memory:
            return ""

        from .unified_memory import MemoryType

        items = await self.memory.read(
            query="",
            options=None,
        )
        return "\n\n".join(
            [item.content for item in items if item.memory_type == MemoryType.SHARED]
        )

    @abstractmethod
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """思考阶段 - 流式输出"""
        pass

    @abstractmethod
    async def decide(self, context: Dict[str, Any], **kwargs) -> Decision:
        """决策阶段"""
        pass

    @abstractmethod
    async def act(self, decision: Decision, **kwargs) -> ActionResult:
        """执行阶段"""
        pass

    async def _get_worklog_tool_messages(
        self, max_entries: int = 30
    ) -> List[Dict[str, Any]]:
        """
        将 WorkLog 历史转换为原生 Function Call 格式的工具消息列表。

        子类可以重写此方法来提供具体的 WorkLog 转换逻辑。
        例如 ReActReasoningAgent 可以从 compaction_pipeline 获取历史工具调用记录。

        Returns:
            符合原生 Function Call 格式的消息列表:
            [
                {"role": "assistant", "content": "", "tool_calls": [...]},
                {"role": "tool", "tool_call_id": "...", "content": "..."},
                ...
            ]
        """
        return []

    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """主执行循环 - 支持四层压缩架构"""
        # Layer 4: 启动新的对话轮次
        await self._start_conversation_round(message)

        self._state = AgentState.THINKING
        self._current_step = 0
        self.add_message("user", message)

        final_response = ""

        while self._current_step < self.info.max_steps:
            try:
                thinking_output = []
                if stream:
                    async for chunk in self.think(message):
                        thinking_output.append(chunk)
                        yield f"[THINKING] {chunk}"

                self._state = AgentState.DECIDING
                context = {
                    "message": message,
                    "thinking": "".join(thinking_output),
                    "history": [m.to_dict() for m in self._messages],
                }
                decision = await self.decide(context)

                if decision.type == DecisionType.RESPONSE:
                    self._state = AgentState.RESPONDING
                    if decision.content:
                        final_response = decision.content
                        yield decision.content
                        self.add_message("assistant", decision.content)
                    break

                elif decision.type == DecisionType.TOOL_CALL:
                    self._state = AgentState.ACTING

                    # 获取 tool_call_id（如果有）
                    tool_call_id = None
                    if (
                        hasattr(self, "_last_llm_response")
                        and self._last_llm_response
                        and self._last_llm_response.tool_calls
                    ):
                        tool_call_id = self._last_llm_response.tool_calls[0].get(
                            "id", f"call_{decision.tool_name}"
                        )

                    # 先添加助手消息（包含工具调用意图）
                    assistant_msg_content = decision.content or ""
                    tool_calls_data = None
                    if (
                        hasattr(self, "_last_llm_response")
                        and self._last_llm_response
                        and self._last_llm_response.tool_calls
                    ):
                        tool_calls_data = self._last_llm_response.tool_calls

                    self.add_message(
                        "assistant",
                        assistant_msg_content,
                        {
                            "tool_name": decision.tool_name,
                            "tool_calls": tool_calls_data,
                        },
                    )

                    # 执行工具
                    result = await self.act(decision)

                    # 添加工具结果消息（使用 tool 角色）
                    tool_output = (
                        result.output or f"工具执行完成。错误: {result.error or '无'}"
                    )
                    self.add_message(
                        "tool",
                        tool_output,
                        {
                            "tool_name": decision.tool_name,
                            "tool_call_id": tool_call_id,
                            "success": result.success,
                        },
                    )
                    logger.info(
                        f"[AgentBase] 工具执行完成: {decision.tool_name}, 成功={result.success}, 输出长度={len(tool_output)}"
                    )

                    yield f"\n[TOOL: {decision.tool_name}]\n{tool_output}"
                    message = tool_output

                elif decision.type == DecisionType.SUBAGENT:
                    self._state = AgentState.ACTING
                    result = await self._delegate_to_subagent(decision)
                    yield f"\n[SUBAGENT: {decision.subagent_name}]\n{result.output}"
                    message = result.output

                elif decision.type == DecisionType.TEAM_TASK:
                    self._state = AgentState.ACTING
                    result = await self._assign_team_task(decision)
                    yield f"\n[TEAM TASK]\n{result.output}"
                    message = result.output

                elif decision.type == DecisionType.TERMINATE:
                    break

                self._current_step += 1

                if self._auto_compaction:
                    await self._auto_compaction.check_and_compact(self._messages)

            except Exception as e:
                self._state = AgentState.ERROR
                yield f"\n[ERROR] {str(e)}"
                break

        # Layer 4: 完成对话轮次
        await self._complete_conversation_round(final_response)

        self._state = AgentState.IDLE

    def add_message(
        self, role: str, content: str, metadata: Optional[Dict] = None
    ) -> None:
        self._messages.append(
            AgentMessage(
                role=role,
                content=content,
                metadata=metadata or {},
            )
        )

    async def _delegate_to_subagent(self, decision: Decision) -> ActionResult:
        """委托给子代理"""
        if not self._subagent_manager:
            return ActionResult(
                success=False,
                output="",
                error="No subagent manager configured",
            )

        result = await self._subagent_manager.delegate(
            subagent_name=decision.subagent_name,
            task=decision.subagent_task,
            parent_messages=[m.to_dict() for m in self._messages],
        )

        return ActionResult(
            success=result.success,
            output=result.output,
            error=result.error,
            metadata={
                "subagent": decision.subagent_name,
                "session_id": result.session_id,
            },
        )

    async def _assign_team_task(self, decision: Decision) -> ActionResult:
        """分配团队任务"""
        if not self._team_manager:
            return ActionResult(
                success=False,
                output="",
                error="No team manager configured",
            )

        result = await self._team_manager.assign_task(decision.team_task or {})
        return result

    async def shutdown(self) -> None:
        """关闭Agent"""
        if self._team_manager:
            await self._team_manager.cleanup()

        self._state = AgentState.TERMINATED


class ProductionAgent(AgentBase):
    """生产环境Agent实现"""

    def __init__(
        self,
        info: AgentInfo,
        llm_client: Optional[Any] = None,
        llm_adapter: Optional[Any] = None,  # alias for llm_client
        tool_registry: Optional[ToolRegistry] = None,
        memory: Optional[Any] = None,
        use_persistent_memory: bool = False,
        **kwargs,
    ):
        # llm_adapter is an alias for llm_client (used by BaseBuiltinAgent)
        if llm_adapter is not None and llm_client is None:
            llm_client = llm_adapter

        # Extract parameters that AgentBase accepts
        base_kwargs = {}
        if tool_registry is not None:
            base_kwargs["tools"] = tool_registry

        # Pass memory to parent if provided
        if memory is not None:
            base_kwargs["memory"] = memory

        super().__init__(info, llm_client=llm_client, **base_kwargs)

    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """思考 - 调用LLM"""
        if not self.llm_client:
            yield "No LLM client configured"
            return

        llm_caller = self.get_llm_caller()
        if llm_caller:
            content = await llm_caller.call(message)
            if content:
                yield content
            else:
                yield "LLM returned empty response"
        else:
            yield "Failed to create LLM caller"

    async def decide(self, context: Dict[str, Any], **kwargs) -> Decision:
        """决策 - 解析LLM输出"""
        thinking = context.get("thinking", "")

        if thinking:
            decision = self._parse_decision_from_thinking(thinking)
            if decision:
                return decision

        return Decision(
            type=DecisionType.RESPONSE,
            content=thinking,
            confidence=0.8,
        )

    async def act(self, decision: Decision, **kwargs) -> ActionResult:
        """执行动作"""
        if decision.type != DecisionType.TOOL_CALL:
            return ActionResult(
                success=False,
                output="",
                error="Invalid decision type for action",
            )

        if not self.tools:
            return ActionResult(
                success=False,
                output="",
                error="No tools registered",
            )

        permission = await self.permission_checker.check_async(
            tool_name=decision.tool_name,
            tool_args=decision.tool_args,
        )

        if not permission:
            return ActionResult(
                success=False,
                output="",
                error="Permission denied",
            )

        tool = self.tools.get(decision.tool_name)
        if not tool:
            return ActionResult(
                success=False,
                output="",
                error=f"Tool '{decision.tool_name}' not found",
            )

        try:
            if hasattr(tool, "execute"):
                result = await tool.execute(decision.tool_args or {})
            elif callable(tool):
                result = tool(**(decision.tool_args or {}))
            else:
                result = str(tool)

            return ActionResult(
                success=True,
                output=str(result),
            )
        except Exception as e:
            return ActionResult(
                success=False,
                output="",
                error=str(e),
            )

    def _build_llm_messages(self) -> List:
        """构建LLM消息列表"""
        from derisk.core import SystemMessage, HumanMessage, AIMessage

        messages = [
            SystemMessage(content=f"You are {self.info.role}. {self.info.description}"),
        ]

        for msg in self._messages:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                tool_calls = msg.metadata.get("tool_calls") if msg.metadata else None
                if tool_calls:
                    # Assistant message with tool calls — preserve for OpenAI pairing
                    messages.append(
                        {
                            "role": "assistant",
                            "content": msg.content or "",
                            "tool_calls": tool_calls,
                        }
                    )
                else:
                    messages.append(AIMessage(content=msg.content))
            elif msg.role == "tool":
                # Tool result message — preserve tool_call_id for OpenAI pairing
                tool_call_id = (
                    msg.metadata.get("tool_call_id", "") if msg.metadata else ""
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": msg.content or "",
                        "tool_call_id": tool_call_id,
                    }
                )
            else:
                messages.append(SystemMessage(content=msg.content))

        if self.tools.list_tools():
            tools_desc = "Available tools: " + ", ".join(self.tools.list_tools())
            messages.append(SystemMessage(content=tools_desc))

        return messages

    def _parse_decision_from_thinking(self, thinking: str) -> Optional[Decision]:
        """从思考内容解析决策"""
        import json
        import re

        json_pattern = r'\{[^{}]*"type"[^{}]*\}'
        matches = re.findall(json_pattern, thinking)

        for match in matches:
            try:
                data = json.loads(match)
                if "type" in data:
                    return Decision(
                        type=DecisionType(data["type"]),
                        content=data.get("content"),
                        tool_name=data.get("tool_name"),
                        tool_args=data.get("tool_args"),
                        subagent_name=data.get("subagent_name"),
                        subagent_task=data.get("subagent_task"),
                    )
            except json.JSONDecodeError:
                continue

        return None

    # ========== Layer 4: Multi-Turn History Support ==========

    async def _start_conversation_round(self, user_question: str):
        """启动新的对话轮次（Layer 4）"""
        try:
            if hasattr(self, "start_conversation_round"):
                await self.start_conversation_round(user_question)
        except Exception as e:
            logger.debug(f"Layer 4: Failed to start conversation round: {e}")

    async def _complete_conversation_round(self, ai_response: str):
        """完成对话轮次（Layer 4）"""
        try:
            if hasattr(self, "complete_conversation_round"):
                await self.complete_conversation_round(ai_response)
        except Exception as e:
            logger.debug(f"Layer 4: Failed to complete conversation round: {e}")
