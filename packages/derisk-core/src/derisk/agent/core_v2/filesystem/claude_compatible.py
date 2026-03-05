"""CLAUDE.md Compatibility Layer.

This module provides compatibility with Claude Code's CLAUDE.md format,
allowing seamless migration and interoperability.

CLAUDE.md Format:
    ---
    # YAML Front Matter
    priority: project
    scope: project
    tags: [architecture, decisions]
    ---

    # Markdown Content
    Project information here...

    @import path/to/other.md
"""

import re
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
import aiofiles

logger = logging.getLogger(__name__)


class ClaudeMdFrontMatter(BaseModel):
    """Represents the YAML front matter in a CLAUDE.md file."""
    priority: str = "project"
    scope: str = "project"
    tags: List[str] = Field(default_factory=list)
    author: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    imports: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class ClaudeMdSection(BaseModel):
    """Represents a section in a CLAUDE.md file."""
    title: str
    level: int
    content: str
    line_start: int
    line_end: int

    class Config:
        arbitrary_types_allowed = True


class ClaudeMdDocument(BaseModel):
    """Represents a parsed CLAUDE.md document."""
    path: Path
    front_matter: Optional[ClaudeMdFrontMatter] = None
    sections: List[ClaudeMdSection] = Field(default_factory=list)
    raw_content: str = ""
    imports: List[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


class ClaudeMdParser:
    """Parser for CLAUDE.md files.

    This parser handles:
    1. YAML front matter extraction
    2. Section structure parsing
    3. @import directive detection
    4. Content normalization

    Example:
        parser = ClaudeMdParser()
        doc = parser.parse_path(Path("CLAUDE.md"))
        print(doc.front_matter.priority)
        print(doc.sections[0].title)
    """

    # Regex patterns
    FRONT_MATTER_PATTERN = re.compile(
        r'^---\s*\n(.*?)\n---\s*\n',
        re.DOTALL
    )
    HEADING_PATTERN = re.compile(
        r'^(#{1,6})\s+(.+?)\s*$',
        re.MULTILINE
    )
    IMPORT_PATTERN = re.compile(
        r'@import\s+([^\s\n]+)'
    )

    @classmethod
    def parse(cls, content: str) -> ClaudeMdDocument:
        """Parse CLAUDE.md content.

        Args:
            content: The raw file content

        Returns:
            Parsed ClaudeMdDocument
        """
        doc = ClaudeMdDocument(path=Path("."), raw_content=content)

        # Extract front matter
        doc.front_matter = cls._parse_front_matter(content)

        # Remove front matter for section parsing
        content_without_fm = cls.FRONT_MATTER_PATTERN.sub('', content)

        # Parse sections
        doc.sections = cls._parse_sections(content_without_fm)

        # Extract imports
        doc.imports = cls._extract_imports(content)

        return doc

    @classmethod
    def parse_path(cls, path: Path) -> ClaudeMdDocument:
        """Parse a CLAUDE.md file from a path.

        Args:
            path: Path to the CLAUDE.md file

        Returns:
            Parsed ClaudeMdDocument
        """
        if not path.exists():
            logger.warning(f"File not found: {path}")
            return ClaudeMdDocument(path=path)

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return ClaudeMdDocument(path=path)

        doc = cls.parse(content)
        doc.path = path

        return doc

    @classmethod
    async def parse_path_async(cls, path: Path) -> ClaudeMdDocument:
        """Asynchronously parse a CLAUDE.md file.

        Args:
            path: Path to the CLAUDE.md file

        Returns:
            Parsed ClaudeMdDocument
        """
        if not path.exists():
            return ClaudeMdDocument(path=path)

        try:
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                content = await f.read()
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            return ClaudeMdDocument(path=path)

        doc = cls.parse(content)
        doc.path = path

        return doc

    @classmethod
    def _parse_front_matter(cls, content: str) -> Optional[ClaudeMdFrontMatter]:
        """Extract and parse YAML front matter."""
        match = cls.FRONT_MATTER_PATTERN.match(content)
        if not match:
            return None

        yaml_content = match.group(1)
        try:
            data = yaml.safe_load(yaml_content)
            if not isinstance(data, dict):
                return None

            return ClaudeMdFrontMatter(
                priority=data.get('priority', 'project'),
                scope=data.get('scope', 'project'),
                tags=data.get('tags', []),
                author=data.get('author'),
                created_at=data.get('created_at'),
                updated_at=data.get('updated_at'),
                imports=data.get('imports', []),
                metadata=data,
            )
        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse front matter: {e}")
            return None

    @classmethod
    def _parse_sections(cls, content: str) -> List[ClaudeMdSection]:
        """Parse markdown sections by headings."""
        sections = []
        lines = content.split('\n')

        current_section = None
        section_content = []
        line_start = 0

        for i, line in enumerate(lines):
            heading_match = cls.HEADING_PATTERN.match(line)

            if heading_match:
                # Save previous section
                if current_section:
                    current_section.content = '\n'.join(section_content).strip()
                    current_section.line_end = i - 1
                    sections.append(current_section)

                # Start new section
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                current_section = ClaudeMdSection(
                    title=title,
                    level=level,
                    content="",
                    line_start=i,
                    line_end=i,
                )
                section_content = []
            elif current_section:
                section_content.append(line)
            elif i == 0:
                line_start = i

        # Save last section
        if current_section:
            current_section.content = '\n'.join(section_content).strip()
            current_section.line_end = len(lines) - 1
            sections.append(current_section)

        return sections

    @classmethod
    def _extract_imports(cls, content: str) -> List[str]:
        """Extract @import directives from content."""
        return cls.IMPORT_PATTERN.findall(content)

    @classmethod
    def to_derisk_format(cls, doc: ClaudeMdDocument) -> str:
        """Convert a CLAUDE.md document to Derisk format.

        This creates a .derisk/MEMORY.md compatible format.

        Args:
            doc: Parsed ClaudeMdDocument

        Returns:
            Derisk-formatted markdown content
        """
        lines = []

        # Add header
        lines.append("# Project Memory (from CLAUDE.md)\n")

        # Add metadata if present
        if doc.front_matter:
            lines.append("> ")
            lines.append(f"> Priority: {doc.front_matter.priority}\n")
            if doc.front_matter.tags:
                lines.append(f"> Tags: {', '.join(doc.front_matter.tags)}\n")
            lines.append("\n")

        # Convert sections
        for section in doc.sections:
            heading_prefix = '#' * section.level
            lines.append(f"{heading_prefix} {section.title}\n\n")
            if section.content:
                lines.append(f"{section.content}\n\n")

        # Add import references
        if doc.imports:
            lines.append("## Imported Files\n\n")
            for imp in doc.imports:
                lines.append(f"- @import {imp}\n")

        return ''.join(lines)


class ClaudeCompatibleAdapter:
    """Adapter for Claude Code compatibility.

    This adapter provides:
    1. Detection of CLAUDE.md files
    2. Automatic conversion to Derisk format
    3. Import resolution across both formats

    Example:
        adapter = ClaudeCompatibleAdapter(Path("/project"))
        claude_files = adapter.detect_claude_files()
        await adapter.convert_to_derisk()
    """

    # Common CLAUDE.md file names
    CLAUDE_MD_FILES = ["CLAUDE.md", "claude.md", ".claude.md", "CLAUDE"]

    def __init__(self, project_root: Path):
        """Initialize the adapter.

        Args:
            project_root: Path to the project root directory
        """
        self.project_root = project_root
        self.derisk_dir = project_root / ".derisk"

    def detect_claude_files(self) -> List[Path]:
        """Detect CLAUDE.md files in the project.

        Returns:
            List of paths to CLAUDE.md files
        """
        found_files = []

        for filename in self.CLAUDE_MD_FILES:
            # Check project root
            file_path = self.project_root / filename
            if file_path.exists():
                found_files.append(file_path)

            # Check subdirectories (one level)
            for subdir in self.project_root.iterdir():
                if subdir.is_dir() and not subdir.name.startswith('.'):
                    subfile = subdir / filename
                    if subfile.exists():
                        found_files.append(subfile)

        return found_files

    async def convert_to_derisk(self, overwrite: bool = False) -> bool:
        """Convert detected CLAUDE.md files to Derisk format.

        Args:
            overwrite: Whether to overwrite existing .derisk/MEMORY.md

        Returns:
            True if conversion was successful
        """
        claude_files = self.detect_claude_files()
        if not claude_files:
            logger.info("No CLAUDE.md files detected")
            return False

        # Ensure .derisk directory exists
        self.derisk_dir.mkdir(parents=True, exist_ok=True)

        derisk_memory = self.derisk_dir / "MEMORY.md"

        # Check if already exists
        if derisk_memory.exists() and not overwrite:
            logger.info(f"{derisk_memory} already exists, skipping conversion")
            return False

        # Parse and convert all CLAUDE.md files
        all_sections = []
        all_imports = []
        combined_metadata = {}

        for claude_file in claude_files:
            doc = await ClaudeMdParser.parse_path_async(claude_file)

            if doc.front_matter:
                combined_metadata.update(doc.front_matter.metadata)

            all_sections.extend(doc.sections)
            all_imports.extend(doc.imports)

        # Generate combined content
        content = self._generate_combined_content(
            all_sections, all_imports, combined_metadata
        )

        # Write the converted file
        try:
            async with aiofiles.open(derisk_memory, 'w', encoding='utf-8') as f:
                await f.write(content)
            logger.info(f"Converted CLAUDE.md to {derisk_memory}")
            return True
        except Exception as e:
            logger.error(f"Failed to write {derisk_memory}: {e}")
            return False

    def _generate_combined_content(
        self,
        sections: List[ClaudeMdSection],
        imports: List[str],
        metadata: Dict[str, Any],
    ) -> str:
        """Generate combined Derisk memory content."""
        lines = []

        lines.append("# Project Memory\n\n")
        lines.append("> Auto-generated from CLAUDE.md\n\n")

        # Group sections by level
        level_1_sections = [s for s in sections if s.level == 1]
        other_sections = [s for s in sections if s.level != 1]

        # Add top-level sections
        for section in level_1_sections:
            lines.append(f"## {section.title}\n\n")
            if section.content:
                lines.append(f"{section.content}\n\n")

        # Add other sections
        for section in other_sections:
            prefix = '#' * (section.level + 1)
            lines.append(f"{prefix} {section.title}\n\n")
            if section.content:
                lines.append(f"{section.content}\n\n")

        # Add imports
        if imports:
            lines.append("## Imported Resources\n\n")
            for imp in set(imports):  # Deduplicate
                lines.append(f"- @import {imp}\n")

        return ''.join(lines)

    def create_derisk_from_claude(
        self,
        claude_content: str,
    ) -> Tuple[str, ClaudeMdDocument]:
        """Create Derisk format content from CLAUDE.md content.

        Args:
            claude_content: The raw CLAUDE.md content

        Returns:
            Tuple of (derisk_content, parsed_document)
        """
        doc = ClaudeMdParser.parse(claude_content)
        derisk_content = ClaudeMdParser.to_derisk_format(doc)
        return derisk_content, doc

    def get_import_resolution_map(self) -> Dict[str, Path]:
        """Get a map of import paths to actual file paths.

        Returns:
            Dictionary mapping import names to file paths
        """
        # This would scan for common import patterns
        resolution_map = {}

        # Check for common knowledge directories
        knowledge_dirs = ["knowledge", "docs", "context", ".claude"]
        for kd in knowledge_dirs:
            kd_path = self.project_root / kd
            if kd_path.exists() and kd_path.is_dir():
                for md_file in kd_path.glob("**/*.md"):
                    # Create relative import path
                    rel_path = md_file.relative_to(self.project_root)
                    resolution_map[str(rel_path)] = md_file
                    # Also add just the filename
                    resolution_map[md_file.name] = md_file

        return resolution_map


class ClaudeMdWatcher:
    """Watches for CLAUDE.md file changes and syncs to Derisk.

    This enables real-time synchronization between CLAUDE.md
    and the Derisk memory system.
    """

    def __init__(self, adapter: ClaudeCompatibleAdapter):
        """Initialize the watcher.

        Args:
            adapter: The ClaudeCompatibleAdapter to use for conversion
        """
        self.adapter = adapter
        self._watching = False
        self._last_modified: Dict[Path, float] = {}

    async def start_watching(self) -> None:
        """Start watching for CLAUDE.md file changes."""
        self._watching = True

        # Initial sync
        await self.sync_all()

        logger.info("Started watching CLAUDE.md files")

    async def stop_watching(self) -> None:
        """Stop watching for file changes."""
        self._watching = False
        logger.info("Stopped watching CLAUDE.md files")

    async def sync_all(self) -> int:
        """Sync all CLAUDE.md files to Derisk format.

        Returns:
            Number of files synced
        """
        claude_files = self.adapter.detect_claude_files()
        synced = 0

        for claude_file in claude_files:
            if await self._sync_file(claude_file):
                synced += 1

        return synced

    async def _sync_file(self, path: Path) -> bool:
        """Sync a single CLAUDE.md file."""
        try:
            stat = path.stat()
            last_mod = self._last_modified.get(path, 0)

            if stat.st_mtime > last_mod:
                self._last_modified[path] = stat.st_mtime
                await self.adapter.convert_to_derisk(overwrite=True)
                logger.debug(f"Synced {path}")
                return True

        except Exception as e:
            logger.error(f"Failed to sync {path}: {e}")

        return False


__all__ = [
    "ClaudeMdFrontMatter",
    "ClaudeMdSection",
    "ClaudeMdDocument",
    "ClaudeMdParser",
    "ClaudeCompatibleAdapter",
    "ClaudeMdWatcher",
]