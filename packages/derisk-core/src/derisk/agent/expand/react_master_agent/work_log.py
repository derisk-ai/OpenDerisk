"""
WorkLog 管理器 - 通用 ReAct Agent 的历史记录管理

核心特性：
1. 支持通过 WorkLogStorage 接口统一集成到 Memory 体系
2. 兼容旧版 AgentFileSystem 直接存储模式
3. 支持历史记录压缩，当超过 LLM 上下文窗口时自动压缩整理
4. 提供结构化的工作日志记录，便于追踪和调试

重构说明：
- 新增 work_log_storage 参数，优先使用 WorkLogStorage 接口
- 保留 agent_file_system 参数向后兼容
- 如果同时提供两者，优先使用 work_log_storage
"""

import asyncio
import json
import logging
import time
import hashlib
from typing import List, Dict, Any, Optional

from derisk.agent import ActionOutput
from ...core.file_system.agent_file_system import AgentFileSystem
from ...core.memory.gpts.file_base import (
    WorkLogStorage,
    WorkLogStatus,
    WorkEntry,
    WorkLogSummary,
    FileType,
)

logger = logging.getLogger(__name__)


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
    4. 历史记录压缩管理
    5. 生成 prompt 上下文

    存储策略：
    - 优先使用 work_log_storage（推荐，集成到 Memory 体系）
    - 回退使用 agent_file_system（向后兼容）
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        agent_file_system: Optional[AgentFileSystem] = None,
        work_log_storage: Optional[WorkLogStorage] = None,
        context_window_tokens: int = 128000,
        compression_threshold_ratio: float = 0.7,
        max_summary_entries: int = 100,
    ):
        """
        初始化工作日志管理器

        Args:
            agent_id: Agent ID
            session_id: Session ID
            agent_file_system: AgentFileSystem 实例（向后兼容）
            work_log_storage: WorkLogStorage 实例（推荐，集成到 Memory）
            context_window_tokens: LLM 上下文窗口大小（token）
            compression_threshold_ratio: 触发压缩的阈值比例
            max_summary_entries: 单次最大摘要条目数
        """
        self.agent_id = agent_id
        self.session_id = session_id
        self.afs = agent_file_system
        self._work_log_storage = work_log_storage
        self.context_window_tokens = context_window_tokens
        self.compression_threshold = int(
            context_window_tokens * compression_threshold_ratio
        )
        self.max_summary_entries = max_summary_entries

        # 工作日志存储（本地缓存）
        self.work_log: List[WorkEntry] = []
        self.summaries: List[WorkLogSummary] = []

        # 文件系统中的 key（向后兼容模式使用）
        self.work_log_file_key = f"{agent_id}_{session_id}_work_log"
        self.summaries_file_key = f"{agent_id}_{session_id}_work_log_summaries"

        # 配置
        self.large_result_threshold_bytes = 10 * 1024  # 10KB
        self.chars_per_token = 4  # 估算 token 的字符比例

        # 特殊工具配置
        self.read_file_preview_length = 2000
        self.summary_only_tools = {"grep", "search", "find"}

        # 锁
        self._lock = asyncio.Lock()
        self._loaded = False

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
    ) -> WorkEntry:
        """
        记录一个工具执行

        Args:
            tool_name: 工具名称
            args: 工具参数
            action_output: ActionOutput 结果

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
            result_to_save = None  # 不保存结果，只用 summary

        elif archive_file_key_from_action:
            # 已有归档文件，不保存完整结果
            result_to_save = None
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
                else:
                    # 归档失败，保存截断的结果
                    result_to_save = result_content[: self.large_result_threshold_bytes]
            else:
                # 结果不大，直接保存
                result_to_save = result_content

        # 创建工作日志条目
        entry = WorkEntry(
            timestamp=time.time(),
            tool=tool_name,
            args=args,
            summary=summary[:500] if summary else None,
            result=result_to_save,  # 根据情况保存完整结果或 None
            full_result_archive=archive_file_key,  # 记录归档文件 key
            success=action_output.is_exe_success,
            tags=tags or [],
            tokens=tokens,
        )

        # 添加到工作日志
        async with self._lock:
            self.work_log.append(entry)

            # 检查是否需要压缩
            await self._check_and_compress()

            # 保存到存储
            if self._work_log_storage:
                await self._work_log_storage.append_work_entry(
                    conv_id=self.session_id,
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
        """检查并压缩工作日志"""
        current_tokens = self._calculate_total_tokens(self.work_log)

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

        # 生成摘要
        summary_content = await self._generate_summary(entries_to_compress)

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

        logger.info(
            f"✅ 压缩完成: {len(entries_to_compress)} 条 -> 1 个摘要, "
            f"保留 {len(entries_to_keep)} 条活跃日志"
        )

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
        """获取工作日志统计信息"""
        async with self._lock:
            total_entries = len(self.work_log) + sum(
                s.compressed_entries_count for s in self.summaries
            )
            current_tokens = self._calculate_total_tokens(self.work_log)

            return {
                "total_entries": total_entries,
                "active_entries": len(self.work_log),
                "compressed_summaries": len(self.summaries),
                "current_tokens": current_tokens,
                "compression_threshold": self.compression_threshold,
                "usage_ratio": current_tokens / self.compression_threshold
                if self.compression_threshold > 0
                else 0,
            }

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
    **kwargs,
) -> WorkLogManager:
    """
    创建并初始化工作日志管理器

    Args:
        agent_id: Agent ID
        session_id: Session ID
        agent_file_system: AgentFileSystem 实例（向后兼容）
        work_log_storage: WorkLogStorage 实例（推荐）
        **kwargs: 传递给 WorkLogManager 的额外参数

    Returns:
        已初始化的 WorkLogManager 实例
    """
    manager = WorkLogManager(
        agent_id=agent_id,
        session_id=session_id,
        agent_file_system=agent_file_system,
        work_log_storage=work_log_storage,
        **kwargs,
    )
    await manager.initialize()
    return manager
