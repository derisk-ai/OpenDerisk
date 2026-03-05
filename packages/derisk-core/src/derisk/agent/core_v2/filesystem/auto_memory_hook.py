"""Auto Memory Hooks for Derisk Agents.

This module provides hooks for automatic memory writing during agent execution.
These hooks detect important events and decisions, then write them to the
project memory system.

Hook Types:
1. AutoMemoryHook - General conversation memory
2. ImportantDecisionHook - Detects and records decisions
3. ErrorRecoveryHook - Records error resolutions
4. KnowledgeExtractionHook - Extracts domain knowledge
"""

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class HookPriority(IntEnum):
    """Priority levels for hooks (higher = run later)."""
    HIGHEST = 100
    HIGH = 75
    NORMAL = 50
    LOW = 25
    LOWEST = 0


class AgentPhase(str, Enum):
    """Phases in the agent execution lifecycle."""
    INITIALIZE = "initialize"
    BEFORE_THINK = "before_think"
    AFTER_THINK = "after_think"
    BEFORE_DECIDE = "before_decide"
    AFTER_DECIDE = "after_decide"
    BEFORE_ACT = "before_act"
    AFTER_ACT = "after_act"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class HookContext:
    """Context passed to hooks during execution."""
    phase: AgentPhase
    agent_name: str
    session_id: str
    message: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """Result returned by a hook."""
    should_continue: bool = True
    should_write_memory: bool = False
    memory_content: Optional[str] = None
    memory_metadata: Optional[Dict[str, Any]] = None
    modifications: Dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None


class SceneHook(ABC):
    """Base class for scene-based hooks.

    Hooks are triggered at specific phases during agent execution
    and can modify behavior, write memories, or both.
    """

    name: str = "base_hook"
    priority: HookPriority = HookPriority.NORMAL
    phases: List[AgentPhase] = []

    def __init__(self):
        """Initialize the hook."""
        self._enabled = True
        self._call_count = 0

    @property
    def enabled(self) -> bool:
        """Check if the hook is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable the hook."""
        self._enabled = True

    def disable(self) -> None:
        """Disable the hook."""
        self._enabled = False

    @abstractmethod
    async def execute(self, ctx: HookContext) -> HookResult:
        """Execute the hook logic.

        Args:
            ctx: The hook execution context

        Returns:
            HookResult with actions to take
        """
        pass

    def should_run(self, phase: AgentPhase) -> bool:
        """Check if this hook should run for the given phase."""
        return self._enabled and phase in self.phases


