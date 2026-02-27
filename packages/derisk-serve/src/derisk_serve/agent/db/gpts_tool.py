import json
import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, List
from httpx import AsyncClient, Timeout
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    select,
)

from derisk._private.pydantic import (
    BaseModel,
    ConfigDict,
)
from derisk.storage.metadata import BaseDao, Model

logger = logging.getLogger(__name__)
NEX_DOMAIN = {
    "prepub": "http://localhost:7777",
    "prod": "http://localhost:7777",
}


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

    async def a_get_tool_by_tool_id(self, tool_id: str):
        async with self.a_session(commit=False) as session:
            stmt = select(GptsToolEntity).limit(1)
            if tool_id:
                stmt = stmt.where(GptsToolEntity.tool_id == tool_id)
            rows = await session.execute(stmt)
            result = rows.scalar_one_or_none()
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

    async def a_get_tool_by_name(self, name: str) -> Optional[GptsTool]:
        """根据 tool_name 查询工具（异步版本）

        Args:
            name: 工具名称

        Returns:
            GptsTool 对象，如果找不到则返回 None
        """
        async with self.a_session(commit=False) as session:
            stmt = select(GptsToolEntity).limit(1)
            if name:
                stmt = stmt.where(GptsToolEntity.tool_name == name)
            rows = await session.execute(stmt)
            result = rows.scalar_one_or_none()
            if result is None:
                return None
            return GptsTool.from_dict({
                "tool_name": result.tool_name,
                "tool_id": result.tool_id,
                "type": result.type,
                "config": result.config,
                "owner": result.owner,
                "gmt_create": result.gmt_create,
                "gmt_modified": result.gmt_modified
            })

    async def get_tools_by_tool_ids(self, tool_ids: list) -> List[GptsTool]:
        """根据 tool_id 列表批量查询工具

        Args:
            tool_ids: tool_id 列表

        Returns:
            GptsTool 列表
        """
        if not tool_ids:
            return []
        async with self.a_session(commit=False) as session:
            stmt = select(GptsToolEntity).where(GptsToolEntity.tool_id.in_(tool_ids))
            rows = await session.execute(stmt)
            results = rows.scalars().all()
            if not results:
                return []
            return [GptsTool.from_dict({
                "tool_name": result.tool_name,
                "tool_id": result.tool_id,
                "type": result.type,
                "config": result.config,
                "owner": result.owner,
                "gmt_create": result.gmt_create,
                "gmt_modified": result.gmt_modified
            }) for result in results]


    async def get_tools_by_names(self, tool_names: list) -> List[GptsTool]:
        """根据 tool_name 列表批量查询工具

        Args:
            tool_names: tool_name 列表

        Returns:
            GptsTool 列表
        """
        if not tool_names:
            return []
        async with self.a_session(commit=False) as session:
            stmt = select(GptsToolEntity).where(GptsToolEntity.tool_name.in_(tool_names))
            rows = await session.execute(stmt)
            results = rows.scalars().all()
            if not results:
                return []
            return [GptsTool.from_dict({
                "tool_name": result.tool_name,
                "tool_id": result.tool_id,
                "type": result.type,
                "config": result.config,
                "owner": result.owner,
                "gmt_create": result.gmt_create,
                "gmt_modified": result.gmt_modified
            }) for result in results]

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
    category: Optional[str] = None
    tag: Optional[str] = None
    owner: Optional[str] = None

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
            input_schema=d.get("input_schema", None),
            category=d.get("category", None),
            tag=d.get("tag", None),
            owner=d.get("owner", None)
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
    category = Column(String(255), nullable=True, comment="tool category")
    tag = Column(String(255), nullable=True, comment="tool tag")
    owner = Column(String(255), nullable=True, comment="tool owner")

    __table_args__ = (Index("idx_tool_detail_id", "tool_id")),


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
            input_schema=gpts_tool_detail.input_schema,
            category=gpts_tool_detail.category,
            tag=gpts_tool_detail.tag,
            owner=gpts_tool_detail.owner
        )
        session.add(tool_detail_entity)
        session.commit()
        session.close()
        return gpts_tool_detail

    def update(self, gpts_tool_detail: GptsToolDetail):
        session = self.get_raw_session()
        tool_detail_query = session.query(GptsToolDetailEntity)
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
        if gpts_tool_detail.category:
            update_params[GptsToolDetailEntity.category] = gpts_tool_detail.category
        if gpts_tool_detail.tag:
            update_params[GptsToolDetailEntity.tag] = gpts_tool_detail.tag
        if gpts_tool_detail.owner:
            update_params[GptsToolDetailEntity.owner] = gpts_tool_detail.owner
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
        if gpts_tool_detail.category:
            tool_detail_query = tool_detail_query.filter(gpts_tool_detail.category in GptsToolDetailEntity.category)
        if gpts_tool_detail.tag:
            tool_detail_query = tool_detail_query.filter(gpts_tool_detail.tag in GptsToolDetailEntity.tag)
        if gpts_tool_detail.owner:
            tool_detail_query = tool_detail_query.filter(GptsToolDetailEntity.owner == gpts_tool_detail.owner)
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
            "input_schema": tool_detail.input_schema,
            "category": tool_detail.category,
            "tag": tool_detail.tag,
            "owner": tool_detail.owner
        }) for tool_detail in result]
        return gpts_tool_details

    def query_all(self):
        session = self.get_raw_session()
        tool_detail_query = session.query(GptsToolDetailEntity)
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
            "input_schema": tool_detail.input_schema,
            "category": tool_detail.category,
            "tag": tool_detail.tag,
            "owner": tool_detail.owner
        }) for tool_detail in result]
        return gpts_tool_details

    def delete(self, id):
        session = self.get_raw_session()
        tool_query = session.query(GptsToolDetailEntity)
        tool_query = tool_query.filter(GptsToolDetailEntity.id == id)
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
    uniqueId: Optional[str] = None

