"""
Tool Management API - 工具管理API

提供工具分组管理和Agent工具绑定配置的API端点
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from derisk.agent.tools.tool_manager import (
    tool_manager,
    ToolBindingType,
    ToolBindingConfig,
    AgentToolConfiguration,
)
from derisk.agent.tools.registry import tool_registry, register_builtin_tools

router = APIRouter(prefix="/tools", tags=["Tool Management"])


# ========== 全局初始化 ==========


def ensure_tools_initialized():
    """确保工具已初始化"""
    if not hasattr(tool_registry, "_initialized") or not tool_registry._initialized:
        register_builtin_tools()


# ========== 请求/响应模型 ==========


class ToolBindingUpdateRequest(BaseModel):
    """工具绑定更新请求"""

    app_id: str = Field(..., description="应用ID")
    agent_name: str = Field(..., description="Agent名称")
    tool_id: str = Field(..., description="工具ID")
    is_bound: bool = Field(..., description="是否绑定")
    disabled_at_runtime: Optional[bool] = Field(None, description="运行时是否禁用")


class BatchToolBindingUpdateRequest(BaseModel):
    """批量工具绑定更新请求"""

    app_id: str = Field(..., description="应用ID")
    agent_name: str = Field(..., description="Agent名称")
    bindings: List[Dict[str, Any]] = Field(..., description="绑定配置列表")


class AgentToolConfigResponse(BaseModel):
    """Agent工具配置响应"""

    app_id: str
    agent_name: str
    enabled_tools: List[str]
    bindings: Dict[str, Any]


class RuntimeToolsRequest(BaseModel):
    """运行时工具请求"""

    app_id: str = Field(..., description="应用ID")
    agent_name: str = Field(..., description="Agent名称")
    format_type: str = Field("openai", description="格式类型(openai/anthropic)")


# ========== API 端点 ==========


@router.get("/groups")
async def get_tool_groups(
    app_id: Optional[str] = Query(None, description="应用ID"),
    agent_name: Optional[str] = Query(None, description="Agent名称"),
    lang: str = Query("zh", description="语言(zh/en)"),
):
    """
    获取工具分组列表

    返回按分组类型组织的工具列表，包括绑定状态信息
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        groups = tool_manager.get_tool_groups(
            app_id=app_id, agent_name=agent_name, lang=lang
        )

        return JSONResponse(
            content={"success": True, "data": [group.model_dump() for group in groups]}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent-config")
async def get_agent_tool_config(
    app_id: str = Query(..., description="应用ID"),
    agent_name: str = Query(..., description="Agent名称"),
):
    """
    获取 Agent 的工具配置

    返回指定 Agent 的完整工具绑定配置
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        config = tool_manager.get_agent_config(app_id, agent_name)
        if not config:
            return JSONResponse(
                content={"success": False, "message": "Configuration not found"}
            )

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "app_id": config.app_id,
                    "agent_name": config.agent_name,
                    "bindings": {k: v.model_dump() for k, v in config.bindings.items()},
                    "updated_at": config.updated_at.isoformat()
                    if config.updated_at
                    else None,
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/binding/update")
async def update_tool_binding(request: ToolBindingUpdateRequest):
    """
    更新单个工具绑定状态

    用于绑定或解绑工具
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        success = tool_manager.update_tool_binding(
            app_id=request.app_id,
            agent_name=request.agent_name,
            tool_id=request.tool_id,
            is_bound=request.is_bound,
            disabled_at_runtime=request.disabled_at_runtime,
        )

        if success:
            return JSONResponse(
                content={"success": True, "message": "Binding updated successfully"}
            )
        else:
            return JSONResponse(
                content={"success": False, "message": "Failed to update binding"},
                status_code=400,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/binding/batch-update")
async def batch_update_tool_bindings(request: BatchToolBindingUpdateRequest):
    """
    批量更新工具绑定状态

    用于一次性更新多个工具的绑定状态
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        results = []
        for binding in request.bindings:
            success = tool_manager.update_tool_binding(
                app_id=request.app_id,
                agent_name=request.agent_name,
                tool_id=binding["tool_id"],
                is_bound=binding.get("is_bound", True),
                disabled_at_runtime=binding.get("disabled_at_runtime"),
            )
            results.append({"tool_id": binding["tool_id"], "success": success})

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "results": results,
                    "total": len(results),
                    "success_count": sum(1 for r in results if r["success"]),
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runtime-tools")
async def get_runtime_tools(request: RuntimeToolsRequest):
    """
    获取运行时工具列表

    返回 Agent 实际可用的工具列表（已排除被禁用的工具）
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        tools = tool_manager.get_runtime_tools(
            app_id=request.app_id, agent_name=request.agent_name
        )

        tool_list = []
        for tool in tools:
            metadata = tool.metadata
            tool_list.append(
                {
                    "tool_id": metadata.name,
                    "name": metadata.name,
                    "display_name": metadata.display_name or metadata.name,
                    "description": metadata.description,
                    "category": metadata.category.value if metadata.category else None,
                    "source": metadata.source.value if metadata.source else None,
                    "risk_level": metadata.risk_level.value
                    if metadata.risk_level
                    else "low",
                }
            )

        return JSONResponse(
            content={
                "success": True,
                "data": {"tools": tool_list, "count": len(tool_list)},
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runtime-schemas")
async def get_runtime_tool_schemas(request: RuntimeToolsRequest):
    """
    获取运行时工具 Schema 列表

    返回用于 LLM 工具调用的 Schema 列表
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        schemas = tool_manager.get_runtime_tool_schemas(
            app_id=request.app_id,
            agent_name=request.agent_name,
            format_type=request.format_type,
        )

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "schemas": schemas,
                    "count": len(schemas),
                    "format": request.format_type,
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_all_tools(
    category: Optional[str] = Query(None, description="类别过滤"),
    source: Optional[str] = Query(None, description="来源过滤"),
    query: Optional[str] = Query(None, description="搜索关键词"),
):
    """
    列出所有工具（扁平结构）

    支持按类别、来源过滤和搜索
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        tools = tool_registry.list_all()
        result = []

        for tool in tools:
            metadata = tool.metadata

            # 类别过滤
            if category and metadata.category and metadata.category.value != category:
                continue

            # 来源过滤
            if source and metadata.source and metadata.source.value != source:
                continue

            # 搜索过滤
            if query:
                query_lower = query.lower()
                if (
                    query_lower not in metadata.name.lower()
                    and query_lower not in metadata.description.lower()
                ):
                    continue

            result.append(
                {
                    "tool_id": metadata.name,
                    "name": metadata.name,
                    "display_name": metadata.display_name or metadata.name,
                    "description": metadata.description,
                    "version": metadata.version,
                    "category": metadata.category.value if metadata.category else None,
                    "source": metadata.source.value if metadata.source else None,
                    "tags": metadata.tags,
                    "risk_level": metadata.risk_level.value
                    if metadata.risk_level
                    else "low",
                    "requires_permission": metadata.requires_permission,
                    "timeout": metadata.timeout,
                }
            )

        return JSONResponse(
            content={"success": True, "data": result, "total": len(result)}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tool_id}")
async def get_tool_detail(tool_id: str):
    """
    获取工具详情

    返回指定工具的完整信息
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        tool = tool_registry.get(tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")

        metadata = tool.metadata
        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "tool_id": metadata.name,
                    "name": metadata.name,
                    "display_name": metadata.display_name or metadata.name,
                    "description": metadata.description,
                    "version": metadata.version,
                    "category": metadata.category.value if metadata.category else None,
                    "subcategory": metadata.subcategory,
                    "source": metadata.source.value if metadata.source else None,
                    "tags": metadata.tags,
                    "risk_level": metadata.risk_level.value
                    if metadata.risk_level
                    else "low",
                    "requires_permission": metadata.requires_permission,
                    "required_permissions": metadata.required_permissions,
                    "approval_message": metadata.approval_message,
                    "environment": metadata.environment.value
                    if metadata.environment
                    else None,
                    "timeout": metadata.timeout,
                    "max_retries": metadata.max_retries,
                    "concurrency_limit": metadata.concurrency_limit,
                    "input_schema": metadata.input_schema,
                    "output_schema": metadata.output_schema,
                    "examples": [ex.model_dump() for ex in metadata.examples]
                    if metadata.examples
                    else [],
                    "dependencies": metadata.dependencies,
                    "conflicts": metadata.conflicts,
                    "doc_url": metadata.doc_url,
                    "author": metadata.author,
                    "license": metadata.license,
                    "created_at": metadata.created_at.isoformat()
                    if metadata.created_at
                    else None,
                    "updated_at": metadata.updated_at.isoformat()
                    if metadata.updated_at
                    else None,
                },
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_tool_cache(
    app_id: Optional[str] = None, agent_name: Optional[str] = None
):
    """
    清除工具配置缓存

    用于配置更新后刷新缓存
    """
    try:
        # 确保工具已初始化
        ensure_tools_initialized()

        tool_manager.clear_cache(app_id, agent_name)
        return JSONResponse(
            content={"success": True, "message": "Cache cleared successfully"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
