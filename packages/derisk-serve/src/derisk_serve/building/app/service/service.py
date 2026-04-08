import json
import logging
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import or_

from derisk._private.config import Config
from derisk.agent import get_agent_manager, AgentResource, ResourceType
from derisk.agent.core.plan.base import SingleAgentContext
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.context.utils import build_by_agent_config
from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk.util.pagination_utils import PaginationResult
from derisk.vis.schema import ChatLayout
from derisk.vis.vis_manage import get_vis_manager
from derisk_serve.agent.model import NativeTeamContext
from derisk_serve.agent.team.base import TeamMode
from derisk_serve.core import BaseService
from ..api.schema_app import GptsAppDetail, GptsAppQuery, GptsAppResponse
from ..api.schema_app_detail import AppDetailServeRequest, AppDetailServerResponse

from ..api.schemas import ServeRequest, ServerResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import ServeDao, ServeEntity
from ..models.models_details import AppDetailServeDao, AppDetailServeEntity
from ...config.service.service import Service as AppConfigService, TEMP_VERSION_SUFFIX
from ...config.api.schemas import ServeRequest as AppConfigRequest, LLMResource, Layout
from ...config.config import (
    SERVE_SERVICE_COMPONENT_NAME as Config_SERVE_SERVICE_COMPONENT,
)
from ...recommend_question.models.models import ServeEntity as RecommendQuestionEntity
from ...recommend_question.models.models import ServeDao as RecommendQuestionDao
from ...recommend_question.api.schemas import ServeRequest as RecommendQuestionRequest
from ...recommend_question.api.schemas import (
    ServerResponse as RecommendQuestionResponse,
)

logger = logging.getLogger(__name__)
CFG = Config()

global_system_app: Optional[SystemApp] = None


def get_config_service() -> AppConfigService:
    """Get the service instance"""
    return CFG.SYSTEM_APP.get_component(
        Config_SERVE_SERVICE_COMPONENT, AppConfigService
    )


