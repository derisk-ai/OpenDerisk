"""Gpts WorkLog 数据库模型和 DAO.

用于持久化存储 Agent 的工作日志记录，支持 ReActAgent 和其他 Agent 的历史记录管理。
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
    select,
)

from derisk.storage.metadata import BaseDao, Model


class GptsWorkLogEntity(Model):
    """Gpts 工作日志实体.

    存储每个工具调用的详细信息，包括参数、结果摘要等。
    """

    __tablename__ = "gpts_work_log"
    __table_args__ = (
        Index("idx_work_log_conv_session", "conv_id", "session_id"),
        Index("idx_work_log_conv_tool", "conv_id", "tool"),
    )

    id = Column(Integer, primary_key=True, comment="autoincrement id")

    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation"
    )
    session_id = Column(
        String(255), nullable=False, comment="The session id within conversation"
    )
    agent_id = Column(
        String(255), nullable=False, comment="The agent id that created this log"
    )
    step_index = Column(
        Integer, nullable=False, default=0, comment="The step index in the session"
    )

    # 工具信息
    tool = Column(String(255), nullable=False, comment="Tool name")
    args = Column(Text, nullable=True, comment="Tool arguments (JSON)")
    summary = Column(Text, nullable=True, comment="Brief summary of the action")
    result = Column(Text(length=2**31 - 1), nullable=True, comment="Result content")
    full_result_archive = Column(
        String(512), nullable=True, comment="File key for archived full result"
    )
    archives = Column(Text, nullable=True, comment="List of archive file keys (JSON)")

    # 元数据
    success = Column(
        Integer, nullable=False, default=1, comment="Whether the action succeeded"
    )
    tags = Column(Text, nullable=True, comment="Tags (JSON array)")
    tokens = Column(Integer, nullable=False, default=0, comment="Estimated token count")
    status = Column(
        String(32),
        nullable=False,
        default="active",
        comment="Status: active/compressed/archived",
    )

    # 时间戳
    timestamp = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When the action was performed",
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


class GptsWorkLogDao(BaseDao):
    """Gpts 工作日志 DAO."""

    def _from_work_entry(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        entry: dict,
    ) -> GptsWorkLogEntity:
        """将 WorkEntry 字典转换为 GptsWorkLogEntity."""
        return GptsWorkLogEntity(
            conv_id=conv_id,
            session_id=session_id,
            agent_id=agent_id,
            step_index=entry.get("step_index", 0),
            tool=entry.get("tool", ""),
            args=json.dumps(entry.get("args"), ensure_ascii=False)
            if entry.get("args")
            else None,
            summary=entry.get("summary"),
            result=entry.get("result"),
            full_result_archive=entry.get("full_result_archive"),
            archives=json.dumps(entry.get("archives"), ensure_ascii=False)
            if entry.get("archives")
            else None,
            success=1 if entry.get("success", True) else 0,
            tags=json.dumps(entry.get("tags", []), ensure_ascii=False)
            if entry.get("tags")
            else None,
            tokens=entry.get("tokens", 0),
            status=entry.get("status", "active"),
            timestamp=datetime.fromtimestamp(
                entry.get("timestamp", datetime.utcnow().timestamp())
            ),
        )

    def _to_work_entry(self, entity: GptsWorkLogEntity) -> dict:
        """将 GptsWorkLogEntity 转换为 WorkEntry 字典."""
        return {
            "id": entity.id,
            "conv_id": entity.conv_id,
            "session_id": entity.session_id,
            "agent_id": entity.agent_id,
            "step_index": entity.step_index,
            "timestamp": entity.timestamp.timestamp() if entity.timestamp else 0.0,
            "tool": entity.tool,
            "args": json.loads(entity.args) if entity.args else None,
            "summary": entity.summary,
            "result": entity.result,
            "full_result_archive": entity.full_result_archive,
            "archives": json.loads(entity.archives) if entity.archives else None,
            "success": bool(entity.success),
            "tags": json.loads(entity.tags) if entity.tags else [],
            "tokens": entity.tokens,
            "status": entity.status,
        }

    def append(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        entry: dict,
    ) -> int:
        """添加一条工作日志记录.

        Args:
            conv_id: 会话 ID
            session_id: 会话内的 session ID
            agent_id: Agent ID
            entry: WorkEntry 字典

        Returns:
            插入记录的 ID
        """
        entity = self._from_work_entry(conv_id, session_id, agent_id, entry)
        session = self.get_raw_session()
        session.add(entity)
        session.commit()
        record_id = entity.id
        session.close()
        return record_id

    async def append_async(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        entry: dict,
    ) -> int:
        """异步添加一条工作日志记录."""
        entity = self._from_work_entry(conv_id, session_id, agent_id, entry)
        async with self.a_session(commit=True) as session:
            session.add(entity)
            await session.flush()
            return entity.id

    def get_by_session(
        self,
        conv_id: str,
        session_id: str,
    ) -> List[dict]:
        """获取指定 session 的所有工作日志.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            WorkEntry 字典列表
        """
        session = self.get_raw_session()
        entities = (
            session.query(GptsWorkLogEntity)
            .filter(
                GptsWorkLogEntity.conv_id == conv_id,
                GptsWorkLogEntity.session_id == session_id,
            )
            .order_by(GptsWorkLogEntity.step_index, GptsWorkLogEntity.timestamp)
            .all()
        )
        session.close()
        return [self._to_work_entry(e) for e in entities]

    async def get_by_session_async(
        self,
        conv_id: str,
        session_id: str,
    ) -> List[dict]:
        """异步获取指定 session 的所有工作日志."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsWorkLogEntity)
                .where(
                    GptsWorkLogEntity.conv_id == conv_id,
                    GptsWorkLogEntity.session_id == session_id,
                )
                .order_by(GptsWorkLogEntity.step_index, GptsWorkLogEntity.timestamp)
            )
            entities = result.scalars().all()
            return [self._to_work_entry(e) for e in entities]

    def delete_by_session(self, conv_id: str, session_id: str) -> bool:
        """删除指定 session 的所有工作日志.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            是否成功
        """
        session = self.get_raw_session()
        (
            session.query(GptsWorkLogEntity)
            .filter(
                GptsWorkLogEntity.conv_id == conv_id,
                GptsWorkLogEntity.session_id == session_id,
            )
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def delete_by_session_async(self, conv_id: str, session_id: str) -> bool:
        """异步删除指定 session 的所有工作日志."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsWorkLogEntity.__table__.delete().where(
                    GptsWorkLogEntity.conv_id == conv_id,
                    GptsWorkLogEntity.session_id == session_id,
                )
            )
        return True

    def get_stats_by_session(
        self,
        conv_id: str,
        session_id: str,
    ) -> dict:
        """获取指定 session 的工作日志统计信息.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            统计信息字典
        """
        session = self.get_raw_session()
        entities = (
            session.query(GptsWorkLogEntity)
            .filter(
                GptsWorkLogEntity.conv_id == conv_id,
                GptsWorkLogEntity.session_id == session_id,
            )
            .all()
        )
        session.close()

        total_entries = len(entities)
        success_count = sum(1 for e in entities if e.success)
        fail_count = total_entries - success_count
        total_tokens = sum(e.tokens for e in entities)

        return {
            "total_entries": total_entries,
            "success_count": success_count,
            "fail_count": fail_count,
            "total_tokens": total_tokens,
        }
