"""
WorkLog 管理器 - 增量分层版本

职责：
1. 记录工具调用（WorkEntry）
2. 持久化存储
3. 提供查询接口
4. 集成 LayerManager 实现增量分层
5. 对话内压缩缓存

增量分层设计：
- 新 Entry 写入时自动进入 Hot 层
- 触发式迁移：超预算时自动迁移到 Warm/Cold 层
- 读取无重算：直接从 LayerManager 读取缓存
"""

import asyncio
import json
import logging
import time
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from derisk.agent import ActionOutput
from ...core.file_system.agent_file_system import AgentFileSystem
from ...core.memory.gpts.file_base import (
    WorkLogStorage,
    WorkLogStatus,
    WorkEntry,
    WorkLogSummary,
    FileType,
)

from .history_message_builder import DEFAULT_CHARS_PER_TOKEN

if TYPE_CHECKING:
    from .layer_manager import LayerManager

logger = logging.getLogger(__name__)


@dataclass
class WorkLogCompressionCache:
    """对话内压缩缓存"""

    layer3_summary: Optional[str] = None
    layer3_end_index: int = 0
    layer2_start_index: int = 0
    last_total_entries: int = 0
    last_compressed_tokens: int = 0

    def needs_recompression(
        self, total_entries: int, new_entries_threshold: int = 20
    ) -> bool:
        return total_entries - self.last_total_entries >= new_entries_threshold


def format_entry_for_prompt(entry: WorkEntry, max_length: int = 500) -> str:
    """格式化工作日志条目为 prompt 文本"""
    time_str = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))

    lines = [f"[{time_str}] {entry.tool}"]

    if entry.args:
        important_args = {
            k: v
            for k, v in entry.args.items()
            if k in ["file_key", "path", "query", "pattern", "offset", "limit"]
        }
        if important_args:
            lines.append(f"  参数: {important_args}")

    if entry.result:
        result_lines = entry.result.split("\n")[:10]
        preview = "\n".join(result_lines)
        if len(preview) > max_length:
            preview = preview[:max_length] + "... (已截断)"
        if len(entry.result.split("\n")) > 10:
            preview += "\n  ... (共 {} 行)".format(len(entry.result.split("\n")))
        lines.append(f"  {preview}")
    elif getattr(entry, "full_result_archive", None):
        lines.append(f"  完整结果已归档: {entry.full_result_archive}")

    return "\n".join(lines)