class Service(BaseService[ServeEntity, ServeRequest, ServerResponse]):
    """The service class for App"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig, dao: Optional[ServeDao] = None
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: ServeDao = dao
        self._detail_dao: AppDetailServeDao = AppDetailServeDao()
        self._recommend_question_dao: RecommendQuestionDao = RecommendQuestionDao(
            config
        )
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or ServeDao(self._serve_config)
        self._system_app = system_app

    async def async_after_start(self):
        """After initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        await self.load_define_app()

    @property
    def dao(self) -> BaseDao[ServeEntity, ServeRequest, ServerResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def detail_app_dao(
        self,
    ) -> BaseDao[AppDetailServeEntity, AppDetailServeRequest, AppDetailServerResponse]:
        """Returns the internal DAO."""
        return self._detail_dao

    @property
    def recommend_question_dao(
        self,
    ) -> BaseDao[
        RecommendQuestionEntity, RecommendQuestionRequest, RecommendQuestionResponse
    ]:
        """Returns the internal DAO."""
        return self._recommend_question_dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    async def new_define_app(self, request: ServeRequest):
        """创建并发布新应用

        流程：
        1. 创建应用记录
        2. 编辑应用配置（创建临时配置）
        3. 发布应用（将临时配置转为正式配置）
        """
        logger.info(
            f"new_define_app: app_code={request.app_code}, published={request.published}"
        )

        # 1. 创建应用记录
        self.create(request)

        # 2. 编辑应用配置（这会创建临时配置）
        new_app = await self.edit(request)

        if not new_app or not new_app.config_code:
            logger.error(f"应用 [{request.app_code}] 配置创建失败")
            raise ValueError(f"应用配置创建失败: {request.app_code}")

        logger.info(
            f"应用 [{request.app_code}] 临时配置创建成功: config_code={new_app.config_code}"
        )

        # 3. 发布应用（如果 request.published 为 True）
        if request.published:
            logger.info(f"正在发布应用 [{request.app_code}]...")
            await self.publish(
                request.app_code,
                new_app.config_code,
                operator=request.user_code or "system",
                carefully_chosen=True,
            )
            logger.info(f"应用 [{request.app_code}] 发布成功")
        else:
            logger.info(f"应用 [{request.app_code}] 设置为未发布状态，跳过发布")

    def create(self, request: ServeRequest) -> Optional[ServerResponse]:
        """应用构建."""
        logger.info(f"app create:{request.app_name},{request.team_mode}")
        # if not request.app_code:
        #     request.app_code = uuid.uuid1().hex
        if not request.team_mode:
            if request.details and len(request.details) > 0:
                request.team_mode = TeamMode.AUTO_PLAN.value
            else:
                request.team_mode = TeamMode.SINGLE_AGENT.value

        # 初始化布局
        if not request.layout:
            from derisk_ext.vis.derisk.derisk_vis_incr_converter import (
                DeriskVisIncrConverter,
            )

            defualt_convert = DeriskVisIncrConverter()
            request.layout = Layout(
                chat_layout=ChatLayout(
                    name=defualt_convert.render_name,
                    incremental=defualt_convert.incremental,
                    description=defualt_convert.description,
                )
            )
        # 初始化模型策略
        if not request.llm_config:
            from derisk.agent import LLMStrategyType

            request.llm_config = LLMResource(llm_strategy=LLMStrategyType.Default.value)

        # 冲突检测
        chek_app = self.get_by_name(request.app_name)
        if chek_app:
            raise ValueError("应用名称或代码冲突！")
        res = self.dao.create(request)
        return res

    def app_info_to_config(self, request: ServeRequest) -> AppConfigRequest:
        agent_version = getattr(request, "agent_version", "v1") or "v1"
        is_v2 = agent_version == "v2"

        logger.info(
            f"[app_info_to_config] agent_version={agent_version}, is_v2={is_v2}"
        )
        logger.info(
            f"[app_info_to_config] team_context type: {type(request.team_context)}"
        )
        logger.info(f"[app_info_to_config] team_context: {request.team_context}")

        if is_v2:
            from derisk.agent.core.plan.unified_context import UnifiedTeamContext

            if request.team_context:
                if isinstance(request.team_context, UnifiedTeamContext):
                    team_context = request.team_context
                elif isinstance(request.team_context, dict):
                    team_context = UnifiedTeamContext.from_dict(request.team_context)
                    logger.info(
                        f"[app_info_to_config] Created UnifiedTeamContext from dict: use_sandbox={team_context.use_sandbox}"
                    )
                else:
                    # 尝试从对象中提取数据
                    tc_dict = (
                        request.team_context.to_dict()
                        if hasattr(request.team_context, "to_dict")
                        else {}
                    )
                    team_context = UnifiedTeamContext(
                        agent_version="v2",
                        team_mode="single_agent",
                        agent_name=tc_dict.get("agent_name")
                        or request.agent
                        or "simple_chat",
                        use_sandbox=tc_dict.get("use_sandbox", False),
                    )
            else:
                team_context = UnifiedTeamContext(
                    agent_version="v2",
                    team_mode="single_agent",
                    agent_name=request.agent or "simple_chat",
                )
            request.team_mode = TeamMode.SINGLE_AGENT.value
        elif not request.team_mode == TeamMode.NATIVE_APP.value:
            if request.agent:
                ag_mg = get_agent_manager()
                ag = ag_mg.get(request.agent)
                if ag and ag.is_team:
                    request.team_mode = TeamMode.AUTO_PLAN.value
                    if not request.team_context:
                        team_context = AutoTeamContext(teamleader=request.agent)
                    else:
                        tc_dict = (
                            request.team_context
                            if isinstance(request.team_context, dict)
                            else request.team_context.to_dict()
                        )
                        team_context = AutoTeamContext(**tc_dict)
                        team_context.teamleader = request.agent
                else:
                    request.team_mode = TeamMode.SINGLE_AGENT.value
                    if not request.team_context:
                        team_context = SingleAgentContext(agent_name=request.agent)
                    else:
                        tc_dict = (
                            request.team_context
                            if isinstance(request.team_context, dict)
                            else request.team_context.to_dict()
                        )
                        team_context = SingleAgentContext(**tc_dict)
                        team_context.agent_name = request.agent
            else:
                request.team_mode = TeamMode.SINGLE_AGENT.value
                if not request.team_context:
                    team_context = SingleAgentContext(
                        agent_name=request.agent or "default"
                    )
                else:
                    tc_dict = (
                        request.team_context
                        if isinstance(request.team_context, dict)
                        else request.team_context.to_dict()
                    )
                    team_context = SingleAgentContext(**tc_dict)
        else:
            if not request.team_context:
                team_context = NativeTeamContext()
            else:
                tc_dict = (
                    request.team_context
                    if isinstance(request.team_context, dict)
                    else request.team_context.to_dict()
                )
                team_context = NativeTeamContext(**tc_dict)
            if request.agent:
                team_context.agent_name = request.agent

        return AppConfigRequest(
            app_code=request.app_code,
            team_mode=request.team_mode,
            team_context=team_context,
            resources=request.resources,
            ext_config=request.ext_config,
            runtime_config=getattr(request, "runtime_config", None),
            gmt_last_edit=request.updated_at,
            editor=request.editor,
            creator=request.creator,
            layout=request.layout,
            custom_variables=request.custom_variables,
            llm_config=request.llm_config,
            resource_knowledge=request.resource_knowledge,
            resource_tool=request.resource_tool,
            resource_agent=request.resource_agent,
            system_prompt_template=request.system_prompt_template,
            user_prompt_template=request.user_prompt_template,
            context_config=request.context_config,
            agent_version=getattr(request, "agent_version", "v1") or "v1",
        )

    async def edit(self, request: ServeRequest) -> Optional[ServerResponse]:
        logger.info(f"app edit:{request}")
        query_dict = {"app_code": request.app_code}
        app_resp = self.dao.get_one(query_dict)
        if not app_resp:
            raise ValueError(f"应用不存在[{request.app_code}]")
        ## 编辑应用基础信息(如果有修改)
        update_dict = {}
        if request.app_name and request.app_name != app_resp.app_name:
            update_dict["app_name"] = request.app_name
        if request.app_describe and request.app_describe != app_resp.app_describe:
            update_dict["app_describe"] = request.app_describe
        if request.icon and request.icon != app_resp.icon:
            update_dict["icon"] = request.icon
        if request.language and request.language != app_resp.language:
            update_dict["language"] = request.language
        request_agent_version = getattr(request, "agent_version", "v1") or "v1"
        if request_agent_version and request_agent_version != getattr(
            app_resp, "agent_version", "v1"
        ):
            update_dict["agent_version"] = request_agent_version

        if len(update_dict) > 0:
            self.dao.update(query_dict, update_dict)
        ## 编辑推荐问题

        if request.recommend_questions:
            recommend_questions = []
            for recommend_question in request.recommend_questions:
                recommend_questions.append(
                    RecommendQuestionEntity(
                        app_code=request.app_code,
                        user_code=request.user_code or "",
                        question=recommend_question.question,
                        params=json.dumps(recommend_question.params),
                        valid=recommend_question.valid,
                    )
                )
            self.recommend_question_dao.replace_all(
                request.app_code, recommend_questions
            )  # type:ignore

        ## 编辑应用配置
        ### 应用基础信息转配置信息
        app_config_service = get_config_service()
        temp_config = await app_config_service.edit(self.app_info_to_config(request))
        config_code = app_resp.config_code
        if temp_config:
            request.config_code = temp_config.code
            request.config_version = temp_config.version_info
            config_code = temp_config.code
        return await self.app_detail(
            app_code=request.app_code, specify_config_code=config_code
        )

    async def publish(
        self,
        app_code: str,
        new_config_code: str,
        operator: Optional[str] = None,
        carefully_chosen: bool = False,
        description: Optional[str] = None,
    ) -> Optional[ServerResponse]:
        logger.info(
            f"[PUBLISH] Starting publish for app_code={app_code}, new_config_code={new_config_code}"
        )
        with self.dao.session(commit=False) as session:
            ### 应用发布需要在同一个事务里做两件事情:
            ### 1.修改当前临时版本配置未正式配置代码，状态修改为发布
            ### 2.修改应用的配置代码未当前发布版本
            ### 3.提交事务
            from derisk_serve.building.config.models.models import (
                ServeEntity as AppConfigEntity,
            )

            config_service = get_config_service()

            app_query_object = {"app_code": app_code}
            query = self.dao._create_query_object(session, app_query_object)
            app_entry: ServeEntity = query.first()
            if app_entry:
                app_config_query = session.query(AppConfigEntity)
                app_config_query = app_config_query.filter(
                    AppConfigEntity.app_code == app_entry.app_code
                ).filter(AppConfigEntity.code == new_config_code)
                app_config_entry: AppConfigEntity = app_config_query.first()
                if not app_config_entry:
                    raise ValueError(f"配置[{new_config_code}]已经不存在")

                # 配置发布,状态和版本信息更新
                release_config_version = config_service.temp_to_formal(
                    app_config_entry.version_info
                )
                now = datetime.now()
                app_config_entry.version_info = release_config_version
                app_config_entry.is_published = 1
                app_config_entry.operator = operator
                app_config_entry.description = description

                logger.info(
                    f"[PUBLISH] Before commit: app_code={app_code}, new_config_code={new_config_code}"
                )
                logger.info(f"[PUBLISH] app_config_entry.code={app_config_entry.code}")
                logger.info(
                    f"[PUBLISH] app_config_entry.is_published={app_config_entry.is_published}"
                )
                logger.info(
                    f"[PUBLISH] app_config_entry.resource_tool={app_config_entry.resource_tool}"
                )
                logger.info(
                    f"[PUBLISH] app_config_entry.agent_version={getattr(app_config_entry, 'agent_version', 'N/A')}"
                )
                logger.info(
                    f"[PUBLISH] app_config_entry.team_mode={app_config_entry.team_mode}"
                )
                logger.info(
                    f"[PUBLISH] app_config_entry.resource_tool type={type(app_config_entry.resource_tool)}"
                )
                if app_config_entry.resource_tool:
                    import json

                    try:
                        resource_tool_parsed = (
                            json.loads(app_config_entry.resource_tool)
                            if isinstance(app_config_entry.resource_tool, str)
                            else app_config_entry.resource_tool
                        )
                        logger.info(
                            f"[PUBLISH] app_config_entry.resource_tool count={len(resource_tool_parsed) if isinstance(resource_tool_parsed, list) else 'not a list'}"
                        )
                    except Exception as e:
                        logger.warning(f"[PUBLISH] Failed to parse resource_tool: {e}")

                app_entry.config_code = new_config_code
                app_entry.config_version = release_config_version
                # When publishing, the app should be visible (published=1)
                app_entry.published = 1
                app_entry.updated_at = now

                # 直接修改实体（已在 session 中被跟踪），不需要 merge
                session.flush()
                session.commit()
                logger.info(f"[PUBLISH] Commit successful for app_code={app_code}")
                logger.info(
                    f"[PUBLISH] After commit, app_entry.config_code={app_entry.config_code}, app_config_entry.is_published={app_config_entry.is_published}"
                )

                # 删除所有旧的临时配置（发布成功后删除）
                try:
                    old_temp_configs_query = session.query(AppConfigEntity)
                    old_temp_configs_query = old_temp_configs_query.filter(
                        AppConfigEntity.app_code == app_entry.app_code
                    ).filter(AppConfigEntity.is_published == False)
                    old_temp_count = old_temp_configs_query.delete(
                        synchronize_session=False
                    )
                    session.commit()
                    logger.info(
                        f"[PUBLISH] Deleted {old_temp_count} old temp configs for app_code={app_code}"
                    )
                except Exception as e:
                    logger.warning(f"[PUBLISH] Failed to delete old temp configs: {e}")

                session.expire_all()
                logger.info(f"[PUBLISH] Session cache cleared")

            else:
                raise ValueError(f"发布失败，未找到对应的应用信息[{app_code}]")

        logger.info(
            f"[PUBLISH] Calling app_detail with building_mode=False to get published config"
        )
        result = await self.app_detail(
            app_code=app_code, specify_config_code=new_config_code, building_mode=False
        )
        logger.info(f"[PUBLISH] app_detail returned: {result is not None}")
        if result:
            logger.info(
                f"[PUBLISH] result.team_mode={result.team_mode}, result.agent_version={getattr(result, 'agent_version', 'N/A')}"
            )
        return result

    def get_apps_by_codes(self, app_codes: List[str]):
        session = self.dao.get_raw_session()
        apps_query = session.query(ServeEntity)
        apps_query = apps_query.filter(ServeEntity.app_code.in_(app_codes))
        result = apps_query.all()
        session.close()
        return result

    async def async_app_list(
        self, query: GptsAppQuery, parse_llm_strategy: bool = False
    ):
        """Asynchronous version of app_list using SQLAlchemy 2.0 async API"""
        from sqlalchemy import select, func
        from sqlalchemy.orm import selectinload

        async with self.dao.a_session(commit=False) as session:
            # Build the base query
            stmt = select(ServeEntity)

            if query.name_filter:
                stmt = stmt.where(ServeEntity.app_name.like(f"%{query.name_filter}%"))

            if not (query.ignore_user and query.ignore_user.lower() == "true"):
                if query.user_code:
                    stmt = stmt.where(
                        or_(
                            ServeEntity.user_code == query.user_code,
                            ServeEntity.admins.like(f"%{query.user_code}%"),
                        )
                    )
                if query.sys_code:
                    stmt = stmt.where(ServeEntity.sys_code == query.sys_code)

            if query.team_mode:
                stmt = stmt.where(ServeEntity.team_mode == query.team_mode)

            if query.published is not None:
                if query.published:
                    stmt = stmt.where(
                        or_(
                            ServeEntity.published == "true",
                            ServeEntity.published == "1",
                            ServeEntity.published == 1,
                        )
                    )
                else:
                    stmt = stmt.where(
                        or_(
                            ServeEntity.published == "false",
                            ServeEntity.published == "0",
                            ServeEntity.published == 0,
                        )
                    )

            if query.app_codes:
                stmt = stmt.where(ServeEntity.app_code.in_(query.app_codes))

            # Get total count
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_count_result = await session.execute(count_stmt)
            total_count = total_count_result.scalar()

            # Apply ordering and pagination
            stmt = stmt.order_by(ServeEntity.id.desc())
            stmt = stmt.offset((query.page - 1) * query.page_size).limit(
                query.page_size
            )

            # Execute query
            result = await session.execute(stmt)
            results = result.scalars().all()

        # Build response (this part doesn't need DB access)
        if results is not None:
            apps: List = []
            for app_entity in results:
                app_info = self.dao.to_response(app_entity)
                apps.append(app_info)

            # Batch query ext_config from config table for all apps
            if apps:
                try:
                    from derisk_serve.building.config.models.models import (
                        ServeEntity as AppConfigEntity,
                    )

                    app_codes = [a.app_code for a in apps if a.app_code]
                    async with self.dao.a_session(commit=False) as config_session:
                        # For each app, get the latest config's ext_config
                        # Prefer temp config (is_published=0), fallback to published
                        config_stmt = (
                            select(
                                AppConfigEntity.app_code,
                                AppConfigEntity.ext_config,
                            )
                            .where(AppConfigEntity.app_code.in_(app_codes))
                            .order_by(
                                AppConfigEntity.app_code,
                                AppConfigEntity.is_published.asc(),  # temp first
                                AppConfigEntity.id.desc(),
                            )
                        )
                        config_result = await config_session.execute(config_stmt)
                        config_rows = config_result.all()

                        # Build map: app_code -> ext_config (first match wins)
                        ext_config_map: Dict = {}
                        for row in config_rows:
                            if row.app_code not in ext_config_map and row.ext_config:
                                try:
                                    ext_config_map[row.app_code] = json.loads(
                                        row.ext_config
                                    )
                                except (json.JSONDecodeError, TypeError):
                                    pass

                        # Attach ext_config to each app
                        for app_info in apps:
                            if app_info.app_code in ext_config_map:
                                app_info.ext_config = ext_config_map[app_info.app_code]
                except Exception as e:
                    logger.warning(f"Failed to batch load ext_config for app list: {e}")

            app_resp = GptsAppResponse()
            app_resp.total_count = total_count
            app_resp.app_list = apps
            app_resp.current_page = query.page
            app_resp.page_size = query.page_size
            app_resp.total_page = (total_count + query.page_size - 1) // query.page_size
            return app_resp

        return GptsAppResponse()

    async def app_list(self, query: GptsAppQuery, parse_llm_strategy: bool = False):
        return await self.async_app_list(query, parse_llm_strategy)

    def app_to_details(
        self, main_app_code: str, main_app_name: str, app_codes: List[str]
    ):
        result: List = []
        detail_apps = self.get_apps_by_codes(app_codes)
        for item in detail_apps:
            result.append(
                GptsAppDetail(
                    app_code=main_app_code,
                    app_name=main_app_name,
                    type="app",
                    agent_name=item.app_name,
                    agent_role=item.app_code,
                    agent_describe=item.app_describe,
                    agent_icon=item.icon,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
        return result

    def _pop_resource(self, resources: List[AgentResource], filter_types: List[str]):
        new_lst = []
        result_resources = []
        for item in resources:
            if not item.type in filter_types:
                new_lst.append(item)
            else:
                result_resources.append(item)
        resources[:] = new_lst  # 原地修改原列表
        return result_resources

    def app_detail_to_app_resource(
        self, app_info: ServerResponse, details: List[GptsAppDetail]
    ):
        resource_agent: List[AgentResource] = []
        for detail in details:
            resource_agent.append(
                AgentResource(
                    type=ResourceType.App.value,
                    value=json.dumps(
                        {
                            "label": f"[{detail.agent_role}]{detail.agent_name}",
                            "key": detail.agent_role,
                            "app_code": detail.agent_role,
                            "app_name": detail.agent_name,
                            "value": detail.agent_role,
                        },
                        ensure_ascii=False,
                    ),
                    name=detail.agent_name,
                )
            )
        app_info.resource_agent = resource_agent
        return app_info

    def _resource_to_app_detail(
        self, app_info: ServerResponse, agent_resources: List[AgentResource]
    ):
        import time

        _start = time.time()
        details = []
        for idx, item in enumerate(agent_resources):
            # {\"name\":\"My Agent Resource\",\"app_code\":\"1bc6d188-735e-11f0-b924-00163e0ea545\"}
            app_code = (None,)
            if isinstance(item.value, str):
                value_dict = json.loads(item.value)
                app_code = value_dict.get("app_code")
            elif isinstance(item.value, dict):
                app_code = item.value.get("app_code")
            else:
                logger.warning("不支持的AgentAppResource内容1！")
            if not app_code:
                logger.warning(f"AgentAppResource{item.value}没有找到AppCode！")
                continue
            _query_start = time.time()
            item_info = self.get(ServeRequest(app_code=app_code))
            logger.info(
                f"[APP_DETAIL][PERF] _resource_to_app_detail 查询关联app[{app_code}]耗时: {(time.time() - _query_start) * 1000:.2f}ms"
            )
            details.append(
                GptsAppDetail(
                    app_code=app_info.app_code,
                    app_name=app_info.app_name,
                    type=item.type,
                    agent_name=item_info.app_name,
                    agent_role=item_info.app_code,
                    agent_icon=item_info.icon,
                    agent_describe=item_info.app_describe,
                    node_id=uuid.uuid4().hex,
                    resources=None,
                    prompt_template=None,
                    llm_strategy=None,
                    llm_strategy_value=None,
                    created_at=item_info.created_at,
                    updated_at=item_info.updated_at,
                )
            )

        app_info.details = details
        app_info.resource_agent = agent_resources
        logger.info(
            f"[APP_DETAIL][PERF] _resource_to_app_detail 总耗时(共{len(agent_resources)}个关联app): {(time.time() - _start) * 1000:.2f}ms"
        )
        return app_info

    def sync_app_detail(
        self,
        app_code: str,
        specify_config_code: Optional[str] = None,
        building_mode: bool = True,
    ) -> Optional[ServerResponse]:
        import time

        _total_start = time.time()

        logger.info(
            f"[APP_DETAIL] get_app_detail: app_code={app_code}, specify_config_code={specify_config_code}, building_mode={building_mode}"
        )

        _step_start = time.time()
        app_resp = self.dao.get_one({"app_code": app_code})
        logger.info(
            f"[APP_DETAIL][PERF] 查询应用基础信息耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        if not app_resp:
            raise ValueError(f"应用不存在[{app_code}]")

        logger.info(
            f"[APP_DETAIL] app_resp.config_code={app_resp.config_code}, app_resp.config_version={app_resp.config_version}"
        )

        _step_start = time.time()
        config_service = get_config_service()
        logger.info(
            f"[APP_DETAIL][PERF] 获取config_service耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        app_config = None
        if specify_config_code:
            logger.info(
                f"[APP_DETAIL] 指定了配置代码，需要加载指定的配置: {specify_config_code}"
            )
            _step_start = time.time()
            app_config = config_service.get_by_code(specify_config_code)
            logger.info(
                f"[APP_DETAIL][PERF] 查询指定配置耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )
            logger.info(f"[APP_DETAIL] 指定配置查询结果: {app_config is not None}")
        else:
            if building_mode:
                _step_start = time.time()
                temp_config = config_service.get_app_temp_code(app_code=app_code)
                logger.info(
                    f"[APP_DETAIL][PERF] 查询临时配置耗时: {(time.time() - _step_start) * 1000:.2f}ms"
                )
                logger.info(
                    f"[APP_DETAIL] 构建模式, 临时配置查询结果: {temp_config is not None}"
                )
                if not temp_config:
                    logger.info(
                        "[APP_DETAIL] 构建模式, 不存在临时配置, 尝试加载发布的配置"
                    )
                    if app_resp.config_code:
                        _step_start = time.time()
                        app_config = config_service.get_by_code(app_resp.config_code)
                        logger.info(
                            f"[APP_DETAIL][PERF] 查询发布配置耗时: {(time.time() - _step_start) * 1000:.2f}ms"
                        )
                        logger.info(
                            f"[APP_DETAIL] 发布配置查询结果: {app_config is not None}"
                        )
                else:
                    app_config = temp_config
            else:
                logger.info("[APP_DETAIL] 非构建模式, 只能加载当前发布版本配置")
                if app_resp.config_code:
                    _step_start = time.time()
                    app_config = config_service.get_by_code(app_resp.config_code)
                    logger.info(
                        f"[APP_DETAIL][PERF] 查询发布配置耗时: {(time.time() - _step_start) * 1000:.2f}ms"
                    )
                    logger.info(
                        f"[APP_DETAIL] 发布配置查询结果: {app_config is not None}"
                    )

        if app_config:
            _config_process_start = time.time()
            all_resources = []
            logger.info(
                f"当前应用有配置代码，需要加载指定版本配置[{app_config.code}][{app_config.version_info}]！"
            )

            if app_config.resource_agent:
                _step_start = time.time()
                app_resp.resource_agent = app_config.resource_agent
                ## 如果配置存在resource_agent资源，转换为detail消费使用
                self._resource_to_app_detail(app_resp, app_config.resource_agent)
                logger.info(
                    f"[APP_DETAIL][PERF] 处理resource_agent耗时: {(time.time() - _step_start) * 1000:.2f}ms"
                )

            # 确保 team_context 被正确序列化为字典，包含 use_sandbox 等字段
            if app_config.team_context and hasattr(app_config.team_context, "to_dict"):
                app_resp.team_context = app_config.team_context.to_dict()
            else:
                app_resp.team_context = app_config.team_context
            app_resp.team_mode = app_config.team_mode

            logger.info(f"[APP_DETAIL] 加载配置后:")
            logger.info(f"  - team_mode: {app_resp.team_mode}")
            logger.info(f"  - team_context: {app_resp.team_context}")
            logger.info(f"  - team_context type: {type(app_resp.team_context)}")
            if app_resp.team_context and isinstance(app_resp.team_context, dict):
                logger.info(
                    f"  - team_context.use_sandbox: {app_resp.team_context.get('use_sandbox')}"
                )

            # app_resp.language =
            app_resp.param_need = (
                app_config.layout.chat_in_layout if app_config.layout else None
            )
            app_resp.recommend_questions = app_config.recommend_questions

            app_resp.config_version = app_config.version_info
            app_resp.config_code = app_config.code

            app_resp.layout = app_config.layout
            app_resp.custom_variables = app_config.custom_variables

            app_resp.llm_config = app_config.llm_config
            app_resp.ext_config = app_config.ext_config

            app_resp.context_config = build_by_agent_config(app_config.context_config)

            ## Agent版本 - 优先使用配置中的版本，否则回退到应用表的版本
            config_agent_version = getattr(app_config, "agent_version", None)
            app_resp.agent_version = (
                config_agent_version or getattr(app_resp, "agent_version", "v1") or "v1"
            )

            ## 资源-知识
            if app_config.resource_knowledge:
                app_resp.resource_knowledge = app_config.resource_knowledge
                all_resources.extend(app_config.resource_knowledge)
            ## 资源-工具
            logger.info(
                f"[APP_DETAIL] app_config.resource_tool is None: {app_config.resource_tool is None}"
            )
            if app_config.resource_tool:
                logger.info(
                    f"[APP_DETAIL] app_config.resource_tool count: {len(app_config.resource_tool)}"
                )
                app_resp.resource_tool = app_config.resource_tool
                all_resources.extend(app_config.resource_tool)
            else:
                logger.warning(
                    f"[APP_DETAIL] app_config.resource_tool is None or empty!"
                )
            ## 资源-agent app
            if app_config.resource_agent:
                app_resp.resource_agent = app_config.resource_agent
                all_resources.extend(app_config.resource_agent)

            ## 资源-其他扩展资源
            if app_config.resources:
                app_resp.resources = app_config.resources
                all_resources.extend(app_config.resources)

            # if not building_mode:
            app_resp.all_resources = all_resources

            logger.info(
                f"[APP_DETAIL][PERF] 处理资源配置总耗时: {(time.time() - _config_process_start) * 1000:.2f}ms"
            )

            _step_start = time.time()
            from derisk.agent.core.plan.unified_context import UnifiedTeamContext

            logger.info(
                f"[APP_DETAIL][PERF] 导入UnifiedTeamContext耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )

            if isinstance(app_config.team_context, SingleAgentContext):
                app_resp.agent = app_config.team_context.agent_name
            elif isinstance(app_config.team_context, UnifiedTeamContext):
                app_resp.agent = app_config.team_context.agent_name
            else:
                if app_config.team_context:
                    app_resp.agent = app_config.team_context.teamleader

            ## 处理ReasoningAgent
            reasoning_engine_resource: Optional[AgentResource] = None
            r_engine_system_prompt_t: Optional[str] = None
            r_engine_user_prompt_t: Optional[str] = None

            _step_start = time.time()
            ag_mg = get_agent_manager()
            ag = ag_mg.get(app_resp.agent)
            logger.info(
                f"[APP_DETAIL][PERF] 获取agent manager耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )

            agent_version = getattr(app_config, "agent_version", "v1") or "v1"
            is_v2_agent = agent_version == "v2"

            if ag and ag.is_reasoning_agent:
                app_resp.is_reasoning_engine_agent = True

                if app_config.resources:
                    for resource in app_config.resources:
                        if resource.type == ResourceType.ReasoningEngine.value:
                            reasoning_engine_resource = resource
                            break
                if reasoning_engine_resource:
                    reasoning_engine_value = {}
                    if isinstance(reasoning_engine_resource.value, str):
                        reasoning_engine_value = json.loads(
                            reasoning_engine_resource.value
                        )
                    elif isinstance(reasoning_engine_resource.value, dict):
                        reasoning_engine_value = reasoning_engine_resource.value
                    reasoning_engine_name = (
                        reasoning_engine_value.get("name")
                        if reasoning_engine_value
                        else None
                    )
                    if reasoning_engine_name:
                        from derisk.agent.core.reasoning.reasoning_engine import (
                            ReasoningEngine,
                        )

                        reasoning_engine = ReasoningEngine.get_reasoning_engine(
                            reasoning_engine_name
                        )
                        r_engine_user_prompt_t = reasoning_engine.user_prompt_template
                        r_engine_system_prompt_t = (
                            reasoning_engine.system_prompt_template
                        )

            ## 处理prompt
            ### 如果配置里没有可用的prompt模版，进行初始化(ReasongAgent还需要继续根据配置的推理引擎进行初始化)
            if not app_config.system_prompt_template and building_mode:
                if app_resp.is_reasoning_engine_agent:
                    logger.info("构建模式初始化推理引擎system_prompt模版！")
                    if r_engine_system_prompt_t:
                        app_resp.system_prompt_template = r_engine_system_prompt_t
                elif is_v2_agent:
                    logger.info("构建模式初始化Core_v2 Agent system_prompt模版！")
                    app_resp.system_prompt_template = _get_v2_agent_system_prompt(
                        app_config
                    )
                else:
                    if not app_resp.team_mode == TeamMode.NATIVE_APP.value and ag:
                        prompt_template, template_format = ag.prompt_template(
                            "system", app_resp.language
                        )
                        app_resp.system_prompt_template = prompt_template
                    elif not app_resp.team_mode == TeamMode.NATIVE_APP.value:
                        logger.warning(
                            f"Agent [{app_resp.agent}] not found in AgentManager, using default prompt"
                        )
                        app_resp.system_prompt_template = _get_default_system_prompt()
            else:
                app_resp.system_prompt_template = app_config.system_prompt_template

            if not app_config.user_prompt_template and building_mode:
                if app_resp.is_reasoning_engine_agent:
                    logger.info("构建模式初始化推理引擎user_prompt模版！")
                    if r_engine_user_prompt_t:
                        app_resp.user_prompt_template = r_engine_user_prompt_t
                elif is_v2_agent:
                    logger.info("构建模式初始化Core_v2 Agent user_prompt模版！")
                    app_resp.user_prompt_template = _get_v2_agent_user_prompt(
                        app_config
                    )
                else:
                    if not app_resp.team_mode == TeamMode.NATIVE_APP.value and ag:
                        logger.info(f"初始化[{app_resp.agent}]user_prompt模版！")
                        prompt_template, template_format = ag.prompt_template(
                            "user", app_resp.language
                        )
                        app_resp.user_prompt_template = prompt_template
                    elif not app_resp.team_mode == TeamMode.NATIVE_APP.value:
                        app_resp.user_prompt_template = _get_default_user_prompt()
            else:
                app_resp.user_prompt_template = app_config.user_prompt_template

            if not app_resp.team_mode == TeamMode.NATIVE_APP.value:
                if not app_config.custom_variables and ag:
                    logger.info(f"构建模式初始化[{app_resp.agent}]的默认参数！")
                    app_resp.custom_variables = ag.init_variables()
            ## 处理关联的推荐问题
            _step_start = time.time()
            app_recommend_questions = self.recommend_question_dao.get_list(
                {"app_code": app_resp.app_code}
            )
            logger.info(
                f"[APP_DETAIL][PERF] 查询推荐问题耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )
            if app_recommend_questions:
                app_resp.recommend_questions = app_recommend_questions

            logger.info(
                f"[APP_DETAIL][PERF] sync_app_detail总耗时: {(time.time() - _total_start) * 1000:.2f}ms"
            )
            return app_resp
        else:
            logger.info(f"当前应用无配置代码，兼容旧数据模式！")
            result = self.sync_old_app_detail(app_code, building_mode)
            logger.info(
                f"[APP_DETAIL][PERF] sync_old_app_detail总耗时: {(time.time() - _total_start) * 1000:.2f}ms"
            )
            return result

    def app_detail_to_resource(self, app_info: ServerResponse):
        import time

        _start = time.time()

        ## 处理关联的App(agent)明细
        if not app_info.app_code:
            return app_info

        app_details = app_info.details
        agent_resources = []
        details = []
        if app_details and len(app_details) > 0:
            for idx, item in enumerate(app_details):
                if item.type == "app":
                    _query_start = time.time()
                    item_info = self.get(ServeRequest(app_code=item.agent_role))
                    logger.info(
                        f"[APP_DETAIL][PERF] app_detail_to_resource 查询关联app[{item.agent_role}]耗时: {(time.time() - _query_start) * 1000:.2f}ms"
                    )
                    if not item_info:
                        logger.warning(f"绑定应用[{item.agent_role}]已经不存在！")
                        continue
                    agent_resources.append(
                        AgentResource(
                            type=ResourceType.App.value,
                            value=json.dumps(
                                {
                                    "name": f"{item_info.app_name}({item_info.app_code})",
                                    "app_code": item_info.app_code,
                                    "app_name": item_info.app_name,
                                    "app_describe": item_info.app_describe,
                                    "icon": item_info.icon,
                                },
                                ensure_ascii=False,
                            ),
                            name=f"{item_info.app_name}({item_info.app_code})",
                            unique_id=uuid.uuid4().hex,
                        )
                    )
                    details.append(
                        GptsAppDetail(
                            app_code=app_info.app_code,
                            app_name=app_info.app_name,
                            type=item.type,
                            agent_name=item_info.app_name,
                            agent_role=item.agent_role,
                            agent_icon=item_info.icon,
                            agent_describe=item_info.app_describe,
                            node_id=item.node_id,
                            resources=None,
                            prompt_template=None,
                            llm_strategy=None,
                            llm_strategy_value=None,
                            created_at=item.created_at,
                            updated_at=item.updated_at,
                        )
                    )
                else:
                    details.append(GptsAppDetail.from_dict(item.to_dict()))

        app_info.details = details
        app_info.resource_agent = agent_resources
        logger.info(
            f"[APP_DETAIL][PERF] app_detail_to_resource 总耗时(共{len(app_details) if app_details else 0}个detail): {(time.time() - _start) * 1000:.2f}ms"
        )
        return app_info

    async def app_detail(
        self,
        app_code: str,
        specify_config_code: Optional[str] = None,
        building_mode: bool = True,
    ) -> Optional[ServerResponse]:
        return self.sync_app_detail(app_code, specify_config_code, building_mode)

    def old_app_switch_new_app(
        self, gpts_app: ServeRequest, building_mode: bool = True
    ) -> ServerResponse:
        import time

        _start = time.time()

        all_resources = []
        if gpts_app.team_context:
            if (
                hasattr(gpts_app.team_context, "resources")
                and gpts_app.team_context.resources
            ):
                all_resources = deepcopy(gpts_app.team_context.resources)
                if building_mode:
                    gpts_app.team_context.resources = None

            if gpts_app.team_context.llm_strategy:
                gpts_app.llm_config = LLMResource(
                    llm_strategy=gpts_app.team_context.llm_strategy,
                    llm_strategy_value=gpts_app.team_context.llm_strategy_value,
                )
                if building_mode:
                    gpts_app.team_context.llm_strategy = None
                    gpts_app.team_context.llm_strategy_value = None

        # 获取当前应用对应的Agent信息
        from derisk.agent.core.plan.unified_context import UnifiedTeamContext

        if isinstance(gpts_app.team_context, SingleAgentContext):
            gpts_app.agent = gpts_app.team_context.agent_name
        elif isinstance(gpts_app.team_context, UnifiedTeamContext):
            gpts_app.agent = gpts_app.team_context.agent_name
        else:
            if gpts_app.team_context:
                gpts_app.agent = gpts_app.team_context.teamleader

        # 上下文工程配置
        gpts_app.context_config = build_by_agent_config(gpts_app.context_config)

        from derisk.agent import ResourceType

        # if not building_mode:
        gpts_app.all_resources = deepcopy(all_resources)

        ## 兼容旧版ReasoningAgent的资源配置
        engine_resources = (
            self._pop_resource(all_resources, [ResourceType.ReasoningEngine.value])
            if all_resources
            else None
        )
        try:
            _step_start = time.time()
            ag_mg = get_agent_manager()
            ag = ag_mg.get(gpts_app.agent)
            logger.info(
                f"[APP_DETAIL][PERF] old_app_switch_new_app 获取agent manager耗时: {(time.time() - _step_start) * 1000:.2f}ms"
            )

            if engine_resources:
                gpts_app.is_reasoning_engine_agent = True
                ## 推理引擎资源取出去还要放回来
                all_resources.extend(engine_resources)
                reasoning_engine: AgentResource = engine_resources[0]
                reasoning_engine_value = json.loads(reasoning_engine.value)

                re_system_prompt_tempalte = reasoning_engine_value.get(
                    "system_prompt_template"
                )
                if re_system_prompt_tempalte is not None:
                    gpts_app.system_prompt_template = re_system_prompt_tempalte
                else:
                    gpts_app.system_prompt_template = ""
                re_user_prompt_template = reasoning_engine_value.get("prompt_template")
                if re_user_prompt_template is not None:
                    gpts_app.user_prompt_template = re_user_prompt_template
                else:
                    gpts_app.user_prompt_template = ""
                # reasoning_arg_suppliers = reasoning_engine_value.get("reasoning_arg_suppliers")
            else:
                if gpts_app.team_context:
                    agent_version = getattr(gpts_app, "agent_version", "v1") or "v1"
                    is_v2_agent = agent_version == "v2"

                    if gpts_app.team_context.prompt_template:
                        gpts_app.system_prompt_template = (
                            gpts_app.team_context.prompt_template
                        )
                    elif is_v2_agent:
                        logger.info(
                            "旧版应用同步：初始化Core_v2 Agent system_prompt模版！"
                        )
                        gpts_app.system_prompt_template = _get_v2_agent_system_prompt(
                            None
                        )
                    elif ag:
                        prompt_template, template_format = ag.prompt_template(
                            "system", gpts_app.language
                        )
                        gpts_app.system_prompt_template = prompt_template
                    else:
                        gpts_app.system_prompt_template = _get_default_system_prompt()

                    if gpts_app.team_context.user_prompt_template:
                        gpts_app.user_prompt_template = (
                            gpts_app.team_context.user_prompt_template
                        )
                    elif is_v2_agent:
                        logger.info(
                            "旧版应用同步：初始化Core_v2 Agent user_prompt模版！"
                        )
                        gpts_app.user_prompt_template = _get_v2_agent_user_prompt(None)
                    elif ag:
                        prompt_template, template_format = ag.prompt_template(
                            "user", gpts_app.language
                        )
                        gpts_app.user_prompt_template = prompt_template
                    else:
                        gpts_app.user_prompt_template = _get_default_user_prompt()

                    # if building_mode:
                    #     gpts_app.team_context.prompt_template = None
                    #     gpts_app.team_context.user_prompt_template = None

            gpts_app.resource_tool = self._pop_resource(
                all_resources,
                [
                    ResourceType.Tool.value,
                    "mcp(derisk)",
                    "tool(mcp(sse))",
                    "tool(local)",
                ],
            )
            gpts_app.resource_knowledge = self._pop_resource(
                all_resources,
                [ResourceType.Knowledge.value, ResourceType.KnowledgePack.value],
            )
            ## 处理旧版Agent App关联为App资源
            if gpts_app.details:
                gpts_app = self.app_detail_to_app_resource(gpts_app, gpts_app.details)
            new_res_agent = self._pop_resource(all_resources, [ResourceType.App.value])
            if new_res_agent:
                if gpts_app.resource_agent:
                    gpts_app.resource_agent.extend(new_res_agent)
                else:
                    gpts_app.resource_agent = new_res_agent

            ## 处理旧版本的额外资源
            gpts_app.resources = all_resources

        except Exception as e:
            logger.warning(str(e), e)
            raise ValueError(f"应用编辑数据转换异常！{str(e)}")
        gpts_app.config_code = None
        gpts_app.config_version = (
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}{TEMP_VERSION_SUFFIX}"
        )
        ## 处理关联APP
        if gpts_app.app_code:
            gpts_app = self.app_detail_to_resource(gpts_app)

        logger.info(
            f"[APP_DETAIL][PERF] old_app_switch_new_app 总耗时: {(time.time() - _start) * 1000:.2f}ms"
        )
        return gpts_app

    def sync_old_app_detail(self, app_code: str, building_mode: bool = True):
        import time

        _start = time.time()

        _step_start = time.time()
        app_resp = self.dao.get_one({"app_code": app_code})
        logger.info(
            f"[APP_DETAIL][PERF] sync_old_app_detail 查询应用基础信息耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        ## 获取旧版数据的应用明细信息
        _step_start = time.time()
        app_resp.details = self.detail_app_dao.get_list({"app_code": app_code})
        logger.info(
            f"[APP_DETAIL][PERF] sync_old_app_detail 查询detail_app耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        ## 处理关联的推荐问题
        _step_start = time.time()
        app_recommend_questions = self.recommend_question_dao.get_list(
            {"app_code": app_code}
        )
        logger.info(
            f"[APP_DETAIL][PERF] sync_old_app_detail 查询推荐问题耗时: {(time.time() - _step_start) * 1000:.2f}ms"
        )

        if app_recommend_questions:
            app_resp.recommend_questions = app_recommend_questions

        result = self.old_app_switch_new_app(app_resp, building_mode)
        logger.info(
            f"[APP_DETAIL][PERF] sync_old_app_detail 总耗时: {(time.time() - _start) * 1000:.2f}ms"
        )
        return result

    def _get_available_llm_models(self) -> List[str]:
        """获取当前可用的 LLM 模型列表

        使用系统中已注册的 ModelConfigCache 获取用户配置的模型列表。
        如果 ModelConfigCache 为空，会尝试从配置中主动加载。

        Returns:
            List[str]: 可用的 LLM 模型名称列表
        """
        try:
            from derisk.agent.util.llm.model_config_cache import (
                ModelConfigCache,
                parse_provider_configs,
            )

            # 从 ModelConfigCache 获取所有已注册的模型
            all_models = ModelConfigCache.get_all_models()

            # 如果 ModelConfigCache 为空，尝试从配置中加载
            if not all_models and CFG.SYSTEM_APP and CFG.SYSTEM_APP.config:
                logger.info("ModelConfigCache 为空，尝试从配置中加载模型...")
                agent_llm_conf = CFG.SYSTEM_APP.config.get("agent.llm")
                if not agent_llm_conf:
                    agent_conf = CFG.SYSTEM_APP.config.get("agent")
                    if isinstance(agent_conf, dict):
                        agent_llm_conf = agent_conf.get("llm")

                if agent_llm_conf:
                    model_configs = parse_provider_configs(agent_llm_conf)
                    if model_configs:
                        ModelConfigCache.register_configs(model_configs)
                        logger.info(
                            f"已从配置加载 {len(model_configs)} 个模型到 ModelConfigCache"
                        )
                        all_models = ModelConfigCache.get_all_models()

            if all_models:
                logger.info(f"从 ModelConfigCache 获取到可用的 LLM 模型: {all_models}")
                return all_models
        except Exception as e:
            logger.warning(f"从 ModelConfigCache 获取模型列表失败: {str(e)}")

        # 兜底：返回默认模型
        default_models = ["deepseek-v3", "deepseek-r1"]
        logger.warning(f"无法获取可用模型，使用默认模型: {default_models}")
        return default_models

    def _update_llm_config(self, app_data: dict) -> dict:
        """更新应用的 LLM 配置，使用当前可用的模型

        Args:
            app_data: 应用配置数据

        Returns:
            dict: 更新后的应用配置数据
        """
        if "llm_config" not in app_data:
            return app_data

        available_models = self._get_available_llm_models()

        # 深拷贝以避免修改原始数据
        app_data = deepcopy(app_data)
        llm_config = app_data.get("llm_config", {})

        # 更新 llm_strategy_value 为当前可用的模型
        if llm_config:
            original_strategy = llm_config.get("llm_strategy", "priority")
            llm_config["llm_strategy_value"] = available_models
            app_data["llm_config"] = llm_config
            logger.info(
                f"更新应用 [{app_data.get('app_name')}] 的模型配置: "
                f"strategy={original_strategy}, models={available_models}"
            )

        return app_data

    def _convert_llm_config_to_resource(self, request: ServeRequest) -> ServeRequest:
        """将字典形式的 llm_config 转换为 LLMResource 对象

        Args:
            request: 应用请求对象

        Returns:
            ServeRequest: 转换后的请求对象
        """
        if request.llm_config and isinstance(request.llm_config, dict):
            from derisk_serve.building.config.api.schemas import LLMResource

            try:
                request.llm_config = LLMResource(**request.llm_config)
                logger.info(
                    f"应用 [{request.app_code}] 的 llm_config 已转换为 LLMResource 对象: "
                    f"strategy={request.llm_config.llm_strategy}, "
                    f"value={request.llm_config.llm_strategy_value}"
                )
            except Exception as e:
                logger.warning(f"转换 llm_config 失败: {str(e)}")
        return request

    async def load_define_app(self):
        """加载并初始化内置的默认应用

        系统启动时自动初始化 derisk_app_define 目录下的默认应用。
        如果应用已存在则跳过，确保应用初始化后处于发布状态。
        模型配置会动态从当前可用的 agent 模型配置中获取。
        """
        logger.info("开始加载内置默认应用数据")
        # 1. 获取当前脚本所在目录
        import os

        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 2. 构建目标文件夹路径
        target_folder = os.path.join(current_dir, "derisk_app_define")

        # 3. 检查文件夹是否存在
        if not os.path.exists(target_folder):
            logger.warning(f"应用定义目录不存在: {target_folder}，跳过内置应用初始化")
            return

        # 4. 获取所有JSON文件
        json_files = [
            f
            for f in os.listdir(target_folder)
            if f.endswith(".json") and os.path.isfile(os.path.join(target_folder, f))
        ]

        # 5. 加载并解析所有JSON文件
        initialized_count = 0
        skipped_count = 0

        for file in json_files:
            file_path = os.path.join(target_folder, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
                    for item in json_data:
                        app_code = item.get("app_code")
                        app_name = item.get("app_name")
                        if not app_code:
                            continue

                        logger.info(f"检查应用 [{app_name}:{app_code}]")

                        # 冲突检测 - 检查应用是否已存在
                        existing_app = self.get(ServeRequest(app_code=app_code))
                        if existing_app:
                            logger.info(
                                f"应用 [{app_code}-{app_name}] 已存在，跳过初始化"
                            )
                            skipped_count += 1
                            continue

                        # 动态更新模型配置
                        updated_item = self._update_llm_config(item)

                        # 创建 ServeRequest 对象
                        request = ServeRequest.from_dict(updated_item)

                        # 转换 llm_config 为 LLMResource 对象（如果是字典）
                        request = self._convert_llm_config_to_resource(request)

                        # 创建并发布应用
                        await self.new_define_app(request=request)
                        initialized_count += 1
                        logger.info(f"应用 [{app_name}] 初始化并发布成功")

                logger.info(f"应用配置文件 {file} 加载完成")
            except Exception as e:
                logger.error(f"应用加载失败 {file}: {str(e)}", exc_info=True)

        logger.info(
            f"内置应用初始化完成: 新初始化 {initialized_count} 个, 跳过 {skipped_count} 个"
        )

    # 保持向后兼容的别名
    async def looad_define_app(self):
        """已废弃：请使用 load_define_app"""
        await self.load_define_app()

    def get(self, request: ServeRequest) -> Optional[ServerResponse]:
        """Get a App entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """

        # Build the query request from the request
        query_request = {}
        if request.app_code:
            query_request["app_code"] = request.app_code
        if request.app_name is not None:
            query_request["app_name"] = request.app_name
        if request.published is not None:
            query_request["published"] = request.published

        return self.dao.get_one(query_request)

    def get_by_name(self, name: str) -> Optional[ServerResponse]:
        """Get a App entity

        Args:
            name (str): The name

        Returns:
            ServerResponse: The response
        """

        session = self.dao.get_raw_session()
        try:
            app_qry = session.query(ServeEntity)
            app_qry = app_qry.filter(ServeEntity.app_name == name)
            result = app_qry.first()
            if result is None:
                return None
            return self.dao.to_response(result)
        finally:
            session.close()

    async def delete_app(self, app_code: str):
        query_request = {"app_code": app_code}
        self.dao.delete(query_request)

    def delete(self, request: ServeRequest) -> None:
        """Delete a App entity

        Args:
            request (ServeRequest): The request
        """

        # Build the query request from the request
        query_request = {}
        if request.app_code:
            query_request["app_code"] = request.app_code
        if request.app_name:
            query_request["app_name"] = request.app_name

        self.dao.delete(query_request)

    def get_list(self, request: ServeRequest) -> List[ServerResponse]:
        """Get a list of App entities

        Args:
            request (ServeRequest): The request

        Returns:
            List[ServerResponse]: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self.dao.get_list(query_request)

    def get_list_by_page(
        self, request: ServeRequest, page: int, page_size: int
    ) -> PaginationResult[ServerResponse]:
        """Get a list of App entities by page

        Args:
            request (ServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[ServerResponse]: The response
        """
        query_request = request
        return self.dao.get_list_page(query_request, page, page_size)

    async def list_hot_apps(self, query: GptsAppQuery):
        from derisk.storage.chat_history.chat_history_db import ChatHistoryDao

        chat_history_dao = ChatHistoryDao()
        hot_app_map = chat_history_dao.get_hot_app_map(query.page - 1, query.page_size)
        logger.info(f"hot_app_map = {hot_app_map}")
        hot_map = {}
        for hp in hot_app_map:
            hot_map[hp.get("app_code")] = hp.get("sz")
        app_codes = [hot_app.get("app_code") for hot_app in hot_app_map]
        if len(app_codes) == 0:
            return []
        apps = await self.app_list(
            GptsAppQuery(app_codes=app_codes, hot_map=hot_map, need_owner_info="true")
        )
        if apps:
            return apps.app_list
        return None

    def add_hub_code(self, app_code: str, app_hub_code: str):
        with self.dao.session() as session:
            app_qry = session.query(ServeEntity).filter(
                ServeEntity.app_code == app_code
            )
            entity = app_qry.one()
            entity.app_hub_code = app_hub_code
            session.merge(entity)
            session.commit()

    def get_hub_code(self, app_code: str) -> Optional[str]:
        app_res = self.get(ServeRequest(app_code=app_code))
        if app_res:
            return app_res.app_hub_code
        return None

    def set_published_status(self, app_code: str, published: int = 1):
        """Set the published status of an app.

        Args:
            app_code: The application code
            published: Published status (0 or 1), default is 1 (published)
        """
        with self.dao.session() as session:
            app_qry = session.query(ServeEntity).filter(
                ServeEntity.app_code == app_code
            )
            entity = app_qry.one()
            entity.published = published
            session.merge(entity)
            session.commit()
            logger.info(f"Set app {app_code} published status to {published}")


def _get_v2_agent_system_prompt(app_config) -> str:
    """
    获取 Core_v2 Agent 的默认 System Prompt

    返回空字符串，让用户编辑的内容作为身份层注入。
    完整的 system prompt 由 PromptAssembler 在运行时动态组装：
    - Layer 1: 身份层（用户编辑的内容）
    - Layer 2: 动态资源层（PromptAssembler 自动注入）
    - Layer 3: 系统控制层（workflow/exceptions/delivery）
    """
    return ""


def _get_v2_agent_user_prompt(app_config) -> str:
    """
    获取 Core_v2 Agent 的默认 User Prompt

    返回空字符串，让用户编辑的内容作为前缀注入。
    完整的 user prompt 由 PromptAssembler 在运行时动态组装：
    - 用户编辑的自定义内容
    - 历史对话（动态注入）
    - 用户问题（动态注入）
    """
    return ""


def _get_default_system_prompt() -> str:
    """获取默认的 System Prompt（当 Agent 未在 AgentManager 中注册时）

    返回空字符串，让用户编辑的内容作为身份层注入。
    """
    return ""


def _get_default_user_prompt() -> str:
    """获取默认的 User Prompt

    返回空字符串，让用户编辑的内容作为前缀注入。
    """
    return ""
