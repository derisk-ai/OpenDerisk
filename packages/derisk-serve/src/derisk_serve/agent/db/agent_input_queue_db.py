"""Agent Input Queue Database Module for persisting user input during agent execution.

This module provides a persistent queue for user inputs that can be consumed
by agents during execution. It supports distributed scenarios where inputs
may be submitted from different server instances.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    and_,
    select,
    update,
    delete,
    func,
)

from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class AgentInputQueueEntity(Model):
    """Agent输入队列持久化实体

    用于存储用户在 Agent 执行过程中追加的输入消息。
    支持分布式场景：任意服务实例可写入，Agent 所在实例消费。
    """

    __tablename__ = "agent_input_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 会话信息
    conv_id = Column(String(255), nullable=False, comment="对话ID (agent_conv_id)")
    conv_session_id = Column(String(255), nullable=False, comment="会话ID")

    # 消息内容
    message_id = Column(String(64), nullable=False, comment="消息唯一ID")
    message_content = Column(Text, nullable=False, comment="消息内容 (JSON)")
    sender_name = Column(String(128), comment="发送者名称")
    sender_type = Column(String(32), default="user", comment="发送者类型 (user/system)")

    # 状态管理
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending/processing/consumed",
    )
    consumed_at = Column(DateTime, comment="消费时间")
    consumed_by = Column(String(64), comment="消费的服务器实例ID")

    # 元数据
    priority = Column(Integer, default=0, comment="优先级 (数字越大越优先)")
    extra = Column(Text, comment="扩展信息 (JSON)")
    gmt_create = Column(DateTime, default=datetime.now, comment="创建时间")
    gmt_modified = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    __table_args__ = (
        Index("idx_input_conv_session_status", "conv_session_id", "status"),
        Index("idx_input_conv_id_status", "conv_id", "status"),
        Index("idx_input_gmt_create", "gmt_create"),
    )


class AgentInputQueueDao(BaseDao):
    """Agent输入队列 DAO

    提供用户输入队列的数据库操作方法。
    """

    async def insert(self, entity: AgentInputQueueEntity) -> int:
        """插入输入项，返回自增ID

        Args:
            entity: 输入队列实体

        Returns:
            自增ID
        """
        async with self.a_session() as session:
            session.add(entity)
            await session.flush()
            return entity.id

    async def get_pending_by_conv(
        self, conv_id: str, limit: int = 10
    ) -> List[AgentInputQueueEntity]:
        """获取指定对话的待处理输入

        Args:
            conv_id: 对话ID
            limit: 最大返回数量

        Returns:
            待处理的输入列表（按优先级降序、ID升序）
        """
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(AgentInputQueueEntity)
                .where(AgentInputQueueEntity.conv_id == conv_id)
                .where(AgentInputQueueEntity.status == "pending")
                .order_by(
                    AgentInputQueueEntity.priority.desc(), AgentInputQueueEntity.id
                )
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_pending_by_session(
        self, conv_session_id: str, limit: int = 10
    ) -> List[AgentInputQueueEntity]:
        """获取指定会话的所有待处理输入

        Args:
            conv_session_id: 会话ID
            limit: 最大返回数量

        Returns:
            待处理的输入列表
        """
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(AgentInputQueueEntity)
                .where(AgentInputQueueEntity.conv_session_id == conv_session_id)
                .where(AgentInputQueueEntity.status == "pending")
                .order_by(
                    AgentInputQueueEntity.priority.desc(), AgentInputQueueEntity.id
                )
                .limit(limit)
            )
            return list(result.scalars().all())

    async def mark_processing(self, item_ids: List[int], consumer_id: str) -> None:
        """标记为处理中

        Args:
            item_ids: 输入项ID列表
            consumer_id: 消费者实例ID
        """
        if not item_ids:
            return
        async with self.a_session() as session:
            await session.execute(
                update(AgentInputQueueEntity)
                .where(AgentInputQueueEntity.id.in_(item_ids))
                .values(status="processing", consumed_by=consumer_id)
            )

    async def mark_consumed(self, item_ids: List[int], consumer_id: str) -> None:
        """标记为已消费

        Args:
            item_ids: 输入项ID列表
            consumer_id: 消费者实例ID
        """
        if not item_ids:
            return
        async with self.a_session() as session:
            await session.execute(
                update(AgentInputQueueEntity)
                .where(AgentInputQueueEntity.id.in_(item_ids))
                .values(
                    status="consumed",
                    consumed_by=consumer_id,
                    consumed_at=datetime.now(),
                )
            )

    async def delete_consumed(
        self, conv_id: Optional[str] = None, before_hours: int = 24
    ) -> int:
        """删除已消费的旧记录

        Args:
            conv_id: 对话ID（可选，不指定则清理所有对话）
            before_hours: 清理多少小时前的记录

        Returns:
            删除的记录数
        """
        async with self.a_session() as session:
            cutoff = datetime.now() - timedelta(hours=before_hours)

            query = select(AgentInputQueueEntity).where(
                and_(
                    AgentInputQueueEntity.status == "consumed",
                    AgentInputQueueEntity.consumed_at < cutoff,
                )
            )

            if conv_id:
                query = query.where(AgentInputQueueEntity.conv_id == conv_id)

            entities = await session.execute(query)
            count = 0
            for entity in entities.scalars().all():
                await session.delete(entity)
                count += 1
            return count

    async def count_pending(self, conv_id: str) -> int:
        """统计待处理输入数量

        Args:
            conv_id: 对话ID

        Returns:
            待处理输入数量
        """
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(func.count(AgentInputQueueEntity.id))
                .where(AgentInputQueueEntity.conv_id == conv_id)
                .where(AgentInputQueueEntity.status == "pending")
            )
            return result.scalar() or 0

    async def count_pending_by_session(self, conv_session_id: str) -> int:
        """统计指定会话的待处理输入数量

        Args:
            conv_session_id: 会话ID

        Returns:
            待处理输入数量
        """
        async with self.a_session(commit=False) as session:
            result = await session.execute(
                select(func.count(AgentInputQueueEntity.id))
                .where(AgentInputQueueEntity.conv_session_id == conv_session_id)
                .where(AgentInputQueueEntity.status == "pending")
            )
            return result.scalar() or 0

    async def clear_by_conv(self, conv_id: str) -> None:
        """清空指定对话的所有输入

        Args:
            conv_id: 对话ID
        """
        async with self.a_session() as session:
            entities = await session.execute(
                select(AgentInputQueueEntity).where(
                    AgentInputQueueEntity.conv_id == conv_id
                )
            )
            for entity in entities.scalars().all():
                await session.delete(entity)

    async def clear_by_session(self, conv_session_id: str) -> None:
        """清空指定会话的所有输入

        Args:
            conv_session_id: 会话ID
        """
        async with self.a_session() as session:
            entities = await session.execute(
                select(AgentInputQueueEntity).where(
                    AgentInputQueueEntity.conv_session_id == conv_session_id
                )
            )
            for entity in entities.scalars().all():
                await session.delete(entity)
