"""System Events Vis Component.

This component displays real-time system events during agent execution,
including preparation phase (build, resource loading, sandbox init) and
execution phase (LLM calls, actions, retries, errors).
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List

from derisk.vis import Vis
from derisk._private.pydantic import Field

logger = logging.getLogger(__name__)


class SystemEventItem:
    """Single system event item for visualization.

    This is a simplified version of SystemEvent optimized for frontend rendering.
    """

    def __init__(
        self,
        event_id: str,
        event_type: str,
        title: str,
        description: Optional[str] = None,
        timestamp: Optional[str] = None,
        duration_ms: Optional[int] = None,
        icon: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.title = title
        self.description = description
        self.timestamp = timestamp
        self.duration_ms = duration_ms
        self.icon = icon
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "title": self.title,
        }
        if self.description is not None:
            result["description"] = self.description
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.icon is not None:
            result["icon"] = self.icon
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class SystemEventsContent:
    """Content model for SystemEvents Vis component.

    Attributes:
        uid: Unique identifier for this component instance
        type: Update type - "incr" for incremental, "all" for full replace
        is_running: Whether the agent is currently running
        current_action: Human-readable description of current action
        current_phase: Current execution phase (preparation/execution/completion)
        recent_events: List of recent events to display (usually 3)
        total_count: Total number of events
        has_more: Whether there are more events than shown
        total_duration_ms: Total duration from first to last event
    """

    def __init__(
        self,
        uid: str,
        type: str = "incr",
        is_running: bool = True,
        current_action: Optional[str] = None,
        current_phase: str = "preparation",
        recent_events: Optional[List[Dict[str, Any]]] = None,
        total_count: int = 0,
        has_more: bool = False,
        total_duration_ms: Optional[int] = None,
    ):
        self.uid = uid
        self.type = type
        self.is_running = is_running
        self.current_action = current_action
        self.current_phase = current_phase
        self.recent_events = recent_events or []
        self.total_count = total_count
        self.has_more = has_more
        self.total_duration_ms = total_duration_ms

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "uid": self.uid,
            "type": self.type,
            "is_running": self.is_running,
            "current_phase": self.current_phase,
            "total_count": self.total_count,
            "has_more": self.has_more,
        }
        if self.current_action is not None:
            result["current_action"] = self.current_action
        if self.recent_events:
            result["recent_events"] = self.recent_events
        if self.total_duration_ms is not None:
            result["total_duration_ms"] = self.total_duration_ms
        return result


EVENT_ICON_MAP = {
    "agent_build_start": "setting",
    "agent_build_complete": "check-circle",
    "sandbox_create_start": "cloud-server",
    "sandbox_create_done": "cloud-server",
    "sandbox_create_failed": "cloud-server",
    "sandbox_init_start": "cloud-server",
    "sandbox_init_done": "cloud-server",
    "sandbox_init_failed": "cloud-server",
    "resource_loading": "folder-open",
    "resource_loaded": "folder",
    "resource_failed": "folder",
    "resource_build_start": "folder-open",
    "resource_build_done": "folder",
    "resource_build_failed": "folder",
    "sub_agent_build_start": "team",
    "sub_agent_build_done": "team",
    "sub_agent_build_failed": "team",
    "agent_instance_create": "robot",
    "environment_ready": "check-circle",
    "agent_start": "play-circle",
    "agent_complete": "check-circle",
    "llm_thinking": "brain",
    "llm_complete": "check-circle",
    "llm_failed": "close-circle",
    "action_start": "play-circle",
    "action_complete": "check-circle",
    "action_failed": "close-circle",
    "retry_triggered": "redo",
    "max_retry_reached": "exclamation-circle",
    "error_occurred": "close-circle",
    "warning": "warning",
    "info": "info-circle",
    "token_budget_allocated": "calculator",
    "token_budget_layer_used": "bar-chart",
    "token_budget_summary": "pie-chart",
}


class SystemEvents(Vis):
    """Vis component for displaying system events.

    This component renders a real-time event timeline showing the agent's
    execution progress, including preparation (build, resources, sandbox)
    and execution (LLM calls, actions, retries, errors).

    Tag: d-system-events
    """

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Generate the parameters required by the vis protocol.

        Args:
            **kwargs: Must contain 'content' key with SystemEventsContent data

        Returns:
            Validated content dictionary for frontend rendering
        """
        content = kwargs.get("content")
        if not content:
            logger.warning("SystemEvents received empty content")
            return None

        try:
            if isinstance(content, dict):
                uid = content.get("uid")
                if not uid:
                    logger.warning("SystemEvents content missing uid")
                    return None

                events = content.get("recent_events", [])
                for event in events:
                    if "icon" not in event or not event["icon"]:
                        event_type = event.get("event_type", "")
                        event["icon"] = EVENT_ICON_MAP.get(event_type, "info-circle")

                return content

            return content

        except Exception as e:
            logger.warning(f"SystemEvents validation error: {e}")
            return content

    @classmethod
    def vis_tag(cls) -> str:
        """Vis tag name.

        Returns:
            The tag name for this component: "d-system-events"
        """
        return "d-system-events"

    @staticmethod
    def get_icon_for_event(event_type: str) -> str:
        """Get the icon name for an event type.

        Args:
            event_type: The event type string

        Returns:
            Icon name for frontend rendering
        """
        return EVENT_ICON_MAP.get(event_type, "info-circle")
