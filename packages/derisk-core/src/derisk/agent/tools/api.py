"""
ToolAPI - 工具API接口

提供前端调用的API接口：
- 工具列表查询
- 工具详情获取
- 工具与应用关联
- 工具配置管理
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query, Depends
import logging

from .resource_manager import (
    ToolResourceManager,
    ToolResource,
    ToolCategoryGroup,
    ToolVisibility,
    ToolStatus,
    tool_resource_manager
)
from .base import ToolCategory, ToolSource, ToolRiskLevel

logger = logging.getLogger(__name__)

# 创建FastAPI路由
tool_router = APIRouter(prefix="/tools", tags=["Tools"])


# === 请求/响应模型 ===

class ToolListRequest(BaseModel):
    """工具列表请求"""
    category: Optional[str] = Field(None, description="分类过滤")
    source: Optional[str] = Field(None, description="来源过滤")
    risk_level: Optional[str] = Field(None, description="风险等级过滤")
    query: Optional[str] = Field(None, description="搜索关键词")
    tags: Optional[List[str]] = Field(None, description="标签过滤")
    visibility: Optional[List[str]] = Field(None, description="可见性过滤")
    status: Optional[List[str]] = Field(None, description="状态过滤")


class ToolAssociateRequest(BaseModel):
    """工具关联请求"""
    tool_id: str = Field(..., description="工具ID")
    app_id: str = Field(..., description="应用ID")


class ToolUpdateRequest(BaseModel):
    """工具更新请求"""
    tool_id: str = Field(..., description="工具ID")
    status: Optional[str] = Field(None, description="状态")
    visibility: Optional[str] = Field(None, description="可见性")
    owner: Optional[str] = Field(None, description="所有者")


class ToolResponse(BaseModel):
    """工具响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field("", description="消息")
    data: Optional[Any] = Field(None, description="数据")


class ToolListResponse(BaseModel):
    """工具列表响应"""
    success: bool = Field(True)
    total: int = Field(0, description="总数")
    categories: List[ToolCategoryGroup] = Field(default_factory=list, description="分类工具列表")


# === API端点 ===

@tool_router.get("/categories", response_model=ToolListResponse)
async def get_tools_by_category(
    include_empty: bool = Query(False, description="是否包含空分类"),
    visibility: Optional[str] = Query(None, description="可见性过滤"),
    status: Optional[str] = Query(None, description="状态过滤")
):
    """
    按分类获取工具列表
    
    用于前端工具选择组件的分类展示
    """
    manager = tool_resource_manager
    
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
    
    return ToolListResponse(
        success=True,
        total=total,
        categories=groups
    )


@tool_router.get("/list", response_model=ToolResponse)
async def list_all_tools(
    category: Optional[str] = Query(None, description="分类过滤"),
    source: Optional[str] = Query(None, description="来源过滤"),
    query: Optional[str] = Query(None, description="搜索关键词")
):
    """
    获取工具列表（扁平结构）
    """
    manager = tool_resource_manager
    
    if query:
        tools = manager.search_tools(query, category=category)
    elif source:
        source_enum = ToolSource(source)
        tools = manager.get_tools_by_source(source_enum)
    elif category:
        all_tools = manager.list_all_tools()
        tools = [t for t in all_tools if t.category == category]
    else:
        tools = manager.list_all_tools()
    
    return ToolResponse(
        success=True,
        data=[t.to_dict() for t in tools]
    )


@tool_router.get("/search", response_model=ToolResponse)
async def search_tools(
    q: str = Query(..., description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类过滤"),
    tags: Optional[str] = Query(None, description="标签过滤(逗号分隔)")
):
    """
    搜索工具
    
    在工具名称、描述中搜索匹配的工具
    """
    manager = tool_resource_manager
    
    tag_list = tags.split(",") if tags else None
    
    tools = manager.search_tools(q, category=category, tags=tag_list)
    
    return ToolResponse(
        success=True,
        data=[t.to_dict() for t in tools]
    )


@tool_router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool_detail(tool_id: str):
    """
    获取工具详情
    
    返回工具的完整信息，包括输入输出Schema
    """
    manager = tool_resource_manager
    
    tool = manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_id}")
    
    return ToolResponse(
        success=True,
        data=tool.to_dict()
    )


