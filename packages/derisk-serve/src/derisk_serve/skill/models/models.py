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
from derisk.util import PaginationResult

from ..api.schemas import SkillRequest, SkillResponse, SkillQueryFilter
from ..config import SERVER_APP_TABLE_NAME, ServeConfig

# Reuse the table name constant or define a new one for skills if needed
SKILL_TABLE_NAME = "server_app_skill"

class SkillEntity(Model):
    __tablename__ = SKILL_TABLE_NAME

    skill_code = Column(String(255), primary_key=True, nullable=False, comment="skill code")
    name = Column(String(255), nullable=False, comment="skill name")
    description = Column(Text, nullable=False, comment="skill description")
    type = Column(String(255), nullable=False, comment="skill type")
    author = Column(String(255), nullable=True, comment="skill author")
    email = Column(String(255), nullable=True, comment="skill author email")

    version = Column(String(255), nullable=True, comment="skill version")
    path = Column(Text, nullable=True, comment="skill path")
    content = Column(Text, nullable=True, comment="skill content (markdown)")
    icon = Column(Text, nullable=True, comment="skill icon")
    category = Column(Text, nullable=True, comment="skill category")
    installed = Column(Integer, nullable=True, comment="skill already installed count")
    available = Column(Boolean, nullable=True, comment="skill already available")
    
    repo_url = Column(Text, nullable=True, comment="git repository url")
    branch = Column(String(255), nullable=True, comment="git branch")
    commit_id = Column(String(255), nullable=True, comment="git commit id")
    auto_sync = Column(Boolean, nullable=True, default=True, comment="whether to auto-sync this skill on startup")

    gmt_created = Column(DateTime, name='gmt_create', default=datetime.now, comment="Record creation time")
    gmt_modified = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="Record update time")

    def __repr__(self):
        return (
            f"SkillEntity(skill_code={self.skill_code}, name='{self.name}', "
            f"gmt_created='{self.gmt_created}', "
            f"gmt_modified='{self.gmt_modified}')"
        )


class SkillDao(BaseDao[SkillEntity, SkillRequest, SkillResponse]):
    """The DAO class for Skill"""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def from_request(self, request: Union[SkillRequest, Dict[str, Any]]) -> SkillEntity:
        request_dict = (
            request.dict() if isinstance(request, SkillRequest) else request
        )

        # Filter out read-only fields
        request_dict.pop('gmt_created', None)
        request_dict.pop('gmt_modified', None)

        entity = SkillEntity(**request_dict)
        return entity

    def to_request(self, entity: SkillEntity) -> SkillRequest:
        return SkillRequest(
            skill_code=entity.skill_code,
            name=entity.name,
            description=entity.description,
            type=entity.type,
            author=entity.author,
            email=entity.email,
            version=entity.version,
            path=entity.path,
            content=entity.content,
            icon=entity.icon,
            category=entity.category,
            installed=entity.installed,
            available=entity.available,
            repo_url=entity.repo_url,
            branch=entity.branch,
            commit_id=entity.commit_id,
            auto_sync=entity.auto_sync,
        )

    def to_response(self, entity: SkillEntity) -> SkillResponse:
        return SkillResponse(
            skill_code=entity.skill_code,
            name=entity.name,
            description=entity.description,
            type=entity.type,
            author=entity.author,
            email=entity.email,
            version=entity.version,
            path=entity.path,
            content=entity.content,
            icon=entity.icon,
            category=entity.category,
            installed=entity.installed,
            available=entity.available,
            repo_url=entity.repo_url,
            branch=entity.branch,
            commit_id=entity.commit_id,
            auto_sync=entity.auto_sync,
            gmt_created=entity.gmt_created.isoformat() if entity.gmt_created else None,
            gmt_modified=entity.gmt_modified.isoformat() if entity.gmt_modified else None,
        )


    def filter_list_page(
        self,
        query_request: SkillQueryFilter,
        page: int,
        page_size: int,
        desc_order_column: Optional[str] = None,
    ) -> PaginationResult[SkillResponse]:
        """Get a page of skill.

        Args:
            query_request (SkillQueryFilter): The request schema object or dict for query.
            page (int): The page number.
            page_size (int): The page size.
            desc_order_column(Optional[str]): The column for descending order.
        Returns:
            PaginationResult: The pagination result.
        """
        session = self.get_raw_session()
        try:
            query = session.query(SkillEntity)
            if query_request.filter:
                query = query.filter(or_(SkillEntity.name.like(f"%{query_request.filter}%"), SkillEntity.description.like(f"%{query_request.filter}%")))

            if desc_order_column:
                query = query.order_by(desc(getattr(SkillEntity, desc_order_column)))
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
