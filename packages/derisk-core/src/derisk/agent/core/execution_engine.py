"""Simplified Agent Execution Engine - Inspired by opencode/openclaw patterns.

Enhanced with Context Lifecycle Management for Skill and Tool active exit mechanism.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    Generic,
    TypeVar,
    TYPE_CHECKING,
)

from derisk._private.pydantic import BaseModel, Field
from derisk.util.tracer import root_tracer

if TYPE_CHECKING:
    from derisk.agent.core.context_lifecycle import (
        ContextLifecycleOrchestrator,
        ExitTrigger,
    )

T = TypeVar("T")
logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Execution status for agent loops."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_INPUT = "needs_input"
    TERMINATED = "terminated"


@dataclass
class ExecutionStep:
    """A single step in agent execution."""

    step_id: str
    step_type: str
    content: Any
    status: ExecutionStatus = ExecutionStatus.PENDING
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complete(self, result: Any = None):
        """Mark step as complete."""
        self.status = ExecutionStatus.SUCCESS
        self.end_time = time.time()
        if result is not None:
            self.content = result

    def fail(self, error: str):
        """Mark step as failed."""
        self.status = ExecutionStatus.FAILED
        self.end_time = time.time()
        self.error = error


@dataclass
class ExecutionResult:
    """Result of agent execution loop."""

    steps: List[ExecutionStep] = field(default_factory=list)
    final_content: Any = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    total_tokens: int = 0
    total_time_ms: int = 0

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def add_step(self, step: ExecutionStep) -> ExecutionStep:
        self.steps.append(step)
        return step


class ExecutionHooks:
    """
    Hooks for agent execution lifecycle.
    Inspired by openclaw event system.
    """

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = {
            "before_thinking": [],
            "after_thinking": [],
            "before_action": [],
            "after_action": [],
            "before_step": [],
            "after_step": [],
            "on_error": [],
            "on_complete": [],
            "before_skill_load": [],
            "after_skill_complete": [],
            "on_context_pressure": [],
        }

    def on(self, event: str, handler: Callable) -> "ExecutionHooks":
        """Register a hook for an event."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(handler)
        return self

    async def emit(self, event: str, *args, **kwargs) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._hooks.get(event, []):
            try:
                result = handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Hook handler error for {event}: {e}")