class HTTPToolConfig(BaseModel):
    name: str
    description: str
    protocol: str
    url: str
    method: str
    preUrl: Optional[str] = None
    headers: Optional[Dict] = None
    inputSchema: Optional[Dict] = None
    outputSchema: Optional[Dict] = None
    script: Optional[Dict] = None
    timeout: Optional[int] = 60
    stream: Optional[bool] = False

class DbQueryRequest(BaseModel):
    sql: str
    database: str
    host: str
    port: int = 2883
    user: str
    password: str
    params: Optional[object]



async def execute_script_and_get_function(script_content):
    global_namespace = {}
    exec(script_content, global_namespace)
    return global_namespace.get('convert_response')


async def _execute_stream_generator(config: HTTPToolConfig, params: dict):
    """流式HTTP请求处理"""
    async with AsyncClient(timeout=Timeout(timeout=config.timeout), verify=False) as client:
        try:
            async with client.stream(config.method, config.url, headers=config.headers, json=params) as response:
                if response.status_code != 200:
                    error = {'data': f"{response}"}
                    yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
                    return
                convert_func = None
                if config.script.get('respCheck') and config.script.get('response'):
                    convert_func = await execute_script_and_get_function(config.script.get('response'))
                async for line in response.aiter_lines():
                    if asyncio.current_task().cancelled():
                        break
                    if line.strip():
                        if not line.startswith("data:"):
                            result = {'data': line}
                            yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                            continue
                        data_part = line[5:]
                        # 检查是否是结束标志
                        if data_part.strip() == "[DONE]":
                            break
                        if convert_func:
                            try:
                                new_data = convert_func(data_part)
                                if new_data is None:
                                    continue
                                result = {'data': new_data}
                                yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
                            except Exception as e:
                                logger.error('[execute_http_tool]transform response fail: error: %s', str(e))
                        else:
                            result = {'data': data_part}
                            yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
        except Exception as e:
            error = {'data': str(e)}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"