class AutoMemoryHook(SceneHook):
    """Hook for automatic memory writing.

    This hook monitors conversations and writes significant content
    to the project memory after a threshold of interactions.
    """

    name = "auto_memory"
    priority = HookPriority.LOW
    phases = [AgentPhase.AFTER_ACT, AgentPhase.COMPLETE]

    # Patterns that indicate memory-worthy content
    PATTERNS = [
        r'(?:decided|determined|concluded)\s+(?:to|that)',
        r'(?:important|key|critical|essential)\s+(?:point|finding|insight)',
        r'(?:solution|fix|resolution)\s+(?:for|to)',
        r'(?:lesson|learned|takeaway)',
        r'(?:remember|note|keep in mind)',
    ]

    def __init__(
        self,
        threshold: int = 10,
        min_importance: float = 0.3,
    ):
        """Initialize the auto memory hook.

        Args:
            threshold: Number of interactions before writing
            min_importance: Minimum importance score to write
        """
        super().__init__()
        self._threshold = threshold
        self._min_importance = min_importance
        self._pending_memories: List[Dict[str, Any]] = []
        self._interaction_count = 0

    async def execute(self, ctx: HookContext) -> HookResult:
        """Execute the auto memory hook."""
        self._call_count += 1
        self._interaction_count += 1

        result = HookResult()

        # Check for memory-worthy content
        if ctx.message:
            memory_content = self._extract_memorable_content(ctx.message)

            if memory_content:
                self._pending_memories.append({
                    "content": memory_content,
                    "timestamp": datetime.now().isoformat(),
                    "phase": ctx.phase.value,
                    "agent": ctx.agent_name,
                })

        # On complete phase, write all pending memories
        if ctx.phase == AgentPhase.COMPLETE:
            if self._pending_memories:
                combined = self._combine_pending_memories()
                result.should_write_memory = True
                result.memory_content = combined
                result.memory_metadata = {
                    "type": "auto_memory",
                    "interaction_count": self._interaction_count,
                    "entries": len(self._pending_memories),
                }
                self._pending_memories.clear()
                self._interaction_count = 0

        # Check threshold for mid-execution writes
        elif self._interaction_count >= self._threshold:
            if self._pending_memories:
                combined = self._combine_pending_memories()
                result.should_write_memory = True
                result.memory_content = combined
                result.memory_metadata = {
                    "type": "threshold_memory",
                    "interaction_count": self._interaction_count,
                }
                self._pending_memories.clear()

        return result

    def _extract_memorable_content(self, text: str) -> Optional[str]:
        """Extract memory-worthy content from text."""
        for pattern in self.PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Get surrounding context
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 200)
                return text[start:end].strip()
        return None

    def _combine_pending_memories(self) -> str:
        """Combine pending memories into a single entry."""
        lines = ["## Memory Entries\n"]

        for mem in self._pending_memories:
            lines.append(f"- [{mem['timestamp']}] {mem['content'][:200]}")

        return '\n'.join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Get hook statistics."""
        return {
            "name": self.name,
            "call_count": self._call_count,
            "interaction_count": self._interaction_count,
            "pending_memories": len(self._pending_memories),
            "threshold": self._threshold,
        }


class ImportantDecisionHook(SceneHook):
    """Hook for detecting and recording important decisions.

    This hook specifically looks for decision-making language
    and records structured decision entries.
    """

    name = "important_decision"
    priority = HookPriority.HIGH
    phases = [AgentPhase.AFTER_DECIDE, AgentPhase.AFTER_ACT]

    # Decision indicators
    DECISION_KEYWORDS = [
        "decided", "chose", "selected", "adopted",
        "determined", "concluded", "resolved",
        "will use", "will implement", "going with",
    ]

    # Rejection indicators
    REJECTION_KEYWORDS = [
        "rejected", "discarded", "ruled out",
        "not using", "won't use", "decided against",
    ]

    def __init__(self, min_confidence: float = 0.7):
        """Initialize the decision hook.

        Args:
            min_confidence: Minimum confidence to record a decision
        """
        super().__init__()
        self._min_confidence = min_confidence
        self._decisions: List[Dict[str, Any]] = []

    async def execute(self, ctx: HookContext) -> HookResult:
        """Execute the decision detection hook."""
        self._call_count += 1
        result = HookResult()

        # Check decision phase
        if ctx.phase == AgentPhase.AFTER_DECIDE and ctx.decision:
            decision_type = ctx.decision.get("type", "")
            content = ctx.decision.get("content", "")

            if decision_type and content:
                detected = self._detect_decision(content)
                if detected:
                    self._decisions.append({
                        "type": decision_type,
                        "content": content,
                        "confidence": detected["confidence"],
                        "timestamp": datetime.now().isoformat(),
                    })

        # Check act phase for tool decisions
        elif ctx.phase == AgentPhase.AFTER_ACT:
            if ctx.tool_name and ctx.tool_result:
                # Tool usage can indicate a decision
                if self._is_decision_tool(ctx.tool_name):
                    self._decisions.append({
                        "type": "tool_decision",
                        "tool": ctx.tool_name,
                        "result": str(ctx.tool_result)[:500],
                        "timestamp": datetime.now().isoformat(),
                    })

        # Write if we have high-confidence decisions
        if any(d["confidence"] >= self._min_confidence for d in self._decisions):
            result.should_write_memory = True
            result.memory_content = self._format_decisions()
            result.memory_metadata = {
                "type": "important_decisions",
                "count": len(self._decisions),
            }

        return result

    def _detect_decision(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text contains a decision.

        Returns:
            Dict with 'confidence' and 'type' if detected
        """
        text_lower = text.lower()

        # Check for positive decisions
        for keyword in self.DECISION_KEYWORDS:
            if keyword in text_lower:
                return {"confidence": 0.8, "type": "decision"}

        # Check for rejections
        for keyword in self.REJECTION_KEYWORDS:
            if keyword in text_lower:
                return {"confidence": 0.7, "type": "rejection"}

        return None

    def _is_decision_tool(self, tool_name: str) -> bool:
        """Check if tool usage represents a decision."""
        decision_tools = [
            "select", "choose", "pick",
            "implement", "create", "configure",
            "set", "enable", "disable",
        ]
        return any(dt in tool_name.lower() for dt in decision_tools)

    def _format_decisions(self) -> str:
        """Format decisions for memory storage."""
        lines = ["## Important Decisions\n"]

        for dec in self._decisions:
            lines.append(f"\n### Decision ({dec['type']})")
            lines.append(f"- Timestamp: {dec['timestamp']}")
            if 'content' in dec:
                lines.append(f"- Content: {dec['content']}")
            if 'tool' in dec:
                lines.append(f"- Tool: {dec['tool']}")

        return '\n'.join(lines)


