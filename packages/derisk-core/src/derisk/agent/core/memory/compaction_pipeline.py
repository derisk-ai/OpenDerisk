"""Unified Compaction Pipeline — four-layer compression for v1 and v2 agents.

Layer 1: Truncation — truncate large tool outputs, archive full content to AFS.
Layer 2: Pruning — prune old tool outputs in history to save tokens.
Layer 3: Compaction & Archival — compress + archive old messages into chapters.
Layer 4: Multi-Turn History — compress cross-round conversation history.

Works with both v1 (core) and v2 (core_v2) AgentMessage via UnifiedMessageAdapter.

Monitoring Integration:
    This module integrates with `context_metrics.ContextMetricsCollector` to provide
    real-time monitoring of context compression operations. Metrics are logged and
    can be pushed to product layers for visualization.

Four-Layer Architecture:
    - Historical rounds: User question + WorkLog summary + Answer summary (compressed, via prompt)
    - Current round: Native Function Call mode, tool messages directly passed
    - memory variable: Injects only historical rounds' compressed summary
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
from .context_metrics import ContextMetricsCollector, ContextMetrics, metrics_registry

logger = logging.getLogger(__name__)

NotificationCallback = Callable[[str, str], Awaitable[None]]


# =============================================================================
# Configuration
# =============================================================================


# =============================================================================
# Unified Configuration
# =============================================================================


@dataclasses.dataclass
class UnifiedCompactionConfig:
    """统一压缩配置 - Pipeline 和 WorkLogManager 共用

    设计原则：
    1. 统一配置避免行为不一致
    2. 所有压缩策略使用相同阈值
    3. 完整的功能覆盖（内容保护、自适应触发、降级机制）
    """

    # ==================== Layer 1: Truncation ====================
    max_output_lines: int = 2000
    max_output_bytes: int = 50 * 1024  # 50KB

    # ==================== Layer 2: Pruning ====================
    # Layer 2: Pruning（简化智能剪枝策略）
    # 设计原则：基于使用率触发 + 按比例保护

    # 基础参数
    prune_protect_tokens: int = 10000  # 废弃：使用 prune_protect_ratio 替代
    prune_protect_ratio: float = 0.15  # 保留最近 15% 上下文空间的消息
    min_messages_keep: int = 20
    prune_protected_tools: Tuple[str, ...] = ("skill", "skill_read", "skill_exec", "skill_list")

    # 自适应剪枝配置
    enable_adaptive_pruning: bool = True

    # 触发条件简化：仅基于使用率
    prune_min_usage_to_trigger: float = 0.5  # 使用率 < 50% 不触发剪枝
    prune_trigger_high_usage: float = 0.8  # 使用率 >= 80% 立即触发

    # 动态剪枝间隔（根据使用率自动调整）
    prune_interval_medium_usage: int = 8  # 使用率 50%-80%：每8轮检查
    prune_interval_high_usage: int = 3  # 使用率 >= 80%：每3轮检查

    # 检查间隔
    adaptive_check_interval: int = 5

    # 智能选择策略
    max_tool_outputs_keep: int = 20  # 最多保留的工具输出数
    use_uniform_sampling: bool = False  # 是否使用均匀采样（否则基于重要性）

    # ==================== Layer 3: Compaction + Archival ====================
    context_window: int = 128000
    compaction_threshold_ratio: float = 0.8  # 统一为 80%
    recent_messages_keep: int = 5
    chars_per_token: int = 4

    # Chapter archival
    chapter_max_messages: int = 100
    chapter_summary_max_tokens: int = 2000
    max_chapters_in_memory: int = 3

    # ==================== Content Protection ====================
    code_block_protection: bool = True
    thinking_chain_protection: bool = True
    file_path_protection: bool = True
    max_protected_blocks: int = 10

    # ==================== Advanced Features ====================
    # Shared memory
    reload_shared_memory: bool = True

    # Recovery tools
    enable_recovery_tools: bool = True
    max_search_results: int = 10

    # Backward compatibility
    fallback_to_legacy: bool = True

    # ==================== WorkLogManager Extensions ====================
    # 大结果归档阈值
    large_result_threshold_bytes: int = 10 * 1024  # 10KB

    # 特殊工具配置
    read_file_preview_length: int = 2000
    summary_only_tools: Tuple[str, ...] = ("grep", "search", "find")

    # ==================== Layer 4: Multi-Turn History ====================
    # 跨轮次对话历史压缩配置
    enable_layer4_compression: bool = True  # 启用第四层压缩
    max_rounds_before_compression: int = 3  # 保留最近3轮不压缩
    max_total_rounds: int = 10  # 最多保留10轮历史
    layer4_compression_token_threshold: int = 8000  # 超过此token数触发压缩
    layer4_chars_per_token: int = 4

    # Layer 4 LLM 摘要配置
    enable_layer4_llm_summary: bool = True  # 启用 LLM 智能摘要（而非截断）
    layer4_summary_max_tokens: int = 200  # LLM 摘要最大 token 数
    layer4_summary_temperature: float = 0.3  # LLM 摘要温度

    # Layer 4 摘要长度限制（截断模式备用）
    max_question_summary_length: int = 200
    max_response_summary_length: int = 300
    max_findings_length: int = 300


# Backward compatibility alias
HistoryCompactionConfig = UnifiedCompactionConfig


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
    """Four-layer compression pipeline shared by v1 and v2 agents.

    Layer 4 (Multi-Turn History): Compress cross-round conversation history.
    - Historical rounds: User question + WorkLog summary + Answer summary
    - Current round: Native Function Call mode with direct tool messages
    """

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

        # Layer 4: Multi-Turn History Compression
        self._conversation_history_manager: Optional[Any] = None
        self._layer4_enabled: bool = self.config.enable_layer4_compression

        # 自适应剪枝状态跟踪
        self._last_token_count: int = 0
        self._last_prune_round: int = 0
        self._tool_calls_in_current_round: int = 0
        self._current_usage_ratio: float = 0.0

        # 监控模块 - 初始化指标收集器
        self._metrics_collector = ContextMetricsCollector(
            conv_id=conv_id,
            session_id=session_id,
            context_window=self.config.context_window,
            config={
                "max_output_lines": self.config.max_output_lines,
                "max_output_bytes": self.config.max_output_bytes,
                "prune_protect_tokens": self.config.prune_protect_tokens,
                "compaction_threshold_ratio": self.config.compaction_threshold_ratio,
                "recent_messages_keep": self.config.recent_messages_keep,
            },
            enable_logging=True,
        )
        metrics_registry.register(self._metrics_collector)

    async def _send_notification(self, title: str, message: str) -> None:
        if self._notify:
            try:
                await self._notify(title, message)
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")

    @property
    def has_compacted(self) -> bool:
        return self._first_compaction_done

    def get_context_metrics(self) -> ContextMetrics:
        return self._metrics_collector.get_metrics()

    def get_context_metrics_dict(self) -> Dict[str, Any]:
        return self._metrics_collector.get_metrics_dict()

    def update_metrics_context_state(
        self,
        tokens: int,
        message_count: int,
        round_counter: Optional[int] = None,
    ) -> None:
        self._metrics_collector.update_context_state(
            tokens=tokens,
            message_count=message_count,
            round_counter=round_counter or self._round_counter,
        )

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

        # 记录截断指标
        self._metrics_collector.record_truncation(
            tool_name=tool_name,
            original_bytes=original_size,
            truncated_bytes=len(truncated.encode("utf-8")),
            original_lines=line_count,
            truncated_lines=min(line_count, self.config.max_output_lines),
            file_key=file_key,
        )

        return TruncationResult(
            content=truncated,
            is_truncated=True,
            original_size=original_size,
            truncated_size=len(truncated.encode("utf-8")),
            file_key=file_key,
            suggestion=suggestion,
        )

    # ==================== Layer 2: Pruning ====================

    def _calculate_adaptive_prune_interval(self, messages: List[Any]) -> int:
        """根据上下文使用率计算动态剪枝间隔"""
        if not self.config.enable_adaptive_pruning:
            return 8

        total_tokens = self._estimate_tokens(messages)
        usage_ratio = total_tokens / self.config.context_window
        self._current_usage_ratio = usage_ratio

        if usage_ratio >= self.config.prune_trigger_high_usage:
            return self.config.prune_interval_high_usage
        else:
            return self.config.prune_interval_medium_usage

    def _should_prune_now(self, messages: List[Any]) -> Tuple[bool, str]:
        """
        简化的剪枝决策逻辑

        触发条件：
        1. 使用率 >= 80%: 立即触发
        2. 使用率 >= 50% 且达到检查间隔: 检查动态间隔
        3. 使用率 < 50%: 不触发，空间足够
        """
        if not self.config.enable_adaptive_pruning:
            rounds_since_last = self._round_counter - self._last_prune_round
            if rounds_since_last >= 8:
                return True, "fixed_interval"
            return False, "interval_not_reached"

        # 1. 检查最小间隔
        rounds_since_check = self._round_counter - self._last_prune_round
        if rounds_since_check < self.config.adaptive_check_interval:
            return False, "check_interval_not_reached"

        # 2. 估算当前 tokens 和使用率
        total_tokens = self._estimate_tokens(messages)
        usage_ratio = total_tokens / self.config.context_window
        self._current_usage_ratio = usage_ratio

        # 3. 使用率低于阈值，空间足够，不触发剪枝
        if usage_ratio < self.config.prune_min_usage_to_trigger:
            self._last_token_count = total_tokens
            logger.debug(f"使用率较低 ({usage_ratio:.1%})，空间充足，跳过剪枝")
            return False, f"low_usage_{usage_ratio:.1%}"

        # 4. 高使用率立即触发（紧急情况）
        if usage_ratio >= self.config.prune_trigger_high_usage:
            logger.info(f"🔥 高上下文使用率 ({usage_ratio:.1%})，立即剪枝")
            self._last_token_count = total_tokens
            return True, f"high_usage_{usage_ratio:.1%}"

        # 5. 中等使用率，检查动态间隔
        dynamic_interval = self._calculate_adaptive_prune_interval(messages)
        rounds_since_last = self._round_counter - self._last_prune_round

        if rounds_since_last >= dynamic_interval:
            logger.debug(
                f"动态间隔检查: {rounds_since_last}/{dynamic_interval} 轮，使用率 {usage_ratio:.1%}"
            )
            self._last_token_count = total_tokens
            return True, f"dynamic_interval_{usage_ratio:.1%}"

        # 6. 更新状态
        self._last_token_count = total_tokens

        return False, "no_need"

    async def prune_history(
        self,
        messages: List[Any],
    ) -> PruningResult:
        self._round_counter += 1

        # 使用智能决策
        should_prune, reason = self._should_prune_now(messages)

        if not should_prune:
            logger.debug(f"剪枝跳过: {reason}")
            return PruningResult(messages=messages)

        if len(messages) <= self.config.min_messages_keep:
            logger.debug(
                f"消息数不足，跳过剪枝: {len(messages)} <= {self.config.min_messages_keep}"
            )
            return PruningResult(messages=messages)

        adapter = self._adapter
        total_tokens = self._estimate_tokens(messages)

        # 按比例计算保护边界：保留最近 prune_protect_ratio 的上下文空间
        protect_tokens_target = int(
            self.config.context_window * self.config.prune_protect_ratio
        )

        cumulative_tokens = 0
        protect_boundary_idx = len(messages)

        for i in range(len(messages) - 1, -1, -1):
            cumulative_tokens += adapter.get_token_estimate(messages[i])
            if cumulative_tokens > protect_tokens_target:
                protect_boundary_idx = i + 1
                break

        logger.debug(
            f"剪枝保护边界: 保留最近 {cumulative_tokens} tokens "
            f"(目标 {protect_tokens_target} tokens, 比例 {self.config.prune_protect_ratio:.1%})"
        )

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
            self._last_prune_round = self._round_counter
            self._last_token_count = self._estimate_tokens(result_messages)

            await self._send_notification(
                "历史剪枝",
                f"正在清理历史消息中的旧工具输出以节省上下文空间...\n"
                f"已清理 {pruned_count} 个工具输出，节省约 {tokens_saved} tokens\n"
                f"触发原因: {reason}\n"
                f"当前使用率: {self._current_usage_ratio:.1%}",
            )

            logger.info(
                f"剪枝完成: 清理 {pruned_count} 个工具输出，"
                f"节省 {tokens_saved} tokens，使用率 {self._current_usage_ratio:.1%}"
            )

            # 记录剪枝指标
            self._metrics_collector.record_pruning(
                messages_pruned=pruned_count,
                tokens_saved=tokens_saved,
                trigger_reason=reason,
                usage_ratio=self._current_usage_ratio,
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

        # 记录压缩指标
        self._metrics_collector.record_compaction(
            messages_archived=len(to_compact),
            tokens_saved=tokens_saved,
            chapter_index=chapter.chapter_index if chapter else 0,
            summary_length=len(summary) if summary else 0,
            key_tools=key_tools,
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
            total_skills = len(chapter.skill_outputs)
            # Eviction: keep first 1 + last 2 full, summarize the rest
            if total_skills <= 3:
                for i, skill_output in enumerate(chapter.skill_outputs):
                    parts.append(f"\n--- Skill Output {i + 1} ---")
                    parts.append(skill_output)
            else:
                # First skill (full)
                parts.append(f"\n--- Skill Output 1 ---")
                parts.append(chapter.skill_outputs[0])
                # Evicted middle skills (names only)
                evicted_count = total_skills - 3
                parts.append(f"\n[{evicted_count} skill output(s) evicted to save context, use skill_read to reload]")
                # Last 2 skills (full)
                for i, skill_output in enumerate(chapter.skill_outputs[-2:], start=total_skills - 1):
                    parts.append(f"\n--- Skill Output {i} ---")
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

    # ==================== Layer 4: Multi-Turn History ====================

    async def get_or_create_history_manager(self) -> Optional[Any]:
        """Get or create Layer 4 conversation history manager."""
        if not self._layer4_enabled:
            return None

        if self._conversation_history_manager is None:
            try:
                from .layer4_conversation_history import (
                    get_conversation_history_manager,
                    Layer4CompressionConfig,
                )

                config = Layer4CompressionConfig(
                    max_rounds_before_compression=self.config.max_rounds_before_compression,
                    max_total_rounds=self.config.max_total_rounds,
                    compression_token_threshold=self.config.layer4_compression_token_threshold,
                    chars_per_token=self.config.layer4_chars_per_token,
                    max_question_summary_length=self.config.max_question_summary_length,
                    max_response_summary_length=self.config.max_response_summary_length,
                    max_findings_length=self.config.max_findings_length,
                )

                self._conversation_history_manager = (
                    await get_conversation_history_manager(
                        session_id=self.session_id,
                        config=config,
                    )
                )
                logger.info(
                    f"Layer 4: Initialized ConversationHistoryManager for session {self.session_id}"
                )
            except Exception as e:
                logger.warning(f"Layer 4: Failed to initialize history manager: {e}")
                self._layer4_enabled = False
                return None

        return self._conversation_history_manager

    async def start_conversation_round(
        self, user_question: str, user_context: Optional[Dict] = None
    ) -> Optional[Any]:
        """Start a new conversation round (Layer 4)."""
        manager = await self.get_or_create_history_manager()
        if manager:
            return await manager.start_new_round(user_question, user_context)
        return None

    async def complete_conversation_round(
        self, ai_response: str, ai_thinking: str = ""
    ):
        """Complete current conversation round (Layer 4)."""
        manager = await self.get_or_create_history_manager()
        if manager:
            await manager.complete_current_round(ai_response, ai_thinking)

    async def get_layer4_history_for_prompt(
        self, max_rounds: Optional[int] = None
    ) -> str:
        """Get Layer 4 compressed history for prompt injection."""
        manager = await self.get_or_create_history_manager()
        if manager:
            return await manager.get_history_for_prompt(
                max_rounds=max_rounds,
                include_current=False,  # Exclude current round
            )
        return ""

    async def get_layer4_history_as_message_list(
        self,
        max_rounds: Optional[int] = None,
        max_tokens: int = 30000,
    ) -> List[Dict[str, Any]]:
        """
        Get Layer 4 history as native Message List format.

        This is the new recommended way to pass history to LLM, replacing
        text-based prompt injection with native Message List format.

        Returns messages in OpenAI-compatible format:
        [
            {"role": "system", "content": "[历史对话摘要] ..."},
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "...", "tool_calls": [...]},
            {"role": "tool", "tool_call_id": "...", "content": "..."},
        ]
        """
        manager = await self.get_or_create_history_manager()
        if not manager:
            return []

        try:
            rounds = await manager.get_history_rounds(
                max_rounds=max_rounds,
                include_current=False,
            )
            if not rounds:
                return []

            messages: List[Dict[str, Any]] = []
            total_tokens = 0
            chars_per_token = self.config.layer4_chars_per_token

            for round_data in rounds:
                round_messages, round_tokens = self._convert_round_to_messages(
                    round_data, chars_per_token
                )

                if total_tokens + round_tokens > max_tokens:
                    break

                messages.extend(round_messages)
                total_tokens += round_tokens

            if messages:
                logger.info(
                    f"[HistoryMessageBuilder] Layer4: {len(messages)} messages from {len(rounds)} rounds, ~{total_tokens} tokens"
                )

            return messages

        except Exception as e:
            logger.warning(f"Layer 4: Failed to build message list: {e}")
            return []

    def _convert_round_to_messages(
        self,
        round_data: Dict[str, Any],
        chars_per_token: int = 4,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Convert a conversation round to Message List format.

        Args:
            round_data: Dict containing round info (user_question, ai_response,
                       work_log_entries, summary, etc.)
            chars_per_token: Characters per token for estimation

        Returns:
            Tuple of (messages list, estimated tokens)
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        is_compressed = round_data.get("status") == "compressed"

        if is_compressed:
            summary = round_data.get("summary", "")
            if summary:
                summary_msg = {
                    "role": "system",
                    "content": f"[历史对话摘要]\n{summary}",
                    "is_history_summary": True,
                }
                messages.append(summary_msg)
                total_tokens += len(summary) // chars_per_token
        else:
            user_question = round_data.get("user_question", "")
            if user_question:
                messages.append(
                    {
                        "role": "user",
                        "content": user_question,
                    }
                )
                total_tokens += len(user_question) // chars_per_token

            work_log_entries = round_data.get("work_log_entries", [])
            for entry in work_log_entries:
                tool_name = entry.get("tool", "unknown")
                tool_args = entry.get("args", {})
                tool_result = entry.get("result", "") or entry.get("summary", "")
                tool_call_id = (
                    entry.get("tool_call_id")
                    or f"tc_{tool_name}_{uuid.uuid4().hex[:8]}"
                )

                assistant_msg = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args, ensure_ascii=False),
                            },
                        }
                    ],
                }
                messages.append(assistant_msg)

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result,
                }
                messages.append(tool_msg)
                total_tokens += (
                    len(tool_result) + len(json.dumps(tool_args))
                ) // chars_per_token

            ai_response = round_data.get("ai_response", "")
            if ai_response and not work_log_entries:
                messages.append(
                    {
                        "role": "assistant",
                        "content": ai_response,
                    }
                )
                total_tokens += len(ai_response) // chars_per_token

        return messages, total_tokens

    async def update_current_round_worklog(
        self, worklog_entries: List[Dict], summary: Optional[Dict] = None
    ):
        """Update current round's worklog (Layer 4)."""
        manager = await self.get_or_create_history_manager()
        if manager:
            from .layer4_conversation_history import WorkLogSummary

            wls = WorkLogSummary(**summary) if summary else None
            await manager.update_current_round_worklog(worklog_entries, wls)

    # ==================== Tool Messages Conversion ====================

    async def get_tool_messages_from_worklog(
        self,
        max_entries: int = 50,
        use_compressed_summary: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        将 WorkLog 历史转换为原生 Function Call 格式的消息列表。

        这是为了让模型能够看到历史工具调用结果，按 OpenAI Function Call 协议格式：
        [
            {"role": "assistant", "content": "", "tool_calls": [...]},
            {"role": "tool", "tool_call_id": "...", "content": "..."},
            ...
        ]

        核心设计：压缩后的条目使用摘要替代原始内容，保证上下文管理有效。

        Args:
            max_entries: 最大条目数
            use_compressed_summary: 对于已压缩条目，是否使用压缩摘要替代原始内容
                - True (默认): 使用压缩摘要，节省 token，保留关键信息
                - False: 跳过压缩条目（仅用于特殊场景，会导致历史信息丢失）

        Returns:
            符合原生 Function Call 格式的消息列表
        """
        messages: List[Dict[str, Any]] = []

        # 1. 从 WorkLogStorage 获取条目
        work_entries = await self._get_work_entries(max_entries)
        if not work_entries:
            return messages

        # 2. 转换为 Function Call 消息格式
        import uuid
        from .gpts.file_base import WorkLogStatus

        compressed_count = 0

        for entry in work_entries:
            is_compressed = (
                hasattr(entry, "status")
                and entry.status == WorkLogStatus.COMPRESSED.value
            )

            # 如果不使用压缩摘要且条目已压缩，则跳过（不推荐，会导致信息丢失）
            if not use_compressed_summary and is_compressed:
                continue

            # 生成唯一的 tool_call_id
            tool_call_id = f"tc_{entry.tool}_{uuid.uuid4().hex[:8]}"

            # 构建 assistant 消息（包含 tool_calls）
            tool_call = {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": entry.tool,
                    "arguments": json.dumps(entry.args) if entry.args else "{}",
                },
            }

            messages.append(
                {
                    "role": "assistant",
                    "content": "",  # 工具调用时 content 通常为空
                    "tool_calls": [tool_call],
                }
            )

            # 构建 tool 消息（工具结果）
            # 根据压缩状态选择内容
            if is_compressed:
                # 压缩条目：优先使用 summary，保证上下文连续性
                result_content = entry.summary or entry.result or ""
                if result_content:
                    result_content = f"[压缩摘要] {result_content}"
                compressed_count += 1
            else:
                # 未压缩条目：优先使用原始 result
                result_content = entry.result or entry.summary or ""

            if entry.full_result_archive:
                # 如果结果被归档，添加提示
                result_content = (
                    f"{result_content}\n\n[完整结果已归档: {entry.full_result_archive}]"
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_content,
                }
            )

        if compressed_count > 0:
            logger.info(
                f"Converted {len(work_entries)} work entries to {len(messages)} tool messages "
                f"({compressed_count} compressed entries using summaries)"
            )
        else:
            logger.info(
                f"Converted {len(work_entries)} work entries to {len(messages)} tool messages"
            )
        return messages

    async def _get_work_entries(self, max_entries: int) -> List[Any]:
        """获取 WorkEntry 列表（包含所有状态，由调用方决定如何处理压缩条目）"""
        entries = []

        # 优先从 WorkLogStorage 获取
        if self.work_log_storage:
            try:
                entries = list(
                    await self.work_log_storage.get_work_log(self.session_id)
                )
                # 限制条目数
                if len(entries) > max_entries:
                    entries = entries[-max_entries:]
            except Exception as e:
                logger.warning(f"Failed to get work log from storage: {e}")

        # 如果没有条目，尝试从历史章节恢复
        if not entries and self._catalog is not None:
            chapters = getattr(self._catalog, "chapters", None)
            if chapters:
                entries = await self._recover_entries_from_chapters(max_entries)

        return entries

    async def _recover_entries_from_chapters(self, max_entries: int) -> List[Any]:
        """从历史章节恢复 WorkEntry"""
        from .gpts.file_base import WorkEntry

        entries = []

        if self._catalog is None:
            return entries

        chapters = getattr(self._catalog, "chapters", [])
        if not chapters:
            return entries

        sorted_chapters = sorted(chapters, key=lambda c: c.time_range[0], reverse=True)

        for chapter in sorted_chapters:
            if len(entries) >= max_entries:
                break

            # 从章节的 tool_call_count 和 summary 推断工具调用
            # 这是一个简化实现，实际可能需要从归档文件恢复
            if chapter.tool_call_count > 0 and chapter.summary:
                # 从摘要中解析工具名称
                tool_names = chapter.key_tools if chapter.key_tools else []
                for i, tool_name in enumerate(tool_names[: chapter.tool_call_count]):
                    entry = WorkEntry(
                        timestamp=chapter.time_range[0] + i,
                        tool=tool_name,
                        summary=chapter.summary[:500],
                        success=True,
                    )
                    entries.append(entry)

        return entries[:max_entries]
