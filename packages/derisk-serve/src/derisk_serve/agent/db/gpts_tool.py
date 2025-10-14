import ast
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, List

import aiohttp
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

class GptsTool(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    tool_name: Optional[str] = None
    tool_id: Optional[str] = None
    type: Optional[str] = None
    config: Optional[str] = None
    owner: Optional[str] = None
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
            tool_name=d["tool_name"],
            tool_id=d["tool_id"],
            type=d["type"],
            config=d["config"],
            owner=d["owner"],
            gmt_create=d.get("gmt_create", None),
            gmt_modified=d.get("gmt_modified", None)
        )


class GptsToolEntity(Model):
    __tablename__ = "gpts_tool"
    id = Column(Integer, primary_key=True, comment="autoincrement id")
    tool_name = Column(String(255), nullable=False, comment="tool name")
    tool_id = Column(String(255), nullable=False, comment="tool id")
    type = Column(String(255), nullable=False, comment="tool type, api/local/mcp")
    config = Column(Text, nullable=False, comment="tool detail config")
    owner = Column(String(255), nullable=False, comment="tool owner")
    gmt_create = Column(DateTime, name="gmt_create", default=datetime.utcnow, comment="create time")
    gmt_modified = Column(DateTime, name="gmt_modified", default=datetime.utcnow, onupdate=datetime.utcnow,
                          comment="last update time", )

    __table_args__ = (Index("idx_tool_name", "tool_id")),


class GptsToolDao(BaseDao):
    def create(self, gpts_tool: GptsTool):
        session = self.get_raw_session()
        if self.get_tool_by_tool_id(gpts_tool.tool_id):
            raise Exception(f"tool_id:{gpts_tool.tool_id} already exists, don't allow to create!")
        if self.get_tool_by_name(gpts_tool.tool_name):
            raise Exception(f"tool_name:{gpts_tool.tool_name} already exists, don't allow to create!")
        tool_entity = GptsToolEntity(
            tool_name=gpts_tool.tool_name,
            tool_id=gpts_tool.tool_id,
            type=gpts_tool.type,
            config=gpts_tool.config,
            owner=gpts_tool.owner,
        )
        session.add(tool_entity)
        session.commit()
        session.close()
        return gpts_tool

    def delete_by_tool_id(self, tool_id: str):
        session = self.get_raw_session()
        tool_query = session.query(GptsToolEntity)
        tool_query = tool_query.filter(GptsToolEntity.tool_id == tool_id)
        tool_query.delete()
        session.commit()
        session.close()

    def update_tool(self, gpts_tool: GptsTool):
        session = self.get_raw_session()
        tool_query = session.query(GptsToolEntity)
        if gpts_tool.tool_id is None:
            raise Exception("tool_id is None, don't allow to edit!")
        tool_query = tool_query.filter(
            GptsToolEntity.tool_id == gpts_tool.tool_id
        )
        update_params = {}
        if gpts_tool.tool_name:
            update_params[GptsToolEntity.tool_name] = gpts_tool.tool_name
        if gpts_tool.type:
            update_params[GptsToolEntity.type] = gpts_tool.type
        if gpts_tool.config:
            update_params[GptsToolEntity.config] = gpts_tool.config
        if gpts_tool.owner:
            update_params[GptsToolEntity.owner] = gpts_tool.owner
        tool_query.update(update_params, synchronize_session="fetch")
        session.commit()
        session.close()

    def get_tool_by_id(self, id):
        session = self.get_raw_session()
        gpts_tools = session.query(GptsToolEntity)
        if id:
            gpts_tools = gpts_tools.filter(GptsToolEntity.id == id)
        result = gpts_tools.first()
        session.close()
        return result

    def get_tool_by_name(self, name):
        session = self.get_raw_session()
        gpts_tools = session.query(GptsToolEntity)
        if name:
            gpts_tools = gpts_tools.filter(GptsToolEntity.tool_name == name)
        result = gpts_tools.first()
        session.close()
        if result is None:
            return None
        gpt_tools = GptsTool.from_dict({
            "tool_name": result.tool_name,
            "tool_id": result.tool_id,
            "type": result.type,
            "config": result.config,
            "owner": result.owner,
            "gmt_create": result.gmt_create,
            "gmt_modified": result.gmt_modified
        })
        return gpt_tools

    def get_tool_by_type(self, type):
        session = self.get_raw_session()
        gpts_tools = session.query(GptsToolEntity)
        if type:
            gpts_tools = gpts_tools.filter(GptsToolEntity.type == type)
        result = gpts_tools.all()
        session.close()
        if result is None:
            return None
        gpts_tools = [GptsTool.from_dict({
            "tool_name": tool.tool_name,
            "tool_id": tool.tool_id,
            "type": tool.type,
            "config": tool.config,
            "owner": tool.owner,
            "gmt_create": tool.gmt_create,
            "gmt_modified": tool.gmt_modified
        }) for tool in result]
        return gpts_tools

    def get_tool_by_tool_id(self, tool_id: str):
        session = self.get_raw_session()
        tool_query = session.query(GptsToolEntity)
        if tool_id:
            tool_query = tool_query.filter(GptsToolEntity.tool_id == tool_id)
        result = tool_query.first()
        session.close()
        if result is None:
            return None
        gpt_tools = GptsTool.from_dict({
            "tool_name": result.tool_name,
            "tool_id": result.tool_id,
            "type": result.type,
            "config": result.config,
            "owner": result.owner,
            "gmt_create": result.gmt_create,
            "gmt_modified": result.gmt_modified
        })
        return gpt_tools


