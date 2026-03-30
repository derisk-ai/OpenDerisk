"""System Event module for tracking agent lifecycle events.

This module provides event tracking capabilities for the entire agent lifecycle,
including preparation phase (build, resource loading, sandbox init) and
execution phase (LLM calls, action execution, retries, errors).
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable, Union


class SystemEventType(Enum):
    """System event types covering the complete agent lifecycle.

    Events are organized into two main phases:
    1. Preparation Phase: Agent construction, resource loading, sandbox initialization
    2. Execution Phase: LLM calls, action execution, retries, error handling
    3. Compression Phase: Token budget allocation, layer compression
    """

    # ============================================
    # PREPARATION PHASE (准备阶段)
    # ============================================
    AGENT_BUILD_START = "agent_build_start"
    """Agent开始构建"""

    AGENT_BUILD_COMPLETE = "agent_build_complete"
    """Agent构建完成"""

    SANDBOX_CREATE_START = "sandbox_create_start"
    """沙箱客户端创建开始"""

    SANDBOX_CREATE_DONE = "sandbox_create_done"
    """沙箱客户端创建完成"""

    SANDBOX_CREATE_FAILED = "sandbox_create_failed"
    """沙箱客户端创建失败"""

    SANDBOX_INIT_START = "sandbox_init_start"
    """沙箱初始化开始"""

    SANDBOX_INIT_DONE = "sandbox_init_done"
    """沙箱初始化完成"""

    SANDBOX_INIT_FAILED = "sandbox_init_failed"
    """沙箱初始化失败"""

    RESOURCE_LOADING = "resource_loading"
    """资源加载中"""

    RESOURCE_LOADED = "resource_loaded"
    """资源加载完成"""

    RESOURCE_FAILED = "resource_failed"
    """资源加载失败"""

    RESOURCE_BUILD_START = "resource_build_start"
    """Agent资源构建开始(包含MCP等)"""

    RESOURCE_BUILD_DONE = "resource_build_done"
    """Agent资源构建完成"""

    RESOURCE_BUILD_FAILED = "resource_build_failed"
    """Agent资源构建失败"""

    SUB_AGENT_BUILD_START = "sub_agent_build_start"
    """子Agent构建开始"""

    SUB_AGENT_BUILD_DONE = "sub_agent_build_done"
    """子Agent构建完成"""

    SUB_AGENT_BUILD_FAILED = "sub_agent_build_failed"
    """子Agent构建失败"""

    AGENT_INSTANCE_CREATE = "agent_instance_create"
    """Agent实例创建"""

    ENVIRONMENT_READY = "environment_ready"
    """环境准备就绪"""

    AGENT_ESSENTIAL_READY = "agent_essential_ready"
    """主Agent核心就绪，开始思考（LLM + 基础资源已加载）"""

    AGENT_FULL_READY = "agent_full_ready"
    """所有组件就绪（包括Sandbox、子Agent等延迟初始化组件）"""

    # ============================================
    # EXECUTION PHASE (执行阶段)
    # ============================================
    AGENT_START = "agent_start"
    """Agent开始运行"""

    AGENT_COMPLETE = "agent_complete"
    """Agent运行完成"""

    LLM_THINKING = "llm_thinking"
    """LLM思考中"""

    LLM_COMPLETE = "llm_complete"
    """LLM调用完成"""

    LLM_FAILED = "llm_failed"
    """LLM调用失败"""

    ACTION_START = "action_start"
    """Action开始执行"""

    ACTION_COMPLETE = "action_complete"
    """Action执行完成"""

    ACTION_FAILED = "action_failed"
    """Action执行失败"""

    RETRY_TRIGGERED = "retry_triggered"
    """触发重试"""

    MAX_RETRY_REACHED = "max_retry_reached"
    """达到最大重试次数"""

    ERROR_OCCURRED = "error_occurred"
    """发生错误"""

    WARNING = "warning"
    """警告"""

    INFO = "info"
    """一般信息"""

    # ============================================
    # COMPRESSION PHASE (压缩阶段)
    # ============================================
    TOKEN_BUDGET_ALLOCATED = "token_budget_allocated"
    """Token预算分配"""

    TOKEN_BUDGET_LAYER_USED = "token_budget_layer_used"
    """层使用情况"""

    TOKEN_BUDGET_SUMMARY = "token_budget_summary"
    """Token预算汇总"""


class EventPhase(Enum):
    """Event phase classification."""

    PREPARATION = "preparation"
    """准备阶段"""

    EXECUTION = "execution"
    """执行阶段"""

    COMPLETION = "completion"
    """完成阶段"""


# Map event types to phases
EVENT_PHASE_MAP: Dict[SystemEventType, EventPhase] = {
    # Preparation phase
    SystemEventType.AGENT_BUILD_START: EventPhase.PREPARATION,
    SystemEventType.AGENT_BUILD_COMPLETE: EventPhase.PREPARATION,
    SystemEventType.SANDBOX_CREATE_START: EventPhase.PREPARATION,
    SystemEventType.SANDBOX_CREATE_DONE: EventPhase.PREPARATION,
    SystemEventType.SANDBOX_CREATE_FAILED: EventPhase.PREPARATION,
    SystemEventType.SANDBOX_INIT_START: EventPhase.PREPARATION,
    SystemEventType.SANDBOX_INIT_DONE: EventPhase.PREPARATION,
    SystemEventType.SANDBOX_INIT_FAILED: EventPhase.PREPARATION,
    SystemEventType.RESOURCE_LOADING: EventPhase.PREPARATION,
    SystemEventType.RESOURCE_LOADED: EventPhase.PREPARATION,
    SystemEventType.RESOURCE_FAILED: EventPhase.PREPARATION,
    SystemEventType.RESOURCE_BUILD_START: EventPhase.PREPARATION,
    SystemEventType.RESOURCE_BUILD_DONE: EventPhase.PREPARATION,
    SystemEventType.RESOURCE_BUILD_FAILED: EventPhase.PREPARATION,
    SystemEventType.SUB_AGENT_BUILD_START: EventPhase.PREPARATION,
    SystemEventType.SUB_AGENT_BUILD_DONE: EventPhase.PREPARATION,
    SystemEventType.SUB_AGENT_BUILD_FAILED: EventPhase.PREPARATION,
    SystemEventType.AGENT_INSTANCE_CREATE: EventPhase.PREPARATION,
    SystemEventType.ENVIRONMENT_READY: EventPhase.PREPARATION,
    # Execution phase
    SystemEventType.AGENT_START: EventPhase.EXECUTION,
    SystemEventType.AGENT_COMPLETE: EventPhase.COMPLETION,
    SystemEventType.LLM_THINKING: EventPhase.EXECUTION,
    SystemEventType.LLM_COMPLETE: EventPhase.EXECUTION,
    SystemEventType.LLM_FAILED: EventPhase.EXECUTION,
    SystemEventType.ACTION_START: EventPhase.EXECUTION,
    SystemEventType.ACTION_COMPLETE: EventPhase.EXECUTION,
    SystemEventType.ACTION_FAILED: EventPhase.EXECUTION,
    SystemEventType.RETRY_TRIGGERED: EventPhase.EXECUTION,
    SystemEventType.MAX_RETRY_REACHED: EventPhase.EXECUTION,
    SystemEventType.ERROR_OCCURRED: EventPhase.EXECUTION,
    SystemEventType.WARNING: EventPhase.EXECUTION,
    SystemEventType.INFO: EventPhase.EXECUTION,
    # Compression phase
    SystemEventType.TOKEN_BUDGET_ALLOCATED: EventPhase.EXECUTION,
    SystemEventType.TOKEN_BUDGET_LAYER_USED: EventPhase.EXECUTION,
    SystemEventType.TOKEN_BUDGET_SUMMARY: EventPhase.EXECUTION,
}


@dataclasses.dataclass
class SystemEvent:
    """Represents a single system event during agent lifecycle.

    Attributes:
        event_id: Unique identifier for this event
        conv_id: Conversation ID
        event_type: Type of the event
        title: Human-readable title
        description: Optional detailed description
        timestamp: When the event occurred
        duration_ms: Duration in milliseconds (for timed events)
        metadata: Additional context data
    """

    event_id: str
    conv_id: str
    event_type: SystemEventType
    title: str
    description: Optional[str] = None
    timestamp: datetime = dataclasses.field(default_factory=datetime.now)
    duration_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "conv_id": self.conv_id,
            "event_type": self.event_type.value,
            "title": self.title,
            "description": self.description,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata or {},
        }

    @property
    def phase(self) -> EventPhase:
        """Get the phase this event belongs to."""
        return EVENT_PHASE_MAP.get(self.event_type, EventPhase.EXECUTION)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemEvent":
        """Create event from dictionary."""
        event_type = data.get("event_type")
        if isinstance(event_type, str):
            event_type = SystemEventType(event_type)
        elif event_type is None:
            raise ValueError("event_type is required")

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            event_id=data["event_id"],
            conv_id=data["conv_id"],
            event_type=event_type,
            title=data["title"],
            description=data.get("description"),
            timestamp=timestamp or datetime.now(),
            duration_ms=data.get("duration_ms"),
            metadata=data.get("metadata"),
        )


class SystemEventManager:
    """Manages system events for an agent conversation.

    This class collects, stores, and provides access to system events
    throughout the agent lifecycle. It supports timing events, event
    grouping, and retrieval for visualization.

    Example:
        >>> manager = SystemEventManager(conv_id="conv_123")
        >>> manager.start_event(SystemEventType.LLM_THINKING, "Thinking...")
        >>> # ... LLM call happens ...
        >>> manager.end_event()
        >>> events = manager.get_recent_events(3)
    """

    MAX_EVENTS = 100
    """Maximum number of events to keep in memory."""

    def __init__(
        self,
        conv_id: str,
        on_event_callback: Optional[Callable[[], Union[None, Awaitable[None]]]] = None,
    ):
        """Initialize the event manager.

        Args:
            conv_id: The conversation ID this manager is associated with
            on_event_callback: Optional async callback to call when events are added.
                              This is used to push updates to frontend.
        """
        self.conv_id = conv_id
        self.events: List[SystemEvent] = []
        self._current_event: Optional[SystemEvent] = None
        self._start_time: Optional[datetime] = None
        self._on_event_callback = on_event_callback

    def set_event_callback(
        self, callback: Optional[Callable[[], Union[None, Awaitable[None]]]]
    ) -> None:
        """Set or update the event callback.

        Args:
            callback: Async callback function to call when events are added
        """
        self._on_event_callback = callback

    async def _notify_event_added(self) -> None:
        """Call the event callback if set."""
        if self._on_event_callback:
            try:
                import asyncio

                # 确保在异步上下文中调用
                if asyncio.iscoroutinefunction(self._on_event_callback):
                    await self._on_event_callback()
                else:
                    self._on_event_callback()
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(f"Event callback failed: {e}")

    @property
    def start_time(self) -> Optional[datetime]:
        """Get the time when the first event was recorded."""
        return self._start_time

    def start_event(
        self,
        event_type: SystemEventType,
        title: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemEvent:
        """Start recording a timed event.

        The event will be added to the list immediately, and its duration
        will be calculated when end_event() is called.

        Args:
            event_type: Type of the event
            title: Human-readable title
            description: Optional detailed description
            metadata: Optional additional context

        Returns:
            The created event
        """
        event = SystemEvent(
            event_id=uuid.uuid4().hex,
            conv_id=self.conv_id,
            event_type=event_type,
            title=title,
            description=description,
            timestamp=datetime.now(),
            metadata=metadata,
        )

        self._current_event = event
        self._add_event(event)

        if self._start_time is None:
            self._start_time = event.timestamp

        return event

    def end_event(self, duration_ms: Optional[int] = None) -> Optional[SystemEvent]:
        """End the current timed event.

        Calculates the duration if not provided and clears the current event.

        Args:
            duration_ms: Optional explicit duration in milliseconds

        Returns:
            The completed event, or None if no event was in progress
        """
        if not self._current_event:
            return None

        if duration_ms is not None:
            self._current_event.duration_ms = duration_ms
        else:
            elapsed = datetime.now() - self._current_event.timestamp
            self._current_event.duration_ms = int(elapsed.total_seconds() * 1000)

        completed = self._current_event
        self._current_event = None
        return completed

    def add_event(
        self,
        event_type: SystemEventType,
        title: str,
        description: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SystemEvent:
        """Add a completed event (non-timed or pre-timed).

        Args:
            event_type: Type of the event
            title: Human-readable title
            description: Optional detailed description
            duration_ms: Optional duration in milliseconds
            metadata: Optional additional context

        Returns:
            The created event
        """
        event = SystemEvent(
            event_id=uuid.uuid4().hex,
            conv_id=self.conv_id,
            event_type=event_type,
            title=title,
            description=description,
            timestamp=datetime.now(),
            duration_ms=duration_ms,
            metadata=metadata,
        )

        self._add_event(event)

        if self._start_time is None:
            self._start_time = event.timestamp

        return event

    def _add_event(self, event: SystemEvent) -> None:
        """Add an event to the list, enforcing max limit."""
        self.events.append(event)

        # Enforce max events limit
        if len(self.events) > self.MAX_EVENTS:
            self.events = self.events[-self.MAX_EVENTS :]

        # Trigger callback after event is added (synchronously, callback handles async)
        if self._on_event_callback:
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    result = self._on_event_callback()
                    if asyncio.iscoroutine(result):
                        asyncio.create_task(result)
            except RuntimeError:
                pass  # No event loop running, skip callback

    def get_recent_events(self, count: int = 3) -> List[SystemEvent]:
        """Get the most recent events.

        Args:
            count: Number of events to return

        Returns:
            List of recent events, sorted by timestamp (newest first)
        """
        if not self.events:
            return []

        sorted_events = sorted(self.events, key=lambda e: e.timestamp, reverse=True)
        return sorted_events[:count]

    def get_all_events(self) -> List[SystemEvent]:
        """Get all events.

        Returns:
            List of all events, sorted by timestamp (newest first)
        """
        if not self.events:
            return []

        return sorted(self.events, key=lambda e: e.timestamp, reverse=True)

    def get_events_by_phase(self, phase: EventPhase) -> List[SystemEvent]:
        """Get events for a specific phase.

        Args:
            phase: The phase to filter by

        Returns:
            List of events in that phase, sorted by timestamp (newest first)
        """
        events = [e for e in self.events if e.phase == phase]
        return sorted(events, key=lambda e: e.timestamp, reverse=True)

    def get_current_phase(self) -> EventPhase:
        """Determine the current execution phase.

        Returns:
            The phase of the most recent event
        """
        if not self.events:
            return EventPhase.PREPARATION

        recent = self.get_recent_events(1)
        if recent:
            return recent[0].phase

        return EventPhase.EXECUTION

    def clear(self) -> None:
        """Clear all events and reset state."""
        self.events.clear()
        self._current_event = None
        self._start_time = None

    def get_total_duration_ms(self) -> Optional[int]:
        """Get the total duration from first to last event.

        Returns:
            Total duration in milliseconds, or None if no events
        """
        if not self.events:
            return None

        first = min(self.events, key=lambda e: e.timestamp)
        last = max(self.events, key=lambda e: e.timestamp)

        elapsed = last.timestamp - first.timestamp
        return int(elapsed.total_seconds() * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the manager state for persistence.

        Returns:
            Dictionary containing all events and state
        """
        return {
            "conv_id": self.conv_id,
            "events": [e.to_dict() for e in self.events],
            "start_time": self._start_time.isoformat() if self._start_time else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SystemEventManager":
        """Restore manager state from dictionary.

        Args:
            data: Previously serialized state

        Returns:
            Restored SystemEventManager instance
        """
        manager = cls(conv_id=data["conv_id"])
        manager.events = [SystemEvent.from_dict(e) for e in data.get("events", [])]

        start_time = data.get("start_time")
        if start_time:
            manager._start_time = datetime.fromisoformat(start_time)

        return manager
