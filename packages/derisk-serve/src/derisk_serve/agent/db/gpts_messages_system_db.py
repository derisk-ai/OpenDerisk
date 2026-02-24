import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    BigInteger,
    String,
    Text,
    SmallInteger,
    and_,
    or_,
    desc
)
from derisk.storage.metadata import BaseDao, Model


class GptsMessagesSystemEntity(Model):
    __tablename__ = "gpts_messages_system"

    id = Column(Integer, primary_key=True, autoincrement=True,
                comment="autoincrement id")
    gmt_create = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="修改时间")
    conv_id = Column(String(255), nullable=False, comment="agent对话id")
    conv_session_id = Column(String(255), nullable=False, comment="agent会话id")
    conv_round_id = Column(String(255), nullable=True, comment="agent会话轮次id")
    agent = Column(String(255), nullable=False, comment="消息所属Agent")
    type = Column(String(255), nullable=False, comment="消息类型(error 运行异常, notify 运行通知)")
    phase = Column(String(255), nullable=False, comment="消息阶段(in_context, llm_call, action_run, message_out)")
    agent_message_id = Column(String(255), nullable=False, comment="关联的Agent消息id")
    message_id = Column(String(255), nullable=False, comment="消息id")
    content = Column(Text(length=2 ** 31 - 1), nullable=True, comment="消息内容")
    content_extra = Column(String(2000), nullable=True, comment="消息扩展内容，根据类型阶段不同，内容不同")
    retry_time = Column(SmallInteger, default=0, nullable=True, comment="当前阶段重试次数")
    final_status = Column(String(20), nullable=True, comment="当前阶段最终状态")

    __table_args__ = (
        Index('idx_message_phase', 'conv_id', 'phase'),
        Index('idx_message_type', 'conv_id', 'type', 'phase'),
        Index('idx_agent_message', 'conv_id', 'agent_message_id'),
        Index('idx_message', 'message_id'),
    )


