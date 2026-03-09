"""上下文压缩监控模块

提供三层压缩机制的实时监控指标采集、日志记录和统计功能。

三层压缩架构:
    Layer 1 (Truncation): 即时截断大工具输出
    Layer 2 (Pruning): 周期性修剪历史消息
    Layer 3 (Compaction): 按需压缩归档会话

使用示例:
    from derisk.agent.core.memory.context_metrics import ContextMetricsCollector

    collector = ContextMetricsCollector(conv_id="xxx", session_id="yyy")

    # 记录截断操作
    collector.record_truncation(
        tool_name="read",
        original_bytes=50000,
        truncated_bytes=5000,
        file_key="tool_output_read_xxx"
    )

    # 获取当前指标
    metrics = collector.get_metrics()
    print(f"当前上下文使用率: {metrics.usage_ratio:.1%}")
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class CompressionLayer(Enum):
    """压缩层级枚举"""

    TRUNCATION = "truncation"  # Layer 1: 截断
    PRUNING = "pruning"  # Layer 2: 修剪
    COMPACTION = "compaction"  # Layer 3: 压缩归档


class LogLevel(Enum):
    """日志级别"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# =============================================================================
# 指标数据类
# =============================================================================


@dataclass
class TruncationMetrics:
    """Layer 1: 截断指标

    记录工具输出截断的统计信息。
    """

    # 累计统计
    total_count: int = 0  # 总截断次数
    total_bytes_truncated: int = 0  # 累计截断字节数
    total_bytes_original: int = 0  # 累计原始字节数
    total_lines_truncated: int = 0  # 累计截断行数
    total_files_archived: int = 0  # 累计归档文件数

    # 最近一次操作
    last_tool_name: str = ""  # 最近截断的工具名
    last_original_size: int = 0  # 最近原始大小
    last_truncated_size: int = 0  # 最近截断后大小
    last_file_key: Optional[str] = None  # 最近文件 key
    last_timestamp: float = 0.0  # 最近操作时间戳

    # 按工具统计
    tool_stats: Dict[str, Dict[str, int]] = field(
        default_factory=dict
    )  # 工具名 -> {count, bytes}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "total_bytes_truncated": self.total_bytes_truncated,
            "total_bytes_original": self.total_bytes_original,
            "total_lines_truncated": self.total_lines_truncated,
            "total_files_archived": self.total_files_archived,
            "last_tool_name": self.last_tool_name,
            "last_original_size": self.last_original_size,
            "last_truncated_size": self.last_truncated_size,
            "last_file_key": self.last_file_key,
            "last_timestamp": self.last_timestamp,
            "tool_stats": self.tool_stats,
        }


@dataclass
class PruningMetrics:
    """Layer 2: 修剪指标

    记录历史消息修剪的统计信息。
    """

    # 累计统计
    total_count: int = 0  # 总修剪次数
    total_messages_pruned: int = 0  # 累计修剪消息数
    total_tokens_saved: int = 0  # 累计节省 tokens

    # 最近一次操作
    last_messages_count: int = 0  # 最近修剪的消息数
    last_tokens_saved: int = 0  # 最近节省的 tokens
    last_trigger_reason: str = ""  # 触发原因
    last_usage_ratio: float = 0.0  # 操作时使用率
    last_timestamp: float = 0.0  # 最近操作时间戳

    # 使用率历史 (用于趋势分析)
    usage_history: List[Dict[str, Any]] = field(
        default_factory=list
    )  # [{timestamp, usage_ratio, tokens}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "total_messages_pruned": self.total_messages_pruned,
            "total_tokens_saved": self.total_tokens_saved,
            "last_messages_count": self.last_messages_count,
            "last_tokens_saved": self.last_tokens_saved,
            "last_trigger_reason": self.last_trigger_reason,
            "last_usage_ratio": self.last_usage_ratio,
            "last_timestamp": self.last_timestamp,
            "usage_history": self.usage_history[-20:],  # 只保留最近 20 条
        }


