"""
工具API服务端点

挂载工具API路由到FastAPI应用，提供前端调用的接口：
- GET /api/tools/categories - 按分类获取工具列表
- GET /api/tools/list - 获取工具列表
- GET /api/tools/search - 搜索工具
- GET /api/tools/{tool_id} - 获取工具详情
- POST /api/tools/associate - 关联工具到应用
- DELETE /api/tools/associate - 解除工具关联
- GET /api/tools/app/{app_id} - 获取应用关联的工具
- GET /api/tools/overview - 获取工具概览
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# 创建路由
tools_router = APIRouter(prefix="/api/tools", tags=["Tools"])


def get_tool_resource_manager():
    """获取工具资源管理器"""
    from derisk.agent.tools import tool_resource_manager
    return tool_resource_manager


def get_tool_registry():
    """获取工具注册表"""
    from derisk.agent.tools import tool_registry
    return tool_registry


@tools_router.get("/categories")
async def get_tools_by_category(
    include_empty: bool = Query(False, description="是否包含空分类"),
    visibility: Optional[str] = Query(None, description="可见性过滤"),
    status: Optional[str] = Query(None, description="状态过滤")
):
    """
    按分类获取工具列表
    
    用于前端工具选择组件的分类展示
    """
    from derisk.agent.tools.resource_manager import ToolVisibility, ToolStatus
    
    manager = get_tool_resource_manager()
    
    visibility_filter = None
    if visibility:
        visibility_filter = [ToolVisibility(v) for v in visibility.split(",")]
    
    status_filter = None
    if status:
        status_filter = [ToolStatus(s) for s in status.split(",")]
    
    groups = manager.get_tools_by_category(
        include_empty=include_empty,
        visibility_filter=visibility_filter,
        status_filter=status_filter
    )
    
    total = sum(g.count for g in groups)
    
    return {
        "success": True,
        "total": total,
        "categories": [
            {
                "category": g.category,
                "display_name": g.display_name,
                "description": g.description,
                "icon": g.icon,
                "tools": [t.to_dict() for t in g.tools],
                "count": g.count
            }
            for g in groups
        ]
    }


@tools_router.get("/list")
async def list_all_tools(
    category: Optional[str] = Query(None, description="分类过滤"),
    source: Optional[str] = Query(None, description="来源过滤"),
    query: Optional[str] = Query(None, description="搜索关键词")
):
    """获取工具列表（扁平结构）"""
    manager = get_tool_resource_manager()
    
    if query:
        tools = manager.search_tools(query, category=category)
    elif source:
        from derisk.agent.tools.base import ToolSource
        source_enum = ToolSource(source)
        tools = manager.get_tools_by_source(source_enum)
    elif category:
        all_tools = manager.list_all_tools()
        tools = [t for t in all_tools if t.category == category]
    else:
        tools = manager.list_all_tools()
    
    return {
        "success": True,
        "data": [t.to_dict() for t in tools]
    }


@tools_router.get("/search")
async def search_tools(
    q: str = Query(..., description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类过滤"),
    tags: Optional[str] = Query(None, description="标签过滤(逗号分隔)")
):
    """搜索工具"""
    manager = get_tool_resource_manager()
    
    tag_list = tags.split(",") if tags else None
    
    tools = manager.search_tools(q, category=category, tags=tag_list)
    
    return {
        "success": True,
        "data": [t.to_dict() for t in tools]
    }


@tools_router.get("/{tool_id}")
async def get_tool_detail(tool_id: str):
    """获取工具详情"""
    manager = get_tool_resource_manager()
    
    tool = manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_id}")
    
    return {
        "success": True,
        "data": tool.to_dict()
    }


@tools_router.post("/associate")
async def associate_tool_to_app(request: dict):
    """
    关联工具到应用
    
    请求体:
    {
        "tool_id": "xxx",
        "app_id": "xxx"
    }
    """
    manager = get_tool_resource_manager()
    
    tool_id = request.get("tool_id")
    app_id = request.get("app_id")
    
    if not tool_id or not app_id:
        raise HTTPException(status_code=400, detail="tool_id和app_id都是必需的")
    
    success = manager.associate_tool_to_app(tool_id, app_id)
    
    return {
        "success": success,
        "message": "关联成功" if success else "关联失败",
        "data": {"tool_id": tool_id, "app_id": app_id}
    }


@tools_router.delete("/associate")
async def dissociate_tool_from_app(request: dict):
    """解除工具与应用的关联"""
    manager = get_tool_resource_manager()
    
    tool_id = request.get("tool_id")
    app_id = request.get("app_id")
    
    if not tool_id or not app_id:
        raise HTTPException(status_code=400, detail="tool_id和app_id都是必需的")
    
    success = manager.dissociate_tool_from_app(tool_id, app_id)
    
    return {
        "success": success,
        "message": "解除关联成功" if success else "解除关联失败"
    }


@tools_router.get("/app/{app_id}")
async def get_app_tools(app_id: str):
    """获取应用关联的工具列表"""
    manager = get_tool_resource_manager()
    
    tools = manager.get_app_tools(app_id)
    
    return {
        "success": True,
        "data": [t.to_dict() for t in tools]
    }


@tools_router.put("/update")
async def update_tool(request: dict):
    """更新工具配置"""
    from derisk.agent.tools.resource_manager import ToolStatus, ToolVisibility
    
    manager = get_tool_resource_manager()
    
    tool_id = request.get("tool_id")
    if not tool_id:
        raise HTTPException(status_code=400, detail="tool_id是必需的")
    
    if request.get("status"):
        manager.update_tool_status(tool_id, ToolStatus(request["status"]))
    
    if request.get("visibility"):
        manager.update_tool_visibility(tool_id, ToolVisibility(request["visibility"]))
    
    if request.get("owner"):
        manager.set_tool_owner(tool_id, request["owner"])
    
    return {
        "success": True,
        "message": "更新成功"
    }


@tools_router.get("/schema/{tool_id}")
async def get_tool_schema(tool_id: str):
    """获取工具的输入输出Schema"""
    manager = get_tool_resource_manager()
    
    tool = manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_id}")
    
    return {
        "success": True,
        "data": {
            "tool_id": tool_id,
            "name": tool.name,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "examples": tool.examples
        }
    }


@tools_router.get("/list/local")
async def list_local_tools():
    """列出本地工具（兼容旧API）"""
    from derisk.agent.tools.base import ToolSource
    manager = get_tool_resource_manager()
    tools = manager.get_tools_by_source(ToolSource.USER)
    return {
        "success": True,
        "data": [t.to_dict() for t in tools]
    }


@tools_router.get("/list/builtin")
async def list_builtin_tools():
    """列出内置工具（兼容旧API）"""
    from derisk.agent.tools.base import ToolSource
    manager = get_tool_resource_manager()
    tools = manager.get_tools_by_source(ToolSource.CORE)
    return {
        "success": True,
        "data": [t.to_dict() for t in tools]
    }


@tools_router.get("/overview")
async def get_tool_overview():
    """获取工具概览"""
    manager = get_tool_resource_manager()
    tools = manager.list_all_tools()
    
    # 按分类统计
    category_stats: Dict[str, int] = {}
    for tool in tools:
        cat = tool.category
        category_stats[cat] = category_stats.get(cat, 0) + 1
    
    # 按来源统计
    source_stats: Dict[str, int] = {}
    for tool in tools:
        src = tool.source
        source_stats[src] = source_stats.get(src, 0) + 1
    
    # 按风险等级统计
    risk_stats: Dict[str, int] = {}
    for tool in tools:
        risk = tool.risk_level
        risk_stats[risk] = risk_stats.get(risk, 0) + 1
    
    return {
        "success": True,
        "data": {
            "total": len(tools),
            "by_category": category_stats,
            "by_source": source_stats,
            "by_risk_level": risk_stats,
            "categories": [
                {
                    "name": cat.value if hasattr(cat, 'value') else str(cat),
                    "display_name": manager.CATEGORY_DISPLAY_NAMES.get(cat, ("", ""))[0],
                    "count": category_stats.get(cat.value if hasattr(cat, 'value') else str(cat), 0)
                }
                for cat in get_tool_registry().list_all()[0].metadata.category.__class__ if hasattr(cat, 'value')
            ] if tools else []
        }
    }


def setup_tool_api(app):
    """
    将工具API路由挂载到FastAPI应用
    
    Args:
        app: FastAPI应用实例
    
    使用方式:
        from derisk.agent.tools.api_server import setup_tool_api
        setup_tool_api(app)
    """
    app.include_router(tools_router)
    logger.info("[ToolAPI] 工具API路由已挂载到 /api/tools")


def init_tool_system():
    """
    初始化工具系统
    
    包括：
    1. 注册内置工具
    2. 迁移LocalTool
    3. 同步工具资源
    """
    from derisk.agent.tools import (
        register_builtin_tools,
        tool_registry,
        tool_resource_manager,
        migrate_local_tools,
    )
    
    # 1. 注册内置工具
    register_builtin_tools()
    logger.info(f"[ToolSystem] 已注册 {len(tool_registry)} 个内置工具")
    
    # 2. 尝试迁移LocalTool
    try:
        count = migrate_local_tools()
        logger.info(f"[ToolSystem] 已迁移 {count} 个LocalTool")
    except Exception as e:
        logger.warning(f"[ToolSystem] LocalTool迁移失败: {e}")
    
    # 3. 同步工具资源
    tool_resource_manager.sync_from_registry()
    logger.info(f"[ToolSystem] 工具资源管理器已同步")
    
    return tool_registry, tool_resource_manager