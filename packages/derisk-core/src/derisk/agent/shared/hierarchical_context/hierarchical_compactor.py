"""
分层上下文压缩器 (Hierarchical Context Compactor)

基于LLM的智能压缩：
1. 章节摘要生成
2. 节内容压缩
3. 结构化摘要模板（参考OpenCode）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .hierarchical_context_index import (
    Chapter,
    ContentPriority,
    Section,
    TaskPhase,
)

if TYPE_CHECKING:
    from derisk.core import LLMClient, ModelMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


@dataclass
class CompactionTemplate:
    CHAPTER_SUMMARY_TEMPLATE = """请为以下任务阶段生成一个结构化的摘要。

## 阶段信息
- 阶段名称: {title}
- 阶段类型: {phase}
- 执行步骤数: {section_count}

## 执行步骤概览
{sections_overview}

## 请按以下格式生成摘要:

### 目标 (Goal)
[这个阶段要达成什么目标？]

### 完成事项 (Accomplished)
[已完成的主要工作和结果]

### 关键发现 (Discoveries)
[在执行过程中的重要发现和洞察]

### 待处理 (Remaining)
[还有什么需要后续跟进的事项？]

### 相关文件 (Relevant Files)
[涉及的文件和资源列表]
"""

    SECTION_COMPACT_TEMPLATE = """请压缩以下执行步骤的内容，保留关键信息。

步骤名称: {step_name}
优先级: {priority}
原始内容:
{content}

请生成简洁的摘要（保留关键决策、结果和下一步行动）:
"""

    MULTI_SECTION_COMPACT_TEMPLATE = """请将以下多个相关执行步骤压缩为一个简洁的摘要。

步骤列表:
{sections_content}

