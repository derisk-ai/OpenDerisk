import json
import logging
import uuid
from datetime import datetime
from itertools import groupby
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    or_,
)

from derisk._private.pydantic import (
    BaseModel,
    Field,
    model_to_json, model_to_dict,
)

from derisk.agent.core.plan.base import SingleAgentContext
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.resource.base import AgentResource, ResourceType
from derisk.storage.metadata import BaseDao, Model
from derisk_app.openapi.api_view_model import ConversationVo
from derisk_serve.agent.app.recommend_question.recommend_question import (
    RecommendQuestion,
    RecommendQuestionDao,
    RecommendQuestionEntity,
)
from derisk_serve.agent.model import NativeTeamContext
from derisk_serve.agent.team.base import TeamMode
from derisk_serve.building.app.api.schema_app import GptsApp, GptsAppDetail
from derisk_serve.building.app.models.models import ServeEntity as GptsAppEntity
from derisk_serve.building.app.models.models_details import AppDetailServeEntity as GptsAppDetailEntity
from derisk_serve.building.config.api.schemas import AppParamType

logger = logging.getLogger(__name__)

recommend_question_dao = RecommendQuestionDao()


class UserRecentApps(BaseModel):
    app_code: Optional[str] = None
    user_code: Optional[str] = None
    sys_code: Optional[str] = None
    last_accessed: datetime = None
    gmt_create: datetime = None
    gmt_modified: datetime = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        return cls(
            app_code=d.get("app_code", None),
            user_code=d.get("user_code", None),
            sys_code=d.get("sys_code", None),
            gmt_create=d.get("gmt_create", None),
            gmt_modified=d.get("gmt_modified", None),
            last_accessed=d.get("last_accessed", None),
        )


class UserRecentAppsEntity(Model):
    __tablename__ = "user_recent_apps"
    id = Column(Integer, primary_key=True, comment="autoincrement id")
    app_code = Column(String(255), nullable=False, comment="Current AI assistant code")
    user_code = Column(String(255), nullable=True, comment="user code")
    sys_code = Column(String(255), nullable=True, comment="system app code")
    gmt_create = Column(DateTime, default=datetime.utcnow, comment="create time")
    gmt_modified = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="last update time",
    )
    last_accessed = Column(DateTime, default=None, comment="last access time")
    __table_args__ = (
        Index("idx_user_r_app_code", "app_code"),
        Index("idx_user_code", "user_code"),
        Index("idx_last_accessed", "last_accessed"),
    )


class UserRecentAppsDao(BaseDao):
    def query(
            self,
            user_code: Optional[str] = None,
            sys_code: Optional[str] = None,
            app_code: Optional[str] = None,
    ):
        with self.session() as session:
            recent_app_qry = session.query(UserRecentAppsEntity)
            if user_code:
                recent_app_qry = recent_app_qry.filter(
                    UserRecentAppsEntity.user_code == user_code
                )
            if sys_code:
                recent_app_qry = recent_app_qry.filter(
                    UserRecentAppsEntity.sys_code == sys_code
                )
            if app_code:
                recent_app_qry = recent_app_qry.filter(
                    UserRecentAppsEntity.app_code == app_code
                )
            recent_app_qry.order_by(UserRecentAppsEntity.last_accessed.desc())
            apps = []
            results = recent_app_qry.all()
            for result in results:
                apps.append(
                    UserRecentApps.from_dict(
                        {
                            "app_code": result.app_code,
                            "sys_code": result.sys_code,
                            "user_code": result.user_code,
                            "last_accessed": result.last_accessed,
                            "gmt_create": result.gmt_create,
                            "gmt_modified": result.gmt_modified,
                        }
                    )
                )
            return apps

    def upsert(
            self,
            user_code: Optional[str] = None,
            sys_code: Optional[str] = None,
            app_code: Optional[str] = None,
    ):
        with self.session() as session:
            try:
                existing_app = (
                    session.query(UserRecentAppsEntity)
                    .filter(
                        UserRecentAppsEntity.user_code == user_code,
                        UserRecentAppsEntity.sys_code == sys_code,
                        UserRecentAppsEntity.app_code == app_code,
                    )
                    .first()
                )

                last_accessed = datetime.utcnow()
                if existing_app:
                    existing_app.last_accessed = last_accessed
                    existing_app.gmt_modified = datetime.utcnow()
                    session.commit()
                else:
                    new_app = UserRecentAppsEntity(
                        user_code=user_code,
                        sys_code=sys_code,
                        app_code=app_code,
                        last_accessed=last_accessed,
                        gmt_create=datetime.utcnow(),
                        gmt_modified=datetime.utcnow(),
                    )
                    session.add(new_app)
                    session.commit()

                return UserRecentApps.from_dict(
                    {
                        "app_code": app_code,
                        "sys_code": sys_code,
                        "user_code": user_code,
                        "last_accessed": last_accessed,
                        "gmt_create": (
                            existing_app.gmt_create
                            if existing_app
                            else new_app.gmt_create
                        ),
                        "gmt_modified": last_accessed,
                    }
                )
            except Exception as ex:
                logger.error(f"recent use app upsert error: {ex}")


