"""
WorkLog 管理器 - 通用 ReAct Agent 的历史记录管理

核心特性：
1. 支持通过 WorkLogStorage 接口统一集成到 Memory 体系
2. 兼容旧版 AgentFileSystem 直接存储模式
3. 支持历史记录压缩，当超过 LLM 上下文窗口时自动压缩整理
4. 提供结构化的工作日志记录，便于追踪和调试
5. 使用统一配置 (UnifiedCompactionConfig)，与 Pipeline 保持一致

四层压缩架构：
- Hot Layer (50%): 完整保留最新工具调用
- Warm Layer (25%): 适度压缩，tool_calls完整，结果压缩到500字符
- Cold Layer (10%): LLM汇总摘要
- Archive Layer (>10KB): 文件存储

重构说明：
- 新增 work_log_storage 参数，优先使用 WorkLogStorage 接口
- 保留 agent_file_system 参数向后兼容
- 如果同时提供两者，优先使用 work_log_storage
- 使用 UnifiedCompactionConfig 统一配置，确保与 Pipeline 行为一致
"""

import asyncio
import dataclasses
import json
import logging
import time
import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple

from derisk.agent import ActionOutput
from ...core.file_system.agent_file_system import AgentFileSystem
from ...core.memory.gpts.file_base import (
    WorkLogStorage,
    WorkLogStatus,
    WorkEntry,
    WorkLogSummary,
    FileType,
)
from ...core.memory.compaction_pipeline import UnifiedCompactionConfig

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class CompressionConfig:
    """
    四层压缩配置

    Token 预算分配：
    - Hot Layer: 50% (完整保留)
    - Warm Layer: 25% (适度压缩)
    - Cold Layer: 10% (LLM摘要)
    - Remaining: 15% (System Prompt + 当前增量)
    """

    hot_ratio: float = 0.50
    warm_ratio: float = 0.25
    cold_ratio: float = 0.10

    hot_conversation_count: int = 3
    warm_conversation_count: int = 5

    hot_tool_result_keep_full_threshold: int = 10000
    warm_tool_result_max_length: int = 500
    warm_summary_max_length: int = 300
    cold_summary_max_length: int = 300
    archive_threshold_bytes: int = 10 * 1024

    llm_summary_temperature: float = 0.3
    chars_per_token: int = 4

    preserve_tools_patterns: Dict[str, List[str]] = dataclasses.field(
        default_factory=lambda: {"view": ["skill.md"]}
    )

    # Warm 层智能剪枝配置
    warm_enable_llm_pruning: bool = True
    warm_prune_error_after_turns: int = 4
    warm_prune_duplicate_tools: bool = True
    warm_prune_superseded_writes: bool = True
    warm_preserve_tools: List[str] = dataclasses.field(
        default_factory=lambda: ["view", "read", "ask_user"]
    )
    warm_write_tools: List[str] = dataclasses.field(
        default_factory=lambda: ["edit", "write", "create_file", "edit_file"]
    )
    warm_read_tools: List[str] = dataclasses.field(
        default_factory=lambda: ["read", "view", "cat"]
    )

    def calculate_budgets(self, context_window: int) -> Dict[str, int]:
        return {
            "hot": int(context_window * self.hot_ratio),
            "warm": int(context_window * self.warm_ratio),
            "cold": int(context_window * self.cold_ratio),
            "remaining": int(
                context_window
                * (1 - self.hot_ratio - self.warm_ratio - self.cold_ratio)
            ),
            "total": context_window,
        }

    @classmethod
    def default(cls) -> "CompressionConfig":
        return cls()

    @classmethod
    def for_small_context(cls, context_window: int = 32000) -> "CompressionConfig":
        return cls(
            hot_ratio=0.40,
            warm_ratio=0.20,
            cold_ratio=0.10,
            hot_tool_result_keep_full_threshold=5000,
            warm_tool_result_max_length=300,
        )

    @classmethod
    def for_large_context(cls, context_window: int = 128000) -> "CompressionConfig":
        return cls()


@dataclasses.dataclass
class CompressionLog:
    action: str
    layer: str
    target: str
    original_length: int
    result_length: int
    trigger_condition: str
    compression_ratio: float


@dataclasses.dataclass
class ColdSegmentSummary:
    """对话分段摘要 - 包含 user + assistant 消息对

    一个对话可以有多个 Cold 段摘要（分段压缩），每个段包含：
    - 用户问题
    - AI 回复摘要
    - 工具调用摘要
    """

    segment_id: str = ""
    conv_id: str = ""
    user_query: Optional[str] = None
    assistant_response: Optional[str] = None
    tool_summary: str = ""
    key_tools: List[str] = dataclasses.field(default_factory=list)
    timestamp: float = 0.0
    tokens: int = 0
    start_index: int = 0
    end_index: int = 0

    def to_message(self) -> Dict[str, Any]:
        """转换为 LLM Message 格式"""
        from derisk.core import ModelMessageRoleType

        content_parts = []

        if self.user_query:
            content_parts.append(f"用户问题: {self.user_query[:200]}")

        if self.tool_summary:
            content_parts.append(self.tool_summary)

        if self.assistant_response:
            content_parts.append(f"AI回复: {self.assistant_response[:200]}...")

        if self.key_tools:
            content_parts.append(f"关键工具: {', '.join(self.key_tools[:5])}")

        content = "\n".join(content_parts)
        return {
            "role": ModelMessageRoleType.SYSTEM,
            "content": f"[历史对话摘要 - {self.segment_id}]\n{content}",
            "is_history_summary": True,
            "segment_id": self.segment_id,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "conv_id": self.conv_id,
            "user_query": self.user_query,
            "assistant_response": self.assistant_response,
            "tool_summary": self.tool_summary,
            "key_tools": self.key_tools,
            "timestamp": self.timestamp,
            "tokens": self.tokens,
            "start_index": self.start_index,
            "end_index": self.end_index,
        }


@dataclasses.dataclass
class WarmCacheEntry:
    """Warm 层单条压缩缓存"""

    tool_call_id: str = ""
    tool_name: str = ""
    compressed_content: str = ""
    timestamp: float = 0.0
    tokens: int = 0


@dataclasses.dataclass
class WorkLogCompressionCache:
    """对话内压缩缓存 - 支持分段压缩和增量更新

    改进点：
    1. Cold 层支持分段摘要列表（layer3_summaries）
    2. Warm 层支持增量缓存（warm_cache_entries + warm_entries_hash）
    3. 只在新增条目超过阈值时重新压缩
    """

    layer3_summaries: List[ColdSegmentSummary] = dataclasses.field(default_factory=list)
    layer3_end_index: int = 0
    layer2_start_index: int = 0
    last_total_entries: int = 0
    last_compressed_tokens: int = 0

    warm_compressed_messages: Optional[str] = None
    warm_cache_entries: List[WarmCacheEntry] = dataclasses.field(default_factory=list)
    warm_entries_hash: Optional[str] = None
    warm_end_index: int = 0

    def needs_recompression(
        self, total_entries: int, new_entries_threshold: int = 20
    ) -> bool:
        """判断是否需要重新压缩"""
        return total_entries - self.last_total_entries >= new_entries_threshold

    def needs_warm_recompression(
        self, entries_hash: str, new_entries_threshold: int = 10
    ) -> bool:
        """判断 Warm 层是否需要重新压缩"""
        if not self.warm_compressed_messages:
            return True
        if self.warm_entries_hash != entries_hash:
            return True
        return False

    def get_cached_cold_messages(self) -> List[Dict[str, Any]]:
        """获取缓存的 Cold 层消息"""
        if not self.layer3_summaries:
            return []
        return [summary.to_message() for summary in self.layer3_summaries]

    def get_cached_warm_messages(self) -> Optional[List[Dict[str, Any]]]:
        """获取缓存的 Warm 层消息"""
        if not self.warm_compressed_messages:
            return None
        try:
            return json.loads(self.warm_compressed_messages)
        except Exception:
            return None

    def add_cold_segment(self, summary: ColdSegmentSummary):
        """添加新的 Cold 段摘要（增量）"""
        self.layer3_summaries.append(summary)

    def clear_cold_summaries(self):
        """清空 Cold 段摘要"""
        self.layer3_summaries.clear()


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
        if entry.tool == "read_file":
            lines.append(f"  读取内容预览:")
        result_lines = entry.result.split("\n")[:10]
        preview = "\n".join(result_lines)
        if len(preview) > max_length:
            preview = preview[:max_length] + "... (已截断)"
        if len(entry.result.split("\n")) > 10:
            preview += "\n  ... (共 {} 行)".format(len(entry.result.split("\n")))
        lines.append(f"  {preview}")
    elif entry.full_result_archive:
        lines.append(f"  完整结果已归档: {entry.full_result_archive}")
        lines.append(
            f'  💡 使用 read_file(file_key="{entry.full_result_archive}") 读取完整内容'
        )

    return "\n".join(lines)