请生成：
1. 这些步骤的共同目标
2. 主要执行结果
3. 关键决策和发现
4. 需要注意的事项
"""


@dataclass
class CompactionResult:
    success: bool
    original_tokens: int
    compacted_tokens: int
    summary: Optional[str] = None
    error: Optional[str] = None


class HierarchicalCompactor:
    """
    分层上下文压缩器

    使用LLM进行智能压缩：
    1. 章节级压缩：生成结构化摘要
    2. 节级压缩：保留关键信息
    3. 批量压缩：多个节合并压缩

    使用示例:
        compactor = HierarchicalCompactor(llm_client=client)

        # 压缩章节
        result = await compactor.compact_chapter(chapter)

        # 压缩节
        result = await compactor.compact_section(section)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_summary_tokens: int = 500,
        max_section_compact_tokens: int = 200,
        enable_structured_output: bool = True,
    ):
        self.llm_client = llm_client
        self.max_summary_tokens = max_summary_tokens
        self.max_section_compact_tokens = max_section_compact_tokens
        self.enable_structured_output = enable_structured_output

        self._compaction_history: List[Dict[str, Any]] = []

        logger.info(
            f"[Layer3:HierarchicalCompaction] INIT | llm_client={'set' if llm_client else 'none'}, "
            f"max_summary_tokens={max_summary_tokens}, "
            f"max_section_compact_tokens={max_section_compact_tokens}"
        )

    def set_llm_client(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client
        logger.info("[Layer3:HierarchicalCompaction] LLM_CLIENT_SET")

    async def compact_chapter(
        self,
        chapter: Chapter,
        force: bool = False,
    ) -> CompactionResult:
        logger.info(
            f"[Layer3:HierarchicalCompaction] COMPACT_CHAPTER_START | "
            f"chapter_id={chapter.chapter_id[:8]}, title={chapter.title}, "
            f"sections={len(chapter.sections)}, is_compacted={chapter.is_compacted}, force={force}"
        )

        if chapter.is_compacted and not force:
            logger.info(
                f"[Layer3:HierarchicalCompaction] COMPACT_CHAPTER_SKIP | "
                f"chapter_id={chapter.chapter_id[:8]} | reason=already_compacted"
            )
            return CompactionResult(
                success=True,
                original_tokens=chapter.tokens,
                compacted_tokens=len(chapter.summary) // 4 if chapter.summary else 0,
                summary=chapter.summary,
            )

        if not self.llm_client:
            logger.info(
                f"[Layer3:HierarchicalCompaction] COMPACT_CHAPTER_SIMPLE | "
                f"chapter_id={chapter.chapter_id[:8]} | reason=no_llm_client"
            )
            return self._simple_chapter_summary(chapter)

        try:
            sections_overview = self._format_sections_overview(chapter.sections)

            prompt = CompactionTemplate.CHAPTER_SUMMARY_TEMPLATE.format(
                title=chapter.title,
                phase=chapter.phase.value,
                section_count=len(chapter.sections),
                sections_overview=sections_overview,
            )

            logger.debug(
                f"[Layer3:HierarchicalCompaction] COMPACT_CHAPTER_LLM_CALL | "
                f"chapter_id={chapter.chapter_id[:8]} | prompt_length={len(prompt)}"
            )

            summary = await self._call_llm(prompt)

            if summary:
                chapter.summary = summary
                chapter.is_compacted = True

                original_tokens = chapter.tokens
                chapter.tokens = len(summary) // 4 + sum(
                    len(s.content) // 4 for s in chapter.sections
                )

                self._record_compaction(
                    "chapter", chapter.chapter_id, original_tokens, chapter.tokens
                )

                compression_ratio = (
                    chapter.tokens / original_tokens if original_tokens > 0 else 0
                )
                logger.info(
                    f"[Layer3:HierarchicalCompaction] COMPACT_CHAPTER_COMPLETE | "
                    f"chapter_id={chapter.chapter_id[:8]} | "
                    f"original={original_tokens}tokens -> compacted={chapter.tokens}tokens | "
                    f"compression_ratio={compression_ratio:.1%} | "
                    f"saved={original_tokens - chapter.tokens}tokens"
                )

                return CompactionResult(
                    success=True,
                    original_tokens=original_tokens,
                    compacted_tokens=chapter.tokens,
                    summary=summary,
                )

            logger.warning(
                f"[Layer3:HierarchicalCompaction] COMPACT_CHAPTER_FAIL | "
                f"chapter_id={chapter.chapter_id[:8]} | reason=empty_summary"
            )
            return CompactionResult(
                success=False,
                original_tokens=chapter.tokens,
                compacted_tokens=chapter.tokens,
                error="Failed to generate summary",
            )

        except Exception as e:
            logger.error(
                f"[Layer3:HierarchicalCompaction] COMPACT_CHAPTER_ERROR | "
                f"chapter_id={chapter.chapter_id[:8]} | error={e}"
            )
            return CompactionResult(
                success=False,
                original_tokens=chapter.tokens,
                compacted_tokens=chapter.tokens,
                error=str(e),
            )

    async def compact_section(
        self,
        section: Section,
        preserve_critical: bool = True,
    ) -> CompactionResult:
        logger.info(
            f"[Layer3:HierarchicalCompaction] COMPACT_SECTION_START | "
            f"section_id={section.section_id[:8]}, step_name={section.step_name}, "
            f"priority={section.priority.value}, preserve_critical={preserve_critical}"
        )

        if preserve_critical and section.priority == ContentPriority.CRITICAL:
            logger.info(
                f"[Layer3:HierarchicalCompaction] COMPACT_SECTION_SKIP | "
                f"section_id={section.section_id[:8]} | reason=critical_priority"
            )
            return CompactionResult(
                success=True,
                original_tokens=section.tokens,
                compacted_tokens=section.tokens,
                summary=section.content,
            )

        if not self.llm_client:
            logger.info(
                f"[Layer3:HierarchicalCompaction] COMPACT_SECTION_SIMPLE | "
                f"section_id={section.section_id[:8]} | reason=no_llm_client"
            )
            return self._simple_section_summary(section)

        try:
            prompt = CompactionTemplate.SECTION_COMPACT_TEMPLATE.format(
                step_name=section.step_name,
                priority=section.priority.value,
                content=section.content[:2000],
            )

            logger.debug(
                f"[Layer3:HierarchicalCompaction] COMPACT_SECTION_LLM_CALL | "
                f"section_id={section.section_id[:8]} | prompt_length={len(prompt)}"
            )

            summary = await self._call_llm(
                prompt, max_tokens=self.max_section_compact_tokens
            )

            if summary:
                original_tokens = section.tokens
                original_content = section.content

                section.content = summary
                section.tokens = len(summary) // 4

                if section.metadata is None:
                    section.metadata = {}
                section.metadata["original_content_preview"] = original_content[:200]
                section.metadata["was_compacted"] = True

                self._record_compaction(
                    "section", section.section_id, original_tokens, section.tokens
                )

                compression_ratio = (
                    section.tokens / original_tokens if original_tokens > 0 else 0
                )
                logger.info(
                    f"[Layer3:HierarchicalCompaction] COMPACT_SECTION_COMPLETE | "
                    f"section_id={section.section_id[:8]} | "
                    f"original={original_tokens}tokens -> compacted={section.tokens}tokens | "
                    f"compression_ratio={compression_ratio:.1%} | "
                    f"saved={original_tokens - section.tokens}tokens"
                )

                return CompactionResult(
                    success=True,
                    original_tokens=original_tokens,
                    compacted_tokens=section.tokens,
                    summary=summary,
                )

            logger.warning(
                f"[Layer3:HierarchicalCompaction] COMPACT_SECTION_FAIL | "
                f"section_id={section.section_id[:8]} | reason=empty_summary"
            )
            return CompactionResult(
                success=False,
                original_tokens=section.tokens,
                compacted_tokens=section.tokens,
                error="Failed to generate summary",
            )

        except Exception as e:
            logger.error(
                f"[Layer3:HierarchicalCompaction] COMPACT_SECTION_ERROR | "
                f"section_id={section.section_id[:8]} | error={e}"
            )
            return CompactionResult(
                success=False,
                original_tokens=section.tokens,
                compacted_tokens=section.tokens,
                error=str(e),
            )

    async def compact_sections_batch(
        self,
        sections: List[Section],
        merge_threshold: int = 5,
    ) -> List[CompactionResult]:
        logger.info(
            f"[Layer3:HierarchicalCompaction] COMPACT_BATCH_START | "
            f"sections={len(sections)}, merge_threshold={merge_threshold}"
        )

        if not sections:
            return []

        results = []

        if len(sections) < merge_threshold:
            logger.debug(
                f"[Layer3:HierarchicalCompaction] COMPACT_BATCH_INDIVIDUAL | "
                f"count={len(sections)} < threshold={merge_threshold}"
            )
            for section in sections:
                result = await self.compact_section(section)
                results.append(result)
            return results

        if not self.llm_client:
            logger.info(
                "[Layer3:HierarchicalCompaction] COMPACT_BATCH_SIMPLE | reason=no_llm_client"
            )
            for section in sections:
                result = self._simple_section_summary(section)
                results.append(result)
            return results

        try:
            sections_content = "\n\n".join(
                [
                    f"**{s.step_name}** ({s.priority.value}):\n{s.content[:500]}"
                    for s in sections
                ]
            )

            prompt = CompactionTemplate.MULTI_SECTION_COMPACT_TEMPLATE.format(
                sections_content=sections_content,
            )

            logger.debug(
                f"[Layer3:HierarchicalCompaction] COMPACT_BATCH_LLM_CALL | "
                f"prompt_length={len(prompt)}"
            )

            batch_summary = await self._call_llm(
                prompt, max_tokens=self.max_summary_tokens
            )

            if batch_summary:
                total_original = sum(s.tokens for s in sections)
                total_compacted = len(batch_summary) // 4

                for section in sections:
                    section.content = f"[批量压缩] {batch_summary[:200]}..."
                    section.tokens = len(section.content) // 4
                    if section.metadata is None:
                        section.metadata = {}
                    section.metadata["batch_compacted"] = True

                self._record_compaction(
                    "batch", "multiple", total_original, total_compacted
                )

                compression_ratio = (
                    total_compacted / total_original if total_original > 0 else 0
                )
                logger.info(
                    f"[Layer3:HierarchicalCompaction] COMPACT_BATCH_COMPLETE | "
                    f"sections={len(sections)} | "
                    f"original={total_original}tokens -> compacted={total_compacted}tokens | "
                    f"compression_ratio={compression_ratio:.1%} | "
                    f"saved={total_original - total_compacted}tokens"
                )

                return [
                    CompactionResult(
                        success=True,
                        original_tokens=total_original,
                        compacted_tokens=total_compacted,
                        summary=batch_summary,
                    )
                ] * len(sections)

        except Exception as e:
            logger.error(
                f"[Layer3:HierarchicalCompaction] COMPACT_BATCH_ERROR | error={e}"
            )

        for section in sections:
            result = await self.compact_section(section)
            results.append(result)

        return results

    async def compact_by_priority(
        self,
        sections: List[Section],
        priority_order: Optional[List[ContentPriority]] = None,
    ) -> Dict[str, CompactionResult]:
        if priority_order is None:
            priority_order = [
                ContentPriority.LOW,
                ContentPriority.MEDIUM,
                ContentPriority.HIGH,
            ]

        logger.info(
            f"[Layer3:HierarchicalCompaction] COMPACT_BY_PRIORITY_START | "
            f"sections={len(sections)}, priority_order={[p.value for p in priority_order]}"
        )

        results = {}

        for priority in priority_order:
            sections_to_compact = [s for s in sections if s.priority == priority]

            logger.debug(
                f"[Layer3:HierarchicalCompaction] COMPACT_BY_PRIORITY | "
                f"priority={priority.value}, count={len(sections_to_compact)}"
            )

            for section in sections_to_compact:
                result = await self.compact_section(section)
                results[section.section_id] = result

        logger.info(
            f"[Layer3:HierarchicalCompaction] COMPACT_BY_PRIORITY_COMPLETE | "
            f"compacted={len(results)}"
        )

        return results

    def _simple_chapter_summary(self, chapter: Chapter) -> CompactionResult:
        original_tokens = chapter.tokens

        summary_parts = [
            f"## {chapter.title} ({chapter.phase.value})",
            f"完成 {len(chapter.sections)} 个执行步骤",
            "",
            "### 主要步骤:",
        ]

        for section in chapter.sections[:5]:
            summary_parts.append(f"- {section.step_name}: {section.content[:100]}...")

        if len(chapter.sections) > 5:
            summary_parts.append(f"- ... 还有 {len(chapter.sections) - 5} 个步骤")

        summary = "\n".join(summary_parts)
        chapter.summary = summary
        chapter.is_compacted = True

        logger.info(
            f"[Layer3:HierarchicalCompaction] SIMPLE_CHAPTER_SUMMARY | "
            f"chapter_id={chapter.chapter_id[:8]} | "
            f"original={original_tokens}tokens -> compacted={len(summary) // 4}tokens"
        )

        return CompactionResult(
            success=True,
            original_tokens=original_tokens,
            compacted_tokens=len(summary) // 4,
            summary=summary,
        )

    def _simple_section_summary(self, section: Section) -> CompactionResult:
        original_tokens = section.tokens

        if len(section.content) > 200:
            section.content = section.content[:200] + "..."
            section.tokens = len(section.content) // 4

        logger.info(
            f"[Layer3:HierarchicalCompaction] SIMPLE_SECTION_SUMMARY | "
            f"section_id={section.section_id[:8]} | "
            f"original={original_tokens}tokens -> compacted={section.tokens}tokens"
        )

        return CompactionResult(
            success=True,
            original_tokens=original_tokens,
            compacted_tokens=section.tokens,
            summary=section.content,
        )

    def _format_sections_overview(self, sections: List[Section]) -> str:
        lines = []
        for i, section in enumerate(sections, 1):
            lines.append(
                f"{i}. [{section.priority.value}] {section.step_name}: "
                f"{section.content[:100]}..."
            )
        return "\n".join(lines)

    async def _call_llm(
        self, prompt: str, max_tokens: Optional[int] = None
    ) -> Optional[str]:
        if not self.llm_client:
            return None

        try:
            from derisk.core import HumanMessage, SystemMessage

            messages = [
                SystemMessage(
                    content="You are a helpful assistant specialized in summarizing task execution history."
                ),
                HumanMessage(content=prompt),
            ]

            response = await self.llm_client.acompletion(
                messages,
                max_tokens=max_tokens or self.max_summary_tokens,
            )

            if response and response.choices:
                return response.choices[0].message.content.strip()

            return None

        except Exception as e:
            logger.error(f"[Layer3:HierarchicalCompaction] LLM_CALL_ERROR | error={e}")
            return None

    def _record_compaction(
        self,
        compaction_type: str,
        target_id: str,
        original_tokens: int,
        compacted_tokens: int,
    ) -> None:
        self._compaction_history.append(
            {
                "type": compaction_type,
                "target_id": target_id,
                "original_tokens": original_tokens,
                "compacted_tokens": compacted_tokens,
                "tokens_saved": original_tokens - compacted_tokens,
                "compression_ratio": compacted_tokens / original_tokens
                if original_tokens > 0
                else 0,
            }
        )

    def get_statistics(self) -> Dict[str, Any]:
        if not self._compaction_history:
            return {
                "total_compactions": 0,
                "total_tokens_saved": 0,
            }

        total_saved = sum(h["tokens_saved"] for h in self._compaction_history)
        avg_ratio = sum(h["compression_ratio"] for h in self._compaction_history) / len(
            self._compaction_history
        )

        return {
            "total_compactions": len(self._compaction_history),
            "total_tokens_saved": total_saved,
            "average_compression_ratio": f"{avg_ratio:.1%}",
            "by_type": {
                t: len([h for h in self._compaction_history if h["type"] == t])
                for t in set(h["type"] for h in self._compaction_history)
            },
        }


