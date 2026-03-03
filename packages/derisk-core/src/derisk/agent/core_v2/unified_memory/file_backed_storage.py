"""File-backed storage for Git-friendly memory sharing."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import MemoryItem, MemoryType, SearchOptions


class FileBackedStorage:
    """File-backed storage that supports Git-friendly memory sharing.
    
    Features:
    - Markdown format for easy editing and Git tracking
    - Support for @import syntax (Claude Code style)
    - Session isolation with gitignored local files
    - Team shared memory via version control
    """
    
    MEMORY_DIR_NAME = ".agent_memory"
    MEMORY_DIR_LOCAL = ".agent_memory.local"
    PROJECT_MEMORY_FILE = "PROJECT_MEMORY.md"
    TEAM_RULES_FILE = "TEAM_RULES.md"
    SESSION_DIR = "sessions"
    MEMORY_INDEX_FILE = "MEMORY.md"
    
    FILE_FORMAT_VERSION = "1.0"
    
    def __init__(self, project_root: str, session_id: Optional[str] = None):
        """Initialize file-backed storage.
        
        Args:
            project_root: Root directory of the project
            session_id: Optional session ID for session-specific memory
        """
        self.project_root = Path(project_root)
        self.session_id = session_id
        
        self.memory_dir = self.project_root / self.MEMORY_DIR_NAME
        self.memory_dir_local = self.project_root / self.MEMORY_DIR_LOCAL
        
        self._ensure_directories()
        
    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        (self.memory_dir / self.SESSION_DIR).mkdir(exist_ok=True)
        self.memory_dir_local.mkdir(parents=True, exist_ok=True)
        
        project_memory = self.memory_dir / self.PROJECT_MEMORY_FILE
        if not project_memory.exists():
            project_memory.write_text(self._create_header("Project Memory"))
    
    def _create_header(self, title: str) -> str:
        """Create a markdown header for memory files."""
        return f"""# {title}

<!-- Agent Memory File -->
<!-- Format Version: {self.FILE_FORMAT_VERSION} -->
<!-- Created: {datetime.now().isoformat()} -->

"""
    
    def _parse_memory_id(self, memory_id: str) -> Tuple[str, Optional[str]]:
        """Parse memory ID to get file path and item index.
        
        Args:
            memory_id: Memory ID (format: "file_path:line" or "file_path")
            
        Returns:
            Tuple of (file_path, line_number or None)
        """
        if ":" in memory_id:
            parts = memory_id.rsplit(":", 1)
            return parts[0], parts[1]
        return memory_id, None
    
    async def save(
        self,
        item: MemoryItem,
        sync_to_shared: bool = False,
    ) -> str:
        """Save a memory item to file.
        
        Args:
            item: Memory item to save
            sync_to_shared: Whether to save to shared memory file
            
        Returns:
            Memory ID
        """
        if item.memory_type == MemoryType.SHARED or sync_to_shared:
            file_path = self.memory_dir / self.PROJECT_MEMORY_FILE
        elif item.memory_type == MemoryType.WORKING and self.session_id:
            file_path = self._get_session_file(self.session_id)
        else:
            file_path = self.memory_dir_local / f"{item.memory_type.value}.md"
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        content_block = self._format_memory_block(item)
        
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content_block)
        
        return f"{file_path.name}:{item.id}"
    
    def _format_memory_block(self, item: MemoryItem) -> str:
        """Format a memory item as a markdown block."""
        metadata_str = json.dumps(item.metadata, ensure_ascii=False) if item.metadata else "{}"
        
        return f"""

---
memory_id: {item.id}
type: {item.memory_type.value}
importance: {item.importance}
created: {item.created_at.isoformat()}
source: {item.source}
metadata: {metadata_str}
---

{item.content}