class ErrorRecoveryHook(SceneHook):
    """Hook for recording error resolutions.

    This hook captures errors and their resolutions for future reference.
    """

    name = "error_recovery"
    priority = HookPriority.HIGH
    phases = [AgentPhase.ERROR, AgentPhase.AFTER_ACT]

    def __init__(self):
        """Initialize the error hook."""
        super().__init__()
        self._errors: List[Dict[str, Any]] = []
        self._resolutions: List[Dict[str, Any]] = []

    async def execute(self, ctx: HookContext) -> HookResult:
        """Execute the error recovery hook."""
        self._call_count += 1
        result = HookResult()

        # Capture errors
        if ctx.phase == AgentPhase.ERROR and ctx.error:
            self._errors.append({
                "error_type": type(ctx.error).__name__,
                "message": str(ctx.error),
                "phase": ctx.phase.value,
                "timestamp": datetime.now().isoformat(),
            })

        # Check for resolution in act phase
        elif ctx.phase == AgentPhase.AFTER_ACT:
            if ctx.tool_result and self._is_resolution(ctx.tool_result):
                self._resolutions.append({
                    "tool": ctx.tool_name,
                    "result": str(ctx.tool_result)[:500],
                    "timestamp": datetime.now().isoformat(),
                })

                # If we had a prior error, this might be the resolution
                if self._errors:
                    result.should_write_memory = True
                    result.memory_content = self._format_error_resolution()
                    result.memory_metadata = {
                        "type": "error_resolution",
                        "errors": len(self._errors),
                        "resolutions": len(self._resolutions),
                    }
                    self._errors.clear()
                    self._resolutions.clear()

        return result

    def _is_resolution(self, result: Any) -> bool:
        """Check if a result represents a resolution."""
        if isinstance(result, str):
            resolution_keywords = [
                "fixed", "resolved", "solved",
                "corrected", "working", "success",
            ]
            return any(kw in result.lower() for kw in resolution_keywords)
        return False

    def _format_error_resolution(self) -> str:
        """Format error-resolution pairs for memory."""
        lines = ["## Error Resolution Record\n"]

        for i, error in enumerate(self._errors):
            lines.append(f"\n### Error {i + 1}")
            lines.append(f"- Type: {error['error_type']}")
            lines.append(f"- Message: {error['message']}")

        for i, resolution in enumerate(self._resolutions):
            lines.append(f"\n### Resolution {i + 1}")
            lines.append(f"- Tool: {resolution['tool']}")
            lines.append(f"- Result: {resolution['result']}")

        return '\n'.join(lines)


class KnowledgeExtractionHook(SceneHook):
    """Hook for extracting domain knowledge.

    This hook identifies factual statements and domain-specific
    information that should be preserved.
    """

    name = "knowledge_extraction"
    priority = HookPriority.LOW
    phases = [AgentPhase.AFTER_THINK, AgentPhase.COMPLETE]

    # Knowledge patterns
    KNOWLEDGE_PATTERNS = [
        r'(?:the\s+)?(\w+)\s+(?:is|are|means|refers to)\s+',
        r'(?:by definition|defined as)\s+',
        r'(?:note that|important|key point)\s*:\s*',
        r'(?:according to|based on|per)\s+',
    ]

    def __init__(self, min_length: int = 50):
        """Initialize the knowledge hook.

        Args:
            min_length: Minimum text length to consider
        """
        super().__init__()
        self._min_length = min_length
        self._knowledge: List[Dict[str, Any]] = []

    async def execute(self, ctx: HookContext) -> HookResult:
        """Execute the knowledge extraction hook."""
        self._call_count += 1
        result = HookResult()

        if not ctx.message or len(ctx.message) < self._min_length:
            return result

        extracted = self._extract_knowledge(ctx.message)

        if extracted:
            self._knowledge.extend(extracted)

        # Write on complete
        if ctx.phase == AgentPhase.COMPLETE and self._knowledge:
            result.should_write_memory = True
            result.memory_content = self._format_knowledge()
            result.memory_metadata = {
                "type": "domain_knowledge",
                "entries": len(self._knowledge),
            }
            self._knowledge.clear()

        return result

    def _extract_knowledge(self, text: str) -> List[Dict[str, Any]]:
        """Extract knowledge items from text."""
        items = []

        for pattern in self.KNOWLEDGE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)

            for match in matches:
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 200)

                item = {
                    "content": text[start:end].strip(),
                    "pattern": pattern,
                    "timestamp": datetime.now().isoformat(),
                }
                items.append(item)

        return items

    def _format_knowledge(self) -> str:
        """Format extracted knowledge for memory."""
        lines = ["## Extracted Knowledge\n"]

        for item in self._knowledge:
            lines.append(f"\n- {item['content']}")

        return '\n'.join(lines)


