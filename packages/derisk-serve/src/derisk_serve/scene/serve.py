"""
场景管理 Serve 模块

提供场景定义的 CRUD 操作和场景管理功能
"""

import logging
from typing import List, Optional, Union

from derisk.component import SystemApp
from derisk.storage.metadata import DatabaseManager
from derisk_serve.core import BaseServe, BaseServeConfig

from .api import router

logger = logging.getLogger(__name__)

# Serve 配置
SERVE_APP_NAME = "derisk_serve_scene"
SERVE_APP_NAME_HUMP = "SceneServe"


class ServeConfig(BaseServeConfig):
    """场景服务配置"""

    __type__ = SERVE_APP_NAME


class Serve(BaseServe):
    """场景管理 Serve 组件

    提供场景的创建、读取、更新、删除等管理功能
    """

    name = SERVE_APP_NAME

    def __init__(
        self,
        system_app: SystemApp,
        config: Optional[ServeConfig] = None,
        api_prefix: Optional[str] = None,  # api.py 中已经定义了 prefix="/api/scenes"
        api_tags: Optional[List[str]] = None,
        db_url_or_db: Union[str, DatabaseManager] = None,
        try_create_tables: Optional[bool] = False,
    ):
        if api_tags is None:
            api_tags = ["scenes"]
        # 注意：api.py 中的 router 已经设置了 prefix="/api/scenes"
        # 所以这里不需要再设置 api_prefix
        super().__init__(
            system_app, api_prefix or "", api_tags, db_url_or_db, try_create_tables
        )
        self._config = config

    def init_app(self, system_app: SystemApp):
        """初始化应用，注册路由"""
        if self._app_has_initiated:
            return
        self._system_app = system_app
        # 直接注册 router，它已经包含了 prefix="/api/scenes"
        self._system_app.app.include_router(router, tags=self._api_tags)
        self._app_has_initiated = True

    def on_init(self):
        """应用初始化前的回调"""
        pass

    def before_start(self):
        """应用启动前的回调"""
        pass


__all__ = ["Serve", "SERVE_APP_NAME", "SERVE_APP_NAME_HUMP"]