class ExecutionEngine(Generic[T]):
    """
    Simplified execution engine for agents.

    Inspired by opencode's simple loop pattern:
    - Clear start/end boundaries
    - Maximum iteration control
    - Early termination support
    - Progress tracking
    - Context lifecycle management (enhanced)
    """

    def __init__(
        self,
        max_steps: int = 10,
        timeout_seconds: Optional[float] = None,
        hooks: Optional[ExecutionHooks] = None,
        context_lifecycle: Optional["ContextLifecycleOrchestrator"] = None,
    ):
        self.max_steps = max_steps
        self.timeout_seconds = timeout_seconds
        self.hooks = hooks or ExecutionHooks()
        self._context_lifecycle = context_lifecycle
        
        self._current_skill: Optional[str] = None
        self._skill_start_time: Optional[float] = None

    @property
    def context_lifecycle(self) -> Optional["ContextLifecycleOrchestrator"]:
        """Get context lifecycle manager."""
        return self._context_lifecycle
    
    def set_context_lifecycle(
        self, 
        context_lifecycle: "ContextLifecycleOrchestrator"
    ) -> "ExecutionEngine":
        """Set context lifecycle manager."""
        self._context_lifecycle = context_lifecycle
        return self
    
    async def prepare_skill(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
    ) -> bool:
        """
        Prepare skill execution context.
        
        Loads skill content and required tools into context.
        """
        if not self._context_lifecycle:
            return False
        
        await self.hooks.emit("before_skill_load", skill_name)
        
        try:
            await self._context_lifecycle.prepare_skill_context(
                skill_name=skill_name,
                skill_content=skill_content,
                required_tools=required_tools,
            )
            
            self._current_skill = skill_name
            self._skill_start_time = time.time()
            
            logger.info(f"[ExecutionEngine] Prepared skill: {skill_name}")
            return True
            
        except Exception as e:
            logger.error(f"[ExecutionEngine] Failed to prepare skill {skill_name}: {e}")
            return False
    
    async def complete_skill(
        self,
        summary: str,
        key_outputs: Optional[List[str]] = None,
        trigger: Optional["ExitTrigger"] = None,
    ) -> Optional[Any]:
        """
        Complete current skill and exit from context.
        
        Removes skill detailed content while keeping summary.
        """
        if not self._context_lifecycle or not self._current_skill:
            return None
        
        from derisk.agent.core.context_lifecycle import ExitTrigger
        
        skill_name = self._current_skill
        self._current_skill = None
        
        try:
            result = await self._context_lifecycle.complete_skill(
                skill_name=skill_name,
                task_summary=summary,
                key_outputs=key_outputs,
                trigger=trigger or ExitTrigger.TASK_COMPLETE,
            )
            
            await self.hooks.emit("after_skill_complete", skill_name, result)
            
            logger.info(
                f"[ExecutionEngine] Completed skill: {skill_name}, "
                f"tokens freed: {result.tokens_freed}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[ExecutionEngine] Failed to complete skill {skill_name}: {e}")
            return None
    
    async def check_context_pressure(self) -> Optional[Dict[str, Any]]:
        """
        Check context pressure and handle if needed.
        
        Returns pressure info if pressure is high.
        """
        if not self._context_lifecycle:
            return None
        
        pressure = self._context_lifecycle.check_context_pressure()
        
        if pressure > 0.8:
            await self.hooks.emit("on_context_pressure", pressure)
            result = await self._context_lifecycle.handle_context_pressure()
            logger.warning(
                f"[ExecutionEngine] Context pressure {pressure:.2%}, "
                f"actions: {result['actions_taken']}"
            )
            return result
        
        return None

    async def execute(
        self,
        initial_input: Any,
        think_func: Callable[[Any], T],
        act_func: Callable[[T], Any],
        verify_func: Optional[Callable[[Any], Tuple[bool, Optional[str]]]] = None,
        should_terminate: Optional[Callable[[Any], bool]] = None,
    ) -> ExecutionResult:
        """
        Execute the agent loop.

        Args:
            initial_input: Starting input
            think_func: Async function to call LLM/thinking
            act_func: Async function to execute actions
            verify_func: Optional function to verify results
            should_terminate: Optional function to check early termination
        """
        result = ExecutionResult()
        current_input = initial_input
        step_count = 0
        start_time = time.time()

        try:
            await self.hooks.emit("before_step", step_count, current_input)

            while step_count < self.max_steps:
                step_id = uuid.uuid4().hex[:8]

                with root_tracer.start_span(
                    f"engine.execute.step.{step_count}", metadata={"step_id": step_id}
                ):
                    thinking_step = ExecutionStep(
                        step_id=step_id,
                        step_type="thinking",
                        content=None,
                    )
                    result.add_step(thinking_step)

                    await self.hooks.emit("before_thinking", step_count, current_input)

                    thinking_result = await think_func(current_input)
                    thinking_step.complete(thinking_result)

                    await self.hooks.emit("after_thinking", step_count, thinking_result)

                    action_step = ExecutionStep(
                        step_id=f"{step_id}_action",
                        step_type="action",
                        content=None,
                    )
                    result.add_step(action_step)

                    await self.hooks.emit("before_action", step_count, thinking_result)

                    action_result = await act_func(thinking_result)
                    action_step.complete(action_result)

                    await self.hooks.emit("after_action", step_count, action_result)

                    if verify_func:
                        passed, reason = await verify_func(action_result)
                        if not passed:
                            current_input = action_result
                            step_count += 1
                            continue

                    if should_terminate and should_terminate(action_result):
                        result.status = ExecutionStatus.TERMINATED
                        result.final_content = action_result
                        break

                    step_count += 1
                    await self.hooks.emit("after_step", step_count, action_result)

                    result.final_content = action_result
                    result.status = ExecutionStatus.SUCCESS

            if step_count >= self.max_steps:
                result.status = ExecutionStatus.FAILED

        except Exception as e:
            result.status = ExecutionStatus.FAILED
            await self.hooks.emit("on_error", e)
            raise

        finally:
            result.total_time_ms = int((time.time() - start_time) * 1000)
            await self.hooks.emit("on_complete", result)

        return result


