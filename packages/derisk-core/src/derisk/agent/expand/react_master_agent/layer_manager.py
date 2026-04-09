"""
LayerManager - 三层增量压缩管理器

核心设计：
1. 写入时分层：新 Entry 写入时确定层级
2. 触发式迁移：超预算时自动迁移到下一层
3. Buffer 预留：预留空间避免频繁迁移
4. 读取无重算：直接读取缓存，O(1) 复杂度

三层结构：
- Hot Layer: 最新条目，完整保留
- Warm Layer: 中间条目，压缩 + 智能剪枝
- Cold Layer: 最旧条目，对话级 LLM 摘要

迁移粒度：
- Hot → Warm: 条目级别
- Warm → Cold: 对话级别（保留上下文关联）
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable, TYPE_CHECKING

# 与 history_message_builder.DEFAULT_CHARS_PER_TOKEN 保持一致
DEFAULT_CHARS_PER_TOKEN = 4

if TYPE_CHECKING:
    from .work_log import WorkEntry

logger = logging.getLogger(__name__)


@dataclass
class LayerMigrationConfig:
    """分层迁移配置"""

    # 统一压缩参数：与 HistoryMessageBuilder.CompressionConfig 和
    # SessionHistoryManagerConfig 保持一致，避免分层边界错乱
    hot_ratio: float = 0.45
    warm_ratio: float = 0.25
    cold_ratio: float = 0.10

    hot_buffer_ratio: float = 0.15
    warm_buffer_ratio: float = 0.15

    migration_batch_min: int = 3

    enable_duplicate_prune: bool = True
    enable_error_prune: bool = True
    error_prune_after_turns: int = 4
    enable_superseded_prune: bool = True
    enable_llm_prune: bool = False

    warm_tool_result_max_length: int = 500
    cold_summary_max_length: int = 300

    preserve_tools: List[str] = field(
        default_factory=lambda: [
            "read_file",
            "search_code",
            "execute_query",
            "list_files",
        ]
    )

    # 保护工具模式：特定工具的特定参数模式完整保留（如 view skill.md）
    preserve_tools_patterns: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "view": ["skill.md"],
        }
    )

    migration_debounce_ms: int = 500

    chars_per_token: int = DEFAULT_CHARS_PER_TOKEN

    def calculate_budgets(self, context_window: int) -> Dict[str, int]:
        return {
            "hot": int(context_window * self.hot_ratio),
            "warm": int(context_window * self.warm_ratio),
            "cold": int(context_window * self.cold_ratio),
        }

    def calculate_buffers(self, budgets: Dict[str, int]) -> Dict[str, int]:
        return {
            "hot": int(budgets["hot"] * self.hot_buffer_ratio),
            "warm": int(budgets["warm"] * self.warm_buffer_ratio),
        }


@dataclass
class EntryWrapper:
    """Entry 包装器，附加分层状态

    layer: 存储位置 ("hot" / "warm")
    compression_level: 压缩策略 ("full" / "pending" / "compressed" / "summarized")
        - "full": 完整保留（Hot 层默认）
        - "pending": 已迁入 Warm，待剪枝后压缩
        - "compressed": 适度压缩（剪枝后压缩完成）
        - "summarized": 高度压缩/摘要（Warm→Cold 迁移后）
    """

    entry: Any
    layer: str = "hot"
    compression_level: str = "full"  # "full" | "pending" | "compressed" | "summarized"
    compressed_result: Optional[str] = None
    compressed_tokens: int = 0
    signature: Optional[str] = None

    @property
    def tokens(self) -> int:
        if self.compression_level in ("compressed", "summarized") and self.compressed_tokens > 0:
            return self.compressed_tokens
        return getattr(self.entry, "tokens", 0) or 0

    @property
    def timestamp(self) -> float:
        return getattr(self.entry, "timestamp", 0) or 0

    @property
    def tool(self) -> str:
        return getattr(self.entry, "tool", "") or ""

    @property
    def args(self) -> Dict[str, Any]:
        return getattr(self.entry, "args", {}) or {}

    @property
    def result(self) -> str:
        return getattr(self.entry, "result", "") or ""

    @property
    def tool_call_id(self) -> Optional[str]:
        return getattr(self.entry, "tool_call_id", None)

    @property
    def conv_id(self) -> Optional[str]:
        return getattr(self.entry, "conv_id", None)

    @property
    def assistant_content(self) -> str:
        """LLM 返回的非工具调用内容（blank action）"""
        return getattr(self.entry, "assistant_content", "") or ""

    @property
    def human_content(self) -> str:
        """User 消息内容"""
        return getattr(self.entry, "human_content", "") or ""

    @property
    def message_role(self) -> str:
        """
        消息角色类型

        Returns:
            "tool_call": 工具调用（有 tool_call_id）
            "assistant": AI 非工具调用消息（有 assistant_content，无 tool_call_id）
            "user": User 消息（有 human_content）
        """
        if self.tool_call_id:
            return "tool_call"
        elif self.human_content:
            return "user"
        elif self.assistant_content:
            return "assistant"
        return "unknown"

    @property
    def is_blank_action(self) -> bool:
        """是否是 blank action（非工具调用，只有 assistant_content）"""
        return not self.tool_call_id and bool(self.assistant_content)

    @property
    def is_user_message(self) -> bool:
        """是否是 user 消息"""
        return bool(self.human_content)


@dataclass
class ColdSummary:
    """Cold 层对话摘要

    支持多步摘要：ai_answers 列表，每个元素对应一个阶段的 AI 回答。
    保留 ai_answer 属性以兼容旧代码。
    """

    conv_id: str
    user_question: str  # User 问题部分
    ai_answers: List[str] = field(default_factory=list)  # 多步 AI 回答
    summary: str = ""  # 完整摘要（用于调试）
    tokens: int = 0
    timestamp: float = 0
    entry_count: int = 0

    # 兼容旧的单步 ai_answer
    ai_answer: str = ""

    def __post_init__(self):
        # 如果通过旧的 ai_answer 参数创建，自动填充 ai_answers
        if self.ai_answer and not self.ai_answers:
            self.ai_answers = [self.ai_answer]
        # 如果通过新的 ai_answers 参数创建，同步 ai_answer
        if self.ai_answers and not self.ai_answer:
            self.ai_answer = self.ai_answers[0] if self.ai_answers else ""


@dataclass
class LayerState:
    """单层状态"""

    entries: List[EntryWrapper] = field(default_factory=list)
    tokens: int = 0
    budget: int = 0
    buffer: int = 0
    compressed_cache: Optional[List[Dict[str, Any]]] = None
    cache_valid: bool = False

    def is_overflow(self) -> bool:
        return self.tokens > self.budget - self.buffer

    def available_space(self) -> int:
        return max(0, self.budget - self.buffer - self.tokens)

    def invalidate_cache(self):
        self.cache_valid = False
        self.compressed_cache = None


class LayerManager:
    """
    三层增量压缩管理器

    核心职责：
    1. 管理三层状态
    2. 触发式迁移
    3. 智能剪枝
    4. 缓存管理
    """

    def __init__(
        self,
        config: Optional[LayerMigrationConfig] = None,
        llm_client: Optional[Any] = None,
    ):
        self.config = config or LayerMigrationConfig()
        self.llm_client = llm_client

        self.hot = LayerState()
        self.warm = LayerState()
        self.cold_summaries: List[ColdSummary] = []
        self.cold_tokens: int = 0

        self._signatures: Dict[str, EntryWrapper] = {}
        self._conv_entries: Dict[str, List[EntryWrapper]] = {}

        self._lock = asyncio.Lock()
        self._last_migration_time: float = 0
        self._pending_migration: bool = False
        self._deferred_task: Optional[asyncio.Task] = None

        self._migration_callbacks: List[Callable] = []

        logger.info(
            f"LayerManager initialized with budgets: "
            f"hot={self.hot.budget}, warm={self.warm.budget}"
        )

    def set_budgets(self, context_window: int):
        """设置预算"""
        budgets = self.config.calculate_budgets(context_window)
        buffers = self.config.calculate_buffers(budgets)

        self.hot.budget = budgets["hot"]
        self.hot.buffer = buffers["hot"]
        self.warm.budget = budgets["warm"]
        self.warm.buffer = buffers["warm"]

        logger.info(
            f"LayerManager budgets set: "
            f"hot={self.hot.budget} (buffer={self.hot.buffer}), "
            f"warm={self.warm.budget} (buffer={self.warm.buffer})"
        )

    def register_migration_callback(self, callback: Callable):
        """注册迁移回调"""
        self._migration_callbacks.append(callback)

    async def _notify_migration(self, event: str, count: int, tokens: int):
        """通知迁移事件"""
        for callback in self._migration_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, count, tokens)
                else:
                    callback(event, count, tokens)
            except Exception as e:
                logger.error(f"Migration callback error: {e}")

    def _compute_signature(self, entry: EntryWrapper) -> str:
        """计算条目签名（用于去重）

        User 消息不参与去重（返回空签名）
        """
        # User 消息不去重
        if entry.human_content:
            return ""

        # 保护工具不去重
        if entry.tool in self.config.preserve_tools:
            return ""

        args_str = json.dumps(entry.args, sort_keys=True, ensure_ascii=False)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:8]
        return f"{entry.tool}:{args_hash}"

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数"""
        return max(1, len(text) // self.config.chars_per_token)

    def get_entries_by_layer(
        self, conv_id: Optional[str] = None
    ) -> Tuple[List[EntryWrapper], List[EntryWrapper], List["ColdSummary"]]:
        """返回按层分类的 entries

        Args:
            conv_id: 可选，仅返回指定对话的 entries

        Returns:
            (hot_entries, warm_entries, cold_summaries)
        """
        if conv_id:
            conv_entries = self._conv_entries.get(conv_id, [])
            hot = [e for e in conv_entries if e.layer == "hot"]
            warm = [e for e in conv_entries if e.layer == "warm"]
        else:
            hot = list(self.hot.entries)
            warm = list(self.warm.entries)
        return hot, warm, list(self.cold_summaries)

    async def add_entry(
        self,
        entry: Any,
        trigger_migration: bool = True,
    ) -> EntryWrapper:
        """
        添加新条目（写入时分层）

        默认进入 Hot 层，如果超预算则触发迁移。
        """
        async with self._lock:
            wrapper = EntryWrapper(entry=entry, layer="hot")
            wrapper.signature = self._compute_signature(wrapper)

            self.hot.entries.append(wrapper)
            self.hot.tokens += wrapper.tokens
            self.hot.invalidate_cache()

            conv_id = wrapper.conv_id
            if conv_id:
                if conv_id not in self._conv_entries:
                    self._conv_entries[conv_id] = []
                self._conv_entries[conv_id].append(wrapper)

            if wrapper.signature and self.config.enable_duplicate_prune:
                if wrapper.signature in self._signatures:
                    old_wrapper = self._signatures[wrapper.signature]
                    await self._remove_entry_from_layer(old_wrapper)
                    logger.debug(f"Pruned duplicate entry: {wrapper.signature}")
                self._signatures[wrapper.signature] = wrapper

            logger.debug(
                f"Entry added to Hot layer: tool={wrapper.tool}, "
                f"tokens={wrapper.tokens}, hot_total={self.hot.tokens}"
            )

            if trigger_migration:
                await self._check_and_migrate()

            return wrapper

    async def _remove_entry_from_layer(self, wrapper: EntryWrapper):
        """从层中移除条目"""
        if wrapper.layer == "hot":
            if wrapper in self.hot.entries:
                self.hot.entries.remove(wrapper)
                self.hot.tokens -= wrapper.tokens
                self.hot.invalidate_cache()
        elif wrapper.layer == "warm":
            if wrapper in self.warm.entries:
                self.warm.entries.remove(wrapper)
                self.warm.tokens -= wrapper.tokens
                self.warm.invalidate_cache()

        if wrapper.signature and wrapper.signature in self._signatures:
            if self._signatures[wrapper.signature] == wrapper:
                del self._signatures[wrapper.signature]

    async def _check_and_migrate(self):
        """检查并触发迁移（带 debounce 和延迟重检）

        P1-3 修复: debounce 期间安排延迟执行，防止迁移丢失
        """
        now = time.time() * 1000
        if now - self._last_migration_time < self.config.migration_debounce_ms:
            # debounce 期间标记待迁移，安排延迟执行
            self._pending_migration = True
            self._schedule_deferred_migration()
            return

        await self._do_migration()
        self._last_migration_time = now

    def _schedule_deferred_migration(self):
        """安排 debounce 结束后自动执行待迁移（防止迁移丢失）"""
        if getattr(self, "_deferred_task", None) and not self._deferred_task.done():
            return  # 已有延迟任务在等待

        async def _deferred():
            delay_s = self.config.migration_debounce_ms / 1000.0
            await asyncio.sleep(delay_s)
            async with self._lock:
                if self._pending_migration:
                    await self._do_migration()
                    self._last_migration_time = time.time() * 1000

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._deferred_task = asyncio.ensure_future(_deferred())
            else:
                self._deferred_task = None
        except RuntimeError:
            self._deferred_task = None

    async def _do_migration(self):
        """执行实际迁移"""
        self._pending_migration = False

        if self.hot.is_overflow():
            await self._migrate_hot_to_warm()

        if self.warm.is_overflow():
            await self._migrate_warm_to_cold()

    async def check_pending_migration(self):
        """检查并执行被 debounce 延迟的迁移"""
        if getattr(self, "_pending_migration", False):
            await self._do_migration()

    async def _migrate_hot_to_warm(self):
        """Hot → Warm 三级粒度迁移 + 智能剪枝 + 延迟压缩

        流程：
        1. 三级迁移（移动 entry 到 Warm，标记 pending 不压缩）
        2. 全局上下文剪枝（新条目可能淘汰旧条目）
        3. 压缩存活的 entry

        三级迁移策略（从粗到细）：
        Level 1: 按对话维度 — 多对话时迁移最旧的完整对话
        Level 2: 按轮次维度 — 单对话多轮时迁移最旧的 turn
        Level 3: 按 ai+tool 消息对 — 单轮多 tool call 时按对迁移

        User 锚定规则：最近一轮的 user 消息不迁移出 Hot 层（旧轮次的可以迁移）
        """
        if not self.hot.entries:
            return

        migrated_count = 0
        migrated_tokens = 0

        logger.info(
            f"Starting Hot→Warm migration: hot_tokens={self.hot.tokens}, "
            f"budget={self.hot.budget}, buffer={self.hot.buffer}"
        )

        # ── Phase 1: 三级迁移（移动但不压缩）──
        # 注意：每级迁移后检查 overflow，已解决则跳过后续级别
        # 但不能在迁移前检查（Level 1 可能不触发，Level 2 仍需执行）

        # Level 1: 按对话维度迁移
        conv_groups = self._group_hot_by_conversation()
        if len(conv_groups) > 1:
            oldest_conv = min(
                conv_groups.keys(),
                key=lambda cid: conv_groups[cid][0].timestamp if conv_groups[cid] else float("inf"),
            )
            batch = conv_groups[oldest_conv]
            count, tokens = self._migrate_batch(batch)
            migrated_count += count
            migrated_tokens += tokens
            if not self.hot.is_overflow():
                # overflow 已解决，跳过 Level 2/3
                pass  # 继续到 Phase 2 剪枝

        # Level 2: 按轮次维度迁移（user + 后续 ai/tool 直到下一个 user）
        if self.hot.is_overflow() or migrated_count == 0:
            turns = self._split_into_turns(self.hot.entries)
            if len(turns) > 1:
                batch = turns[0]
                first_user = self._find_anchored_user_in_hot()
                if first_user and first_user in batch:
                    batch = [e for e in batch if e is not first_user]
                if batch:
                    count, tokens = self._migrate_batch(batch)
                    migrated_count += count
                    migrated_tokens += tokens

        # Level 3: 按 ai+tool 消息对迁移
        if self.hot.is_overflow():
            migratable = self._get_migratable_pairs(self.hot.entries)
            while self.hot.is_overflow() and migratable:
                pair = migratable.pop(0)
                count, tokens = self._migrate_batch(pair)
                migrated_count += count
                migrated_tokens += tokens

        if migrated_count == 0:
            return

        # ── Phase 2: 全局上下文剪枝（新条目可能淘汰旧条目）──
        pruned_count, freed_tokens = self._prune_warm_entries()

        # ── Phase 3: 压缩存活的未压缩 entry ──
        self._compress_uncompressed()

        self._finish_migration(
            migrated_count, migrated_tokens
        )

    def _finish_migration(self, count: int, tokens: int):
        """完成迁移后的清理"""
        if count > 0:
            self.hot.invalidate_cache()
            self.warm.invalidate_cache()
            logger.info(
                f"Hot→Warm migration complete: migrated={count}, "
                f"tokens={tokens}, hot={self.hot.tokens}, warm={self.warm.tokens}"
            )

    def _migrate_batch(self, entries: List[EntryWrapper]) -> Tuple[int, int]:
        """批量迁移 entries 从 Hot 到 Warm（移动但不压缩）

        迁移后 entry 标记为 compression_level="pending"，
        等待 _prune_warm_entries() 剪枝后再由 _compress_uncompressed() 压缩。

        Returns:
            (migrated_count, migrated_tokens)
        """
        migrated_count = 0
        migrated_tokens = 0

        for entry in entries:
            if entry not in self.hot.entries:
                continue

            original_tokens = entry.tokens
            self.hot.entries.remove(entry)
            self.hot.tokens -= original_tokens

            # P0-2 修复: 迁移到 Warm 后清理 Hot 层签名跟踪
            if entry.signature and entry.signature in self._signatures:
                if self._signatures[entry.signature] == entry:
                    del self._signatures[entry.signature]

            entry.layer = "warm"
            entry.compression_level = "pending"  # 标记待压缩，先剪枝再压缩

            # 用原始 token 计入 Warm 预算（压缩后会更新差值）
            self.warm.entries.append(entry)
            self.warm.tokens += original_tokens

            migrated_count += 1
            migrated_tokens += original_tokens

        return migrated_count, migrated_tokens

    def _prune_warm_entries(self) -> Tuple[int, int]:
        """全局上下文剪枝 — 新条目可能淘汰旧条目

        在所有 Hot→Warm 迁移完成后调用，扫描全部 Warm 层 entries。
        剪枝决策基于元数据（tool/args/success），不依赖内容。

        策略执行顺序：
        1. 重复去重（同 tool + 同 args → 只留最新）
        2. 被覆盖写清理（同文件多次 write → 只留最新）
        3. 已解决错误清理（同工具先 fail 后 success → 删 fail）
        4. 过期错误清理（error 超过 N 轮 → 删除）

        Returns:
            (pruned_count, freed_tokens)
        """
        if not self.warm.entries:
            return 0, 0

        to_remove: set = set()  # entry id() 集合

        # 保护判断：user 消息、blank action、preserve 工具永不剪枝
        def _is_protected(entry: EntryWrapper) -> bool:
            if entry.is_user_message:
                return True
            if entry.is_blank_action:
                return True
            if entry.tool in self.config.preserve_tools:
                return True
            if self._should_preserve_full(entry.tool, entry.args):
                return True
            return False

        # ── 策略 1：重复去重 ──
        # 同 tool + 同 args hash → 只保留 timestamp 最新的
        if self.config.enable_duplicate_prune:
            sig_groups: Dict[str, List[EntryWrapper]] = {}
            for entry in self.warm.entries:
                if _is_protected(entry) or id(entry) in to_remove:
                    continue
                sig = self._compute_signature(entry)
                if not sig:
                    continue
                if sig not in sig_groups:
                    sig_groups[sig] = []
                sig_groups[sig].append(entry)

            for sig, group in sig_groups.items():
                if len(group) <= 1:
                    continue
                # 按 timestamp 降序，保留最新，其余标记删除
                group.sort(key=lambda e: e.timestamp, reverse=True)
                for old_entry in group[1:]:
                    to_remove.add(id(old_entry))
                    logger.debug(
                        f"[Prune] Duplicate removed: {old_entry.tool} "
                        f"(keeping newer at {group[0].timestamp:.0f})"
                    )

        # ── 策略 2：被覆盖写清理 ──
        # 同文件多次 write_file/edit_file → 只保留最新
        if self.config.enable_superseded_prune:
            write_tools = {"write_file", "write_to_file", "edit_file"}
            file_writes: Dict[str, List[EntryWrapper]] = {}
            for entry in self.warm.entries:
                if _is_protected(entry) or id(entry) in to_remove:
                    continue
                if entry.tool not in write_tools:
                    continue
                file_path = str(
                    entry.args.get("path", entry.args.get("file_path", ""))
                )
                if not file_path:
                    continue
                if file_path not in file_writes:
                    file_writes[file_path] = []
                file_writes[file_path].append(entry)

            for file_path, writes in file_writes.items():
                if len(writes) <= 1:
                    continue
                writes.sort(key=lambda e: e.timestamp, reverse=True)
                for old_write in writes[1:]:
                    to_remove.add(id(old_write))
                    logger.debug(
                        f"[Prune] Superseded write removed: {old_write.tool}({file_path})"
                    )

        # ── 策略 3：已解决错误清理 ──
        # 同 tool+args 组内，如果有 success=True 的，则 success=False 的可删
        if self.config.enable_error_prune:
            tool_groups: Dict[str, List[EntryWrapper]] = {}
            for entry in self.warm.entries:
                if _is_protected(entry) or id(entry) in to_remove:
                    continue
                sig = self._compute_signature(entry)
                if not sig:
                    continue
                if sig not in tool_groups:
                    tool_groups[sig] = []
                tool_groups[sig].append(entry)

            for sig, group in tool_groups.items():
                has_success = any(
                    getattr(e.entry, "success", True) for e in group
                )
                if not has_success:
                    continue
                for entry in group:
                    if not getattr(entry.entry, "success", True):
                        to_remove.add(id(entry))
                        logger.debug(
                            f"[Prune] Resolved error removed: {entry.tool} "
                            f"(same tool succeeded later)"
                        )

        # ── 策略 4：过期错误清理 ──
        # success=False 且距离最新 entry 超过 N 轮 → 删除
        if self.config.enable_error_prune and self.warm.entries:
            max_round = max(
                getattr(e.entry, "round_index", 0) for e in self.warm.entries
            )
            threshold = self.config.error_prune_after_turns
            for entry in self.warm.entries:
                if _is_protected(entry) or id(entry) in to_remove:
                    continue
                if not getattr(entry.entry, "success", True):
                    entry_round = getattr(entry.entry, "round_index", 0)
                    if max_round - entry_round > threshold:
                        to_remove.add(id(entry))
                        logger.debug(
                            f"[Prune] Expired error removed: {entry.tool} "
                            f"(round {entry_round}, current {max_round})"
                        )

        # ── 执行删除 ──
        if not to_remove:
            return 0, 0

        pruned_count = 0
        freed_tokens = 0
        surviving = []
        for entry in self.warm.entries:
            if id(entry) in to_remove:
                freed_tokens += entry.tokens
                pruned_count += 1
                # 清理 conv_entries 引用
                if entry.conv_id and entry.conv_id in self._conv_entries:
                    ce = self._conv_entries[entry.conv_id]
                    if entry in ce:
                        ce.remove(entry)
                    if not ce:
                        del self._conv_entries[entry.conv_id]
            else:
                surviving.append(entry)

        self.warm.entries = surviving
        self.warm.tokens -= freed_tokens

        logger.info(
            f"[Prune] Warm layer pruned: removed={pruned_count}, "
            f"freed_tokens={freed_tokens}, remaining={len(self.warm.entries)}, "
            f"warm_tokens={self.warm.tokens}"
        )

        return pruned_count, freed_tokens

    def _compress_uncompressed(self):
        """压缩 Warm 层中尚未压缩的 entry（剪枝后调用）

        遍历 Warm entries，对 compression_level="pending" 的执行压缩，
        更新 token 差值确保 warm.tokens 准确。
        """
        for entry in self.warm.entries:
            if entry.compression_level != "pending":
                continue

            original_tokens = entry.tokens  # pending 状态返回原始 tokens
            entry.compression_level = "compressed"
            entry.compressed_result = self._compress_for_warm(entry)

            if entry.human_content:
                entry.compressed_tokens = self._estimate_tokens(entry.human_content)
            else:
                entry.compressed_tokens = self._estimate_tokens(
                    entry.compressed_result
                )

            # 更新 Warm 层 token 差值（原始→压缩后）
            token_diff = entry.compressed_tokens - original_tokens
            self.warm.tokens += token_diff

        self.warm.invalidate_cache()

    def _group_hot_by_conversation(self) -> Dict[str, List[EntryWrapper]]:
        """按对话 ID 分组 Hot 层 entries"""
        groups: Dict[str, List[EntryWrapper]] = {}
        for entry in self.hot.entries:
            cid = entry.conv_id or "_default"
            if cid not in groups:
                groups[cid] = []
            groups[cid].append(entry)
        return groups

    def _split_into_turns(self, entries: List[EntryWrapper]) -> List[List[EntryWrapper]]:
        """按 user 消息切分为轮次

        一个 turn = user 消息 + 后续所有 ai/tool 消息（直到下一个 user）
        """
        if not entries:
            return []

        turns: List[List[EntryWrapper]] = []
        current_turn: List[EntryWrapper] = []

        for entry in entries:
            if entry.is_user_message and current_turn:
                turns.append(current_turn)
                current_turn = []
            current_turn.append(entry)

        if current_turn:
            turns.append(current_turn)

        return turns

    def _get_migratable_pairs(self, entries: List[EntryWrapper]) -> List[List[EntryWrapper]]:
        """提取可迁移的 ai+tool 消息对（从最旧开始）

        跳过 user 消息，锚定保护最近一轮的 user 消息
        跳过 preserve_tools_patterns 匹配的工具调用（如 view skill.md）
        """
        first_user = self._find_anchored_user_in_hot()
        pairs: List[List[EntryWrapper]] = []

        for entry in entries:
            # 跳过 user 消息（不单独迁移）
            if entry.is_user_message:
                continue
            # 跳过第一个 user 关联的消息（锚定保护）
            if first_user and entry is first_user:
                continue
            # 跳过 preserve 工具调用（如 view skill.md），保留在 Hot 层
            if self._should_preserve_full(entry.tool, entry.args):
                continue
            pairs.append([entry])

        return pairs

    def _find_anchored_user_in_hot(self) -> Optional[EntryWrapper]:
        """找到 Hot 层中需要锚定的 user 消息

        锚定规则：保护最近一轮的 user 消息（而非第一轮）
        - 多轮对话中，旧轮次的 user 可以随 turn 迁移
        - 最近一轮的 user 是当前活跃目标，必须保留在 Hot
        """
        last_user = None
        for entry in self.hot.entries:
            if entry.is_user_message:
                last_user = entry
        return last_user

    def _should_preserve_full(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        判断是否应该保留完整结果（基于工具名称和参数模式）

        保护特定工具的特定参数模式，例如：
        - view 工具的 skill.md 后缀路径
        """
        patterns = self.config.preserve_tools_patterns.get(tool_name, [])
        if not patterns:
            return False

        path = str(args.get("path", args.get("file_path", "")))
        for pattern in patterns:
            if path.endswith(pattern):
                return True
        return False

    def _compress_for_warm(self, wrapper: EntryWrapper) -> str:
        """Warm 层压缩"""
        # User 消息直接返回
        if wrapper.is_user_message:
            content = wrapper.human_content
            if len(content) > self.config.warm_tool_result_max_length:
                return content[: self.config.warm_tool_result_max_length] + "..."
            return content

        # 如果是 blank action（非工具调用），直接返回 assistant_content
        if wrapper.is_blank_action:
            content = wrapper.assistant_content
            if len(content) > self.config.warm_tool_result_max_length:
                return content[: self.config.warm_tool_result_max_length] + "..."
            return content

        result = wrapper.result

        # 检查是否应该保留完整结果
        if self._should_preserve_full(wrapper.tool, wrapper.args):
            return result

        if len(result) > self.config.warm_tool_result_max_length:
            result = result[: self.config.warm_tool_result_max_length]
            archive_ref = getattr(wrapper.entry, "full_result_archive", None)
            if archive_ref:
                result += f"\n...详情见: {archive_ref}"

        return result

    async def _migrate_warm_to_cold(self):
        """Warm → Cold 迁移（对话级别）

        迁移 Warm 层中该对话的所有条目，不要求对话完整
        Cold 摘要只包含已迁移部分，后续部分在 Hot 层
        """
        if not self.warm.entries:
            return

        migrated_convs = 0
        migrated_tokens = 0

        logger.info(f"Starting Warm→Cold migration: warm_tokens={self.warm.tokens}")

        while self.warm.is_overflow() and self.warm.entries:
            conv_id = self._find_oldest_conv_in_warm()
            if not conv_id:
                break

            # 收集 Warm 层中该对话的所有条目
            conv_entries = [e for e in self.warm.entries if e.conv_id == conv_id]

            if not conv_entries:
                break

            # 移除条目
            for e in conv_entries:
                self.warm.entries.remove(e)
                self.warm.tokens -= e.compressed_tokens

            logger.info(
                f"[Warm→Cold] Migrating conv {conv_id}: {len(conv_entries)} entries"
            )

            # 调试信息
            for e in conv_entries:
                if e.human_content:
                    logger.info(f"[Warm→Cold] user: {e.human_content[:50]}")
                if e.is_blank_action:
                    logger.info(f"[Warm→Cold] blank: {e.assistant_content[:50] if e.assistant_content else ''}")

            (
                user_question,
                ai_answers,
                full_summary,
            ) = await self._generate_conv_summary(conv_entries)

            total_summary = f"[历史摘要] {user_question}\n" + "\n".join(
                f"[历史摘要] {a}" for a in ai_answers
            )
            summary_tokens = self._estimate_tokens(total_summary)

            cold_summary = ColdSummary(
                conv_id=conv_id,
                user_question=user_question,
                ai_answers=ai_answers,
                ai_answer=ai_answers[0] if ai_answers else "",
                summary=full_summary,
                tokens=summary_tokens,
                timestamp=conv_entries[-1].timestamp,
                entry_count=len(conv_entries),
            )

            self.cold_summaries.append(cold_summary)
            self.cold_tokens += cold_summary.tokens

            # P0-2 修复: Cold 迁移后清理 _conv_entries 和 _signatures 引用
            for e in conv_entries:
                if e.signature and e.signature in self._signatures:
                    if self._signatures[e.signature] == e:
                        del self._signatures[e.signature]
            if conv_id in self._conv_entries:
                # 仅移除已迁移到 Cold 的条目，保留仍在 Hot 层的条目
                remaining = [
                    e for e in self._conv_entries[conv_id]
                    if e not in conv_entries
                ]
                if remaining:
                    self._conv_entries[conv_id] = remaining
                else:
                    del self._conv_entries[conv_id]

            migrated_convs += 1
            migrated_tokens += sum(e.compressed_tokens for e in conv_entries)

        self.warm.invalidate_cache()

        logger.info(
            f"Warm→Cold migration complete: migrated_convs={migrated_convs}, "
            f"tokens={migrated_tokens}, warm={self.warm.tokens}, cold={self.cold_tokens}"
        )

        await self._notify_migration("warm_to_cold", migrated_convs, migrated_tokens)

    def _find_oldest_conv_in_warm(self) -> Optional[str]:
        """找到 Warm 层最早的对话"""
        if not self.warm.entries:
            return None

        conv_timestamps: Dict[str, float] = {}
        for e in self.warm.entries:
            conv_id = e.conv_id
            if conv_id:
                if conv_id not in conv_timestamps or e.timestamp < conv_timestamps[conv_id]:
                    conv_timestamps[conv_id] = e.timestamp

        if not conv_timestamps:
            return None

        return min(conv_timestamps, key=conv_timestamps.get)

    async def _generate_conv_summary(
        self, entries: List[EntryWrapper]
    ) -> Tuple[str, List[str], str]:
        """生成对话摘要，返回 (user_question, ai_answers, full_summary)

        支持多步摘要：按 turn 拆分对话，每个 turn 生成一个 ai_answer。
        """
        # 收集完整对话内容
        user_questions = []
        blank_actions = []
        tool_calls_summary = []

        # 按 turn 拆分（每个 user 消息开始一个新 turn）
        turns: List[List[EntryWrapper]] = []
        current_turn: List[EntryWrapper] = []
        for e in entries:
            if e.human_content:
                user_questions.append(e.human_content)
                if current_turn:
                    turns.append(current_turn)
                current_turn = [e]
            else:
                current_turn.append(e)
                if e.is_blank_action and e.assistant_content:
                    blank_actions.append(e.assistant_content)
                if e.tool and e.result:
                    tool_calls_summary.append(f"- {e.tool}: {e.result[:100]}")
        if current_turn:
            turns.append(current_turn)

        # 构建完整对话文本
        conversation_text = ""
        if user_questions:
            conversation_text += f"【用户问题】\n{chr(10).join(user_questions)}\n\n"
        if tool_calls_summary:
            conversation_text += (
                f"【工具调用】\n{chr(10).join(tool_calls_summary[:10])}\n\n"
            )
        if blank_actions:
            conversation_text += f"【AI最终回答】\n{chr(10).join(blank_actions)}\n"

        # 用 LLM 总结
        if self.llm_client and conversation_text:
            try:
                prompt = f"""请总结以下对话，提炼核心问题和答案结论：

{conversation_text}

请按以下格式输出（简洁，不超过{self.config.cold_summary_max_length}字）：
问题: [用户问题的核心]
回答: [AI给出的答案/结论]"""

                llm_summary = await self.llm_client.acall(prompt)

                # 解析 LLM 输出
                user_question = ""
                ai_answers = []
                for line in llm_summary.split("\n"):
                    if line.startswith("问题:"):
                        user_question = line.replace("问题:", "").strip()
                    elif line.startswith("回答:"):
                        ai_answers.append(line.replace("回答:", "").strip())

                # 如果解析失败，使用原始内容
                if not user_question:
                    user_question = "; ".join(user_questions[:2])
                if not ai_answers:
                    ai_answers = (
                        blank_actions[:3]
                        if blank_actions
                        else ["通过工具调用解决"]
                    )

                return (
                    user_question[:100],
                    [a[:200] for a in ai_answers],
                    llm_summary[: self.config.cold_summary_max_length],
                )
            except Exception as e:
                logger.error(f"LLM summary failed: {e}")

        # 没有 LLM 或失败时，按 turn 生成多步摘要
        user_question = "; ".join(user_questions[:2]) if user_questions else ""

        # 生成多步 ai_answers：每个 turn 的 blank_action 或工具调用概述
        ai_answers = []
        for turn in turns:
            turn_blanks = [e.assistant_content for e in turn if e.is_blank_action and e.assistant_content]
            turn_tools = [e.tool for e in turn if e.tool]
            if turn_blanks:
                ai_answers.append("; ".join(turn_blanks)[:200])
            elif turn_tools:
                ai_answers.append(f"执行了: {', '.join(turn_tools[:5])}")

        if not ai_answers:
            ai_answers = ["通过工具调用解决"] if tool_calls_summary else [""]

        full_summary = f"问题: {user_question}\n" + "\n".join(f"回答{i+1}: {a}" for i, a in enumerate(ai_answers))
        return (
            user_question[:100],
            ai_answers,
            full_summary[: self.config.cold_summary_max_length],
        )

    # 注：Dict 级别的智能剪枝逻辑已移至 _prune_warm_entries()（EntryWrapper 级别）
    # HistoryMessageBuilder 中的 _smart_prune_messages() 作为跨会话历史的安全网保留

    def build_messages(
        self,
        hot_messages_builder: Optional[Callable[[Any], List[Dict[str, Any]]]] = None,
        warm_messages_builder: Optional[Callable[[Any], str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        构建消息列表 — 层=压缩策略，按时间顺序输出

        核心设计：
        1. Cold 摘要（跨对话级别，时间最早）放在最前
        2. 所有 Hot+Warm entries 按时间排序，应用各自的压缩策略
        3. 保证同一对话内 user 在 ai/tool 之前（时间序自然保证）
        """
        messages: List[Dict[str, Any]] = []
        layer_tokens = {"hot": 0, "warm": 0, "cold": 0}

        # 1. Cold 摘要放在最前（已完成的旧对话）
        cold_messages = self._build_cold_messages()
        messages.extend(cold_messages)
        layer_tokens["cold"] = self.cold_tokens

        # 2. 所有 Hot+Warm entries 按时间排序，应用各自的压缩策略
        all_entries = sorted(
            list(self.warm.entries) + list(self.hot.entries),
            key=lambda e: e.timestamp,
        )

        for entry in all_entries:
            entry_messages = self._build_entry_messages(entry)
            messages.extend(entry_messages)
            if entry.compression_level == "compressed":
                layer_tokens["warm"] += entry.tokens
            else:
                layer_tokens["hot"] += entry.tokens

        return messages, layer_tokens

    def _build_entry_messages(self, wrapper: EntryWrapper) -> List[Dict[str, Any]]:
        """根据 compression_level 构建单个 entry 的消息"""
        messages = []

        # User 消息
        if wrapper.is_user_message:
            content = wrapper.human_content
            if wrapper.compression_level == "compressed" and wrapper.compressed_result:
                content = wrapper.compressed_result
            messages.append({"role": "user", "content": content})
            return messages

        # Blank Action（非工具调用，只有 assistant_content）
        if wrapper.is_blank_action:
            content = wrapper.assistant_content
            if wrapper.compression_level == "compressed" and wrapper.compressed_result:
                content = wrapper.compressed_result
            if content:
                messages.append({"role": "assistant", "content": content})
            return messages

        if not wrapper.tool_call_id:
            return messages

        # Tool call: assistant + tool response
        messages.append(
            {
                "role": "assistant",
                "content": wrapper.assistant_content,
                "tool_calls": [
                    {
                        "id": wrapper.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": wrapper.tool,
                            "arguments": json.dumps(wrapper.args),
                        },
                    }
                ],
            }
        )

        # 根据压缩级别选择 result
        if wrapper.compression_level == "compressed" and wrapper.compressed_result:
            result = wrapper.compressed_result
        else:
            result = wrapper.result
            archive_ref = getattr(wrapper.entry, "full_result_archive", None)
            if archive_ref:
                result = f"{result[:500]}...\n详情: {archive_ref}"

        messages.append(
            {
                "role": "tool",
                "tool_call_id": wrapper.tool_call_id,
                "content": result,
            }
        )

        return messages

    def _build_cold_messages(self) -> List[Dict[str, Any]]:
        """构建 Cold 层消息（user + assistant 消息对，支持多步摘要）"""
        messages = []
        for summary in self.cold_summaries:
            # User 消息
            if summary.user_question:
                messages.append(
                    {
                        "role": "user",
                        "content": f"[历史摘要] {summary.user_question}",
                    }
                )
            # 多步 AI 回答
            if summary.ai_answers:
                for answer in summary.ai_answers:
                    if answer:
                        messages.append(
                            {
                                "role": "assistant",
                                "content": f"[历史摘要] {answer}",
                            }
                        )
            elif summary.ai_answer:
                # 兼容旧的单步格式
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"[历史摘要] {summary.ai_answer}",
                    }
                )
        return messages

    # _build_warm_messages / _build_hot_messages 已删除
    # 统一使用 build_messages() → _build_entry_messages() 路径

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "hot": {
                "entries": len(self.hot.entries),
                "tokens": self.hot.tokens,
                "budget": self.hot.budget,
                "buffer": self.hot.buffer,
                "overflow": self.hot.is_overflow(),
            },
            "warm": {
                "entries": len(self.warm.entries),
                "tokens": self.warm.tokens,
                "budget": self.warm.budget,
                "buffer": self.warm.buffer,
                "overflow": self.warm.is_overflow(),
            },
            "cold": {
                "summaries": len(self.cold_summaries),
                "tokens": self.cold_tokens,
            },
            "signatures_tracked": len(self._signatures),
            "conversations_tracked": len(self._conv_entries),
        }

    def clear(self):
        """清空所有状态"""
        self.hot.entries.clear()
        self.hot.tokens = 0
        self.hot.invalidate_cache()

        self.warm.entries.clear()
        self.warm.tokens = 0
        self.warm.invalidate_cache()

        self.cold_summaries.clear()
        self.cold_tokens = 0

        self._signatures.clear()
        self._conv_entries.clear()

        # 取消延迟迁移任务
        deferred = getattr(self, "_deferred_task", None)
        if deferred and not deferred.done():
            deferred.cancel()


__all__ = [
    "LayerManager",
    "LayerMigrationConfig",
    "LayerState",
    "EntryWrapper",
    "ColdSummary",
]
