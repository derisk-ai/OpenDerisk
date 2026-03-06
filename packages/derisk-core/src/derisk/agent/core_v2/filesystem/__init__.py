"""Filesystem Integration Package for Core V2.

This package provides file system integration for the Core V2 agent framework.

Modules:
- claude_compatible: CLAUDE.md compatibility layer
- auto_memory_hook: Automatic memory writing hooks
- integration: AgentFileSystem integration
"""

from .claude_compatible import (
    ClaudeMdFrontMatter,
    ClaudeMdSection,
    ClaudeMdDocument,
    ClaudeMdParser,
    ClaudeCompatibleAdapter,
    ClaudeMdWatcher,
)

from .auto_memory_hook import (
    HookPriority,
    AgentPhase,
    HookContext,
    HookResult,
    SceneHook,
    AutoMemoryHook,
    ImportantDecisionHook,
    ErrorRecoveryHook,
    KnowledgeExtractionHook,
    HookRegistry,
    create_default_hooks,
)

from .integration import (
    MemoryArtifact,
    AgentFileSystemMemoryExtension,
    MemoryFileSync,
    PromptFileManager,
    register_project_memory_hooks,
)

__all__ = [
    # CLAUDE.md compatibility
    "ClaudeMdFrontMatter",
    "ClaudeMdSection",
    "ClaudeMdDocument",
    "ClaudeMdParser",
    "ClaudeCompatibleAdapter",
    "ClaudeMdWatcher",
    # Auto memory hooks
    "HookPriority",
    "AgentPhase",
    "HookContext",
    "HookResult",
    "SceneHook",
    "AutoMemoryHook",
    "ImportantDecisionHook",
    "ErrorRecoveryHook",
    "KnowledgeExtractionHook",
    "HookRegistry",
    "create_default_hooks",
    # Integration
    "MemoryArtifact",
    "AgentFileSystemMemoryExtension",
    "MemoryFileSync",
    "PromptFileManager",
    "register_project_memory_hooks",
]