class AgentExecutor:
    """
    Agent executor that wraps an agent with execution engine.

    This provides a simplified interface for running agents
    while maintaining compatibility with existing code.
    Enhanced with context lifecycle management.
    """

    def __init__(
        self,
        agent,
        max_steps: int = 10,
        hooks: Optional[ExecutionHooks] = None,
        context_lifecycle: Optional["ContextLifecycleOrchestrator"] = None,
    ):
        self.agent = agent
        self.engine = ExecutionEngine(
            max_steps=max_steps, 
            hooks=hooks,
            context_lifecycle=context_lifecycle,
        )
        
    @property
    def context_lifecycle(self) -> Optional["ContextLifecycleOrchestrator"]:
        """Get context lifecycle manager."""
        return self.engine.context_lifecycle
    
    def set_context_lifecycle(
        self, 
        context_lifecycle: "ContextLifecycleOrchestrator"
    ) -> "AgentExecutor":
        """Set context lifecycle manager."""
        self.engine.set_context_lifecycle(context_lifecycle)
        return self

    async def run(self, message, sender=None, **kwargs) -> ExecutionResult:
        """
        Run the agent with simplified execution.
        """

        async def think_func(input_msg):
            return await self.agent.thinking(input_msg, **kwargs)

        async def act_func(thinking_result):
            return await self.agent.act(thinking_result, sender=sender, **kwargs)

        async def verify_func(action_result):
            return await self.agent.verify(action_result, sender=sender, **kwargs)

        return await self.engine.execute(
            initial_input=message,
            think_func=think_func,
            act_func=act_func,
            verify_func=verify_func,
        )
    
    async def prepare_skill(
        self,
        skill_name: str,
        skill_content: str,
        required_tools: Optional[List[str]] = None,
    ) -> bool:
        """Prepare skill execution context."""
        return await self.engine.prepare_skill(skill_name, skill_content, required_tools)
    
    async def complete_skill(
        self,
        summary: str,
        key_outputs: Optional[List[str]] = None,
    ) -> Optional[Any]:
        """Complete current skill and exit from context."""
        return await self.engine.complete_skill(summary, key_outputs)


class ToolExecutor:
    """
    Tool execution with permission checks.

    Inspired by opencode's permission-first design.
    """

    def __init__(self, permission_ruleset=None):
        self.permission_ruleset = permission_ruleset
        self._tools: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable) -> "ToolExecutor":
        """Register a tool function."""
        self._tools[name] = func
        return self

    async def execute(self, tool_name: str, *args, **kwargs) -> Tuple[bool, Any]:
        """
        Execute a tool with permission check.

        Returns:
            Tuple of (success, result)
        """
        if self.permission_ruleset:
            action = self.permission_ruleset.check(tool_name)

            from .agent_info import PermissionAction

            if action == PermissionAction.DENY:
                return False, f"Tool '{tool_name}' is denied by permission rules"

            if action == PermissionAction.ASK:
                needs_approval = kwargs.pop("needs_approval", None)
                if needs_approval is None:
                    return False, f"Tool '{tool_name}' requires approval"

                if not needs_approval():
                    return False, f"Tool '{tool_name}' was not approved"

        if tool_name not in self._tools:
            return False, f"Tool '{tool_name}' not found"

        try:
            result = self._tools[tool_name](*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return True, result
        except Exception as e:
            return False, str(e)


class SessionManager:
    """
    Session management inspired by openclaw.

    Manages agent sessions with proper isolation and state.
    """

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self, session_id: str, agent_id: str, metadata: Optional[Dict] = None
    ) -> str:
        """Create a new session."""
        async with self._lock:
            self._sessions[session_id] = {
                "agent_id": agent_id,
                "created_at": datetime.now().isoformat(),
                "metadata": metadata or {},
                "state": {},
                "history": [],
            }
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID."""
        return self._sessions.get(session_id)

    async def update_state(self, session_id: str, state: Dict) -> None:
        """Update session state."""
        if session_id in self._sessions:
            self._sessions[session_id]["state"].update(state)

    async def add_history(self, session_id: str, entry: Any) -> None:
        """Add entry to session history."""
        if session_id in self._sessions:
            self._sessions[session_id]["history"].append(entry)

    async def end_session(self, session_id: str) -> None:
        """End a session."""
        if session_id in self._sessions:
            self._sessions[session_id]["ended_at"] = datetime.now().isoformat()


class ToolRegistry:
    """
    Registry for tools with lazy loading.
    """

    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, Type] = {}

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    @classmethod
    def register(cls, name: str, tool_cls: Type) -> None:
        """Register a tool class."""
        cls._tools[name] = tool_cls

    @classmethod
    def get(cls, name: str) -> Optional[Type]:
        """Get a tool class by name."""
        return cls._tools.get(name)

    @classmethod
    def list(cls) -> List[str]:
        """List all registered tools."""
        return list(cls._tools.keys())


def tool(name: str = None, description: str = ""):
    """
    Decorator to register a function as a tool.

    Usage:
        @tool("search")
        async def search_tool(query: str) -> str:
            return "result"
    """

    def decorator(func):
        tool_name = name or func.__name__
        ToolRegistry.register(tool_name, func)
        func._tool_name = tool_name
        func._tool_description = description
        return func

    if callable(name):
        func = name
        name = func.__name__
        return decorator(func)

    return decorator