class WorkLogManager:
    """
    工作日志管理器

    职责：
    1. 记录工具调用和工作日志
    2. 支持通过 WorkLogStorage 接口统一集成到 Memory 体系
    3. 兼容旧版 AgentFileSystem 直接存储模式
    4. 历史记录压缩管理（四层压缩架构）
    5. 生成 prompt 上下文
    6. 生成 Message List（原生 Function Call 模式）

    四层压缩架构：
    - Hot Layer (50%): 完整保留最新工具调用
    - Warm Layer (25%): 适度压缩，tool_calls完整，结果压缩到500字符
    - Cold Layer (10%): LLM汇总摘要
    - Archive Layer (>10KB): 文件存储
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        agent_file_system: Optional[AgentFileSystem] = None,
        work_log_storage: Optional[WorkLogStorage] = None,
        config: Optional[UnifiedCompactionConfig] = None,
        # 向后兼容参数
        context_window_tokens: Optional[int] = None,
        compression_threshold_ratio: Optional[float] = None,
        max_summary_entries: Optional[int] = None,
        on_compression_callback: Optional[Any] = None,
        compression_config: Optional[CompressionConfig] = None,
        system_event_manager: Optional[Any] = None,
    ):
        """
        初始化工作日志管理器

        Args:
            agent_id: Agent ID
            session_id: Session ID
            agent_file_system: AgentFileSystem 实例（向后兼容）
            work_log_storage: WorkLogStorage 实例（推荐，集成到 Memory）
            config: UnifiedCompactionConfig 实例（推荐，统一配置）
            context_window_tokens: 向后兼容参数，优先使用 config
            compression_threshold_ratio: 向后兼容参数，优先使用 config
            max_summary_entries: 向后兼容参数
            on_compression_callback: 压缩回调
            compression_config: 旧版压缩配置
            system_event_manager: 系统事件管理器
        """
        self.agent_id = agent_id
        self.session_id = session_id
        self.afs = agent_file_system
        self._work_log_storage = work_log_storage

        # 使用统一配置或创建默认配置
        if config is None:
            config = UnifiedCompactionConfig()

        # 向后兼容：允许覆盖配置参数
        if context_window_tokens is not None:
            config.context_window = context_window_tokens
        if compression_threshold_ratio is not None:
            config.compaction_threshold_ratio = compression_threshold_ratio

        self.config = config
        self.max_summary_entries = max_summary_entries or config.chapter_max_messages

        # 从统一配置中获取参数
        self.context_window_tokens = config.context_window
        self.compression_threshold = int(
            config.context_window * config.compaction_threshold_ratio
        )

        # 配置属性（优先使用 UnifiedCompactionConfig，回退到 CompressionConfig）
        self.large_result_threshold_bytes = config.large_result_threshold_bytes
        self.chars_per_token = config.chars_per_token
        self.read_file_preview_length = config.read_file_preview_length
        self.summary_only_tools = set(config.summary_only_tools)

        # 回调和管理器
        self._on_compression_callback = on_compression_callback
        self.compression_config = compression_config or CompressionConfig()
        self._system_event_manager = system_event_manager

        # 交互工具集合
        self.interactive_tools = {"ask_user", "send_message"}

        self.work_log: List[WorkEntry] = []
        self.summaries: List[WorkLogSummary] = []

        self.work_log_file_key = f"{agent_id}_{session_id}_work_log"
        self.summaries_file_key = f"{agent_id}_{session_id}_work_log_summaries"

        # 锁
        self._lock = asyncio.Lock()
        self._loaded = False

        # 自适应触发相关
        self._round_counter: int = 0
        self._last_token_count: int = 0

        # 监控指标
        self._metrics = {
            "truncation_count": 0,
            "compression_count": 0,
            "tokens_saved": 0,
            "archived_count": 0,
        }

        # 压缩日志和预算信息
        self._compression_logs: List[CompressionLog] = []
        self._last_budget_info: Optional[Dict[str, Any]] = None

        # 对话内压缩缓存：conv_id -> WorkLogCompressionCache
        self.compression_cache: Dict[str, WorkLogCompressionCache] = {}

        # 对话级别元数据：conv_id -> {"user_query": str, "final_answer": str, "timestamp": float}
        # 用于 Cold 层分段摘要生成
        self.conversation_metadata: Dict[str, Dict[str, Any]] = {}

        # 记录存储模式
        if work_log_storage:
            logger.info(f"WorkLogManager 初始化: 使用 WorkLogStorage 模式")
        elif agent_file_system:
            logger.info(f"WorkLogManager 初始化: 使用 AgentFileSystem 模式（兼容）")
        else:
            logger.info(f"WorkLogManager 初始化: 仅内存模式")

    @property
    def storage_mode(self) -> str:
        """获取当前存储模式"""
        if self._work_log_storage:
            return "work_log_storage"
        elif self.afs:
            return "agent_file_system"
        else:
            return "memory_only"

    async def initialize(self):
        """初始化，加载历史日志"""
        async with self._lock:
            if self._loaded:
                return

            # 优先从 WorkLogStorage 加载
            if self._work_log_storage:
                await self._load_from_storage()
            else:
                await self._load_from_filesystem()

            self._loaded = True

    async def _load_from_storage(self):
        """从 WorkLogStorage 加载历史日志"""
        if self._work_log_storage is None:
            return

        try:
            self.work_log = list(
                await self._work_log_storage.get_work_log(self.session_id)
            )
            self.summaries = list(
                await self._work_log_storage.get_work_log_summaries(self.session_id)
            )
            logger.info(
                f"📚 从 WorkLogStorage 加载了 {len(self.work_log)} 条日志, "
                f"{len(self.summaries)} 个摘要"
            )
        except Exception as e:
            logger.error(f"从 WorkLogStorage 加载失败: {e}")

    async def _load_from_filesystem(self):
        """从文件系统加载历史日志"""
        if self.afs is None:
            return

        try:
            # 加载工作日志
            log_content = await self.afs.read_file(self.work_log_file_key)
            if log_content:
                log_data = json.loads(log_content)
                self.work_log = [WorkEntry.from_dict(entry) for entry in log_data]
                logger.info(f"📚 加载了 {len(self.work_log)} 条历史工作日志")

            # 加载摘要
            summary_content = await self.afs.read_file(self.summaries_file_key)
            if summary_content:
                summary_data = json.loads(summary_content)
                self.summaries = [WorkLogSummary.from_dict(s) for s in summary_data]
                logger.info(f"📚 加载了 {len(self.summaries)} 个历史摘要")

        except Exception as e:
            logger.error(f"加载历史日志失败: {e}")

    async def _save_to_storage(self):
        """保存到 WorkLogStorage"""
        if self._work_log_storage is None:
            return

        try:
            # WorkLogStorage 会自动处理缓存和持久化
            # 这里只需要同步最新的数据
            pass
        except Exception as e:
            logger.error(f"保存到 WorkLogStorage 失败: {e}")

    async def _save_to_filesystem(self):
        """保存到文件系统"""
        if self.afs is None:
            return

        try:
            # 保存工作日志
            log_data = [entry.to_dict() for entry in self.work_log]
            await self.afs.save_file(
                file_key=self.work_log_file_key,
                data=log_data,
                file_type=FileType.WORK_LOG.value,
                extension="json",
            )

            # 保存摘要
            summary_data = [s.to_dict() for s in self.summaries]
            await self.afs.save_file(
                file_key=self.summaries_file_key,
                data=summary_data,
                file_type=FileType.WORK_LOG_SUMMARY.value,
                extension="json",
            )

            logger.debug(f"💾 保存工作日志到文件系统")

        except Exception as e:
            logger.error(f"保存工作日志失败: {e}")

    def _estimate_tokens(self, text: Optional[str]) -> int:
        """估算文本的 token 数量"""
        if not text:
            return 0
        return len(text) // self.chars_per_token

    def _extract_protected_content(
        self, text: str, max_blocks: Optional[int] = None
    ) -> Dict[str, List[str]]:
        """
        提取受保护的内容块（代码块、思维链、文件路径）

        Args:
            text: 文本内容
            max_blocks: 最大保护块数，默认使用配置

        Returns:
            分类的受保护内容字典
        """
        if max_blocks is None:
            max_blocks = self.config.max_protected_blocks

        protected: Dict[str, List[str]] = {
            "code": [],
            "thinking": [],
            "file_path": [],
        }

        if self.config.code_block_protection:
            code_pattern = r"```[\s\S]*?```"
            code_blocks = re.findall(code_pattern, text)
            protected["code"] = code_blocks[:max_blocks]

        if self.config.thinking_chain_protection:
            thinking_pattern = (
                r"<(?:thinking|scratch_pad|reasoning)>[\s\S]*?"
                r"</(?:thinking|scratch_pad|reasoning)>"
            )
            thinking_blocks = re.findall(thinking_pattern, text, re.IGNORECASE)
            protected["thinking"] = thinking_blocks[:max_blocks]

        if self.config.file_path_protection:
            file_pattern = r'["\']?(?:/[\w\-./]+|(?:\.\.?/)?[\w\-./]+\.[\w]+)["\']?'
            file_paths = list(set(re.findall(file_pattern, text)))
            protected["file_path"] = [
                p for p in file_paths if len(p) > 3 and not p.startswith("http")
            ][:max_blocks]

        return protected

    def _format_protected_content_for_summary(
        self, protected: Dict[str, List[str]]
    ) -> str:
        """格式化受保护内容用于摘要"""
        parts = []

        if protected.get("code"):
            parts.append("\n=== Protected Code Blocks ===")
            for i, code in enumerate(protected["code"][:5], 1):
                parts.append(f"\n--- Code Block {i} ---")
                parts.append(code[:500])

        if protected.get("thinking"):
            parts.append("\n=== Key Reasoning ===")
            for thinking in protected["thinking"][:2]:
                parts.append(thinking[:300])

        if protected.get("file_path"):
            parts.append("\n=== Referenced Files ===")
            for path in list(set(protected["file_path"]))[:10]:
                parts.append(f"- {path}")

        return "\n".join(parts) if parts else ""

    async def _save_large_result(self, tool_name: str, result: str) -> Optional[str]:
        """保存大结果到文件系统

        Args:
            tool_name: 工具名称
            result: 结果内容

        Returns:
            文件 key
        """
        if self.afs is None or len(result) < self.large_result_threshold_bytes:
            return None

        try:
            # 生成唯一文件 key
            content_hash = hashlib.md5(result.encode("utf-8")).hexdigest()[:8]
            timestamp = int(time.time())
            file_key = f"{self.agent_id}_{tool_name}_{content_hash}_{timestamp}"

            # 保存到文件系统
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
    ) -> WorkEntry:
        """
        记录一个工具执行

        Args:
            tool_name: 工具名称
            args: 工具参数
            action_output: ActionOutput 结果
            tool_call_id: 工具调用 ID（原生 Function Call 模式）
            assistant_content: 触发工具调用的 AI 消息内容
            round_index: 当前轮次索引
            conv_id: 对话 ID（用于隔离不同对话的工具调用记录）

        Returns:
            WorkEntry: 创建的工作日志条目
        """
        result_content = action_output.content or ""
        tokens = self._estimate_tokens(result_content)

        # 从 action_output.extra 中提取归档文件 key
        archive_file_key = None
        if action_output.extra and isinstance(action_output.extra, dict):
            archive_file_key = action_output.extra.get("archive_file_key")

        # 检查 content 中是否包含截断提示（作为备份检测）
        if not archive_file_key and "完整输出已保存至文件:" in result_content:
            import re

            match = re.search(r"完整输出已保存至文件:\s*(\S+)", result_content)
            if match:
                archive_file_key = match.group(1).strip()
                logger.info(f"从截断提示中提取到 file_key: {archive_file_key}")

        # 创建摘要，保持简短
        summary = (
            result_content[:500] + "..."
            if len(result_content) > 500
            else result_content
        )

        # 决定是否保存完整结果：
        # 分三种情况处理：
        # 1. read_file 工具：保存较长预览（让 LLM 知道读了什么），但不保存完整内容
        # 2. grep/search/find 等工具：只保存摘要（结果通常是列表，太大）
        # 3. 普通工具：正常处理（有归档用归档，无归档存结果，大结果自动归档）

        result_to_save = None
        archive_file_key_from_action = (
            archive_file_key  # 保存 action_output 中的归档 key
        )

        truncated = False  # 标记是否截断

        if tool_name == "read_file":
            # read_file 特殊处理：保存较长预览，完整内容归档
            if len(result_content) > self.read_file_preview_length:
                result_to_save = (
                    result_content[: self.read_file_preview_length]
                    + "\n... (内容已截断，如需更多请再次调用 read_file)"
                )
                # 如果结果很大，也归档一份
                if len(result_content) > self.large_result_threshold_bytes:
                    saved_archive_key = await self._save_large_result(
                        tool_name, result_content
                    )
                    if saved_archive_key:
                        archive_file_key = saved_archive_key
                        truncated = True
            else:
                result_to_save = result_content

        elif tool_name in self.summary_only_tools:
            # grep/search/find 等：只保存摘要，大结果自动归档
            if len(result_content) > self.large_result_threshold_bytes:
                saved_archive_key = await self._save_large_result(
                    tool_name, result_content
                )
                if saved_archive_key:
                    archive_file_key = saved_archive_key
                    truncated = True
            result_to_save = None  # 不保存结果，只用 summary

        elif archive_file_key_from_action:
            # 已有归档文件，不保存完整结果
            result_to_save = None
            truncated = True
        else:
            # 普通工具，没有归档文件
            if len(result_content) > self.large_result_threshold_bytes:
                # 结果太大且没有归档，尝试创建归档
                saved_archive_key = await self._save_large_result(
                    tool_name, result_content
                )
                if saved_archive_key:
                    archive_file_key = saved_archive_key
                    result_to_save = None
                    truncated = True
                else:
                    # 归档失败，保存截断的结果
                    result_to_save = result_content[: self.large_result_threshold_bytes]
                    truncated = True
            else:
                # 结果不大，直接保存
                result_to_save = result_content

        # 更新监控指标
        if truncated:
            self._metrics["truncation_count"] += 1

        # 创建工作日志条目
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
        )

        # 添加到工作日志
        async with self._lock:
            self.work_log.append(entry)

            # 检查是否需要压缩
            await self._check_and_compress()

            # 保存到存储
            # 使用 entry.conv_id 而非 self.session_id，确保按对话隔离存储
            storage_conv_id = entry.conv_id or self.session_id
            if self._work_log_storage:
                await self._work_log_storage.append_work_entry(
                    conv_id=storage_conv_id,
                    entry=entry,
                    save_db=True,
                )
            else:
                await self._save_to_filesystem()

        return entry

    def _calculate_total_tokens(self, entries: List[WorkEntry]) -> int:
        """计算条目列表的总 token 数"""
        return sum(entry.tokens for entry in entries)

    async def _generate_summary(self, entries: List[WorkEntry]) -> str:
        """
        生成工作日志摘要

        Args:
            entries: 要摘要的条目列表

        Returns:
            摘要文本
        """
        if not entries:
            return ""

        # 统计工具调用
        tool_stats: Dict[str, int] = {}
        for entry in entries:
            tool_stats[entry.tool] = tool_stats.get(entry.tool, 0) + 1

        # 统计成功/失败
        success_count = sum(1 for e in entries if e.success)
        fail_count = len(entries) - success_count

        # 提取关键工具
        key_tools = sorted(tool_stats.keys(), key=lambda x: -tool_stats[x])[:5]

        # 生成摘要
        lines = [
            f"## 工作日志摘要",
            f"",
            f"时间范围: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entries[0].timestamp))} - "
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entries[-1].timestamp))}",
            f"总操作数: {len(entries)}",
            f"成功: {success_count}, 失败: {fail_count}",
            f"",
            f"### 工具调用统计",
        ]

        for tool in key_tools:
            lines.append(f"- {tool}: {tool_stats[tool]} 次")

        lines.append("")

        # 添加最近的几个重要操作
        recent_important = [
            e for e in entries if not any(tag in ["info", "debug"] for tag in e.tags)
        ][-5:]
        if recent_important:
            lines.append("### 最近的重要操作")
            for entry in recent_important:
                lines.append(f"- {format_entry_for_prompt(entry, max_length=200)}")
            lines.append("")

        return "\n".join(lines)

    async def _check_and_compress(self):
        """检查并压缩工作日志（基于使用率触发）

        改进：
        - 移除 growth 触发（初始阶段会有误导）
        - 改为基于使用率触发
        - 使用率低于阈值不触发压缩
        """
        current_tokens = self._calculate_total_tokens(self.work_log)

        # 自适应触发检查
        self._round_counter += 1
        should_check = self._round_counter % self.config.adaptive_check_interval == 0

        # 计算使用率
        usage_ratio = current_tokens / self.config.context_window

        # 使用率低于阈值，空间足够，不触发压缩
        if should_check and usage_ratio < self.config.prune_min_usage_to_trigger:
            logger.debug(
                f"工作日志使用率较低 ({usage_ratio:.1%})，空间充足，跳过压缩检查"
            )
            self._last_token_count = current_tokens
            return

        # 高使用率日志
        if should_check and usage_ratio >= self.config.prune_trigger_high_usage:
            logger.info(f"🔥 工作日志高使用率 ({usage_ratio:.1%})，立即触发压缩检查")

        self._last_token_count = current_tokens

        # 标准阈值检查
        if current_tokens <= self.compression_threshold:
            return

        logger.info(
            f"🔄 工作日志超限: {current_tokens} tokens > {self.compression_threshold}, "
            f"开始压缩..."
        )

        # 选择要压缩的条目（保留最新的 N 条）
        if len(self.work_log) <= self.max_summary_entries:
            return

        entries_to_compress = self.work_log[: -self.max_summary_entries]
        entries_to_keep = self.work_log[-self.max_summary_entries :]

        # 提取受保护内容
        all_content = "\n\n".join(
            e.result or e.summary or "" for e in entries_to_compress
        )
        protected = self._extract_protected_content(all_content)
        protected_text = self._format_protected_content_for_summary(protected)

        # 生成摘要
        summary_content = await self._generate_summary(entries_to_compress)

        if protected_text:
            summary_content += "\n" + protected_text

        # 提取关键工具
        key_tools = list(set(e.tool for e in entries_to_compress))

        # 创建摘要对象
        summary = WorkLogSummary(
            compressed_entries_count=len(entries_to_compress),
            time_range=(
                entries_to_compress[0].timestamp,
                entries_to_compress[-1].timestamp,
            ),
            summary_content=summary_content,
            key_tools=key_tools,
        )

        # 标记被压缩的条目
        for entry in entries_to_compress:
            entry.status = WorkLogStatus.COMPRESSED

        # 更新工作日志
        self.work_log = entries_to_keep
        self.summaries.append(summary)

        # 更新监控指标
        tokens_saved = current_tokens - self._calculate_total_tokens(self.work_log)
        self._metrics["compression_count"] += 1
        self._metrics["tokens_saved"] += tokens_saved
        self._metrics["archived_count"] += len(entries_to_compress)

        logger.info(
            f"✅ 压缩完成: {len(entries_to_compress)} 条 -> 1 个摘要, "
            f"保留 {len(entries_to_keep)} 条活跃日志, 节省 {tokens_saved} tokens"
        )

        # 调用压缩完成回调（通知 Agent 注入 history_tools）
        if self._on_compression_callback:
            try:
                await self._on_compression_callback()
                logger.info("✅ 已触发压缩回调，通知 Agent 注入历史工具")
            except Exception as e:
                logger.warning(f"压缩回调执行失败: {e}")

    async def get_context_for_prompt(
        self,
        max_entries: int = 50,
        include_summaries: bool = True,
    ) -> str:
        """
        获取用于 prompt 的工作日志上下文

        Args:
            max_entries: 最大条目数
            include_summaries: 是否包含摘要

        Returns:
            格式化的上下文文本
        """
        async with self._lock:
            if not self._loaded:
                await self.initialize()

            if not self.work_log and not self.summaries:
                return "\n暂无工作日志记录。"

            lines = ["## 工作日志", ""]

            # 添加历史摘要
            if include_summaries and self.summaries:
                lines.append("### 历史摘要")
                for i, summary in enumerate(self.summaries, 1):
                    lines.append(f"#### 摘要 {i}")
                    lines.append(summary.summary_content)
                    lines.append("")

            # 添加活跃日志
            if self.work_log:
                lines.append("### 最近的工作")
                # 只显示最近的 N 条
                recent_entries = self.work_log[-max_entries:]
                for entry in recent_entries:
                    if entry.status == WorkLogStatus.ACTIVE.value:
                        lines.append(format_entry_for_prompt(entry))
                lines.append("")

            return "\n".join(lines)

    async def get_full_work_log(self) -> Dict[str, Any]:
        """获取完整的工作日志（包括已压缩的条目）"""
        async with self._lock:
            return {
                "work_log": [entry.to_dict() for entry in self.work_log],
                "summaries": [s.to_dict() for s in self.summaries],
            }

    async def get_stats(self) -> Dict[str, Any]:
        """获取工作日志统计信息（包含监控指标）"""
        async with self._lock:
            total_entries = len(self.work_log) + sum(
                s.compressed_entries_count for s in self.summaries
            )
            current_tokens = self._calculate_total_tokens(self.work_log)

            return {
                # 基础统计
                "total_entries": total_entries,
                "active_entries": len(self.work_log),
                "compressed_summaries": len(self.summaries),
                "current_tokens": current_tokens,
                "compression_threshold": self.compression_threshold,
                "usage_ratio": current_tokens / self.compression_threshold
                if self.compression_threshold > 0
                else 0,
                # 监控指标
                "metrics": {
                    "truncation_count": self._metrics["truncation_count"],
                    "compression_count": self._metrics["compression_count"],
                    "tokens_saved": self._metrics["tokens_saved"],
                    "archived_count": self._metrics["archived_count"],
                    "avg_tokens_per_compression": (
                        self._metrics["tokens_saved"]
                        / self._metrics["compression_count"]
                        if self._metrics["compression_count"] > 0
                        else 0
                    ),
                },
                # 配置信息
                "config": {
                    "context_window": self.config.context_window,
                    "compaction_threshold_ratio": self.config.compaction_threshold_ratio,
                    "prune_protect_tokens": self.config.prune_protect_tokens,
                    "adaptive_check_interval": self.config.adaptive_check_interval,
                },
            }

    def build_tool_messages(
        self,
        max_tokens: Optional[int] = None,
        keep_recent_count: int = 20,
        apply_prune: bool = True,
        conv_id: Optional[str] = None,
        context_window: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        from derisk.core import ModelMessageRoleType

        context_window = context_window or self.context_window_tokens
        budgets = self.compression_config.calculate_budgets(context_window)
        self._last_budget_info = {
            "context_window": context_window,
            **budgets,
        }

        self._emit_budget_event("TOKEN_BUDGET_ALLOCATED", budgets)

        messages: List[Dict[str, Any]] = []

        if self.summaries:
            summary_lines = ["[历史工作日志摘要]\n"]
            for i, summary in enumerate(self.summaries, 1):
                summary_lines.append(f"## 摘要 {i}")
                summary_lines.append(summary.summary_content[:500])
                summary_lines.append(f"关键工具: {', '.join(summary.key_tools[:5])}")
                summary_lines.append("")

            summary_content = "\n".join(summary_lines)
            messages.append(
                {
                    "role": ModelMessageRoleType.SYSTEM,
                    "content": summary_content,
                }
            )

        if not self.work_log:
            return messages

        if conv_id:
            filtered_entries = [
                entry
                for entry in self.work_log
                if entry.conv_id == conv_id or entry.conv_id is None
            ]
        else:
            filtered_entries = self.work_log

        # 检查缓存
        cache = None
        if conv_id and apply_prune:
            cache = self.get_compression_cache(conv_id)
            total_entries = len(filtered_entries)

            # 如果缓存有效且不需要重新压缩
            if cache.warm_compressed_messages and not cache.needs_recompression(
                total_entries, new_entries_threshold=10
            ):
                logger.debug(
                    f"[WorkLogManager] 使用缓存的压缩结果: conv_id={conv_id[:8] if conv_id else 'N/A'}"
                )

                # 从缓存恢复 Cold 层分段摘要
                if cache.layer3_summaries:
                    cached_cold_messages = cache.get_cached_cold_messages()
                    messages.extend(cached_cold_messages)

                # 从缓存恢复 warm messages
                cached_warm_messages = cache.get_cached_warm_messages()
                if cached_warm_messages:
                    messages.extend(cached_warm_messages)

                # Hot layer 始终重新构建（最新的工具调用）
                hot_entries, _, _, _ = self._categorize_entries_by_tokens(
                    filtered_entries,
                    budgets["hot"],
                    0,
                    0,
                )
                non_tool_actions = {"Blank", "ask_user", "terminate"}
                hot_messages = self._build_hot_layer_messages(
                    hot_entries, non_tool_actions
                )
                messages.extend(hot_messages)

                return messages

        non_tool_actions = {"Blank", "ask_user", "terminate"}

        hot_entries, warm_entries, cold_entries, layer_tokens = (
            self._categorize_entries_by_tokens(
                filtered_entries,
                budgets["hot"],
                budgets["warm"],
                budgets["cold"],
            )
        )

        # 构建 Cold 层消息（使用分段摘要）
        cold_messages = self._build_cold_layer_messages(
            cold_entries, cache=cache, cold_budget=budgets["cold"]
        )
        messages.extend(cold_messages)

        # 计算当前对话轮次（用于错误清理）
        current_turn = len(hot_entries) + len(warm_entries)

        # 构建 warm messages 并应用智能剪枝
        warm_messages = self._build_warm_layer_messages(
            warm_entries,
            warm_budget=budgets["warm"],
            current_turn=current_turn,
            cache=cache,
        )
        messages.extend(warm_messages)

        hot_messages = self._build_hot_layer_messages(hot_entries, non_tool_actions)
        messages.extend(hot_messages)

        total_tokens = sum(
            self._estimate_tokens(m.get("content", "")) for m in messages
        )

        logger.info(
            f"[WorkLogManager] Built tool_messages: {len(messages)} messages, "
            f"~{total_tokens} tokens, "
            f"hot={len(hot_entries)}, warm={len(warm_entries)}, cold={len(cold_entries)}"
        )

        # 更新缓存（Cold 和 Warm 层在各自的方法中已更新）
        if conv_id and cache:
            cache.last_total_entries = len(filtered_entries)
            cache.last_compressed_tokens = total_tokens

        self._emit_layer_events(layer_tokens, budgets)
        self._emit_summary_event(total_tokens, context_window, budgets)

        return messages

    def _categorize_entries_by_tokens(
        self,
        entries: List[WorkEntry],
        hot_budget: int,
        warm_budget: int,
        cold_budget: int,
    ) -> Tuple[List[WorkEntry], List[WorkEntry], List[WorkEntry], Dict[str, int]]:
        """
        从最新往最旧遍历，累计 tokens 判断归属层级

        Returns:
            (hot_entries, warm_entries, cold_entries, layer_tokens)
        """
        hot_entries: List[WorkEntry] = []
        warm_entries: List[WorkEntry] = []
        cold_entries: List[WorkEntry] = []

        cumulative_tokens = 0
        hot_threshold = hot_budget
        warm_threshold = hot_budget + warm_budget

        hot_tokens = 0
        warm_tokens = 0
        cold_tokens = 0

        for entry in reversed(entries):
            if entry.status != WorkLogStatus.ACTIVE.value:
                continue
            if entry.tool in self.interactive_tools:
                continue

            entry_tokens = entry.tokens or self._estimate_entry_tokens(entry)
            cumulative_tokens += entry_tokens

            if cumulative_tokens <= hot_threshold:
                hot_entries.append(entry)
                hot_tokens += entry_tokens
            elif cumulative_tokens <= warm_threshold:
                warm_entries.append(entry)
                warm_tokens += entry_tokens
            else:
                cold_entries.append(entry)
                cold_tokens += entry_tokens

        hot_entries.reverse()
        warm_entries.reverse()
        cold_entries.reverse()

        if cold_tokens > cold_budget and cold_entries:
            kept_count = 0
            kept_tokens = 0
            for entry in reversed(cold_entries):
                if kept_tokens + (entry.tokens or 0) > cold_budget:
                    break
                kept_tokens += entry.tokens or 0
                kept_count += 1

            evicted_count = len(cold_entries) - kept_count
            if evicted_count > 0:
                logger.info(
                    f"[WorkLogManager] Cold budget exceeded, evicting {evicted_count} oldest entries"
                )
                cold_entries = cold_entries[-kept_count:] if kept_count > 0 else []
                cold_tokens = kept_tokens

        return (
            hot_entries,
            warm_entries,
            cold_entries,
            {
                "hot": hot_tokens,
                "warm": warm_tokens,
                "cold": cold_tokens,
            },
        )

    def _estimate_entry_tokens(self, entry: WorkEntry) -> int:
        total_chars = 0
        if entry.result:
            total_chars += len(entry.result)
        if entry.summary:
            total_chars += len(entry.summary)
        if entry.assistant_content:
            total_chars += len(entry.assistant_content)
        if entry.args:
            total_chars += len(json.dumps(entry.args))
        return max(1, total_chars // self.chars_per_token)

    def _build_cold_layer_messages(
        self,
        entries: List[WorkEntry],
        cache: Optional[WorkLogCompressionCache] = None,
        cold_budget: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        构建 Cold Layer 消息：分段摘要，包含 user + assistant 消息对

        改进点：
        1. 一个对话可以有多个 Cold 段摘要（分段压缩）
        2. 每个 Cold 段包含：user_query + assistant_response + tool_summary
        3. 使用缓存避免重复压缩

        Args:
            entries: Cold 层的 WorkEntry 列表
            cache: 压缩缓存（如果提供，优先使用缓存）
            cold_budget: Cold 层 token 预算

        Returns:
            Message List 格式的摘要消息列表
        """
        from derisk.core import ModelMessageRoleType

        if not entries:
            return []

        # 检查缓存：如果缓存的分段摘要覆盖了所有 entries，直接使用缓存
        if cache and cache.layer3_summaries:
            cached_messages = cache.get_cached_cold_messages()
            # 验证缓存是否覆盖当前 entries
            if cache.layer3_end_index >= len(entries):
                logger.debug(
                    f"[WorkLogManager] Cold 层使用缓存: {len(cache.layer3_summaries)} 个分段摘要"
                )
                return cached_messages

        messages: List[Dict[str, Any]] = []

        # 分段压缩：按 conv_id 和 token 数分段
        segment_summaries: List[ColdSegmentSummary] = []

        # 按 conv_id 分组
        entries_by_conv: Dict[str, List[WorkEntry]] = {}
        for entry in entries:
            conv_id = entry.conv_id or "default"
            if conv_id not in entries_by_conv:
                entries_by_conv[conv_id] = []
            entries_by_conv[conv_id].append(entry)

        # 对每个对话生成摘要
        segment_id_counter = 0
        max_segment_tokens = max(500, cold_budget // 3)  # 每段最大 token

        for conv_id, conv_entries in entries_by_conv.items():
            # 获取对话元数据（user_query, final_answer）
            conv_meta = self.conversation_metadata.get(conv_id, {})
            user_query = conv_meta.get("user_query", "")
            final_answer = conv_meta.get("final_answer", "")

            # 按 token 数分段（避免单个摘要太大）
            current_segment_tokens = 0
            current_segment_entries: List[WorkEntry] = []

            for entry in conv_entries:
                entry_tokens = entry.tokens or self._estimate_entry_tokens(entry)

                # 如果当前段超过阈值，生成一个摘要
                if (
                    current_segment_tokens + entry_tokens > max_segment_tokens
                    and current_segment_entries
                ):
                    segment_summary = self._create_cold_segment(
                        current_segment_entries,
                        conv_id,
                        user_query if len(segment_summaries) == 0 else None,
                        final_answer
                        if current_segment_entries == conv_entries[-1:]
                        else None,
                        segment_id_counter,
                    )
                    segment_summaries.append(segment_summary)
                    segment_id_counter += 1

                    current_segment_entries = [entry]
                    current_segment_tokens = entry_tokens
                else:
                    current_segment_entries.append(entry)
                    current_segment_tokens += entry_tokens

            # 处理最后一段（包含 final_answer）
            if current_segment_entries:
                segment_summary = self._create_cold_segment(
                    current_segment_entries,
                    conv_id,
                    user_query if len(segment_summaries) == 0 else None,
                    final_answer,
                    segment_id_counter,
                )
                segment_summaries.append(segment_summary)

        # 转换为消息列表
        for summary in segment_summaries:
            messages.append(summary.to_message())

        # 记录压缩日志
        total_original_chars = sum(
            len(e.result or "") + len(e.summary or "") for e in entries
        )
        total_compressed_chars = sum(len(m.get("content", "")) for m in messages)

        self._compression_logs.append(
            CompressionLog(
                action="compress_segmented",
                layer="cold",
                target=f"{len(entries)} entries -> {len(segment_summaries)} segments",
                original_length=total_original_chars,
                result_length=total_compressed_chars,
                trigger_condition="cumulative_tokens > hot_budget + warm_budget",
                compression_ratio=total_compressed_chars / max(1, total_original_chars),
            )
        )

        # 更新缓存
        if cache:
            cache.clear_cold_summaries()
            for summary in segment_summaries:
                cache.add_cold_segment(summary)
            cache.layer3_end_index = len(entries)

        logger.info(
            f"[WorkLogManager] Cold 层分段压缩: {len(entries)} 条目 -> {len(segment_summaries)} 段摘要"
        )

        return messages

    def _create_cold_segment(
        self,
        entries: List[WorkEntry],
        conv_id: str,
        user_query: Optional[str] = None,
        final_answer: Optional[str] = None,
        segment_id: int = 0,
    ) -> ColdSegmentSummary:
        """
        创建单个 Cold 段摘要

        Args:
            entries: 该段包含的 WorkEntry
            conv_id: 对话 ID
            user_query: 用户问题（第一个段才有）
            final_answer: 最终回复（最后一段才有）
            segment_id: 段 ID

        Returns:
            ColdSegmentSummary 对象
        """
        # 提取关键工具
        tool_names = list(
            set(
                e.tool
                for e in entries
                if e.tool not in {"Blank", "terminate", "ask_user"}
            )
        )

        # 提取 assistant_content（如果有）
        assistant_contents = []
        for e in entries:
            if e.assistant_content:
                assistant_contents.append(e.assistant_content[:100])

        # 生成工具调用摘要
        tool_summary_lines = []
        tool_summary_lines.append(f"执行了 {len(entries)} 次工具调用")
        if tool_names:
            tool_summary_lines.append(f"涉及工具: {', '.join(tool_names[:5])}")

        # 提取关键结果（取前3个重要工具的结果摘要）
        important_results = []
        for e in entries[:3]:
            if e.result and len(e.result) > 50:
                important_results.append(f"{e.tool}: {e.result[:100]}...")

        if important_results:
            tool_summary_lines.append("关键结果:")
            tool_summary_lines.extend(important_results[:3])

        tool_summary = "\n".join(tool_summary_lines)

        # 截断最终回复
        assistant_response = None
        if final_answer:
            assistant_response = final_answer[:200]
        elif assistant_contents:
            assistant_response = (
                "..." + assistant_contents[-1] if assistant_contents else None
            )

        # 计算 tokens
        content = ""
        if user_query:
            content += user_query[:200]
        content += tool_summary
        if assistant_response:
            content += assistant_response
        tokens = max(1, len(content) // self.chars_per_token)

        return ColdSegmentSummary(
            segment_id=f"{conv_id}_seg_{segment_id}",
            conv_id=conv_id,
            user_query=user_query[:200] if user_query else None,
            assistant_response=assistant_response,
            tool_summary=tool_summary,
            key_tools=tool_names[:5],
            timestamp=entries[-1].timestamp if entries else time.time(),
            tokens=tokens,
            start_index=0,
            end_index=len(entries),
        )

    def _build_warm_layer_messages(
        self,
        entries: List[WorkEntry],
        warm_budget: int = 0,
        current_turn: int = 0,
        cache: Optional[WorkLogCompressionCache] = None,
    ) -> List[Dict[str, Any]]:
        """
        构建 Warm Layer 消息：适度压缩 + 智能剪枝

        改进点：
        1. 支持 cache 参数，增量缓存
        2. 只在条目变化时重新压缩
        3. 使用 warm_entries_hash 判断是否需要重新压缩

        Args:
            entries: Warm 层的 WorkEntry 列表
            warm_budget: Warm 层 token 预算
            current_turn: 当前对话轮次
            cache: 压缩缓存

        Returns:
            Message List 格式的消息列表
        """
        from derisk.core import ModelMessageRoleType

        if not entries:
            return []

        # 计算条目 hash（用于判断是否需要重新压缩）
        entries_hash = self._compute_entries_hash(entries)

        # 检查缓存是否有效
        if cache and cache.warm_compressed_messages:
            if not cache.needs_warm_recompression(
                entries_hash, new_entries_threshold=5
            ):
                cached_messages = cache.get_cached_warm_messages()
                if cached_messages:
                    logger.debug(
                        f"[WorkLogManager] Warm 层使用缓存: {len(cached_messages)} 条消息"
                    )
                    return cached_messages

        messages: List[Dict[str, Any]] = []
        max_result_length = self.compression_config.warm_tool_result_max_length

        for entry in entries:
            if entry.tool in {"Blank", "ask_user", "terminate"}:
                continue

            if entry.tool_call_id:
                messages.append(
                    {
                        "role": ModelMessageRoleType.AI,
                        "content": entry.assistant_content or "",
                        "tool_calls": [
                            {
                                "id": entry.tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": entry.tool,
                                    "arguments": json.dumps(entry.args or {}),
                                },
                            }
                        ],
                    }
                )

                result = entry.result or "(工具执行完成)"
                if len(result) > max_result_length:
                    result = (
                        result[:max_result_length]
                        + f"\n... [压缩，原始 {len(entry.result or '')} 字符]"
                    )
                    if entry.full_result_archive:
                        result += f"\n归档: {entry.full_result_archive}"

                messages.append(
                    {
                        "role": ModelMessageRoleType.TOOL,
                        "tool_call_id": entry.tool_call_id,
                        "content": result,
                    }
                )

        # 应用智能剪枝
        messages = self._smart_prune_messages(messages, warm_budget, current_turn)

        # 更新缓存
        if cache:
            cache.warm_compressed_messages = json.dumps(messages) if messages else None
            cache.warm_entries_hash = entries_hash
            cache.warm_end_index = len(entries)
            logger.debug(
                f"[WorkLogManager] Warm 层更新缓存: {len(messages)} 条消息, hash={entries_hash[:8]}"
            )

        return messages

    def _compute_entries_hash(self, entries: List[WorkEntry]) -> str:
        """计算条目列表的 hash（用于判断是否需要重新压缩）"""
        if not entries:
            return ""

        # 只取关键信息计算 hash
        hash_parts = []
        for e in entries[-10:]:  # 只看最后10条（新增部分）
            hash_parts.append(f"{e.tool}:{e.tool_call_id}:{len(e.result or '')}")

        hash_str = "|".join(hash_parts)
        return hashlib.md5(hash_str.encode()).hexdigest()

    def _smart_prune_messages(
        self,
        messages: List[Dict[str, Any]],
        token_budget: int = 0,
        current_turn: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        智能剪枝：整合去重、错误清理、写入覆盖

        执行顺序：
        1. 去重 (_prune_duplicate_tools)
        2. 写入覆盖清理 (_prune_superseded_writes)
        3. 错误清理 (_prune_error_tools)
        4. Token 预算控制
        """
        pruned = self._prune_duplicate_tools(messages)
        pruned = self._prune_superseded_writes(pruned)
        pruned = self._prune_error_tools(pruned, current_turn)

        # Token 预算控制
        if token_budget > 0:
            current_tokens = self._estimate_messages_tokens(pruned)
            if current_tokens > token_budget:
                final_messages = []
                for msg in reversed(pruned):
                    if current_tokens <= token_budget:
                        final_messages.insert(0, msg)
                    else:
                        current_tokens -= self._estimate_messages_tokens([msg])
                pruned = final_messages

        return pruned

    def _prune_duplicate_tools(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """去重：相同工具+相同参数的调用只保留最新的"""
        if not self.compression_config.warm_prune_duplicate_tools:
            return messages

        seen_signatures: Dict[str, str] = {}
        tool_call_id_to_keep: set = set()

        for i, msg in enumerate(messages):
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    func_name = tc.get("function", {}).get("name", "")
                    args = tc.get("function", {}).get("arguments", "")

                    if func_name in self.compression_config.warm_preserve_tools:
                        tool_call_id_to_keep.add(tc.get("id"))
                        continue

                    signature = f"{func_name}:{args}"
                    tool_call_id_to_keep.add(tc.get("id"))
                    if signature in seen_signatures:
                        old_id = seen_signatures[signature]
                        if old_id in tool_call_id_to_keep:
                            tool_call_id_to_keep.remove(old_id)
                    seen_signatures[signature] = tc.get("id")

        pruned_messages: List[Dict[str, Any]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                tc_id = tool_calls[0].get("id")
                if tc_id in tool_call_id_to_keep:
                    pruned_messages.append(msg)
                    if i + 1 < len(messages) and messages[i + 1].get("role") == "tool":
                        pruned_messages.append(messages[i + 1])
                        i += 1
            elif msg.get("role") != "tool":
                pruned_messages.append(msg)

            i += 1

        return pruned_messages

    def _prune_error_tools(
        self,
        messages: List[Dict[str, Any]],
        current_turn: int = 0,
    ) -> List[Dict[str, Any]]:
        """清理错误工具调用：N 轮后移除失败的调用"""
        threshold = self.compression_config.warm_prune_error_after_turns
        pruned_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                is_error = (
                    "error" in content.lower()
                    or "failed" in content.lower()
                    or "exception" in content.lower()
                )

                if is_error and current_turn > threshold:
                    pruned_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": msg.get("tool_call_id"),
                            "content": "[错误工具调用已清理]",
                        }
                    )
                else:
                    pruned_messages.append(msg)
            else:
                pruned_messages.append(msg)

        return pruned_messages

    def _prune_superseded_writes(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """清理被覆盖的写入操作"""
        if not self.compression_config.warm_prune_superseded_writes:
            return messages

        write_tools = set(self.compression_config.warm_write_tools)
        read_tools = set(self.compression_config.warm_read_tools)
        written_files: Dict[str, int] = {}

        for i, msg in enumerate(messages):
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                continue

            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")

                try:
                    args = (
                        json.loads(args_str) if isinstance(args_str, str) else args_str
                    )
                except Exception:
                    continue

                file_path = str(args.get("path", args.get("file_path", "")))

                if func_name in write_tools and file_path:
                    written_files[file_path] = i

                elif func_name in read_tools and file_path:
                    if file_path in written_files:
                        write_idx = written_files[file_path]
                        if 0 <= write_idx < len(messages):
                            write_msg = messages[write_idx]
                            tool_calls_write = write_msg.get("tool_calls", [])
                            if tool_calls_write:
                                for tc_write in tool_calls_write:
                                    args_write = tc_write.get("function", {}).get(
                                        "arguments", "{}"
                                    )
                                    try:
                                        args_dict = (
                                            json.loads(args_write)
                                            if isinstance(args_write, str)
                                            else args_write
                                        )
                                        new_args = dict(args_dict)
                                        if (
                                            "content" in new_args
                                            and len(str(new_args.get("content", "")))
                                            > 200
                                        ):
                                            new_args["content"] = (
                                                f"[写入内容已清理，后续已读取文件: {file_path}]"
                                            )
                                            tc_write["function"]["arguments"] = (
                                                json.dumps(new_args, ensure_ascii=False)
                                            )
                                    except Exception:
                                        pass
                        del written_files[file_path]

        return messages

    def _estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的 token 数"""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                total_chars += len(json.dumps(tool_calls, ensure_ascii=False))
        return max(1, total_chars // self.chars_per_token)

    def get_compression_cache(self, conv_id: str) -> WorkLogCompressionCache:
        """获取压缩缓存"""
        if conv_id not in self.compression_cache:
            self.compression_cache[conv_id] = WorkLogCompressionCache()
        return self.compression_cache[conv_id]

    def update_compression_cache(
        self,
        conv_id: str,
        layer3_end_index: int = 0,
        layer2_start_index: int = 0,
        total_entries: int = 0,
        compressed_tokens: int = 0,
        warm_compressed_messages: Optional[str] = None,
        warm_entries_hash: Optional[str] = None,
    ):
        """
        更新压缩缓存

        注意：Cold 层分段摘要现在在 _build_cold_layer_messages 中直接更新 cache.layer3_summaries
        """
        cache = self.get_compression_cache(conv_id)
        cache.layer3_end_index = layer3_end_index
        cache.layer2_start_index = layer2_start_index
        cache.last_total_entries = total_entries
        cache.last_compressed_tokens = compressed_tokens
        if warm_compressed_messages is not None:
            cache.warm_compressed_messages = warm_compressed_messages
        if warm_entries_hash is not None:
            cache.warm_entries_hash = warm_entries_hash

        logger.debug(
            f"[WorkLog] 更新压缩缓存: conv_id={conv_id}, "
            f"layer3_end={layer3_end_index}, layer2_start={layer2_start_index}, "
            f"total_entries={total_entries}, cold_segments={len(cache.layer3_summaries)}"
        )

    def record_conversation_metadata(
        self,
        conv_id: str,
        user_query: Optional[str] = None,
        final_answer: Optional[str] = None,
    ):
        """
        记录对话级别的元数据

        用于 Cold 层分段摘要生成，包含用户问题和最终回复

        Args:
            conv_id: 对话 ID
            user_query: 用户问题
            final_answer: Agent 最终回复

        Example:
            work_log_manager.record_conversation_metadata(
                conv_id="conv_123",
                user_query="分析这个项目的认证流程",
                final_answer="认证流程包含三个步骤..."
            )
        """
        if conv_id not in self.conversation_metadata:
            self.conversation_metadata[conv_id] = {
                "timestamp": time.time(),
            }

        if user_query is not None:
            self.conversation_metadata[conv_id]["user_query"] = user_query
        if final_answer is not None:
            self.conversation_metadata[conv_id]["final_answer"] = final_answer

        logger.debug(
            f"[WorkLog] 记录对话元数据: conv_id={conv_id}, "
            f"user_query={user_query[:50] if user_query else 'N/A'}..., "
            f"final_answer={final_answer[:50] if final_answer else 'N/A'}..."
        )

    def update_cold_segment_with_final_answer(
        self,
        conv_id: str,
        final_answer: str,
    ):
        """
        更新 Cold 层最后一个分段摘要的 final_answer

        在对话结束时调用，补充最终回复

        Args:
            conv_id: 对话 ID
            final_answer: 最终回复
        """
        cache = self.get_compression_cache(conv_id)

        # 找到该对话最后一个分段
        for summary in reversed(cache.layer3_summaries):
            if summary.conv_id == conv_id:
                summary.assistant_response = final_answer[:200]
                # 更新元数据
                self.record_conversation_metadata(conv_id, final_answer=final_answer)
                logger.debug(
                    f"[WorkLog] 更新 Cold 段最终回复: segment_id={summary.segment_id}"
                )
                break

    def clear_compression_cache(self, conv_id: Optional[str] = None):
        """清空压缩缓存"""
        if conv_id:
            self.compression_cache.pop(conv_id, None)
            self.conversation_metadata.pop(conv_id, None)
        else:
            self.compression_cache.clear()
            self.conversation_metadata.clear()

    def _build_hot_layer_messages(
        self,
        entries: List[WorkEntry],
        non_tool_actions: set,
    ) -> List[Dict[str, Any]]:
        from derisk.core import ModelMessageRoleType

        if not entries:
            return []

        messages: List[Dict[str, Any]] = []

        for entry in entries:
            if entry.tool in non_tool_actions:
                if entry.assistant_content or entry.result:
                    messages.append(
                        {
                            "role": ModelMessageRoleType.AI,
                            "content": entry.assistant_content or entry.result or "",
                        }
                    )
                continue

            if entry.tool_call_id:
                messages.append(
                    {
                        "role": ModelMessageRoleType.AI,
                        "content": entry.assistant_content or "",
                        "tool_calls": [
                            {
                                "id": entry.tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": entry.tool,
                                    "arguments": json.dumps(entry.args or {}),
                                },
                            }
                        ],
                    }
                )

                result = entry.result or "(工具执行完成，无输出内容)"
                if entry.full_result_archive:
                    result += f"\n\n完整结果归档: {entry.full_result_archive}"

                messages.append(
                    {
                        "role": ModelMessageRoleType.TOOL,
                        "tool_call_id": entry.tool_call_id,
                        "content": result,
                    }
                )

        return messages

    def get_compression_logs(self) -> List[CompressionLog]:
        return self._compression_logs.copy()

    def get_compression_summary(self) -> Dict[str, Any]:
        if not self._compression_logs:
            return {"total_operations": 0, "total_saved_chars": 0}

        total_saved = sum(
            log.original_length - log.result_length for log in self._compression_logs
        )
        avg_ratio = sum(log.compression_ratio for log in self._compression_logs) / len(
            self._compression_logs
        )

        return {
            "total_operations": len(self._compression_logs),
            "total_saved_chars": total_saved,
            "average_compression_ratio": avg_ratio,
            "by_layer": {
                layer: len([l for l in self._compression_logs if l.layer == layer])
                for layer in ["hot", "warm", "cold"]
            },
        }

    def get_last_budget_info(self) -> Optional[Dict[str, Any]]:
        return self._last_budget_info

    def set_system_event_manager(self, manager: Any) -> None:
        self._system_event_manager = manager

    def _emit_budget_event(
        self,
        event_type: str,
        budgets: Dict[str, int],
    ) -> None:
        if not self._system_event_manager:
            return

        try:
            from derisk.agent.core.memory.gpts.system_event import (
                SystemEventType,
                SystemEvent,
            )

            event_type_enum = getattr(SystemEventType, event_type, None)
            if not event_type_enum:
                return

            self._system_event_manager.add_event(
                event_type=event_type_enum,
                title="Token 预算分配",
                description=f"上下文窗口: {budgets.get('total', 0):,} tokens",
                metadata={
                    "hot_budget": budgets.get("hot", 0),
                    "warm_budget": budgets.get("warm", 0),
                    "cold_budget": budgets.get("cold", 0),
                    "remaining": budgets.get("remaining", 0),
                    "ratios": {
                        "hot": self.compression_config.hot_ratio,
                        "warm": self.compression_config.warm_ratio,
                        "cold": self.compression_config.cold_ratio,
                    },
                },
            )
        except Exception as e:
            logger.debug(f"[WorkLogManager] Failed to emit budget event: {e}")

    def _emit_layer_events(
        self,
        layer_tokens: Dict[str, int],
        budgets: Dict[str, int],
    ) -> None:
        if not self._system_event_manager:
            return

        try:
            from derisk.agent.core.memory.gpts.system_event import (
                SystemEventType,
            )

            for layer in ["hot", "warm", "cold"]:
                used = layer_tokens.get(layer, 0)
                budget = budgets.get(layer, 1)
                usage_ratio = used / budget if budget > 0 else 0

                self._system_event_manager.add_event(
                    event_type=SystemEventType.TOKEN_BUDGET_LAYER_USED,
                    title=f"{layer.upper()} Layer 使用",
                    description=f"使用: {used:,} / {budget:,} tokens ({usage_ratio:.1%})",
                    metadata={
                        "layer": layer,
                        "used_tokens": used,
                        "budget_tokens": budget,
                        "usage_ratio": usage_ratio,
                    },
                )
        except Exception as e:
            logger.debug(f"[WorkLogManager] Failed to emit layer events: {e}")

    def _emit_summary_event(
        self,
        total_used: int,
        context_window: int,
        budgets: Dict[str, int],
    ) -> None:
        if not self._system_event_manager:
            return

        try:
            from derisk.agent.core.memory.gpts.system_event import (
                SystemEventType,
            )

            remaining = context_window - total_used
            usage_ratio = total_used / context_window if context_window > 0 else 0

            self._system_event_manager.add_event(
                event_type=SystemEventType.TOKEN_BUDGET_SUMMARY,
                title="Token 预算汇总",
                description=f"总使用: {total_used:,} / {context_window:,} tokens ({usage_ratio:.1%}), 剩余: {remaining:,}",
                metadata={
                    "total_used": total_used,
                    "context_window": context_window,
                    "remaining": remaining,
                    "usage_ratio": usage_ratio,
                    "budgets": budgets,
                },
            )
        except Exception as e:
            logger.debug(f"[WorkLogManager] Failed to emit summary event: {e}")

    def get_tool_call_ids(self) -> List[str]:
        """获取所有 tool_call_id 列表"""
        return [entry.tool_call_id for entry in self.work_log if entry.tool_call_id]

    def get_entry_by_tool_call_id(self, tool_call_id: str) -> Optional[WorkEntry]:
        """通过 tool_call_id 查找条目"""
        for entry in reversed(self.work_log):
            if entry.tool_call_id == tool_call_id:
                return entry
        return None

    async def clear(self):
        """清空工作日志"""
        async with self._lock:
            self.work_log.clear()
            self.summaries.clear()
            if self._work_log_storage:
                await self._work_log_storage.clear_work_log(self.session_id)
            else:
                await self._save_to_filesystem()
            logger.info("工作日志已清空")


# 便捷函数
async def create_work_log_manager(
    agent_id: str,
    session_id: str,
    agent_file_system: Optional[AgentFileSystem] = None,
    work_log_storage: Optional[WorkLogStorage] = None,
    config: Optional[UnifiedCompactionConfig] = None,
    on_compression_callback: Optional[Any] = None,
    **kwargs,
) -> WorkLogManager:
    """
    创建并初始化工作日志管理器

    Args:
        agent_id: Agent ID
        session_id: Session ID
        agent_file_system: AgentFileSystem 实例（向后兼容）
        work_log_storage: WorkLogStorage 实例（推荐）
        config: UnifiedCompactionConfig 实例（推荐，统一配置）
        on_compression_callback: 压缩完成后的回调函数
        **kwargs: 传递给 WorkLogManager 的额外参数（向后兼容）
            - context_window_tokens: 上下文窗口大小
            - compression_threshold_ratio: 压缩阈值比例
            - max_summary_entries: 最大摘要条目数

    Returns:
        已初始化的 WorkLogManager 实例

    示例:
        # 推荐用法：使用统一配置
        from derisk.agent.core.memory.compaction_pipeline import UnifiedCompactionConfig

        config = UnifiedCompactionConfig(
            compaction_threshold_ratio=0.8,
            prune_protect_tokens=10000,
        )
        manager = await create_work_log_manager(
            agent_id="my_agent",
            session_id="session_123",
            work_log_storage=storage,
            config=config,
        )

        # 向后兼容用法
        manager = await create_work_log_manager(
            agent_id="my_agent",
            session_id="session_123",
            agent_file_system=afs,
            context_window_tokens=128000,
        )
    """
    manager = WorkLogManager(
        agent_id=agent_id,
        session_id=session_id,
        agent_file_system=agent_file_system,
        work_log_storage=work_log_storage,
        config=config,
        on_compression_callback=on_compression_callback,
        **kwargs,
    )
    await manager.initialize()
    return manager