@tool_router.post("/associate", response_model=ToolResponse)
async def associate_tool_to_app(request: ToolAssociateRequest):
    """
    关联工具到应用
    
    将工具与应用建立关联关系，供应用编辑模块使用
    """
    manager = tool_resource_manager
    
    success = manager.associate_tool_to_app(request.tool_id, request.app_id)
    
    return ToolResponse(
        success=success,
        message="关联成功" if success else "关联失败",
        data={"tool_id": request.tool_id, "app_id": request.app_id}
    )


@tool_router.delete("/associate", response_model=ToolResponse)
async def dissociate_tool_from_app(request: ToolAssociateRequest):
    """
    解除工具与应用的关联
    """
    manager = tool_resource_manager
    
    success = manager.dissociate_tool_from_app(request.tool_id, request.app_id)
    
    return ToolResponse(
        success=success,
        message="解除关联成功" if success else "解除关联失败"
    )


@tool_router.get("/app/{app_id}", response_model=ToolResponse)
async def get_app_tools(app_id: str):
    """
    获取应用关联的工具列表
    
    用于应用编辑模块展示已关联的工具
    """
    manager = tool_resource_manager
    
    tools = manager.get_app_tools(app_id)
    
    return ToolResponse(
        success=True,
        data=[t.to_dict() for t in tools]
    )


@tool_router.put("/update", response_model=ToolResponse)
async def update_tool(request: ToolUpdateRequest):
    """
    更新工具配置
    
    更新工具的状态、可见性或所有者
    """
    manager = tool_resource_manager
    
    if request.status:
        manager.update_tool_status(request.tool_id, ToolStatus(request.status))
    
    if request.visibility:
        manager.update_tool_visibility(request.tool_id, ToolVisibility(request.visibility))
    
    if request.owner:
        manager.set_tool_owner(request.tool_id, request.owner)
    
    return ToolResponse(
        success=True,
        message="更新成功"
    )


@tool_router.get("/schema/{tool_id}", response_model=ToolResponse)
async def get_tool_schema(tool_id: str):
    """
    获取工具的输入输出Schema
    
    用于前端动态生成工具参数表单
    """
    manager = tool_resource_manager
    
    tool = manager.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_id}")
    
    return ToolResponse(
        success=True,
        data={
            "tool_id": tool_id,
            "name": tool.name,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "examples": tool.examples
        }
    )


# === 兼容旧API ===

@tool_router.get("/list/local", response_model=ToolResponse)
async def list_local_tools():
    """列出本地工具（兼容旧API）"""
    manager = tool_resource_manager
    tools = manager.get_tools_by_source(ToolSource.USER)
    return ToolResponse(
        success=True,
        data=[t.to_dict() for t in tools]
    )


@tool_router.get("/list/builtin", response_model=ToolResponse)
async def list_builtin_tools():
    """列出内置工具（兼容旧API）"""
    manager = tool_resource_manager
    tools = manager.get_tools_by_source(ToolSource.CORE)
    return ToolResponse(
        success=True,
        data=[t.to_dict() for t in tools]
    )


# === 工具信息概览 ===

@tool_router.get("/overview", response_model=ToolResponse)
async def get_tool_overview():
    """
    获取工具概览
    
    用于前端工具管理首页展示统计数据
    """
    manager = tool_resource_manager
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
    
    return ToolResponse(
        success=True,
        data={
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
                for cat in ToolCategory
            ]
        }
    )


def get_tool_router() -> APIRouter:
    """获取工具API路由"""
    return tool_router