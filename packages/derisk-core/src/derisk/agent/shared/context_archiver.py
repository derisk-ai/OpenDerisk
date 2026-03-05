"""
ContextArchiver - 上下文自动归档器

实现工具调用结果的自动归档、大文件管理、上下文压缩联动。
作为共享基础设施，可供 Core V1 和 Core V2 共同使用。

核心能力：
1. 工具输出超阈值自动归档到文件系统
2. 上下文压力触发自动归档
3. 归档内容按需恢复
4. 与 MemoryCompaction 联动
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from derisk.agent.core.file_system.agent_file_system import AgentFileSystem
    from derisk.agent.core.memory.gpts import FileType

logger = logging.getLogger(__name__)


class ArchiveTrigger(str, Enum):
    """归档触发原因"""
    SIZE_THRESHOLD = "size_threshold"
    CONTEXT_PRESSURE = "context_pressure"
    MANUAL = "manual"
    SKILL_EXIT = "skill_exit"
    SESSION_END = "session_end"


class ContentType(str, Enum):
    """内容类型"""
    TOOL_OUTPUT = "tool_output"
    THINKING = "thinking"
    MEMORY = "memory"
    SKILL_CONTENT = "skill_content"
    REASONING_TRACE = "reasoning_trace"


@dataclass
class ArchiveRule:
    """归档规则配置"""
    content_type: ContentType
    max_tokens: int = 2000
    compress: bool = True
    keep_preview: int = 500
    auto_archive: bool = True
    priority: int = 5


@dataclass
class ArchiveEntry:
    """归档条目"""
    reference_id: str
    content_type: ContentType
    file_id: str
    file_name: str
    oss_url: Optional[str] = None
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    original_tokens: int = 0
    original_size: int = 0
    archived_at: float = field(default_factory=time.time)
    trigger: ArchiveTrigger = ArchiveTrigger.SIZE_THRESHOLD
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "content_type": self.content_type.value,
            "file_id": self.file_id,
            "file_name": self.file_name,
            "oss_url": self.oss_url,
            "preview_url": self.preview_url,
            "download_url": self.download_url,
            "original_tokens": self.original_tokens,
            "original_size": self.original_size,
            "archived_at": self.archived_at,
            "trigger": self.trigger.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArchiveEntry":
        return cls(
            reference_id=data["reference_id"],
            content_type=ContentType(data["content_type"]),
            file_id=data["file_id"],
            file_name=data["file_name"],
            oss_url=data.get("oss_url"),
            preview_url=data.get("preview_url"),
            download_url=data.get("download_url"),
            original_tokens=data.get("original_tokens", 0),
            original_size=data.get("original_size", 0),
            archived_at=data.get("archived_at", time.time()),
            trigger=ArchiveTrigger(data.get("trigger", "size_threshold")),
            metadata=data.get("metadata", {}),
        )


class ContextArchiver:
    """
    上下文自动归档器
    
    核心职责：
    1. 监控工具输出大小，超阈值自动归档
    2. 上下文压力触发自动归档历史内容
    3. 在上下文中保留摘要/预览+引用
    4. 支持按需恢复完整内容
    
    使用示例：
        archiver = ContextArchiver(file_system=afs)
        
        # 处理工具输出
        result = await archiver.process_tool_output(
            tool_name="bash",
            output=large_output,
        )
        
        if result["archived"]:
            print(f"已归档：{result['archive_ref']['file_id']}")
    
    设计原则：
    - 与 AgentFileSystem 集成，统一文件管理
    - 支持多种内容类型的归档策略
    - 提供预览机制，平衡上下文占用和可追溯性
    """
    
    DEFAULT_RULES: Dict[ContentType, ArchiveRule] = {
        ContentType.TOOL_OUTPUT: ArchiveRule(
            content_type=ContentType.TOOL_OUTPUT,
            max_tokens=2000,
            compress=True,
            keep_preview=500,
        ),
        ContentType.THINKING: ArchiveRule(
            content_type=ContentType.THINKING,
            max_tokens=4000,
            compress=False,
            keep_preview=1000,
        ),
        ContentType.MEMORY: ArchiveRule(
            content_type=ContentType.MEMORY,
            max_tokens=6000,
            compress=True,
            keep_preview=300,
        ),
        ContentType.SKILL_CONTENT: ArchiveRule(
            content_type=ContentType.SKILL_CONTENT,
            max_tokens=3000,
            compress=True,
            keep_preview=500,
        ),
        ContentType.REASONING_TRACE: ArchiveRule(
            content_type=ContentType.REASONING_TRACE,
            max_tokens=4000,
            compress=False,
            keep_preview=800,
        ),
    }
    
    def __init__(
        self,
        file_system: "AgentFileSystem",
        default_threshold_tokens: int = 2000,
        auto_archive: bool = True,
        rules: Optional[Dict[ContentType, ArchiveRule]] = None,
    ):
        self.file_system = file_system
        self.default_threshold_tokens = default_threshold_tokens
        self.auto_archive_enabled = auto_archive
        self.rules = rules or self.DEFAULT_RULES
        
        self._archives: Dict[str, ArchiveEntry] = {}
        self._session_archives: Dict[str, List[str]] = {}
        self._total_archived_tokens: int = 0
        self._archive_count: int = 0
    
    @property
    def session_id(self) -> str:
        return self.file_system.session_id
    
    @property
    def conv_id(self) -> str:
        return self.file_system.conv_id
    
    def _estimate_tokens(self, content: str) -> int:
        if not content:
            return 0
        return len(content) // 4
    
    def _generate_reference_id(
        self,
        content_type: ContentType,
        tool_name: Optional[str] = None,
    ) -> str:
        timestamp = int(time.time() * 1000)
        prefix = f"archive_{content_type.value}"
        if tool_name:
            prefix = f"{prefix}_{tool_name}"
        return f"{prefix}_{timestamp}_{self._archive_count}"
    
    async def process_tool_output(
        self,
        tool_name: str,
        output: Any,
        metadata: Optional[Dict[str, Any]] = None,
        force_archive: bool = False,
    ) -> Dict[str, Any]:
        if not isinstance(output, str):
            output_str = json.dumps(output, ensure_ascii=False, indent=2)
        else:
            output_str = output
        
        output_tokens = self._estimate_tokens(output_str)
        rule = self.rules.get(ContentType.TOOL_OUTPUT)
        
        should_archive = force_archive or (
            self.auto_archive_enabled
            and rule
            and rule.auto_archive
            and output_tokens > rule.max_tokens
        )
        
        if should_archive:
            return await self._archive_content(
                content=output_str,
                content_type=ContentType.TOOL_OUTPUT,
                reference_id=self._generate_reference_id(ContentType.TOOL_OUTPUT, tool_name),
                trigger=ArchiveTrigger.SIZE_THRESHOLD if not force_archive else ArchiveTrigger.MANUAL,
                metadata={
                    "tool_name": tool_name,
                    "original_tokens": output_tokens,
                    **(metadata or {}),
                },
                keep_preview=rule.keep_preview if rule else 500,
            )
        
        return {
            "content": output_str,
            "archived": False,
            "original_tokens": output_tokens,
        }
    
    async def archive_thinking(
        self,
        thinking_content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        thinking_tokens = self._estimate_tokens(thinking_content)
        rule = self.rules.get(ContentType.THINKING)
        
        if thinking_tokens > (rule.max_tokens if rule else 4000):
            return await self._archive_content(
                content=thinking_content,
                content_type=ContentType.THINKING,
                reference_id=self._generate_reference_id(ContentType.THINKING),
                trigger=ArchiveTrigger.SIZE_THRESHOLD,
                metadata={
                    "original_tokens": thinking_tokens,
                    **(metadata or {}),
                },
                keep_preview=rule.keep_preview if rule else 1000,
            )
        
        return {"content": thinking_content, "archived": False}
    
    async def archive_skill_content(
        self,
        skill_name: str,
        content: str,
        summary: Optional[str] = None,
        key_results: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        content_tokens = self._estimate_tokens(content)
        rule = self.rules.get(ContentType.SKILL_CONTENT)
        
        result = await self._archive_content(
            content=content,
            content_type=ContentType.SKILL_CONTENT,
            reference_id=f"skill_{skill_name}_archive_{int(time.time()*1000)}",
            trigger=ArchiveTrigger.SKILL_EXIT,
            metadata={
                "skill_name": skill_name,
                "original_tokens": content_tokens,
                "summary": summary,
                "key_results": key_results or [],
            },
            keep_preview=rule.keep_preview if rule else 500,
        )
        
        if summary:
            preview = self._create_skill_preview(skill_name, summary, key_results)
            result["content"] = preview
        
        return result
    
    def _create_skill_preview(
        self,
        skill_name: str,
        summary: str,
        key_results: Optional[List[str]] = None,
    ) -> str:
        lines = [
            f"<skill-exit name=\"{skill_name}\">",
            f"<summary>{summary}</summary>",
        ]
        
        if key_results:
            lines.append("<key-results>")
            for kr in key_results[:5]:
                lines.append(f"  - {kr}")
            lines.append("</key-results>")
        
        lines.append("</skill-exit>")
        return "\n".join(lines)
    
    async def _archive_content(
        self,
        content: str,
        content_type: ContentType,
        reference_id: str,
        trigger: ArchiveTrigger,
        metadata: Dict[str, Any],
        keep_preview: int = 500,
    ) -> Dict[str, Any]:
        from derisk.agent.core.memory.gpts import FileType
        
        file_type_map = {
            ContentType.TOOL_OUTPUT: FileType.TRUNCATED_OUTPUT,
            ContentType.THINKING: FileType.TOOL_OUTPUT,
            ContentType.MEMORY: FileType.TOOL_OUTPUT,
            ContentType.SKILL_CONTENT: FileType.TOOL_OUTPUT,
            ContentType.REASONING_TRACE: FileType.TOOL_OUTPUT,
        }
        
        file_metadata = await self.file_system.save_file(
            file_key=reference_id,
            data=content,
            file_type=file_type_map.get(content_type, FileType.TOOL_OUTPUT),
            extension="txt",
            metadata={
                "content_type": content_type.value,
                "trigger": trigger.value,
                **metadata,
            },
        )
        
        entry = ArchiveEntry(
            reference_id=reference_id,
            content_type=content_type,
            file_id=file_metadata.file_id,
            file_name=file_metadata.file_name,
            oss_url=file_metadata.oss_url,
            preview_url=file_metadata.preview_url,
            download_url=file_metadata.download_url,
            original_tokens=metadata.get("original_tokens", self._estimate_tokens(content)),
            original_size=len(content),
            trigger=trigger,
            metadata=metadata,
        )
        
        self._archives[reference_id] = entry
        
        session_id = self.session_id
        if session_id not in self._session_archives:
            self._session_archives[session_id] = []
        self._session_archives[session_id].append(reference_id)
        
        self._total_archived_tokens += entry.original_tokens
        self._archive_count += 1
        
        logger.info(
            f"[ContextArchiver] Archived {content_type.value}: "
            f"{reference_id} ({entry.original_tokens} tokens, trigger={trigger.value})"
        )
        
        preview = content[:keep_preview]
        if len(content) > keep_preview:
            preview += f"\n\n... [内容已归档，共 {len(content)} 字符，{entry.original_tokens} tokens]"
        
        return {
            "content": preview,
            "archived": True,
            "archive_ref": {
                "reference_id": reference_id,
                "file_id": file_metadata.file_id,
                "file_name": file_metadata.file_name,
                "download_url": file_metadata.download_url,
                "preview_url": file_metadata.preview_url,
                "original_tokens": entry.original_tokens,
            },
        }
    
    async def restore_content(self, reference_id: str) -> Optional[str]:
        entry = self._archives.get(reference_id)
        if not entry:
            logger.warning(f"[ContextArchiver] Archive not found: {reference_id}")
            return None
        
        content = await self.file_system.read_file(reference_id)
        if content:
            logger.info(f"[ContextArchiver] Restored: {reference_id}")
        return content
    
    async def batch_restore(
        self,
        reference_ids: List[str],
    ) -> Dict[str, Optional[str]]:
        results = {}
        for ref_id in reference_ids:
            results[ref_id] = await self.restore_content(ref_id)
        return results
    
    async def auto_archive_for_pressure(
        self,
        current_tokens: int,
        budget_tokens: int,
        pressure_threshold: float = 0.8,
    ) -> List[Dict[str, Any]]:
        if current_tokens < budget_tokens * pressure_threshold:
            return []
        
        archived_refs = []
        target_reduction = int(current_tokens - budget_tokens * 0.6)
        
        candidates = sorted(
            self._archives.values(),
            key=lambda e: (e.metadata.get("priority", 5), e.archived_at),
        )
        
        reduced_tokens = 0
        for entry in candidates:
            if reduced_tokens >= target_reduction:
                break
            
            if entry.content_type in (ContentType.THINKING, ContentType.REASONING_TRACE):
                continue
            
            archived_refs.append({
                "reference_id": entry.reference_id,
                "original_tokens": entry.original_tokens,
                "content_type": entry.content_type.value,
            })
            reduced_tokens += entry.original_tokens
        
        logger.info(
            f"[ContextArchiver] Auto-archive for pressure: "
            f"reduced {reduced_tokens} tokens via {len(archived_refs)} archives"
        )
        
        return archived_refs
    
    def get_archive(self, reference_id: str) -> Optional[ArchiveEntry]:
        return self._archives.get(reference_id)
    
    def list_archives(
        self,
        content_type: Optional[ContentType] = None,
        session_id: Optional[str] = None,
    ) -> List[ArchiveEntry]:
        archives = list(self._archives.values())
        
        if content_type:
            archives = [a for a in archives if a.content_type == content_type]
        
        if session_id:
            ref_ids = self._session_archives.get(session_id, [])
            archives = [a for a in archives if a.reference_id in ref_ids]
        
        return archives
    
    def get_statistics(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for entry in self._archives.values():
            ct = entry.content_type.value
            by_type[ct] = by_type.get(ct, 0) + 1
        
        return {
            "total_archives": len(self._archives),
            "total_archived_tokens": self._total_archived_tokens,
            "archive_count": self._archive_count,
            "by_content_type": by_type,
            "sessions": len(self._session_archives),
        }
    
    async def export_archives_manifest(self) -> Dict[str, Any]:
        return {
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "archives": [a.to_dict() for a in self._archives.values()],
            "statistics": self.get_statistics(),
            "exported_at": datetime.utcnow().isoformat(),
        }
    
    async def import_archives_manifest(
        self,
        manifest: Dict[str, Any],
    ) -> int:
        imported = 0
        for archive_data in manifest.get("archives", []):
            try:
                entry = ArchiveEntry.from_dict(archive_data)
                self._archives[entry.reference_id] = entry
                imported += 1
            except Exception as e:
                logger.warning(f"[ContextArchiver] Failed to import archive: {e}")
        
        logger.info(f"[ContextArchiver] Imported {imported} archives from manifest")
        return imported


async def create_context_archiver(
    file_system: "AgentFileSystem",
    config: Optional[Dict[str, Any]] = None,
) -> ContextArchiver:
    config = config or {}
    
    return ContextArchiver(
        file_system=file_system,
        default_threshold_tokens=config.get("threshold_tokens", 2000),
        auto_archive=config.get("auto_archive", True),
        rules=config.get("rules"),
    )


__all__ = [
    "ContextArchiver",
    "ArchiveRule",
    "ArchiveEntry",
    "ArchiveTrigger",
    "ContentType",
    "create_context_archiver",
]