class HookRegistry:
    """Registry for managing hooks.

    This provides a central place to register, enable, and
    execute hooks during agent execution.
    """

    def __init__(self):
        """Initialize the hook registry."""
        self._hooks: Dict[str, SceneHook] = {}
        self._phase_hooks: Dict[AgentPhase, List[SceneHook]] = {
            phase: [] for phase in AgentPhase
        }

    def register(self, hook: SceneHook) -> None:
        """Register a hook."""
        self._hooks[hook.name] = hook

        for phase in hook.phases:
            self._phase_hooks[phase].append(hook)

        # Sort by priority
        for phase in AgentPhase:
            self._phase_hooks[phase].sort(key=lambda h: -h.priority)

        logger.debug(f"Registered hook: {hook.name}")

    def unregister(self, name: str) -> bool:
        """Unregister a hook by name."""
        hook = self._hooks.pop(name, None)
        if hook:
            for phase in hook.phases:
                try:
                    self._phase_hooks[phase].remove(hook)
                except ValueError:
                    pass
            return True
        return False

    def get_hook(self, name: str) -> Optional[SceneHook]:
        """Get a hook by name."""
        return self._hooks.get(name)

    async def execute_phase(
        self,
        phase: AgentPhase,
        ctx: HookContext,
    ) -> List[HookResult]:
        """Execute all hooks for a phase.

        Args:
            phase: The execution phase
            ctx: The hook context

        Returns:
            List of hook results
        """
        results = []

        for hook in self._phase_hooks[phase]:
            if hook.should_run(phase):
                try:
                    result = await hook.execute(ctx)
                    results.append(result)

                    # Stop processing if hook says to stop
                    if not result.should_continue:
                        break

                except Exception as e:
                    logger.error(f"Hook {hook.name} failed: {e}")

        return results

    def enable_hook(self, name: str) -> bool:
        """Enable a specific hook."""
        hook = self._hooks.get(name)
        if hook:
            hook.enable()
            return True
        return False

    def disable_hook(self, name: str) -> bool:
        """Disable a specific hook."""
        hook = self._hooks.get(name)
        if hook:
            hook.disable()
            return True
        return False

    def get_all_hooks(self) -> List[SceneHook]:
        """Get all registered hooks."""
        return list(self._hooks.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all hooks."""
        return {
            name: hook.get_stats() if hasattr(hook, 'get_stats') else {
                "name": name,
                "enabled": hook.enabled,
            }
            for name, hook in self._hooks.items()
        }


def create_default_hooks() -> List[SceneHook]:
    """Create the default set of memory hooks.

    Returns:
        List of configured hooks
    """
    return [
        AutoMemoryHook(threshold=10),
        ImportantDecisionHook(min_confidence=0.7),
        ErrorRecoveryHook(),
        KnowledgeExtractionHook(min_length=50),
    ]


__all__ = [
    # Enums
    "HookPriority",
    "AgentPhase",
    # Data classes
    "HookContext",
    "HookResult",
    # Base class
    "SceneHook",
    # Hooks
    "AutoMemoryHook",
    "ImportantDecisionHook",
    "ErrorRecoveryHook",
    "KnowledgeExtractionHook",
    # Registry
    "HookRegistry",
    # Factory
    "create_default_hooks",
]