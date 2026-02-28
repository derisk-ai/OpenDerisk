"""
Scene Strategy API Endpoints

场景策略管理API接口
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from derisk.component import SystemApp
from derisk_serve.core import Result, blocking_func_to_async
from derisk_serve.scene_strategy.api.schemas import (
    SceneStrategyCreateRequest,
    SceneStrategyUpdateRequest,
    SceneStrategyResponse,
    SceneStrategyListResponse,
    SceneStrategyBriefResponse,
    AppSceneBindingRequest,
    AppSceneBindingResponse,
    PreviewSystemPromptRequest,
    PreviewSystemPromptResponse,
)
from derisk_serve.scene_strategy.service.service import SceneStrategyService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_service() -> SceneStrategyService:
    """获取服务实例"""
    from derisk._private.config import Config
    return SceneStrategyService.get_instance(Config().SYSTEM_APP)


@router.post("/scenes", response_model=Result[SceneStrategyResponse])
async def create_scene(
    request: SceneStrategyCreateRequest,
    service: SceneStrategyService = Depends(get_service),
):
    """创建场景策略"""
    try:
        result = await service.create_scene(request)
        return Result.succ(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scenes/{scene_code}", response_model=Result[SceneStrategyResponse])
async def get_scene(
    scene_code: str,
    service: SceneStrategyService = Depends(get_service),
):
    """获取场景策略详情"""
    result = await service.get_scene(scene_code)
    if not result:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_code}' not found")
    return Result.succ(result)


@router.get("/scenes", response_model=Result[SceneStrategyListResponse])
async def list_scenes(
    user_code: Optional[str] = Query(None, description="用户编码"),
    sys_code: Optional[str] = Query(None, description="系统编码"),
    scene_type: Optional[str] = Query(None, description="场景类型"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    include_builtin: bool = Query(True, description="是否包含内置场景"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    service: SceneStrategyService = Depends(get_service),
):
    """列出场景策略"""
    result = await service.list_scenes(
        user_code=user_code,
        sys_code=sys_code,
        scene_type=scene_type,
        is_active=is_active,
        include_builtin=include_builtin,
        page=page,
        page_size=page_size,
    )
    return Result.succ(result)


@router.put("/scenes/{scene_code}", response_model=Result[SceneStrategyResponse])
async def update_scene(
    scene_code: str,
    request: SceneStrategyUpdateRequest,
    service: SceneStrategyService = Depends(get_service),
):
    """更新场景策略"""
    try:
        result = await service.update_scene(scene_code, request)
        if not result:
            raise HTTPException(status_code=404, detail=f"Scene '{scene_code}' not found")
        return Result.succ(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/scenes/{scene_code}")
async def delete_scene(
    scene_code: str,
    service: SceneStrategyService = Depends(get_service),
):
    """删除场景策略"""
    try:
        success = await service.delete_scene(scene_code)
        if not success:
            raise HTTPException(status_code=404, detail=f"Scene '{scene_code}' not found")
        return Result.succ({"deleted": True})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scenes/brief/list", response_model=Result[list[SceneStrategyBriefResponse]])
async def list_brief_scenes(
    include_builtin: bool = Query(True, description="是否包含内置场景"),
    user_code: Optional[str] = Query(None, description="用户编码"),
    service: SceneStrategyService = Depends(get_service),
):
    """获取场景简要列表（用于选择器）"""
    result = await service.list_brief_scenes(
        include_builtin=include_builtin,
        user_code=user_code,
    )
    return Result.succ(result)


@router.post("/scenes/{scene_code}/clone", response_model=Result[SceneStrategyResponse])
async def clone_scene(
    scene_code: str,
    new_scene_code: str = Query(..., description="新场景编码"),
    new_scene_name: str = Query(..., description="新场景名称"),
    service: SceneStrategyService = Depends(get_service),
):
    """克隆场景"""
    try:
        result = await service.clone_scene(
            scene_code,
            new_scene_code,
            new_scene_name,
        )
        return Result.succ(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scenes/{scene_code}/export")
async def export_scene(
    scene_code: str,
    service: SceneStrategyService = Depends(get_service),
):
    """导出场景配置"""
    try:
        result = await service.export_scene(scene_code)
        return Result.succ(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/scenes/import", response_model=Result[SceneStrategyResponse])
async def import_scene(
    config: dict,
    service: SceneStrategyService = Depends(get_service),
):
    """导入场景配置"""
    try:
        result = await service.import_scene(config)
        return Result.succ(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scenes/preview-prompt", response_model=Result[PreviewSystemPromptResponse])
async def preview_system_prompt(
    request: PreviewSystemPromptRequest,
    service: SceneStrategyService = Depends(get_service),
):
    """预览System Prompt"""
    result = await service.preview_system_prompt(request)
    return Result.succ(result)


@router.post("/apps/bindings", response_model=Result[AppSceneBindingResponse])
async def bind_scene_to_app(
    request: AppSceneBindingRequest,
    service: SceneStrategyService = Depends(get_service),
):
    """将场景绑定到应用"""
    try:
        result = await service.bind_scene_to_app(request)
        return Result.succ(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/apps/{app_code}/bindings/{scene_code}")
async def unbind_scene_from_app(
    app_code: str,
    scene_code: str,
    service: SceneStrategyService = Depends(get_service),
):
    """解除应用场景绑定"""
    success = await service.unbind_scene_from_app(app_code, scene_code)
    return Result.succ({"unbound": success})


@router.get("/apps/{app_code}/scenes", response_model=Result[list[AppSceneBindingResponse]])
async def get_app_scenes(
    app_code: str,
    service: SceneStrategyService = Depends(get_service),
):
    """获取应用绑定的所有场景"""
    result = await service.get_app_scenes(app_code)
    return Result.succ(result)


@router.get("/apps/{app_code}/primary-scene", response_model=Result[SceneStrategyResponse])
async def get_app_primary_scene(
    app_code: str,
    service: SceneStrategyService = Depends(get_service),
):
    """获取应用的主要场景"""
    result = await service.get_app_primary_scene(app_code)
    if not result:
        return Result.succ(None)
    return Result.succ(result)


def register_router(app, prefix: str = "/api/v1/scene-strategy"):
    """注册路由"""
    app.include_router(router, prefix=prefix, tags=["Scene Strategy"])