class GptsToolDetail(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: Optional[int] = None
    gmt_create: datetime = datetime.utcnow
    gmt_modified: datetime = datetime.utcnow
    tool_id: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    sub_name: Optional[str] = None
    description: Optional[str] = None
    sub_description: Optional[str] = None
    input_schema: Optional[str] = None

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
            id=d.get("id", None),
            gmt_create=d.get("gmt_create", None),
            gmt_modified=d.get("gmt_modified", None),
            tool_id=d["tool_id"],
            type=d["type"],
            name=d["name"],
            sub_name=d.get("sub_name", None),
            description=d.get("description", None),
            sub_description=d.get("sub_description", None),
            input_schema=d.get("input_schema", None)
        )


class GptsToolDetailEntity(Model):
    __tablename__ = "gpts_tool_detail"
    id = Column(Integer, primary_key=True, comment="autoincrement id")
    gmt_create = Column(DateTime, name="gmt_create", default=datetime.utcnow, comment="create time")
    gmt_modified = Column(DateTime, name="gmt_modified", default=datetime.utcnow, onupdate=datetime.utcnow,
                          comment="last update time", )
    tool_id = Column(String(255), nullable=False, comment="tool id")
    type = Column(String(255), nullable=False, comment="tool type, http/tr/local/mcp")
    name = Column(String(255), nullable=False, comment="tool name")
    sub_name = Column(String(255), nullable=True, comment="tool sub name")
    description = Column(Text, nullable=True, comment="tool description")
    sub_description = Column(Text, nullable=True, comment="tool sub description")
    input_schema = Column(Text, nullable=True, comment="tool detail config")

    __table_args__ = (Index("idx_detail_tool_id", "tool_id")),