@dataclass
class CompactionMetrics:
    """Layer 3: 压缩归档指标

    记录会话压缩归档的统计信息。
    """

    # 累计统计
    total_count: int = 0  # 总压缩次数
    total_messages_archived: int = 0  # 累计归档消息数
    total_tokens_saved: int = 0  # 累计节省 tokens
    total_chapters_created: int = 0  # 累计创建章节数

    # 当前状态
    current_chapters: int = 0  # 当前章节数
    current_chapter_index: int = 0  # 当前章节索引

    # 最近一次操作
    last_messages_archived: int = 0  # 最近归档消息数
    last_tokens_saved: int = 0  # 最近节省 tokens
    last_chapter_index: int = 0  # 最近章节索引
    last_summary_length: int = 0  # 最近摘要长度
    last_timestamp: float = 0.0  # 最近操作时间戳

    # 章节统计
    chapter_stats: List[Dict[str, Any]] = field(
        default_factory=list
    )  # [{index, messages, tools, tokens}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "total_messages_archived": self.total_messages_archived,
            "total_tokens_saved": self.total_tokens_saved,
            "total_chapters_created": self.total_chapters_created,
            "current_chapters": self.current_chapters,
            "current_chapter_index": self.current_chapter_index,
            "last_messages_archived": self.last_messages_archived,
            "last_tokens_saved": self.last_tokens_saved,
            "last_chapter_index": self.last_chapter_index,
            "last_summary_length": self.last_summary_length,
            "last_timestamp": self.last_timestamp,
            "chapter_stats": self.chapter_stats[-10:],  # 只保留最近 10 个章节
        }


@dataclass
class ContextMetrics:
    """上下文压缩总指标

    汇总三层压缩的全部监控数据。
    """

    # 会话标识
    conv_id: str = ""
    session_id: str = ""

    # 当前上下文状态
    current_tokens: int = 0  # 当前 token 数
    context_window: int = 128000  # 上下文窗口大小
    usage_ratio: float = 0.0  # 使用率 (0.0 - 1.0)
    message_count: int = 0  # 当前消息数
    round_counter: int = 0  # 会话轮次

    # 配置信息
    config: Dict[str, Any] = field(default_factory=dict)  # 压缩配置快照

    # 各层指标
    truncation: TruncationMetrics = field(default_factory=TruncationMetrics)
    pruning: PruningMetrics = field(default_factory=PruningMetrics)
    compaction: CompactionMetrics = field(default_factory=CompactionMetrics)

    # 时间戳
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "current_tokens": self.current_tokens,
            "context_window": self.context_window,
            "usage_ratio": self.usage_ratio,
            "usage_percent": f"{self.usage_ratio * 100:.1f}%",
            "message_count": self.message_count,
            "round_counter": self.round_counter,
            "config": self.config,
            "truncation": self.truncation.to_dict(),
            "pruning": self.pruning.to_dict(),
            "compaction": self.compaction.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "duration_seconds": self.updated_at - self.created_at,
        }

    def to_summary(self) -> str:
        """生成摘要字符串，用于日志输出"""
        return (
            f"[Context Metrics] "
            f"Tokens: {self.current_tokens}/{self.context_window} ({self.usage_ratio:.1%}), "
            f"Messages: {self.message_count}, Rounds: {self.round_counter} | "
            f"L1(Truncate): {self.truncation.total_count}x, "
            f"L2(Prune): {self.pruning.total_count}x ({self.pruning.total_messages_pruned} msgs), "
            f"L3(Compact): {self.compaction.total_count}x ({self.compaction.total_chapters_created} chapters)"
        )


# =============================================================================
# 指标收集器
# =============================================================================


