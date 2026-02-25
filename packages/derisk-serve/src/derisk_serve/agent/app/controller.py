import json
import logging
import asyncio
from typing import List, Optional

import aiohttp
import pymysql
from fastapi import APIRouter, Depends, Request

from derisk import SystemApp
from derisk._private.config import Config
from derisk.agent.core.agent_manage import get_agent_manager
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.resource.manage import get_resource_manager
from derisk.agent.util.llm.llm import LLMStrategyType
from derisk_app.openapi.api_view_model import Result
from derisk_serve.agent.app.gpts_server import available_llms
from derisk_serve.agent.db.gpts_app import (
    GptsApp,
    GptsAppDao,
    TransferSseRequest,
)
from derisk_serve.agent.db.gpts_tool import (
    GptsTool,
    GptsToolDao,
    ExecuteToolRequest,
    DbQueryRequest,
)
from derisk_serve.agent.resource.func_registry import central_registry
from derisk_serve.agent.team.base import TeamMode
from derisk_serve.building.app.api.schema_app import GptsAppQuery

from derisk_serve.building.config.service.service import Service as AppConfigService
from derisk_serve.building.app.service.service import Service as AppService
from derisk_serve.core import blocking_func_to_async
from derisk_serve.utils.auth import UserRequest, get_user_from_headers

CFG = Config()

router = APIRouter()
logger = logging.getLogger(__name__)

gpts_dao = GptsAppDao()
gpts_tool_dao = GptsToolDao()

global_system_app: Optional[SystemApp] = None


def get_app_config_service() -> AppConfigService:
    """Get the service instance"""
    return AppConfigService.get_instance(CFG.SYSTEM_APP)


def get_app_service() -> AppService:
    return AppService.get_instance(CFG.SYSTEM_APP)


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
    type: str = None,  # Added type parameter
    user_info: UserRequest = Depends(get_user_from_headers),
):
    try:
        results = []
        if type == LLMStrategyType.Priority.value:
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
    query: Optional[str] = None,
    version: Optional[str] = None,
    user_info: UserRequest = Depends(get_user_from_headers),
):
    """
    Get agent resources, such as db, knowledge, internet, plugin.
    """
    try:
        user_code = None
        sys_code = None
        if user_info:
            user_code: Optional[str] = user_info.user_id
            sys_code: Optional[str] = user_info.user_name

        # Determine if we should call as async or sync wrapped in thread
        # In newer version, get_supported_resources is async
        resource_manager = get_resource_manager()
        if hasattr(resource_manager.get_supported_resources, "__call__") and (
            asyncio.iscoroutinefunction(resource_manager.get_supported_resources)
            or (
                hasattr(resource_manager.get_supported_resources, "__func__")
                and asyncio.iscoroutinefunction(
                    resource_manager.get_supported_resources.__func__
                )
            )
        ):
            # It's an async function, call directly
            resources = await resource_manager.get_supported_resources(
                version=version or "v1",
                type=type,
                query=query,
                name=name,
                cache_enable=False,
                user_code=user_code,
                sys_code=sys_code,
            )
        else:
            # It's a sync function, wrap it
            resources = await blocking_func_to_async(
                CFG.SYSTEM_APP,
                resource_manager.get_supported_resources,
                version=version or "v1",
                type=type,
                query=query,
                name=name,
                cache_enable=False,
                user_code=user_code,
                sys_code=sys_code,
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
                resource_value = json.loads(resource.value)
                # For skill resources, get sandbox path
                if resource_type == "skill" or resource.type.startswith("skill"):
                    try:
                        from derisk_serve.skill.service.service import (
                            Service,
                            SKILL_SERVICE_COMPONENT_NAME,
                        )

                        skill_code = (
                            resource_value.get("skill_code")
                            or resource_value.get("skillCode")
                            or resource_value.get("skill_name")
                            or resource_value.get("name")
                        )
                        if skill_code:
                            skill_service = CFG.SYSTEM_APP.get_component(
                                SKILL_SERVICE_COMPONENT_NAME, Service, default=None
                            )
                            if skill_service:
                                sandbox_path = skill_service.get_skill_directory(
                                    skill_code
                                )
                                if sandbox_path:
                                    resource_value["skill_path"] = sandbox_path
                                    resource_value["path"] = sandbox_path
                    except Exception as skill_e:
                        logger.warning(f"Error getting sandbox skill path: {skill_e}")
                return Result.succ(resource_value)
    except Exception as ex:
        logger.exception(str(ex))
        return Result.failed(code="E000X", msg=f"query app resources error: {ex}")


@router.get("/v1/derisks/list", response_model=Result[List[GptsApp]])
async def get_derisks(user_code: str = None, sys_code: str = None):
    logger.info(f"get_derisks:{user_code},{sys_code}")
    try:
        query: GptsAppQuery = GptsAppQuery()
        query.ignore_user = "true"
        app_servoce = get_app_service()
        response = await app_servoce.app_list(query, True)
        return Result.succ(response.app_list)
    except Exception as e:
        logger.exception(f"get_derisks failed:{str(e)}")
        return Result.failed(msg=str(e), code="E300003")


@router.post("/v1/tool/create")
async def create_tool(
    gpts_tool: GptsTool,
    user_request: UserRequest = Depends(get_user_from_headers),
):
    try:
        await blocking_func_to_async(CFG.SYSTEM_APP, gpts_tool_dao.create, gpts_tool)
        return Result.succ()
    except Exception as e:
        return Result.failed(code="E000X", msg=f"create tool error: {e}")


@router.post("/v1/tool/update")
async def update_tool(
    gpts_tool: GptsTool,
    user_request: UserRequest = Depends(get_user_from_headers),
):
    try:
        await blocking_func_to_async(
            CFG.SYSTEM_APP, gpts_tool_dao.update_tool, gpts_tool
        )
        return Result.succ()
    except Exception as e:
        return Result.failed(code="E000X", msg=f"update tool error: {e}")


@router.get("/v1/tool/{tool_id}")
async def query_tool(tool_id: str):
    try:
        return Result.succ(gpts_tool_dao.get_tool_by_tool_id(tool_id))
    except Exception as e:
        return Result.failed(code="E000X", msg=f"get tool error: {e}")


@router.get("/v1/tool")
async def query_tool(type: str, user_id: str = None):
    try:
        tools = gpts_tool_dao.get_tool_by_type(type)
        if not user_id:
            return Result.succ(tools)
        filter_tools = []
        for tool in tools:
            if tool.owner == user_id or tool.owner == "derisk":
                filter_tools.append(tool)
        return Result.succ(filter_tools)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"get tool error: {e}")


