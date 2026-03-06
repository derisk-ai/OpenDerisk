"""Unified Compaction Pipeline — three-layer compression for v1 and v2 agents.

Layer 1: Truncation — truncate large tool outputs, archive full content to AFS.
Layer 2: Pruning — prune old tool outputs in history to save tokens.
Layer 3: Compaction & Archival — compress + archive old messages into chapters.

Works with both v1 (core) and v2 (core_v2) AgentMessage via UnifiedMessageAdapter.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, Awaitable

from .message_adapter import UnifiedMessageAdapter
from .history_archive import HistoryChapter, HistoryCatalog

logger = logging.getLogger(__name__)

NotificationCallback = Callable[[str, str], Awaitable[None]]


# =============================================================================
# Configuration
# =============================================================================


@dataclasses.dataclass
class HistoryCompactionConfig:
    # Layer 1: Truncation
    max_output_lines: int = 2000
    max_output_bytes: int = 50 * 1024  # 50KB

    # Layer 2: Pruning
    prune_protect_tokens: int = 4000
    prune_interval_rounds: int = 5
    min_messages_keep: int = 10
    prune_protected_tools: Tuple[str, ...] = ("skill",)

    # Layer 3: Compaction + Archival
    context_window: int = 128000
    compaction_threshold_ratio: float = 0.8
    recent_messages_keep: int = 5
    chars_per_token: int = 4

    # Chapter archival
    chapter_max_messages: int = 100
    chapter_summary_max_tokens: int = 2000
    max_chapters_in_memory: int = 3

    # Content protection (ported from ImprovedSessionCompaction)
    code_block_protection: bool = True
    thinking_chain_protection: bool = True
    file_path_protection: bool = True
    max_protected_blocks: int = 10

    # Shared memory
    reload_shared_memory: bool = True

    # Adaptive trigger
    adaptive_check_interval: int = 5
    adaptive_growth_threshold: float = 0.3

    # Recovery tools
    enable_recovery_tools: bool = True
    max_search_results: int = 10

    # Backward compatibility
    fallback_to_legacy: bool = True


# =============================================================================
# Result dataclasses
# =============================================================================


@dataclasses.dataclass
class TruncationResult:
    content: str
    is_truncated: bool = False
    original_size: int = 0
    truncated_size: int = 0
    file_key: Optional[str] = None
    suggestion: Optional[str] = None


@dataclasses.dataclass
class PruningResult:
    messages: List[Any]
    pruned_count: int = 0
    tokens_saved: int = 0


@dataclasses.dataclass
class CompactionResult:
    messages: List[Any]
    chapter: Optional[HistoryChapter] = None
    summary_content: Optional[str] = None
    messages_archived: int = 0
    tokens_saved: int = 0
    compaction_triggered: bool = False


# =============================================================================
# Content protection — ported from ImprovedSessionCompaction.ContentProtector
# =============================================================================

CODE_BLOCK_PATTERN = r"```[\s\S]*?```"
THINKING_CHAIN_PATTERN = (
    r"<(?:thinking|scratch_pad|reasoning)>[\s\S]*?"
    r"</(?:thinking|scratch_pad|reasoning)>"
)
FILE_PATH_PATTERN = r'["\']?(?:/[\w\-./]+|(?:\.\.?/)?[\w\-./]+\.[\w]+)["\']?'

IMPORTANT_MARKERS = [
    "important:",
    "critical:",
    "注意:",
    "重要:",
    "关键:",
    "must:",
    "should:",
    "必须:",
    "应该:",
    "remember:",
    "note:",
    "记住:",
    "todo:",
    "fixme:",
    "hack:",
    "bug:",
]

KEY_INFO_PATTERNS = {
    "decision": [
        r"(?:decided|decision|决定|确定)[：:]\s*(.+)",
        r"(?:chose|selected|选择)[：:]\s*(.+)",
    ],
    "constraint": [
        r"(?:constraint|限制|约束|requirement|要求)[：:]\s*(.+)",
        r"(?:must|should|需要|必须)\s+(.+)",
    ],
    "preference": [
        r"(?:prefer|preference|更喜欢|偏好)[：:]\s*(.+)",
    ],
    "action": [
        r"(?:action|动作|execute|执行)[：:]\s*(.+)",
        r"(?:ran|executed|运行)\s+(.+)",
    ],
}

COMPACTION_PROMPT_TEMPLATE = """You are a session compaction assistant. Summarize the conversation history into a condensed format while preserving essential information.

