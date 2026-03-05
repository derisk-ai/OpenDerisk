"""
Agent Base - Unified Tool Authorization System

This module implements the core agent base class:
- AgentState: Agent execution state enum
- AgentBase: Abstract base class for all agents

All agents must inherit from AgentBase and implement:
- think(): Analyze and generate thought process
- decide(): Decide on next action
- act(): Execute the decision

Version: 2.0
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator, List, Callable, Awaitable
from enum import Enum
import asyncio
import logging
import time
import uuid

from .info import AgentInfo, AgentCapability
from ..tools.base import ToolRegistry, ToolResult, tool_registry
from ..tools.metadata import ToolMetadata
from ..authorization.engine import (
    AuthorizationEngine,
    AuthorizationContext,
    AuthorizationResult,
    get_authorization_engine,
)
from ..authorization.model import AuthorizationConfig
from ..interaction.gateway import InteractionGateway, get_interaction_gateway
from ..interaction.protocol import (
    InteractionRequest,
    InteractionResponse,
    create_authorization_request,
    create_text_input_request,
    create_confirmation_request,
    create_selection_request,
    create_notification,
)

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    """Agent execution states."""
    IDLE = "idle"             # Agent is idle, not running
    RUNNING = "running"       # Agent is actively processing
    WAITING = "waiting"       # Agent is waiting for user input or external response
    COMPLETED = "completed"   # Agent has completed its task
    FAILED = "failed"         # Agent encountered an error


class AgentBase(ABC):
    """
    Abstract base class for all agents.
    
    Provides unified interface for:
    - Tool execution with authorization
    - User interaction
    - Think-Decide-Act loop
    
    All agents must implement:
    - think(): Generate thought process (streaming)
    - decide(): Make a decision about next action
    - act(): Execute the decision
    
    Example:
        class MyAgent(AgentBase):
            async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
                yield "Thinking about: " + message
                
            async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
                return {"type": "response", "content": "Hello!"}
                
            async def act(self, action: Dict[str, Any], **kwargs) -> Any:
                return action.get("content")
    """
    
    def __init__(
        self,
        info: AgentInfo,
        tool_registry: Optional[ToolRegistry] = None,
        auth_engine: Optional[AuthorizationEngine] = None,
        interaction_gateway: Optional[InteractionGateway] = None,
    ):
        """
        Initialize the agent.
        
        Args:
            info: Agent configuration
            tool_registry: Tool registry to use (uses global if not provided)
            auth_engine: Authorization engine (uses global if not provided)
            interaction_gateway: Interaction gateway (uses global if not provided)
        """
        self.info = info
        self.tools = tool_registry or tool_registry
        self.auth_engine = auth_engine or get_authorization_engine()
        self.interaction = interaction_gateway or get_interaction_gateway()
        
        # Internal state
        self._state = AgentState.IDLE
        self._session_id: Optional[str] = None
        self._current_step = 0
        self._start_time: Optional[float] = None
        
        # Execution history
        self._history: List[Dict[str, Any]] = []
        
        # Messages (for LLM context)
        self._messages: List[Dict[str, Any]] = []
    
    # ========== Properties ==========
    
    @property
    def state(self) -> AgentState:
        """Get current agent state."""
        return self._state
    
    @property
    def session_id(self) -> Optional[str]:
        """Get current session ID."""
        return self._session_id
    
    @property
    def current_step(self) -> int:
        """Get current execution step number."""
        return self._current_step
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since run started (in seconds)."""
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time
    
    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self._state in (AgentState.RUNNING, AgentState.WAITING)
    
    @property
    def history(self) -> List[Dict[str, Any]]:
        """Get execution history."""
        return self._history.copy()
    
    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Get LLM message history."""
        return self._messages.copy()
    
    # ========== Abstract Methods ==========
    
    @abstractmethod
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """
        Thinking phase.
        
        Analyze the problem and generate thinking process (streaming).
        This is where the agent reasons about the task.
        
        Args:
            message: Input message or context
            **kwargs: Additional arguments
            
        Yields:
            Chunks of thinking text (for streaming output)
        """
        pass
    
    @abstractmethod
    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """
        Decision phase.
        
        Decide on the next action based on thinking.
        
        Args:
            message: Input message or context
            **kwargs: Additional arguments
            
        Returns:
            Decision dict with at least "type" key:
            - {"type": "response", "content": "..."} - Direct response to user
            - {"type": "tool_call", "tool": "...", "arguments": {...}} - Call a tool
            - {"type": "complete"} - Task is complete
            - {"type": "error", "error": "..."} - An error occurred
        """
        pass
    
    @abstractmethod
    async def act(self, action: Dict[str, Any], **kwargs) -> Any:
        """
        Action phase.
        
        Execute the decision (e.g., call a tool).
        
        Args:
            action: Decision from decide()
            **kwargs: Additional arguments
            
        Returns:
            Result of the action
        """
        pass
    
    # ========== Tool Execution ==========
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Execute a tool with full authorization check.
        
        Flow:
        1. Get tool from registry
        2. Check authorization
        3. Execute tool
        4. Return result
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            context: Optional execution context
            
        Returns:
            ToolResult with success/failure info
        """
        # 1. Get tool
        tool = self.tools.get(tool_name)
        if not tool:
            logger.warning(f"[{self.info.name}] Tool not found: {tool_name}")
            return ToolResult.error_result(f"Tool not found: {tool_name}")
        
        # 2. Authorization check
        authorized = await self._check_authorization(
            tool_name=tool_name,
            tool_metadata=tool.metadata,
            arguments=arguments,
        )
        
        if not authorized:
            logger.info(f"[{self.info.name}] Authorization denied for tool: {tool_name}")
            return ToolResult.error_result("Authorization denied")
        
        # 3. Execute tool
        try:
            logger.debug(f"[{self.info.name}] Executing tool: {tool_name}")
            result = await tool.execute_safe(arguments, context)
            
            # Record in history
            self._history.append({
                "type": "tool_call",
                "tool": tool_name,
                "arguments": arguments,
                "result": result.to_dict(),
                "step": self._current_step,
                "timestamp": time.time(),
            })
            
            return result
            
        except Exception as e:
            logger.exception(f"[{self.info.name}] Tool execution failed: {tool_name}")
            return ToolResult.error_result(str(e))
    
    async def _check_authorization(
        self,
        tool_name: str,
        tool_metadata: ToolMetadata,
        arguments: Dict[str, Any],
    ) -> bool:
        """
        Check authorization for a tool call.
        
        Args:
            tool_name: Name of the tool
            tool_metadata: Tool metadata
            arguments: Tool arguments
            
        Returns:
            True if authorized, False otherwise
        """
        auth_ctx = AuthorizationContext(
            session_id=self._session_id or "default",
            tool_name=tool_name,
            arguments=arguments,
            tool_metadata=tool_metadata,
            agent_name=self.info.name,
        )
        
        auth_result = await self.auth_engine.check_authorization(auth_ctx)
        
        return auth_result.decision.value in ("granted", "cached")
    
    async def _handle_user_confirmation(
        self,
        request: Dict[str, Any],
    ) -> bool:
        """
        Handle user confirmation request.
        
        Called by authorization engine when user confirmation is needed.
        
        Args:
            request: Confirmation request details
            
        Returns:
            True if user confirmed, False otherwise
        """
        # Update state to waiting
        previous_state = self._state
        self._state = AgentState.WAITING
        
        try:
            # Create interaction request
            interaction_request = create_authorization_request(
                tool_name=request.get("tool_name", "unknown"),
                tool_description=request.get("tool_description", ""),
                arguments=request.get("arguments", {}),
                risk_assessment=request.get("risk_assessment"),
                session_id=self._session_id,
                agent_name=self.info.name,
                allow_session_grant=request.get("allow_session_grant", True),
                timeout=request.get("timeout", 300),
            )
            
            # Send and wait for response
            response = await self.interaction.send_and_wait(interaction_request)
            
            return response.is_confirmed
            
        finally:
            # Restore state
            self._state = previous_state
    
    # ========== User Interaction ==========
    
    async def ask_user(
        self,
        question: str,
        title: str = "Input Required",
        default: Optional[str] = None,
        placeholder: Optional[str] = None,
        timeout: int = 300,
    ) -> str:
        """
        Ask user for text input.
        
        Args:
            question: Question to ask
            title: Dialog title
            default: Default value
            placeholder: Input placeholder
            timeout: Timeout in seconds
            
        Returns:
            User's input string
        """
        previous_state = self._state
        self._state = AgentState.WAITING
        
        try:
            request = create_text_input_request(
                question=question,
                title=title,
                default=default,
                placeholder=placeholder,
                session_id=self._session_id,
                timeout=timeout,
            )
            
            response = await self.interaction.send_and_wait(request)
            return response.input_value or default or ""
            
        finally:
            self._state = previous_state
    
    async def confirm(
        self,
        message: str,
        title: str = "Confirm",
        default: bool = False,
        timeout: int = 60,
    ) -> bool:
        """
        Ask user for confirmation.
        
        Args:
            message: Confirmation message
            title: Dialog title
            default: Default choice
            timeout: Timeout in seconds
            
        Returns:
            True if confirmed, False otherwise
        """
        previous_state = self._state
        self._state = AgentState.WAITING
        
        try:
            request = create_confirmation_request(
                message=message,
                title=title,
                default=default,
                session_id=self._session_id,
                timeout=timeout,
            )
            
            response = await self.interaction.send_and_wait(request)
            return response.is_confirmed
            
        finally:
            self._state = previous_state
    
    async def select(
        self,
        message: str,
        options: List[Dict[str, Any]],
        title: str = "Select",
        default: Optional[str] = None,
        multiple: bool = False,
        timeout: int = 120,
    ) -> str:
        """
        Ask user to select from options.
        
        Args:
            message: Selection prompt
            options: List of options (each with "value", "label", optional "description")
            title: Dialog title
            default: Default selection
            multiple: Allow multiple selection
            timeout: Timeout in seconds
            
        Returns:
            Selected value(s)
        """
        previous_state = self._state
        self._state = AgentState.WAITING
        
        try:
            request = create_selection_request(
                message=message,
                options=options,
                title=title,
                default=default,
                multiple=multiple,
                session_id=self._session_id,
                timeout=timeout,
            )
            
            response = await self.interaction.send_and_wait(request)
            return response.choice or default or ""
            
        finally:
            self._state = previous_state
    
    async def notify(
        self,
        message: str,
        level: str = "info",
        title: Optional[str] = None,
    ) -> None:
        """
        Send a notification to user.
        
        Args:
            message: Notification message
            level: Notification level (info, warning, error, success)
            title: Optional title
        """
        request = create_notification(
            message=message,
            level=level,
            title=title,
            session_id=self._session_id,
        )
        
        await self.interaction.send(request)
    
    # ========== Run Loop ==========
    
    async def run(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Main execution loop.
        
        Implements Think -> Decide -> Act cycle.
        
        Args:
            message: Initial message/task
            session_id: Session ID (auto-generated if not provided)
            **kwargs: Additional arguments passed to think/decide/act
            
        Yields:
            Output chunks (thinking, responses, tool results)
        """
        # Initialize run
        self._state = AgentState.RUNNING
        self._session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
        self._current_step = 0
        self._start_time = time.time()
        
        # Add initial message to history
        self._messages.append({
            "role": "user",
            "content": message,
        })
        
        logger.info(f"[{self.info.name}] Starting run, session={self._session_id}")
        
        try:
            while self._current_step < self.info.max_steps:
                self._current_step += 1
                
                # Check timeout
                if self.elapsed_time > self.info.timeout:
                    yield f"\n[Timeout] Exceeded maximum time ({self.info.timeout}s)\n"
                    self._state = AgentState.FAILED
                    break
                
                # 1. Think phase
                thinking_output = []
                async for chunk in self.think(message, **kwargs):
                    thinking_output.append(chunk)
                    yield chunk
                
                # 2. Decide phase
                decision = await self.decide(message, **kwargs)
                
                # Record decision in history
                self._history.append({
                    "type": "decision",
                    "decision": decision,
                    "step": self._current_step,
                    "timestamp": time.time(),
                })
                
                # 3. Act phase based on decision type
                decision_type = decision.get("type", "error")
                
                if decision_type == "response":
                    # Direct response to user
                    content = decision.get("content", "")
                    yield content
                    
                    # Add to messages
                    self._messages.append({
                        "role": "assistant",
                        "content": content,
                    })
                    
                    self._state = AgentState.COMPLETED
                    break
                
                elif decision_type == "tool_call":
                    # Execute tool
                    tool_name = decision.get("tool", "")
                    arguments = decision.get("arguments", {})
                    
                    result = await self.act(decision, **kwargs)
                    
                    if isinstance(result, ToolResult):
                        if result.success:
                            output_preview = result.output[:500]
                            message = f"Tool '{tool_name}' succeeded: {output_preview}"
                            yield f"\n[Tool] {message}\n"
                        else:
                            message = f"Tool '{tool_name}' failed: {result.error}"
                            yield f"\n[Tool Error] {message}\n"
                        
                        # Add tool result to messages for next iteration
                        self._messages.append({
                            "role": "assistant",
                            "content": f"Called tool: {tool_name}",
                            "tool_calls": [{
                                "name": tool_name,
                                "arguments": arguments,
                            }],
                        })
                        self._messages.append({
                            "role": "tool",
                            "name": tool_name,
                            "content": result.output if result.success else result.error or "",
                        })
                    else:
                        yield f"\n[Action] {result}\n"
                
                elif decision_type == "complete":
                    # Task completed
                    final_message = decision.get("message", "Task completed")
                    yield f"\n{final_message}\n"
                    self._state = AgentState.COMPLETED
                    break
                
                elif decision_type == "error":
                    # Error occurred
                    error = decision.get("error", "Unknown error")
                    yield f"\n[Error] {error}\n"
                    self._state = AgentState.FAILED
                    break
                
                else:
                    # Unknown decision type
                    yield f"\n[Warning] Unknown decision type: {decision_type}\n"
            
            else:
                # Max steps reached
                yield f"\n[Warning] Reached maximum steps ({self.info.max_steps})\n"
                self._state = AgentState.COMPLETED
            
            # Final status
            if self._state == AgentState.COMPLETED:
                yield "\n[Done]"
                logger.info(f"[{self.info.name}] Run completed, steps={self._current_step}")
            
        except asyncio.CancelledError:
            self._state = AgentState.FAILED
            yield "\n[Cancelled]"
            logger.info(f"[{self.info.name}] Run cancelled")
            raise
            
        except Exception as e:
            self._state = AgentState.FAILED
            yield f"\n[Exception] {str(e)}\n"
            logger.exception(f"[{self.info.name}] Run failed with exception")
    
    # ========== Utility Methods ==========
    
    def reset(self) -> None:
        """Reset agent state for a new run."""
        self._state = AgentState.IDLE
        self._session_id = None
        self._current_step = 0
        self._start_time = None
        self._history.clear()
        self._messages.clear()
    
    def add_message(self, role: str, content: str, **kwargs) -> None:
        """Add a message to the message history."""
        message = {"role": role, "content": content}
        message.update(kwargs)
        self._messages.append(message)
    
    def get_available_tools(self) -> List[ToolMetadata]:
        """
        Get list of available tools for this agent.
        
        Returns:
            List of ToolMetadata for tools this agent can use
        """
        all_tools = self.tools.list_all()
        
        # Apply tool policy filter
        if self.info.tool_policy:
            return self.info.tool_policy.filter_tools(all_tools)
        
        # Apply explicit tool list filter
        if self.info.tools:
            return [t for t in all_tools if t.name in self.info.tools]
        
        return all_tools
    
    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools in OpenAI function calling format.
        
        Returns:
            List of tool specifications for OpenAI API
        """
        return [tool.get_openai_spec() for tool in self.get_available_tools()]
    
    def has_capability(self, capability: AgentCapability) -> bool:
        """Check if agent has a specific capability."""
        return self.info.has_capability(capability)
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.info.name} state={self._state.value}>"
