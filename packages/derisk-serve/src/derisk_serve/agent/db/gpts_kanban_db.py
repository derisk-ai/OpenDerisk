"""Gpts Kanban 数据库模型和 DAO.

用于持久化存储 PDCA Agent 的看板数据，包括阶段、交付物和预研日志。
"""

import json
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


class GptsKanbanEntity(Model):
    """Gpts 看板实体.

    存储看板的基本信息和当前状态。
    """

    __tablename__ = "gpts_kanban"
    __table_args__ = (Index("idx_kanban_conv_session", "conv_id", "session_id"),)

    id = Column(Integer, primary_key=True, comment="autoincrement id")

    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation"
    )
    session_id = Column(
        String(255), nullable=False, comment="The session id within conversation"
    )
    agent_id = Column(
        String(255), nullable=False, comment="The agent id that created this kanban"
    )

    # 看板基本信息
    kanban_id = Column(
        String(255), nullable=False, unique=True, comment="Kanban unique id"
    )
    mission = Column(Text, nullable=False, comment="Mission description")
    current_stage_index = Column(
        Integer, nullable=False, default=0, comment="Current stage index"
    )

    # 阶段和交付物信息 (JSON)
    stages = Column(Text(length=2**31 - 1), nullable=True, comment="Stages data (JSON)")
    deliverables = Column(
        Text(length=2**31 - 1), nullable=True, comment="Deliverables data (JSON)"
    )

    # 时间戳
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