Your summary should:
1. Capture the main goals and intents discussed
2. Preserve key decisions and conclusions reached
3. Maintain important context for continuing the task
4. Be concise but comprehensive
5. Include any critical values, results, or findings
6. Preserve code snippets and their purposes
7. Remember user preferences and constraints

{key_info_section}

Conversation History:
{history}

Please provide your summary in the following format:
<summary>
[Your detailed summary here]
</summary>

<key_points>
- Key point 1
- Key point 2
</key_points>

<remaining_tasks>
[If there are pending tasks, list them here]
</remaining_tasks>

<code_references>
[List any important code snippets or file references to remember]
</code_references>
"""


def _calculate_importance(content: str) -> float:
    importance = 0.5
    content_lower = content.lower()
    for marker in IMPORTANT_MARKERS:
        if marker in content_lower:
            importance += 0.1
    line_count = content.count("\n") + 1
    if line_count > 20:
        importance += 0.1
    if line_count > 50:
        importance += 0.1
    if "def " in content or "function " in content or "class " in content:
        importance += 0.15
    return min(importance, 1.0)


def _extract_protected_content(
    messages: List[Any],
    config: HistoryCompactionConfig,
) -> List[Dict[str, Any]]:
    """Extract protected content blocks (code, thinking chains, file paths)."""
    adapter = UnifiedMessageAdapter
    protected: List[Dict[str, Any]] = []

    for idx, msg in enumerate(messages):
        content = adapter.get_content(msg)

        if config.code_block_protection:
            code_blocks = re.findall(CODE_BLOCK_PATTERN, content)
            for block in code_blocks[:3]:
                protected.append(
                    {
                        "type": "code",
                        "content": block,
                        "index": idx,
                        "importance": _calculate_importance(block),
                    }
                )

        if config.thinking_chain_protection:
            chains = re.findall(THINKING_CHAIN_PATTERN, content, re.IGNORECASE)
            for chain in chains[:2]:
                protected.append(
                    {
                        "type": "thinking",
                        "content": chain,
                        "index": idx,
                        "importance": 0.7,
                    }
                )

        if config.file_path_protection:
            file_paths = set(re.findall(FILE_PATH_PATTERN, content))
            for path in list(file_paths)[:5]:
                if len(path) > 3 and not path.startswith("http"):
                    protected.append(
                        {
                            "type": "file_path",
                            "content": path,
                            "index": idx,
                            "importance": 0.3,
                        }
                    )

    protected.sort(key=lambda x: x["importance"], reverse=True)
    return protected[: config.max_protected_blocks]


def _format_protected_content(protected: List[Dict[str, Any]]) -> str:
    if not protected:
        return ""

    sections: Dict[str, List[str]] = {"code": [], "thinking": [], "file_path": []}
    for item in protected:
        sections.get(item["type"], []).append(item["content"])

    result = ""
    if sections["code"]:
        result += "\n## Protected Code Blocks\n"
        for i, code in enumerate(sections["code"][:5], 1):
            result += f"\n### Code Block {i}\n{code}\n"
    if sections["thinking"]:
        result += "\n## Key Reasoning\n"
        for thinking in sections["thinking"][:2]:
            result += f"\n{thinking}\n"
    if sections["file_path"]:
        result += "\n## Referenced Files\n"
        for path in list(set(sections["file_path"]))[:10]:
            result += f"- {path}\n"
    return result


def _extract_key_infos_by_rules(
    messages: List[Any],
) -> List[Dict[str, Any]]:
    """Rule-based key info extraction (no LLM required)."""
    adapter = UnifiedMessageAdapter
    infos: List[Dict[str, Any]] = []
    seen: set = set()

    for msg in messages:
        content = adapter.get_content(msg)
        role = adapter.get_role(msg)

        for category, patterns in KEY_INFO_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    info_content = match.group(1).strip()
                    if 5 < len(info_content) < 500 and info_content not in seen:
                        seen.add(info_content)
                        infos.append(
                            {
                                "category": category,
                                "content": info_content,
                                "importance": 0.6 if role in ("user", "human") else 0.5,
                                "source": role,
                            }
                        )

    infos.sort(key=lambda x: x["importance"], reverse=True)
    return infos[:20]


def _format_key_infos(
    key_infos: List[Dict[str, Any]], min_importance: float = 0.5
) -> str:
    filtered = [i for i in key_infos if i["importance"] >= min_importance]
    if not filtered:
        return ""

    category_names = {
        "decision": "Decisions",
        "constraint": "Constraints",
        "preference": "Preferences",
        "fact": "Facts",
        "action": "Actions",
    }

    by_category: Dict[str, List[str]] = {}
    for info in filtered:
        cat = info["category"]
        by_category.setdefault(cat, []).append(info["content"])

    result = "\n### Key Information\n"
    for category, contents in by_category.items():
        result += f"\n**{category_names.get(category, category)}:**\n"
        for c in contents[:5]:
            result += f"- {c}\n"
    return result


# =============================================================================
# Pipeline
# =============================================================================


class UnifiedCompactionPipeline:
    """Three-layer compression pipeline shared by v1 and v2 agents."""

    def __init__(
        self,
        conv_id: str,
        session_id: str,
        agent_file_system: Any,
        work_log_storage: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        config: Optional[HistoryCompactionConfig] = None,
        notification_callback: Optional[NotificationCallback] = None,
    ):
        self.conv_id = conv_id
        self.session_id = session_id
        self.afs = agent_file_system
        self.work_log_storage = work_log_storage
        self.llm_client = llm_client
        self.config = config or HistoryCompactionConfig()
        self._notify = notification_callback

        self._catalog: Optional[HistoryCatalog] = None
        self._round_counter: int = 0
        self._adapter = UnifiedMessageAdapter
        self._first_compaction_done: bool = False

    async def _send_notification(self, title: str, message: str) -> None:
        if self._notify:
            try:
                await self._notify(title, message)
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")

    @property
    def has_compacted(self) -> bool:
        """Whether at least one compaction has occurred (for tool injection gating)."""
        return self._first_compaction_done

    # ==================== Layer 1: Truncation ====================

    async def truncate_output(
        self,
        output: str,
        tool_name: str,
        tool_args: Optional[Dict] = None,
    ) -> TruncationResult:
        original_size = len(output.encode("utf-8"))
        line_count = output.count("\n") + 1

        exceeds_lines = line_count > self.config.max_output_lines
        exceeds_bytes = original_size > self.config.max_output_bytes

        if not exceeds_lines and not exceeds_bytes:
            return TruncationResult(
                content=output,
                is_truncated=False,
                original_size=original_size,
                truncated_size=original_size,
            )

        # Archive full output to AFS
        file_key: Optional[str] = None
        if self.afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                fk = f"truncated_{tool_name}_{uuid.uuid4().hex[:8]}"
                await self.afs.save_file(
                    file_key=fk,
                    data=output,
                    file_type=FileType.TRUNCATED_OUTPUT,
                    extension="txt",
                    file_name=f"{fk}.txt",
                    tool_name=tool_name,
                )
                file_key = fk
            except Exception as e:
                logger.warning(f"Failed to archive truncated output: {e}")

        # Truncate
        lines = output.split("\n")
        if exceeds_lines:
            lines = lines[: self.config.max_output_lines]
        truncated = "\n".join(lines)
        if len(truncated.encode("utf-8")) > self.config.max_output_bytes:
            truncated = truncated[: self.config.max_output_bytes]

        suggestion = (
            f"[Output truncated] Original {line_count} lines ({original_size} bytes)."
        )
        if file_key:
            suggestion += (
                f" Full output archived: file_key={file_key}."
                " Use read_history_chapter or read_file to get full content."
            )
        truncated = truncated + "\n\n" + suggestion

        return TruncationResult(
            content=truncated,
            is_truncated=True,
            original_size=original_size,
            truncated_size=len(truncated.encode("utf-8")),
            file_key=file_key,
            suggestion=suggestion,
        )

    # ==================== Layer 2: Pruning ====================

    async def prune_history(
        self,
        messages: List[Any],
    ) -> PruningResult:
        self._round_counter += 1
        if self._round_counter % self.config.prune_interval_rounds != 0:
            return PruningResult(messages=messages)

        if len(messages) <= self.config.min_messages_keep:
            return PruningResult(messages=messages)

        adapter = self._adapter
        # Walk backwards, accumulate tokens; once we exceed protect budget,
        # start pruning old tool output messages.
        cumulative_tokens = 0
        protect_boundary_idx = len(
            messages
        )  # everything at/after this index is protected
        for i in range(len(messages) - 1, -1, -1):
            cumulative_tokens += adapter.get_token_estimate(messages[i])
            if cumulative_tokens > self.config.prune_protect_tokens:
                protect_boundary_idx = i + 1
                break

        pruned_count = 0
        tokens_saved = 0
        result_messages = list(messages)

        for i in range(protect_boundary_idx):
            msg = result_messages[i]
            role = adapter.get_role(msg)

            if role in ("system", "user", "human"):
                continue

            if role != "tool":
                continue

            tool_name = adapter.get_tool_name_for_tool_result(msg, result_messages, i)
            if tool_name and tool_name in self.config.prune_protected_tools:
                continue

            content = adapter.get_content(msg)
            if len(content) < 200:
                continue

            tool_call_id = adapter.get_tool_call_id(msg) or "unknown"
            preview = content[:100].replace("\n", " ")
            pruned_text = f"[Tool output pruned] ({tool_call_id}): {preview}..."

            tokens_saved += adapter.get_token_estimate(msg) - (len(pruned_text) // 4)
            pruned_count += 1

            if hasattr(msg, "content"):
                try:
                    msg.content = pruned_text
                except Exception:
                    pass

        if pruned_count > 0:
            await self._send_notification(
                "历史剪枝",
                f"正在清理历史消息中的旧工具输出以节省上下文空间...\n已清理 {pruned_count} 个工具输出，节省约 {tokens_saved} tokens",
            )

        return PruningResult(
            messages=result_messages,
            pruned_count=pruned_count,
            tokens_saved=tokens_saved,
        )

    # ==================== Layer 3: Compaction & Archival ====================

    async def compact_if_needed(
        self,
        messages: List[Any],
        force: bool = False,
    ) -> CompactionResult:
        if not messages:
            return CompactionResult(messages=messages)

        total_tokens = self._estimate_tokens(messages)
        threshold = int(
            self.config.context_window * self.config.compaction_threshold_ratio
        )

        if not force and total_tokens < threshold:
            return CompactionResult(messages=messages)

        to_compact, to_keep = self._select_messages_to_compact(messages)
        if not to_compact:
            return CompactionResult(messages=messages)

        await self._send_notification(
            "历史压缩",
            f"正在压缩历史消息以释放上下文空间...\n将压缩 {len(to_compact)} 条历史消息",
        )

        summary, key_tools, key_decisions = await self._generate_chapter_summary(
            to_compact
        )

        # Archive messages to chapter
        chapter = await self._archive_messages_to_chapter(
            to_compact, summary, key_tools, key_decisions
        )

        # Build summary message dict
        summary_msg_dict = self._create_summary_message(summary, chapter)

        # Preserve system messages from compacted range
        system_msgs = [m for m in to_compact if self._adapter.get_role(m) == "system"]

        # Construct new messages: system msgs + summary + kept messages
        new_messages: List[Any] = []
        new_messages.extend(system_msgs)
        new_messages.append(summary_msg_dict)
        new_messages.extend(to_keep)

        # Calculate tokens saved
        new_tokens = self._estimate_tokens(new_messages)
        tokens_saved = total_tokens - new_tokens

        # Create WorkLogSummary if storage available
        if self.work_log_storage and chapter:
            try:
                from derisk.agent.core.memory.gpts.file_base import WorkLogSummary

                wls = WorkLogSummary(
                    compressed_entries_count=chapter.message_count,
                    time_range=chapter.time_range,
                    summary_content=summary,
                    key_tools=key_tools,
                    archive_file=chapter.file_key,
                )
                await self.work_log_storage.append_work_log_summary(self.conv_id, wls)
            except Exception as e:
                logger.warning(f"Failed to create WorkLogSummary: {e}")

        self._first_compaction_done = True

        logger.info(
            f"Compaction completed: archived {len(to_compact)} messages into "
            f"chapter {chapter.chapter_index if chapter else '?'}, "
            f"saved ~{tokens_saved} tokens"
        )

        await self._send_notification(
            "历史压缩完成",
            f"已将 {len(to_compact)} 条历史消息归档至章节 {chapter.chapter_index if chapter else '?'}\n"
            f"节省约 {tokens_saved} tokens，可通过历史回溯工具查看已归档内容",
        )

        return CompactionResult(
            messages=new_messages,
            chapter=chapter,
            summary_content=summary,
            messages_archived=len(to_compact),
            tokens_saved=tokens_saved,
            compaction_triggered=True,
        )

    # ==================== Catalog Management ====================

    async def get_catalog(self) -> HistoryCatalog:
        if self._catalog is not None:
            return self._catalog

        # Try loading from WorkLogStorage
        if self.work_log_storage:
            try:
                data = await self.work_log_storage.get_history_catalog(self.conv_id)
                if data:
                    self._catalog = HistoryCatalog.from_dict(data)
                    return self._catalog
            except Exception:
                pass

        # Try loading from AFS
        if self.afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                content = await self.afs.read_file(f"history_catalog_{self.session_id}")
                if content:
                    self._catalog = HistoryCatalog.from_dict(json.loads(content))
                    return self._catalog
            except Exception:
                pass

        # Create new catalog
        self._catalog = HistoryCatalog(
            conv_id=self.conv_id,
            session_id=self.session_id,
            created_at=time.time(),
        )
        return self._catalog

    async def save_catalog(self) -> None:
        if not self._catalog:
            return

        catalog_data = self._catalog.to_dict()

        # Save to WorkLogStorage
        if self.work_log_storage:
            try:
                await self.work_log_storage.save_history_catalog(
                    self.conv_id, catalog_data
                )
            except Exception as e:
                logger.warning(f"Failed to save catalog to WorkLogStorage: {e}")

        # Save to AFS
        if self.afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                await self.afs.save_file(
                    file_key=f"history_catalog_{self.session_id}",
                    data=catalog_data,
                    file_type=FileType.HISTORY_CATALOG,
                    extension="json",
                    file_name=f"history_catalog_{self.session_id}.json",
                )
            except Exception as e:
                logger.warning(f"Failed to save catalog to AFS: {e}")

    # ==================== Chapter Recovery ====================

    async def read_chapter(self, chapter_index: int) -> Optional[str]:
        catalog = await self.get_catalog()
        chapter = catalog.get_chapter(chapter_index)
        if not chapter:
            return f"Chapter {chapter_index} not found. Use get_history_overview() to see available chapters."

        if not self.afs:
            return "AgentFileSystem not available — cannot read archived chapter."

        try:
            content = await self.afs.read_file(chapter.file_key)
            if content:
                # Format archived messages for readability
                try:
                    archived_msgs = json.loads(content)
                    return self._format_archived_messages(archived_msgs, chapter)
                except json.JSONDecodeError:
                    return content
            return f"Chapter {chapter_index} file not found in storage."
        except Exception as e:
            logger.error(f"Failed to read chapter {chapter_index}: {e}")
            return f"Error reading chapter {chapter_index}: {e}"

    async def search_chapters(
        self,
        query: str,
        max_results: int = 10,
    ) -> str:
        catalog = await self.get_catalog()
        if not catalog.chapters:
            return "No history chapters available."

        query_lower = query.lower()
        matches: List[str] = []

        for ch in catalog.chapters:
            relevance_parts: List[str] = []

            if query_lower in ch.summary.lower():
                relevance_parts.append(f"Summary match: ...{ch.summary[:200]}...")

            for decision in ch.key_decisions:
                if query_lower in decision.lower():
                    relevance_parts.append(f"Decision: {decision}")

            for tool in ch.key_tools:
                if query_lower in tool.lower():
                    relevance_parts.append(f"Tool: {tool}")

            if relevance_parts:
                header = (
                    f"Chapter {ch.chapter_index} "
                    f"({ch.message_count} msgs, {ch.tool_call_count} tool calls)"
                )
                matches.append(
                    header + "\n" + "\n".join(f"  - {p}" for p in relevance_parts)
                )

            if len(matches) >= max_results:
                break

        if not matches:
            return (
                f'No results found for "{query}" in {len(catalog.chapters)} chapters.'
            )

        return f'Search results for "{query}":\n\n' + "\n\n".join(matches)

    # ==================== Internal Methods ====================

    def _estimate_tokens(self, messages: List[Any]) -> int:
        total = 0
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls")
                total += len(str(content)) // self.config.chars_per_token
                if tool_calls:
                    total += (
                        len(json.dumps(tool_calls, ensure_ascii=False))
                        // self.config.chars_per_token
                    )
            else:
                total += self._adapter.get_token_estimate(msg)
        return total

    def _select_messages_to_compact(
        self,
        messages: List[Any],
    ) -> Tuple[List[Any], List[Any]]:
        """Select messages to compact, respecting tool-call atomic groups.

        Ported from ImprovedSessionCompaction._select_messages_to_compact().
        """
        if len(messages) <= self.config.recent_messages_keep:
            return [], messages

        split_idx = len(messages) - self.config.recent_messages_keep
        adapter = self._adapter

        # Walk split point backwards to avoid breaking tool-call atomic groups
        while split_idx > 0:
            msg = messages[split_idx]
            role = adapter.get_role(msg)
            is_tool_msg = role == "tool"
            is_tool_assistant = adapter.is_tool_call_message(msg)

            if is_tool_msg or is_tool_assistant:
                split_idx -= 1
            else:
                break

        to_compact = messages[:split_idx]
        to_keep = messages[split_idx:]
        return to_compact, to_keep

    async def _generate_chapter_summary(
        self,
        messages: List[Any],
    ) -> Tuple[str, List[str], List[str]]:
        """Generate chapter summary, key_tools, and key_decisions."""
        adapter = self._adapter

        # Collect key tools and decisions
        key_tools_set: set = set()
        key_decisions: List[str] = []

        for msg in messages:
            tool_calls = adapter.get_tool_calls(msg)
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    name = func.get("name", "")
                    if name:
                        key_tools_set.add(name)

        key_tools = list(key_tools_set)

        # Extract key infos for decisions
        key_infos = _extract_key_infos_by_rules(messages)
        for info in key_infos:
            if info["category"] == "decision":
                key_decisions.append(info["content"])

        # Try LLM summary first
        summary = await self._generate_llm_summary(messages, key_infos)

        if not summary:
            summary = self._generate_simple_summary(messages, key_infos)

        return summary, key_tools, key_decisions[:10]

    async def _generate_llm_summary(
        self,
        messages: List[Any],
        key_infos: List[Dict[str, Any]],
    ) -> Optional[str]:
        if not self.llm_client:
            return None

        await self._send_notification(
            "生成历史摘要", "正在使用 AI 分析历史对话并生成摘要..."
        )

        try:
            adapter = self._adapter
            history_lines = []
            for msg in messages:
                formatted = adapter.format_message_for_summary(msg)
                if formatted:
                    history_lines.append(formatted)
            history_text = "\n\n".join(history_lines)

            key_info_section = _format_key_infos(key_infos, 0.5)

            prompt = COMPACTION_PROMPT_TEMPLATE.format(
                history=history_text,
                key_info_section=key_info_section,
            )

            from derisk.agent.core_v2.llm_utils import call_llm

            result = await call_llm(
                self.llm_client,
                prompt,
                system_prompt=(
                    "You are a helpful assistant specialized in summarizing "
                    "conversations while preserving critical technical information."
                ),
            )
            if result:
                return result.strip()
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}")

        return None

    def _generate_simple_summary(
        self,
        messages: List[Any],
        key_infos: List[Dict[str, Any]],
    ) -> str:
        adapter = self._adapter
        tool_calls: List[str] = []
        user_inputs: List[str] = []
        assistant_responses: List[str] = []

        for msg in messages:
            role = adapter.get_role(msg)
            content = adapter.get_content(msg)

            if role in ("tool",):
                tool_calls.append(content[:100])
            elif role in ("user", "human"):
                user_inputs.append(content[:300])
            elif role in ("assistant", "agent"):
                assistant_responses.append(content[:300])

        parts: List[str] = []

        if user_inputs:
            parts.append("User Queries:")
            for q in user_inputs[-5:]:
                parts.append(f"  - {q[:150]}...")

        if tool_calls:
            parts.append(f"\nTool Executions: {len(tool_calls)} tool calls made")

        if assistant_responses:
            parts.append("\nKey Responses:")
            for r in assistant_responses[-3:]:
                parts.append(f"  - {r[:200]}...")

        if key_infos:
            parts.append(_format_key_infos(key_infos, 0.3))

        return "\n".join(parts) if parts else "Previous conversation history"

    async def _archive_messages_to_chapter(
        self,
        messages: List[Any],
        summary: str,
        key_tools: List[str],
        key_decisions: List[str],
    ) -> HistoryChapter:
        adapter = self._adapter
        catalog = await self.get_catalog()

        chapter_index = catalog.current_chapter_index

        serialized = [adapter.serialize_message(m) for m in messages]

        timestamps = [adapter.get_timestamp(m) for m in messages]
        timestamps = [t for t in timestamps if t > 0]
        time_range = (min(timestamps), max(timestamps)) if timestamps else (0.0, 0.0)

        tool_call_count = sum(1 for m in messages if adapter.is_tool_call_message(m))

        token_estimate = sum(adapter.get_token_estimate(m) for m in messages)

        skill_outputs = self._extract_skill_outputs(messages, serialized)

        file_key = f"chapter_{self.session_id}_{chapter_index}"
        if self.afs:
            try:
                from derisk.agent.core.memory.gpts.file_base import FileType

                await self.afs.save_file(
                    file_key=file_key,
                    data=serialized,
                    file_type=FileType.HISTORY_CHAPTER,
                    extension="json",
                    file_name=f"chapter_{chapter_index}.json",
                )
            except Exception as e:
                logger.error(f"Failed to archive chapter {chapter_index}: {e}")

        chapter = HistoryChapter(
            chapter_id=uuid.uuid4().hex,
            chapter_index=chapter_index,
            time_range=time_range,
            message_count=len(messages),
            tool_call_count=tool_call_count,
            summary=summary[: self.config.chapter_summary_max_tokens * 4],
            key_tools=key_tools,
            key_decisions=key_decisions,
            file_key=file_key,
            token_estimate=token_estimate,
            created_at=time.time(),
            skill_outputs=skill_outputs,
        )

        catalog.add_chapter(chapter)
        await self.save_catalog()

        return chapter

    def _extract_skill_outputs(
        self,
        messages: List[Any],
        serialized: List[Dict],
    ) -> List[str]:
        adapter = self._adapter
        skill_outputs: List[str] = []

        for i, msg in enumerate(messages):
            role = adapter.get_role(msg)
            if role != "tool":
                continue

            tool_name = adapter.get_tool_name_for_tool_result(msg, messages, i)
            if tool_name not in self.config.prune_protected_tools:
                continue

            content = adapter.get_content(msg)
            if content:
                skill_outputs.append(content)

        return skill_outputs

    def _create_summary_message(
        self,
        summary: str,
        chapter: HistoryChapter,
    ) -> Dict:
        parts = [
            f"[History Compaction] Chapter {chapter.chapter_index} archived.",
            "",
            summary,
            "",
            f"Archived {chapter.message_count} messages "
            f"({chapter.tool_call_count} tool calls).",
        ]

        if chapter.skill_outputs:
            parts.append("")
            parts.append("=== Active Skill Instructions (Rehydrated) ===")
            for i, skill_output in enumerate(chapter.skill_outputs):
                parts.append(f"\n--- Skill Output {i + 1} ---")
                parts.append(skill_output)

        parts.append("")
        parts.append(
            f"Use get_history_overview() or "
            f"read_history_chapter({chapter.chapter_index}) "
            f"to access archived content."
        )

        content = "\n".join(parts)
        return {
            "role": "system",
            "content": content,
            "is_compaction_summary": True,
            "chapter_index": chapter.chapter_index,
        }

    def _format_archived_messages(
        self,
        archived_msgs: List[Dict],
        chapter: HistoryChapter,
    ) -> str:
        lines = [
            f"=== Chapter {chapter.chapter_index} ===",
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(chapter.time_range[0]))} - "
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(chapter.time_range[1]))}",
            f"Messages: {chapter.message_count}, Tool calls: {chapter.tool_call_count}",
            f"Summary: {chapter.summary[:300]}",
            "",
            "--- Messages ---",
            "",
        ]

        for msg_dict in archived_msgs:
            role = msg_dict.get("role", "unknown")
            content = msg_dict.get("content", "")
            tool_calls = msg_dict.get("tool_calls")
            tool_call_id = msg_dict.get("tool_call_id")

            if role == "assistant" and tool_calls:
                tc_names = []
                for tc in tool_calls:
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    tc_names.append(func.get("name", "unknown"))
                lines.append(f"[{role}] Called: {', '.join(tc_names)}")
                if content:
                    lines.append(f"  {content[:500]}")
            elif role == "tool" and tool_call_id:
                if len(content) > 1000:
                    content = content[:1000] + "... [truncated]"
                lines.append(f"[tool ({tool_call_id})]: {content}")
            else:
                if len(content) > 1000:
                    content = content[:1000] + "... [truncated]"
                lines.append(f"[{role}]: {content}")

            lines.append("")

        return "\n".join(lines)
