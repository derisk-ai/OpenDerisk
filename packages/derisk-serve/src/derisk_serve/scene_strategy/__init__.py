# Scene Strategy Module
"""
场景策略模块 - 支持应用构建时关联场景策略

模块结构：
- models: 数据库模型
- api: API接口和Schema
- service: 业务服务层

使用方式：
    # 在应用构建时关联场景
    app = GptsApp(
        app_code="my_app",
        scene_strategy=SceneStrategyRef(
            scene_code="coding",
            is_primary=True
        )
    )
    
    # 通过API管理场景策略
    POST /api/v1/scene-strategy/scenes - 创建场景
    GET /api/v1/scene-strategy/scenes - 列出场景
    PUT /api/v1/scene-strategy/scenes/{code} - 更新场景
    POST /api/v1/scene-strategy/apps/bindings - 绑定到应用
"""

from derisk_serve.scene_strategy.models.models import (
    SceneStrategyEntity,
    SceneStrategyDao,
    AppSceneBindingEntity,
    AppSceneBindingDao,
)
from derisk_serve.scene_strategy.service.service import SceneStrategyService
from derisk_serve.scene_strategy.api.endpoints import router, register_router
from derisk_serve.scene_strategy.api.schemas import (
    SceneStrategyCreateRequest,
    SceneStrategyResponse,
    AppSceneBindingRequest,
    AppSceneBindingResponse,
)

__all__ = [
    "SceneStrategyEntity",
    "SceneStrategyDao",
    "AppSceneBindingEntity",
    "AppSceneBindingDao",
    "SceneStrategyService",
    "router",
    "register_router",
    "SceneStrategyCreateRequest",
    "SceneStrategyResponse",
    "AppSceneBindingRequest",
    "AppSceneBindingResponse",
]