"""
    
    async def load(
        self,
        file_path: str,
        resolve_imports: bool = True,
    ) -> List[MemoryItem]:
        """Load memory items from a file.
        
        Args:
            file_path: Path to the memory file
            resolve_imports: Whether to resolve @import references
            
        Returns:
            List of memory items
        """
        path = self.project_root / file_path if not os.path.isabs(file_path) else Path(file_path)
        
        if not path.exists():
            return []
        
        content = path.read_text(encoding="utf-8")
        
        if resolve_imports:
            content = self._resolve_imports(content)
        
        return self._parse_memory_blocks(content, str(path))
    
    def _resolve_imports(self, content: str) -> str:
        """Resolve @import references in content.
        
        Supports @path/to/file syntax from project root.
        Maximum recursion depth is 5.
        """
        return self._resolve_imports_recursive(content, depth=0)
    
    def _resolve_imports_recursive(self, content: str, depth: int) -> str:
        """Recursively resolve imports with depth limit."""
        if depth >= 5:
            return content
        
        pattern = r'@([a-zA-Z0-9_\-./]+\.[a-zA-Z]+)'
        
        def replace(match: re.Match) -> str:
            import_path = match.group(1)
            full_path = self.project_root / import_path
            
            if full_path.exists() and full_path.is_file():
                imported_content = full_path.read_text(encoding="utf-8")
                return self._resolve_imports_recursive(imported_content, depth + 1)
            return match.group(0)
        
        return re.sub(pattern, replace, content)
    
    def _parse_memory_blocks(
        self,
        content: str,
        file_path: str,
    ) -> List[MemoryItem]:
        """Parse memory blocks from markdown content."""
        items = []
        
        blocks = re.split(r'\n---\n', content)
        
        for i in range(0, len(blocks) - 1, 2):
            if i + 1 >= len(blocks):
                break
                
            header = blocks[i].strip()
            body = blocks[i + 1].strip()
            
            if not header.startswith("memory_id"):
                continue
            
            item = self._parse_header_and_body(header, body, file_path)
            if item:
                items.append(item)
        
        return items
    
    def _parse_header_and_body(
        self,
        header: str,
        body: str,
        file_path: str,
    ) -> Optional[MemoryItem]:
        """Parse header and body to create MemoryItem."""
        try:
            metadata: Dict[str, Any] = {}
            for line in header.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()
            
            memory_id = metadata.get("memory_id", "")
            memory_type = MemoryType(metadata.get("type", "working"))
            importance = float(metadata.get("importance", "0.5"))
            created = datetime.fromisoformat(metadata["created"]) if "created" in metadata else datetime.now()
            source = metadata.get("source", "file")
            extra_metadata = json.loads(metadata.get("metadata", "{}"))
            
            return MemoryItem(
                id=memory_id,
                content=body,
                memory_type=memory_type,
                importance=importance,
                created_at=created,
                source=source,
                file_path=file_path,
                metadata=extra_metadata,
            )
        except Exception:
            return None
    
    def _get_session_file(self, session_id: str) -> Path:
        """Get the memory file path for a session."""
        session_dir = self.memory_dir_local / self.SESSION_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / self.MEMORY_INDEX_FILE
    
    async def load_shared_memory(self) -> List[MemoryItem]:
        """Load all shared memory files.
        
        This includes:
        - PROJECT_MEMORY.md (project-level shared)
        - TEAM_RULES.md (team rules)
        - User-level memory (~/.agent_memory/CLAUDE.md style)
        """
        items = []
        
        project_memory = self.memory_dir / self.PROJECT_MEMORY_FILE
        if project_memory.exists():
            items.extend(await self.load(str(project_memory)))
        
        team_rules = self.memory_dir / self.TEAM_RULES_FILE
        if team_rules.exists():
            items.extend(await self.load(str(team_rules)))
        
        user_memory = Path.home() / ".agent_memory" / "USER_MEMORY.md"
        if user_memory.exists():
            user_items = await self.load(str(user_memory), resolve_imports=False)
            for item in user_items:
                item.source = "user"
            items.extend(user_items)
        
        return items
    
    async def load_session_memory(self, session_id: str) -> List[MemoryItem]:
        """Load memory for a specific session."""
        session_file = self._get_session_file(session_id)
        if session_file.exists():
            return await self.load(str(session_file), resolve_imports=False)
        return []
    
    async def archive_session(self, session_id: str) -> Dict[str, Any]:
        """Archive a session's memory.
        
        Moves session memory to topic-based files if it exceeds 200 lines.
        
        Returns:
            Archive statistics
        """
        session_file = self._get_session_file(session_id)
        
        if not session_file.exists():
            return {"archived": False, "reason": "No session file"}
        
        content = session_file.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        if len(lines) <= 200:
            return {"archived": False, "lines": len(lines)}
        
        topic_dir = session_file.parent / "topics"
        topic_dir.mkdir(exist_ok=True)
        
        topics = await self._extract_topics(content)
        
        saved_files = []
        for topic_name, topic_content in topics.items():
            topic_file = topic_dir / f"{topic_name}.md"
            topic_file.write_text(topic_content, encoding="utf-8")
            saved_files.append(str(topic_file))
        
        index_content = "# Memory Index\n\n"
        for topic_name in topics.keys():
            index_content += f"- @{topic_name}.md\n"
        session_file.write_text(index_content, encoding="utf-8")
        
        return {
            "archived": True,
            "original_lines": len(lines),
            "topics": list(topics.keys()),
            "files": saved_files,
        }
    
    async def _extract_topics(
        self,
        content: str,
    ) -> Dict[str, str]:
        """Extract topics from content (placeholder for LLM-based extraction)."""
        topics: Dict[str, str] = {}
        
        sections = re.split(r'\n##\s+', content)
        
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            
            lines = section.strip().split("\n")
            if lines:
                topic_name = re.sub(r'[^\w\-]', '_', lines[0].lower())[:50]
                if not topic_name:
                    topic_name = f"topic_{i}"
                topics[topic_name] = f"## {section}"
        
        return topics
    
    async def export(
        self,
        output_path: str,
        memory_types: Optional[List[MemoryType]] = None,
        format: str = "markdown",
    ) -> int:
        """Export memory to a file.
        
        Args:
            output_path: Output file path
            memory_types: Types to export (all if None)
            format: Export format (markdown, json)
            
        Returns:
            Number of items exported
        """
        items = await self.load_shared_memory()
        
        if memory_types:
            items = [i for i in items if i.memory_type in memory_types]
        
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "json":
            data = [item.to_dict() for item in items]
            output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            content = self._create_header("Exported Memory")
            for item in items:
                content += self._format_memory_block(item)
            output.write_text(content, encoding="utf-8")
        
        return len(items)
    
    async def get_gitignore_patterns(self) -> List[str]:
        """Get patterns to add to .gitignore."""
        return [
            "# Agent Memory",
            f"/{self.MEMORY_DIR_LOCAL}/",
            f"/{self.MEMORY_DIR_NAME}/{self.SESSION_DIR}/",
        ]
    
    async def ensure_gitignore(self) -> bool:
        """Ensure .gitignore contains memory patterns."""
        gitignore_path = self.project_root / ".gitignore"
        patterns = await self.get_gitignore_patterns()
        
        if not gitignore_path.exists():
            gitignore_path.write_text("\n".join(patterns) + "\n", encoding="utf-8")
            return True
        
        content = gitignore_path.read_text(encoding="utf-8")
        updated = False
        
        for pattern in patterns:
            if pattern not in content and not pattern.startswith("#"):
                content += f"\n{pattern}"
                updated = True
        
        if updated:
            gitignore_path.write_text(content, encoding="utf-8")
        
        return updated