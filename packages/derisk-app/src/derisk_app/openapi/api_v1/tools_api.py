"""工具执行 API"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import asyncio
import json

from derisk_serve.utils.auth import UserRequest
from derisk_app.feature_plugins.permissions.checker import require_permission

router = APIRouter(prefix="/tools", tags=["Tools"])


# 请求模型
class ToolExecuteRequest(BaseModel):
    tool_name: str
    args: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


class BatchExecuteRequest(BaseModel):
    calls: List[Dict[str, Any]]
    fail_fast: Optional[bool] = False


class PermissionCheckRequest(BaseModel):
    tool_name: str
    args: Optional[Dict[str, Any]] = None


# 全局工具注册表
_tool_registry = None


def get_tool_registry():
    global _tool_registry
    if _tool_registry is None:
        from derisk_core.tools import tool_registry, register_builtin_tools

        register_builtin_tools()
        _tool_registry = tool_registry
    return _tool_registry


@router.get("/list")
async def list_tools(
    user: UserRequest = Depends(require_permission("tool", "read")),
):
    """列出所有可用工具（需要 tool:read 权限）"""
    registry = get_tool_registry()
    tools = []

    for tool in registry.list_all():
        meta = tool.metadata
        tools.append(
            {
                "name": meta.name,
                "description": meta.description,
                "category": meta.category.value
                if hasattr(meta.category, "value")
                else str(meta.category),
                "risk": meta.risk_level.value
                if hasattr(meta.risk_level, "value")
                else str(meta.risk_level),
                "requires_permission": meta.requires_permission,
                "examples": [
                    e.model_dump() if hasattr(e, "model_dump") else e
                    for e in meta.examples
                ],
            }
        )

    return JSONResponse(content={"success": True, "data": tools})


@router.get("/schemas")
async def get_tool_schemas():
    """获取所有工具的 Schema（用于 LLM 工具调用）"""
    registry = get_tool_registry()
    schemas = registry.get_schemas()

    return JSONResponse(content={"success": True, "data": schemas})


@router.get("/{tool_name}/schema")
async def get_tool_schema(tool_name: str):
    """获取单个工具的 Schema"""
    registry = get_tool_registry()
    tool = registry.get(tool_name)

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "name": tool.metadata.name,
                "description": tool.metadata.description,
                "parameters": tool.parameters_schema,
            },
        }
    )


@router.post("/execute")
async def execute_tool(
    request: ToolExecuteRequest,
    user: UserRequest = Depends(require_permission("tool", "execute")),
):
    """执行单个工具（需要 tool:execute 权限）"""
    try:
        registry = get_tool_registry()
        tool = registry.get(request.tool_name)

        if not tool:
            raise HTTPException(
                status_code=404, detail=f"Tool '{request.tool_name}' not found"
            )

        # 验证参数
        errors = tool.validate_args(request.args)
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))

        # 执行工具
        result = await tool.execute(request.args, request.context)

        return JSONResponse(
            content={
                "success": result.success,
                "data": {
                    "output": result.output,
                    "error": result.error,
                    "metadata": result.metadata,
                },
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def batch_execute(request: BatchExecuteRequest):
    """批量并行执行工具"""
    try:
        from derisk_core.tools import BatchExecutor

        registry = get_tool_registry()
        executor = BatchExecutor(registry)

        result = await executor.execute(request.calls, request.fail_fast)

        # 转换结果
        results = {}
        for call_id, tool_result in result.results.items():
            results[call_id] = {
                "success": tool_result.success,
                "output": tool_result.output,
                "error": tool_result.error,
                "metadata": tool_result.metadata,
            }

        return JSONResponse(
            content={
                "success": result.failure_count == 0,
                "data": {
                    "results": results,
                    "success_count": result.success_count,
                    "failure_count": result.failure_count,
                    "total_duration_ms": result.total_duration_ms,
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/permission/check")
async def check_tool_permission(request: PermissionCheckRequest):
    """检查工具执行权限"""
    try:
        from derisk_core.permission import PermissionChecker, PRIMARY_PERMISSION

        checker = PermissionChecker(PRIMARY_PERMISSION)
        result = await checker.check(request.tool_name, request.args)

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "allowed": result.allowed,
                    "action": result.action.value,
                    "message": result.message,
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/permission/presets")
async def get_permission_presets():
    """获取预设权限配置"""
    from derisk_core.permission import (
        PRIMARY_PERMISSION,
        READONLY_PERMISSION,
        EXPLORE_PERMISSION,
        SANDBOX_PERMISSION,
        PermissionAction,
    )

    def ruleset_to_dict(ruleset):
        return {
            "rules": {
                pattern: {"action": rule.action.value, "message": rule.message}
                for pattern, rule in ruleset.rules.items()
            },
            "default_action": ruleset.default_action.value,
        }

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "primary": ruleset_to_dict(PRIMARY_PERMISSION),
                "readonly": ruleset_to_dict(READONLY_PERMISSION),
                "explore": ruleset_to_dict(EXPLORE_PERMISSION),
                "sandbox": ruleset_to_dict(SANDBOX_PERMISSION),
            },
        }
    )


@router.get("/sandbox/status")
async def get_sandbox_status():
    """获取沙箱状态"""
    try:
        from derisk_core.sandbox import SandboxFactory

        docker_available = False
        try:
            sandbox = await SandboxFactory.create(prefer_docker=True)
            docker_available = (
                isinstance(sandbox, type) and sandbox.__name__ == "DockerSandbox"
            )
        except:
            pass

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "docker_available": docker_available,
                    "recommended": "docker" if docker_available else "local",
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
