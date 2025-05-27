import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends

from derisk._private.config import Config
from derisk.agent.core.agent_manage import get_agent_manager
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.resource.manage import get_resource_manager
from derisk.agent.util.llm.llm import LLMStrategyType
from derisk_app.openapi.api_view_model import Result
from derisk_serve.agent.app.gpts_server import available_llms
from derisk_serve.agent.db.gpts_app import (
    GptsApp,
    GptsAppCollectionDao,
    GptsAppDao,
    GptsAppQuery,
    native_app_params,
    BindAppRequest, TransferSseRequest, mcp_address, AllowToolsRequest,
)
from derisk_serve.agent.team.base import TeamMode
from derisk_serve.core import blocking_func_to_async
from derisk_serve.utils.auth import UserRequest, get_user_from_headers

CFG = Config()

router = APIRouter()
logger = logging.getLogger(__name__)

gpts_dao = GptsAppDao()
collection_dao = GptsAppCollectionDao()


@router.post("/v1/app/create")
async def create(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        res = await blocking_func_to_async(CFG.SYSTEM_APP, gpts_dao.create, gpts_app)
        return Result.succ(res)
    except Exception as ex:
        return Result.failed(code="E000X", msg=f"create app error: {ex}")


@router.post("/v1/app/list")
async def app_list(
    query: GptsAppQuery,
    user_info: UserRequest = Depends(get_user_from_headers),
):
    try:
        # query.user_code = (
        #     user_info.user_id if user_info.user_id is not None else query.user_code
        # )
        query.ignore_user = "true"
        res = await blocking_func_to_async(
            CFG.SYSTEM_APP, gpts_dao.app_list, query, True
        )
        return Result.succ(res)
    except Exception as ex:
        logger.exception("app_list exception!")
        return Result.failed(code="E000X", msg=f"query app list error: {ex}")


@router.get("/v1/app/info")
async def app_detail(
    chat_scene: str,
    app_code: str = None,
):
    logger.info(f"app_detail:{chat_scene},{app_code}")
    try:
        if app_code:
            if app_code == "ai_sre":
                return Result.succ(GptsApp(app_code='ai_sre', app_name="DeRisk(AI-SRE)", app_describe="test",team_mode=TeamMode.AUTO_PLAN.value ))
            else:
                res = await blocking_func_to_async(
                    CFG.SYSTEM_APP, gpts_dao.app_detail, app_code
                )
                return Result.succ(res)
        else:
            from derisk_app.scene.base import ChatScene

            scene: ChatScene = ChatScene.of_mode(chat_scene)
            res = await blocking_func_to_async(
                CFG.SYSTEM_APP, gpts_dao.native_app_detail, scene.scene_name()
            )
            return Result.succ(res)
    except Exception as ex:
        logger.exception("query app detail error!")
        return Result.failed(code="E000X", msg=f"query app detail error: {ex}")


@router.get("/v1/app/export")
async def app_export(
    chat_scene: str,
    app_code: str = None,
):
    logger.info(f"app_export:{app_code}")
    try:
        if app_code:
            app_info = await blocking_func_to_async(
                CFG.SYSTEM_APP, gpts_dao.app_detail, app_code
            )
        else:
            from derisk_app.scene.base import ChatScene

            scene: ChatScene = ChatScene.of_mode(chat_scene)
            app_info = await blocking_func_to_async(
                CFG.SYSTEM_APP, gpts_dao.native_app_detail, scene.scene_name()
            )

        return Result.succ(app_info)
    except Exception as ex:
        logger.exception("export app info error!")
        return Result.failed(code="E000X", msg=f"export app info error: {ex}")


@router.get("/v1/app/{app_code}")
async def get_app_by_code(
    app_code: str,
):
    try:
        return Result.succ(gpts_dao.app_detail(app_code))
    except Exception as ex:
        logger.exception("query app detail error!")
        return Result.failed(code="E000X", msg=f"query app detail error: {ex}")


@router.post("/v1/app/hot/list")
async def hot_app_list(
    query: GptsAppQuery, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        query.user_code = (
            user_info.user_id if user_info.user_id is not None else query.user_code
        )
        list_hot_apps = gpts_dao.list_hot_apps(query)
        return Result.succ(list_hot_apps)
    except Exception as ex:
        logger.exception("hot_app_list exception！")
        return Result.failed(code="E000X", msg=f"query hot app error: {ex}")


@router.post("/v1/app/detail")
async def app_list(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        return Result.succ(gpts_dao.app_detail(gpts_app.app_code))
    except Exception as ex:
        return Result.failed(code="E000X", msg=f"query app error: {ex}")


@router.post("/v1/app/edit")
async def edit(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        return Result.succ(gpts_dao.edit(gpts_app))
    except Exception as ex:
        logger.exception(" app edit exception!")
        return Result.failed(code="E000X", msg=f"edit app error: {ex}")


@router.get("/v1/agents/list")
async def all_agents(user_info: UserRequest = Depends(get_user_from_headers)):
    try:
        agents = get_agent_manager().list_agents()
        for agent in agents:
            label = agent["name"]
            agent["label"] = label
        return Result.succ(agents)
    except Exception as ex:
        return Result.failed(code="E000X", msg=f"query agents error: {ex}")


@router.post("/v1/app/remove", response_model=Result)
async def delete(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        gpts_dao.delete(gpts_app.app_code, gpts_app.user_code, gpts_app.sys_code)
        return Result.succ()
    except Exception as ex:
        logger.exception("app remove exception!")
        return Result.failed(code="E000X", msg=f"delete app error: {ex}")


@router.post("/v1/app/collect", response_model=Result)
async def collect(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        collection_dao.collect(gpts_app.app_code, gpts_app.user_code, gpts_app.sys_code)
        return Result.succ()
    except Exception as ex:
        return Result.failed(code="E000X", msg=f"collect app error: {ex}")


@router.post("/v1/app/uncollect", response_model=Result)
async def uncollect(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        collection_dao.uncollect(
            gpts_app.app_code, gpts_app.user_code, gpts_app.sys_code
        )
        return Result.succ()
    except Exception as ex:
        return Result.failed(code="E000X", msg=f"uncollect app error: {ex}")


@router.get("/v1/team-mode/list")
async def team_mode_list(user_info: UserRequest = Depends(get_user_from_headers)):
    try:
        return Result.succ([mode.to_dict() for mode in TeamMode])
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(code="E000X", msg=f"query team mode list error: {ex}")


@router.get("/v1/resource-type/list")
async def team_mode_list(user_info: UserRequest = Depends(get_user_from_headers)):
    try:
        resources = get_resource_manager().get_supported_resources_type()
        return Result.succ(resources)
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(code="E000X", msg=f"query resource type list error: {ex}")


@router.get("/v1/llm-strategy/list")
async def llm_strategies(user_info: UserRequest = Depends(get_user_from_headers)):
    try:
        return Result.succ([type.to_dict() for type in LLMStrategyType])
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(
            code="E000X", msg=f"query llm strategy type list error: {ex}"
        )


@router.get("/v1/llm-strategy/value/list")
async def llm_strategy_values(
    type: str, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        results = []
        match type:
            case LLMStrategyType.Priority.value:
                results = await available_llms()
        return Result.succ(results)
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(
            code="E000X", msg=f"query llm strategy type list error: {ex}"
        )


@router.get("/v1/app/resources/list", response_model=Result)
async def app_resources(
    type: str,
    name: Optional[str] = None,
    version: Optional[str] = None,
    user_code: Optional[str] = None,
    sys_code: Optional[str] = None,
    user_info: UserRequest = Depends(get_user_from_headers),
):
    """
    Get agent resources, such as db, knowledge, internet, plugin.
    """
    try:
        resources = await blocking_func_to_async(
            CFG.SYSTEM_APP,
            get_resource_manager().get_supported_resources,
            version=version or "v1",
            type=type,
            user_id=None,
        )
        results = resources.get(type, [])
        return Result.succ(results)
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(code="E000X", msg=f"query app resources error: {ex}")


@router.get("/v1/app/resources/get", response_model=Result)
async def app_resources_parameter(
    app_code: str,
    resource_type: str,
    name: Optional[str] = None,
    version: Optional[str] = None,
    user_code: Optional[str] = None,
    sys_code: Optional[str] = None,
    user_info: UserRequest = Depends(get_user_from_headers),
):
    """
    Get agent resources, such as db, knowledge, internet, plugin.
    """
    try:
        app_info = gpts_dao.app_detail(app_code)
        if not app_info.details:
            raise ValueError("app details is None")
        app_detail = app_info.details[0]
        resources = app_detail.resources
        for resource in resources:
            if resource.type == resource_type:
                return Result.succ(json.loads(resource.value))
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(code="E000X", msg=f"query app resources error: {ex}")


@router.post("/v1/app/publish", response_model=Result)
async def publish(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        gpts_dao.publish(gpts_app.app_code, gpts_app.user_code, gpts_app.sys_code)
        return Result.succ([])
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(code="E000X", msg=f"publish app error: {ex}")


@router.post("/v1/app/unpublish", response_model=Result)
async def unpublish(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        gpts_app.user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        gpts_dao.unpublish(gpts_app.app_code, gpts_app.user_code, gpts_app.sys_code)
        return Result.succ([])
    except Exception as ex:
        logger.exception("unpublish:" + str(ex))
        return Result.failed(code="E000X", msg=f"unpublish app error: {ex}")


@router.post("/v1/app/native/init", response_model=Result)
async def init_native_apps(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    try:
        user_code = (
            user_info.user_id if user_info.user_id is not None else gpts_app.user_code
        )
        gpts_dao.init_native_apps(user_code)
        return Result.succ([])
    except Exception as ex:
        logger.exception("init natove error!")
        return Result.failed(code="E000X", msg=f"init natove error: {ex}")


@router.get("/v1/native_scenes")
async def native_scenes(user_info: UserRequest = Depends(get_user_from_headers)):
    return Result.succ(native_app_params())


@router.post("/v1/app/admins/update")
def update_admins(
    gpts_app: GptsApp, user_info: UserRequest = Depends(get_user_from_headers)
):
    return Result.succ(gpts_dao.update_admins(gpts_app.app_code, gpts_app.admins))


@router.get("/v1/app/{app_code}/admins")
async def query_admins(
    app_code: str,
    user_info: UserRequest = Depends(get_user_from_headers),
):
    try:
        return Result.succ(gpts_dao.get_admins(app_code))
    except Exception as ex:
        logger.exception("query_admins:" + str(ex))
        return Result.failed(code="E000X", msg=f"query admins error: {ex}")


@router.get("/v1/derisks/list", response_model=Result[List[GptsApp]])
async def get_derisks(user_code: str = None, sys_code: str = None):
    logger.info(f"get_derisks:{user_code},{sys_code}")
    try:
        query: GptsAppQuery = GptsAppQuery()
        query.ignore_user = "true"
        response = gpts_dao.app_list(query, True)
        return Result.succ(response.app_list)
    except Exception as e:
        logger.error(f"get_derisks failed:{str(e)}")
        return Result.failed(msg=str(e), code="E300003")


@router.post("/v1/derisks/app/bind", response_model=Result[List[GptsApp]])
async def app_bind(bind_app: BindAppRequest, sys_code: str = None):
    logger.info(f"app_bind:{bind_app},{sys_code}")
    try:
        return Result.succ(
            await gpts_dao.auto_team_bin_apps(
                bind_app.team_app_code, bind_app.bin_app_codes
            )
        )
    except Exception as e:
        logger.error(f"get_derisks failed:{str(e)}")
        return Result.failed(msg=str(e), code="E300003")


@router.post("/v1/app/transfer_sse", response_model=Result)
async def transfer_sse(transfer_request: TransferSseRequest):
    try:
        if not transfer_request.all:
            query = GptsAppQuery(
                app_codes=transfer_request.app_code_list
            )
            apps = gpts_dao.app_list(query, True).app_list
        else:
            apps = gpts_dao.list_all()
        for app in apps:
            if app.team_mode != "auto_plan" or app.team_context is None:
                continue
            team_context = None
            if isinstance(app.team_context, AutoTeamContext):
                team_context = app.team_context
            elif isinstance(app.team_context, str):
                try:
                    team_context = AutoTeamContext.model_validate(json.loads(app.team_context))
                except Exception as e:
                    logger.error(f"transfer_sse failed:{str(e)}")
                    continue
            resources = team_context.resources
            if not resources:
                continue
            need_edit = False
            for resource in resources:
                if resource.type != "tool(mcp(sse))":
                    continue
                need_edit = True
                json_val = json.loads(resource.value)
                new_json = mcp_address(transfer_request.source, json_val["name"], transfer_request.uri, transfer_request.faas_function_pre)
                if not new_json:
                    continue
                resource.value = json.dumps(new_json, ensure_ascii=False)
            if need_edit:
                team_context.resources = resources
                if isinstance(app.team_context, AutoTeamContext):
                    app.team_context = team_context
                elif isinstance(app.team_context, str):
                    app.team_context = json.dumps(team_context.to_dict(), ensure_ascii=False)
                gpts_dao.edit(app)
        return Result.succ()
    except Exception as e:
        logger.error(f"transfer_sse failed:{str(e)}")
        return Result.failed(msg=str(e), code="E300003")


@router.post("/v1/app/allow_tools", response_model=Result)
async def edit_app_allow_tools(request: AllowToolsRequest):
    try:
        app = gpts_dao.app_detail(request.app_code)
        if not app:
            return Result.failed(msg=f"app {request.app_code} not exist", code="E300001")
        if app.team_mode != "auto_plan" or app.team_context is None:
            return Result.failed(msg=f"app {request.app_code} not auto plan", code="E300001")
        team_context = None
        if isinstance(app.team_context, AutoTeamContext):
            team_context = app.team_context
        elif isinstance(app.team_context, str):
            try:
                team_context = AutoTeamContext.model_validate(json.loads(app.team_context))
            except Exception as e:
                logger.error(f"edit_app_allow_tools failed:{str(e)}")
                return Result.failed(msg=str(e), code="E300001")
        resources = team_context.resources
        need_edit = False
        for resource in resources:
            if resource.type != "tool(mcp(sse))":
                continue
            json_val = json.loads(resource.value)
            if json_val['name'] != request.mcp_server:
                continue
            need_edit = True
            json_val['allow_tools'] = request.allow_tools
            resource.value = json.dumps(json_val, ensure_ascii=False)
        if need_edit:
            team_context.resources = resources
            if isinstance(app.team_context, AutoTeamContext):
                app.team_context = team_context
            elif isinstance(app.team_context, str):
                app.team_context = json.dumps(team_context.to_dict(), ensure_ascii=False)
            gpts_dao.edit(app)
        return Result.succ()
    except Exception as e:
        logger.error(f"bind_allow_tools failed:{str(e)}")
        return Result.failed(msg=str(e), code="E300003")