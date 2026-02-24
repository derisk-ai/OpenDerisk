import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
)
from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)


class GptsToolMessages(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    tool_id: Optional[str]
    name: Optional[str]
    sub_name: Optional[str] = None
    type: Optional[str]
    input: Optional[str] = None
    output: Optional[str] = None
    success: Optional[int]
    error: Optional[str] = None
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    gmt_create: datetime = datetime.utcnow
    gmt_modified: datetime = datetime.utcnow

    def to_dict(self):
        return {k: self._serialize(v) for k, v in self.__dict__.items()}

    def _serialize(self, value):
        if isinstance(value, BaseModel):
            return value.to_dict()
        elif isinstance(value, list):
            return [self._serialize(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        else:
            return value

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(
            tool_id=d.get("tool_id", None),
            name=d.get("name", None),
            sub_name=d.get("sub_name", None),
            type=d.get("type", None),
            input=d.get("input", None),
            output=d.get("output", None),
            success=d.get("success", None),
            error=d.get("error", None),
            trace_id=d.get("trace_id", None),
            session_id=d.get("session_id", None),
            gmt_create=d.get("gmt_create", datetime.utcnow),
            gmt_modified=d.get("gmt_modified", datetime.utcnow),
        )


class GptsToolMessagesEntity(Model):
    __tablename__ = "gpts_tool_messages"
    id = Column(Integer, primary_key=True, comment="autoincrement id")
    tool_id = Column(String(255), nullable=False, comment="tool id")
    name = Column(String(255), nullable=False, comment="tool name")
    sub_name = Column(String(255), nullable=True, comment="tool sub name")
    type = Column(String(255), nullable=False, comment="tool type, api/local/mcp")
    input = Column(Text, nullable=True, comment="tool input")
    output = Column(Text, nullable=True, comment="tool output")
    success = Column(Integer, nullable=False, comment="tool success")
    error = Column(Text, nullable=True, comment="tool error")
    trace_id = Column(String(255), nullable=True, comment="tool trace id")
    session_id = Column(String(255), nullable=True, comment="tool session id")
    gmt_create = Column(DateTime, name="gmt_create", default=datetime.utcnow, comment="create time")
    gmt_modified = Column(DateTime, name="gmt_modified", default=datetime.utcnow, onupdate=datetime.utcnow,
                          comment="last update time", )

    __table_args__ = (
        Index("idx_tool_id", "tool_id"),
        Index("idx_tool_name", "name"),
        Index("idx_tool_name_sub_name", "name", "sub_name"),
        Index("idx_session_id", "session_id")
    )

    def to_dict(self):
        """将实体转换为字典格式"""
        return {
            'id': self.id,
            'tool_id': self.tool_id,
            'name': self.name,
            'sub_name': self.sub_name,
            'type': self.type,
            'input': self.input,
            'output': self.output,
            'success': self.success,
            'error': self.error,
            'trace_id': self.trace_id,
            'session_id': self.session_id,
            'gmt_create': self.gmt_create.isoformat() if self.gmt_create else None,
            'gmt_modified': self.gmt_modified.isoformat() if self.gmt_modified else None,
        }


class GptsToolMessagesDao(BaseDao):
    def create(self, gpts_tool_messages: GptsToolMessages):
        session = self.get_raw_session()
        tool_message_entity = GptsToolMessagesEntity(
            tool_id=gpts_tool_messages.tool_id,
            name=gpts_tool_messages.name,
            sub_name=gpts_tool_messages.sub_name,
            type=gpts_tool_messages.type,
            input=gpts_tool_messages.input,
            output=gpts_tool_messages.output,
            success=gpts_tool_messages.success,
            error=gpts_tool_messages.error,
            trace_id=gpts_tool_messages.trace_id,
            session_id=gpts_tool_messages.session_id
        )
        session.add(tool_message_entity)
        session.commit()
        session.close()
        return tool_message_entity

    def delete(self, id):
        session = self.get_raw_session()
        tool_message_query = session.query(GptsToolMessagesEntity)
        tool_message_query = tool_message_query.filter(GptsToolMessagesEntity.id == id)
        tool_message_query.delete()
        session.commit()
        session.close()

    def delete_by_tool_id(self, tool_id):
        session = self.get_raw_session()
        tool_message_query = session.query(GptsToolMessagesEntity)
        tool_message_query = tool_message_query.filter(GptsToolMessagesEntity.tool_id == tool_id)
        tool_message_query.delete()
        session.commit()
        session.close()

    def query(self, gpts_tool_messages: GptsToolMessages):
        session = self.get_raw_session()
        tool_message_query = session.query(GptsToolMessagesEntity)
        tool_message_query = tool_message_query.filter(
            GptsToolMessagesEntity.tool_id == gpts_tool_messages.tool_id if gpts_tool_messages.tool_id else True,
            GptsToolMessagesEntity.name == gpts_tool_messages.name if gpts_tool_messages.name else True,
            GptsToolMessagesEntity.sub_name == gpts_tool_messages.sub_name if gpts_tool_messages.sub_name else True,
            GptsToolMessagesEntity.type == gpts_tool_messages.type if gpts_tool_messages.type else True,
            GptsToolMessagesEntity.input == gpts_tool_messages.input if gpts_tool_messages.input else True,
            GptsToolMessagesEntity.output == gpts_tool_messages.output if gpts_tool_messages.output else True,
            GptsToolMessagesEntity.success == gpts_tool_messages.success if gpts_tool_messages.success else True,
            GptsToolMessagesEntity.error == gpts_tool_messages.error if gpts_tool_messages.error else True,
            GptsToolMessagesEntity.trace_id == gpts_tool_messages.trace_id if gpts_tool_messages.trace_id else True,
            GptsToolMessagesEntity.session_id == gpts_tool_messages.session_id if gpts_tool_messages.session_id else True
        )
        tool_messages = tool_message_query.all()
        session.close()
        result = [GptsToolMessages.from_dict(tool_message.to_dict()) for tool_message in tool_messages]
        return result