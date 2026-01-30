import json
import logging
from typing import List, Optional, Type, Any, Dict, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from derisk.component import SystemApp
from derisk.storage.metadata import BaseDao
from derisk.util.pagination_utils import PaginationResult
from derisk_serve.core import BaseService
from .base_upload import initialize_config_update, get_config_update_manager, BaseConfigUpdater
from ..api.schemas import ServeRequest, ServerResponse
from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..models.models import ServeDao, ServeEntity

logger = logging.getLogger(__name__)


class Service(BaseService[ServeEntity, ServeRequest, ServerResponse]):
    """The service class for Config"""

    name = SERVE_SERVICE_COMPONENT_NAME

    def __init__(
        self, system_app: SystemApp, config: ServeConfig, dao: Optional[ServeDao] = None
    ):
        self._system_app = None
        self._serve_config: ServeConfig = config
        self._dao: ServeDao = dao
        super().__init__(system_app)
        # 使用异步调度器
        self.scheduler = AsyncIOScheduler()

        # 初始化配置自动更新器管理
        initialize_config_update(system_app)

        # 服务配置
        self.updater_config_map = {s.get_type_value(): s for s in config.updaters}

    def init_app(self, system_app: SystemApp) -> None:
        """Initialize the service

        Args:
            system_app (SystemApp): The system app
        """
        super().init_app(system_app)
        self._dao = self._dao or ServeDao(self._serve_config)
        self._system_app = system_app

    def after_start(self):
        """Execute after the application starts"""

        self.scheduler.add_job(
            self.config_auto_update,
            'interval',
            seconds=self._serve_config.config_update_interval
        )

        # 启动调度器
        self.scheduler.start()

    async def _update_config(self, config_res: ServerResponse, operator: Optional[str] = None):
        try:
            updater_manager = get_config_update_manager(self.system_app)

            updater_cls: Type[BaseConfigUpdater] = updater_manager.get_updater(config_res.upload_cls)
            if updater_cls:
                config = self.updater_config_map.get(updater_cls.config_type())
                updater_inst = updater_cls(system_app=self.system_app, config=config)
                param = {}
                if config_res.upload_param:
                    try:
                        param = json.loads(config_res.upload_param)
                    except Exception as e:
                        logger.warning(f"配置{config_res.name}的更新参数加载异常！{config_res.upload_param}")
                value = await updater_inst.get_value(**param)
                if value:
                    logger.info(f"配置{config_res.name}更新成功！")
                    self._dao.complete_config_update(config_res, value, operator)
                else:
                    logger.info(f"配置{config_res.name}更新失败！")
            else:
                logger.error(f"没有找到当前配置{config_res.name}的更新服务！{config_res.upload_cls}")
        finally:
            self._dao.fail_config_update(config_res)

    async def force_update(self, key: str, operator: str):
        logger.info(f"force update config,key={key},operator={operator}")
        query_request = {
            "name": key,
        }
        config_res = await self.a_get(query_request)
        if config_res:
            if self._dao.try_acquire_config(config_res, force=True):
                await self._update_config(config_res, operator)

    async def config_auto_update(self):
        config_res = self._dao.acquire_config()
        if config_res:
            await self._update_config(config_res)

    @property
    def dao(self) -> BaseDao[ServeEntity, ServeRequest, ServerResponse]:
        """Returns the internal DAO."""
        return self._dao

    @property
    def config(self) -> ServeConfig:
        """Returns the internal ServeConfig."""
        return self._serve_config

    def update(self, request: ServeRequest) -> ServerResponse:
        """Update a Config entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        # Build the query request from the request
        query_request = {
            "id": request.id
        }
        return self.dao.update(query_request, update_request=request)

    def get(self, request: ServeRequest) -> Optional[ServerResponse]:
        """Get a Config entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = request
        return self.dao.get_one(query_request)

    async def a_get(self, request: Union[Dict[str, Any], ServeRequest]) -> Optional[ServerResponse]:
        """Get a Config entity

        Args:
            request (ServeRequest): The request

        Returns:
            ServerResponse: The response
        """
        return await self.dao.a_get_one(request)

    def delete(self, request: ServeRequest) -> None:
        """Delete a Config entity

        Args:
            request (ServeRequest): The request
        """

        # TODO: implement your own logic here
        # Build the query request from the request
        query_request = {
            "id": request.id
        }
        self.dao.delete(query_request)

    def get_list(self, request: ServeRequest) -> List[ServerResponse]:
        """Get a list of Config entities

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
        """Get a list of Config entities by page

        Args:
            request (ServeRequest): The request
            page (int): The page number
            page_size (int): The page size

        Returns:
            List[ServerResponse]: The response
        """
        query_request = request
        return self.dao.get_list_page(query_request, page, page_size)

    def get_by_category(self, category: str) -> Optional[List[ServerResponse]]:
        """获取指定分类的配置列表

        Args:
            category: The category

        Returns:
            List[ServerResponse]: The response
        """
        query_request = {
            "category": category,
        }
        return self.dao.get_list(query_request)

    def get_by_key(self, key_name: str) -> Optional[str]:
        """获取指定名称的配置值信息
        Args:
            key_name: The key

        Returns:
            Optional[str]: The response
        """
        query_request = {
            "name": key_name,
        }
        resp = self.dao.get_one(query_request)
        return resp.value if resp else None


async def a_get_config_by_key(key_name: str) -> Optional[str]:
    """获取指定名称的配置值信息
    Args:
        key_name: The key

    Returns:
        Optional[str]: The response
    """
    from derisk._private.config import Config
    service = Service.get_instance(Config().SYSTEM_APP)
    resp = await service.a_get({"name": key_name, })
    return resp.value if resp else None

def get_config_by_key(key_name: str) -> Optional[str]:
    """获取指定名称的配置值信息
    Args:
        key_name: The key

    Returns:
        Optional[str]: The response
    """
    from derisk._private.config import Config
    service = Service.get_instance(Config().SYSTEM_APP)
    return service.get_by_key(key_name)