class CompactionScheduler:
    """
    压缩调度器

    决定何时触发压缩，压缩哪些内容

    策略：
    1. Token阈值触发：超过阈值自动压缩
    2. 阶段转换触发：进入新阶段时压缩旧阶段
    3. 周期性压缩：每N步检查一次
    """

    def __init__(
        self,
        compactor: HierarchicalCompactor,
        token_threshold: int = 50000,
        check_interval: int = 10,
        auto_compact: bool = True,
    ):
        self.compactor = compactor
        self.token_threshold = token_threshold
        self.check_interval = check_interval
        self.auto_compact = auto_compact

        self._step_count = 0
        self._last_compaction_step = 0

        logger.info(
            f"[Layer3:CompactionScheduler] INIT | "
            f"token_threshold={token_threshold}, check_interval={check_interval}, "
            f"auto_compact={auto_compact}"
        )

    async def check_and_compact(
        self,
        chapters: List[Chapter],
        current_tokens: int,
    ) -> Dict[str, Any]:
        self._step_count += 1

        logger.debug(
            f"[Layer3:CompactionScheduler] CHECK | "
            f"step={self._step_count}, tokens={current_tokens}/{self.token_threshold}"
        )

        actions = []
        total_saved = 0

        needs_compaction = (
            current_tokens > self.token_threshold
            and self._step_count - self._last_compaction_step >= self.check_interval
        )

        if not needs_compaction:
            logger.debug(
                f"[Layer3:CompactionScheduler] CHECK_SKIP | "
                f"tokens={current_tokens}/{self.token_threshold}, "
                f"steps_since_last={self._step_count - self._last_compaction_step}"
            )
            return {
                "triggered": False,
                "reason": "No compaction needed",
            }

        logger.info(
            f"[Layer3:CompactionScheduler] TRIGGERED | "
            f"tokens={current_tokens} > threshold={self.token_threshold}"
        )

        chapters_to_compact = [c for c in chapters[:-1] if not c.is_compacted]

        logger.info(
            f"[Layer3:CompactionScheduler] CHAPTERS_TO_COMPACT | "
            f"count={len(chapters_to_compact)}"
        )

        for chapter in chapters_to_compact:
            result = await self.compactor.compact_chapter(chapter)
            if result.success:
                actions.append(
                    {
                        "action": "compact_chapter",
                        "target": chapter.chapter_id,
                        "tokens_saved": result.original_tokens
                        - result.compacted_tokens,
                    }
                )
                total_saved += result.original_tokens - result.compacted_tokens

        self._last_compaction_step = self._step_count

        logger.info(
            f"[Layer3:CompactionScheduler] COMPLETE | "
            f"actions={len(actions)}, total_saved={total_saved}tokens, "
            f"new_tokens={current_tokens - total_saved}"
        )

        return {
            "triggered": True,
            "reason": f"Token threshold exceeded ({current_tokens} > {self.token_threshold})",
            "actions": actions,
            "total_tokens_saved": total_saved,
            "new_token_count": current_tokens - total_saved,
        }


def create_hierarchical_compactor(
    llm_client: Optional[LLMClient] = None,
    **kwargs,
) -> HierarchicalCompactor:
    return HierarchicalCompactor(llm_client=llm_client, **kwargs)
