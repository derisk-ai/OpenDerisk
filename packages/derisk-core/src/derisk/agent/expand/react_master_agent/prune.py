"""
历史记录修剪 (Prune)

定期清理旧的、可能不再相关的工具调用输出。
从后向前遍历消息历史，当累积的工具输出 Token 数超过阈值时，
将更早的工具输出标记为已压缩 (compacted = true)，
从而在构建下一次 Prompt 时将其忽略。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
from enum import Enum
from datetime import datetime

from derisk.agent import AgentMessage, ActionOutput

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型分类"""
    SYSTEM = "system"           # 系统消息
    USER = "user"               # 用户消息
    ASSISTANT = "assistant"     # 助手消息
    TOOL_OUTPUT = "tool_output" # 工具输出
    THINKING = "thinking"       # 思考过程
    SUMMARY = "summary"         # 摘要消息
    OBSOLETE = "obsolete"       # 已过时消息


@dataclass
class PruneConfig:
    """修剪配置"""
    # 默认保护阈值 - 当累积 Token 超过此值时开始修剪
    DEFAULT_PRUNE_PROTECT = 4000

    # 工具输出 Token 保护比例
    TOOL_OUTPUT_THRESHOLD_RATIO = 0.6

    # 消息过期时间（秒）- 超过此时间的消息可被修剪
    MESSAGE_EXPIRY_SECONDS = 1800  # 30分钟

    # 最小保留消息数
    MIN_MESSAGES_KEEP = 5

    # 最大保留消息数
    MAX_MESSAGES_KEEP = 50

    # 修剪策略
    PRUNE_STRATEGY = "token_based"  # token_based, count_based, time_based


@dataclass
class MessageMetrics:
    """消息指标"""
    message_id: str
    token_count: int
    message_type: MessageType
    timestamp: float
    is_essential: bool = False  # 是否为关键消息（不修剪）
    is_compacted: bool = False   # 是否已压缩


@dataclass
class PruneResult:
    """修剪结果"""
    success: bool
    original_messages: List[AgentMessage]
    pruned_messages: List[AgentMessage]
    removed_count: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    pruned_message_ids: List[str] = field(default_factory=list)


class MessageClassifier:
    """消息分类器"""

    ESSENTIAL_ROLES = {"system", "user", "human"}
    TOOL_ROLES = {"tool", "function", "action"}
    THINKING_PATTERNS = ["thought", "thinking", "reasoning"]

    @classmethod
    def classify(cls, message: AgentMessage) -> MessageType:
        """分类消息类型"""
        role = message.role or ""
        content = message.content or ""

        # 检查是否为摘要消息
        if message.context and isinstance(message.context, dict) and message.context.get("is_compaction_summary"):
            return MessageType.SUMMARY

        # 检查是否为已过时消息
        if message.context and isinstance(message.context, dict) and message.context.get("compacted"):
            return MessageType.OBSOLETE

        # 根据角色分类
        if role in cls.ESSENTIAL_ROLES:
            return MessageType.SYSTEM if role == "system" else MessageType.USER

        if role in cls.TOOL_ROLES:
            return MessageType.TOOL_OUTPUT

        if role in ["assistant", "agent"]:
            # 检查是否为思考过程
            content_lower = content.lower()
            if any(pattern in content_lower for pattern in cls.THINKING_PATTERNS):
                return MessageType.THINKING
            return MessageType.ASSISTANT

        return MessageType.TOOL_OUTPUT

    @classmethod
    def is_essential(cls, message: AgentMessage) -> bool:
        """判断消息是否为关键消息（不应被修剪）"""
        role = message.role or ""

        # 系统消息和用户消息始终保留
        if role in cls.ESSENTIAL_ROLES:
            return True

        # 包含关键信息的消息
        if message.context and isinstance(message.context, dict):
            if message.context.get("is_critical"):
                return True
            if message.context.get("is_compaction_summary"):
                return True
            # Skill 内容需要保护，不被修剪
            if message.context.get("is_skill_content"):
                return True

        return False


class TokenEstimator:
    """简单的 Token 估算器"""

    def __init__(self, chars_per_token: int = 4):
        self.chars_per_token = chars_per_token

    def estimate(self, text: str) -> int:
        """估算文本的 token 数量"""
        if not text:
            return 0
        return len(text) // self.chars_per_token

    def estimate_message(self, message: AgentMessage) -> int:
        """估算消息的 token 数量"""
        content_tokens = self.estimate(message.content or "")

        # 考虑 action_report
        if message.action_report:
            for action in message.action_report:
                if isinstance(action, ActionOutput):
                    content_tokens += self.estimate(action.content or "")

        return max(content_tokens, 1)  # 至少 1 个 token


