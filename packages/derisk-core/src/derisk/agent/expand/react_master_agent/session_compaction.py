"""
上下文压缩 (SessionCompaction)

当一次 LLM 调用的总 Token 数超过模型上下文窗口的一定阈值时，
SessionCompaction 机制会被触发，对当前对话进行总结，生成浓缩的摘要。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Awaitable, Tuple
from enum import Enum

from derisk.agent import Agent, AgentMessage
from derisk.core import LLMClient, HumanMessage, SystemMessage, ModelMessage

logger = logging.getLogger(__name__)


class CompactionStrategy(Enum):
    """压缩策略"""
    SUMMARIZE = "summarize"         # 总结模式
    TRUNCATE_OLD = "truncate_old"   # 截断旧消息
    HYBRID = "hybrid"               # 混合模式


@dataclass
class CompactionConfig:
    """压缩配置"""
    # 默认上下文窗口大小（token）
    DEFAULT_CONTEXT_WINDOW = 128000

    # 触发压缩的阈值比例（可用上下文的 80%）
    DEFAULT_THRESHOLD_RATIO = 0.8

    # 压缩后保留的摘要消息数量
    SUMMARY_MESSAGES_TO_KEEP = 5

    # 最近消息保留数量（不压缩的最新消息）
    RECENT_MESSAGES_KEEP = 3

    # 估算 token 的字符比例（approximately 1 token ≈ 4 chars）
    CHARS_PER_TOKEN = 4

    # 压缩 Agent 的提示模板
    COMPACTION_PROMPT_TEMPLATE = """You are a session compaction assistant. Your task is to summarize the conversation history into a condensed format while preserving essential information.

Please summarize the following conversation history. Your summary should:
1. Capture the main goals and intents discussed
2. Preserve key decisions and conclusions reached
3. Maintain important context for continuing the task
4. Be concise but comprehensive
5. Include any critical values, results, or findings

Conversation History:
{history}

Please provide your summary in the following format:
<summary>
[Your detailed summary here]
</summary>

<key_points>
- Key point 1
- Key point 2
- ...
</key_points>

<remaining_tasks>
[If there are pending tasks, list them here]
</remaining_tasks>
"""


@dataclass
class TokenEstimate:
    """Token 估算结果"""
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    total_tokens: int
    usable_context: int


@dataclass
class CompactionResult:
    """压缩结果"""
    success: bool
    original_messages: List[AgentMessage]
    compacted_messages: List[AgentMessage]
    summary_content: Optional[str] = None
    tokens_saved: int = 0
    messages_removed: int = 0
    error_message: Optional[str] = None


@dataclass
class CompactionSummary:
    """压缩摘要消息"""
    content: str
    original_message_count: int
    timestamp: float = field(default_factory=lambda: __import__('time').time())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> AgentMessage:
        """转换为 AgentMessage"""
        formatted_content = f"""[Session Summary - Previous {self.original_message_count} messages compacted]

{self.content}