class GptsAppDao(BaseDao):
    def list_all(self):
        with self.session() as session:
            app_qry = session.query(GptsAppEntity)
            app_entities = app_qry.all()
            apps = [
                GptsApp.from_dict(
                    {
                        "app_code": app_info.app_code,
                        "app_name": app_info.app_name,
                        "language": app_info.language,
                        "app_describe": app_info.app_describe,
                        "team_mode": app_info.team_mode,
                        "config_code": app_info.config_code,
                        "config_version": app_info.config_version,
                        "team_context": app_info.team_context,
                        "user_code": app_info.user_code,
                        "sys_code": app_info.sys_code,
                        "created_at": app_info.created_at,
                        "updated_at": app_info.updated_at,
                        "published": app_info.published,
                        "details": [],
                        "admins": [],
                        # "keep_start_rounds": app_info.keep_start_rounds,
                        # "keep_end_rounds": app_info.keep_end_rounds,
                    }
                )
                for app_info in app_entities
            ]
            return apps

    def get_gpts_apps_by_knowledge_id(self, knowledge_id: Optional[str] = None):
        session = self.get_raw_session()
        try:
            apps = session.query(GptsAppEntity)
            if knowledge_id is not None:
                apps = apps.filter(
                    GptsAppEntity.team_context.like("%" + knowledge_id + "%")
                )

            apps = apps.order_by(GptsAppEntity.id.asc())

            results = apps.all()
            return results

        finally:
            session.close()

    def _entity_to_app_dict(
            self,
            app_info: GptsAppEntity,
            app_details: List[GptsAppDetailEntity],
            hot_app_map: dict = None,
            app_collects: List[str] = [],
            parse_llm_strategy: bool = False,
            owner_name: str = None,
            owner_avatar_url: str = None,
            recommend_questions: List[RecommendQuestionEntity] = None,
    ):
        return {
            "app_code": app_info.app_code,
            "app_name": app_info.app_name,
            "language": app_info.language,
            "app_describe": app_info.app_describe,
            "team_mode": app_info.team_mode,
            "config_code": app_info.config_code,
            "team_context": _load_team_context(
                app_info.team_mode, app_info.team_context
            ),
            "user_code": app_info.user_code,
            "icon": app_info.icon,
            "sys_code": app_info.sys_code,
            "is_collected": "true" if app_info.app_code in app_collects else "false",
            "created_at": app_info.created_at,
            "updated_at": app_info.updated_at,
            "details": [
                GptsAppDetail.from_dict(item.to_dict(), parse_llm_strategy)
                for item in app_details
            ],
            "published": app_info.published,
            "param_need": (
                json.loads(app_info.param_need) if app_info.param_need else None
            ),
            "hot_value": (
                hot_app_map.get(app_info.app_code, 0) if hot_app_map is not None else 0
            ),
            "owner_name": app_info.user_code,
            "owner_avatar_url": owner_avatar_url,
            "recommend_questions": (
                [RecommendQuestion.from_entity(item) for item in recommend_questions]
                if recommend_questions
                else []
            ),
            "admins": [],
        }

    def app_detail(self, app_code: str, user_code: str = None, sys_code: str = None):
        from datetime import datetime
        with self.session() as session:
            app_qry = session.query(GptsAppEntity).filter(
                GptsAppEntity.app_code == app_code
            )

            app_info = app_qry.first()

            app_detail_qry = session.query(GptsAppDetailEntity).filter(
                GptsAppDetailEntity.app_code == app_code
            )
            app_details = app_detail_qry.all()

            if app_info:
                app = GptsApp.from_dict(
                    self._entity_to_app_dict(
                        app_info,
                        app_details,
                        None,
                    )
                )
                return app

            else:
                return app_info

    def app_detail_with_question(self, app_code: str, user_code: str = None, sys_code: str = None):
        with self.session() as session:
            app_qry = session.query(GptsAppEntity).filter(
                GptsAppEntity.app_code == app_code
            )

            app_info = app_qry.first()

            app_detail_qry = session.query(GptsAppDetailEntity).filter(
                GptsAppDetailEntity.app_code == app_code
            )
            app_details = app_detail_qry.all()

            recommend_questions = session.query(RecommendQuestionEntity).filter(
                RecommendQuestionEntity.app_code == app_code
            ).all()

            if app_info:
                app = GptsApp.from_dict(
                    self._entity_to_app_dict(
                        app_info,
                        app_details,
                        None,
                        [],
                        recommend_questions=recommend_questions
                    )
                )
                return app
            else:
                return app_info

    # def delete(
    #     self,
    #     app_code: str,
    #     user_code: Optional[str] = None,
    #     sys_code: Optional[str] = None,
    # ):
    #     """
    #     To delete the application, you also need to delete the corresponding plug-ins
    #     and collections.
    #     """
    #     if app_code is None:
    #         raise "cannot delete app when app_code is None"
    #     with self.session() as session:
    #         app_qry = session.query(GptsAppEntity)
    #         app_qry = app_qry.filter(GptsAppEntity.app_code == app_code)
    #         app_qry.delete()
    #
    #         app_detail_qry = session.query(GptsAppDetailEntity).filter(
    #             GptsAppDetailEntity.app_code == app_code
    #         )
    #         app_detail_qry.delete()
    #
    #         app_collect_qry = session.query(GptsAppCollectionEntity).filter(
    #             GptsAppCollectionEntity.app_code == app_code
    #         )
    #         app_collect_qry.delete()
    #     recommend_question_dao.delete_by_app_code(app_code)

    def create(self, gpts_app: GptsApp):
        with self.session() as session:
            app_entity = GptsAppEntity(
                app_code=gpts_app.app_code if gpts_app.app_code else str(uuid.uuid1()),
                app_name=gpts_app.app_name,
                app_describe=gpts_app.app_describe,
                team_mode=gpts_app.team_mode,
                team_context=_parse_team_context(gpts_app.team_context),
                language=gpts_app.language,
                user_code=gpts_app.user_code,
                sys_code=gpts_app.sys_code,
                created_at=gpts_app.created_at,
                updated_at=gpts_app.updated_at,
                icon=gpts_app.icon,
                published="true" if gpts_app.published else "false",
                param_need=(
                    json.dumps(gpts_app.param_need) if gpts_app.param_need else None
                ),
            )
            session.add(app_entity)

            app_details = []
            for item in gpts_app.details:
                resource_dicts = [resource.to_dict() for resource in item.resources]
                if item.agent_name is None:
                    raise "agent name cannot be None"

                app_details.append(
                    GptsAppDetailEntity(
                        app_code=app_entity.app_code,
                        app_name=app_entity.app_name,
                        agent_name=item.agent_name,
                        agent_role=item.agent_role
                        if item.agent_role
                        else item.agent_name,
                        node_id=str(uuid.uuid1()),
                        resources=json.dumps(resource_dicts, ensure_ascii=False),
                        prompt_template=item.prompt_template,
                        llm_strategy=item.llm_strategy,
                        llm_strategy_value=(
                            None
                            if item.llm_strategy_value is None
                            else json.dumps(tuple(item.llm_strategy_value.split(",")))
                        ),
                        created_at=item.created_at,
                        updated_at=item.updated_at,
                    )
                )
            session.add_all(app_details)

            recommend_questions = []
            for recommend_question in gpts_app.recommend_questions:
                recommend_questions.append(
                    RecommendQuestionEntity(
                        app_code=app_entity.app_code,
                        question=recommend_question.question,
                        user_code=app_entity.user_code,
                        gmt_create=recommend_question.gmt_create,
                        gmt_modified=recommend_question.gmt_modified,
                        params=json.dumps(recommend_question.params),
                        valid=recommend_question.valid,
                        is_hot_question="false",
                    )
                )
            session.add_all(recommend_questions)
            gpts_app.app_code = app_entity.app_code
            return gpts_app

    def edit(self, gpts_app: GptsApp):
        with self.session() as session:
            app_qry = session.query(GptsAppEntity)
            if gpts_app.app_code is None:
                raise Exception("app_code is None, don't allow to edit!")
            app_qry = app_qry.filter(GptsAppEntity.app_code == gpts_app.app_code)
            app_entity = app_qry.one()

            is_reasoning_agent: bool = (
                    len(gpts_app.details) == 1
                    and gpts_app.details[0].agent_name == "ReasoningPlanner"
            )
            if is_reasoning_agent:
                app_entity.team_context = json.dumps(
                    AutoTeamContext(
                        can_ask_user=True,
                        llm_strategy=gpts_app.details[0].llm_strategy,
                        llm_strategy_value=gpts_app.details[0].llm_strategy_value.split(
                            ","
                        ),
                        prompt_template=None,
                        resources=gpts_app.details[0].resources,
                        teamleader="ReasoningPlanner",
                    ).to_dict(),
                    ensure_ascii=False,
                )
            else:
                app_entity.team_context = _parse_team_context(gpts_app.team_context)
            app_entity.app_name = gpts_app.app_name
            app_entity.app_describe = gpts_app.app_describe
            app_entity.language = gpts_app.language
            app_entity.team_mode = gpts_app.team_mode
            app_entity.icon = gpts_app.icon
            app_entity.param_need = json.dumps(gpts_app.param_need)
            app_entity.keep_start_rounds = gpts_app.keep_start_rounds
            app_entity.keep_end_rounds = gpts_app.keep_end_rounds
            session.merge(app_entity)

            old_details = session.query(GptsAppDetailEntity).filter(
                GptsAppDetailEntity.app_code == gpts_app.app_code
            )
            old_details.delete()

            app_details = []
            if not is_reasoning_agent:
                for item in gpts_app.details:
                    resource_dicts = None
                    if item.resources:
                        resource_dicts = [resource.to_dict() for resource in item.resources]
                    app_details.append(
                        GptsAppDetailEntity(
                            app_code=gpts_app.app_code,
                            app_name=gpts_app.app_name,
                            agent_name=item.agent_name,
                            type=item.type,
                            agent_role=item.agent_role
                            if item.agent_role
                            else item.agent_name,
                            agent_describe=item.agent_describe,
                            node_id=str(uuid.uuid1()),
                            resources=json.dumps(resource_dicts, ensure_ascii=False) if resource_dicts else None,
                            prompt_template=item.prompt_template,
                            llm_strategy=item.llm_strategy,
                            llm_strategy_value=(
                                None
                                if item.llm_strategy_value is None
                                else json.dumps(
                                    tuple(item.llm_strategy_value.split(","))
                                )
                            ),
                            created_at=item.created_at,
                            updated_at=item.updated_at,
                        )
                    )
                session.add_all(app_details)

            old_questions = session.query(RecommendQuestionEntity).filter(
                RecommendQuestionEntity.app_code == gpts_app.app_code
            )
            old_questions.delete()
            session.commit()

            recommend_questions = []
            for recommend_question in gpts_app.recommend_questions:
                recommend_questions.append(
                    RecommendQuestionEntity(
                        app_code=gpts_app.app_code,
                        user_code=gpts_app.user_code or "",
                        question=recommend_question.question,
                        gmt_create=recommend_question.gmt_create,
                        gmt_modified=recommend_question.gmt_modified,
                        params=json.dumps(recommend_question.params),
                        valid=recommend_question.valid,
                    )
                )
            session.add_all(recommend_questions)
            return True


