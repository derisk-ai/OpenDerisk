"""FastAPI dependency factories for permission checking."""

from typing import Optional

from fastapi import Depends, HTTPException

from derisk_serve.utils.auth import UserRequest, get_user_from_headers


def require_permission(
    resource_type: str,
    action: str,
    resource_id: Optional[str] = "*",
):
    """FastAPI 依赖工厂 - 检查用户是否拥有指定权限。

    使用方式:
        # 检查对所有 agent 的 write 权限（通配符）
        @router.post("/agents")
        async def create_agent(
            user: UserRequest = Depends(require_permission("agent", "write")),
        ):
            ...

        # 检查对特定 agent 的 chat 权限（资源范围）
        @router.post("/agents/{agent_name}/chat")
        async def chat_with_agent(
            agent_name: str,
            user: UserRequest = Depends(require_permission("agent", "chat", resource_id=agent_name)),
        ):
            ...

    插件关闭时：直接放行（user.permissions 为 None）
    插件开启时：检查 RBAC，无权限返回 403

    注意：如果用户 role 字段为 "admin"，也允许通过（兼容旧版 admin 用户）

    权限检查优先级：
    1. superadmin 角色绕过所有检查
    2. 精确匹配 resource_id 的权限
    3. 通配符 resource_id="*" 的权限
    """

    def dependency(user: UserRequest = Depends(get_user_from_headers)) -> UserRequest:
        # 插件关闭 → permissions 为 None → 不做检查
        if user.permissions is None:
            return user

        # 用户表中 role 为 admin 的用户也允许通过（兼容旧版）
        if user.role == "admin":
            return user

        # superadmin 角色绕过所有权限检查
        if "superadmin" in (user.roles or []):
            return user

        # 检查权限：支持资源范围权限和通配符权限
        # 权限格式：user.permissions 是 dict，value 是 list of strings
        # 例如：{"agent": ["read", "chat"], "agent:financial-advisor": ["read"]}

        # 1. 先检查精确匹配（resource_id 指定的资源）
        if resource_id and resource_id != "*":
            scoped_key = f"{resource_type}:{resource_id}"
            scoped_actions = user.permissions.get(scoped_key, [])
            if action in scoped_actions or "admin" in scoped_actions:
                return user

        # 2. 检查通配符权限（resource_id="*" 或 resource_type 本身）
        allowed = user.permissions.get(resource_type, [])
        wildcard = user.permissions.get("*", [])

        if (
            action in allowed
            or "admin" in allowed
            or action in wildcard
            or "admin" in wildcard
        ):
            return user

        # 3. 无权限
        if resource_id and resource_id != "*":
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {action} on {resource_type}:{resource_id}",
            )
        else:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {action} on {resource_type}",
            )

    return dependency


def require_admin():
    """快捷方式：要求 system admin 权限"""
    return require_permission("system", "admin")


def require_read(resource_type: str):
    """快捷方式：要求读权限"""
    return require_permission(resource_type, "read")


def require_write(resource_type: str):
    """快捷方式：要求写权限"""
    return require_permission(resource_type, "write")


def require_execute(resource_type: str):
    """快捷方式：要求执行权限"""
    return require_permission(resource_type, "execute")