[End of Summary]"""
        msg = AgentMessage(
            content=formatted_content,
            role="system",
        )
        msg.context = {
            "is_compaction_summary": True,
            **self.metadata,
        }
        return msg


class TokenEstimator:
    """Token 估算器"""

    def __init__(self, chars_per_token: int = CompactionConfig.CHARS_PER_TOKEN):
        self.chars_per_token = chars_per_token

    def estimate(self, text: str) -> int:
        """估算文本的 token 数量"""
        if not text:
            return 0
        return len(text) // self.chars_per_token

    def estimate_messages(self, messages: List[Any]) -> TokenEstimate:
        """
        估算消息列表的 token 使用情况

        Args:
            messages: 消息列表 (AgentMessage 或 ModelMessage)

        Returns:
            TokenEstimate: Token 估算结果
        """
        input_tokens = 0
        cached_tokens = 0
        output_tokens = 0

        for msg in messages:
            if isinstance(msg, AgentMessage):
                content = msg.content or ""
                tokens = self.estimate(content)

                # 区分输入和输出
                if msg.role in ["user", "human"]:
                    input_tokens += tokens
                elif msg.role in ["assistant", "agent"]:
                    output_tokens += tokens
                else:
                    input_tokens += tokens

            elif isinstance(msg, ModelMessage):
                content = msg.content or ""
                tokens = self.estimate(content)
                input_tokens += tokens

            elif isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    tokens = self.estimate(content)
                    role = msg.get("role", "")
                    if role in ["assistant", "agent"]:
                        output_tokens += tokens
                    else:
                        input_tokens += tokens

        total_tokens = input_tokens + cached_tokens + output_tokens

        return TokenEstimate(
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            usable_context=0,  # 由调用者设置
        )


class SessionCompaction:
    """
    会话压缩器

    当 Token 使用超过阈值时，对历史消息进行压缩总结。
    """

    def __init__(
        self,
        context_window: int = CompactionConfig.DEFAULT_CONTEXT_WINDOW,
        threshold_ratio: float = CompactionConfig.DEFAULT_THRESHOLD_RATIO,
        recent_messages_keep: int = CompactionConfig.RECENT_MESSAGES_KEEP,
        llm_client: Optional[LLMClient] = None,
    ):
        """
        初始化会话压缩器

        Args:
            context_window: 模型的上下文窗口大小
            threshold_ratio: 触发压缩的阈值比例
            recent_messages_keep: 保留的最近消息数量
            llm_client: LLM 客户端，用于生成摘要
        """
        self.context_window = context_window
        self.threshold_ratio = threshold_ratio
        self.usable_context = int(context_window * threshold_ratio)
        self.recent_messages_keep = recent_messages_keep
        self.llm_client = llm_client
        self.token_estimator = TokenEstimator()
        self._compaction_history: List[CompactionResult] = []

    def set_llm_client(self, llm_client: LLMClient):
        """设置 LLM 客户端"""
        self.llm_client = llm_client

    def is_overflow(
        self,
        messages: List[AgentMessage],
        estimated_output_tokens: int = 500,
    ) -> Tuple[bool, TokenEstimate]:
        """
        判断是否需要进行上下文压缩

        Args:
            messages: 当前消息列表
            estimated_output_tokens: 预估的输出 token 数

        Returns:
            Tuple[bool, TokenEstimate]: (是否需要压缩, Token 估算结果)
        """
        estimate = self.token_estimator.estimate_messages(messages)
        estimate.output_tokens = estimated_output_tokens
        estimate.total_tokens = (
            estimate.input_tokens + estimate.cached_tokens + estimate.output_tokens
        )
        estimate.usable_context = self.usable_context

        is_overflowing = estimate.total_tokens > self.usable_context

        if is_overflowing:
            logger.info(
                f"Context overflow detected: {estimate.total_tokens} tokens "
                f"(threshold: {self.usable_context})"
            )

        return is_overflowing, estimate

    def _select_messages_to_compact(
        self,
        messages: List[AgentMessage],
    ) -> Tuple[List[AgentMessage], List[AgentMessage]]:
        """
        选择需要压缩的消息

        Returns:
            Tuple[List[AgentMessage], List[AgentMessage]]: (要压缩的消息, 保留的消息)
        """
        if len(messages) <= self.recent_messages_keep:
            return [], messages

        # 保留最近的消息
        to_keep = messages[-self.recent_messages_keep:]
        to_compact = messages[:-self.recent_messages_keep]

        return to_compact, to_keep

    def _format_messages_for_summary(self, messages: List[AgentMessage]) -> str:
        """将消息格式化为可总结的文本"""
        lines = []
        for msg in messages:
            role = msg.role or "unknown"
            content = msg.content or ""

            # 跳过系统消息和摘要消息
            if role in ["system"] or (isinstance(msg.context, dict) and msg.context.get("is_compaction_summary")):
                continue

            # 截断过长的内容
            if len(content) > 1000:
                content = content[:1000] + "... [truncated]"

            lines.append(f"[{role}]: {content}")

        return "\n\n".join(lines)

    async def _generate_summary(
        self,
        messages: List[AgentMessage],
    ) -> Optional[str]:
        """
        使用 LLM 生成消息摘要

        Args:
            messages: 要总结的消息

        Returns:
            Optional[str]: 生成的摘要内容
        """
        if not self.llm_client:
            # 没有 LLM 客户端时使用简单摘要
            return self._generate_simple_summary(messages)

        try:
            history_text = self._format_messages_for_summary(messages)

            prompt = CompactionConfig.COMPACTION_PROMPT_TEMPLATE.format(
                history=history_text
            )

            # 构建消息列表
            model_messages = [
                SystemMessage(content="You are a helpful assistant specialized in summarizing conversations."),
                HumanMessage(content=prompt),
            ]

            # 调用 LLM
            response = await self.llm_client.acompletion(model_messages)

            if response and response.choices:
                summary = response.choices[0].message.content
                return summary.strip()

            return None

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return self._generate_simple_summary(messages)

    def _generate_simple_summary(self, messages: List[AgentMessage]) -> str:
        """生成简单的摘要（当 LLM 不可用时使用）"""
        tool_calls = []
        user_inputs = []
        assistant_responses = []

        for msg in messages:
            role = msg.role or "unknown"
            content = msg.content or ""

            if "tool" in role or "action" in role:
                tool_calls.append(content[:100])
            elif role in ["user", "human"]:
                user_inputs.append(content[:200])
            elif role in ["assistant", "agent"]:
                assistant_responses.append(content[:200])

        summary_parts = []

        if user_inputs:
            summary_parts.append("User Queries:")
            for q in user_inputs[-3:]:  # 只保留最近3个
                summary_parts.append(f"  - {q[:100]}...")

        if tool_calls:
            summary_parts.append(f"\nTool Executions: {len(tool_calls)} tool calls made")

        if assistant_responses:
            summary_parts.append("\nKey Responses:")
            for r in assistant_responses[-2:]:
                summary_parts.append(f"  - {r[:150]}...")

        return "\n".join(summary_parts) if summary_parts else "Previous conversation history"

    async def compact(
        self,
        messages: List[AgentMessage],
        force: bool = False,
    ) -> CompactionResult:
        """
        执行上下文压缩

        Args:
            messages: 当前消息列表
            force: 是否强制压缩

        Returns:
            CompactionResult: 压缩结果
        """
        if not messages:
            return CompactionResult(
                success=True,
                original_messages=[],
                compacted_messages=[],
                tokens_saved=0,
                messages_removed=0,
            )

        # 检查是否需要压缩
        if not force:
            should_compact, estimate = self.is_overflow(messages)
            if not should_compact:
                return CompactionResult(
                    success=True,
                    original_messages=messages,
                    compacted_messages=messages,
                    tokens_saved=0,
                    messages_removed=0,
                )

        logger.info(f"Starting session compaction for {len(messages)} messages")

        # 选择要压缩的消息
        to_compact, to_keep = self._select_messages_to_compact(messages)

        if not to_compact:
            logger.info("No messages to compact")
            return CompactionResult(
                success=True,
                original_messages=messages,
                compacted_messages=messages,
                tokens_saved=0,
                messages_removed=0,
            )

        # 生成摘要
        summary_content = await self._generate_summary(to_compact)

        if not summary_content:
            return CompactionResult(
                success=False,
                original_messages=messages,
                compacted_messages=messages,
                error_message="Failed to generate summary",
            )

        # 创建摘要消息
        summary = CompactionSummary(
            content=summary_content,
            original_message_count=len(to_compact),
            metadata={
                "compacted_roles": list(set(m.role for m in to_compact)),
                "compaction_timestamp": logging.time.time() if hasattr(logging, 'time') else __import__('time').time(),
            },
        )

        # 构建新的消息列表
        compacted_messages = []

        # 保留系统消息
        system_messages = [m for m in to_compact if m.role == "system"]
        compacted_messages.extend(system_messages)

        # 添加摘要消息
        summary_msg = summary.to_message()
        compacted_messages.append(summary_msg)

        # 保留最近的消息
        compacted_messages.extend(to_keep)

        # 计算节省的 token
        original_tokens = self.token_estimator.estimate_messages(messages).total_tokens
        new_tokens = self.token_estimator.estimate_messages(compacted_messages).total_tokens
        tokens_saved = original_tokens - new_tokens

        result = CompactionResult(
            success=True,
            original_messages=messages,
            compacted_messages=compacted_messages,
            summary_content=summary_content,
            tokens_saved=tokens_saved,
            messages_removed=len(to_compact) - len(system_messages),
        )

        self._compaction_history.append(result)

        logger.info(
            f"Compaction completed: removed {result.messages_removed} messages, "
            f"saved ~{tokens_saved} tokens, "
            f"current message count: {len(compacted_messages)}"
        )

        return result

    def get_compaction_history(self) -> List[CompactionResult]:
        """获取压缩历史"""
        return self._compaction_history.copy()

    def clear_history(self):
        """清除压缩历史"""
        self._compaction_history.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取压缩统计信息"""
        if not self._compaction_history:
            return {
                "total_compactions": 0,
                "total_tokens_saved": 0,
                "total_messages_removed": 0,
            }

        return {
            "total_compactions": len(self._compaction_history),
            "total_tokens_saved": sum(r.tokens_saved for r in self._compaction_history),
            "total_messages_removed": sum(r.messages_removed for r in self._compaction_history),
            "context_window": self.context_window,
            "threshold_ratio": self.threshold_ratio,
        }
