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
        """检查并压缩工作日志（支持自适应触发）"""
        current_tokens = self._calculate_total_tokens(self.work_log)

        # 自适应触发检查
        self._round_counter += 1
        should_check = self._round_counter % self.config.adaptive_check_interval == 0

        # 检查增长率
        if should_check and self._last_token_count > 0:
            growth_rate = (
                (current_tokens - self._last_token_count) / self._last_token_count
                if self._last_token_count > 0
                else 0
            )

            if growth_rate > self.config.adaptive_growth_threshold:
                logger.info(
                    f"🔄 检测到快速增长率 ({growth_rate:.2%})，提前触发压缩检查"
                )

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

        non_tool_actions = {"Blank", "ask_user", "terminate"}

        hot_entries, warm_entries, cold_entries, layer_tokens = (
            self._categorize_entries_by_tokens(
                filtered_entries,
                budgets["hot"],
                budgets["warm"],
                budgets["cold"],
            )
        )

        cold_messages = self._build_cold_layer_messages(cold_entries)
        messages.extend(cold_messages)

        warm_messages = self._build_warm_layer_messages(warm_entries)
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
    ) -> List[Dict[str, Any]]:
        from derisk.core import ModelMessageRoleType

        if not entries:
            return []

        messages: List[Dict[str, Any]] = []

        tool_names = list(
            set(e.tool for e in entries if e.tool not in {"Blank", "terminate"})
        )
        tools_str = ", ".join(tool_names[:10])

        cold_summary = (
            f"[更早的工具调用摘要]\n"
            f"执行了 {len(entries)} 次工具调用\n"
            f"涉及工具: {tools_str}\n"
        )

        if len(cold_summary) > self.compression_config.cold_summary_max_length:
            cold_summary = (
                cold_summary[: self.compression_config.cold_summary_max_length] + "..."
            )

        messages.append(
            {
                "role": ModelMessageRoleType.SYSTEM,
                "content": cold_summary,
            }
        )

        self._compression_logs.append(
            CompressionLog(
                action="compress_llm",
                layer="cold",
                target=f"{len(entries)} entries",
                original_length=sum(len(e.result or "") for e in entries),
                result_length=len(cold_summary),
                trigger_condition="cumulative_tokens > hot_budget + warm_budget",
                compression_ratio=len(cold_summary)
                / max(1, sum(len(e.result or "") for e in entries)),
            )
        )

        return messages

    def _build_warm_layer_messages(
        self,
        entries: List[WorkEntry],
    ) -> List[Dict[str, Any]]:
        from derisk.core import ModelMessageRoleType

        if not entries:
            return []

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

        return messages

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