@router.get("/v1/agent/default-prompt")
async def get_agent_default_prompt(
    agent_name: str,
    language: str = "en",
    user_info: UserRequest = Depends(get_user_from_headers),
):
    """
    Get the default prompt templates for a specified agent.

    Args:
        agent_name: The name/role of the agent
        language: The language preference (default: "en")
        user_info: User information from headers

    Returns:
        Result with system_prompt_template and user_prompt_template
    """
    try:
        agent_manager = get_agent_manager()
        agent = agent_manager.get_agent(agent_name)

        if agent is None:
            return Result.failed(code="E4004", msg=f"Agent '{agent_name}' not found")

        result = {
            "system_prompt_template": _get_prompt_template(
                agent.profile.system_prompt_template, language
            ),
            "user_prompt_template": _get_prompt_template(
                agent.profile.user_prompt_template, language
            ),
        }

        return Result.succ(result)
    except ValueError as e:
        return Result.failed(code="E4004", msg=str(e))
    except Exception as e:
        logger.exception(f"Get agent default prompt error: {e}")
        return Result.failed(code="E000X", msg=f"get agent default prompt error: {e}")


def _get_prompt_template(template, language: str) -> str:
    """
    Extract the prompt template string.

    Args:
        template: The template (string or PromptTemplate object)
        language: The language preference

    Returns:
        The template string
    """
    if template is None:
        return ""

    if isinstance(template, str):
        return template

    if hasattr(template, "template"):
        return template.template

    if hasattr(template, "__str__"):
        return str(template)

    return ""


@router.delete("/v1/tool/{tool_id}")
async def delete_tool(tool_id: str):
    try:
        return Result.succ(gpts_tool_dao.delete_by_tool_id(tool_id))
    except Exception as e:
        return Result.failed(code="E000X", msg=f"delete tool error: {e}")


@router.post("/v1/tool/execute")
async def execute_tool(
    execute_request: ExecuteToolRequest,
    user_request: UserRequest = Depends(get_user_from_headers),
    request: Request = None,
):
    global result
    cookie = str(request.headers.get("Cookie", ""))
    try:
        if execute_request.type.lower() == "local":
            central_registry.set_context_entry("Cookie", cookie)
            class_name, method_name = (
                execute_request.config.get("class_name", None),
                execute_request.config.get("method_name", None),
            )
            result = await central_registry.call_registered_function(
                class_name, method_name, **execute_request.params
            )
        elif execute_request.type.lower() == "http":
            url, headers = (
                execute_request.config.get("url", None),
                execute_request.config.get("headers", None),
            )
            method, plugin = (
                execute_request.config.get("method", None),
                execute_request.config.get("plugin", None),
            )
            timeout, params = (
                execute_request.config.get("timeout", 60),
                execute_request.params,
            )
            if plugin:
                exec(str(plugin), globals())
                params, headers = convert_request(params=params, headers=headers)
            if cookie and headers:
                headers["Cookie"] = cookie
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                if method == "GET":
                    async with session.get(
                        url, headers=headers, params=params, ssl=False
                    ) as response:
                        response.raise_for_status()
                        result = await response.text()
                elif method == "POST":
                    async with session.post(
                        url, headers=headers, json=params, ssl=False
                    ) as response:
                        response.raise_for_status()
                        result = await response.text()
                else:
                    raise ValueError(f"method {method} not supported")
                if plugin:
                    result = convert_response(result)
        else:
            raise ValueError(f"{execute_request.type} type not supported")
        return Result.succ(result)
    except Exception as e:
        return Result.failed(code="E000X", msg=f"execute tool error: {e}")
