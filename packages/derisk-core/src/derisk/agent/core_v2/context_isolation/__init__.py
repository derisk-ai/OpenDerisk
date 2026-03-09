"""Context Isolation System for Subagents.

This module provides context isolation mechanisms for subagent delegation,
inspired by Claude Code's Task tool design.

Features:
1. Multiple isolation modes (ISOLATED, SHARED, FORK)
2. Memory scope management
3. Resource binding isolation
4. Tool access control

Isolation Modes:
- ISOLATED: Completely new context, no inheritance from parent
- SHARED: Inherits parent's context and sees updates
- FORK: Copies parent's context snapshot, independent afterwards
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Set
from pydantic import BaseModel, Field
from datetime import datetime
import copy


class ContextIsolationMode(str, Enum):
    """Context isolation modes for subagents.

    - ISOLATED: Completely new context, no inheritance from parent.
                Best for independent tasks that don't need parent context.

    - SHARED: Inherits parent's context and sees updates in real-time.
              Best for tasks that need to work with parent's state.

    - FORK: Copies parent's context snapshot at delegation time.
            Independent afterwards, parent changes don't affect it.
            Best for tasks that need initial context but should not be affected
            by parent's subsequent actions.
    """

    ISOLATED = "isolated"
    SHARED = "shared"
    FORK = "fork"


@dataclass
class ContextWindow:
    """Defines a context window for an agent.

    The context window contains all the information an agent can access:
    - Messages (conversation history)
    - Tools that are available
    - Memory types that can be accessed
    - Resource bindings (file paths, databases, etc.)
    """

    messages: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    max_tokens: int = 128000
    available_tools: Set[str] = field(default_factory=set)
    memory_types: Set[str] = field(default_factory=lambda: {"working"})
    resource_bindings: Dict[str, str] = field(default_factory=dict)

    def clone(self) -> "ContextWindow":
        """Create a deep copy of this context window."""
        return ContextWindow(
            messages=copy.deepcopy(self.messages),
            total_tokens=self.total_tokens,
            max_tokens=self.max_tokens,
            available_tools=copy.copy(self.available_tools),
            memory_types=copy.copy(self.memory_types),
            resource_bindings=copy.deepcopy(self.resource_bindings),
        )

    def add_message(self, role: str, content: str, **metadata) -> None:
        """Add a message to the context."""
        message = {"role": role, "content": content, **metadata}
        self.messages.append(message)
        # Rough token estimation
        self.total_tokens += len(content) // 4

    def can_add_tokens(self, tokens: int) -> bool:
        """Check if we can add more tokens."""
        return self.total_tokens + tokens <= self.max_tokens


class MemoryScope(BaseModel):
    """Memory scope configuration for subagents.

    Defines which memory layers a subagent can access and how
    memory operations are handled.
    """

    accessible_layers: List[str] = Field(
        default_factory=lambda: ["working"],
        description="Memory layers the subagent can read from",
    )
    inherit_parent: bool = Field(
        default=True, description="Whether to inherit parent's working memory"
    )
    share_to_children: bool = Field(
        default=True,
        description="Whether this agent's memory is visible to its children",
    )
    write_policy: str = Field(
        default="append",
        description="How to handle memory writes: append, replace, or merge",
    )
    propagate_up: bool = Field(
        default=False, description="Whether to propagate results to parent agent"
    )
    max_memory_items: int = Field(
        default=100, description="Maximum number of memory items to keep"
    )

    class Config:
        arbitrary_types_allowed = True


class ResourceBinding(BaseModel):
    """A resource binding for context isolation.

    Resources are named references that agents can access, such as:
    - File paths
    - Database connections
    - API endpoints
    - Environment variables
    """

    name: str
    resource_type: str  # "file", "directory", "database", "api", etc.
    value: str
    read_only: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolAccessRule(BaseModel):
    """A rule for tool access control.

    Tools can be allowed or denied based on regex patterns.
    """

    pattern: str  # Regex pattern to match tool names
    action: str  # "allow" or "deny"
    priority: int = 0  # Higher priority rules are evaluated first
    reason: Optional[str] = None


class SubagentContextConfig(BaseModel):
    """Configuration for subagent context isolation.

    This configuration determines how a subagent's context is
    created and managed.
    """

    isolation_mode: ContextIsolationMode = ContextIsolationMode.ISOLATED
    memory_scope: MemoryScope = Field(default_factory=MemoryScope)
    resource_bindings: List[ResourceBinding] = Field(default_factory=list)
    allowed_tools: Optional[List[str]] = Field(
        default=None,
        description="List of allowed tools (None means use tool_access_rules)",
    )
    denied_tools: List[str] = Field(
        default_factory=list, description="List of explicitly denied tools"
    )
    tool_access_rules: List[ToolAccessRule] = Field(default_factory=list)
    model_id: Optional[str] = Field(
        default=None, description="Model ID to use (None means inherit from parent)"
    )
    max_context_tokens: int = Field(
        default=32000, description="Maximum context tokens for this subagent"
    )
    timeout_seconds: int = Field(
        default=300, description="Timeout for subagent execution"
    )
    max_iterations: int = Field(
        default=300,
        description="Maximum number of iterations/steps (increased from 10 for long-running tasks)",
    )
    system_prompt_override: Optional[str] = Field(
        default=None, description="Override the system prompt"
    )
    additional_instructions: Optional[str] = Field(
        default=None, description="Additional instructions to append to system prompt"
    )

    class Config:
        arbitrary_types_allowed = True

    def is_tool_allowed(self, tool_name: str) -> tuple[bool, Optional[str]]:
        """Check if a tool is allowed.

        Returns:
            Tuple of (is_allowed, reason)
        """
        import re

        # Check explicit denies first
        if tool_name in self.denied_tools:
            return False, f"Tool '{tool_name}' is explicitly denied"

        # If there's an allow list, check it
        if self.allowed_tools is not None:
            if tool_name in self.allowed_tools:
                return True, None
            # Check patterns
            for pattern in self.allowed_tools:
                if re.match(pattern, tool_name):
                    return True, None
            return False, f"Tool '{tool_name}' is not in allowed list"

        # Check tool access rules (sorted by priority)
        for rule in sorted(self.tool_access_rules, key=lambda r: -r.priority):
            if re.match(rule.pattern, tool_name):
                if rule.action == "deny":
                    return False, rule.reason
                elif rule.action == "allow":
                    return True, rule.reason

        # Default: allow
        return True, None


class IsolatedContext(BaseModel):
    """An isolated context for a subagent.

    This contains all the information needed to run a subagent
    with proper isolation from its parent.
    """

    context_id: str
    parent_context_id: Optional[str] = None
    isolation_mode: ContextIsolationMode
    context_window: Dict[str, Any] = Field(default_factory=dict)
    config: SubagentContextConfig
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class ContextIsolationInterface(ABC):
    """Abstract interface for context isolation management.

    This interface defines the core operations for managing
    isolated subagent contexts.
    """

    @abstractmethod
    async def create_isolated_context(
        self,
        parent_context: Optional[ContextWindow],
        config: SubagentContextConfig,
    ) -> IsolatedContext:
        """Create a new isolated context.

        Args:
            parent_context: The parent agent's context (if any)
            config: Configuration for the isolated context

        Returns:
            The newly created IsolatedContext
        """
        pass

    @abstractmethod
    async def merge_context_back(
        self,
        isolated_context: IsolatedContext,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge results back to parent context.

        This is called when a subagent completes and its results
        should be propagated back to the parent.

        Args:
            isolated_context: The subagent's context
            result: The result from the subagent

        Returns:
            Data to merge into parent's context
        """
        pass

    @abstractmethod
    async def get_context(self, context_id: str) -> Optional[IsolatedContext]:
        """Get an isolated context by ID.

        Args:
            context_id: The context ID to look up

        Returns:
            The IsolatedContext, or None if not found
        """
        pass

    @abstractmethod
    async def update_context(
        self,
        context_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """Update an isolated context.

        Args:
            context_id: The context ID to update
            updates: The updates to apply

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def cleanup_context(self, context_id: str) -> None:
        """Clean up an isolated context after use.

        Args:
            context_id: The context ID to clean up
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about context isolation.

        Returns:
            Statistics dictionary
        """
        pass


__all__ = [
    # Enums
    "ContextIsolationMode",
    # Dataclasses
    "ContextWindow",
    # Models
    "MemoryScope",
    "ResourceBinding",
    "ToolAccessRule",
    "SubagentContextConfig",
    "IsolatedContext",
    # Interface
    "ContextIsolationInterface",
]

# Import manager for convenience
from .manager import ContextIsolationManager

__all__.append("ContextIsolationManager")
