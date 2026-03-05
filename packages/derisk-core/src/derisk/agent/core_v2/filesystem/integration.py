"""AgentFileSystem Integration for Project Memory.

This module integrates the project memory system with AgentFileSystem,
enabling seamless file-based context and prompt management.

Integration Features:
1. Register memory files with AgentFileSystem
2. Sync memory content to file storage
3. Export memory as artifacts
4. Bridge between memory and file operations
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field
import asyncio

if TYPE_CHECKING:
    from ..project_memory import ProjectMemoryManager, ProjectMemoryConfig
    from ..project_memory.manager import MemoryLayer

logger = logging.getLogger(__name__)


class MemoryArtifact(BaseModel):
    """Represents a memory artifact exported to file system."""
    name: str
    path: str
    content_type: str = "text/markdown"
    size_bytes: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class AgentFileSystemMemoryExtension:
    """Extension for integrating project memory with AgentFileSystem.

    This class provides methods to:
    1. Initialize memory files in AgentFileSystem
    2. Sync memory content to storage
    3. Export memory as artifacts for agent consumption

    Example:
        from derisk.agent.core_v2.project_memory import ProjectMemoryManager

        manager = ProjectMemoryManager()
        extension = AgentFileSystemMemoryExtension(manager)
        await extension.initialize()

        # Export memory as artifact
        artifact = await extension.get_memory_as_artifact("project")
    """

    # Memory file mappings
    MEMORY_FILE_MAPPINGS = {
        "main": "MEMORY.md",
        "rules": "RULES.md",
        "default_agent": "AGENTS/DEFAULT.md",
        "knowledge": "KNOWLEDGE/",
        "auto": "MEMORY.LOCAL/auto-memory.md",
    }

    def __init__(
        self,
        project_memory: "ProjectMemoryManager",
        storage_backend: Optional[str] = None,
    ):
        """Initialize the file system extension.

        Args:
            project_memory: The project memory manager instance
            storage_backend: Optional storage backend identifier
        """
        self._project_memory = project_memory
        self._storage_backend = storage_backend
        self._initialized = False
        self._artifacts: Dict[str, MemoryArtifact] = {}

    async def initialize(self) -> None:
        """Initialize the file system integration.

        This registers all memory files with AgentFileSystem and
        prepares the storage backend.
        """
        if self._initialized:
            return

        # Register memory files
        await self._register_memory_files()

        self._initialized = True
        logger.info("AgentFileSystemMemoryExtension initialized")

    async def _register_memory_files(self) -> None:
        """Register memory files with the file system."""
        config = self._project_memory._config
        if not config:
            logger.warning("Project memory not configured")
            return

        memory_path = config.memory_path

        # Define file patterns to register
        patterns = [
            ("MEMORY.md", "main"),
            ("RULES.md", "rules"),
            ("AGENTS/*.md", "agent_config"),
            ("KNOWLEDGE/*.md", "knowledge"),
            ("MEMORY.LOCAL/auto-memory.md", "auto"),
        ]

        for pattern, file_type in patterns:
            full_pattern = memory_path / pattern
            await self._scan_and_register(full_pattern, file_type)

    async def _scan_and_register(self, pattern: Path, file_type: str) -> int:
        """Scan files matching pattern and register them.

        Args:
            pattern: Glob pattern for files
            file_type: Type identifier for the files

        Returns:
            Number of files registered
        """
        import glob

        count = 0
        parent_dir = pattern.parent

        if not parent_dir.exists():
            return 0

        if pattern.is_file():
            files = [pattern]
        else:
            files = list(parent_dir.glob(pattern.name))

        for file_path in files:
            if file_path.is_file():
                await self._register_file(file_path, file_type)
                count += 1

        return count

    async def _register_file(self, path: Path, file_type: str) -> None:
        """Register a single file with AgentFileSystem.

        Args:
            path: Path to the file
            file_type: Type identifier for the file
        """
        try:
            stat = path.stat()

            artifact = MemoryArtifact(
                name=path.name,
                path=str(path),
                size_bytes=stat.st_size,
                metadata={
                    "type": file_type,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                },
            )

            self._artifacts[str(path)] = artifact
            logger.debug(f"Registered memory file: {path}")

        except Exception as e:
            logger.error(f"Failed to register {path}: {e}")

    async def sync_memory_to_storage(self) -> Dict[str, Any]:
        """Sync all memory content to storage backend.

        This exports the current memory state to the configured
        storage backend (if any).

        Returns:
            Sync statistics
        """
        stats = {
            "files_synced": 0,
            "bytes_synced": 0,
            "errors": [],
        }

        for path, artifact in self._artifacts.items():
            try:
                file_path = Path(path)
                if file_path.exists():
                    content = file_path.read_text(encoding='utf-8')
                    await self._write_to_storage(path, content)

                    stats["files_synced"] += 1
                    stats["bytes_synced"] += len(content)

            except Exception as e:
                stats["errors"].append({"path": path, "error": str(e)})
                logger.error(f"Failed to sync {path}: {e}")

        return stats

    async def _write_to_storage(self, path: str, content: str) -> None:
        """Write content to storage backend.

        Args:
            path: File path
            content: File content
        """
        # Write to local file system by default
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')

        # If there's a storage backend, write there too
        if self._storage_backend:
            # Integration with external storage would go here
            pass

    async def get_memory_as_artifact(
        self,
        layer_name: str = "project",
    ) -> Optional[MemoryArtifact]:
        """Get merged memory content as an artifact.

        This builds the context for a specific layer and returns
        it as a file-system compatible artifact.

        Args:
            layer_name: Name of the memory layer to export

        Returns:
            MemoryArtifact with the layer content, or None
        """
        # Get the memory context
        context = await self._project_memory.build_context()

        if not context:
            return None

        # Create artifact
        artifact = MemoryArtifact(
            name=f"memory_{layer_name}.md",
            path=f".derisk/exports/memory_{layer_name}.md",
            content_type="text/markdown",
            size_bytes=len(context.encode('utf-8')),
            metadata={
                "layer": layer_name,
                "generated_at": datetime.now().isoformat(),
            },
        )

        return artifact

    async def export_all_artifacts(self) -> List[MemoryArtifact]:
        """Export all memory layers as artifacts.

        Returns:
            List of MemoryArtifact objects
        """
        artifacts = []

        for layer_name in ["auto", "user", "project"]:
            artifact = await self.get_memory_as_artifact(layer_name)
            if artifact:
                artifacts.append(artifact)

        return artifacts

    def get_artifact(self, name: str) -> Optional[MemoryArtifact]:
        """Get a registered artifact by name.

        Args:
            name: Artifact name to look up

        Returns:
            The artifact, or None if not found
        """
        for artifact in self._artifacts.values():
            if artifact.name == name:
                return artifact
        return None

    def list_artifacts(self) -> List[MemoryArtifact]:
        """List all registered artifacts.

        Returns:
            List of all artifacts
        """
        return list(self._artifacts.values())


class MemoryFileSync:
    """Synchronizes memory state with file system.

    This provides bidirectional sync between the in-memory state
    and the file system representation.
    """

    def __init__(
        self,
        memory_manager: "ProjectMemoryManager",
        watch_enabled: bool = True,
    ):
        """Initialize the file sync.

        Args:
            memory_manager: The project memory manager
            watch_enabled: Whether to enable file watching
        """
        self._memory_manager = memory_manager
        self._watch_enabled = watch_enabled
        self._sync_interval = 30  # seconds
        self._running = False

    async def start_sync(self) -> None:
        """Start the background sync process."""
        if not self._watch_enabled:
            return

        self._running = True

        while self._running:
            try:
                await self._sync_cycle()
            except Exception as e:
                logger.error(f"Sync cycle error: {e}")

            await asyncio.sleep(self._sync_interval)

    def stop_sync(self) -> None:
        """Stop the background sync process."""
        self._running = False

    async def _sync_cycle(self) -> None:
        """Perform one sync cycle."""
        # Check for file changes
        await self._check_file_changes()

        # Write any pending changes
        await self._write_pending_changes()

    async def _check_file_changes(self) -> None:
        """Check for external file changes and reload."""
        config = self._memory_manager._config
        if not config:
            return

        # Re-scan memory sources
        await self._memory_manager._scan_memory_sources()

    async def _write_pending_changes(self) -> None:
        """Write pending memory changes to files."""
        # This would check for pending writes and apply them
        pass


class PromptFileManager:
    """Manages prompt templates as file system artifacts.

    This enables storing and retrieving prompt templates from
    the project memory file structure.
    """

    PROMPT_DIR = ".derisk/PROMPTS"

    def __init__(self, project_root: Path):
        """Initialize the prompt file manager.

        Args:
            project_root: Path to the project root
        """
        self.project_root = project_root
        self.prompt_dir = project_root / self.PROMPT_DIR

    def ensure_dir(self) -> None:
        """Ensure the prompt directory exists."""
        self.prompt_dir.mkdir(parents=True, exist_ok=True)

    async def save_prompt(
        self,
        name: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Save a prompt template to file.

        Args:
            name: Prompt name
            content: Prompt content
            metadata: Optional metadata

        Returns:
            Path to the saved file
        """
        self.ensure_dir()

        file_path = self.prompt_dir / f"{name}.md"

        # Build file content with metadata
        lines = [
            "---",
            f"name: {name}",
            f"created: {datetime.now().isoformat()}",
        ]

        if metadata:
            for key, value in metadata.items():
                lines.append(f"{key}: {value}")

        lines.extend([
            "---",
            "",
            content,
        ])

        file_content = '\n'.join(lines)

        # Write file
        import aiofiles
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(file_content)

        return file_path

    async def load_prompt(self, name: str) -> Optional[str]:
        """Load a prompt template by name.

        Args:
            name: Prompt name

        Returns:
            Prompt content, or None if not found
        """
        import aiofiles

        file_path = self.prompt_dir / f"{name}.md"

        if not file_path.exists():
            return None

        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()

        # Remove front matter
        import re
        match = re.match(r'^---\s*\n.*?\n---\s*\n', content, re.DOTALL)
        if match:
            return content[match.end():]

        return content

    def list_prompts(self) -> List[str]:
        """List all available prompt names.

        Returns:
            List of prompt names
        """
        if not self.prompt_dir.exists():
            return []

        return [p.stem for p in self.prompt_dir.glob("*.md")]

    async def delete_prompt(self, name: str) -> bool:
        """Delete a prompt template.

        Args:
            name: Prompt name to delete

        Returns:
            True if deleted, False if not found
        """
        file_path = self.prompt_dir / f"{name}.md"

        if file_path.exists():
            file_path.unlink()
            return True

        return False


def register_project_memory_hooks(
    project_memory: "ProjectMemoryManager",
) -> None:
    """Register hooks for project memory integration.

    This sets up the necessary hooks for automatic memory writing
    and file synchronization.

    Args:
        project_memory: The project memory manager instance
    """
    from .auto_memory_hook import (
        HookRegistry,
        AutoMemoryHook,
        ImportantDecisionHook,
        create_default_hooks,
    )

    # Create hook registry if not exists
    registry = HookRegistry()

    # Register default hooks
    for hook in create_default_hooks():
        registry.register(hook)

    logger.info("Registered project memory hooks")


__all__ = [
    "MemoryArtifact",
    "AgentFileSystemMemoryExtension",
    "MemoryFileSync",
    "PromptFileManager",
    "register_project_memory_hooks",
]