"""Claude Code compatible memory implementation."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from derisk.core import Embeddings
from derisk.storage.vector_store.base import VectorStoreBase

from .base import MemoryItem, MemoryType
from .unified_manager import UnifiedMemoryManager


class ClaudeCodeCompatibleMemory(UnifiedMemoryManager):
    """Claude Code compatible memory manager.
    
    Features:
    - CLAUDE.md style memory files
    - Recursive directory search for memory files
    - User-level and project-level memory
    - Auto-memory with 200-line limit
    - @import syntax support
    """
    
    CLAUDE_MD_NAMES = ["CLAUDE.md", ".claude/CLAUDE.md"]
    CLAUDE_LOCAL_MD = "CLAUDE.local.md"
    USER_CLAUDE_MD = "~/.claude/CLAUDE.md"
    AUTO_MEMORY_LINES_LIMIT = 200
    
    def __init__(
        self,
        project_root: str,
        vector_store: VectorStoreBase,
        embedding_model: Embeddings,
        session_id: Optional[str] = None,
    ):
        """Initialize Claude Code compatible memory.
        
        Args:
            project_root: Project root directory
            vector_store: Vector store for semantic search
            embedding_model: Embedding model for vectorization
            session_id: Optional session ID
        """
        super().__init__(
            project_root=project_root,
            vector_store=vector_store,
            embedding_model=embedding_model,
            session_id=session_id,
            auto_sync_to_file=True,
        )
        self._auto_memory_topics: Dict[str, List[str]] = {}
    
    @classmethod
    def from_project(
        cls,
        project_root: str,
        vector_store: Optional[VectorStoreBase] = None,
        embedding_model: Optional[Embeddings] = None,
        session_id: Optional[str] = None,
    ) -> "ClaudeCodeCompatibleMemory":
        """Create instance with default configurations.
        
        Args:
            project_root: Project root directory
            vector_store: Optional vector store (will create default if None)
            embedding_model: Optional embedding model (will create default if None)
            session_id: Optional session ID
            
        Returns:
            ClaudeCodeCompatibleMemory instance
        """
        if embedding_model is None:
            from derisk.rag.embedding import DefaultEmbeddingFactory
            embedding_model = DefaultEmbeddingFactory.openai()
        
        if vector_store is None:
            from derisk.configs.model_config import DATA_DIR
            from derisk_ext.storage.vector_store.chroma_store import (
                ChromaStore,
                ChromaVectorConfig,
            )
            
            vstore_path = os.path.join(DATA_DIR, "claude_memory")
            vector_store = ChromaStore(
                ChromaVectorConfig(persist_path=vstore_path),
                name="claude_memory",
                embedding_fn=embedding_model,
            )
        
        return cls(
            project_root=project_root,
            vector_store=vector_store,
            embedding_model=embedding_model,
            session_id=session_id,
        )
    
    async def load_claude_md_style(self) -> Dict[str, int]:
        """Load CLAUDE.md style memory files from various locations.
        
        Loads from:
        1. Managed policy (system-level)
        2. User-level (~/.claude/CLAUDE.md)
        3. Project ancestors (recursive upward search)
        4. Current project
        5. Local overrides
        
        Returns:
            Dict mapping source to number of items loaded
        """
        await self.initialize()
        stats = {}
        
        managed_policy_path = self._get_managed_policy_path()
        if managed_policy_path and managed_policy_path.exists():
            count = await self._load_memory_file(managed_policy_path, "managed_policy")
            stats["managed_policy"] = count
        
        user_claude = Path.home() / ".claude" / "CLAUDE.md"
        if user_claude.exists():
            count = await self._load_memory_file(user_claude, "user")
            stats["user"] = count
        
        ancestor_files = self._find_ancestor_claude_files()
        for file_path in ancestor_files:
            count = await self._load_memory_file(file_path, "ancestor")
            if count > 0:
                stats[f"ancestor:{file_path}"] = count
        
        for name in self.CLAUDE_MD_NAMES:
            project_file = Path(self.project_root) / name
            if project_file.exists():
                count = await self._load_memory_file(project_file, "project")
                stats["project"] = count
                break
        
        local_file = Path(self.project_root) / self.CLAUDE_LOCAL_MD
        if local_file.exists():
            count = await self._load_memory_file(local_file, "local")
            stats["local"] = count
        
        return stats
    
    def _get_managed_policy_path(self) -> Optional[Path]:
        """Get managed policy CLAUDE.md path based on platform."""
        import platform
        
        system = platform.system()
        if system == "Darwin":
            return Path("/Library/Application Support/ClaudeCode/CLAUDE.md")
        elif system == "Linux":
            return Path("/etc/claude-code/CLAUDE.md")
        elif system == "Windows":
            return Path("C:\\Program Files\\ClaudeCode\\CLAUDE.md")
        return None
    
    def _find_ancestor_claude_files(self) -> List[Path]:
        """Find CLAUDE.md files in ancestor directories."""
        files = []
        current = Path(self.project_root).parent
        
        while current != current.parent:
            for name in self.CLAUDE_MD_NAMES:
                candidate = current / name
                if candidate.exists():
                    files.append(candidate)
                    break
            current = current.parent
        
        return files
    
    async def _load_memory_file(
        self,
        file_path: Path,
        source: str,
    ) -> int:
        """Load a CLAUDE.md style memory file.
        
        Args:
            file_path: Path to the memory file
            source: Source identifier
            
        Returns:
            Number of items loaded
        """
        content = file_path.read_text(encoding="utf-8")
        
        content = self.file_storage._resolve_imports(content)
        
        memory_id = f"claude_md_{source}_{file_path.name}"
        
        item = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=MemoryType.SHARED,
            metadata={
                "source": source,
                "file_path": str(file_path),
                "loaded_at": str(file_path.stat().st_mtime),
            },
            source=source,
            file_path=str(file_path),
        )
        
        if not item.embedding:
            item.embedding = await self.embedding_model.embed([content])
        
        self._memory_cache[memory_id] = item
        await self._add_to_vector_store(item)
        
        return 1
    
    async def auto_memory(
        self,
        session_id: str,
        content: str,
        topic: Optional[str] = None,
    ) -> str:
        """Add auto-memory for a session.
        
        Auto-memory saves content to MEMORY.md file. If the file exceeds
        200 lines, content is archived to topic files.
        
        Args:
            session_id: Session ID
            content: Content to remember
            topic: Optional topic classification
            
        Returns:
            Memory ID
        """
        await self.initialize()
        
        memory_id = await self.write(
            content=content,
            memory_type=MemoryType.WORKING,
            metadata={"auto_memory": True, "topic": topic},
        )
        
        session_file = self.file_storage._get_session_file(session_id)
        
        if session_file.exists():
            lines = session_file.read_text(encoding="utf-8").split("\n")
            if len(lines) >= self.AUTO_MEMORY_LINES_LIMIT:
                await self.file_storage.archive_session(session_id)
        
        timestamped_content = f"\n## [{timestamp := __import__('datetime').datetime.now().isoformat()}]\n{content}\n"
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(timestamped_content)
        
        return memory_id
    
    def get_subagent_memory_dir(self, agent_name: str) -> Path:
        """Get the memory directory for a subagent.
        
        Args:
            agent_name: Name of the subagent
            
        Returns:
            Path to the subagent's memory directory
        """
        memory_dir = Path.home() / ".claude" / "agent-memory" / agent_name
        memory_dir.mkdir(parents=True, exist_ok=True)
        return memory_dir
    
    async def load_subagent_memory(
        self,
        agent_name: str,
        scope: str = "user",
    ) -> List[MemoryItem]:
        """Load memory for a specific subagent.
        
        Args:
            agent_name: Name of the subagent
            scope: Memory scope (user, project, local)
            
        Returns:
            List of memory items
        """
        if scope == "user":
            memory_dir = Path.home() / ".claude" / "agent-memory" / agent_name
        elif scope == "project":
            memory_dir = Path(self.project_root) / ".claude" / "agent-memory" / agent_name
        else:
            memory_dir = Path(self.project_root) / ".claude" / "agent-memory-local" / agent_name
        
        memory_file = memory_dir / "MEMORY.md"
        
        if not memory_file.exists():
            return []
        
        items = await self.file_storage.load(str(memory_file), resolve_imports=True)
        
        for item in items:
            item.metadata["subagent"] = agent_name
            item.metadata["scope"] = scope
        
        return items
    
    async def update_subagent_memory(
        self,
        agent_name: str,
        content: str,
        scope: str = "user",
    ) -> str:
        """Update memory for a specific subagent.
        
        Args:
            agent_name: Name of the subagent
            content: Content to add
            scope: Memory scope (user, project, local)
            
        Returns:
            Memory ID
        """
        if scope == "user":
            memory_dir = Path.home() / ".claude" / "agent-memory" / agent_name
        elif scope == "project":
            memory_dir = Path(self.project_root) / ".claude" / "agent-memory" / agent_name
        else:
            memory_dir = Path(self.project_root) / ".claude" / "agent-memory-local" / agent_name
        
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_file = memory_dir / "MEMORY.md"
        
        if memory_file.exists():
            lines = memory_file.read_text(encoding="utf-8").split("\n")
            if len(lines) >= self.AUTO_MEMORY_LINES_LIMIT:
                archive_result = await self._archive_subagent_topics(memory_dir, memory_file)
        
        memory_id = await self.write(
            content=content,
            memory_type=MemoryType.WORKING,
            metadata={"subagent": agent_name, "scope": scope},
        )
        
        timestamp = __import__('datetime').datetime.now().isoformat()
        with open(memory_file, "a", encoding="utf-8") as f:
            f.write(f"\n## [{timestamp}]\n{content}\n")
        
        return memory_id
    
    async def _archive_subagent_topics(
        self,
        memory_dir: Path,
        memory_file: Path,
    ) -> Dict[str, Any]:
        """Archive subagent memory to topic files."""
        topics_dir = memory_dir / "topics"
        topics_dir.mkdir(exist_ok=True)
        
        content = memory_file.read_text(encoding="utf-8")
        topics = await self.file_storage._extract_topics(content)
        
        saved_files = []
        for topic_name, topic_content in topics.items():
            topic_file = topics_dir / f"{topic_name}.md"
            topic_file.write_text(topic_content, encoding="utf-8")
            saved_files.append(str(topic_file))
        
        index_content = "# Memory Index\n\n"
        for topic_name in topics.keys():
            index_content += f"- @{topic_name}.md\n"
        memory_file.write_text(index_content, encoding="utf-8")
        
        return {
            "archived": True,
            "topics": list(topics.keys()),
            "files": saved_files,
        }
    
    async def create_claude_md_from_context(
        self,
        output_path: Optional[str] = None,
        include_imports: bool = True,
    ) -> str:
        """Create a CLAUDE.md file from accumulated context.
        
        Analyzes all memories and creates a structured CLAUDE.md file
        that can be shared with team members.
        
        Args:
            output_path: Output file path (defaults to project_root/CLAUDE.md)
            include_imports: Whether to include @import references
            
        Returns:
            Path to the created file
        """
        await self.initialize()
        
        items = [i for i in self._memory_cache.values() 
                 if i.memory_type in [MemoryType.SHARED, MemoryType.SEMANTIC, MemoryType.PREFERENCE]]
        
        if not output_path:
            output_path = str(Path(self.project_root) / "CLAUDE.md")
        
        content = "# Project Memory\n\n"
        content += f"<!-- Generated: {__import__('datetime').datetime.now().isoformat()} -->\n\n"
        
        if include_imports:
            items_by_source: Dict[str, List[MemoryItem]] = {}
            for item in items:
                source = item.source
                if source not in items_by_source:
                    items_by_source[source] = []
                items_by_source[source].append(item)
            
            for source, source_items in items_by_source.items():
                if source in ["project", "user", "file"]:
                    continue
                content += f"## {source.title()}\n\n"
                for item in source_items[:10]:
                    content += f"{item.content}\n\n"
        
        Path(output_path).write_text(content, encoding="utf-8")
        
        return output_path