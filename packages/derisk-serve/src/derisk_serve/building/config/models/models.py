"""This is an auto-generated model file
You can define your own models and DAOs here
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Union, Optional, List, Type
from derisk._private.pydantic import BaseModel
from derisk.agent import AgentResource
from derisk.agent.core.plan.base import SingleAgentContext, TeamContext
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.core.schema import DynamicParam
from derisk.context.utils import build_by_agent_config
from derisk.context.operator import GroupedConfigItem
from derisk.storage.metadata import BaseDao, Model
from derisk.storage.metadata._base_dao import REQ, RES
from derisk.vis.vis_manage import get_vis_manager
from derisk_serve.agent.model import NativeTeamContext

from ..api.schemas import ServeRequest, ServerResponse, Layout, LLMResource
from ..config import SERVER_APP_TABLE_NAME, ServeConfig
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    SmallInteger,
    UniqueConstraint,
    or_,
)

logger = logging.getLogger(__name__)


class ServeEntity(Model):
    __tablename__ = "gpts_app_config"
    id = Column(Integer, primary_key=True, comment="Auto increment id")

    code = Column(String(100), nullable=False, comment="当前配置代码")
    app_code = Column(String(100), nullable=False, comment="应用代码")
    team_mode = Column(String(255), nullable=False, comment="当前版本配置的对话模式")
    team_context = Column(Text, nullable=True, comment="应用当前版本的TeamContext信息")
    resources = Column(
        Text(length=2**31 - 1), nullable=True, comment="应用当前版本的Resources信息"
    )
    details = Column(
        String(2000), nullable=True, comment="应用当前版本的小弟details信息"
    )
    recommend_questions = Column(
        Text, nullable=True, comment="当前版本配置设定的推进问题信息"
    )
    version_info = Column(String(1000), nullable=False, comment="版本信息")
    creator = Column(String(255), nullable=True, comment="创建者(域账户)")
    description = Column(String(1000), nullable=True, comment="当前版本配置的备注描述")
    is_published = Column(
        SmallInteger, nullable=True, default=0, comment="当前版本配置的备注描述"
    )
    gmt_last_edit = Column(
        DateTime, nullable=True, comment="当前版本配置最后一次内容编辑时间"
    )
    editor = Column(String(255), nullable=True, comment="当前版本配置最后修改者")
    ext_config = Column(
        Text(length=2**31 - 1),
        nullable=True,
        comment="当前版本配置的扩展配置，各自动态扩展的内容",
    )
    runtime_config = Column(
        Text(length=2**31 - 1),
        nullable=True,
        comment="Agent运行时配置，包含DoomLoop检测、Loop执行、WorkLog压缩等",
    )
    system_prompt_template = Column(
        Text, nullable=True, comment="当前版本配置的system prompt模版"
    )
    user_prompt_template = Column(
        Text, nullable=True, comment="当前版本配置的user prompt模版"
    )

    layout = Column(String(255), nullable=True, comment="当前版本配置的布局配置")
    custom_variables = Column(
        String(2000), nullable=True, comment="当前版本配置自定义参数配置"
    )
    llm_config = Column(Text, nullable=True, comment="当前版本配置的模型配置")
    resource_knowledge = Column(Text, nullable=True, comment="当前版本配置的知识配置")
    resource_tool = Column(Text, nullable=True, comment="当前版本配置的工具配置")
    resource_agent = Column(Text, nullable=True, comment="当前版本配置的agent配置")
    context_config = Column(String(2000), nullable=True, comment="上下文工程配置")
    agent_version = Column(
        String(32), nullable=True, default="v1", comment="agent version: v1 or v2"
    )

    gmt_create = Column(DateTime, default=datetime.now, comment="Record creation time")
    gmt_modified = Column(DateTime, default=datetime.now, comment="Record update time")

    __table_args__ = (
        UniqueConstraint("code", name="uk_config_version"),
        Index("idx_app_config", "app_code", "is_published"),
    )

    def __repr__(self):
        return (
            f"ServeEntity(id={self.id}, code={self.code},app_code={self.app_code},version_info={self.version_info}, gmt_created='{self.gmt_created}', "
            f"gmt_modified='{self.gmt_modified}')"
        )


def _load_team_context(
    team_mode: Optional[str] = None,
    team_context: Optional[Union[str, dict]] = None,
    agent_version: Optional[str] = None,
) -> Optional[Union[str, SingleAgentContext, AutoTeamContext]]:
    """
    load team_context to str or AWELTeamContext
    """

    def _str_to_team_context(
        cls_type: Type[Union[TeamContext, BaseModel]], content: Optional[str] = None
    ) -> Optional[TeamContext]:
        try:
            agent_ctx = None
            if team_context:
                if isinstance(team_context, str):
                    agent_ctx = cls_type(**json.loads(team_context))
                elif isinstance(team_context, dict) and cls_type.model_validate(
                    team_context
                ):
                    agent_ctx = cls_type(**team_context)
                else:
                    logger.warning(f"无法解析的TeamContext数据：{team_context}")
            return agent_ctx
        except Exception as ex:
            logger.warning(
                f"_load_team_context error, team_mode={team_mode}, "
                f"team_context={team_context}, {ex}"
            )
            return None

    actual_version = agent_version or "v1"
    is_v2 = actual_version == "v2"

    if is_v2:
        from derisk.agent.core.plan.unified_context import UnifiedTeamContext

        return _str_to_team_context(UnifiedTeamContext, team_context)

    if team_mode is not None:
        from derisk_serve.agent.team.base import TeamMode

        match team_mode:
            case TeamMode.SINGLE_AGENT.value:
                return _str_to_team_context(SingleAgentContext, team_context)

            case TeamMode.AUTO_PLAN.value:
                return _str_to_team_context(AutoTeamContext, team_context)

    return team_context


def _load_resource(resource: Optional[str] = None):
    if resource:
        resource_obj = json.loads(resource)
        return [AgentResource(**item) for item in resource_obj]
    else:
        return None


def _load_llm_config(llm_config_str: Optional[str] = None):
    if llm_config_str:
        llm_config_obj = json.loads(llm_config_str)
        return LLMResource(**llm_config_obj)
    else:
        return None


def _load_layout(layout: Optional[str] = None):
    if layout:
        layout_obj = json.loads(layout)
        layout = Layout(**layout_obj)
        vis_manager = get_vis_manager()
        vis_convert = vis_manager.get(layout.chat_layout.name)
        layout.chat_layout.reuse_name = vis_convert.reuse_name
        return layout
    else:
        return None


def _load_variable(custom_variables: Optional[str] = None):
    if custom_variables:
        variables_obj = json.loads(custom_variables)
        return [DynamicParam(**item) for item in variables_obj]
    else:
        return None


def _load_context_config(context_config: str):
    reference = None
    if context_config:
        try:
            context_dict = json.loads(context_config)
            reference = GroupedConfigItem.model_validate(context_dict)
        except Exception as e:
            logger.exception(f"_load_context_config except: f{repr(e)}")
            # raise

    return build_by_agent_config(reference)


class ServeDao(BaseDao[ServeEntity, ServeRequest, ServerResponse]):
    """The DAO class for App"""

    def __init__(self, serve_config: ServeConfig):
        super().__init__()
        self._serve_config = serve_config

    def create(self, request: REQ) -> RES:
        entry = self.from_request(request)
        with self.session(commit=False) as session:
            session.add(entry)
            session.commit()
            res = self.get_one({"code": entry.code})
            return res  # type: ignore

    def to_update_dict(self, request: ServeRequest):
        def _bm_to_str(bms: Optional[List]):
            if bms:
                if isinstance(bms[0], BaseModel):
                    return json.dumps(
                        [item.to_dict() for item in bms], ensure_ascii=False
                    )
                elif hasattr(bms[0], "__dict__"):
                    return json.dumps(
                        [item.__dict__ for item in bms], ensure_ascii=False
                    )
                else:
                    return json.dumps([item for item in bms], ensure_ascii=False)
            else:
                return None

        return {
            "team_mode": request.team_mode,
            "team_context": json.dumps(
                request.team_context.to_dict(), ensure_ascii=False
            )
            if request.team_context
            else None,
            "resources": _bm_to_str(request.resources),
            "details": _bm_to_str(request.details),
            "ext_config": json.dumps(request.ext_config, ensure_ascii=False),
            "runtime_config": json.dumps(request.runtime_config, ensure_ascii=False)
            if getattr(request, "runtime_config", None)
            else None,
            "recommend_questions": _bm_to_str(request.recommend_questions),
            "gmt_last_edit": request.gmt_last_edit,
            "editor": request.editor,
            "layout": json.dumps(request.layout.to_dict(), ensure_ascii=False)
            if request.layout
            else None,
            "custom_variables": _bm_to_str(request.custom_variables),
            "llm_config": json.dumps(request.llm_config.to_dict(), ensure_ascii=False)
            if request.llm_config
            else None,
            "resource_knowledge": _bm_to_str(request.resource_knowledge),
            "resource_tool": _bm_to_str(request.resource_tool),
            "resource_agent": _bm_to_str(request.resource_agent),
            "system_prompt_template": request.system_prompt_template,
            "user_prompt_template": request.user_prompt_template,
            "context_config": json.dumps(
                request.context_config.to_dict(), ensure_ascii=False
            )
            if request.context_config
            else None,
            "agent_version": getattr(request, "agent_version", "v1") or "v1",
        }

    def to_db_dict(self, request: ServeRequest):
        result_dict = self.to_update_dict(request)

        result_dict.update(
            {
                "app_code": request.app_code,
                "code": request.code,
                "team_mode": request.team_mode,
                "version_info": request.version_info,
                "creator": request.creator,
                "description": request.description,
                "is_published": request.is_published,
                "gmt_last_edit": request.gmt_last_edit,
                "editor": request.editor,
                "gmt_create": request.gmt_create,
                "gmt_modified": request.gmt_modified,
            }
        )
        return result_dict

    def from_request(self, request: Union[ServeRequest, Dict[str, Any]]) -> ServeEntity:
        """Convert the request to an entity

        Args:
            request (Union[ServeRequest, Dict[str, Any]]): The request

        Returns:
            T: The entity
        """

        if isinstance(request, ServeRequest):
            request_dict = self.to_db_dict(request)
        else:
            request_dict = request
        entity = ServeEntity(**request_dict)  # type: ignore

        return entity

    def to_request(self, entity: ServeEntity) -> ServeRequest:
        """Convert the entity to a request"""
        gmt_created_str = (
            entity.gmt_create.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_create
            else None
        )
        gmt_modified_str = (
            entity.gmt_modified.strftime("%Y-%m-%d %H:%M:%S")
            if entity.gmt_modified
            else None
        )
        return ServeRequest(
            id=entity.id,
            code=entity.code,
            app_code=entity.app_code,
            team_mode=entity.team_mode,
            team_context=_load_team_context(
                team_mode=entity.team_mode,
                team_context=entity.team_context,
                agent_version=getattr(entity, "agent_version", "v1"),
            ),
            resources=_load_resource(entity.resources),
            details=json.loads(entity.details) if entity.details else None,
            ext_config=json.loads(entity.ext_config) if entity.ext_config else None,
            runtime_config=json.loads(entity.runtime_config)
            if entity.runtime_config
            else None,
            version_info=entity.version_info,
            creator=entity.creator,
            description=entity.description,
            is_published=bool(entity.is_published),
            gmt_last_edit=entity.gmt_last_edit,
            editor=entity.editor,
            system_prompt_template=entity.system_prompt_template,
            user_prompt_template=entity.user_prompt_template,
            layout=_load_layout(entity.layout),
            custom_variables=_load_variable(entity.custom_variables),
            llm_config=_load_llm_config(entity.llm_config),
            resource_knowledge=_load_resource(entity.resource_knowledge),
            resource_tool=_load_resource(entity.resource_tool),
            resource_agent=_load_resource(entity.resource_agent),
            context_config=_load_context_config(entity.context_config),
            gmt_create=gmt_created_str,
            gmt_modified=gmt_modified_str,
            agent_version=getattr(entity, "agent_version", "v1") or "v1",
        )

    def to_response(self, entity: ServeEntity) -> ServerResponse:
        """Convert the entity to a response

        Args:
            entity (T): The entity

        Returns:
            RES: The response
        """
        return self.to_request(entity)
