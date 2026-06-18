"""Gpts ColdSegment 数据库模型和 DAO.

用于持久化 BAIZE ContextEngine 的"历史背景交接"(cold handoff)压缩摘要。

按 (session_id, content_hash) 唯一键存储 —— content_hash 是落入 cold 的全部
单元 id 的稳定指纹。中断恢复时按 content_hash 读回，**不重新调用模型**。
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)

from derisk.storage.metadata import BaseDao, Model


class GptsColdSegmentEntity(Model):
    """Gpts cold handoff 实体.

    存储一段被压缩为 handoff 的历史上下文摘要。
    """

    __tablename__ = "gpts_cold_segments"
    __table_args__ = (
        UniqueConstraint("session_id", "content_hash", name="uk_cold_session_hash"),
        Index("idx_cold_session", "session_id"),
    )

    id = Column(Integer, primary_key=True, comment="autoincrement id")

    session_id = Column(
        String(255), nullable=False, comment="The session id of the conversation"
    )
    conv_id = Column(
        String(255), nullable=False, comment="The conv id that produced this handoff"
    )
    content_hash = Column(
        String(64),
        nullable=False,
        comment="Stable fingerprint of cold unit ids (cache key)",
    )
    segment_index = Column(
        Integer, nullable=False, default=0, comment="Segment index (reserved)"
    )

    # 摘要正文（handoff 完整 content）
    summary = Column(
        Text(length=2**31 - 1), nullable=True, comment="Handoff summary content"
    )
    source_message_ids = Column(
        Text, nullable=True, comment="Source unit message ids (JSON array)"
    )
    original_tokens = Column(
        Integer, nullable=False, default=0, comment="Estimated original token count"
    )
    compressed_tokens = Column(
        Integer, nullable=False, default=0, comment="Estimated compressed token count"
    )
    degraded = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Whether this was a truncation fallback (not normally persisted)",
    )

    created_at = Column(
        DateTime, name="gmt_create", default=datetime.utcnow, comment="create time"
    )
    updated_at = Column(
        DateTime,
        name="gmt_modified",
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time",
    )


class GptsColdSegmentDao(BaseDao):
    """Gpts cold handoff DAO."""

    def _to_dict(self, entity: GptsColdSegmentEntity) -> dict:
        return {
            "id": entity.id,
            "session_id": entity.session_id,
            "conv_id": entity.conv_id,
            "content_hash": entity.content_hash,
            "segment_index": entity.segment_index,
            "summary": entity.summary,
            "source_message_ids": json.loads(entity.source_message_ids)
            if entity.source_message_ids
            else [],
            "original_tokens": entity.original_tokens,
            "compressed_tokens": entity.compressed_tokens,
            "degraded": bool(entity.degraded),
        }

    # ------------------------------------------------------------------ #
    # 同步
    # ------------------------------------------------------------------ #
    def upsert(
        self,
        session_id: str,
        conv_id: str,
        content_hash: str,
        summary: str,
        source_message_ids: List[str],
        original_tokens: int = 0,
        compressed_tokens: int = 0,
        segment_index: int = 0,
    ) -> int:
        """按 (session_id, content_hash) upsert 一条 handoff。"""
        session = self.get_raw_session()
        try:
            existing = (
                session.query(GptsColdSegmentEntity)
                .filter(
                    GptsColdSegmentEntity.session_id == session_id,
                    GptsColdSegmentEntity.content_hash == content_hash,
                )
                .first()
            )
            if existing:
                existing.summary = summary
                existing.conv_id = conv_id
                existing.source_message_ids = json.dumps(
                    source_message_ids, ensure_ascii=False
                )
                existing.original_tokens = original_tokens
                existing.compressed_tokens = compressed_tokens
                existing.segment_index = segment_index
                session.commit()
                return existing.id
            entity = GptsColdSegmentEntity(
                session_id=session_id,
                conv_id=conv_id,
                content_hash=content_hash,
                summary=summary,
                source_message_ids=json.dumps(
                    source_message_ids, ensure_ascii=False
                ),
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                segment_index=segment_index,
                degraded=0,
            )
            session.add(entity)
            session.commit()
            return entity.id
        finally:
            session.close()

    def get_by_hash(
        self, session_id: str, content_hash: str
    ) -> Optional[dict]:
        """按 (session_id, content_hash) 读回一条 handoff。"""
        session = self.get_raw_session()
        try:
            entity = (
                session.query(GptsColdSegmentEntity)
                .filter(
                    GptsColdSegmentEntity.session_id == session_id,
                    GptsColdSegmentEntity.content_hash == content_hash,
                )
                .first()
            )
            return self._to_dict(entity) if entity else None
        finally:
            session.close()

    def get_by_session(self, session_id: str) -> List[dict]:
        session = self.get_raw_session()
        try:
            entities = (
                session.query(GptsColdSegmentEntity)
                .filter(GptsColdSegmentEntity.session_id == session_id)
                .order_by(GptsColdSegmentEntity.segment_index)
                .all()
            )
            return [self._to_dict(e) for e in entities]
        finally:
            session.close()

    # ------------------------------------------------------------------ #
    # 异步
    # ------------------------------------------------------------------ #
    async def get_by_hash_async(
        self, session_id: str, content_hash: str
    ) -> Optional[dict]:
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsColdSegmentEntity).where(
                    GptsColdSegmentEntity.session_id == session_id,
                    GptsColdSegmentEntity.content_hash == content_hash,
                )
            )
            entity = result.scalars().first()
            return self._to_dict(entity) if entity else None

    async def upsert_async(
        self,
        session_id: str,
        conv_id: str,
        content_hash: str,
        summary: str,
        source_message_ids: List[str],
        original_tokens: int = 0,
        compressed_tokens: int = 0,
        segment_index: int = 0,
    ) -> int:
        async with self.a_session(commit=True) as session:
            result = await session.execute(
                select(GptsColdSegmentEntity).where(
                    GptsColdSegmentEntity.session_id == session_id,
                    GptsColdSegmentEntity.content_hash == content_hash,
                )
            )
            existing = result.scalars().first()
            if existing:
                existing.summary = summary
                existing.conv_id = conv_id
                existing.source_message_ids = json.dumps(
                    source_message_ids, ensure_ascii=False
                )
                existing.original_tokens = original_tokens
                existing.compressed_tokens = compressed_tokens
                existing.segment_index = segment_index
                await session.flush()
                return existing.id
            entity = GptsColdSegmentEntity(
                session_id=session_id,
                conv_id=conv_id,
                content_hash=content_hash,
                summary=summary,
                source_message_ids=json.dumps(
                    source_message_ids, ensure_ascii=False
                ),
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                segment_index=segment_index,
                degraded=0,
            )
            session.add(entity)
            await session.flush()
            return entity.id