class GptsToolDetailDao(BaseDao):
    def create(self, gpts_tool_detail: GptsToolDetail):
        session = self.get_raw_session()
        tool_detail_entity = GptsToolDetailEntity(
            tool_id=gpts_tool_detail.tool_id,
            type=gpts_tool_detail.type,
            name=gpts_tool_detail.name,
            sub_name=gpts_tool_detail.sub_name,
            description=gpts_tool_detail.description,
            sub_description=gpts_tool_detail.sub_description,
            input_schema=gpts_tool_detail.input_schema
        )
        session.add(tool_detail_entity)
        session.commit()
        session.close()
        return gpts_tool_detail

    def update(self, gpts_tool_detail: GptsToolDetail):
        session = self.get_raw_session()
        tool_detail_query = session.query(GptsToolDetailEntity)
        if gpts_tool_detail.tool_id is None:
            raise Exception("tool_id is None, don't allow to edit!")
        tool_detail_query = tool_detail_query.filter(
            GptsToolDetailEntity.id == gpts_tool_detail.id
        )
        update_params = {}
        if gpts_tool_detail.type:
            update_params[GptsToolDetailEntity.type] = gpts_tool_detail.type
        if gpts_tool_detail.name:
            update_params[GptsToolDetailEntity.name] = gpts_tool_detail.name
        if gpts_tool_detail.sub_name:
            update_params[GptsToolDetailEntity.sub_name] = gpts_tool_detail.sub_name
        if gpts_tool_detail.description:
            update_params[GptsToolDetailEntity.description] = gpts_tool_detail.description
        if gpts_tool_detail.sub_description:
            update_params[GptsToolDetailEntity.sub_description] = gpts_tool_detail.sub_description
        if gpts_tool_detail.input_schema:
            update_params[GptsToolDetailEntity.input_schema] = gpts_tool_detail.input_schema
        tool_detail_query.update(update_params, synchronize_session="fetch")
        session.commit()
        session.close()

    def query(self, gpts_tool_detail: GptsToolDetail):
        session = self.get_raw_session()
        tool_detail_query = session.query(GptsToolDetailEntity)
        if gpts_tool_detail.id:
            tool_detail_query = tool_detail_query.filter(GptsToolDetailEntity.id == gpts_tool_detail.id)
        if gpts_tool_detail.type:
            tool_detail_query = tool_detail_query.filter(GptsToolDetailEntity.type == gpts_tool_detail.type)
        if gpts_tool_detail.tool_id:
            tool_detail_query = tool_detail_query.filter(GptsToolDetailEntity.tool_id == gpts_tool_detail.tool_id)
        if gpts_tool_detail.name:
            tool_detail_query = tool_detail_query.filter(GptsToolDetailEntity.name == gpts_tool_detail.name)
        if gpts_tool_detail.sub_name:
            tool_detail_query = tool_detail_query.filter(GptsToolDetailEntity.sub_name == gpts_tool_detail.sub_name)
        result = tool_detail_query.all()
        session.close()
        if result is None:
            return None
        gpts_tool_details = [GptsToolDetail.from_dict({
            "id": tool_detail.id,
            "gmt_create": tool_detail.gmt_create,
            "gmt_modified": tool_detail.gmt_modified,
            "tool_id": tool_detail.tool_id,
            "type": tool_detail.type,
            "name": tool_detail.name,
            "sub_name": tool_detail.sub_name,
            "description": tool_detail.description,
            "sub_description": tool_detail.sub_description,
            "input_schema": tool_detail.input_schema
        }) for tool_detail in result]
        return gpts_tool_details

    def delete(self, id: str):
        session = self.get_raw_session()
        tool_query = session.query(GptsToolDetailEntity)
        tool_query = tool_query.filter(str(GptsToolDetailEntity.id) == id)
        tool_query.delete()
        session.commit()
        session.close()


class ExecuteToolRequest(BaseModel):
    type: str
    config: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, Any]] = None


class LocalToolConfig(BaseModel):
    class_name: str
    method_name: str
    description: Optional[str] = None
    input_schema: Optional[str] = None


class APIToolConfig(BaseModel):
    url: str
    method: str
    headers: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    input_schema: Optional[str] = None


class TrParams(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    value: Optional[Any] = None


class TRToolConfig(BaseModel):
    name: str
    description: str
    packageName: str
    protocol: str
    headers: Optional[Dict] = None
    inputSchema: Optional[Dict] = None
    outputSchema: Optional[Dict] = None
    tenant: Optional[str] = None
    paramsList: Optional[List[TrParams]] = None
    plugin: Optional[str] = None
    script: Optional[Dict] = None
    timeout: Optional[int] = 60
    vipUrl: Optional[str] = None
    vipEnforce: Optional[bool] = False
    vipOnly: Optional[bool] = False


class DbQueryRequest(BaseModel):
    sql: str
    database: str
    host: str
    port: int = 2883
    user: str
    password: str
    params: Optional[object]