class ContextMetricsCollector:
    """上下文压缩指标收集器

    管理三层压缩的指标采集、存储、日志记录和实时推送。

    Attributes:
        conv_id: 会话ID
        session_id: 会话会话ID
        enable_logging: 是否启用日志
        push_callback: 推送回调函数 (用于推送到前端)

    使用方式:
        collector = ContextMetricsCollector(
            conv_id="conv_123",
            session_id="sess_456",
            context_window=128000
        )

        # 设置推送回调
        collector.set_push_callback(async_push_function)

        # 更新上下文状态
        collector.update_context_state(
            tokens=50000,
            message_count=30,
            round_counter=10
        )

        # 记录各层操作
        collector.record_truncation(...)
        collector.record_pruning(...)
        collector.record_compaction(...)

        # 获取指标
        metrics = collector.get_metrics()
    """

    def __init__(
        self,
        conv_id: str,
        session_id: str,
        context_window: int = 128000,
        config: Optional[Dict[str, Any]] = None,
        enable_logging: bool = True,
        push_callback: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
    ):
        self.conv_id = conv_id
        self.session_id = session_id
        self.enable_logging = enable_logging
        self._push_callback = push_callback

        self._metrics = ContextMetrics(
            conv_id=conv_id,
            session_id=session_id,
            context_window=context_window,
            config=config or {},
        )

        # 操作日志缓冲 (用于调试和审计)
        self._operation_log: List[Dict[str, Any]] = []
        self._max_log_entries = 100

        # 推送节流 (避免频繁推送)
        self._last_push_time: float = 0.0
        self._push_interval: float = 1.0  # 最小推送间隔 1 秒

    def set_push_callback(
        self, callback: Callable[[str, str, Dict[str, Any]], Any]
    ) -> None:
        """设置推送回调函数"""
        self._push_callback = callback

    async def _push_metrics(self, event_type: str = "context_metrics_update") -> None:
        """推送指标到前端"""
        import time as time_module

        current_time = time_module.time()

        # 节流检查
        if current_time - self._last_push_time < self._push_interval:
            return

        if not self._push_callback:
            return

        try:
            await self._push_callback(self.conv_id, event_type, self._metrics.to_dict())
            self._last_push_time = current_time
        except Exception as e:
            logger.warning(f"Failed to push metrics: {e}")

    # ==================== 上下文状态更新 ====================

    def update_context_state(
        self,
        tokens: int,
        message_count: int,
        round_counter: int,
    ) -> None:
        """更新当前上下文状态"""
        self._metrics.current_tokens = tokens
        self._metrics.message_count = message_count
        self._metrics.round_counter = round_counter
        self._metrics.usage_ratio = (
            tokens / self._metrics.context_window
            if self._metrics.context_window > 0
            else 0.0
        )
        self._metrics.updated_at = time.time()

        # 记录使用率历史 (用于趋势分析)
        self._metrics.pruning.usage_history.append(
            {
                "timestamp": time.time(),
                "usage_ratio": self._metrics.usage_ratio,
                "tokens": tokens,
                "message_count": message_count,
            }
        )

        self._log(
            LogLevel.DEBUG,
            CompressionLayer.TRUNCATION,
            f"上下文状态更新: {tokens} tokens ({self._metrics.usage_ratio:.1%}), {message_count} msgs",
        )

    # ==================== Layer 1: Truncation ====================

    def record_truncation(
        self,
        tool_name: str,
        original_bytes: int,
        truncated_bytes: int,
        original_lines: int = 0,
        truncated_lines: int = 0,
        file_key: Optional[str] = None,
    ) -> None:
        """记录截断操作"""
        metrics = self._metrics.truncation

        # 更新累计统计
        metrics.total_count += 1
        metrics.total_bytes_truncated += truncated_bytes
        metrics.total_bytes_original += original_bytes
        metrics.total_lines_truncated += (
            (original_lines - truncated_lines)
            if original_lines > truncated_lines
            else 0
        )
        if file_key:
            metrics.total_files_archived += 1

        # 更新最近一次操作
        metrics.last_tool_name = tool_name
        metrics.last_original_size = original_bytes
        metrics.last_truncated_size = truncated_bytes
        metrics.last_file_key = file_key
        metrics.last_timestamp = time.time()

        # 更新工具统计
        if tool_name not in metrics.tool_stats:
            metrics.tool_stats[tool_name] = {"count": 0, "bytes": 0}
        metrics.tool_stats[tool_name]["count"] += 1
        metrics.tool_stats[tool_name]["bytes"] += original_bytes - truncated_bytes

        self._metrics.updated_at = time.time()

        # 日志记录
        compression_ratio = (
            truncated_bytes / original_bytes if original_bytes > 0 else 0
        )
        self._log(
            LogLevel.INFO,
            CompressionLayer.TRUNCATION,
            f"[Layer 1 - Truncation] 工具 '{tool_name}' 输出截断: "
            f"{original_bytes}B -> {truncated_bytes}B (压缩率 {compression_ratio:.1%}), "
            f"file_key={file_key}",
        )

        # 记录操作日志
        self._add_operation_log(
            layer=CompressionLayer.TRUNCATION,
            action="truncate",
            details={
                "tool_name": tool_name,
                "original_bytes": original_bytes,
                "truncated_bytes": truncated_bytes,
                "file_key": file_key,
            },
        )

    # ==================== Layer 2: Pruning ====================

    def record_pruning(
        self,
        messages_pruned: int,
        tokens_saved: int,
        trigger_reason: str = "",
        usage_ratio: float = 0.0,
    ) -> None:
        """记录修剪操作"""
        metrics = self._metrics.pruning

        # 更新累计统计
        metrics.total_count += 1
        metrics.total_messages_pruned += messages_pruned
        metrics.total_tokens_saved += tokens_saved

        # 更新最近一次操作
        metrics.last_messages_count = messages_pruned
        metrics.last_tokens_saved = tokens_saved
        metrics.last_trigger_reason = trigger_reason
        metrics.last_usage_ratio = usage_ratio
        metrics.last_timestamp = time.time()

        self._metrics.updated_at = time.time()

        # 日志记录
        self._log(
            LogLevel.INFO,
            CompressionLayer.PRUNING,
            f"[Layer 2 - Pruning] 历史修剪完成: "
            f"{messages_pruned} 条消息, 节省 {tokens_saved} tokens, "
            f"触发原因: {trigger_reason}, 使用率: {usage_ratio:.1%}",
        )

        # 记录操作日志
        self._add_operation_log(
            layer=CompressionLayer.PRUNING,
            action="prune",
            details={
                "messages_pruned": messages_pruned,
                "tokens_saved": tokens_saved,
                "trigger_reason": trigger_reason,
                "usage_ratio": usage_ratio,
            },
        )

    # ==================== Layer 3: Compaction ====================

    def record_compaction(
        self,
        messages_archived: int,
        tokens_saved: int,
        chapter_index: int,
        summary_length: int = 0,
        key_tools: Optional[List[str]] = None,
    ) -> None:
        """记录压缩归档操作"""
        metrics = self._metrics.compaction

        # 更新累计统计
        metrics.total_count += 1
        metrics.total_messages_archived += messages_archived
        metrics.total_tokens_saved += tokens_saved
        metrics.total_chapters_created += 1

        # 更新当前状态
        metrics.current_chapters += 1
        metrics.current_chapter_index = chapter_index

        # 更新最近一次操作
        metrics.last_messages_archived = messages_archived
        metrics.last_tokens_saved = tokens_saved
        metrics.last_chapter_index = chapter_index
        metrics.last_summary_length = summary_length
        metrics.last_timestamp = time.time()

        # 记录章节统计
        metrics.chapter_stats.append(
            {
                "index": chapter_index,
                "messages": messages_archived,
                "tokens_saved": tokens_saved,
                "summary_length": summary_length,
                "key_tools": key_tools or [],
                "timestamp": time.time(),
            }
        )

        self._metrics.updated_at = time.time()

        # 日志记录
        self._log(
            LogLevel.INFO,
            CompressionLayer.COMPACTION,
            f"[Layer 3 - Compaction] 会话压缩完成: "
            f"归档 {messages_archived} 条消息至章节 {chapter_index}, "
            f"节省 {tokens_saved} tokens, 摘要长度: {summary_length}",
        )

        # 记录操作日志
        self._add_operation_log(
            layer=CompressionLayer.COMPACTION,
            action="compact",
            details={
                "messages_archived": messages_archived,
                "tokens_saved": tokens_saved,
                "chapter_index": chapter_index,
                "summary_length": summary_length,
                "key_tools": key_tools,
            },
        )

    # ==================== 章节状态更新 ====================

    def update_chapter_state(self, total_chapters: int, current_index: int) -> None:
        """更新章节状态 (从外部同步)"""
        self._metrics.compaction.current_chapters = total_chapters
        self._metrics.compaction.current_chapter_index = current_index
        self._metrics.updated_at = time.time()

    # ==================== 指标获取 ====================

    def get_metrics(self) -> ContextMetrics:
        """获取当前指标"""
        return self._metrics

    def get_metrics_dict(self) -> Dict[str, Any]:
        """获取指标字典 (用于序列化)"""
        return self._metrics.to_dict()

    def get_metrics_json(self) -> str:
        """获取指标 JSON 字符串"""
        return json.dumps(self.get_metrics_dict(), ensure_ascii=False, indent=2)

    def get_summary(self) -> str:
        """获取摘要字符串"""
        return self._metrics.to_summary()

    def get_operation_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取操作日志"""
        return self._operation_log[-limit:]

    # ==================== 重置和导出 ====================

    def reset(self) -> None:
        """重置所有指标"""
        self._metrics = ContextMetrics(
            conv_id=self.conv_id,
            session_id=self.session_id,
            context_window=self._metrics.context_window,
            config=self._metrics.config,
        )
        self._operation_log.clear()

        self._log(LogLevel.INFO, CompressionLayer.TRUNCATION, "指标收集器已重置")

    # ==================== 内部方法 ====================

    def _log(self, level: LogLevel, layer: CompressionLayer, message: str) -> None:
        """内部日志记录"""
        if not self.enable_logging:
            return

        log_msg = f"[{self.conv_id[:8]}] {message}"

        if level == LogLevel.DEBUG:
            logger.debug(log_msg)
        elif level == LogLevel.INFO:
            logger.info(log_msg)
        elif level == LogLevel.WARNING:
            logger.warning(log_msg)
        elif level == LogLevel.ERROR:
            logger.error(log_msg)

    def _add_operation_log(
        self,
        layer: CompressionLayer,
        action: str,
        details: Dict[str, Any],
    ) -> None:
        """添加操作日志"""
        entry = {
            "timestamp": time.time(),
            "layer": layer.value,
            "action": action,
            "details": details,
            "context_state": {
                "tokens": self._metrics.current_tokens,
                "usage_ratio": self._metrics.usage_ratio,
                "message_count": self._metrics.message_count,
            },
        }

        self._operation_log.append(entry)

        # 限制日志条目数量
        if len(self._operation_log) > self._max_log_entries:
            self._operation_log = self._operation_log[-self._max_log_entries :]


# =============================================================================
# 全局指标注册表 (可选 - 用于跨会话查询)
# =============================================================================


class ContextMetricsRegistry:
    """全局指标注册表

    用于缓存和查询多个会话的指标。
    注意: 仅用于内存缓存，不持久化。
    """

    _instance: Optional[ContextMetricsRegistry] = None
    _collectors: Dict[str, ContextMetricsCollector] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, collector: ContextMetricsCollector) -> None:
        """注册收集器"""
        key = f"{collector.conv_id}:{collector.session_id}"
        self._collectors[key] = collector

    def unregister(self, conv_id: str, session_id: str) -> None:
        """注销收集器"""
        key = f"{conv_id}:{session_id}"
        self._collectors.pop(key, None)

    def get(self, conv_id: str, session_id: str) -> Optional[ContextMetricsCollector]:
        """获取收集器"""
        key = f"{conv_id}:{session_id}"
        return self._collectors.get(key)

    def get_all_metrics(self) -> List[ContextMetrics]:
        """获取所有指标"""
        return [c.get_metrics() for c in self._collectors.values()]

    def clear_all(self) -> None:
        """清空所有"""
        self._collectors.clear()


# 全局注册表实例
metrics_registry = ContextMetricsRegistry()
