"""History Archive Data Models.

HistoryChapter and HistoryCatalog for chapter-based history archival
in the unified compaction pipeline.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclasses.dataclass
class HistoryChapter:
    """A single archived chapter — product of one compaction cycle."""

    chapter_id: str
    chapter_index: int
    time_range: Tuple[float, float]
    message_count: int
    tool_call_count: int
    summary: str
    key_tools: List[str]
    key_decisions: List[str]
    file_key: str
    token_estimate: int
    created_at: float
    work_log_summary_id: Optional[str] = None
    skill_outputs: List[str] = dataclasses.field(default_factory=list)
    skill_outputs: List[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "HistoryChapter":
        return cls(**data)

    def to_catalog_entry(self) -> str:
        start = time.strftime("%H:%M:%S", time.localtime(self.time_range[0]))
        end = time.strftime("%H:%M:%S", time.localtime(self.time_range[1]))
        tools_str = ", ".join(self.key_tools[:5])
        return (
            f"Chapter {self.chapter_index}: [{start} - {end}] "
            f"{self.message_count} msgs, {self.tool_call_count} tool calls | "
            f"Tools: {tools_str}\n"
            f"Summary: {self.summary[:200]}"
        )


@dataclasses.dataclass
class HistoryCatalog:
    """Index of all chapters in a session, persisted via AgentFileSystem."""

    conv_id: str
    session_id: str
    chapters: List[HistoryChapter] = dataclasses.field(default_factory=list)
    total_messages: int = 0
    total_tool_calls: int = 0
    current_chapter_index: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def add_chapter(self, chapter: HistoryChapter) -> None:
        self.chapters.append(chapter)
        self.total_messages += chapter.message_count
        self.total_tool_calls += chapter.tool_call_count
        self.current_chapter_index = chapter.chapter_index + 1
        self.updated_at = chapter.created_at

    def get_chapter(self, index: int) -> Optional[HistoryChapter]:
        for ch in self.chapters:
            if ch.chapter_index == index:
                return ch
        return None

    def get_overview(self) -> str:
        lines = [
            "=== History Catalog ===",
            f"Session: {self.session_id}",
            f"Total: {self.total_messages} messages, "
            f"{self.total_tool_calls} tool calls, "
            f"{len(self.chapters)} chapters",
            "",
        ]
        for ch in self.chapters:
            lines.append(ch.to_catalog_entry())
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "total_messages": self.total_messages,
            "total_tool_calls": self.total_tool_calls,
            "current_chapter_index": self.current_chapter_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "HistoryCatalog":
        chapters_data = data.pop("chapters", [])
        catalog = cls(**data)
        catalog.chapters = [HistoryChapter.from_dict(ch) for ch in chapters_data]
        return catalog
