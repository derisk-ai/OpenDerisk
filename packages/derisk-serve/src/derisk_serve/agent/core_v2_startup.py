"""
服务启动时集成 Core_v2 组件
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from .core_v2_adapter import get_core_v2
from .core_v2_api import router as core_v2_router
from .agent_selection_api import router as agent_selection_router

logger = logging.getLogger(__name__)


def register_core_v2_routes(app: FastAPI):
    """注册 Core_v2 API 路由"""
    app.include_router(core_v2_router)
    app.include_router(agent_selection_router)
    logger.info("[Core_v2] API routes registered at /api/v2")
    logger.info("[Core_v2] Agent selection routes registered at /api/agent")


@asynccontextmanager
async def core_v2_lifespan(app: FastAPI):
    """Core_v2 生命周期管理"""
    core_v2 = get_core_v2()
    logger.info("[Core_v2] Starting...")
    await core_v2.start()
    logger.info("[Core_v2] Started successfully")
    yield
    logger.info("[Core_v2] Stopping...")
    await core_v2.stop()
    logger.info("[Core_v2] Stopped")


def setup_core_v2(app: FastAPI):
    """设置 Core_v2 组件"""
    register_core_v2_routes(app)

    @app.on_event("startup")
    async def startup():
        core_v2 = get_core_v2()
        await core_v2.start()

    @app.on_event("shutdown")
    async def shutdown():
        core_v2 = get_core_v2()
        await core_v2.stop()

    logger.info("[Core_v2] Setup complete")


class CoreV2Startup:
    """Core_v2 启动管理器"""

    def __init__(self, app: Optional[FastAPI] = None):
        self.app = app
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        if self.app:
            register_core_v2_routes(self.app)
        core_v2 = get_core_v2()
        await core_v2.start()
        self._initialized = True

    async def shutdown(self):
        if not self._initialized:
            return
        core_v2 = get_core_v2()
        await core_v2.stop()
        self._initialized = False


_startup: Optional[CoreV2Startup] = None


def get_startup() -> CoreV2Startup:
    global _startup
    if _startup is None:
        _startup = CoreV2Startup()
    return _startup