class HistoryPruner:
    """
    历史记录修剪器

    定期清理旧的工具调用输出，当累积 Token 数超过阈值时，
    将更早的工具输出标记为已压缩。
    """

    def __init__(
        self,
        prune_protect: int = PruneConfig.DEFAULT_PRUNE_PROTECT,
        min_messages_keep: int = PruneConfig.MIN_MESSAGES_KEEP,
        max_messages_keep: int = PruneConfig.MAX_MESSAGES_KEEP,
        message_expiry_seconds: float = PruneConfig.MESSAGE_EXPIRY_SECONDS,
        strategy: str = PruneConfig.PRUNE_STRATEGY,
    ):
        """
        初始化历史记录修剪器

        Args:
            prune_protect: 触发修剪的 Token 阈值
            min_messages_keep: 最小保留消息数
            max_messages_keep: 最大保留消息数
            message_expiry_seconds: 消息过期时间（秒）
            strategy: 修剪策略
        """
        self.prune_protect = prune_protect
        self.min_messages_keep = min_messages_keep
        self.max_messages_keep = max_messages_keep
        self.message_expiry_seconds = message_expiry_seconds
        self.strategy = strategy
        self.token_estimator = TokenEstimator()
        self._prune_history: List[PruneResult] = []

    def _calculate_metrics(self, messages: List[AgentMessage]) -> List[MessageMetrics]:
        """计算所有消息的指标"""
        import time
        current_time = time.time()

        metrics = []
        for msg in messages:
            msg_type = MessageClassifier.classify(msg)
            is_essential = MessageClassifier.is_essential(msg)

            # 计算消息年龄
            msg_time = msg.timestamp if hasattr(msg, 'timestamp') and msg.timestamp else current_time
            if isinstance(msg_time, datetime):
                msg_time = msg_time.timestamp()

            metrics.append(MessageMetrics(
                message_id=msg.message_id or str(id(msg)),
                token_count=self.token_estimator.estimate_message(msg),
                message_type=msg_type,
                timestamp=msg_time,
                is_essential=is_essential,
                is_compacted=msg.context.get("compacted", False) if isinstance(msg.context, dict) else False,
            ))

        return metrics

    def _get_prunable_indices(
        self,
        messages: List[AgentMessage],
        metrics: List[MessageMetrics],
    ) -> List[int]:
        """
        获取可修剪消息的索引列表

        策略：从后向前遍历，保留最新的 min_messages_keep 条消息，
        然后当累积 Token 超过阈值时，修剪更早的工具输出。
        """
        if len(messages) <= self.min_messages_keep:
            return []

        prunable = []
        total_tokens = sum(m.token_count for m in metrics)

        # 如果总 Token 数未超过阈值，可能不需要修剪
        if total_tokens <= self.prune_protect:
            # 但仍然检查消息数量限制
            if len(messages) <= self.max_messages_keep:
                return []

        # 从后向前遍历（除了最后 min_messages_keep 条必须保留的）
        cumulative_tokens = 0
        for i in range(len(messages) - 1, self.min_messages_keep - 1, -1):
            metric = metrics[i]

            # 关键消息不修剪
            if metric.is_essential:
                cumulative_tokens += metric.token_count
                continue

            # 已压缩的消息跳过
            if metric.is_compacted:
                continue

            cumulative_tokens += metric.token_count

            # 当累积 Token 超过阈值时，标记更早的消息为可修剪
            if cumulative_tokens > self.prune_protect:
                # 检查消息类型 - 优先修剪工具输出和思考过程
                if metric.message_type in [MessageType.TOOL_OUTPUT, MessageType.THINKING]:
                    prunable.append(i)
                # 如果消息数量超过限制，也修剪普通消息
                elif len(messages) - len(prunable) > self.max_messages_keep:
                    if metric.message_type == MessageType.ASSISTANT:
                        prunable.append(i)

        return prunable

    def _mark_compacted(self, message: AgentMessage) -> AgentMessage:
        """将消息标记为已压缩"""
        if message.context is None or not isinstance(message.context, dict):
            message.context = {}

        message.context["compacted"] = True
        message.context["compacted_at"] = datetime.now().isoformat()

        # 保留内容摘要
        original_content = message.content or ""
        if len(original_content) > 100:
            summary = original_content[:100] + "..."
        else:
            summary = original_content

        message.context["original_summary"] = summary

        # 替换内容为占位符
        message.content = f"[内容已压缩: {MessageClassifier.classify(message).value}] {summary}"

        return message

    def prune(self, messages: List[AgentMessage]) -> PruneResult:
        """
        执行历史记录修剪

        Args:
            messages: 当前消息列表

        Returns:
            PruneResult: 修剪结果
        """
        if not messages:
            return PruneResult(
                success=True,
                original_messages=[],
                pruned_messages=[],
            )

        # 计算消息指标
        metrics = self._calculate_metrics(messages)
        total_tokens = sum(m.token_count for m in metrics)

        # 检查是否需要修剪
        need_prune = (
            total_tokens > self.prune_protect or
            len(messages) > self.max_messages_keep
        )

        if not need_prune:
            return PruneResult(
                success=True,
                original_messages=messages,
                pruned_messages=messages,
                tokens_before=total_tokens,
                tokens_after=total_tokens,
            )

        logger.info(
            f"Pruning history: {len(messages)} messages, "
            f"~{total_tokens} tokens, threshold {self.prune_protect}"
        )

        # 获取可修剪的索引
        prunable_indices = self._get_prunable_indices(messages, metrics)

        if not prunable_indices:
            logger.info("No messages eligible for pruning")
            return PruneResult(
                success=True,
                original_messages=messages,
                pruned_messages=messages,
                tokens_before=total_tokens,
                tokens_after=total_tokens,
            )

        # 执行修剪
        pruned_messages = []
        pruned_ids = []

        for i, msg in enumerate(messages):
            if i in prunable_indices:
                # 标记为已压缩
                compacted_msg = self._mark_compacted(msg)
                pruned_messages.append(compacted_msg)
                pruned_ids.append(msg.message_id or str(id(msg)))
            else:
                pruned_messages.append(msg)

        # 计算修剪后的 Token 数
        new_metrics = self._calculate_metrics(pruned_messages)
        tokens_after = sum(m.token_count for m in new_metrics)

        result = PruneResult(
            success=True,
            original_messages=messages,
            pruned_messages=pruned_messages,
            removed_count=len(prunable_indices),
            tokens_before=total_tokens,
            tokens_after=tokens_after,
            tokens_saved=total_tokens - tokens_after,
            pruned_message_ids=pruned_ids,
        )

        self._prune_history.append(result)

        logger.info(
            f"Pruning completed: marked {result.removed_count} messages as compacted, "
            f"saved ~{result.tokens_saved} tokens"
        )

        return result

    def prune_action_outputs(
        self,
        action_outputs: List[ActionOutput],
        max_total_length: int = 10000,
    ) -> List[ActionOutput]:
        """
        修剪 ActionOutput 列表

        Args:
            action_outputs: ActionOutput 列表
            max_total_length: 最大总长度

        Returns:
            List[ActionOutput]: 修剪后的列表
        """
        if not action_outputs:
            return []

        total_length = sum(len(str(a.content)) for a in action_outputs)

        if total_length <= max_total_length:
            return action_outputs

        # 保留最新的结果
        pruned = []
        current_length = 0

        for action in reversed(action_outputs):
            content_length = len(str(action.content))

            if current_length + content_length <= max_total_length or not pruned:
                pruned.insert(0, action)
                current_length += content_length
            else:
                # 创建压缩版本
                summary = str(action.content)[:100] + "... [内容已压缩]"
                compacted_action = ActionOutput(
                    action_id=action.action_id,
                    name=action.name,
                    content=summary,
                    view=action.view,
                    is_exe_success=action.is_exe_success,
                )
                compacted_action.extra = {
                    **(action.extra or {}),
                    "compacted": True,
                }
                pruned.insert(0, compacted_action)

        return pruned

    def get_prune_history(self) -> List[PruneResult]:
        """获取修剪历史"""
        return self._prune_history.copy()

    def get_stats(self) -> Dict[str, Any]:
        """获取修剪统计"""
        if not self._prune_history:
            return {
                "total_prunes": 0,
                "total_messages_pruned": 0,
                "total_tokens_saved": 0,
            }

        return {
            "total_prunes": len(self._prune_history),
            "total_messages_pruned": sum(r.removed_count for r in self._prune_history),
            "total_tokens_saved": sum(r.tokens_saved for r in self._prune_history),
            "prune_threshold": self.prune_protect,
            "max_messages_keep": self.max_messages_keep,
        }


# 便捷函数
def prune_messages(
    messages: List[AgentMessage],
    prune_protect: int = PruneConfig.DEFAULT_PRUNE_PROTECT,
) -> PruneResult:
    """
    便捷函数：修剪消息列表

    Args:
        messages: 消息列表
        prune_protect: Token 阈值

    Returns:
        PruneResult: 修剪结果
    """
    pruner = HistoryPruner(prune_protect=prune_protect)
    return pruner.prune(messages)
