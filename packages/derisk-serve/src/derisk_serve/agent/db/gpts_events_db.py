"""Tier 3.1: 事件日志数据库模型和 DAO（加法版本，与 gpts_message/gpts_work_log 共存）。

每个 think/act/tool_call 都作为 event 追加到这里，提供可重放的会话状态视图。
本表只追加（append-only），不修改已有行，确保事件流完整性。

设计原则：
- 与 gpts_message/gpts_work_log 共存，不替代（additive，向后兼容）
- 当前 PR 只做存储 + 查询，不做 replay（replay 是未来 PR）
- emit_event 是 fire-and-forget，失败只 log warning，不影响主流程
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    select,
)

from derisk.storage.metadata import BaseDao, Model


class GptsEventEntity(Model):
    """事件日志实体：每个 think/act/tool_call 作为一个 event 追加。"""

    __tablename__ = "gpts_events"
    __table_args__ = (
        Index("idx_events_conv_seq", "conv_id", "sequence"),
        Index("idx_events_message", "message_id"),
    )

    id = Column(Integer, primary_key=True, comment="autoincrement id")

    conv_id = Column(
        String(255), nullable=False, comment="The conversation id"
    )
    message_id = Column(
        String(255), nullable=True, comment="The message id this event belongs to"
    )
    sequence = Column(
        Integer, nullable=False, default=0, comment="Per-conv monotonic sequence number"
    )
    event_type = Column(
        String(64), nullable=False,
        comment="Event type: think_start, think_end, act_start, act_end, tool_call_start, tool_call_end, etc.",
    )
    event_data = Column(
        Text(length=2**31 - 1), nullable=True,
        comment="JSON event payload (tool_name, args, result, etc.)",
    )

    created_at = Column(
        DateTime, name="gmt_create", default=datetime.utcnow, comment="create time"
    )


class EventLogDao(BaseDao):
    """事件日志 DAO：append-only 写入 + 顺序读取。"""

    def append_event(
        self,
        conv_id: str,
        event_type: str,
        message_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """追加一个事件。自动分配 sequence（per-conv 单调递增）。

        Returns:
            插入的 event id；失败返回 None。
        """
        import json

        if not conv_id or not event_type:
            return None

        session = self.get_raw_session()
        try:
            # 分配 sequence：查当前 conv 最大 sequence + 1
            max_seq = (
                session.query(GptsEventEntity.sequence)
                .filter(GptsEventEntity.conv_id == conv_id)
                .order_by(GptsEventEntity.sequence.desc())
                .first()
            )
            next_seq = (max_seq[0] + 1) if max_seq else 1

            entity = GptsEventEntity(
                conv_id=conv_id,
                message_id=message_id,
                sequence=next_seq,
                event_type=event_type,
                event_data=json.dumps(event_data, ensure_ascii=False) if event_data else None,
            )
            session.add(entity)
            session.commit()
            return entity.id
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def get_events(
        self, conv_id: str, since_sequence: int = 0, limit: int = 1000
    ) -> List[GptsEventEntity]:
        """按 sequence 顺序读取 conv 的事件。"""
        session = self.get_raw_session()
        try:
            q = (
                session.query(GptsEventEntity)
                .filter(
                    GptsEventEntity.conv_id == conv_id,
                    GptsEventEntity.sequence > since_sequence,
                )
                .order_by(GptsEventEntity.sequence.asc())
                .limit(limit)
            )
            return q.all()
        finally:
            session.close()

    def get_events_by_message(self, message_id: str) -> List[GptsEventEntity]:
        """读取某个 message 的所有事件。"""
        session = self.get_raw_session()
        try:
            return (
                session.query(GptsEventEntity)
                .filter(GptsEventEntity.message_id == message_id)
                .order_by(GptsEventEntity.sequence.asc())
                .all()
            )
        finally:
            session.close()

    def get_latest_sequence(self, conv_id: str) -> int:
        """读取 conv 的最新 sequence（用于断点续传）。无事件返回 0。"""
        session = self.get_raw_session()
        try:
            row = (
                session.query(GptsEventEntity.sequence)
                .filter(GptsEventEntity.conv_id == conv_id)
                .order_by(GptsEventEntity.sequence.desc())
                .first()
            )
            return row[0] if row else 0
        finally:
            session.close()