class GptsKanbanDao(BaseDao):
    """Gpts 看板 DAO."""

    def _from_kanban_data(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        kanban_data: dict,
    ) -> GptsKanbanEntity:
        """将 Kanban 字典转换为 GptsKanbanEntity."""
        return GptsKanbanEntity(
            conv_id=conv_id,
            session_id=session_id,
            agent_id=agent_id,
            kanban_id=kanban_data.get("kanban_id", f"{agent_id}_{session_id}"),
            mission=kanban_data.get("mission", ""),
            current_stage_index=kanban_data.get("current_stage_index", 0),
            stages=json.dumps(kanban_data.get("stages", []), ensure_ascii=False),
            deliverables=json.dumps(
                kanban_data.get("deliverables", {}), ensure_ascii=False
            ),
        )

    def _to_kanban_data(self, entity: GptsKanbanEntity) -> dict:
        """将 GptsKanbanEntity 转换为 Kanban 字典."""
        return {
            "id": entity.id,
            "conv_id": entity.conv_id,
            "session_id": entity.session_id,
            "agent_id": entity.agent_id,
            "kanban_id": entity.kanban_id,
            "mission": entity.mission,
            "current_stage_index": entity.current_stage_index,
            "stages": json.loads(entity.stages) if entity.stages else [],
            "deliverables": json.loads(entity.deliverables)
            if entity.deliverables
            else {},
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    def save_kanban(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        kanban_data: dict,
    ) -> int:
        """保存或更新看板.

        Args:
            conv_id: 会话 ID
            session_id: Session ID
            agent_id: Agent ID
            kanban_data: Kanban 字典

        Returns:
            记录 ID
        """
        session = self.get_raw_session()

        # 查找现有记录
        existing = (
            session.query(GptsKanbanEntity)
            .filter(
                GptsKanbanEntity.conv_id == conv_id,
                GptsKanbanEntity.session_id == session_id,
            )
            .one_or_none()
        )

        if existing:
            # 更新现有记录
            existing.mission = kanban_data.get("mission", existing.mission)
            existing.current_stage_index = kanban_data.get(
                "current_stage_index", existing.current_stage_index
            )
            existing.stages = json.dumps(
                kanban_data.get("stages", []), ensure_ascii=False
            )
            existing.deliverables = json.dumps(
                kanban_data.get("deliverables", {}), ensure_ascii=False
            )
        else:
            # 创建新记录
            entity = self._from_kanban_data(conv_id, session_id, agent_id, kanban_data)
            session.add(entity)

        session.commit()
        record_id = existing.id if existing else entity.id
        session.close()
        return record_id

    async def save_kanban_async(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        kanban_data: dict,
    ) -> int:
        """异步保存或更新看板."""
        async with self.a_session(commit=True) as session:
            result = await session.execute(
                select(GptsKanbanEntity).where(
                    GptsKanbanEntity.conv_id == conv_id,
                    GptsKanbanEntity.session_id == session_id,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.mission = kanban_data.get("mission", existing.mission)
                existing.current_stage_index = kanban_data.get(
                    "current_stage_index", existing.current_stage_index
                )
                existing.stages = json.dumps(
                    kanban_data.get("stages", []), ensure_ascii=False
                )
                existing.deliverables = json.dumps(
                    kanban_data.get("deliverables", {}), ensure_ascii=False
                )
                await session.flush()
                return existing.id
            else:
                entity = self._from_kanban_data(
                    conv_id, session_id, agent_id, kanban_data
                )
                session.add(entity)
                await session.flush()
                return entity.id

    def get_kanban(
        self,
        conv_id: str,
        session_id: str,
    ) -> Optional[dict]:
        """获取看板数据.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            Kanban 字典或 None
        """
        session = self.get_raw_session()
        entity = (
            session.query(GptsKanbanEntity)
            .filter(
                GptsKanbanEntity.conv_id == conv_id,
                GptsKanbanEntity.session_id == session_id,
            )
            .one_or_none()
        )
        session.close()
        return self._to_kanban_data(entity) if entity else None

    async def get_kanban_async(
        self,
        conv_id: str,
        session_id: str,
    ) -> Optional[dict]:
        """异步获取看板数据."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsKanbanEntity).where(
                    GptsKanbanEntity.conv_id == conv_id,
                    GptsKanbanEntity.session_id == session_id,
                )
            )
            entity = result.scalar_one_or_none()
            return self._to_kanban_data(entity) if entity else None

    def delete_kanban(self, conv_id: str, session_id: str) -> bool:
        """删除看板.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            是否成功
        """
        session = self.get_raw_session()
        (
            session.query(GptsKanbanEntity)
            .filter(
                GptsKanbanEntity.conv_id == conv_id,
                GptsKanbanEntity.session_id == session_id,
            )
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def delete_kanban_async(self, conv_id: str, session_id: str) -> bool:
        """异步删除看板."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsKanbanEntity.__table__.delete().where(
                    GptsKanbanEntity.conv_id == conv_id,
                    GptsKanbanEntity.session_id == session_id,
                )
            )
        return True


class GptsPreKanbanLogEntity(Model):
    """Gpts 预研日志实体.

    存储看板创建前的预研工作日志。
    """

    __tablename__ = "gpts_pre_kanban_log"
    __table_args__ = (
        Index("idx_pre_kanban_log_conv_session", "conv_id", "session_id"),
    )

    id = Column(Integer, primary_key=True, comment="autoincrement id")

    conv_id = Column(
        String(255), nullable=False, comment="The unique id of the conversation"
    )
    session_id = Column(
        String(255), nullable=False, comment="The session id within conversation"
    )
    agent_id = Column(String(255), nullable=False, comment="The agent id")

    # 工作日志条目 (JSON)
    logs = Column(
        Text(length=2**31 - 1), nullable=True, comment="Pre-kanban logs (JSON)"
    )

    # 时间戳
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


class GptsPreKanbanLogDao(BaseDao):
    """Gpts 预研日志 DAO."""

    def get_logs(
        self,
        conv_id: str,
        session_id: str,
    ) -> List[dict]:
        """获取预研日志.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            日志条目列表
        """
        session = self.get_raw_session()
        entity = (
            session.query(GptsPreKanbanLogEntity)
            .filter(
                GptsPreKanbanLogEntity.conv_id == conv_id,
                GptsPreKanbanLogEntity.session_id == session_id,
            )
            .one_or_none()
        )
        session.close()

        if entity and entity.logs:
            return json.loads(entity.logs)
        return []

    async def get_logs_async(
        self,
        conv_id: str,
        session_id: str,
    ) -> List[dict]:
        """异步获取预研日志."""
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(GptsPreKanbanLogEntity).where(
                    GptsPreKanbanLogEntity.conv_id == conv_id,
                    GptsPreKanbanLogEntity.session_id == session_id,
                )
            )
            entity = result.scalar_one_or_none()
            if entity and entity.logs:
                return json.loads(entity.logs)
            return []

    def append_log(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        log_entry: dict,
    ) -> int:
        """追加一条预研日志.

        Args:
            conv_id: 会话 ID
            session_id: Session ID
            agent_id: Agent ID
            log_entry: 日志条目

        Returns:
            记录 ID
        """
        session = self.get_raw_session()

        entity = (
            session.query(GptsPreKanbanLogEntity)
            .filter(
                GptsPreKanbanLogEntity.conv_id == conv_id,
                GptsPreKanbanLogEntity.session_id == session_id,
            )
            .one_or_none()
        )

        if entity:
            logs = json.loads(entity.logs) if entity.logs else []
            logs.append(log_entry)
            entity.logs = json.dumps(logs, ensure_ascii=False)
        else:
            entity = GptsPreKanbanLogEntity(
                conv_id=conv_id,
                session_id=session_id,
                agent_id=agent_id,
                logs=json.dumps([log_entry], ensure_ascii=False),
            )
            session.add(entity)

        session.commit()
        record_id = entity.id
        session.close()
        return record_id

    async def append_log_async(
        self,
        conv_id: str,
        session_id: str,
        agent_id: str,
        log_entry: dict,
    ) -> int:
        """异步追加一条预研日志."""
        async with self.a_session(commit=True) as session:
            result = await session.execute(
                select(GptsPreKanbanLogEntity).where(
                    GptsPreKanbanLogEntity.conv_id == conv_id,
                    GptsPreKanbanLogEntity.session_id == session_id,
                )
            )
            entity = result.scalar_one_or_none()

            if entity:
                logs = json.loads(entity.logs) if entity.logs else []
                logs.append(log_entry)
                entity.logs = json.dumps(logs, ensure_ascii=False)
                await session.flush()
                return entity.id
            else:
                entity = GptsPreKanbanLogEntity(
                    conv_id=conv_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    logs=json.dumps([log_entry], ensure_ascii=False),
                )
                session.add(entity)
                await session.flush()
                return entity.id

    def clear_logs(
        self,
        conv_id: str,
        session_id: str,
    ) -> bool:
        """清空预研日志.

        Args:
            conv_id: 会话 ID
            session_id: Session ID

        Returns:
            是否成功
        """
        session = self.get_raw_session()
        (
            session.query(GptsPreKanbanLogEntity)
            .filter(
                GptsPreKanbanLogEntity.conv_id == conv_id,
                GptsPreKanbanLogEntity.session_id == session_id,
            )
            .delete()
        )
        session.commit()
        session.close()
        return True

    async def clear_logs_async(self, conv_id: str, session_id: str) -> bool:
        """异步清空预研日志."""
        async with self.a_session(commit=True) as session:
            await session.execute(
                GptsPreKanbanLogEntity.__table__.delete().where(
                    GptsPreKanbanLogEntity.conv_id == conv_id,
                    GptsPreKanbanLogEntity.session_id == session_id,
                )
            )
        return True
