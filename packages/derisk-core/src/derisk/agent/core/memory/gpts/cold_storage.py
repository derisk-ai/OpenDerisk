"""
ColdStorage - Cold 层压缩数据存储

职责：
1. 持久化 Cold 层的压缩摘要
2. 对话恢复时加载 Cold 摘要（不加载原始数据）
3. 与 HistoryMessageBuilder 协作：Cold 数据从这里读取

压缩模型：
─────────────────────────────────────────────────────────────────
Cold层是高度压缩的对话摘要：
- 只保留 user + assistant 两种角色
- 不保留 tool_call_id（Cold层不需要）
- N个tool调用压缩为摘要中的一句话

压缩是增量的：
- 第一次压缩：msg_1~msg_20 → 摘要1
- 第二次压缩：摘要1 + msg_21~msg_40 → 摘要2（替代摘要1）
- Message List: user + ai(摘要2) + 新消息...

─────────────────────────────────────────────────────────────────
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class ColdSummaryMessage:
    """
    压缩后的单条消息（Cold层）

    只有两种角色：user / assistant
    不保留 tool_call_id
    """

    role: str  # user / assistant
    content: str  # 压缩后的摘要内容

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
        }

    def to_llm_message(self) -> Dict[str, Any]:
        """转换为 LLM 消息格式"""
        prefix = "[历史对话] " if self.role == "user" else "[历史摘要] "
        return {
            "role": self.role,
            "content": prefix + self.content,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColdSummaryMessage":
        return cls(
            role=data.get("role", "assistant"),
            content=data.get("content", ""),
        )


@dataclass
class ColdSegment:
    """
    Cold层压缩片段

    代表一次压缩的结果，包含：
    - 压缩范围（round_start ~ round_end）
    - 压缩后的摘要（summary）
    - 统计信息

    压缩是增量的：
    - segment_index 递增
    - 新摘要可能包含旧摘要的内容
    """

    segment_id: Optional[int] = None
    conv_id: str = ""
    session_id: str = ""
    segment_index: int = 0

    round_start: int = 0
    round_end: int = 0
    message_count: int = 0
    entry_count: int = 0

    summary: List[ColdSummaryMessage] = field(default_factory=list)

    original_tokens: int = 0
    compressed_tokens: int = 0

    source_segment_ids: List[int] = field(default_factory=list)
    source_message_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "segment_index": self.segment_index,
            "round_start": self.round_start,
            "round_end": self.round_end,
            "message_count": self.message_count,
            "entry_count": self.entry_count,
            "summary": json.dumps([s.to_dict() for s in self.summary]),
            "source_message_ids": json.dumps(self.source_message_ids)
            if self.source_message_ids
            else None,
            "source_segment_ids": json.dumps(self.source_segment_ids)
            if self.source_segment_ids
            else None,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColdSegment":
        summary_data = data.get("summary", "[]")
        if isinstance(summary_data, str):
            summary_list = json.loads(summary_data)
        else:
            summary_list = summary_data

        source_message_ids_data = data.get("source_message_ids", [])
        if isinstance(source_message_ids_data, str):
            source_message_ids = (
                json.loads(source_message_ids_data) if source_message_ids_data else []
            )
        else:
            source_message_ids = source_message_ids_data or []

        source_segment_ids_data = data.get("source_segment_ids", [])
        if isinstance(source_segment_ids_data, str):
            source_segment_ids = (
                json.loads(source_segment_ids_data) if source_segment_ids_data else []
            )
        else:
            source_segment_ids = source_segment_ids_data or []

        segment = cls(
            segment_id=data.get("segment_id"),
            conv_id=data.get("conv_id", ""),
            session_id=data.get("session_id", ""),
            segment_index=data.get("segment_index", 0),
            round_start=data.get("round_start", 0),
            round_end=data.get("round_end", 0),
            message_count=data.get("message_count", 0),
            entry_count=data.get("entry_count", 0),
            original_tokens=data.get("original_tokens", 0),
            compressed_tokens=data.get("compressed_tokens", 0),
            source_message_ids=source_message_ids,
            source_segment_ids=source_segment_ids,
        )

        for item in summary_list:
            segment.summary.append(ColdSummaryMessage.from_dict(item))

        return segment

    def to_llm_messages(self) -> List[Dict[str, Any]]:
        """转换为 LLM 消息列表"""
        return [m.to_llm_message() for m in self.summary]

    def get_user_summary(self) -> str:
        """获取用户问题摘要"""
        for m in self.summary:
            if m.role == "user":
                return m.content
        return ""

    def get_assistant_summary(self) -> str:
        """获取AI回答摘要"""
        for m in self.summary:
            if m.role == "assistant":
                return m.content
        return ""


@dataclass
class ColdConversationSummary:
    """
    单个对话的 Cold 层摘要（兼容旧版本）
    """

    conv_id: str
    session_id: str
    question_summary: str = ""
    answer_summary: str = ""
    tool_calls_summary: List[str] = field(default_factory=list)
    message_count: int = 0
    entry_count: int = 0
    original_tokens: int = 0
    compressed_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conv_id": self.conv_id,
            "session_id": self.session_id,
            "question_summary": self.question_summary,
            "answer_summary": self.answer_summary,
            "tool_calls_summary": self.tool_calls_summary,
            "message_count": self.message_count,
            "entry_count": self.entry_count,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColdConversationSummary":
        return cls(
            conv_id=data["conv_id"],
            session_id=data["session_id"],
            question_summary=data.get("question_summary", ""),
            answer_summary=data.get("answer_summary", ""),
            tool_calls_summary=data.get("tool_calls_summary", []),
            message_count=data.get("message_count", 0),
            entry_count=data.get("entry_count", 0),
            original_tokens=data.get("original_tokens", 0),
            compressed_tokens=data.get("compressed_tokens", 0),
        )


@dataclass
class ColdLayerData:
    """Cold 层数据（用于 LLM 上下文构建）"""

    session_id: str
    segments: List[ColdSegment] = field(default_factory=list)
    summaries: List[ColdConversationSummary] = field(default_factory=list)
    total_tokens: int = 0

    def to_llm_messages(self) -> List[Dict[str, Any]]:
        """转换为 LLM 消息格式"""
        messages = []

        for segment in self.segments:
            messages.extend(segment.to_llm_messages())

        if not self.segments:
            for summary in self.summaries:
                if summary.question_summary:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[历史对话] {summary.question_summary}",
                        }
                    )

                content_parts = []
                if summary.answer_summary:
                    content_parts.append(summary.answer_summary)
                if summary.tool_calls_summary:
                    content_parts.append(
                        f"工具: {', '.join(summary.tool_calls_summary)}"
                    )

                if content_parts:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": f"[历史摘要] {' '.join(content_parts)}",
                        }
                    )

        return messages


class ColdStorage:
    """Cold 层数据存储"""

    def __init__(
        self,
        db_storage: Optional[Any] = None,
        file_storage: Optional[Any] = None,
    ):
        self._db_storage = db_storage
        self._file_storage = file_storage

        self._segments: Dict[str, List[ColdSegment]] = {}
        self._summaries: Dict[str, ColdConversationSummary] = {}
        self._session_index: Dict[str, List[str]] = {}

    async def save_segment(self, segment: ColdSegment) -> bool:
        """保存压缩片段

        先构建新列表再原子替换，避免中途崩溃导致数据丢失
        """
        if segment.conv_id not in self._segments:
            self._segments[segment.conv_id] = []

        new_segments = [
            s
            for s in self._segments[segment.conv_id]
            if s.segment_index != segment.segment_index
        ]
        new_segments.append(segment)
        new_segments.sort(key=lambda s: s.segment_index)
        self._segments[segment.conv_id] = new_segments

        if segment.session_id not in self._session_index:
            self._session_index[segment.session_id] = []
        if segment.conv_id not in self._session_index[segment.session_id]:
            self._session_index[segment.session_id].append(segment.conv_id)

        return True

    async def save_summary(self, summary: ColdConversationSummary) -> bool:
        """保存摘要（兼容旧版本）"""
        self._summaries[summary.conv_id] = summary
        if summary.session_id not in self._session_index:
            self._session_index[summary.session_id] = []
        if summary.conv_id not in self._session_index[summary.session_id]:
            self._session_index[summary.session_id].append(summary.conv_id)
        return True

    async def get_segments(self, conv_id: str) -> List[ColdSegment]:
        """获取对话的所有压缩片段（按segment_index排序）"""
        segments = self._segments.get(conv_id, [])
        return sorted(segments, key=lambda s: s.segment_index)

    async def get_latest_segment(self, conv_id: str) -> Optional[ColdSegment]:
        """获取对话的最新压缩片段"""
        segments = await self.get_segments(conv_id)
        return segments[-1] if segments else None

    async def get_summary(self, conv_id: str) -> Optional[ColdConversationSummary]:
        """获取摘要（兼容旧版本）"""
        return self._summaries.get(conv_id)

    async def get_session_cold_data(
        self,
        session_id: str,
        exclude_conv_ids: Optional[List[str]] = None,
    ) -> ColdLayerData:
        """获取会话的 Cold 层数据"""
        exclude_set = set(exclude_conv_ids or [])

        segments = []
        summaries = []
        total_tokens = 0

        for conv_id in self._session_index.get(session_id, []):
            if conv_id in exclude_set:
                continue

            conv_segments = self._segments.get(conv_id, [])
            if conv_segments:
                latest = conv_segments[-1]
                segments.append(latest)
                total_tokens += latest.compressed_tokens
            else:
                summary = self._summaries.get(conv_id)
                if summary:
                    summaries.append(summary)
                    total_tokens += summary.compressed_tokens

        return ColdLayerData(
            session_id=session_id,
            segments=segments,
            summaries=summaries,
            total_tokens=total_tokens,
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_tokens = sum(
            s.compressed_tokens for segs in self._segments.values() for s in segs
        )

        conv_ids = set(self._summaries.keys()) | set(self._segments.keys())

        return {
            "cached_segments": sum(len(segs) for segs in self._segments.values()),
            "cached_summaries": len(self._summaries),
            "conversations": len(conv_ids),
            "sessions": len(self._session_index),
            "total_compressed_tokens": total_tokens,
        }