class WorkLogManager:
    """
    工作日志管理器 - 集成增量分层

    职责：
    1. 记录工具调用
    2. 持久化存储
    3. 集成 LayerManager 实现增量分层
    4. 对话内压缩缓存管理
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        agent_file_system: Optional[AgentFileSystem] = None,
        work_log_storage: Optional[WorkLogStorage] = None,
        layer_manager: Optional["LayerManager"] = None,
        context_window: Optional[int] = None,
    ):
        self.agent_id = agent_id
        self.session_id = session_id
        self.afs = agent_file_system
        self._work_log_storage = work_log_storage

        self.work_log: List[WorkEntry] = []
        self.work_log_file_key = f"{agent_id}_{session_id}_work_log"

        self.large_result_threshold_bytes = 10 * 1024
        self.chars_per_token = DEFAULT_CHARS_PER_TOKEN

        self.read_archive_preview_length = 2000
        self.summary_only_tools = {"grep", "search", "find"}
        self.interactive_tools = {"ask_user", "send_message"}

        self._lock = asyncio.Lock()
        self._loaded = False

        # P2-4 修复: 自动跟踪 round_index，按 conv_id 计数
        self._round_counters: Dict[str, int] = {}

        # 对话内压缩缓存：conv_id -> WorkLogCompressionCache
        self.compression_cache: Dict[str, WorkLogCompressionCache] = {}

        # 增量分层管理器：立即创建（使用默认配置）
        if layer_manager:
            self._layer_manager = layer_manager
            logger.info(
                f"WorkLogManager: LayerManager 已集成（外部传入），启用增量分层"
            )
        else:
            from .layer_manager import LayerManager, LayerMigrationConfig

            default_context_window = context_window or 256000
            default_config = LayerMigrationConfig(
                hot_ratio=0.45,
                warm_ratio=0.25,
                cold_ratio=0.10,
                chars_per_token=self.chars_per_token,
            )

            self._layer_manager = LayerManager(config=default_config)
            self._layer_manager.set_budgets(default_context_window)

            logger.info(
                f"WorkLogManager: LayerManager 自动创建，context_window={default_context_window}, "
                f"hot_budget={self._layer_manager.hot.budget}, warm_budget={self._layer_manager.warm.budget}"
            )

        if work_log_storage:
            logger.info(f"WorkLogManager 初始化: 使用 WorkLogStorage 模式")
        elif agent_file_system:
            logger.info(f"WorkLogManager 初始化: 使用 AgentFileSystem 模式（兼容）")
        else:
            logger.info(f"WorkLogManager 初始化: 仅内存模式")

    def set_layer_manager(self, layer_manager: "LayerManager"):
        """更新 LayerManager 配置（在 HistoryMessageBuilder 创建时调用）"""
        self._layer_manager = layer_manager
        logger.info(
            f"WorkLogManager: LayerManager 配置已更新, "
            f"hot_budget={layer_manager.hot.budget}, warm_budget={layer_manager.warm.budget}"
        )

    @property
    def storage_mode(self) -> str:
        if self._work_log_storage:
            return "work_log_storage"
        elif self.afs:
            return "agent_file_system"
        else:
            return "memory_only"

    async def initialize(self):
        async with self._lock:
            if self._loaded:
                logger.debug(
                    f"[DIAG-9] initialize: Already loaded, skipping. "
                    f"session_id={self.session_id}, entries={len(self.work_log)}"
                )
                return

            logger.debug(
                f"[DIAG-9] initialize: Starting load, "
                f"session_id={self.session_id}, has_storage={self._work_log_storage is not None}"
            )

            if self._work_log_storage:
                await self._load_from_storage()
            else:
                await self._load_from_filesystem()

            self._loaded = True

            logger.debug(
                f"[DIAG-9] initialize: Complete, "
                f"session_id={self.session_id}, total_entries={len(self.work_log)}"
            )

    async def _load_from_storage(self):
        if self._work_log_storage is None:
            logger.debug(
                f"[DIAG-8] _load_from_storage: No storage available, "
                f"session_id={self.session_id}"
            )
            return

        try:
            loaded_entries = await self._work_log_storage.get_work_log(self.session_id)
            self.work_log = list(loaded_entries)

            # 从 DB 加载后还原 user message 的 human_content
            # DB 中 user message 通过 tool="__user_message__" 标识，内容存在 result 列
            for entry in self.work_log:
                if getattr(entry, "tool", "") == self.USER_MESSAGE_TOOL:
                    if not getattr(entry, "human_content", None):
                        entry.human_content = getattr(entry, "result", "") or ""

            conv_ids = set(e.conv_id for e in self.work_log if e.conv_id)
            logger.info(
                f"[WorkLog] Loaded from storage: "
                f"session_id={self.session_id}, "
                f"total_entries={len(self.work_log)}, "
                f"conv_ids={conv_ids}, "
                f"user_messages={sum(1 for e in self.work_log if getattr(e, 'tool', '') == self.USER_MESSAGE_TOOL)}"
            )
        except Exception as e:
            logger.error(
                f"[DIAG-8-ERROR] Failed to load from storage: {e}", exc_info=True
            )

    async def _load_from_filesystem(self):
        if self.afs is None:
            return

        try:
            log_content = await self.afs.read_file(self.work_log_file_key)
            if log_content:
                log_data = json.loads(log_content)
                self.work_log = [WorkEntry.from_dict(entry) for entry in log_data]
                # 还原 user message 的 human_content
                for entry in self.work_log:
                    if getattr(entry, "tool", "") == self.USER_MESSAGE_TOOL:
                        if not getattr(entry, "human_content", None):
                            entry.human_content = getattr(entry, "result", "") or ""
                logger.info(f"📚 加载了 {len(self.work_log)} 条历史工作日志")
        except Exception as e:
            logger.error(f"加载历史日志失败: {e}")

    def _estimate_tokens(self, text: Optional[str]) -> int:
        if not text:
            return 0
        # P0-3 修复: 与 LayerManager/HistoryMessageBuilder 保持一致，最小返回 1
        return max(1, len(text) // self.chars_per_token)

    async def _save_large_result(self, tool_name: str, result: str) -> Optional[str]:
        if self.afs is None or len(result) < self.large_result_threshold_bytes:
            return None

        try:
            content_hash = hashlib.md5(result.encode("utf-8")).hexdigest()[:8]
            timestamp = int(time.time())
            file_key = f"{self.agent_id}_{tool_name}_{content_hash}_{timestamp}"

            await self.afs.save_file(
                file_key=file_key,
                data=result,
                file_type="tool_output",
                extension="txt",
                tool_name=tool_name,
            )

            logger.info(f"💾 大结果已归档到文件系统: {file_key}")
            return file_key

        except Exception as e:
            logger.error(f"保存大结果失败: {e}")
            return None

    # User message 在 work_log 中的标识符
    USER_MESSAGE_TOOL = "__user_message__"

    async def record_user_message(
        self,
        user_content: str,
        conv_id: Optional[str] = None,
    ) -> Optional[WorkEntry]:
        """记录 user 消息到 work_log。

        注意：此方法用于旧架构兼容。
        新架构 (data_version="v2") 下，用户消息应通过 GptsMemory.append_message 直接写入 GptsMessage。

        User message 作为普通 WorkEntry 存储：
        - tool = "__user_message__" 作为标识
        - result = user_content（复用 DB 现有列）
        - human_content = user_content（内存中快速访问）

        同一个 conv_id + 同内容 去重（防止重试时重复记录）。
        """
        if not user_content:
            return None

        async with self._lock:
            # 精确去重：同 conv_id + 同内容 才跳过
            # 兼容 DB 加载的 entry（human_content 可能为空，但 tool+result 可识别）
            for entry in self.work_log:
                is_same_user_msg = (
                    (getattr(entry, "human_content", None) == user_content)
                    or (
                        getattr(entry, "tool", "") == self.USER_MESSAGE_TOOL
                        and getattr(entry, "result", "") == user_content
                    )
                )
                if entry.conv_id == conv_id and is_same_user_msg:
                    logger.debug(
                        f"[DIAG-6-DUP] User message skipped (duplicate): "
                        f"conv_id={conv_id}, content_preview={user_content[:50]}"
                    )
                    return None

            tokens = self._estimate_tokens(user_content)
            # P2-4: user message 触发 round_index 递增
            round_key = conv_id or self.session_id
            self._round_counters[round_key] = self._round_counters.get(round_key, -1) + 1
            current_round = self._round_counters[round_key]
            entry = WorkEntry(
                timestamp=time.time(),
                tool=self.USER_MESSAGE_TOOL,
                result=user_content,         # DB 持久化用 result 列
                summary=user_content[:200],   # 摘要
                human_content=user_content,   # 内存中快速访问
                conv_id=conv_id,
                tokens=tokens,
                round_index=current_round,
            )
            self.work_log.append(entry)

            # 🔍 DIAG-6: 验证 user message 写入
            logger.debug(
                f"[DIAG-6] User message added to memory: "
                f"conv_id={conv_id}, total_entries={len(self.work_log)}, "
                f"has_storage={self._work_log_storage is not None}"
            )

            if self._layer_manager:
                try:
                    await self._layer_manager.add_entry(entry, trigger_migration=True)
                except Exception as e:
                    logger.error(
                        f"[WorkLog] LayerManager add_entry (user_message) failed: {e}"
                    )

            storage_conv_id = conv_id or self.session_id
            if self._work_log_storage:
                try:
                    await self._work_log_storage.append_work_entry(
                        conv_id=storage_conv_id,
                        entry=entry,
                        save_db=True,
                    )
                    logger.debug(
                        f"[DIAG-7] User message persisted to storage: "
                        f"conv_id={storage_conv_id}, storage_type={type(self._work_log_storage).__name__}"
                    )
                except Exception as e:
                    logger.error(
                        f"[DIAG-7-ERROR] Failed to persist user message: {e}",
                        exc_info=True,
                    )
            elif self.afs:
                log_data = [e.to_dict() for e in self.work_log]
                await self.afs.save_file(
                    file_key=self.work_log_file_key,
                    data=log_data,
                    file_type=FileType.WORK_LOG.value,
                    extension="json",
                )
            else:
                logger.debug(f"[DIAG-7-SKIP] No work_log_storage for user message")

            logger.info(
                f"[WorkLog] Recorded user message: conv_id={conv_id}, "
                f"tokens={tokens}, content_len={len(user_content)}"
            )
            return entry

    async def record_action(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]],
        action_output: ActionOutput,
        tags: Optional[List[str]] = None,
        tool_call_id: Optional[str] = None,
        assistant_content: Optional[str] = None,
        round_index: int = 0,
        conv_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> WorkEntry:
        result_content = action_output.content or ""
        tokens = self._estimate_tokens(result_content)

        archive_file_key = None
        if action_output.extra and isinstance(action_output.extra, dict):
            archive_file_key = action_output.extra.get("archive_file_key")

        if not archive_file_key and "完整输出已保存至文件:" in result_content:
            import re

            match = re.search(r"完整输出已保存至文件:\s*(\S+)", result_content)
            if match:
                archive_file_key = match.group(1).strip()
                logger.info(f"从截断提示中提取到 file_key: {archive_file_key}")

        summary = (
            result_content[:500] + "..."
            if len(result_content) > 500
            else result_content
        )

        result_to_save = None
        archive_file_key_from_action = archive_file_key

        if tool_name == "read_archive":
            if len(result_content) > self.read_archive_preview_length:
                result_to_save = (
                    result_content[: self.read_archive_preview_length]
                    + "\n... (内容已截断，如需更多请再次调用 read_archive)"
                )
                if len(result_content) > self.large_result_threshold_bytes:
                    saved_archive_key = await self._save_large_result(
                        tool_name, result_content
                    )
                    if saved_archive_key:
                        archive_file_key = saved_archive_key
            else:
                result_to_save = result_content

        elif tool_name in self.summary_only_tools:
            if len(result_content) > self.large_result_threshold_bytes:
                saved_archive_key = await self._save_large_result(
                    tool_name, result_content
                )
                if saved_archive_key:
                    archive_file_key = saved_archive_key
            result_to_save = None

        elif archive_file_key_from_action:
            result_to_save = result_content
        else:
            if len(result_content) > self.large_result_threshold_bytes:
                saved_archive_key = await self._save_large_result(
                    tool_name, result_content
                )
                if saved_archive_key:
                    archive_file_key = saved_archive_key
                    result_to_save = None
                else:
                    result_to_save = result_content[: self.large_result_threshold_bytes]
            else:
                result_to_save = result_content

        # P2-4: 使用自动跟踪的 round_index
        if round_index == 0:
            round_key = conv_id or self.session_id
            round_index = self._round_counters.get(round_key, 0)

        entry = WorkEntry(
            timestamp=time.time(),
            tool=tool_name,
            args=args,
            summary=summary[:500] if summary else None,
            result=result_to_save,
            full_result_archive=archive_file_key,
            success=action_output.is_exe_success,
            tags=tags or [],
            tokens=tokens,
            tool_call_id=tool_call_id,
            assistant_content=assistant_content,
            round_index=round_index,
            conv_id=conv_id,
            message_id=message_id,
        )

        async with self._lock:
            self.work_log.append(entry)

            # 🔍 DIAG-6: 验证数据写入内存
            logger.debug(
                f"[DIAG-6] WorkLog entry added to memory: tool={tool_name}, "
                f"conv_id={conv_id}, total_entries={len(self.work_log)}, "
                f"has_storage={self._work_log_storage is not None}"
            )

            # 增量分层：新 Entry 自动进入 Hot 层，触发迁移检查
            if self._layer_manager:
                try:
                    await self._layer_manager.add_entry(entry, trigger_migration=True)
                    logger.debug(
                        f"[WorkLog] Entry added to LayerManager: tool={tool_name}, "
                        f"tokens={tokens}"
                    )
                except Exception as e:
                    logger.error(f"[WorkLog] LayerManager add_entry failed: {e}")

            storage_conv_id = entry.conv_id or self.session_id
            if self._work_log_storage:
                try:
                    await self._work_log_storage.append_work_entry(
                        conv_id=storage_conv_id,
                        entry=entry,
                        save_db=True,
                    )
                    # 🔍 DIAG-7: 验证持久化成功
                    logger.debug(
                        f"[DIAG-7] WorkLog persisted to storage: tool={tool_name}, "
                        f"conv_id={storage_conv_id}, storage_type={type(self._work_log_storage).__name__}"
                    )
                except Exception as e:
                    logger.error(
                        f"[DIAG-7-ERROR] Failed to persist work_log: {e}", exc_info=True
                    )
            else:
                logger.warning(
                    f"[DIAG-7-SKIP] No work_log_storage available, using filesystem fallback"
                )
                if self.afs:
                    log_data = [e.to_dict() for e in self.work_log]
                    await self.afs.save_file(
                        file_key=self.work_log_file_key,
                        data=log_data,
                        file_type=FileType.WORK_LOG.value,
                        extension="json",
                    )

        return entry

    def get_entries(self, conv_id: Optional[str] = None) -> List[WorkEntry]:
        logger.info(
            f"[WorkLogManager] get_entries called: conv_id={conv_id}, "
            f"total_entries={len(self.work_log)}"
        )
        if conv_id:
            result = [
                entry
                for entry in self.work_log
                if entry.conv_id == conv_id or entry.conv_id is None
            ]
            logger.info(
                f"[WorkLogManager] Filtered entries for conv_id={conv_id}: "
                f"count={len(result)}, entry_conv_ids={[e.conv_id for e in self.work_log[:5]]}"
            )
            return result
        return self.work_log

    def get_recent_entries(
        self, count: int = 20, conv_id: Optional[str] = None
    ) -> List[WorkEntry]:
        entries = self.get_entries(conv_id)
        return entries[-count:] if len(entries) > count else entries

    def calculate_entries_tokens(self, entries: List[WorkEntry]) -> int:
        """计算 entries 的总 token 数。

        P1-1 修复: 只使用 entry.tokens（已在 record_action 时估算），
        不再重复计算 result 和 args 的 token。
        """
        total = 0
        for entry in entries:
            total += entry.tokens or 0
        return total

    def get_compression_cache(self, conv_id: str) -> WorkLogCompressionCache:
        if conv_id not in self.compression_cache:
            self.compression_cache[conv_id] = WorkLogCompressionCache()
        return self.compression_cache[conv_id]

    def update_compression_cache(
        self,
        conv_id: str,
        layer3_summary: str,
        layer3_end_index: int,
        layer2_start_index: int,
        total_entries: int,
        compressed_tokens: int,
    ):
        cache = self.get_compression_cache(conv_id)
        cache.layer3_summary = layer3_summary
        cache.layer3_end_index = layer3_end_index
        cache.layer2_start_index = layer2_start_index
        cache.last_total_entries = total_entries
        cache.last_compressed_tokens = compressed_tokens

        logger.info(
            f"[WorkLog] 更新压缩缓存: conv_id={conv_id}, "
            f"layer3_end={layer3_end_index}, layer2_start={layer2_start_index}, "
            f"total_entries={total_entries}"
        )

    def clear_compression_cache(self, conv_id: Optional[str] = None):
        if conv_id:
            self.compression_cache.pop(conv_id, None)
        else:
            self.compression_cache.clear()

    def get_layer_manager(self) -> Optional["LayerManager"]:
        """获取 LayerManager 实例"""
        return self._layer_manager

    async def get_stats(self) -> Dict[str, Any]:
        async with self._lock:
            total_tokens = sum(e.tokens for e in self.work_log)
            stats = {
                "total_entries": len(self.work_log),
                "current_tokens": total_tokens,
                "storage_mode": self.storage_mode,
                "cached_conversations": list(self.compression_cache.keys()),
            }

            # 添加 LayerManager 统计
            if self._layer_manager:
                stats["layer_manager"] = self._layer_manager.get_stats()

            return stats

    # P1-5 修复: work_log 最大条目数限制，防止长周期运行 OOM
    MAX_WORK_LOG_ENTRIES = 3000

    async def cleanup_archives(self, evictable_entries: Optional[List] = None):
        """P2-5: 清理已归档到文件系统的大结果文件。

        仅清理 evictable_entries 中有 full_result_archive 的条目。
        """
        if not self.afs or not evictable_entries:
            return

        cleaned = 0
        for entry in evictable_entries:
            archive_key = getattr(entry, "full_result_archive", None)
            if archive_key:
                try:
                    await self.afs.delete_file(archive_key)
                    cleaned += 1
                except Exception as e:
                    logger.debug(f"[WorkLog] Archive cleanup failed for {archive_key}: {e}")

        if cleaned > 0:
            logger.info(f"[WorkLog] Cleaned {cleaned} archive files")

    async def get_context_for_prompt(
        self,
        max_entries: int = 50,
        include_summaries: bool = True,
    ) -> str:
        """获取用于 prompt 的工作日志上下文。

        Args:
            max_entries: 最大条目数
            include_summaries: 是否包含压缩摘要

        Returns:
            格式化的上下文文本
        """
        async with self._lock:
            if not self._loaded:
                await self.initialize()

            if not self.work_log:
                return "\n暂无工作日志记录。"

            lines = ["## 工作日志", ""]

            # 添加压缩缓存中的摘要
            if include_summaries and self.compression_cache:
                for conv_id, cache in self.compression_cache.items():
                    if cache.layer3_summary:
                        lines.append("### 历史摘要")
                        lines.append(cache.layer3_summary)
                        lines.append("")

            # 添加活跃日志
            if self.work_log:
                lines.append("### 最近的工作")
                recent_entries = self.work_log[-max_entries:]
                for entry in recent_entries:
                    if getattr(entry, "status", WorkLogStatus.ACTIVE.value) == WorkLogStatus.ACTIVE.value:
                        lines.append(format_entry_for_prompt(entry))
                lines.append("")

            return "\n".join(lines)

    def trim_work_log(self, evictable_message_ids: Optional[set] = None):
        """裁剪 work_log 列表，移除已被 Cold/Warm 层处理的旧条目。

        优先移除 evictable_message_ids 指定的条目；
        若超过 MAX_WORK_LOG_ENTRIES 仍需裁剪，丢弃最老的条目。
        """
        if evictable_message_ids:
            self.work_log = [
                e for e in self.work_log
                if getattr(e, "message_id", None) not in evictable_message_ids
            ]

        if len(self.work_log) > self.MAX_WORK_LOG_ENTRIES:
            overflow = len(self.work_log) - self.MAX_WORK_LOG_ENTRIES
            self.work_log = self.work_log[overflow:]
            logger.info(
                f"[WorkLog] Trimmed {overflow} oldest entries, "
                f"remaining={len(self.work_log)}"
            )

    async def clear(self):
        async with self._lock:
            self.work_log = []
            self.compression_cache.clear()
            self._loaded = True


async def create_work_log_manager(
    agent_id: str,
    session_id: str,
    agent_file_system: Optional[AgentFileSystem] = None,
    work_log_storage: Optional[WorkLogStorage] = None,
    on_compression_callback: Optional[Any] = None,
    context_window_tokens: Optional[int] = None,
    compression_threshold_ratio: float = 0.7,
    **kwargs,
) -> WorkLogManager:
    manager = WorkLogManager(
        agent_id=agent_id,
        session_id=session_id,
        agent_file_system=agent_file_system,
        work_log_storage=work_log_storage,
        context_window=context_window_tokens,
    )
    await manager.initialize()
    return manager


__all__ = [
    "WorkLogManager",
    "WorkEntry",
    "WorkLogSummary",
    "WorkLogStatus",
    "WorkLogCompressionCache",
    "create_work_log_manager",
]
