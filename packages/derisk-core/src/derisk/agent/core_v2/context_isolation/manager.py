"""Context Isolation Manager Implementation.

This module implements the ContextIsolationInterface to provide
context isolation for subagent delegation.
"""

import asyncio
import copy
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from . import (
    ContextIsolationMode,
    ContextWindow,
    MemoryScope,
    ResourceBinding,
    SubagentContextConfig,
    IsolatedContext,
    ContextIsolationInterface,
)

logger = logging.getLogger(__name__)


class ContextIsolationManager(ContextIsolationInterface):
    """Manages context isolation for subagent delegation.

    This implementation provides:
    1. Multiple isolation modes (ISOLATED, SHARED, FORK)
    2. Memory scope management
    3. Resource binding isolation
    4. Tool access control

    Example:
        manager = ContextIsolationManager()

        # Create an isolated context
        config = SubagentContextConfig(
            isolation_mode=ContextIsolationMode.FORK,
            max_context_tokens=16000,
        )
        context = await manager.create_isolated_context(parent_context, config)

        # Use the context...

        # Merge results back
        result = await manager.merge_context_back(context, {"output": "done"})

        # Clean up
        await manager.cleanup_context(context.context_id)
    """

    def __init__(self, max_contexts: int = 100):
        """Initialize the context isolation manager.

        Args:
            max_contexts: Maximum number of concurrent contexts to track
        """
        self._contexts: Dict[str, IsolatedContext] = {}
        self._shared_views: Dict[str, List[str]] = {}  # parent_id -> child_ids
        self._max_contexts = max_contexts
        self._stats = {
            "contexts_created": 0,
            "contexts_merged": 0,
            "contexts_cleaned": 0,
            "total_tokens_managed": 0,
        }

    async def create_isolated_context(
        self,
        parent_context: Optional[ContextWindow],
        config: SubagentContextConfig,
    ) -> IsolatedContext:
        """Create a new isolated context.

        The context is created based on the isolation mode:
        - ISOLATED: Empty context window
        - SHARED: Reference to parent's context window
        - FORK: Deep copy of parent's context window

        Args:
            parent_context: The parent agent's context (if any)
            config: Configuration for the isolated context

        Returns:
            The newly created IsolatedContext
        """
        context_id = self._generate_context_id()

        # Create the context window based on isolation mode
        if config.isolation_mode == ContextIsolationMode.ISOLATED:
            context_window = self._create_isolated_window(config)
        elif config.isolation_mode == ContextIsolationMode.SHARED:
            context_window = self._create_shared_window(parent_context, config)
        elif config.isolation_mode == ContextIsolationMode.FORK:
            context_window = self._create_forked_window(parent_context, config)
        else:
            raise ValueError(f"Unknown isolation mode: {config.isolation_mode}")

        # Create resource bindings
        resource_bindings = self._prepare_resource_bindings(config)

        # Create the isolated context
        isolated_context = IsolatedContext(
            context_id=context_id,
            parent_context_id=None,  # Will be set if parent exists
            isolation_mode=config.isolation_mode,
            context_window=self._window_to_dict(context_window),
            config=config,
            metadata={
                "resource_bindings": [r.dict() for r in resource_bindings],
                "created_from_parent": parent_context is not None,
            }
        )

        # Track parent-child relationship
        if parent_context and config.isolation_mode == ContextIsolationMode.SHARED:
            parent_id = str(id(parent_context))
            isolated_context.parent_context_id = parent_id
            if parent_id not in self._shared_views:
                self._shared_views[parent_id] = []
            self._shared_views[parent_id].append(context_id)

        # Store the context
        self._contexts[context_id] = isolated_context
        self._stats["contexts_created"] += 1
        self._stats["total_tokens_managed"] += context_window.total_tokens

        # Enforce max contexts limit
        await self._enforce_context_limit()

        logger.debug(
            f"Created {config.isolation_mode.value} context {context_id} "
            f"with {context_window.total_tokens} tokens"
        )

        return isolated_context

    def _generate_context_id(self) -> str:
        """Generate a unique context ID."""
        return f"ctx_{uuid.uuid4().hex[:12]}_{datetime.now().strftime('%H%M%S')}"

    def _create_isolated_window(self, config: SubagentContextConfig) -> ContextWindow:
        """Create an empty isolated context window."""
        return ContextWindow(
            messages=[],
            total_tokens=0,
            max_tokens=config.max_context_tokens,
            available_tools=set(config.allowed_tools) if config.allowed_tools else set(),
            memory_types=set(config.memory_scope.accessible_layers),
            resource_bindings={
                rb.name: rb.value for rb in config.resource_bindings
            },
        )

    def _create_shared_window(
        self,
        parent_context: Optional[ContextWindow],
        config: SubagentContextConfig,
    ) -> ContextWindow:
        """Create a shared context window that references the parent.

        In shared mode, the subagent sees all updates to the parent's context
        in real-time. This is implemented by returning the same context object.
        """
        if parent_context is None:
            logger.warning("Shared mode requested but no parent context, using isolated")
            return self._create_isolated_window(config)

        # In shared mode, we return the same context object
        # The subagent will see all parent updates
        return parent_context

    def _create_forked_window(
        self,
        parent_context: Optional[ContextWindow],
        config: SubagentContextConfig,
    ) -> ContextWindow:
        """Create a forked context window from the parent.

        In fork mode, we create a deep copy of the parent's context at
        delegation time. The subagent's context is independent afterward.
        """
        if parent_context is None:
            logger.warning("Fork mode requested but no parent context, using isolated")
            return self._create_isolated_window(config)

        # Create a deep copy of the parent's context
        forked = parent_context.clone()

        # Apply memory scope filtering
        if not config.memory_scope.inherit_parent:
            forked.messages = []
            forked.total_tokens = 0

        # Update max tokens if specified
        forked.max_tokens = config.max_context_tokens

        # Filter tools based on configuration
        if config.allowed_tools:
            forked.available_tools = forked.available_tools.intersection(
                set(config.allowed_tools)
            )

        # Remove denied tools
        for denied_tool in config.denied_tools:
            forked.available_tools.discard(denied_tool)

        # Update resource bindings
        for rb in config.resource_bindings:
            forked.resource_bindings[rb.name] = rb.value

        return forked

    def _prepare_resource_bindings(
        self, config: SubagentContextConfig
    ) -> List[ResourceBinding]:
        """Prepare and validate resource bindings."""
        bindings = []

        for rb in config.resource_bindings:
            # Validate resource binding
            if not rb.name or not rb.resource_type:
                logger.warning(f"Skipping invalid resource binding: {rb}")
                continue
            bindings.append(rb)

        return bindings

    def _window_to_dict(self, window: ContextWindow) -> Dict[str, Any]:
        """Convert a ContextWindow to a dictionary."""
        return {
            "messages": window.messages,
            "total_tokens": window.total_tokens,
            "max_tokens": window.max_tokens,
            "available_tools": list(window.available_tools),
            "memory_types": list(window.memory_types),
            "resource_bindings": window.resource_bindings,
        }

    def _dict_to_window(self, data: Dict[str, Any]) -> ContextWindow:
        """Convert a dictionary to a ContextWindow."""
        return ContextWindow(
            messages=data.get("messages", []),
            total_tokens=data.get("total_tokens", 0),
            max_tokens=data.get("max_tokens", 128000),
            available_tools=set(data.get("available_tools", [])),
            memory_types=set(data.get("memory_types", ["working"])),
            resource_bindings=data.get("resource_bindings", {}),
        )

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
        self._stats["contexts_merged"] += 1

        # Check if propagation is allowed
        if not isolated_context.config.memory_scope.propagate_up:
            logger.debug(
                f"Context {isolated_context.context_id} has propagate_up=False, "
                "skipping merge"
            )
            return {}

        merge_data = {}

        # Merge based on write policy
        write_policy = isolated_context.config.memory_scope.write_policy

        if write_policy == "append":
            # Append new messages to parent
            if "messages" in isolated_context.context_window:
                merge_data["messages"] = isolated_context.context_window.get("messages", [])
            merge_data["result"] = result

        elif write_policy == "replace":
            # Replace with subagent's final state
            merge_data = {
                "messages": isolated_context.context_window.get("messages", []),
                "result": result,
            }

        elif write_policy == "merge":
            # Merge with parent (dedup messages, combine resources)
            merge_data = {
                "messages": isolated_context.context_window.get("messages", []),
                "resources": isolated_context.context_window.get("resource_bindings", {}),
                "result": result,
            }

        # Add metadata
        merge_data["_metadata"] = {
            "source_context": isolated_context.context_id,
            "isolation_mode": isolated_context.isolation_mode.value,
            "merged_at": datetime.now().isoformat(),
        }

        logger.debug(
            f"Merged context {isolated_context.context_id} with policy {write_policy}"
        )

        return merge_data

    async def get_context(self, context_id: str) -> Optional[IsolatedContext]:
        """Get an isolated context by ID.

        Args:
            context_id: The context ID to look up

        Returns:
            The IsolatedContext, or None if not found
        """
        return self._contexts.get(context_id)

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
        context = self._contexts.get(context_id)
        if not context:
            return False

        # Deep merge updates into context window
        window_data = context.context_window
        for key, value in updates.items():
            if key == "messages" and isinstance(value, list):
                window_data["messages"].extend(value)
            elif key == "available_tools" and isinstance(value, (list, set)):
                window_data["available_tools"] = list(
                    set(window_data.get("available_tools", [])) | set(value)
                )
            elif key == "resource_bindings" and isinstance(value, dict):
                window_data.setdefault("resource_bindings", {}).update(value)
            else:
                window_data[key] = value

        # Recalculate tokens
        if "messages" in window_data:
            total = sum(
                len(m.get("content", "")) // 4
                for m in window_data["messages"]
            )
            window_data["total_tokens"] = total

        return True

    async def cleanup_context(self, context_id: str) -> None:
        """Clean up an isolated context after use.

        Args:
            context_id: The context ID to clean up
        """
        context = self._contexts.pop(context_id, None)
        if context:
            self._stats["contexts_cleaned"] += 1
            self._stats["total_tokens_managed"] -= context.context_window.get(
                "total_tokens", 0
            )

            # Clean up shared views tracking
            parent_id = context.parent_context_id
            if parent_id and parent_id in self._shared_views:
                try:
                    self._shared_views[parent_id].remove(context_id)
                except ValueError:
                    pass

            logger.debug(f"Cleaned up context {context_id}")

    async def _enforce_context_limit(self) -> None:
        """Enforce the maximum number of tracked contexts.

        Removes oldest contexts if we exceed the limit.
        """
        if len(self._contexts) <= self._max_contexts:
            return

        # Sort by creation time and remove oldest
        sorted_contexts = sorted(
            self._contexts.items(),
            key=lambda x: x[1].created_at
        )

        to_remove = len(self._contexts) - self._max_contexts
        for context_id, _ in sorted_contexts[:to_remove]:
            await self.cleanup_context(context_id)
            logger.info(f"Removed old context {context_id} to enforce limit")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about context isolation.

        Returns:
            Statistics dictionary
        """
        return {
            **self._stats,
            "active_contexts": len(self._contexts),
            "shared_views_count": sum(len(v) for v in self._shared_views.values()),
            "max_contexts": self._max_contexts,
        }

    # Context validation methods

    def validate_context_config(
        self, config: SubagentContextConfig
    ) -> List[str]:
        """Validate a context configuration.

        Returns a list of validation errors (empty if valid).
        """
        errors = []

        # Validate token limits
        if config.max_context_tokens < 1000:
            errors.append("max_context_tokens must be at least 1000")
        if config.max_context_tokens > 128000:
            errors.append("max_context_tokens exceeds maximum of 128000")

        # Validate timeout
        if config.timeout_seconds < 1:
            errors.append("timeout_seconds must be at least 1")

        # Validate isolation mode
        try:
            ContextIsolationMode(config.isolation_mode)
        except ValueError:
            errors.append(f"Invalid isolation_mode: {config.isolation_mode}")

        # Validate tool access rules
        for rule in config.tool_access_rules:
            if rule.action not in ("allow", "deny"):
                errors.append(f"Invalid tool rule action: {rule.action}")

        return errors

    # Tool access management

    def filter_tools_for_context(
        self,
        available_tools: List[str],
        config: SubagentContextConfig,
    ) -> List[str]:
        """Filter available tools based on context configuration.

        Args:
            available_tools: List of all available tool names
            config: The subagent context configuration

        Returns:
            Filtered list of allowed tools
        """
        filtered = []

        for tool_name in available_tools:
            is_allowed, reason = config.is_tool_allowed(tool_name)
            if is_allowed:
                filtered.append(tool_name)
            else:
                logger.debug(f"Tool '{tool_name}' denied: {reason}")

        return filtered

    # Resource binding management

    def get_resource_bindings(
        self, context_id: str
    ) -> Dict[str, ResourceBinding]:
        """Get resource bindings for a context.

        Args:
            context_id: The context ID

        Returns:
            Dictionary of resource bindings
        """
        context = self._contexts.get(context_id)
        if not context:
            return {}

        bindings = {}
        for rb_data in context.metadata.get("resource_bindings", []):
            try:
                rb = ResourceBinding(**rb_data)
                bindings[rb.name] = rb
            except Exception as e:
                logger.warning(f"Invalid resource binding: {e}")

        return bindings

    def add_resource_binding(
        self,
        context_id: str,
        binding: ResourceBinding,
    ) -> bool:
        """Add a resource binding to a context.

        Args:
            context_id: The context ID
            binding: The resource binding to add

        Returns:
            True if successful, False otherwise
        """
        context = self._contexts.get(context_id)
        if not context:
            return False

        bindings = context.metadata.setdefault("resource_bindings", [])

        # Remove existing binding with same name
        bindings = [b for b in bindings if b.get("name") != binding.name]
        bindings.append(binding.dict())

        context.metadata["resource_bindings"] = bindings
        context.context_window.setdefault("resource_bindings", {})
        context.context_window["resource_bindings"][binding.name] = binding.value

        return True

    # Shared context updates (for SHARED mode)

    async def propagate_to_children(
        self,
        parent_context_id: str,
        updates: Dict[str, Any],
    ) -> int:
        """Propagate updates to child contexts in SHARED mode.

        Args:
            parent_context_id: The parent context ID
            updates: The updates to propagate

        Returns:
            Number of children updated
        """
        child_ids = self._shared_views.get(parent_context_id, [])
        updated_count = 0

        for child_id in child_ids:
            if await self.update_context(child_id, updates):
                updated_count += 1

        return updated_count

    # Context snapshot

    def create_snapshot(self, context_id: str) -> Optional[Dict[str, Any]]:
        """Create a snapshot of a context for debugging or persistence.

        Args:
            context_id: The context ID

        Returns:
            Snapshot dictionary, or None if context not found
        """
        context = self._contexts.get(context_id)
        if not context:
            return None

        return {
            "context_id": context.context_id,
            "parent_context_id": context.parent_context_id,
            "isolation_mode": context.isolation_mode.value,
            "context_window": copy.deepcopy(context.context_window),
            "config": context.config.dict(),
            "created_at": context.created_at.isoformat(),
            "metadata": copy.deepcopy(context.metadata),
        }

    async def restore_snapshot(self, snapshot: Dict[str, Any]) -> IsolatedContext:
        """Restore a context from a snapshot.

        Args:
            snapshot: The snapshot dictionary

        Returns:
            The restored IsolatedContext
        """
        context = IsolatedContext(
            context_id=snapshot["context_id"],
            parent_context_id=snapshot.get("parent_context_id"),
            isolation_mode=ContextIsolationMode(snapshot["isolation_mode"]),
            context_window=snapshot["context_window"],
            config=SubagentContextConfig(**snapshot["config"]),
            created_at=datetime.fromisoformat(snapshot["created_at"]),
            metadata=snapshot.get("metadata", {}),
        )

        self._contexts[context.context_id] = context
        self._stats["contexts_created"] += 1

        return context