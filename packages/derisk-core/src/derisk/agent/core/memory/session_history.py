"""
Session History Manager - 第四层压缩管理器

管理一个 conv_session_id 下的所有对话历史,实现跨对话的上下文继承。
支持三层存储: Hot(完全保留) / Warm(压缩摘要) / Cold(归档淘汰)

与现有三层压缩的关系:
- Layer 1 (Truncation): 处理工具输出截断
- Layer 2 (Pruning): 处理历史消息剪枝
- Layer 3 (Compaction): 处理会话压缩和归档
- Layer 4 (Session History): 管理跨对话的历史上下文 (本模块)
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型
# =============================================================================


@dataclass
class SessionConversation:
    """
    一次完整的对话单元 (对应一个 agent_conv_id)

    包含用户提问、Agent 回答、执行细节,以及压缩后的摘要信息。
    """

    conv_id: str  # agent_conv_id, 如 "session_123_1"
    session_id: str  # conv_session_id, 如 "session_123"

    # 时间戳
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    # 对话内容
    user_query: str = ""  # 用户原始提问
    final_answer: Optional[str] = None  # Agent 最终回答

    # 执行链 (完整细节,用于热数据区)
    message_chain: List[Any] = field(
        default_factory=list
    )  # GptsMessage 或 AgentMessage
    work_entries: List[Any] = field(default_factory=list)  # WorkEntry 列表
    action_reports: List[Any] = field(default_factory=list)  # ActionOutput 列表

    # 元数据
    total_tokens: int = 0
    total_rounds: int = 0
    success: bool = True

    # 摘要 (当进入温数据区时生成)
    summary: Optional[str] = None
    key_takeaways: List[str] = field(default_factory=list)  # 关键结论

    # 状态
    status: str = "active"  # active, compressed, archived

    # 纯模型输出标记
    has_tool_calls: bool = False  # 是否包含工具调用
    pure_model_output: Optional[str] = None  # 纯模型输出(无工具调用时)

    def to_dict(self) -> Dict:
        """序列化"""
        return {
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "user_query": self.user_query,
            "final_answer": self.final_answer,
            "total_tokens": self.total_tokens,
            "total_rounds": self.total_rounds,
            "success": self.success,
            "summary": self.summary,
            "key_takeaways": self.key_takeaways,
            "status": self.status,
            "has_tool_calls": self.has_tool_calls,
            "pure_model_output": self.pure_model_output,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SessionConversation":
        return cls(**data)


@dataclass
class SessionHistoryConfig:
    """Session History Manager 配置"""

    # 热数据区: 保留完整细节的对话数量
    hot_retention_count: int = 3  # 保留最近 3 次对话的完整细节

    # 温数据区: 保留摘要的对话数量
    warm_retention_count: int = 5  # 再保留 5 次摘要

    # 冷数据区: 归档后的保留策略
    cold_retention_days: int = 30  # 归档保留 30 天

    # Token 限制
    max_hot_tokens: int = 6000  # 热数据区最大 token 数
    max_warm_tokens: int = 3000  # 温数据区最大 token 数

    # 摘要生成配置
    summary_model: str = "aistudio/DeepSeek-V3"
    summary_max_length: int = 500  # 摘要最大长度

    # 纯模型输出处理
    include_pure_model_outputs: bool = True  # 是否包含纯模型输出到历史
    pure_model_max_length: int = 1000  # 纯模型输出最大长度


# =============================================================================
# Session History Manager
# =============================================================================


class SessionHistoryManager:
    """
    会话级历史管理器 (第四层压缩)

    职责:
    1. 管理一个 conv_session_id 下的所有 SessionConversation
    2. 实现分层存储策略: Hot(热) / Warm(温) / Cold(冷)
    3. 构建跨对话的历史上下文
    4. 处理纯模型输出(无工具调用)的记录和压缩

    与现有三层压缩的集成:
    - 在 generate_reply 开始时加载历史上下文
    - 在 generate_reply 结束时保存对话记录
    - 复用 Layer 3 的压缩逻辑生成摘要
    """

    def __init__(
        self,
        session_id: str,
        gpts_memory: Optional[Any] = None,
        config: Optional[SessionHistoryConfig] = None,
    ):
        self.session_id = session_id
        self.gpts_memory = gpts_memory
        self.config = config or SessionHistoryConfig()

        # 三层存储
        self.hot_conversations: OrderedDict[str, SessionConversation] = OrderedDict()
        self.warm_summaries: OrderedDict[str, SessionConversation] = OrderedDict()
        self.cold_archive_refs: Dict[str, str] = {}  # 归档引用

        # 统计
        self._total_tokens: int = 0

        # 纯模型输出缓存
        self._pure_model_outputs: List[str] = []

        logger.info(f"SessionHistoryManager initialized for session {session_id}")

    async def load_session_history(self):
        """
        从 GptsMemory 加载整个 session 的历史对话
        构建 SessionConversation 列表
        """
        if not self.gpts_memory:
            logger.warning("No GptsMemory available, using empty history")
            return

        try:
            # 1. 获取该 session 下的所有消息
            messages = await self.gpts_memory.get_session_messages(self.session_id)

            # 2. 按 conv_id 分组
            conv_messages: Dict[str, List[Any]] = {}
            for msg in messages:
                conv_id = getattr(msg, "conv_id", None)
                if conv_id:
                    conv_messages.setdefault(conv_id, []).append(msg)

            # 3. 构建 SessionConversation
            conversations = []
            for conv_id, msgs in conv_messages.items():
                conv = await self._build_session_conversation(conv_id, msgs)
                conversations.append(conv)

            # 4. 按时间排序,最近的在前面
            conversations.sort(key=lambda x: x.created_at, reverse=True)

            # 5. 分层加载
            for i, conv in enumerate(conversations):
                if i < self.config.hot_retention_count:
                    # 热数据: 加载完整细节
                    self.hot_conversations[conv.conv_id] = conv
                elif (
                    i
                    < self.config.hot_retention_count + self.config.warm_retention_count
                ):
                    # 温数据: 加载摘要
                    if conv.summary:
                        self.warm_summaries[conv.conv_id] = conv
                else:
                    # 冷数据: 只保留引用
                    self.cold_archive_refs[conv.conv_id] = conv.conv_id

            logger.info(
                f"SessionHistory loaded: {len(self.hot_conversations)} hot, "
                f"{len(self.warm_summaries)} warm, {len(self.cold_archive_refs)} cold"
            )

        except Exception as e:
            logger.error(f"Failed to load session history: {e}")

    async def _build_session_conversation(
        self,
        conv_id: str,
        messages: List[Any],
    ) -> SessionConversation:
        """
        从消息列表构建 SessionConversation

        关键: 处理纯模型输出(无工具调用)
        """
        conv = SessionConversation(
            conv_id=conv_id,
            session_id=self.session_id,
        )

        # 提取用户查询
        for msg in messages:
            role = getattr(msg, "role", "")
            if role in ("user", "human"):
                conv.user_query = getattr(msg, "content", "")[:200]
                break

        # 检查是否有工具调用
        has_tool_calls = False
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                has_tool_calls = True
                break
            # 检查 context 或 metadata
            context = getattr(msg, "context", None)
            if isinstance(context, dict) and context.get("tool_calls"):
                has_tool_calls = True
                break
            metadata = getattr(msg, "metadata", None)
            if isinstance(metadata, dict) and metadata.get("tool_calls"):
                has_tool_calls = True
                break

        conv.has_tool_calls = has_tool_calls

        # 如果没有工具调用,提取纯模型输出
        if not has_tool_calls:
            for msg in messages:
                role = getattr(msg, "role", "")
                if role in ("assistant", "agent"):
                    content = getattr(msg, "content", "")
                    conv.pure_model_output = content[
                        : self.config.pure_model_max_length
                    ]
                    conv.final_answer = content
                    break

        # 保存消息链
        conv.message_chain = messages
        conv.total_rounds = len(messages)

        return conv

    async def on_conversation_complete(
        self,
        conv_id: str,
        messages: Optional[List[Any]] = None,
    ):
        """
        当一次对话完成时,将其加入历史管理

        关键: 自动检测纯模型输出并处理
        """
        if messages:
            conv = await self._build_session_conversation(conv_id, messages)
        elif self.gpts_memory:
            msgs = await self.gpts_memory.get_messages(conv_id)
            conv = await self._build_session_conversation(conv_id, msgs)
        else:
            logger.warning(f"No messages available for conv {conv_id}")
            return

        # 如果是纯模型输出,记录到缓存
        if not conv.has_tool_calls and conv.pure_model_output:
            self._pure_model_outputs.append(conv.pure_model_output)
            logger.info(f"Recorded pure model output for conv {conv_id}")

        # 加入热数据区 (最新)
        self.hot_conversations[conv_id] = conv
        self.hot_conversations.move_to_end(conv_id, last=False)

        # 检查是否需要压缩
        await self._check_and_compress()

    async def _check_and_compress(self):
        """
        检查并执行压缩
        当热数据区超过阈值时,将最老的对话移入温数据区
        """
        if len(self.hot_conversations) <= self.config.hot_retention_count:
            return

        # 需要压缩的数量
        overflow = len(self.hot_conversations) - self.config.hot_retention_count

        for _ in range(overflow):
            # 取出最老的对话
            oldest_conv_id, oldest_conv = self.hot_conversations.popitem(last=True)

            # 生成摘要
            await self._generate_summary(oldest_conv)

            # 移入温数据区
            self.warm_summaries[oldest_conv_id] = oldest_conv

            logger.info(f"Compressed conversation {oldest_conv_id} into warm layer")

        # 检查温数据区是否也需要清理
        await self._check_warm_archive()

    async def _generate_summary(self, conv: SessionConversation):
        """
        生成对话摘要

        复用 Layer 3 (Compaction) 的逻辑
        """
        if not conv.message_chain:
            return

        # 使用简单的规则生成摘要
        summary_parts = []

        summary_parts.append(f"用户问题: {conv.user_query}")

        if conv.has_tool_calls:
            # 有工具调用: 提取关键工具
            tools_used = []
            for msg in conv.message_chain:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if isinstance(tc, dict):
                            func = tc.get("function", {})
                            tool_name = func.get("name", "unknown")
                            tools_used.append(tool_name)

            if tools_used:
                summary_parts.append(f"使用工具: {', '.join(set(tools_used))}")
        else:
            # 纯模型输出
            if conv.pure_model_output:
                summary_parts.append(f"模型回答: {conv.pure_model_output[:200]}...")

        if conv.final_answer:
            summary_parts.append(f"最终回答: {conv.final_answer[:200]}...")

        conv.summary = "\n".join(summary_parts)
        conv.status = "compressed"

    async def _check_warm_archive(self):
        """检查温数据区是否需要归档"""
        if len(self.warm_summaries) <= self.config.warm_retention_count:
            return

        overflow = len(self.warm_summaries) - self.config.warm_retention_count

        for _ in range(overflow):
            oldest_conv_id, oldest_conv = self.warm_summaries.popitem(last=True)

            # 归档到文件系统 (如果有 GptsMemory)
            if self.gpts_memory:
                # TODO: 实现归档到 AgentFileSystem
                pass

            self.cold_archive_refs[oldest_conv_id] = oldest_conv_id
            logger.info(f"Archived conversation {oldest_conv_id} into cold layer")

    async def build_history_context(
        self,
        current_conv_id: Optional[str] = None,
        max_tokens: int = 8000,
    ) -> List[Dict[str, Any]]:
        """
        构建用于 LLM 的历史上下文

        策略:
        1. 优先包含热数据区的完整对话
        2. 如果 token 充足,包含温数据区的摘要
        3. 完全不包含冷数据(或只包含一句话提示)

        关键: 包含纯模型输出的历史记录
        """
        context: List[Dict[str, Any]] = []
        total_tokens = 0

        # 1. 添加纯模型输出历史 (如果有)
        if self.config.include_pure_model_outputs and self._pure_model_outputs:
            pure_outputs_text = "\n".join(
                [
                    f"- {output[:200]}..."
                    for output in self._pure_model_outputs[-3:]  # 最近3个
                ]
            )
            pure_outputs_msg = {
                "role": "system",
                "content": f"\n### 历史纯模型输出\n{pure_outputs_text}\n",
            }
            context.append(pure_outputs_msg)
            total_tokens += len(pure_outputs_text) // 4

        # 2. 添加热数据区的完整对话 (按时间倒序)
        for conv_id, conv in reversed(self.hot_conversations.items()):
            if conv_id == current_conv_id:
                continue  # 跳过当前对话

            conv_context = await self._format_conversation_full(conv)
            conv_tokens = len(str(conv_context)) // 4

            if total_tokens + conv_tokens > max_tokens * 0.7:
                break

            context.extend(conv_context)
            total_tokens += conv_tokens

        # 3. 添加温数据区的摘要
        remaining_tokens = max_tokens - total_tokens
        for conv_id, conv in self.warm_summaries.items():
            summary_context = self._format_conversation_summary(conv)
            summary_tokens = len(str(summary_context)) // 4

            if summary_tokens > remaining_tokens:
                break

            context.extend(summary_context)
            total_tokens += summary_tokens

        logger.info(
            f"Built history context: {len(context)} messages, ~{total_tokens} tokens"
        )

        return context

    async def _format_conversation_full(
        self,
        conv: SessionConversation,
    ) -> List[Dict[str, Any]]:
        """格式化完整对话为 LLM 消息格式"""
        messages = []

        # 添加分隔标记
        header = (
            f"\n\n=== 历史对话 [{conv.conv_id}] ===\n"
            f"时间: {datetime.fromtimestamp(conv.created_at).strftime('%Y-%m-%d %H:%M')}\n"
            f"用户问题: {conv.user_query[:200]}\n"
        )

        if not conv.has_tool_calls:
            header += f"(纯模型输出)\n"

        messages.append(
            {
                "role": "system",
                "content": header,
            }
        )

        # 添加消息链 (精简版)
        for msg in conv.message_chain:
            role = getattr(msg, "role", "unknown")
            content = getattr(msg, "content", "")

            # 跳过太长的内容
            if len(content) > 1000:
                content = content[:1000] + "... [truncated]"

            messages.append(
                {
                    "role": role
                    if role not in ("ai", "human")
                    else ("assistant" if role == "ai" else "user"),
                    "content": content,
                }
            )

        return messages

    def _format_conversation_summary(
        self,
        conv: SessionConversation,
    ) -> List[Dict[str, Any]]:
        """格式化对话摘要"""
        messages = []

        summary_lines = [
            f"\n### 历史对话摘要 [{conv.conv_id}]",
            f"时间: {datetime.fromtimestamp(conv.created_at).strftime('%Y-%m-%d %H:%M')}",
            f"用户问题: {conv.user_query[:150]}...",
        ]

        if not conv.has_tool_calls:
            summary_lines.append("类型: 纯模型输出")

        if conv.summary:
            summary_lines.append(f"摘要: {conv.summary}")

        if conv.key_takeaways:
            summary_lines.append("关键结论:")
            for takeaway in conv.key_takeaways[:3]:
                summary_lines.append(f"  - {takeaway}")

        messages.append(
            {
                "role": "system",
                "content": "\n".join(summary_lines),
            }
        )

        return messages

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "session_id": self.session_id,
            "hot_count": len(self.hot_conversations),
            "warm_count": len(self.warm_summaries),
            "cold_count": len(self.cold_archive_refs),
            "pure_model_outputs_count": len(self._pure_model_outputs),
            "total_tokens": self._total_tokens,
        }
