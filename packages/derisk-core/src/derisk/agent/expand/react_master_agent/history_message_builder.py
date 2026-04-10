"""
HistoryMessageBuilder - 统一三层压缩架构

================================================================================
架构设计
================================================================================

统一分层：当前对话和历史对话使用同一套三层架构

┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 4 (归档层) - 不在 message list 中                                      │
│ 由 ToolAction 自动处理：大工具结果存文件，返回 file_key 引用                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 3 (Cold Layer) - 高度压缩                                              │
│ ├── 最老历史对话：LLM 摘要                                                    │
│ ├── 当前对话的旧工具调用：LLM 汇总摘要（超出 Hot+Warm 预算的部分）              │
│ └── Token 预算: 10%                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 2 (Warm Layer) - 适度压缩                                              │
│ ├── 较早历史对话：摘要                                                        │
│ ├── 当前对话的中等旧工具调用：结果压缩（超出 Hot 预算但在 Hot+Warm 预算内）      │
│ └── Token 预算: 25%                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 1 (Hot Layer) - 完整保留                                               │
│ ├── 当前对话的最近工具调用（完整，在 Hot 预算内）                              │
│ ├── 当前对话的 message_chain（完整）                                          │
│ ├── 最近历史对话（完整）                                                      │
│ └── Token 预算: 50%                                                         │
└─────────────────────────────────────────────────────────────────────────────┘

触发机制：
- 基于 Token 阈值实时触发
- 从最新往最旧遍历工具调用，累计 tokens 超过阈值则进入下一层
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING
from enum import Enum

from derisk.core import ModelMessageRoleType
from derisk.core.interface.media import MediaContent
from derisk.agent.core.memory.gpts.system_event import SystemEventType

if TYPE_CHECKING:
    from derisk.agent.core.memory.session_history import (
        SessionHistoryManager,
        SessionConversation,
    )
    from derisk.agent.expand.react_master_agent.work_log import (
        WorkLogManager,
        WorkLogCompressionCache,
    )
    from derisk.agent.core.memory.gpts.system_event import SystemEventManager
    from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
    from derisk.agent.core.memory.gpts.base import GptsMessage
    from derisk.core.interface.llm import LLMClient

logger = logging.getLogger(__name__)

# 统一 token 估算常量：约4个字符为1个 token
# 所有组件（HistoryMessageBuilder, LayerManager, WorkLogManager, SessionConversation）
# 必须使用相同的值，否则分层边界会错乱
DEFAULT_CHARS_PER_TOKEN = 4


@dataclass
class BuildResult:
    """
    消息构建结果

    包含构建的消息列表和分层信息，用于：
    1. 返回给调用者使用
    2. 告知 GptsMemory 哪些数据进入了 Cold 层（可清理）
    """

    messages: List[Dict[str, Any]]
    layer_tokens: Dict[str, int]

    hot_message_ids: List[str] = field(default_factory=list)
    warm_message_ids: List[str] = field(default_factory=list)
    cold_message_ids: List[str] = field(default_factory=list)

    hot_entry_count: int = 0
    warm_entry_count: int = 0
    cold_entry_count: int = 0

    total_tokens: int = 0
    context_window: int = 0

    def get_cache_cleanup_hints(self) -> Dict[str, List[str]]:
        """
        获取缓存清理提示

        Cold 层消息已被压缩为摘要，原始数据可从内存清理
        Warm 层消息已被适度压缩，WorkEntry 原始结果可清理

        Returns:
            {
                "can_evict_message_ids": [...],  # Cold 层消息 ID
                "can_evict_entry_message_ids": [...],  # Cold + Warm 层
            }
        """
        return {
            "can_evict_message_ids": self.cold_message_ids,
            "can_evict_entry_message_ids": self.cold_message_ids
            + self.warm_message_ids,
        }


class CompressionAction(Enum):
    KEEP_FULL = "keep_full"
    COMPRESS_MODERATE = "compress_moderate"
    COMPRESS_LLM = "compress_llm"
    ARCHIVE = "archive"
    SKIP = "skip"
    MOVE_TO_WARM = "move_to_warm"
    MOVE_TO_COLD = "move_to_cold"


@dataclass
class CompressionLog:
    action: CompressionAction
    layer: str
    target: str
    target_id: Optional[str] = None
    original_length: int = 0
    result_length: int = 0
    reason: str = ""
    trigger_condition: str = ""
    compression_ratio: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.original_length > 0:
            self.compression_ratio = round(
                1 - (self.result_length / self.original_length), 2
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "layer": self.layer,
            "target": self.target,
            "target_id": self.target_id,
            "original_length": self.original_length,
            "result_length": self.result_length,
            "reason": self.reason,
            "trigger_condition": self.trigger_condition,
            "compression_ratio": self.compression_ratio,
            "saved_chars": self.original_length - self.result_length,
            "timestamp": self.timestamp,
        }


@dataclass
class CompressionConfig:
    # 统一压缩参数 — 与 LayerManager / SessionHistoryManagerConfig 一致
    hot_ratio: float = 0.45
    warm_ratio: float = 0.25
    cold_ratio: float = 0.10
    tool_messages_ratio: float = 0.15

    hot_conversation_count: int = 10
    hot_tool_result_keep_full_threshold: int = 8000

    warm_conversation_count: int = 5
    warm_tool_result_max_length: int = 400
    warm_summary_max_length: int = 250
    warm_enable_llm_pruning: bool = True
    warm_prune_error_after_turns: int = 4
    warm_prune_duplicate_tools: bool = True
    warm_prune_superseded_writes: bool = True
    warm_preserve_tools: List[str] = field(
        default_factory=lambda: ["view", "read", "ask_user"]
    )
    warm_write_tools: List[str] = field(
        default_factory=lambda: ["edit", "write", "create_file", "edit_file"]
    )
    warm_read_tools: List[str] = field(default_factory=lambda: ["read", "view", "cat"])

    cold_summary_max_length: int = 250

    archive_threshold_bytes: int = 10 * 1024

    llm_summary_temperature: float = 0.3

    preserve_tools_patterns: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "view": ["skill.md"],
        }
    )

    chars_per_token: int = DEFAULT_CHARS_PER_TOKEN

    max_tool_result_length: int = 5000
    emergency_compression_threshold: float = 0.90

    def calculate_budgets(self, context_window: int) -> Dict[str, int]:
        return {
            "hot": int(context_window * self.hot_ratio),
            "warm": int(context_window * self.warm_ratio),
            "cold": int(context_window * self.cold_ratio),
            "tool_messages": int(context_window * self.tool_messages_ratio),
            "system_and_tools": int(context_window * 0.10),
            "total": context_window,
        }


HistoryMessageBuilderConfig = CompressionConfig


class HistoryMessageBuilder:
    """
    历史消息构建器 - 三层增量压缩架构

    核心设计：
    1. 历史对话：使用 SessionHistoryManager 的三层缓存（已压缩）
    2. 当前对话：使用 LayerManager 进行增量分层
    3. 预算共享：当前对话预算 = 总预算 - 历史对话占用

    写入时分层，读取无重算。
    """

    def __init__(
        self,
        session_history_manager: Optional["SessionHistoryManager"] = None,
        work_log_manager: Optional["WorkLogManager"] = None,
        config: Optional[HistoryMessageBuilderConfig] = None,
        llm_client: Optional["LLMClient"] = None,
        system_event_manager: Optional["SystemEventManager"] = None,
        layer_manager: Optional["LayerManager"] = None,
        gpts_memory: Optional["GptsMemory"] = None,
    ):
        self.session_history_manager = session_history_manager
        self.work_log_manager = work_log_manager
        self.config = config or HistoryMessageBuilderConfig()
        self.llm_client = llm_client
        self.system_event_manager = system_event_manager
        # gpts_memory: 消息骨架数据源（user/AI 消息来自这里）
        self.gpts_memory = gpts_memory
        if not self.gpts_memory and self.session_history_manager:
            self.gpts_memory = getattr(
                self.session_history_manager, "gpts_memory", None
            )
        self.compression_logs: List[CompressionLog] = []
        self._last_budget_info: Dict[str, Any] = {}
        self._last_layer_event_data: Optional[Dict[str, Any]] = None
        self._layer_event_min_change_ratio: float = 0.05

        # 当前对话的分层管理器
        self._layer_manager: Optional["LayerManager"] = layer_manager
        self._layer_manager_initialized = False

        logger.info(
            f"HistoryMessageBuilder initialized with 3-layer incremental architecture, "
            f"ratios: hot={self.config.hot_ratio}, warm={self.config.warm_ratio}, cold={self.config.cold_ratio}"
        )

    def get_compression_logs(self) -> List[Dict[str, Any]]:
        return [log.to_dict() for log in self.compression_logs]

    def clear_compression_logs(self):
        self.compression_logs = []

    def get_compression_summary(self) -> Dict[str, Any]:
        total_original = sum(log.original_length for log in self.compression_logs)
        total_result = sum(log.result_length for log in self.compression_logs)
        total_saved = total_original - total_result

        actions = {}
        for log in self.compression_logs:
            key = log.action.value
            if key not in actions:
                actions[key] = {"count": 0, "saved_chars": 0}
            actions[key]["count"] += 1
            actions[key]["saved_chars"] += log.original_length - log.result_length

        return {
            "total_operations": len(self.compression_logs),
            "total_original_chars": total_original,
            "total_result_chars": total_result,
            "total_saved_chars": total_saved,
            "compression_ratio": round(1 - (total_result / total_original), 2)
            if total_original > 0
            else 0,
            "actions": actions,
        }

    def _log_compression(
        self,
        action: CompressionAction,
        layer: str,
        target: str,
        target_id: Optional[str] = None,
        original_length: int = 0,
        result_length: int = 0,
        reason: str = "",
        trigger_condition: str = "",
    ):
        log_entry = CompressionLog(
            action=action,
            layer=layer,
            target=target,
            target_id=target_id,
            original_length=original_length,
            result_length=result_length,
            reason=reason,
            trigger_condition=trigger_condition,
        )
        self.compression_logs.append(log_entry)
        logger.debug(f"[CompressionLog] {log_entry.action.value} {layer}/{target}")

    def set_session_history_manager(self, manager: "SessionHistoryManager"):
        self.session_history_manager = manager

    def set_work_log_manager(self, manager: "WorkLogManager"):
        self.work_log_manager = manager

    def set_llm_client(self, client: "LLMClient"):
        self.llm_client = client

    def set_system_event_manager(self, manager: "SystemEventManager"):
        self.system_event_manager = manager

    # ========== gpts_messages 消息骨架方法 ==========

    async def _get_gpts_messages(self, conv_id: str) -> List["GptsMessage"]:
        """从 gpts_memory 加载指定对话的消息列表（按 rounds 排序）。

        优先使用 get_messages_with_work_entries() 以关联 v2 消息的 WorkEntry，
        使 action_report property 能正确从 WorkEntry 构建。
        异常时返回空列表，由调用方 fallback 到 work_log。
        """
        if not self.gpts_memory:
            return []
        try:
            if hasattr(self.gpts_memory, "get_messages_with_work_entries"):
                messages = await self.gpts_memory.get_messages_with_work_entries(
                    conv_id
                )
            else:
                messages = await self.gpts_memory.get_messages(conv_id)
            return messages or []
        except Exception as e:
            logger.warning(
                f"[HistoryMessageBuilder] Failed to get gpts_messages "
                f"for {conv_id}: {e}"
            )
            return []

    def _build_worklog_lookup(self, entries: List[Any]) -> Dict[str, Any]:
        """从 work_log entries 构建 {tool_call_id: entry} 映射。

        过滤掉 __user_message__ 等非工具条目。
        """
        lookup = {}
        for entry in entries:
            tool = getattr(entry, "tool", "")
            if tool == "__user_message__":
                continue
            tc_id = getattr(entry, "tool_call_id", None)
            if tc_id:
                lookup[tc_id] = entry
        return lookup

    def _build_messages_from_gpts_and_worklog(
        self,
        gpts_msgs: List["GptsMessage"],
        worklog_lookup: Dict[str, Any],
        compression_level: str = "hot",
    ) -> List[Dict[str, Any]]:
        """核心统一构建器：gpts_messages 做消息骨架 + work_log 提供工具结果。

        Args:
            gpts_msgs: GptsMessage 列表（按 rounds 排序）
            worklog_lookup: {tool_call_id: WorkEntry} 映射
            compression_level: "hot" | "warm" | "cold"

        Returns:
            标准 LLM message list
        """
        messages: List[Dict[str, Any]] = []

        # 构建辅助索引: tool_name -> [entry] (按时间排序，用于 fallback)
        tool_name_lookup: Dict[str, List[Any]] = {}
        for entry in worklog_lookup.values():
            tname = getattr(entry, "tool", "")
            if tname:
                if tname not in tool_name_lookup:
                    tool_name_lookup[tname] = []
                tool_name_lookup[tname].append(entry)
        # 跟踪已消费的 fallback 索引
        tool_name_consumed: Dict[str, int] = {}

        for msg in gpts_msgs:
            role = (
                getattr(msg, "role", None) or getattr(msg, "sender", None) or ""
            ).lower()

            if role in ("human", "user"):
                content = self._build_user_content(msg)
                if content:
                    messages.append(
                        {
                            "role": ModelMessageRoleType.HUMAN,
                            "content": content,
                        }
                    )

            elif role not in ("system", "tool"):
                # 非 human/system/tool 的消息都视为 AI 消息
                # 兼容自定义 agent role（如 "BAIZE(DERISK)"）和标准 "ai"/"assistant"
                content = str(msg.content) if msg.content else ""
                tool_calls = getattr(msg, "tool_calls", None)

                if tool_calls:
                    # AI message with tool_calls
                    messages.append(
                        {
                            "role": ModelMessageRoleType.AI,
                            "content": content,
                            "tool_calls": tool_calls,
                        }
                    )
                    # 每个 tool_call 从 work_log 查结果
                    for tc in tool_calls:
                        tc_id = tc.get("id")
                        if not tc_id:
                            continue

                        entry = worklog_lookup.get(tc_id)

                        # Fallback 1: 按 tool_name 顺序匹配
                        if not entry:
                            func = tc.get("function", {})
                            tc_name = func.get("name", "") if isinstance(func, dict) else ""
                            if tc_name and tc_name in tool_name_lookup:
                                idx = tool_name_consumed.get(tc_name, 0)
                                candidates = tool_name_lookup[tc_name]
                                if idx < len(candidates):
                                    entry = candidates[idx]
                                    tool_name_consumed[tc_name] = idx + 1

                        # Fallback 2: 从 gpts_message 的 action_report 获取
                        if entry:
                            result = self._compress_tool_result(
                                entry, compression_level
                            )
                        else:
                            result = self._get_tool_result_from_gpts_msg(msg, tc_id)

                        messages.append(
                            {
                                "role": ModelMessageRoleType.TOOL,
                                "tool_call_id": tc_id,
                                "content": result,
                            }
                        )
                elif content:
                    # Plain AI message (no tool calls, e.g. blank action)
                    messages.append(
                        {
                            "role": ModelMessageRoleType.AI,
                            "content": content,
                        }
                    )

        return messages

    def _get_tool_result_from_gpts_msg(
        self, msg: "GptsMessage", tool_call_id: str
    ) -> str:
        """从 GptsMessage 的 action_report / observation 中提取工具结果（fallback）。"""
        # 尝试 action_report
        action_report = getattr(msg, "action_report", None)
        if action_report and isinstance(action_report, list):
            for report in action_report:
                content = getattr(report, "content", None) or getattr(
                    report, "observations", None
                )
                if content:
                    return str(content)

        # 尝试 observation
        obs = getattr(msg, "observation", None)
        if obs:
            return str(obs)

        logger.warning(
            f"[HistoryMessageBuilder] No result found for tool_call_id={tool_call_id}, "
            f"message_id={getattr(msg, 'message_id', 'unknown')}"
        )
        return "[tool execution result not recorded]"

    def _compress_tool_result(self, entry: Any, level: str = "hot") -> str:
        """根据压缩级别处理工具结果。

        Args:
            entry: WorkEntry
            level: "hot" (完整) | "warm" (截断) | "cold" (摘要)
        """
        if level == "cold":
            summary = getattr(entry, "summary", "") or ""
            return summary or "[no summary]"

        result = getattr(entry, "result", "") or ""

        if level == "warm":
            tool_name = getattr(entry, "tool", "")
            args = getattr(entry, "args", {}) or {}
            if self._should_preserve_full(tool_name, args):
                return result
            if len(result) > self.config.warm_tool_result_max_length:
                truncated = self._truncate_content(
                    result, self.config.warm_tool_result_max_length
                )
                archive_ref = getattr(entry, "full_result_archive", None)
                if archive_ref:
                    truncated += f"\n详情: {archive_ref}"
                return truncated
            return result

        # hot: 完整结果，超大时截断
        if len(result) > self.config.hot_tool_result_keep_full_threshold:
            archive_ref = getattr(entry, "full_result_archive", None)
            if archive_ref:
                return f"{result[:500]}...\n\n[完整结果已归档] 文件: {archive_ref}"
        return result

    @staticmethod
    def _extract_text_content(content: Any) -> str:
        """将各种格式的 content 统一转为 str。

        处理: str, list (MediaContent), dict 等格式。
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    obj = item.get("object", {})
                    text_parts.append(
                        obj.get("data", "") if isinstance(obj, dict) else ""
                    )
                elif hasattr(item, "object"):
                    obj = getattr(item, "object", None)
                    text_parts.append(getattr(obj, "data", "") if obj else "")
            return "\n".join(filter(None, text_parts))
        return str(content)

    @staticmethod
    def _build_user_content(msg) -> Union[str, List[Dict[str, Any]]]:
        """从 GptsMessage 构建用户消息 content，支持多模态。

        新格式：content 直接是 List[MediaContent]，直接转为 OpenAI 格式。
        老格式（兼容）：content 是纯文本，从 content_types + context 重建。

        返回 OpenAI 多模态格式或纯文本字符串。
        """
        content = getattr(msg, "content", "")

        # 新格式：content 已经是 List[MediaContent]
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, MediaContent):
                result = MediaContent.to_chat_completion_message(content)
                return result

        # 纯文本或老格式
        text = HistoryMessageBuilder._extract_text_content(content)

        content_types = getattr(msg, "content_types", None) or []
        context = getattr(msg, "context", None) or {}

        # 收集多模态内容（老格式兼容）
        multimodal_parts: List[Dict[str, Any]] = []
        _MEDIA_TYPE_MAPPING = {
            "image_url": "image_url",
            "file_url": "file_url",
            "audio_url": "audio_url",
            "video_url": "video_url",
        }

        for ctx_key, part_type in _MEDIA_TYPE_MAPPING.items():
            if ctx_key in content_types and ctx_key in context:
                urls = context[ctx_key]
                if isinstance(urls, str):
                    urls = [urls]
                for url in urls:
                    if url:
                        multimodal_parts.append(
                            {"type": part_type, part_type: {"url": url}}
                        )

        if not multimodal_parts:
            return text

        parts: List[Dict[str, Any]] = []
        if text:
            parts.append({"type": "text", "text": text})
        parts.extend(multimodal_parts)
        return parts if parts else text

    async def _generate_summary_with_llm(
        self,
        content: str,
        summary_type: str = "general",
        max_length: int = 500,
    ) -> str:
        if not self.llm_client:
            return self._truncate_content(content, max_length)

        prompts = {
            "cold_question": f"请用简洁的语言总结以下用户问题的核心内容，不超过{max_length}字：\n\n{content}",
            "cold_answer": f"请用简洁的语言总结以下AI回答的核心内容，不超过{max_length}字：\n\n{content}",
            "tool_result": f"请用简洁的语言总结以下工具执行结果的关键信息，不超过{max_length}字：\n\n{content}",
            "work_log_batch": f"请用简洁的语言总结以下工具调用记录的核心内容和结果，不超过{max_length}字：\n\n{content}",
            "conversation": f"请用简洁的语言总结以下对话的问题和答案，不超过{max_length}字：\n\n{content}",
        }

        prompt = prompts.get(summary_type, prompts["conversation"])
        content_preview = content[:100] + "..." if len(content) > 100 else content

        if self.system_event_manager:
            self.system_event_manager.add_event(
                event_type=SystemEventType.COMPRESSION_LLM_SUMMARY,
                title=f"正在生成摘要 ({summary_type})",
                description=f"内容预览: {content_preview}",
                metadata={"summary_type": summary_type, "content_length": len(content)},
            )

        try:
            response = await self.llm_client.async_call(
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.llm_summary_temperature,
                max_tokens=max_length,
            )
            response_content = response.content
            if isinstance(response_content, list):
                summary = MediaContent.last_text(response_content)
            else:
                summary = response_content.get_text()

            if self.system_event_manager:
                self.system_event_manager.add_event(
                    event_type=SystemEventType.COMPRESSION_COMPLETE,
                    title="摘要生成完成",
                    description=f"原始长度: {len(content)} -> 摘要长度: {len(summary)}",
                    metadata={
                        "summary_type": summary_type,
                        "original_length": len(content),
                        "summary_length": len(summary),
                    },
                )

            return summary[:max_length]
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}")

            if self.system_event_manager:
                self.system_event_manager.add_event(
                    event_type=SystemEventType.COMPRESSION_LLM_FAILED,
                    title="摘要生成失败",
                    description=f"错误: {str(e)}",
                    metadata={"summary_type": summary_type, "error": str(e)},
                )

            return self._truncate_content(content, max_length)

    def _truncate_content(self, content: str, max_length: int) -> str:
        if len(content) <= max_length:
            return content
        return content[: max_length - 3] + "..."

    def _should_preserve_full(self, tool_name: str, args: Dict[str, Any]) -> bool:
        patterns = self.config.preserve_tools_patterns.get(tool_name, [])
        if not patterns:
            return False

        path = str(args.get("path", args.get("file_path", "")))
        for pattern in patterns:
            if path.endswith(pattern):
                return True
        return False

    def _is_preserved_message(self, msg: Dict[str, Any]) -> bool:
        """判断消息是否包含需要保护的工具调用（如 view skill.md）

        保护规则：匹配 preserve_tools_patterns 的 AI 消息（带 tool_calls）
        及其配对的 tool 消息不应在剪枝时被丢弃。
        """
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            return False
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                args = json.loads(func.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                args = {}
            if self._should_preserve_full(tool_name, args):
                return True
        return False

    def _categorize_entries_by_tokens(
        self,
        entries: List[Any],
        hot_budget: int,
        warm_budget: int,
        cold_budget: int = 0,
    ) -> Tuple[List[Any], List[Any], List[Any]]:
        """
        基于 Token 阈值分层工具调用

        从最新往最旧遍历，累计 tokens 判断归属层级：
        - 累计 ≤ hot_budget → Hot Layer
        - 累计 ≤ hot_budget + warm_budget → Warm Layer
        - 累计 > hot_budget + warm_budget → Cold Layer

        Cold Layer 的处理：
        - 超出 Hot+Warm 的部分会被标记为 Cold
        - 但 Cold Layer 有预算上限 (cold_budget)
        - 超出 Cold 预算的最旧部分会被抛弃

        Returns:
            (hot_entries, warm_entries, cold_entries)
        """
        hot_entries: List[Any] = []
        warm_entries: List[Any] = []
        cold_entries: List[Any] = []

        cumulative_tokens = 0
        hot_threshold = hot_budget
        warm_threshold = hot_budget + warm_budget

        for entry in reversed(entries):
            entry_tokens = self._estimate_entry_tokens(entry)
            cumulative_tokens += entry_tokens

            if cumulative_tokens <= hot_threshold:
                hot_entries.insert(0, entry)
            elif cumulative_tokens <= warm_threshold:
                warm_entries.insert(0, entry)
            else:
                cold_entries.insert(0, entry)

        # Cold Layer 预算控制：如果超出，从最旧的开始抛弃
        if cold_budget > 0 and cold_entries:
            cold_tokens = sum(self._estimate_entry_tokens(e) for e in cold_entries)
            if cold_tokens > cold_budget:
                # 从最旧的开始抛弃，直到符合预算
                kept_entries = []
                kept_tokens = 0
                for entry in cold_entries:
                    entry_tokens = self._estimate_entry_tokens(entry)
                    if kept_tokens + entry_tokens <= cold_budget:
                        kept_entries.append(entry)
                        kept_tokens += entry_tokens
                    else:
                        # 跳过超大 entry，继续检查后面更小的
                        continue
                dropped_count = len(cold_entries) - len(kept_entries)
                if dropped_count > 0:
                    logger.info(
                        f"[HistoryMessageBuilder] Cold budget exceeded, "
                        f"dropped {dropped_count} oldest entries "
                        f"({cold_tokens} -> {kept_tokens} tokens)"
                    )
                cold_entries = kept_entries

        return hot_entries, warm_entries, cold_entries

    def _estimate_entry_tokens(self, entry: Any) -> int:
        tokens = getattr(entry, "tokens", 0) or 0
        if tokens == 0:
            result = getattr(entry, "result", "") or ""
            args = getattr(entry, "args", {}) or {}
            assistant_content = getattr(entry, "assistant_content", "") or ""
            total_chars = len(result) + len(str(args)) + len(assistant_content)
            tokens = max(1, total_chars // self.config.chars_per_token)
        return tokens

    async def build_messages(
        self,
        current_conv_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context_window: int = 128000,
        include_current_conversation: bool = True,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        构建消息列表（三层增量压缩架构）

        统一从 session_history + work_log 构建完整的消息列表，包括：
        - Cold 层：已提交的历史对话摘要（来自 session_history_manager）
        - Warm 层：已提交的历史对话剪枝版（来自 session_history_manager）
        - Hot 层：最近的完整对话记录（来自 session_history + work_log 合并）
          包含前轮对话和当前对话的 user/ai/tool 完整消息

        Args:
            current_conv_id: 当前对话 ID
            session_id: 当前会话 ID，用于过滤 work_log 中同 session 的 entries
            context_window: 上下文窗口大小
            include_current_conversation: 是否包含当前对话（通常为 True）

        Returns:
            Tuple[List[Dict[str, Any]], Dict[str, int]]: (messages, layer_tokens)
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0
        layer_tokens = {"hot": 0, "warm": 0, "cold": 0}

        budgets = self.config.calculate_budgets(context_window)
        hot_budget = budgets["hot"]
        warm_budget = budgets["warm"]
        cold_budget = budgets["cold"]

        self._last_budget_info = {
            "context_window": context_window,
            "hot_budget": hot_budget,
            "warm_budget": warm_budget,
            "cold_budget": cold_budget,
        }

        logger.info(
            f"[HistoryMessageBuilder] Building messages: "
            f"context_window={context_window}, hot={hot_budget}, warm={warm_budget}, cold={cold_budget}, "
            f"current_conv_id={current_conv_id}, session_id={session_id}, "
            f"include_current={include_current_conversation}"
        )

        # ========== 初始化 LayerManager ==========
        if self._layer_manager and not self._layer_manager_initialized:
            from .layer_manager import LayerMigrationConfig

            layer_config = LayerMigrationConfig(
                hot_ratio=self.config.hot_ratio,
                warm_ratio=self.config.warm_ratio,
                cold_ratio=self.config.cold_ratio,
                warm_tool_result_max_length=self.config.warm_tool_result_max_length,
                cold_summary_max_length=self.config.cold_summary_max_length,
                enable_duplicate_prune=self.config.warm_prune_duplicate_tools,
                enable_error_prune=True,
                error_prune_after_turns=self.config.warm_prune_error_after_turns,
                enable_superseded_prune=self.config.warm_prune_superseded_writes,
                preserve_tools=self.config.warm_preserve_tools,
                chars_per_token=self.config.chars_per_token,
            )
            self._layer_manager.config = layer_config
            self._layer_manager.set_budgets(context_window)
            self._layer_manager_initialized = True

        if self.session_history_manager:
            # ========== 有 session_history_manager: Cold + Warm + Hot（合并 work_log）==========
            if not getattr(self.session_history_manager, "_initialized", False):
                try:
                    await self.session_history_manager.load_session_history()
                except Exception as e:
                    logger.error(
                        f"[HistoryMessageBuilder] Failed to load session history: {e}",
                        exc_info=True,
                    )
                    # 降级：仅使用 work_log
                    logger.warning(
                        "[HistoryMessageBuilder] Falling back to work_log only mode"
                    )
                    self.session_history_manager = None

        if self.session_history_manager:
            # ========== 有 session_history_manager: Cold + Warm + Hot（合并 work_log）==========

            # ✅ 主动触发压缩检查，确保分层符合 token 预算
            if self.session_history_manager.config.enable_compression:
                try:
                    await self.session_history_manager._check_and_compress()
                    logger.info(
                        f"[HistoryMessageBuilder] Compression check triggered: "
                        f"hot={len(self.session_history_manager.hot_conversations)}, "
                        f"warm={len(self.session_history_manager.warm_summaries)}, "
                        f"cold={len(self.session_history_manager.cold_archives)}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[HistoryMessageBuilder] Compression check failed: {e}"
                    )

            # Step 1: Cold 层 — 已提交的历史对话摘要
            cold_messages, cold_tokens = await self._build_cold_layer(
                cold_budget, current_conv_id, hot_budget, warm_budget
            )
            messages.extend(cold_messages)
            total_tokens += cold_tokens
            layer_tokens["cold"] = cold_tokens

            # Step 2: Warm 层 — 已提交的历史对话剪枝版
            warm_messages, warm_tokens = await self._build_warm_layer(
                current_conv_id, warm_budget, hot_budget
            )
            messages.extend(warm_messages)
            total_tokens += warm_tokens
            layer_tokens["warm"] = warm_tokens

            # Step 3: Hot 层 — 合并 session_history.hot_conversations + work_log
            hot_messages, hot_tokens = await self._build_hot_layer(
                current_conv_id, session_id, hot_budget, include_current_conversation
            )
            messages.extend(hot_messages)
            total_tokens += hot_tokens
            layer_tokens["hot"] = hot_tokens

        elif self.work_log_manager:
            # ========== 无 session_history_manager: 全部从 work_log 构建 ==========
            hot_messages, hot_tokens = await self._build_all_from_work_log(
                session_id, current_conv_id, hot_budget, include_current_conversation
            )
            messages.extend(hot_messages)
            total_tokens += hot_tokens
            layer_tokens["hot"] = hot_tokens

        elif self._layer_manager and include_current_conversation:
            # ========== 最后回退: 仅 LayerManager ==========
            current_messages, current_layer_tokens = (
                self._build_current_from_layer_manager()
            )
            messages.extend(current_messages)
            total_tokens += sum(current_layer_tokens.values())
            layer_tokens = current_layer_tokens

        self._notify_token_budget_summary(
            total_tokens, context_window, layer_tokens, budgets
        )

        logger.info(
            f"[HistoryMessageBuilder] Built {len(messages)} messages, ~{total_tokens} tokens, "
            f"layers: hot={layer_tokens.get('hot', 0)}, warm={layer_tokens.get('warm', 0)}, cold={layer_tokens.get('cold', 0)}"
        )

        return messages, layer_tokens

    async def build_messages_with_result(
        self,
        current_conv_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context_window: int = 128000,
        include_current_conversation: bool = True,
        cold_storage: Optional["ColdStorage"] = None,
    ) -> BuildResult:
        """
        构建消息列表并返回 BuildResult

        与 build_messages 功能相同，但返回结构化的 BuildResult，
        包含分层信息和清理提示，用于与 GptsMemory 协作。

        Args:
            current_conv_id: 当前对话 ID
            session_id: 会话 ID
            context_window: 上下文窗口
            include_current_conversation: 是否包含当前对话
            cold_storage: Cold 层存储（用于读取/保存 Cold 摘要）

        Returns:
            BuildResult 包含消息列表、分层信息、清理提示
        """
        messages, layer_tokens = await self.build_messages(
            current_conv_id=current_conv_id,
            session_id=session_id,
            context_window=context_window,
            include_current_conversation=include_current_conversation,
        )

        total_tokens = sum(layer_tokens.values())

        hot_message_ids = []
        warm_message_ids = []
        cold_message_ids = []

        hot_entry_count = 0
        warm_entry_count = 0
        cold_entry_count = 0

        if self.session_history_manager:
            for conv_id, conv in self.session_history_manager.hot_conversations.items():
                hot_message_ids.extend(getattr(conv, "message_ids", []) or [])
                hot_entry_count += len(getattr(conv, "work_entries", []) or [])

            for conv_id, summary in self.session_history_manager.warm_summaries.items():
                warm_message_ids.append(conv_id)

            for conv_id in self.session_history_manager.cold_archives.keys():
                cold_message_ids.append(conv_id)

        if cold_storage and cold_message_ids:
            await self._ensure_cold_summaries_persisted(
                cold_storage, cold_message_ids, session_id
            )

        return BuildResult(
            messages=messages,
            layer_tokens=layer_tokens,
            hot_message_ids=hot_message_ids,
            warm_message_ids=warm_message_ids,
            cold_message_ids=cold_message_ids,
            hot_entry_count=hot_entry_count,
            warm_entry_count=warm_entry_count,
            cold_entry_count=cold_entry_count,
            total_tokens=total_tokens,
            context_window=context_window,
        )

    async def _ensure_cold_summaries_persisted(
        self,
        cold_storage: "ColdStorage",
        cold_conv_ids: List[str],
        session_id: Optional[str],
    ):
        """确保 Cold 摘要已持久化"""
        from derisk.agent.core.memory.gpts.cold_storage import ColdConversationSummary
        from datetime import datetime

        for conv_id in cold_conv_ids:
            existing = await cold_storage.get_summary(conv_id)
            if existing:
                continue

            if self.session_history_manager:
                conv = self.session_history_manager.cold_archives.get(conv_id)
                if conv:
                    summary = ColdConversationSummary(
                        conv_id=conv_id,
                        session_id=session_id or "",
                        created_at=datetime.now(),
                        updated_at=datetime.now(),
                        question_summary=getattr(conv, "cold_summary", "")[:500] or "",
                        answer_summary="",
                        message_count=1,
                        compressed_tokens=getattr(conv, "tokens", 0) or 0,
                    )
                    await cold_storage.save_summary(summary)

    def _notify_token_budget_summary(
        self,
        total_used: int,
        context_window: int,
        layer_tokens: Dict[str, int],
        budgets: Dict[str, int],
    ):
        if not self.system_event_manager:
            return

        usage_ratio = round(total_used / context_window, 4) if context_window > 0 else 0
        remaining = context_window - total_used

        def format_tokens(tokens: int) -> str:
            if tokens >= 1000000:
                return f"{tokens / 1000000:.1f}M"
            elif tokens >= 1000:
                return f"{tokens / 1000:.0f}K"
            return str(tokens)

        usage_pct = usage_ratio * 100
        description = f"历史: {format_tokens(total_used)}, Hot/Warm/Cold: {format_tokens(layer_tokens.get('hot', 0))}/{format_tokens(layer_tokens.get('warm', 0))}/{format_tokens(layer_tokens.get('cold', 0))}"

        should_push = False
        if self._last_layer_event_data is None:
            should_push = True
        else:
            last_total = self._last_layer_event_data.get("total_used", 0)
            change_ratio = abs(total_used - last_total) / max(total_used, last_total, 1)
            if change_ratio >= self._layer_event_min_change_ratio:
                should_push = True

        if should_push:
            self.system_event_manager.add_event(
                event_type=SystemEventType.TOKEN_BUDGET_LAYER_USED,
                title="历史消息分层",
                description=description,
                metadata={
                    "total_used": total_used,
                    "context_window": context_window,
                    "remaining": remaining,
                    "usage_ratio": usage_ratio,
                    "layer_tokens": layer_tokens,
                    "budgets": budgets,
                },
            )

            self._last_layer_event_data = {
                "total_used": total_used,
                "layer_tokens": layer_tokens,
                "budgets": budgets,
            }

    def get_last_budget_info(self) -> Dict[str, Any]:
        return self._last_budget_info

    async def _build_cold_layer(
        self,
        token_budget: int,
        current_conv_id: Optional[str] = None,
        hot_budget: int = 0,
        warm_budget: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        if not self.session_history_manager:
            return messages, total_tokens

        cold_archives = getattr(self.session_history_manager, "cold_archives", {})

        for conv_id, conv in cold_archives.items():
            # G2 修复: 不使用缓存的 cold_summary，直接构建 user + ai 消息对
            # 因为缓存格式是单条 AI 消息，不符合 user/ai 对格式要求

            # 构建 Cold Layer 摘要：包含用户问题 + AI 回复 + 关键工具调用
            summary_parts = []
            question_summary = ""
            ai_summary = ""
            tool_calls_summary = []

            # 1. 用户问题
            initial_query = conv.initial_user_query or conv.user_query or ""
            if initial_query:
                if (
                    len(initial_query) > self.config.cold_summary_max_length
                    and self.llm_client
                ):
                    question_summary = await self._generate_summary_with_llm(
                        initial_query,
                        summary_type="cold_question",
                        max_length=self.config.cold_summary_max_length,
                    )
                else:
                    question_summary = self._truncate_content(
                        initial_query, self.config.cold_summary_max_length
                    )
                summary_parts.append(f"问题: {question_summary}")

            # 2. 从 message_chain 提取关键 AI 回复和工具调用
            if conv.message_chain:
                tool_calls_summary = []
                ai_responses = []

                for msg in conv.message_chain:
                    role_lower = (msg.role or "").lower()
                    content_str = str(msg.content) if msg.content else ""

                    if role_lower in ("ai", "assistant"):
                        # 提取 AI 回复
                        if content_str and len(content_str) > 100:
                            ai_responses.append(content_str[:200])
                        # 提取 tool_calls
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                func_name = tc.get("function", {}).get(
                                    "name", "unknown"
                                )
                                tool_calls_summary.append(func_name)
                    elif role_lower == "tool":
                        # 工具结果的关键信息
                        if content_str and len(content_str) > 100:
                            pass  # 工具结果在 Cold 层只保留 tool_calls 名称

                if tool_calls_summary:
                    unique_tools = list(dict.fromkeys(tool_calls_summary))
                    summary_parts.append(f"工具调用: {', '.join(unique_tools[:5])}")

                if ai_responses:
                    combined_ai = "\n".join(ai_responses[:3])
                    if len(combined_ai) > self.config.cold_summary_max_length:
                        if self.llm_client:
                            ai_summary = await self._generate_summary_with_llm(
                                combined_ai,
                                summary_type="cold_answer",
                                max_length=self.config.cold_summary_max_length,
                            )
                        else:
                            ai_summary = self._truncate_content(
                                combined_ai, self.config.cold_summary_max_length
                            )
                    else:
                        ai_summary = combined_ai
                    summary_parts.append(f"回答: {ai_summary}")

            # 3. 最终答案（如果有）
            answer_summary = ""
            final_answer = conv.final_answer or ""
            if final_answer and not summary_parts:
                if (
                    len(final_answer) > self.config.cold_summary_max_length
                    and self.llm_client
                ):
                    answer_summary = await self._generate_summary_with_llm(
                        final_answer,
                        summary_type="cold_answer",
                        max_length=self.config.cold_summary_max_length,
                    )
                else:
                    answer_summary = self._truncate_content(
                        final_answer, self.config.cold_summary_max_length
                    )
                summary_parts.append(f"结果: {answer_summary}")

            # 合并摘要
            full_summary = "\n".join(summary_parts)
            conv.cold_summary = full_summary

            # Cold 层：user 问题 + ai 摘要（不加额外前缀）
            # P1-2 修复: 确保 AI 消息前必有 user 消息，避免违反对话结构
            if not question_summary:
                question_summary = initial_query or "(历史对话)"
            messages.append(
                {
                    "role": ModelMessageRoleType.HUMAN,
                    "content": question_summary,
                }
            )

            if ai_summary or tool_calls_summary:
                answer_content = ai_summary if ai_summary else ""
                if tool_calls_summary:
                    unique_tools = list(dict.fromkeys(tool_calls_summary))
                    tools_str = ", ".join(unique_tools[:5])
                    answer_content = (
                        f"{answer_content}\n工具: {tools_str}"
                        if answer_content
                        else f"工具: {tools_str}"
                    )

                messages.append(
                    {
                        "role": ModelMessageRoleType.AI,
                        "content": answer_content,
                    }
                )
            elif final_answer and answer_summary:
                messages.append(
                    {
                        "role": ModelMessageRoleType.AI,
                        "content": answer_summary,
                    }
                )

            conv_tokens = self._estimate_tokens(messages[-1:])
            if total_tokens + conv_tokens > token_budget:
                messages = messages[:-1]
                break

            total_tokens += conv_tokens

            self._log_compression(
                action=CompressionAction.COMPRESS_LLM,
                layer="cold",
                target=conv_id,
                original_length=conv.total_tokens or 0,
                result_length=conv_tokens * self.config.chars_per_token,
                reason="cold_layer_llm_summary",
                trigger_condition=f"len>{self.config.cold_summary_max_length}",
            )

        # 当前对话 worklog 的 cold 处理：仅在 worklog 总 token 超过 hot+warm 预算时才触发
        # 避免内容很少时过早压缩到 cold 层
        if current_conv_id and self.work_log_manager:
            await self.work_log_manager.initialize()
            current_entries = self.work_log_manager.get_entries(current_conv_id)
            if current_entries:
                total_entry_tokens = sum(
                    self._estimate_entry_tokens(e) for e in current_entries
                )
                if total_entry_tokens > hot_budget + warm_budget:
                    (
                        cold_worklog_messages,
                        cold_worklog_tokens,
                    ) = await self._build_current_conv_cold_worklog(
                        current_conv_id,
                        token_budget - total_tokens,
                        hot_budget,
                        warm_budget,
                    )
                    messages.extend(cold_worklog_messages)
                    total_tokens += cold_worklog_tokens
                else:
                    logger.info(
                        f"[HistoryMessageBuilder] Skipping cold worklog for {current_conv_id}: "
                        f"total_entry_tokens={total_entry_tokens} <= hot+warm={hot_budget + warm_budget}"
                    )

        return messages, total_tokens

    async def _build_current_conv_cold_worklog(
        self,
        conv_id: str,
        token_budget: int,
        hot_budget: int,
        warm_budget: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        if not self.work_log_manager:
            return messages, total_tokens

        await self.work_log_manager.initialize()

        # 优先使用 LayerManager 的分层结果（避免双重分层）
        if self._layer_manager:
            hot_wrappers, warm_wrappers, cold_summaries = (
                self._layer_manager.get_entries_by_layer(conv_id)
            )
            # LayerManager 的 cold 是摘要，这里需要原始 entries
            # cold worklog entries 是不在 hot/warm 中的最旧 entries
            entries = self.work_log_manager.get_entries(conv_id)
            hot_warm_set = set()
            for w in hot_wrappers + warm_wrappers:
                hot_warm_set.add(id(w.entry))
            cold_entries = [e for e in entries if id(e) not in hot_warm_set]
        else:
            entries = self.work_log_manager.get_entries(conv_id)
            _, _, cold_entries = self._categorize_entries_by_tokens(
                entries, hot_budget, warm_budget, token_budget
            )

        if not cold_entries:
            return messages, total_tokens

        # 压缩逻辑：把 cold 范围的所有 entries 转为文本 → LLM 摘要 → 输出为消息
        # cold_entries 已按时间顺序排列，直接整体处理

        # 1. 提取 user 问题（从 gpts_messages 获取）
        user_question = None
        gpts_msgs = await self._get_gpts_messages(conv_id)
        for msg in gpts_msgs:
            role = (
                getattr(msg, "role", None) or getattr(msg, "sender", None) or ""
            ).lower()
            if role in ("human", "user"):
                user_question = self._extract_text_content(getattr(msg, "content", ""))
                break  # 只取第一个 user 问题

        # 2. 把所有 cold entries 转为文本，整体发给 LLM 做摘要
        cold_content = self._entries_to_summary_text(cold_entries)
        original_length = len(cold_content)

        max_summary_chars = token_budget * self.config.chars_per_token
        max_summary_chars = min(
            max_summary_chars, self.config.cold_summary_max_length * 2
        )

        if self.llm_client and len(cold_content) > 200:
            summary = await self._generate_summary_with_llm(
                cold_content,
                summary_type="work_log_batch",
                max_length=max_summary_chars,
            )
        else:
            summary = self._truncate_content(cold_content, max_summary_chars)

        summary_tokens = self._estimate_tokens_text(summary)
        if summary_tokens > token_budget:
            max_chars = token_budget * self.config.chars_per_token
            summary = summary[:max_chars]

        # 3. 输出消息：user 问题 + ai 摘要
        if user_question:
            if len(user_question) > self.config.cold_summary_max_length:
                user_question = self._truncate_content(
                    user_question, self.config.cold_summary_max_length
                )
            messages.append(
                {"role": ModelMessageRoleType.HUMAN, "content": user_question}
            )
        messages.append({"role": ModelMessageRoleType.AI, "content": summary})

        self.work_log_manager.update_compression_cache(
            conv_id=conv_id,
            layer3_summary=summary,
            layer3_end_index=len(cold_entries),
            layer2_start_index=len(cold_entries),
            total_entries=len(entries),
            compressed_tokens=self._estimate_tokens_text(summary),
        )

        self._log_compression(
            action=CompressionAction.COMPRESS_LLM,
            layer="cold",
            target=f"current_conv_worklog/{conv_id}",
            original_length=original_length,
            result_length=len(summary),
            reason="token_budget_exceeded",
            trigger_condition=f"tokens>{hot_budget + warm_budget}",
        )

        return messages, self._estimate_tokens(messages)

    async def _build_warm_layer(
        self,
        current_conv_id: Optional[str],
        token_budget: int,
        hot_budget: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        if not self.session_history_manager:
            return messages, total_tokens

        # P1-4 修复: 不 reverse，保持时间正序（旧→新），先处理老对话
        warm_convs = list(self.session_history_manager.warm_summaries.items())

        for conv_id, conv in warm_convs:
            if conv_id == current_conv_id:
                continue

            conv_messages = await self._build_warm_conv_messages(conv, conv_id)
            conv_tokens = self._estimate_tokens(conv_messages)

            if total_tokens + conv_tokens > token_budget:
                break

            messages.extend(conv_messages)
            total_tokens += conv_tokens

        if current_conv_id and self.work_log_manager:
            (
                warm_worklog_messages,
                warm_worklog_tokens,
            ) = await self._build_current_conv_warm_worklog(
                current_conv_id, token_budget - total_tokens, hot_budget, token_budget
            )
            messages.extend(warm_worklog_messages)
            total_tokens += warm_worklog_tokens

        return messages, total_tokens

    async def _build_current_conv_warm_worklog(
        self,
        conv_id: str,
        token_budget: int,
        hot_budget: int,
        total_budget: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        if not self.work_log_manager:
            return messages, total_tokens

        await self.work_log_manager.initialize()

        # 优先使用 LayerManager 的分层结果（避免双重分层）
        if self._layer_manager:
            _, warm_wrappers, _ = self._layer_manager.get_entries_by_layer(conv_id)
            warm_entries = [w.entry for w in warm_wrappers]
        else:
            entries = self.work_log_manager.get_entries(conv_id)
            warm_budget = total_budget - hot_budget
            _, warm_entries, _ = self._categorize_entries_by_tokens(
                entries, hot_budget, warm_budget, 0
            )

        if not warm_entries:
            return messages, total_tokens

        for entry in warm_entries:
            tool = getattr(entry, "tool", "")
            # 跳过 __user_message__ 条目
            if tool == "__user_message__":
                continue

            tool_call_id = getattr(entry, "tool_call_id", None)
            assistant_content = getattr(entry, "assistant_content", "") or ""

            # Blank action: LLM 纯文本输出（非工具调用），转为 AI message
            if not tool_call_id:
                if assistant_content:
                    messages.append(
                        {
                            "role": ModelMessageRoleType.AI,
                            "content": assistant_content,
                        }
                    )
                    msg_tokens = self._estimate_tokens(messages[-1:])
                    if total_tokens + msg_tokens > token_budget:
                        messages.pop()
                        break
                    total_tokens += msg_tokens
                continue

            messages.append(
                {
                    "role": ModelMessageRoleType.AI,
                    "content": assistant_content,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool,
                                "arguments": json.dumps(
                                    getattr(entry, "args", None) or {}
                                ),
                            },
                        }
                    ],
                }
            )

            result_content = self._compress_tool_result(entry, "warm")
            messages.append(
                {
                    "role": ModelMessageRoleType.TOOL,
                    "tool_call_id": tool_call_id,
                    "content": result_content,
                }
            )

            conv_tokens = self._estimate_tokens(messages[-2:])
            if total_tokens + conv_tokens > token_budget:
                args = getattr(entry, "args", None) or {}
                if not self._should_preserve_full(tool, args):
                    messages = messages[:-2]
                    break
            total_tokens += conv_tokens

        if messages:
            warm_tokens = sum(self._estimate_entry_tokens(e) for e in warm_entries)
            self._log_compression(
                action=CompressionAction.COMPRESS_MODERATE,
                layer="warm",
                target=f"current_conv_worklog/{conv_id}",
                original_length=warm_tokens,
                result_length=total_tokens,
                reason="token_budget_moderate",
                trigger_condition=f"tokens>{hot_budget}({warm_tokens})",
            )

        # 智能剪枝
        messages = await self._smart_prune_messages(
            messages,
            token_budget=token_budget,
            current_turn=0,
        )
        total_tokens = self._estimate_tokens(messages)

        return messages, total_tokens

    async def _build_warm_conv_messages(
        self,
        conv: "SessionConversation",
        conv_id: str,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []

        # Warm 缓存失效检查：内容变化时重新生成
        content_hash = self._compute_conv_hash(conv)
        cache_hash = getattr(conv, "_warm_cache_hash", None)
        if conv.warm_compressed_content and cache_hash == content_hash:
            return self._parse_cached_warm_content(conv.warm_compressed_content)

        # 从 message_chain 构建，保留 tool_calls 和 tool 消息
        if conv.message_chain:
            for msg in conv.message_chain:
                content_str = str(msg.content) if msg.content else ""
                role_lower = (msg.role or "").lower()

                if role_lower in ("human", "user"):
                    # 用户消息：适度压缩
                    if len(content_str) > self.config.warm_tool_result_max_length:
                        content_str = self._truncate_content(
                            content_str, self.config.warm_tool_result_max_length
                        )
                    messages.append(
                        {
                            "role": ModelMessageRoleType.HUMAN,
                            "content": content_str,
                        }
                    )
                elif role_lower in ("ai", "assistant"):
                    # AI 消息：保留 tool_calls，压缩 content
                    if len(content_str) > self.config.warm_tool_result_max_length:
                        content_str = self._truncate_content(
                            content_str, self.config.warm_tool_result_max_length
                        )
                    msg_dict = {
                        "role": ModelMessageRoleType.AI,
                        "content": content_str,
                    }
                    if msg.tool_calls:
                        msg_dict["tool_calls"] = msg.tool_calls
                    messages.append(msg_dict)
                elif role_lower == "tool":
                    messages.append(
                        {
                            "role": ModelMessageRoleType.TOOL,
                            "tool_call_id": getattr(msg, "tool_call_id", None),
                            "content": content_str,
                        }
                    )

        # 如果没有 message_chain，使用 summary 作为备选
        if not messages:
            user_query = conv.user_query or ""
            if user_query:
                messages.append(
                    {
                        "role": ModelMessageRoleType.HUMAN,
                        "content": user_query,
                    }
                )

            if conv.summary:
                messages.append(
                    {
                        "role": ModelMessageRoleType.AI,
                        "content": conv.summary[: self.config.cold_summary_max_length],
                    }
                )

            if conv.final_answer:
                messages.append(
                    {
                        "role": ModelMessageRoleType.AI,
                        "content": f"结果: {conv.final_answer[: self.config.cold_summary_max_length]}",
                    }
                )

        # 智能剪枝（去重 + 清理错误 + LLM 评估）
        warm_budget = int(self.config.warm_ratio * 128000)
        messages = await self._smart_prune_messages(
            messages,
            token_budget=warm_budget,
            current_turn=conv.total_rounds or 0,
        )

        conv.warm_compressed_content = json.dumps(messages)
        conv._warm_cache_hash = content_hash

        self._log_compression(
            action=CompressionAction.COMPRESS_MODERATE,
            layer="warm",
            target=conv_id,
            original_length=conv.total_tokens or 0,
            result_length=self._estimate_tokens(messages) * self.config.chars_per_token,
            reason="warm_layer_moderate_compression",
            trigger_condition="moved_from_hot_layer",
        )

        return messages

    def _parse_cached_warm_content(self, cached: str) -> List[Dict[str, Any]]:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning(f"[HistoryMessageBuilder] Failed to parse warm cache: {e}")
            return []

    async def _build_hot_layer(
        self,
        current_conv_id: Optional[str],
        session_id: Optional[str],
        token_budget: int,
        include_current: bool,
    ) -> tuple[List[Dict[str, Any]], int]:
        """构建 Hot 层消息 — 数据源职责分离。

        数据源职责划分（不重叠）：
        - 历史对话 → SessionHistoryManager.hot_conversations（已完成的对话）
        - 当前对话 → WorkLogManager / LayerManager（实时在途数据）
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        # ========== Part 1: 历史对话（从 SessionHistoryManager）==========
        history_conv_ids = []
        if self.session_history_manager:
            logger.info(
                f"[HistoryMessageBuilder] _build_hot_layer: "
                f"session_history hot={len(self.session_history_manager.hot_conversations)}, "
                f"warm={len(self.session_history_manager.warm_summaries)}, "
                f"cold={len(self.session_history_manager.cold_archives)}"
            )

            # 历史对话按时间正序排列
            for cid, conv in self.session_history_manager.hot_conversations.items():
                if cid == current_conv_id:
                    continue  # 当前对话不从 SessionHistory 取，由 Part 2 处理

                conv_messages = self._build_hot_conv_messages(conv)
                conv_tokens = self._estimate_tokens(conv_messages)

                if total_tokens + conv_tokens > token_budget:
                    logger.info(
                        f"[HistoryMessageBuilder] Hot budget exceeded at history conv {cid}, stopping"
                    )
                    break

                messages.extend(conv_messages)
                total_tokens += conv_tokens
                history_conv_ids.append(cid)

                logger.info(
                    f"[HistoryMessageBuilder] Hot history conv {cid}: "
                    f"{len(conv_messages)} messages, {conv_tokens} tokens"
                )

        # ========== Part 2: 当前对话（从 WorkLogManager / LayerManager）==========
        if include_current and current_conv_id:
            remaining_budget = token_budget - total_tokens

            # 同时收集 work_log 中属于同 session 但不在 history 的前轮对话
            work_log_by_conv = self._group_work_log_by_conv(session_id)
            history_conv_id_set = set(history_conv_ids)
            if self.session_history_manager:
                history_conv_id_set |= set(self.session_history_manager.warm_summaries.keys())
                history_conv_id_set |= set(self.session_history_manager.cold_archives.keys())

            for cid, entries in work_log_by_conv.items():
                if cid == current_conv_id:
                    continue  # 当前对话最后处理
                if cid in history_conv_id_set:
                    continue  # 已在 SessionHistory 中处理过

                conv_messages = self._build_messages_from_work_entries(entries)
                conv_tokens = self._estimate_tokens(conv_messages)

                if total_tokens + conv_tokens > remaining_budget:
                    break

                messages.extend(conv_messages)
                total_tokens += conv_tokens
                logger.info(
                    f"[HistoryMessageBuilder] Hot work_log conv {cid}: "
                    f"{len(conv_messages)} messages, {conv_tokens} tokens"
                )

            # 最后：当前对话
            if current_conv_id in work_log_by_conv:
                current_entries = work_log_by_conv[current_conv_id]
                current_messages = self._build_messages_from_work_entries(current_entries)
                current_tokens = self._estimate_tokens(current_messages)
                messages.extend(current_messages)
                total_tokens += current_tokens
                logger.info(
                    f"[HistoryMessageBuilder] Hot current conv {current_conv_id}: "
                    f"{len(current_messages)} messages, {current_tokens} tokens"
                )

        logger.info(
            f"[HistoryMessageBuilder] _build_hot_layer total: "
            f"history_convs={len(history_conv_ids)}, "
            f"total_messages={len(messages)}, total_tokens={total_tokens}"
        )

        return messages, total_tokens

    def _group_work_log_by_conv(
        self, session_id: Optional[str] = None
    ) -> Dict[str, List]:
        """将 work_log 的 entries 按 conv_id 分组，可选按 session_id 过滤。"""
        if not self.work_log_manager:
            return {}

        result: Dict[str, List] = {}
        for entry in self.work_log_manager.work_log:
            cid = entry.conv_id or "default"
            # 如果提供了 session_id，只保留同 session 的 entries
            # P2-1 修复: 使用分隔符匹配或精确匹配，防止 "abc" 匹配 "abcxyz"
            if session_id and cid != session_id and not cid.startswith(session_id + "_"):
                continue
            if cid not in result:
                result[cid] = []
            result[cid].append(entry)
        return result

    def _build_messages_from_work_entries(self, entries: List) -> List[Dict[str, Any]]:
        """从 WorkEntry 列表构建消息（fallback 路径，无 gpts_messages 时使用）。

        处理工具调用、blank action 和 user 消息（从 __user_message__ 条目还原）。
        """
        messages: List[Dict[str, Any]] = []
        for entry in entries:
            tool = getattr(entry, "tool", "")
            human_content = getattr(entry, "human_content", "") or ""

            # __user_message__: 从 work_log 还原 user 消息
            if tool == "__user_message__" or (not tool and human_content):
                content = human_content or getattr(entry, "result", "") or ""
                if content:
                    messages.append(
                        {
                            "role": ModelMessageRoleType.HUMAN,
                            "content": self._extract_text_content(content),
                        }
                    )
                continue

            tool_call_id = getattr(entry, "tool_call_id", None)
            assistant_content = getattr(entry, "assistant_content", "") or ""

            # Blank action
            if not tool_call_id:
                if assistant_content:
                    messages.append(
                        {
                            "role": ModelMessageRoleType.AI,
                            "content": assistant_content,
                        }
                    )
                continue

            # Tool call: ai + tool result
            messages.append(
                {
                    "role": ModelMessageRoleType.AI,
                    "content": assistant_content,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool,
                                "arguments": json.dumps(
                                    getattr(entry, "args", None) or {}
                                ),
                            },
                        }
                    ],
                }
            )
            result = self._compress_tool_result(entry, "hot")
            messages.append(
                {
                    "role": ModelMessageRoleType.TOOL,
                    "tool_call_id": tool_call_id,
                    "content": result,
                }
            )

        return messages

    async def _build_all_from_work_log(
        self,
        session_id: Optional[str],
        current_conv_id: Optional[str],
        token_budget: int,
        include_current: bool,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """无 session_history_manager 时的消息构建。

        统一使用 WorkEntry 构建消息，WorkLogManager 是权威数据源。
        如果有 gpts_memory 可用，尝试用 gpts_messages 做消息骨架以获得更完整的消息结构。

        追问场景补偿：当 WorkLog 缺少历史轮次（如 round 1 数据未从 DB 加载）时，
        通过 get_session_messages(session_id) 从 DB 加载全 session 的 gpts_messages，
        补充缺失的 conv_ids。
        """
        work_log_by_conv = self._group_work_log_by_conv(session_id)

        # ========== 追问补偿：从 gpts_memory 补充缺失的历史轮次 ==========
        # 优先使用 load_full_session_history（支持 Cold 层压缩过滤），
        # 降级使用 get_session_messages（加载全部，用 token_budget 兜底）。
        session_gpts_msgs_by_conv: Dict[str, list] = {}
        cold_data = None
        if self.gpts_memory and session_id and current_conv_id:
            try:
                loaded_msgs = []

                # 方案 1: load_full_session_history — 压缩感知，只加载 hot/warm
                if hasattr(self.gpts_memory, "load_full_session_history"):
                    # 获取已压缩的 conv_ids（来自 WorkLogManager 的压缩缓存）
                    cold_conv_ids = []
                    if self.work_log_manager and hasattr(
                        self.work_log_manager, "compression_cache"
                    ):
                        cache = self.work_log_manager.compression_cache
                        if cache and hasattr(cache, "cold_conv_ids"):
                            cold_conv_ids = list(cache.cold_conv_ids)

                    result = await self.gpts_memory.load_full_session_history(
                        conv_id=current_conv_id,
                        conv_session_id=session_id,
                        cold_conv_ids=cold_conv_ids,
                    )
                    if result:
                        cold_data = result.get("cold_data")
                        # 从缓存中获取刚加载的消息
                        loaded_msgs = await self.gpts_memory.get_messages(
                            current_conv_id
                        )
                        logger.info(
                            f"[HistoryMessageBuilder] 追问补偿(压缩感知): "
                            f"hot_warm={result.get('hot_warm_count', 0)}, "
                            f"cold={result.get('cold_count', 0)}, "
                            f"loaded_msgs={len(loaded_msgs)}"
                        )

                # 方案 2: get_session_messages — 无压缩过滤，加载全部
                if not loaded_msgs and hasattr(
                    self.gpts_memory, "get_session_messages"
                ):
                    loaded_msgs = await self.gpts_memory.get_session_messages(
                        session_id
                    )
                    if loaded_msgs:
                        logger.info(
                            f"[HistoryMessageBuilder] 追问补偿(全量): "
                            f"loaded {len(loaded_msgs)} msgs from DB"
                        )
                        if hasattr(self.gpts_memory, "_cache_messages"):
                            await self.gpts_memory._cache_messages(
                                current_conv_id, loaded_msgs
                            )

                if loaded_msgs:
                    for msg in loaded_msgs:
                        cid = getattr(msg, "conv_id", None) or "default"
                        if cid not in session_gpts_msgs_by_conv:
                            session_gpts_msgs_by_conv[cid] = []
                        session_gpts_msgs_by_conv[cid].append(msg)

                    # 补充 work_log 中缺失的 conv_ids
                    missing_cids = set(session_gpts_msgs_by_conv.keys()) - set(
                        work_log_by_conv.keys()
                    )
                    if missing_cids:
                        logger.info(
                            f"[HistoryMessageBuilder] 追问补偿: 补充 "
                            f"{len(missing_cids)} 个历史轮次: {missing_cids}"
                        )
                        for cid in missing_cids:
                            work_log_by_conv[cid] = []

            except Exception as e:
                logger.warning(
                    f"[HistoryMessageBuilder] 追问补偿失败: {e}"
                )

        def _sort_key(cid: str):
            entries = work_log_by_conv.get(cid, [])
            if entries:
                return entries[0].timestamp if entries else 0
            # 无 WorkEntry 时，用 gpts_message 的 rounds 或 created_at 排序
            msgs = session_gpts_msgs_by_conv.get(cid, [])
            if msgs:
                return getattr(msgs[0], "rounds", 0) or 0
            return 0

        ordered_conv_ids = sorted(work_log_by_conv.keys(), key=_sort_key)

        logger.info(
            f"[HistoryMessageBuilder] _build_all_from_work_log: "
            f"conv_count={len(ordered_conv_ids)}, "
            f"current_conv_id={current_conv_id}, include_current={include_current}"
        )

        messages: List[Dict[str, Any]] = []
        total_tokens = 0

        # Cold 层摘要消息放在最前面（最早的历史）
        if cold_data and hasattr(cold_data, "to_llm_messages"):
            cold_messages = cold_data.to_llm_messages()
            if cold_messages:
                cold_tokens = self._estimate_tokens(cold_messages)
                messages.extend(cold_messages)
                total_tokens += cold_tokens
                logger.info(
                    f"[HistoryMessageBuilder] Cold 层摘要: {len(cold_messages)} msgs, "
                    f"~{cold_tokens} tokens"
                )

        for cid in ordered_conv_ids:
            if cid == current_conv_id and not include_current:
                continue

            entries = work_log_by_conv.get(cid, [])

            # 优先使用已加载的 session gpts_msgs，再 fallback 到按 conv_id 查询
            gpts_msgs = session_gpts_msgs_by_conv.get(cid, [])
            if not gpts_msgs and self.gpts_memory:
                gpts_msgs = await self._get_gpts_messages(cid)

            if gpts_msgs:
                worklog_lookup = self._build_worklog_lookup(entries)
                conv_messages = self._build_messages_from_gpts_and_worklog(
                    gpts_msgs, worklog_lookup, "hot"
                )
            elif entries:
                # 纯 work_log 构建（WorkEntry 自包含完整数据）
                conv_messages = self._build_messages_from_work_entries(entries)
            else:
                continue

            conv_tokens = self._estimate_tokens(conv_messages)

            if total_tokens + conv_tokens > token_budget:
                logger.info(
                    f"[HistoryMessageBuilder] work_log budget exceeded at conv {cid}"
                )
                break

            messages.extend(conv_messages)
            total_tokens += conv_tokens

        return messages, total_tokens

    def _build_hot_conv_messages(
        self,
        conv: "SessionConversation",
    ) -> List[Dict[str, Any]]:
        """从 SessionConversation 构建 Hot 层消息。

        message_chain (gpts_messages) 做消息骨架，work_entries 提供工具结果。
        """
        if conv.message_chain:
            worklog_lookup = self._build_worklog_lookup(conv.work_entries or [])
            return self._build_messages_from_gpts_and_worklog(
                conv.message_chain, worklog_lookup, "hot"
            )

        # Fallback: 无 message_chain，直接从 work_entries 构建 ai+tool 消息
        if conv.work_entries:
            return self._build_hot_tool_messages(conv.work_entries)

        return []

    async def _build_current_conv_messages(
        self,
        conv: "SessionConversation",
        hot_budget: int,
    ) -> List[Dict[str, Any]]:
        """从 SessionConversation 构建当前对话消息。

        message_chain (gpts_messages) 做消息骨架，work_entries 提供工具结果。
        """
        if conv.message_chain:
            worklog_lookup = self._build_worklog_lookup(conv.work_entries or [])
            return self._build_messages_from_gpts_and_worklog(
                conv.message_chain, worklog_lookup, "hot"
            )

        # Fallback: 无 message_chain，直接从 work_entries 构建
        if conv.work_entries:
            return self._build_hot_tool_messages(conv.work_entries)

        return []

    async def _build_current_conv_only(
        self,
        conv_id: Optional[str],
        hot_budget: int,
        warm_budget: int,
        cold_budget: int,
    ) -> tuple[List[Dict[str, Any]], int, Dict[str, int]]:
        """
        仅构建当前对话的工具调用消息（无历史对话时使用）

        应用三层压缩：
        - Hot: 最新工具调用（完整）
        - Warm: 中等旧工具调用（压缩）
        - Cold: 旧工具调用（LLM 摘要）

        Returns:
            (messages, total_tokens, layer_tokens)
        """
        messages: List[Dict[str, Any]] = []
        total_tokens = 0
        layer_tokens: Dict[str, int] = {"hot": 0, "warm": 0, "cold": 0}

        if not self.work_log_manager:
            return messages, total_tokens, layer_tokens

        await self.work_log_manager.initialize()

        # 优先使用 LayerManager 的分层结果（避免双重分层）
        if self._layer_manager:
            hot_wrappers, warm_wrappers, cold_summaries = (
                self._layer_manager.get_entries_by_layer(conv_id)
            )
            hot_entries = [w.entry for w in hot_wrappers]
            warm_entries = [w.entry for w in warm_wrappers]
            # cold entries: 不在 hot/warm 中的 entries
            entries = self.work_log_manager.get_entries(conv_id)
            hot_warm_set = set()
            for w in hot_wrappers + warm_wrappers:
                hot_warm_set.add(id(w.entry))
            cold_entries = [e for e in entries if id(e) not in hot_warm_set]
        else:
            entries = self.work_log_manager.get_entries(conv_id)
            if not entries:
                return messages, total_tokens, layer_tokens
            hot_entries, warm_entries, cold_entries = (
                self._categorize_entries_by_tokens(
                    entries, hot_budget, warm_budget, cold_budget
                )
            )

        if not hot_entries and not warm_entries and not cold_entries:
            return messages, total_tokens, layer_tokens

        # Cold Layer: LLM 摘要
        if cold_entries:
            cold_content = self._entries_to_summary_text(cold_entries)
            max_summary_chars = cold_budget * self.config.chars_per_token

            if self.llm_client and len(cold_content) > 200:
                summary = await self._generate_summary_with_llm(
                    cold_content,
                    summary_type="work_log_batch",
                    max_length=max_summary_chars,
                )
            else:
                summary = self._truncate_content(cold_content, max_summary_chars)

            messages.append(
                {
                    "role": ModelMessageRoleType.AI,
                    "content": f"[更早的工具调用摘要] {summary}",
                }
            )
            cold_tokens = self._estimate_tokens(messages[-1:])
            total_tokens += cold_tokens
            layer_tokens["cold"] = cold_tokens

        # Warm Layer: 适度压缩
        if warm_entries:
            warm_messages = self._build_warm_tool_messages(warm_entries, warm_budget)
            messages.extend(warm_messages)
            warm_tokens = self._estimate_tokens(warm_messages)
            total_tokens += warm_tokens
            layer_tokens["warm"] = warm_tokens

        # Hot Layer: 完整保留
        if hot_entries:
            hot_messages = self._build_hot_tool_messages(hot_entries)
            messages.extend(hot_messages)
            hot_tokens = self._estimate_tokens(hot_messages)
            total_tokens += hot_tokens
            layer_tokens["hot"] = hot_tokens

        return messages, total_tokens, layer_tokens

    def _build_warm_tool_messages(
        self,
        entries: List[Any],
        token_budget: int,
    ) -> List[Dict[str, Any]]:
        """构建 Warm Layer ai+tool 消息对（适度压缩）。

        纯工具结果构建器，不处理 user 消息（user 消息来自 gpts_messages）。
        """
        messages: List[Dict[str, Any]] = []

        for entry in entries:
            tool = getattr(entry, "tool", "")
            # 跳过 __user_message__ 条目
            if tool == "__user_message__":
                continue

            tool_call_id = getattr(entry, "tool_call_id", None)
            assistant_content = getattr(entry, "assistant_content", "") or ""

            # Blank action: LLM 纯文本输出（非工具调用），转为 AI message
            if not tool_call_id:
                if assistant_content:
                    messages.append(
                        {
                            "role": ModelMessageRoleType.AI,
                            "content": assistant_content,
                        }
                    )
                continue

            messages.append(
                {
                    "role": ModelMessageRoleType.AI,
                    "content": assistant_content,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool,
                                "arguments": json.dumps(
                                    getattr(entry, "args", None) or {}
                                ),
                            },
                        }
                    ],
                }
            )

            result_content = self._compress_tool_result(entry, "warm")

            messages.append(
                {
                    "role": ModelMessageRoleType.TOOL,
                    "tool_call_id": tool_call_id,
                    "content": result_content,
                }
            )

        return messages

    async def _build_current_conv_hot_worklog(
        self,
        conv_id: Optional[str],
        hot_budget: int,
    ) -> List[Dict[str, Any]]:
        """从 gpts_messages + work_log 构建当前对话的完整消息列表。

        gpts_messages 做消息骨架（user/AI），work_log 提供工具结果。
        conv_id 每轮变化（xxx_1, xxx_2），使用 session_id 跨轮次查询。
        """
        if not conv_id:
            return []

        session_id = conv_id.rsplit("_", 1)[0] if "_" in conv_id else conv_id
        logger.info(
            f"[HistoryMessageBuilder] _build_current_conv_hot_worklog: "
            f"conv_id={conv_id}, session_id={session_id}"
        )

        # ========== 优先用 gpts_messages 做消息骨架 ==========
        gpts_memory = self.gpts_memory
        if gpts_memory:
            try:
                # 1. 先尝试从缓存按 session_id 获取（load_full_session_history 已预加载时）
                gpts_msgs = await gpts_memory.get_messages(session_id)
                if not gpts_msgs:
                    # 2. 缓存未命中：从 DB 按 session_id 加载全部轮次消息
                    if hasattr(gpts_memory, "get_session_messages"):
                        gpts_msgs = await gpts_memory.get_session_messages(session_id)
                        if gpts_msgs:
                            logger.info(
                                f"[HistoryMessageBuilder] Loaded {len(gpts_msgs)} msgs "
                                f"from get_session_messages({session_id})"
                            )
                            # 缓存到当前 conv_id 以便后续访问
                            if hasattr(gpts_memory, "_cache_messages"):
                                await gpts_memory._cache_messages(conv_id, gpts_msgs)
                if not gpts_msgs:
                    # 3. 最后兜底：按当前 conv_id 获取（仅当前轮）
                    gpts_msgs = await gpts_memory.get_messages(conv_id)

                if gpts_msgs:
                    # 构建 worklog lookup
                    if self.work_log_manager:
                        await self.work_log_manager.initialize()
                        all_entries = self.work_log_manager.work_log
                        entries = [
                            e
                            for e in all_entries
                            if e.conv_id and e.conv_id.startswith(session_id)
                        ]
                    else:
                        entries = []
                    worklog_lookup = self._build_worklog_lookup(entries)

                    messages = self._build_messages_from_gpts_and_worklog(
                        gpts_msgs, worklog_lookup, "hot"
                    )
                    logger.info(
                        f"[HistoryMessageBuilder] Built {len(messages)} messages "
                        f"from gpts_messages + worklog"
                    )
                    return messages

            except Exception as e:
                logger.warning(
                    f"[HistoryMessageBuilder] Failed to get gpts_messages: {e}"
                )

        # ========== Fallback: 纯 work_log 构建 ai+tool 消息 ==========
        if self.work_log_manager:
            await self.work_log_manager.initialize()
            all_entries = self.work_log_manager.work_log
            entries = [
                e for e in all_entries if e.conv_id and e.conv_id.startswith(session_id)
            ]

            logger.info(
                f"[HistoryMessageBuilder] WorkLogManager fallback: "
                f"session_id={session_id}, entries={len(entries)}"
            )

            hot_entries, _, _ = self._categorize_entries_by_tokens(
                entries, hot_budget, 0, 0
            )
            return self._build_hot_tool_messages(hot_entries)

        return []

    def _build_hot_tool_messages(
        self,
        entries: List[Any],
    ) -> List[Dict[str, Any]]:
        """从 work_log entries 构建 Hot 层 ai+tool 消息对。

        纯工具结果构建器，不处理 user 消息（user 消息来自 gpts_messages）。
        仅作为 fallback 使用（无 gpts_messages 时）。
        """
        messages: List[Dict[str, Any]] = []

        for entry in entries:
            tool = getattr(entry, "tool", "")
            # 跳过 __user_message__ 条目
            if tool == "__user_message__":
                continue

            tool_call_id = getattr(entry, "tool_call_id", None)
            assistant_content = getattr(entry, "assistant_content", "") or ""

            # Blank action: LLM 纯文本输出（非工具调用），转为 AI message
            if not tool_call_id:
                if assistant_content:
                    messages.append(
                        {
                            "role": ModelMessageRoleType.AI,
                            "content": assistant_content,
                        }
                    )
                continue

            messages.append(
                {
                    "role": ModelMessageRoleType.AI,
                    "content": assistant_content,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool,
                                "arguments": json.dumps(
                                    getattr(entry, "args", None) or {}
                                ),
                            },
                        }
                    ],
                }
            )

            result = self._compress_tool_result(entry, "hot")
            messages.append(
                {
                    "role": ModelMessageRoleType.TOOL,
                    "tool_call_id": tool_call_id,
                    "content": result,
                }
            )

        return messages

    def _entries_to_summary_text(self, entries: List[Any]) -> str:
        lines = []
        for entry in entries:
            tool = getattr(entry, "tool", "unknown")
            summary = getattr(entry, "summary", "") or ""
            success = getattr(entry, "success", True)
            status = "成功" if success else "失败"
            lines.append(f"- {tool}({status}): {summary[:200]}")
        return "\n".join(lines)

    def _prune_duplicate_tools(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        去重：相同工具+相同参数的调用只保留最新的

        OpenCode DCP 策略：
        - 通过签名（tool_name + args）判断重复
        - 只保留最新的调用结果
        """
        if not self.config.warm_prune_duplicate_tools:
            return messages

        seen_signatures: Dict[str, int] = {}
        pruned_messages: List[Dict[str, Any]] = []

        tool_call_id_to_keep: set = set()

        # 第一遍：找出要保留的 tool_call_id
        for i, msg in enumerate(messages):
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    func_name = tc.get("function", {}).get("name", "")
                    args = tc.get("function", {}).get("arguments", "")

                    # 保护特定工具不去重
                    if func_name in self.config.warm_preserve_tools:
                        tool_call_id_to_keep.add(tc.get("id"))
                        continue

                    # 生成签名
                    signature = f"{func_name}:{args}"

                    # 只保留最新的
                    tool_call_id_to_keep.add(tc.get("id"))
                    if signature in seen_signatures:
                        # 移除旧的
                        old_id = seen_signatures[signature]
                        if old_id in tool_call_id_to_keep:
                            tool_call_id_to_keep.remove(old_id)
                    seen_signatures[signature] = tc.get("id")

        # 第二遍：过滤消息
        i = 0
        while i < len(messages):
            msg = messages[i]
            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                tc_id = tool_calls[0].get("id")
                if tc_id in tool_call_id_to_keep:
                    pruned_messages.append(msg)
                    # 同时保留对应的 tool 响应
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
        """
        清理错误工具调用：N 轮后移除失败的调用

        OpenCode DCP 策略：
        - 保留错误消息（用于调试）
        - 只移除失败的输入参数
        """
        threshold = self.config.warm_prune_error_after_turns
        pruned_messages: List[Dict[str, Any]] = []

        i = 0
        while i < len(messages):
            msg = messages[i]

            if msg.get("role") == "tool":
                content = msg.get("content", "")
                # 使用更精确的错误检测，避免误判 "no error" 等正常内容
                is_error = self._is_error_content(content)

                if is_error and current_turn > threshold:
                    # 替换为错误提示，不保留完整错误
                    pruned_messages.append(
                        {
                            "role": ModelMessageRoleType.TOOL,
                            "tool_call_id": msg.get("tool_call_id"),
                            "content": "[错误工具调用已清理]",
                        }
                    )
                else:
                    pruned_messages.append(msg)
            else:
                pruned_messages.append(msg)

            i += 1

        return pruned_messages

    def _prune_superseded_writes(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        清理被覆盖的写入操作

        OpenCode DCP 策略：
        - 当写入操作之后有读取同一文件的操作
        - 清理写入操作的输入参数（文件内容）
        - 保留写入操作的记录，只清理大内容

        示例：
        [1] edit("config.json", "修改内容...") → 写入
        [2] read("config.json") → 读取
        → [1] 的参数可清理为 "[写入内容已清理，后续已读取]"
        """
        if not self.config.warm_prune_superseded_writes:
            return messages

        write_tools = set(self.config.warm_write_tools)
        read_tools = set(self.config.warm_read_tools)

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
                except:
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
                                                json.dumps(new_args)
                                            )
                                    except:
                                        pass
                        del written_files[file_path]

        return messages

    async def _llm_evaluate_message_value(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        LLM 评估消息价值，清理低价值消息

        评估标准：
        - 是否包含关键决策信息
        - 是否包含重要的技术细节
        - 是否与当前任务相关

        返回：保留的高价值消息
        """
        if not self.config.warm_enable_llm_pruning or not self.llm_client:
            return messages

        if len(messages) < 4:
            return messages

        # 构建评估 prompt
        messages_text = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 50:
                messages_text.append(f"[{i}] {role}: {content[:200]}...")

        if not messages_text:
            return messages

        prompt = f"""分析以下对话片段，判断每条消息的价值。

消息列表:
{chr(10).join(messages_text)}

请返回一个 JSON 数组，包含应该保留的消息索引，格式如: [0, 2, 4]

保留标准：
1. 包含关键决策或结论
2. 包含重要的技术细节（文件路径、错误信息、配置值）
3. 用户的明确指令或问题
4. 重要的工具调用结果

应该清理的：
1. 重复的确认信息
2. 过长的中间过程（可压缩）
3. 与主要任务无关的对话

只返回 JSON 数组，不要其他内容。"""

        try:
            response = await self.llm_client.async_call(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100,
            )

            response_content = response.content
            if isinstance(response_content, list):
                result_text = MediaContent.last_text(response_content)
            else:
                result_text = response_content.get_text()

            # 解析 JSON
            import re

            match = re.search(r"\[.*?\]", result_text)
            if match:
                indices_to_keep = json.loads(match.group())
                return [messages[i] for i in indices_to_keep if i < len(messages)]
        except Exception as e:
            logger.warning(f"LLM message evaluation failed: {e}")

        return messages

    async def _smart_prune_messages(
        self,
        messages: List[Dict[str, Any]],
        token_budget: int,
        current_turn: int = 0,
    ) -> List[Dict[str, Any]]:
        pruned = self._prune_duplicate_tools(messages)
        pruned = self._prune_superseded_writes(pruned)
        pruned = self._prune_error_tools(pruned, current_turn)

        if self.config.warm_enable_llm_pruning and self.llm_client:
            pruned = await self._llm_evaluate_message_value(pruned)

        current_tokens = self._estimate_tokens(pruned)
        if current_tokens > token_budget:
            # 将消息分组为原子单元：assistant(tool_calls)+tool 必须成对保留/丢弃
            # 每个 group = (start_idx, end_idx_exclusive, is_protected, tokens)
            groups: List[Tuple[int, int, bool, int]] = []
            i = 0
            while i < len(pruned):
                msg = pruned[i]
                is_protected = self._is_preserved_message(msg)

                # assistant + tool pair: 必须作为原子单元处理
                if msg.get("tool_calls") and i + 1 < len(pruned) and pruned[i + 1].get("role") == "tool":
                    pair_tokens = self._estimate_tokens([pruned[i], pruned[i + 1]])
                    groups.append((i, i + 2, is_protected, pair_tokens))
                    i += 2
                else:
                    msg_tokens = self._estimate_tokens([msg])
                    # user 消息也受保护
                    if msg.get("role") == "user":
                        is_protected = True
                    groups.append((i, i + 1, is_protected, msg_tokens))
                    i += 1

            # 先预留 protected 组的 token
            protected_tokens = sum(g[3] for g in groups if g[2])
            remaining_budget = token_budget - protected_tokens

            # 从最新组开始累积，丢弃更旧的组（保留最新）
            keep_groups: List[Tuple[int, int]] = []
            for group in reversed(groups):
                start, end, is_prot, g_tokens = group
                if is_prot:
                    keep_groups.append((start, end))
                    continue
                if remaining_budget >= g_tokens:
                    keep_groups.append((start, end))
                    remaining_budget -= g_tokens
                # 否则整组跳过（assistant+tool 一起丢弃）

            # 按原始顺序重建
            keep_indices = set()
            for start, end in keep_groups:
                for idx in range(start, end):
                    keep_indices.add(idx)
            pruned = [pruned[i] for i in range(len(pruned)) if i in keep_indices]

        return pruned

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                total_chars += len(json.dumps(tool_calls))
        return max(1, total_chars // self.config.chars_per_token)

    def _estimate_tokens_text(self, text: str) -> int:
        return max(1, len(text) // self.config.chars_per_token)

    @staticmethod
    def _is_error_content(content: str) -> bool:
        """更精确的错误内容检测，避免误判 'no error'、'error-free' 等"""
        if not content:
            return False
        content_lower = content.lower()
        error_indicators = [
            "traceback (most recent call last)",
            "exception:",
            "error:",
            "执行失败",
            "调用失败",
            "操作失败",
            "raise ",
        ]
        return any(indicator in content_lower for indicator in error_indicators)

    @staticmethod
    def _compute_conv_hash(conv: "SessionConversation") -> str:
        """计算对话内容哈希，用于 warm 缓存失效检测"""
        import hashlib

        parts = [
            str(conv.total_tokens),
            str(conv.total_rounds),
            str(len(conv.message_chain)),
            str(len(conv.work_entries)),
            conv.final_answer[:100] if conv.final_answer else "",
        ]
        return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


async def create_history_message_builder(
    session_history_manager: Optional["SessionHistoryManager"] = None,
    work_log_manager: Optional["WorkLogManager"] = None,
    config: Optional[HistoryMessageBuilderConfig] = None,
    llm_client: Optional["LLMClient"] = None,
    system_event_manager: Optional["SystemEventManager"] = None,
    layer_manager: Optional["LayerManager"] = None,
    context_window: int = 128000,
    gpts_memory: Optional["GptsMemory"] = None,
) -> HistoryMessageBuilder:
    # 如果没有提供 LayerManager，创建一个默认的
    if layer_manager is None and work_log_manager:
        from .layer_manager import LayerManager, LayerMigrationConfig

        layer_config = LayerMigrationConfig(
            hot_ratio=config.hot_ratio if config else 0.5,
            warm_ratio=config.warm_ratio if config else 0.25,
            cold_ratio=config.cold_ratio if config else 0.1,
            warm_tool_result_max_length=config.warm_tool_result_max_length
            if config
            else 500,
            cold_summary_max_length=config.cold_summary_max_length if config else 300,
            enable_duplicate_prune=config.warm_prune_duplicate_tools
            if config
            else True,
            error_prune_after_turns=config.warm_prune_error_after_turns
            if config
            else 4,
            enable_superseded_prune=config.warm_prune_superseded_writes
            if config
            else True,
            preserve_tools=config.warm_preserve_tools if config else [],
            preserve_tools_patterns=config.preserve_tools_patterns
            if config
            else {"view": ["skill.md"]},
            chars_per_token=config.chars_per_token if config else 4,
        )

        layer_manager = LayerManager(config=layer_config, llm_client=llm_client)
        layer_manager.set_budgets(context_window)

        # 关联到 WorkLogManager
        if work_log_manager:
            work_log_manager.set_layer_manager(layer_manager)

    builder = HistoryMessageBuilder(
        session_history_manager=session_history_manager,
        work_log_manager=work_log_manager,
        config=config,
        llm_client=llm_client,
        system_event_manager=system_event_manager,
        layer_manager=layer_manager,
        gpts_memory=gpts_memory,
    )
    return builder


__all__ = [
    "HistoryMessageBuilder",
    "HistoryMessageBuilderConfig",
    "CompressionConfig",
    "CompressionAction",
    "CompressionLog",
    "create_history_message_builder",
]