def _parse_team_context(
        team_context: Optional[
            Union[
                str, AutoTeamContext, SingleAgentContext
            ]
        ] = None,
):
    """
    parse team_context to str
    """
    if (
            isinstance(team_context, AutoTeamContext)
            or isinstance(team_context, SingleAgentContext)
    ):
        return model_to_json(team_context)
    return team_context


def _load_team_context(
        team_mode: str = None, team_context: str = None
) -> Union[
    str, SingleAgentContext, AutoTeamContext
]:
    """
    load team_context to str or AWELTeamContext
    """
    if team_mode is not None:
        match team_mode:
            case TeamMode.SINGLE_AGENT.value:
                try:
                    if team_context:
                        single_agent_ctx = SingleAgentContext(
                            **json.loads(team_context)
                        )
                        return single_agent_ctx
                    else:
                        return None
                except Exception as ex:
                    logger.warning(
                        f"_load_team_context error, team_mode={team_mode}, "
                        f"team_context={team_context}, {ex}"
                    )
                    return None

            case TeamMode.AUTO_PLAN.value:
                try:
                    if team_context:
                        context_obj = json.loads(team_context)
                        if "resources" in context_obj:
                            resource = context_obj["resources"]
                            if isinstance(resource, str):
                                resource_obj = json.loads(context_obj["resources"])
                            else:
                                resource_obj = resource
                            context_obj["resources"] = resource_obj

                        auto_team_ctx = AutoTeamContext(**context_obj)
                        return auto_team_ctx
                    else:
                        return None
                except Exception as ex:
                    logger.exception(
                        f"_load_team_context error, team_mode={team_mode}, "
                        f"team_context={team_context}, {ex}"
                    )
    return team_context


class TransferSseRequest(BaseModel):
    all: Optional[bool] = False
    app_code_list: Optional[List[str]] = None
    source: Optional[str] = None
    faas_function_pre: Optional[str] = None
    uri: Optional[str] = None

    def to_dict(self):
        return model_to_dict(self)


class SubToolConfig(BaseModel):
    sub_tool_name: str = None
    description: str = None
    post_script: str = None
    post_check: bool = None
    input_schema: Optional[Any] = None

    def to_dict(self):
            return self.model_dump()


class SkillConfig(BaseModel):
    is_debug: Optional[bool] = False
    debug: Optional[Dict] = None
    release: Optional[Dict] = None

    def to_dict(self):
            return self.model_dump()


class DynamicEditToolsRequest(BaseModel):
    app_code: str
    tool_type: str = None
    tool_id: str = None
    mcp_server_id: str = None
    allow_tools: List[str] = None
    description: str = None
    post_script: str = None
    post_check: bool = False
    input_schema: Optional[Any] = None
    sub_tool_config: List[SubToolConfig] = None
    config_code: Optional[str] = None
    skill_config: Optional[SkillConfig] = None

    def to_dict(self):
        return self.model_dump()
