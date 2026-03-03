"""Project Memory System for Derisk.

This module provides a multi-level project memory system inspired by Claude Code's CLAUDE.md mechanism.

Features:
1. Multi-layer memory priority (AUTO < USER < PROJECT < MANAGED < SYSTEM)
2. @import directive support for modular memory organization
3. Git-friendly file-backed storage
4. Automatic memory consolidation

Directory Structure:
    .derisk/
    ├── MEMORY.md                 # Main project memory
    ├── RULES.md                  # Project rules (behavior constraints)
    ├── AGENTS/
    │   ├── DEFAULT.md            # Default agent config
    │   └── {agent_name}.md       # Agent-specific config
    ├── KNOWLEDGE/
    │   ├── domain.md             # Domain knowledge
    │   └── glossary.md           # Glossary
    ├── MEMORY.LOCAL/             # Local memory (not committed to Git)
    │   ├── auto-memory.md        # Auto-generated memory
    │   └── sessions/             # Session memory
    └── .gitignore                # Git ignore rules
"""

from abc import ABC, abstractmethod
from enum import Enum, IntEnum
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from pydantic import BaseModel, Field
from datetime import datetime
import re


class MemoryPriority(IntEnum):
    """Memory priority levels - higher values override lower ones.

    This follows Claude Code's priority model:
    - AUTO: Automatically generated memories (lowest priority)
    - USER: User-level memories (~/.derisk/)
    - PROJECT: Project-level memories (./.derisk/)
    - MANAGED: Managed/enterprise policies
    - SYSTEM: System-level (cannot be overridden)
    """
    AUTO = 0         # Auto-generated memory
    USER = 25        # User-level memory (~/.derisk/)
    PROJECT = 50     # Project-level memory (./.derisk/)
    MANAGED = 75     # Managed policy (enterprise)
    SYSTEM = 100     # System-level (cannot be overridden)


class MemorySource(BaseModel):
    """Represents a memory source file.

    A memory source is a file that contributes to the agent's context.
    Sources can import other sources using @import directives.
    """
    path: Path
    priority: MemoryPriority
    scope: str  # "user" | "project" | "agent" | "session" | "auto"
    created_at: datetime = Field(default_factory=datetime.now)
    content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    imports: List[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    @property
    def name(self) -> str:
        """Get the source name (filename without extension)."""
        return self.path.stem

    @property
    def exists(self) -> bool:
        """Check if the source file exists."""
        return self.path.exists()


class MemoryLayer(BaseModel):
    """A layer of memory with a specific priority.

    Memory layers are ordered by priority and merged to form
    the complete context for an agent.
    """
    name: str
    priority: MemoryPriority
    sources: List[MemorySource] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def add_source(self, source: MemorySource) -> None:
        """Add a source to this layer."""
        self.sources.append(source)

    def get_merged_content(self) -> str:
        """Get merged content from all sources in this layer."""
        contents = []
        for source in self.sources:
            if source.content:
                contents.append(f"## {source.name}\n\n{source.content}")
        return "\n\n---\n\n".join(contents)


class ProjectMemoryConfig(BaseModel):
    """Configuration for the project memory system."""
    project_root: str
    memory_dir: str = ".derisk"
    enable_user_memory: bool = True
    enable_project_memory: bool = True
    enable_auto_memory: bool = True
    auto_memory_threshold: int = 10  # Conversations before writing
    max_import_depth: int = 5  # Maximum @import recursion depth
    auto_memory_file: str = "MEMORY.LOCAL/auto-memory.md"
    session_dir: str = "MEMORY.LOCAL/sessions"

    @property
    def memory_path(self) -> Path:
        """Get the full memory directory path."""
        return Path(self.project_root) / self.memory_dir

    @property
    def auto_memory_path(self) -> Path:
        """Get the auto-memory file path."""
        return self.memory_path / self.auto_memory_file

    @property
    def session_path(self) -> Path:
        """Get the session directory path."""
        return self.memory_path / self.session_dir


class ImportDirective(BaseModel):
    """Represents an @import directive in a memory file.

    Syntax: @import path/to/file.md
    The path is relative to the .derisk directory.
    """
    raw_path: str
    resolved_path: Optional[Path] = None
    line_number: int = 0

    @classmethod
    def parse(cls, content: str) -> List["ImportDirective"]:
        """Parse all @import directives from content.

        Args:
            content: The markdown content to parse

        Returns:
            List of ImportDirective objects
        """
        directives = []
        # Match @import followed by a path
        pattern = r'@import\s+([^\s\n]+)'

        for i, line in enumerate(content.split('\n'), 1):
            match = re.search(pattern, line)
            if match:
                directives.append(cls(
                    raw_path=match.group(1).strip(),
                    line_number=i
                ))

        return directives


class MemoryConsolidationConfig(BaseModel):
    """Configuration for memory consolidation."""
    max_age_days: int = 30  # Maximum age before consolidation
    min_importance: float = 0.3  # Minimum importance to keep
    merge_threshold: int = 100  # Lines before forcing consolidation
    deduplicate: bool = True  # Remove duplicate entries
    summarize: bool = True  # Summarize old memories


class ProjectMemoryInterface(ABC):
    """Abstract interface for project memory management.

    This interface defines the core operations for managing
    multi-level project memories.
    """

    @abstractmethod
    async def initialize(self, config: ProjectMemoryConfig) -> None:
        """Initialize the project memory system.

        Args:
            config: Configuration for the memory system
        """
        pass

    @abstractmethod
    async def build_context(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Build the complete context string.

        This merges all memory layers by priority and resolves
        all @import directives.

        Args:
            agent_name: Optional agent name for agent-specific memory
            session_id: Optional session ID for session-specific memory

        Returns:
            The merged context string
        """
        pass

    @abstractmethod
    async def get_memory_layers(self) -> List[MemoryLayer]:
        """Get all memory layers sorted by priority.

        Returns:
            List of MemoryLayer objects from lowest to highest priority
        """
        pass

    @abstractmethod
    async def write_auto_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Write to auto-memory.

        Auto-memory is automatically generated and has the lowest priority.
        It's typically written after conversations or important decisions.

        Args:
            content: The memory content to write
            metadata: Optional metadata (importance, tags, etc.)

        Returns:
            The ID or path of the written memory
        """
        pass

    @abstractmethod
    async def resolve_imports(self, content: str, depth: int = 0) -> str:
        """Resolve all @import directives in content.

        Args:
            content: The content containing @import directives
            depth: Current recursion depth (for cycle detection)

        Returns:
            Content with all imports resolved
        """
        pass

    @abstractmethod
    async def get_agent_memory(self, agent_name: str) -> Optional[MemorySource]:
        """Get agent-specific memory.

        Args:
            agent_name: The name of the agent

        Returns:
            MemorySource for the agent, or None if not found
        """
        pass

    @abstractmethod
    async def consolidate_memories(
        self,
        config: Optional[MemoryConsolidationConfig] = None,
    ) -> Dict[str, Any]:
        """Consolidate and clean up memories.

        This removes duplicates, summarizes old entries, and
        organizes the memory structure.

        Args:
            config: Optional consolidation configuration

        Returns:
            Statistics about the consolidation process
        """
        pass


__all__ = [
    # Enums
    "MemoryPriority",
    # Models
    "MemorySource",
    "MemoryLayer",
    "ProjectMemoryConfig",
    "ImportDirective",
    "MemoryConsolidationConfig",
    # Interface
    "ProjectMemoryInterface",
]

# Import manager for convenience
from .manager import ProjectMemoryManager

__all__.append("ProjectMemoryManager")