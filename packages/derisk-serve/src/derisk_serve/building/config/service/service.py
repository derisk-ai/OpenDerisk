import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict

from derisk._private.config import Config
from derisk.agent import get_agent_manager
from derisk.agent.core.schema import DynamicParam, DynamicParamView
from derisk.component import SystemApp, ComponentType
from derisk.storage.metadata import BaseDao
from derisk.util import ParameterDescription
from derisk.util.pagination_utils import PaginationResult
from derisk.vis.vis_manage import get_vis_manager
from derisk_serve.core import BaseService, blocking_func_to_async

from ..api.schemas import (
    ServeRequest,
    ServerResponse,
    ChatInParam,
    AppParamType,
    ChatInParamDefine,
    ChatInParamType,
)
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import ServeDao, ServeEntity

TEMP_VERSION_SUFFIX = "[.temp]"
CFG = Config()
logger = logging.getLogger(__name__)


class Service(BaseService[ServeEntity, ServeRequest, ServerResponse]):
    """The service class for Building/config"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig, dao: Optional[ServeDao] = None
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: ServeDao = dao
        super().__init__(system_app)

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or ServeDao(self._serve_config)
        self._system_app = system_app

    @property
    def dao(self) -> BaseDao[ServeEntity, ServeRequest, ServerResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    def _deduplicate_resources(self, resources: Optional[List]) -> Optional[List]:
        """Deduplicate resources by type and name.

        For resources like MCP, when the service is re-created, the mcp_code changes.
        This function ensures only the latest resource with same type+name is kept.

        Args:
            resources: List of AgentResource objects

        Returns:
            Deduplicated list of AgentResource objects
        """
        if not resources:
            return resources

        from derisk.agent import AgentResource

        seen = {}
        for resource in resources:
            if not isinstance(resource, AgentResource):
                continue

            resource_type = resource.type
            resource_name = resource.name

            if not resource_type or not resource_name:
                continue

            key = (resource_type, resource_name)
            seen[key] = resource

        result = list(seen.values())
        if len(result) != len(resources):
            logger.info(f"Deduplicated resources: {len(resources)} -> {len(result)}")
        return result if result else resources

    def _deduplicate_request_resources(self, request: ServeRequest) -> None:
        """Deduplicate all resource lists in the request in-place.

        Args:
            request: The request object to deduplicate
        """
        if request.resource_tool:
            request.resource_tool = self._deduplicate_resources(request.resource_tool)
        if request.resource_knowledge:
            request.resource_knowledge = self._deduplicate_resources(
                request.resource_knowledge
            )
        if request.resource_agent:
            request.resource_agent = self._deduplicate_resources(request.resource_agent)
        if request.resources:
            request.resources = self._deduplicate_resources(request.resources)

    async def edit(self, request: ServeRequest) -> ServerResponse:
        """编辑配置，值能编辑对应应用的临时版本配置，如果没有临时版本基于当前内容创建最新的临时版本

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """

        if not request.app_code:
            raise ValueError("当前编辑配置缺少应用代码参数")
        # if not request.editor:
        #     raise ValueError("当前编辑配置缺少编辑者信息参数")

        # Deduplicate resources to handle MCP re-creation scenario
        self._deduplicate_request_resources(request)

        temp_config_request = ServeRequest(
            app_code=request.app_code, is_published=False
        )
        temp_config = await self.get(temp_config_request)

        request.gmt_last_edit = datetime.now()
        if temp_config:
            query_request = {
                "id": temp_config.id,
                "is_published": False,
            }
            ## 控制可以更新的字段， 防止误更新发布等基础逻辑信息字段
            update_req = self.dao.to_update_dict(request)
            return self.dao.update(query_request, update_req, True)
        else:
            # if not request.creator:
            #     raise ValueError("当前编辑配置缺少创建者信息参数")
            request.is_published = False
            request.version_info = (
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}{TEMP_VERSION_SUFFIX}"
            )
            request.code = uuid.uuid4().hex
            request.gmt_create = datetime.now()
            return self.dao.create(request)

    def get_all_chat_in_params(self) -> List[ChatInParamDefine]:
        results: List[ChatInParamDefine] = []
        for item in AppParamType:
            match item:
                case AppParamType.Resource:
                    ## 获取资源类型
                    from derisk.agent.resource import get_resource_manager

                    resources = get_resource_manager().get_supported_resources_type()

                    from derisk.agent.resource.base import FILE_RESOURCES

                    resources.extend(FILE_RESOURCES)
                    results.append(
                        ChatInParamDefine(
                            param_type=AppParamType.Resource.value,
                            param_description="资源选项",
                            sub_types=resources,
                            param_default_value=None,
                            param_render_type=ChatInParamType.SELECT.value,
                        )
                    )
                case AppParamType.Model:
                    results.append(
                        ChatInParamDefine(
                            param_type=AppParamType.Model.value,
                            param_description="模型选项",
                            sub_types=None,
                            param_default_value="index(0)",
                            param_render_type=ChatInParamType.SELECT.value,
                        )
                    )
                case AppParamType.Temperature:
                    results.append(
                        ChatInParamDefine(
                            param_type=AppParamType.Temperature.value,
                            param_description="Temperature设置",
                            sub_types=None,
                            param_default_value="0.6",
                            param_render_type=ChatInParamType.FLOAT.value,
                        )
                    )
                case AppParamType.MaxNewTokens:
                    results.append(
                        ChatInParamDefine(
                            param_type=AppParamType.MaxNewTokens.value,
                            param_description="Token设置",
                            sub_types=None,
                            param_default_value="16000",
                            param_render_type=ChatInParamType.INT.value,
                        )
                    )
                case _:
                    continue
        return results

    def resource_to_options(self, resource_type: str, resources: dict):
        resources_params: List[ParameterDescription] = resources.get(resource_type)
        if resources_params:
            from derisk.agent import ResourceType

            if (
                ResourceType.KnowledgePack.value == resource_type
                or ResourceType.Knowledge.value == resource_type
            ):
                valid_values = None
                for item in resources_params:
                    if item.param_name == "knowledge":
                        valid_values = item.valid_values
                    if item.param_name == "knowledges":
                        valid_values = item.valid_values
                    if valid_values and len(valid_values) > 0:
                        break
                return valid_values
            elif ResourceType.DB.value == resource_type:
                for item in resources_params:
                    if item.param_name == "db_name":
                        return item.valid_values

            else:
                valid_values = []
                for item in resources_params:
                    if item.valid_values and item.required:
                        valid_values = item.valid_values
                return valid_values
        else:
            return []

    async def render_chat_in_params(
        self,
        params: List[ChatInParam],
        query: Optional[str] = None,
        name: Optional[str] = None,
        user_code: Optional[str] = None,
        sys_code: Optional[str] = None,
    ) -> List[ChatInParam]:
        logger.info(f"render_chat_in_params:{params}")
        results = []
        for item in params:
            match AppParamType(item.param_type):
                case AppParamType.Resource:
                    ## 获取资源类型
                    from derisk.agent.resource import get_resource_manager

                    resources = await blocking_func_to_async(
                        CFG.SYSTEM_APP,
                        get_resource_manager().get_supported_resources,
                        version="v2",
                        type=item.sub_type,
                        query=query,
                        name=name,
                        user_code=user_code,
                        sys_code=sys_code,
                    )

                    vaild_options = self.resource_to_options(item.sub_type, resources)
                    from derisk.agent.resource.base import FILE_RESOURCES

                    if item.sub_type in FILE_RESOURCES:
                        item.param_render_type = ChatInParamType.FILE_UPLOAD.value
                    elif len(vaild_options) <= 0:
                        item.param_render_type = ChatInParamType.STRING.value
                    else:
                        if item.param_default_value == "":
                            if vaild_options:
                                item.param_default_value = vaild_options[0]
                    item.param_type_options = vaild_options

                    ## 添加文件资源类型

                case AppParamType.Model:
                    types = set()
                    from derisk.model.cluster import BaseModelController

                    controller = CFG.SYSTEM_APP.get_component(
                        ComponentType.MODEL_CONTROLLER, BaseModelController
                    )
                    models = await controller.get_all_instances(healthy_only=True)
                    model_select_list = []
                    for model in models:
                        worker_name, worker_type = model.model_name.split("@")
                        if worker_type == "llm" and worker_name not in [
                            "codegpt_proxyllm",
                            "text2sql_proxyllm",
                        ]:
                            types.add(worker_name)
                            model_select_list.append(
                                {
                                    "label": f"{worker_name}[{worker_type}]",
                                    "key": worker_name,
                                    "value": worker_name,
                                }
                            )
                    item.param_type_options = model_select_list
                    if item.param_default_value == "index(1)":
                        item.param_default_value = model_select_list[1]
                case _:
                    pass
            results.append(item)
        return results

    def temp_to_formal(self, temp_version: str) -> str:
        if not temp_version.endswith(TEMP_VERSION_SUFFIX):
            return temp_version
            # raise ValueError(f"正式版本[{temp_version}]无法进行版本信息转换!")
        return temp_version.removesuffix(TEMP_VERSION_SUFFIX)

    def get_app_config(
        self, app_code: str, page: int, page_size: int
    ) -> PaginationResult[ServerResponse]:
        query_request = ServeRequest(app_code=app_code, is_published=None)
        return self.dao.get_list_page(
            query_request, page, page_size, ServeEntity.id.name
        )

    def get_by_code(self, code: str) -> Optional[ServerResponse]:
        return self.dao.get_one({"code": code})

    def get_app_temp_code(self, app_code: str) -> Optional[ServerResponse]:
        return self.dao.get_one({"app_code": app_code, "is_published": False})

    async def get(self, request: ServeRequest) -> Optional[ServerResponse]:
        """Get a Building/config entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        # Build the query request from the request
        query_request = request
        return self.dao.get_one(query_request)

    def delete(self, request: ServeRequest) -> None:
        """Delete a Building/config entity

        Args:
            request (ServeRequest): The request
        """

        # Build the query request from the request
        query_request = {
            "id": request.id,
            "code": request.code,
        }
        self.dao.delete(query_request)

    def get_list(self, request: ServeRequest) -> List[ServerResponse]:
        """Get a list of Building/config entities

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
        """Get a list of Building/config entities by page

        Args:
            request (ServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[ServerResponse]: The response
        """
        query_request = request
        return self.dao.get_list_page(query_request, page, page_size)

    def get_vis_modes(self):
        vis_manager = get_vis_manager()
        return vis_manager.list_all_web_use()

    async def get_agent_variables(self, agent_role: str):
        agent_manage = get_agent_manager()
        agent_inst = agent_manage.get(agent_role)
        if agent_inst:
            return await agent_inst.get_all_variables()
        return []

    async def variables_render(
        self, agent_role: str, params: List[DynamicParam]
    ) -> Optional[Dict[str, DynamicParamView]]:
        logger.info(f"variables_render:{agent_role},{params}")
        agent_manage = get_agent_manager()
        agent_inst = agent_manage.get(agent_role)
        if agent_inst:
            return await agent_inst.variables_view(params)
        return {}