async def _execute_stream_with_queue(
        config: HTTPToolConfig,
        params: dict,
        queue: Optional[asyncio.Queue] = None
) -> str:
    """流式处理并收集所有结果返回拼接后的字符串"""
    result = []

    convert_func = None
    if config.script.get('respCheck') and config.script.get('response'):
        convert_func = await execute_script_and_get_function(config.script.get('response'))
    async with AsyncClient(timeout=Timeout(timeout=config.timeout), verify=False) as client:
        try:
            async with client.stream(config.method, config.url, headers=config.headers, json=params) as response:
                if response.status_code != 200:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    if queue:
                        await queue.put(error_msg)
                    return error_msg
                async for line in response.aiter_lines():
                    if asyncio.current_task().cancelled():
                        break
                    if line.strip():
                        data_part = line[5:] if line.startswith("data:") else line
                        # 检查是否是结束标志
                        if data_part.strip() == "[DONE]":
                            break
                        if convert_func:
                            try:
                                data_part = convert_func(data_part)
                            except Exception as e:
                                logger.error('[execute_http_tool]transform response fail: error: %s', str(e))

                        if data_part is None:
                            continue
                        if queue:
                            await queue.put(data_part)
                        result.append(data_part)
        except Exception as e:
            error_msg = str(e)
            logger.error('[execute_http_tool]stream request fail: error: %s', error_msg)
            if queue:
                await queue.put(error_msg)
            return error_msg
    return ''.join(result)



def filter_response_by_schema(response_data: Any, schema: Dict[str, Any]) -> Any:
    """
    根据 schema 过滤和校验响应数据

    Args:
        response_data: HTTP 响应的 JSON 数据
        schema: 输出 schema 定义

    Returns:
        过滤后的数据
    """

    def validate_and_filter_object(data: Dict[str, Any], obj_schema: Dict[str, Any], is_root: bool = False) -> Dict[str, Any]:
        """递归处理对象类型的数据"""
        if not isinstance(data, dict):
            raise ValueError(f"Expected object, got {type(data).__name__}")

        result = {}
        properties = obj_schema.get("properties", {})

        for field_name, field_schema in properties.items():
            key = field_schema.get("key", field_name)
            field_type = field_schema.get("type", "string")
            is_selected = field_schema.get("selected", False)

            # 对于根级别的包装对象，即使 selected=false，也要检查其内部属性
            if is_root and field_type == "object" and "properties" in field_schema:
                # 检查内部是否有 selected=true 的字段
                inner_properties = field_schema.get("properties", {})
                has_selected_children = any(
                    prop.get("selected", False) for prop in inner_properties.values()
                )

                if has_selected_children:
                    # 递归处理内部对象，但将结果直接合并到当前级别
                    inner_result = validate_and_filter_object(data, field_schema, is_root=False)
                    result.update(inner_result)
                continue

            # 普通字段处理：只处理 selected=true 的字段
            if not is_selected:
                continue

            # 检查字段是否存在
            if key not in data:
                continue

            field_value = data[key]

            # 类型校验和转换
            validated_value = validate_field_type(field_value, field_type, field_schema)
            result[key] = validated_value

        return result

    def validate_field_type(value: Any, expected_type: str, field_schema: Dict[str, Any]) -> Any:
        """校验字段类型"""
        if value is None:
            if field_schema.get("required", False):
                raise ValueError(f"Required field cannot be null")
            return None

        if expected_type == "string":
            if not isinstance(value, str):
                return str(value)
            return value

        elif expected_type == "integer":
            if isinstance(value, int):
                return value
            elif isinstance(value, str) and value.isdigit():
                return int(value)
            else:
                raise ValueError(f"Cannot convert {value} to integer")

        elif expected_type == "boolean":
            if isinstance(value, bool):
                return value
            elif isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            elif isinstance(value, int):
                return bool(value)
            else:
                raise ValueError(f"Cannot convert {value} to boolean")

        elif expected_type == "object":
            if value is None:
                return None

            if isinstance(value, dict):
                if "properties" in field_schema:
                    return validate_and_filter_object(value, field_schema, is_root=False)
                return value

            return value

        elif expected_type == "array":
            if not isinstance(value, list):
                raise ValueError(f"Expected array, got {type(value).__name__}")
            return value

        else:
            return value

    # 处理响应数据是 list 的情况
    if isinstance(response_data, list):
        if not response_data:
            return []

        if schema.get("type") == "Object" and "properties" in schema:
            if all(isinstance(item, dict) for item in response_data):
                return [validate_and_filter_object(item, schema, is_root=True) for item in response_data]

        return response_data

    # 处理响应数据是 dict 的情况
    elif isinstance(response_data, dict):
        if schema.get("type") == "Object" and "properties" in schema:
            return validate_and_filter_object(response_data, schema, is_root=True)
        else:
            raise ValueError("Invalid schema format")

    else:
        return response_data