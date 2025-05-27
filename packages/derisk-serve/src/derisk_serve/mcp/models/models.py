"""This is an auto-generated model file
You can define your own models and DAOs here
"""
import json
from datetime import datetime
from typing import Any, Dict, Union, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    and_,
    desc,
    or_,
)

from derisk.storage.metadata import BaseDao, Model
from derisk.storage.metadata._base_dao import QUERY_SPEC
from derisk.util import PaginationResult

from ..api.schemas import ServeRequest, ServerResponse, QueryFilter
from ..config import SERVER_APP_TABLE_NAME, ServeConfig


class ServeEntity(Model):
    __tablename__ = SERVER_APP_TABLE_NAME
    id = Column(Integer, primary_key=True, nullable=False, comment="Auto increment id")

    name = Column(String(255), nullable=False, comment="mcp name")
    description = Column(Text, nullable=False, comment="mcp description")
    type = Column(String(255), nullable=False, comment="mcp type")
    author = Column(String(255), nullable=True, comment="mcp author")
    email = Column(String(255), nullable=True, comment="mcp author email")

    version = Column(String(255), nullable=True, comment="mcp version")
    stdio_cmd = Column(Text, nullable=True, comment="mcp stdio cmd")
    sse_url = Column(Text, nullable=True, comment="mcp sse connect url")
    sse_headers = Column(Text(length=2 ** 31 - 1), nullable=True, comment="mcp sse connect headers")
    token = Column(Text(length=2 ** 31 - 1), nullable=True, comment="mcp sse connect token")
    icon = Column(Text, nullable=True, comment="mcp icon")
    category = Column(Text, nullable=True, comment="mcp category")
    installed = Column(Integer, nullable=True, comment="mcp already installed count")
    available = Column(Boolean, nullable=True, comment="mcp already available")
    server_ips = Column(Text, nullable=True, comment="mcp server run machine ips")
    gmt_created = Column(DateTime, name='gmt_create', default=datetime.now, comment="Record creation time")
    gmt_modified = Column(DateTime, default=datetime.now, comment="Record update time")

    def __repr__(self):
        return (
            f"ServeEntity(id={self.id}, gmt_created='{self.gmt_created}', "
            f"gmt_modified='{self.gmt_modified}')"
        )


class ServeDao(BaseDao[ServeEntity, ServeRequest, ServerResponse]):
    """The DAO class for Mcp"""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[ServeRequest, Dict[str, Any]]) -> ServeEntity:
        request_dict = (
            request.dict() if isinstance(request, ServeRequest) else request
        )

        # 处理 JSON 字段序列化
        if 'sse_headers' in request_dict and isinstance(request_dict['sse_headers'], dict):
            request_dict['sse_headers'] = json.dumps(request_dict['sse_headers'])

        # 过滤掉只读字段（如自动生成的 id 和时间戳）
        request_dict.pop('id', None)
        request_dict.pop('gmt_created', None)
        request_dict.pop('gmt_modified', None)

        entity = ServeEntity(**request_dict)
        return entity

    def to_request(self, entity: ServeEntity) -> ServeRequest:
        # 转换 JSON 字段
        sse_headers = json.loads(entity.sse_headers) if entity.sse_headers else None

        return ServeRequest(
            name=entity.name,
            description=entity.description,
            type=entity.type,
            author=entity.author,
            email=entity.email,
            version=entity.version,
            stdio_cmd=entity.stdio_cmd,
            sse_url=entity.sse_url,
            sse_headers=sse_headers,
            token=entity.token,
            icon=entity.icon,
            category=entity.category,
            installed=entity.installed,
            available=entity.available,
            server_ips=entity.server_ips,
        )

    def to_response(self, entity: ServeEntity) -> ServerResponse:
        # 转换 JSON 字段和日期时间
        sse_headers = json.loads(entity.sse_headers) if entity.sse_headers else None

        return ServerResponse(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            type=entity.type,
            author=entity.author,
            email=entity.email,
            version=entity.version,
            stdio_cmd=entity.stdio_cmd,
            sse_url=entity.sse_url,
            sse_headers=sse_headers,
            token=entity.token,
            icon=entity.icon,
            category=entity.category,
            installed=entity.installed,
            available=entity.available,
            server_ips=entity.server_ips,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else None,
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else None,
        )


    def filter_list_page(
        self,
        query_request: QueryFilter,
        page: int,
        page_size: int,
        desc_order_column: Optional[str] = None,
    ) -> PaginationResult[ServerResponse]:
        """Get a page of mcp.

        Args:
            query_request (ServeRequest): The request schema object or dict for query.
            page (int): The page number.
            page_size (int): The page size.
            desc_order_column(Optional[str]): The column for descending order.
        Returns:
            PaginationResult: The pagination result.
        """
        session = self.get_raw_session()
        try:
            query = session.query(ServeEntity)
            if query_request.filter:
                query = query.filter(or_(ServeEntity.name.like(f"%{query_request.filter}%"), ServeEntity.description.like(f"%{query_request.filter}%")))

            if desc_order_column:
                query = query.order_by(desc(getattr(ServeEntity, desc_order_column)))
            total_count = query.count()
            items = query.offset((page - 1) * page_size).limit(page_size)
            res_items = [self.to_response(item) for item in items]
            total_pages = (total_count + page_size - 1) // page_size
        finally:
            session.close()

        return PaginationResult(
            items=res_items,
            total_count=total_count,
            total_pages=total_pages,
            page=page,
            page_size=page_size,
        )