class GptsMessagesSystemDao(BaseDao):
    def _dict_to_entity(self, param: dict) -> GptsMessagesSystemEntity:
        return GptsMessagesSystemEntity(
            conv_id=param.get("conv_id"),  # type: ignore
            conv_session_id=param.get("conv_session_id"),  # type: ignore
            conv_round_id=param.get("conv_round_id"),  # type: ignore
            agent=param.get("agent"),  # type: ignore
            type=param.get("type"),  # type: ignore
            phase=param.get("phase"),  # type: ignore
            agent_message_id=param.get("agent_message_id"),  # type: ignore
            message_id=param.get("message_id"),  # type: ignore
            content=param.get("content"),  # type: ignore
            content_extra=param.get("content_extra"),  # type: ignore
            retry_time=param.get("retry_time", 0),  # type: ignore
            final_status=param.get("final_status"),  # type: ignore
            gmt_create=param.get("gmt_create", datetime.now()),  # type: ignore
            gmt_modified=param.get("gmt_modified", datetime.now()),  # type: ignore
        )

    def append(self, entity: dict) -> int:
        """插入新的系统消息记录"""
        session = self.get_raw_session()
        message = self._dict_to_entity(entity)
        session.add(message)
        session.commit()
        id = message.id
        session.close()
        return id

    def update_message(self, entity: dict):
        """根据message_id更新系统消息记录"""
        session = self.get_raw_session()
        message_qry = session.query(GptsMessagesSystemEntity)
        message_qry = message_qry.filter(
            GptsMessagesSystemEntity.message_id == entity["message_id"]
        )
        old_message = message_qry.one_or_none()

        if old_message:
            update_data = {
                GptsMessagesSystemEntity.conv_id: entity.get("conv_id", old_message.conv_id),
                GptsMessagesSystemEntity.conv_session_id: entity.get("conv_session_id", old_message.conv_session_id),
                GptsMessagesSystemEntity.conv_round_id: entity.get("conv_round_id", old_message.conv_round_id),
                GptsMessagesSystemEntity.agent: entity.get("agent", old_message.agent),
                GptsMessagesSystemEntity.type: entity.get("type", old_message.type),
                GptsMessagesSystemEntity.phase: entity.get("phase", old_message.phase),
                GptsMessagesSystemEntity.agent_message_id: entity.get("agent_message_id", old_message.agent_message_id),
                GptsMessagesSystemEntity.content: entity.get("content", old_message.content),
                GptsMessagesSystemEntity.content_extra: entity.get("content_extra", old_message.content_extra),
                GptsMessagesSystemEntity.retry_time: entity.get("retry_time", old_message.retry_time),
                GptsMessagesSystemEntity.final_status: entity.get("final_status", old_message.final_status),
                GptsMessagesSystemEntity.gmt_modified: datetime.utcnow()
            }
            message_qry.update(update_data, synchronize_session="fetch")
        else:
            session.add(self._dict_to_entity(entity))

        session.commit()
        session.close()

    def get_by_conv_id(self, conv_id: str) -> Optional[List[GptsMessagesSystemEntity]]:
        session = self.get_raw_session()
        gpts_messages_system_qry = session.query(GptsMessagesSystemEntity)
        if conv_id:
            gpts_messages = gpts_messages_system_qry.filter(GptsMessagesSystemEntity.conv_id == conv_id)
        result = gpts_messages_system_qry.all()
        session.close()
        return result

    def get_by_conv_session_id(
        self, conv_session_id: str
    ) -> Optional[List[GptsMessagesSystemEntity]]:
        session = self.get_raw_session()
        gpts_messages_system_qry = session.query(GptsMessagesSystemEntity)
        if conv_session_id:
            gpts_messages_system_qry = gpts_messages_system_qry.filter(
                GptsMessagesSystemEntity.conv_session_id == conv_session_id
            )
        result = gpts_messages_system_qry.all()
        session.close()
        return result

    def get_by_message_id(self, message_id: str) -> Optional[GptsMessagesSystemEntity]:
        """根据消息ID获取系统消息"""
        session = self.get_raw_session()
        result = session.query(GptsMessagesSystemEntity).filter(
            GptsMessagesSystemEntity.message_id == message_id
        ).one_or_none()
        session.close()
        return result

    def get_by_agent_message_id(self, agent_message_id: str) -> List[GptsMessagesSystemEntity]:
        """根据关联的Agent消息ID获取系统消息列表"""
        session = self.get_raw_session()
        result = session.query(GptsMessagesSystemEntity).filter(
            GptsMessagesSystemEntity.agent_message_id == agent_message_id
        ).all()
        session.close()
        return result

    def get_by_conv_phase(self, conv_id: str, phase: str) -> List[GptsMessagesSystemEntity]:
        """根据对话ID和阶段获取系统消息"""
        session = self.get_raw_session()
        result = session.query(GptsMessagesSystemEntity).filter(
            and_(
                GptsMessagesSystemEntity.conv_id == conv_id,
                GptsMessagesSystemEntity.phase == phase
            )
        ).all()
        session.close()
        return result

    def get_by_conv_type_phase(self, conv_id: str, msg_type: str, phase: str) -> List[GptsMessagesSystemEntity]:
        """根据对话ID、消息类型和阶段获取系统消息"""
        session = self.get_raw_session()
        result = session.query(GptsMessagesSystemEntity).filter(
            and_(
                GptsMessagesSystemEntity.conv_id == conv_id,
                GptsMessagesSystemEntity.type == msg_type,
                GptsMessagesSystemEntity.phase == phase
            )
        ).all()
        session.close()
        return result

    def delete_by_msg_id(self, message_id: str):
        """根据消息ID删除系统消息"""
        session = self.get_raw_session()
        session.query(GptsMessagesSystemEntity).filter(
            GptsMessagesSystemEntity.message_id == message_id
        ).delete()
        session.commit()
        session.close()
