"""HTTP API for RBAC permission management."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from derisk.storage.metadata.db_manager import db
from derisk_serve.utils.auth import UserRequest, get_user_from_headers

from .checker import require_permission
from .dao import PermissionDao
from .service import PermissionDefinitionService, PermissionService

router = APIRouter(prefix="/permissions", tags=["Permissions"])

_dao = PermissionDao()
_svc = PermissionService()
_def_svc = PermissionDefinitionService()


def _get_role_or_404(role_id: int) -> Dict[str, Any]:
    role = _dao.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def _ensure_role_mutable(role: Dict[str, Any]) -> None:
    if role.get("is_system") == 1:
        raise HTTPException(status_code=400, detail="System role is read-only")


# ========== Request/Response Models ==========
class RoleCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=500)


class RoleUpdateBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=500)


class PermissionAddBody(BaseModel):
    resource_type: str = Field(..., min_length=1, max_length=64)
    resource_id: str = Field(default="*", max_length=255)
    action: str = Field(..., min_length=1, max_length=32)
    effect: str = Field(default="allow", pattern="^(allow|deny)$")


class UserRoleAssignBody(BaseModel):
    role_id: int


class GroupRoleAssignBody(BaseModel):
    role_id: int


# ========== Role Management ==========
@router.get("/roles")
async def list_roles(
    _user: UserRequest = Depends(require_permission("system", "read")),
):
    roles = _dao.list_roles()
    return {"success": True, "data": roles}


@router.post("/roles")
async def create_role(
    body: RoleCreateBody,
    _user: UserRequest = Depends(require_permission("system", "write")),
):
    try:
        r = _dao.create_role(body.name, body.description)
        return {"success": True, "data": r}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Role name already exists")


@router.get("/roles/{role_id}")
async def get_role(
    role_id: int,
    _user: UserRequest = Depends(require_permission("system", "read")),
):
    r = _dao.get_role(role_id)
    if not r:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"success": True, "data": r}


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    body: RoleUpdateBody,
    _user: UserRequest = Depends(require_permission("system", "write")),
):
    role = _get_role_or_404(role_id)
    _ensure_role_mutable(role)
    try:
        r = _dao.update_role(role_id, name=body.name, description=body.description)
        if not r:
            raise HTTPException(status_code=404, detail="Role not found")
        _svc.invalidate_cache()
        return {"success": True, "data": r}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Role name already exists")


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    ok = _dao.delete_role(role_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Role not found or is system role")
    _svc.invalidate_cache()
    return {"success": True, "data": None}


# ========== Role Permission Management ==========
@router.get("/roles/{role_id}/permissions")
async def list_role_permissions(
    role_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    perms = _dao.list_role_permissions(role_id)
    return {"success": True, "data": perms}


@router.post("/roles/{role_id}/permissions")
async def add_role_permission(
    role_id: int,
    body: PermissionAddBody,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    role = _get_role_or_404(role_id)
    _ensure_role_mutable(role)
    try:
        p = _dao.add_role_permission(
            role_id,
            body.resource_type,
            body.action,
            body.resource_id,
            body.effect,
        )
        _svc.invalidate_cache()
        return {"success": True, "data": p}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Permission already exists")


@router.delete("/roles/{role_id}/permissions/{permission_id}")
async def remove_role_permission(
    role_id: int,
    permission_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    from derisk_app.feature_plugins.permissions.models import RolePermissionEntity

    role = _get_role_or_404(role_id)
    _ensure_role_mutable(role)

    with db.session() as s:
        p = (
            s.query(RolePermissionEntity)
            .filter(
                RolePermissionEntity.id == permission_id,
                RolePermissionEntity.role_id == role_id,
            )
            .first()
        )
        if not p:
            raise HTTPException(status_code=404, detail="Permission not found")

    ok = _dao.remove_role_permission(permission_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Permission not found")
    _svc.invalidate_cache()
    return {"success": True, "data": None}


# ========== User Role Assignment ==========
@router.get("/users/{user_id}/roles")
async def list_user_roles(
    user_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    assignments = _dao.list_user_role_assignments(user_id)
    return {"success": True, "data": assignments}


@router.post("/users/{user_id}/roles")
async def assign_role_to_user(
    user_id: int,
    body: UserRoleAssignBody,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    if not _dao.get_role(body.role_id):
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        ur = _dao.assign_role_to_user(user_id, body.role_id)
        _svc.invalidate_cache(user_id)
        return {"success": True, "data": ur}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Role already assigned to user")


@router.delete("/users/{user_id}/roles/{role_id}")
async def remove_user_role(
    user_id: int,
    role_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    ok = _dao.remove_user_role(user_id, role_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    _svc.invalidate_cache(user_id)
    return {"success": True, "data": None}


# ========== Group Role Assignment ==========
@router.get("/groups/{group_id}/roles")
async def list_group_roles(
    group_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    assignments = _dao.list_group_role_assignments(group_id)
    return {"success": True, "data": assignments}


@router.post("/groups/{group_id}/roles")
async def assign_role_to_group(
    group_id: int,
    body: GroupRoleAssignBody,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    if not _dao.get_role(body.role_id):
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        gr = _dao.assign_role_to_group(group_id, body.role_id)
        _svc.invalidate_cache()
        return {"success": True, "data": gr}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Role already assigned to group")


@router.delete("/groups/{group_id}/roles/{role_id}")
async def remove_group_role(
    group_id: int,
    role_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    ok = _dao.remove_group_role(group_id, role_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    _svc.invalidate_cache()
    return {"success": True, "data": None}


# ========== Current User Permissions ==========
@router.get("/me")
async def get_my_permissions(user: UserRequest = Depends(get_user_from_headers)):
    """获取当前用户的有效权限（仅需认证）"""
    return {
        "success": True,
        "data": {
            "user_id": user.user_id,
            "roles": user.roles or [],
            "permissions": user.permissions or {},
        },
    }


# ========== User Management ==========
class UserListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    keyword: str = Field(default="")


class BatchRoleAssignBody(BaseModel):
    role_ids: List[int] = Field(..., min_items=1)


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """列出所有用户（分页）"""
    from derisk_app.auth.user_service import UserService

    svc = UserService()
    users, total = svc.list_users(page=page, page_size=page_size, keyword=keyword)

    # 补充每个用户的角色信息
    user_ids = [u["id"] for u in users]
    user_roles_map: Dict[int, List[Dict[str, Any]]] = {}
    if user_ids:
        for uid in user_ids:
            direct_roles = _dao.get_user_roles(uid)
            user_roles_map[uid] = [r["name"] for r in direct_roles]

    items = []
    for u in users:
        items.append({
            "id": u["id"],
            "name": u["name"],
            "fullname": u["fullname"],
            "email": u["email"],
            # 注意：不再返回旧版 role 字段，以 RBAC 角色为准
            "is_active": u["is_active"],
            "roles": user_roles_map.get(u["id"], []),
            "gmt_create": u["gmt_create"],
        })

    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """获取用户详情（含角色信息）"""
    from derisk_app.auth.user_service import UserService

    svc = UserService()
    user = svc.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 获取直接角色
    direct_roles = _dao.get_user_roles(user_id)
    # 获取组角色
    group_roles = _dao.get_user_group_roles(user_id)

    # 合并所有角色
    all_role_names = list({r["name"] for r in direct_roles + group_roles})

    # 获取生效权限
    perms = _svc.get_user_permissions(user_id)

    return {
        "success": True,
        "data": {
            "id": user["id"],
            "name": user["name"],
            "fullname": user["fullname"],
            "email": user["email"],
            "role": user["role"],
            "is_active": user["is_active"],
            "direct_roles": direct_roles,
            "group_roles": group_roles,
            "all_roles": all_role_names,
            "effective_permissions": perms.permissions_map,
        },
    }


@router.get("/users/{user_id}/effective-permissions")
async def get_user_effective_permissions(
    user_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """获取用户的生效权限（含组继承）"""
    from derisk_app.auth.user_service import UserService

    svc = UserService()
    user = svc.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    perms = _svc.get_user_permissions(user_id)
    return {
        "success": True,
        "data": {
            "user_id": user_id,
            "roles": perms.role_names,
            "permissions": perms.permissions_map,
        },
    }


@router.post("/users/{user_id}/roles/batch")
async def batch_assign_roles(
    user_id: int,
    body: BatchRoleAssignBody,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """批量分配角色给用户"""
    from derisk_app.auth.user_service import UserService

    svc = UserService()
    user = svc.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    assigned = []
    errors = []
    for role_id in body.role_ids:
        if not _dao.get_role(role_id):
            errors.append(f"Role {role_id} not found")
            continue
        try:
            _dao.assign_role_to_user(user_id, role_id)
            assigned.append(role_id)
        except IntegrityError:
            errors.append(f"Role {role_id} already assigned")

    _svc.invalidate_cache(user_id)
    return {
        "success": True,
        "data": {
            "assigned": assigned,
            "errors": errors,
        },
    }


@router.post("/users/{user_id}/roles/batch-remove")
async def batch_remove_roles(
    user_id: int,
    body: BatchRoleAssignBody,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """批量移除用户的角色"""
    removed = []
    for role_id in body.role_ids:
        ok = _dao.remove_user_role(user_id, role_id)
        if ok:
            removed.append(role_id)

    _svc.invalidate_cache(user_id)
    return {
        "success": True,
        "data": {
            "removed": removed,
        },
    }


# ========== Scoped Resource Permissions ==========
class ScopedPermissionGrantBody(BaseModel):
    """授予资源范围权限"""

    role_id: int = Field(..., gt=0)
    resource_type: str = Field(..., min_length=1, max_length=64)
    resource_id: str = Field(..., min_length=1, max_length=255)
    action: str = Field(..., min_length=1, max_length=32)
    effect: str = Field(default="allow", pattern="^(allow|deny)$")


class ScopedPermissionRevokeBody(BaseModel):
    """撤销资源范围权限"""

    role_id: int = Field(..., gt=0)
    resource_type: str = Field(..., min_length=1, max_length=64)
    resource_id: str = Field(..., min_length=1, max_length=255)
    action: str = Field(..., min_length=1, max_length=32)


class ScopedPermissionListQuery(BaseModel):
    """查询资源范围权限"""

    role_id: Optional[int] = Field(None, gt=0)
    resource_type: Optional[str] = Field(None, min_length=1, max_length=64)
    resource_id: Optional[str] = Field(None, min_length=1, max_length=255)


@router.get("/scoped/list")
async def list_scoped_permissions(
    role_id: Optional[int] = Query(None, gt=0),
    resource_type: Optional[str] = Query(None, min_length=1, max_length=64),
    resource_id: Optional[str] = Query(None, min_length=1, max_length=255),
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """列出资源范围权限配置（支持筛选）"""
    with db.session(commit=False) as s:
        from derisk_app.feature_plugins.permissions.models import RolePermissionEntity

        query = s.query(RolePermissionEntity)
        if role_id is not None:
            query = query.filter(RolePermissionEntity.role_id == role_id)
        if resource_type is not None:
            query = query.filter(RolePermissionEntity.resource_type == resource_type)
        if resource_id is not None:
            query = query.filter(RolePermissionEntity.resource_id == resource_id)

        rows = query.order_by(RolePermissionEntity.id.asc()).all()
        permissions = [
            {
                "id": p.id,
                "role_id": p.role_id,
                "resource_type": p.resource_type,
                "resource_id": p.resource_id,
                "action": p.action,
                "effect": p.effect,
                "gmt_create": p.gmt_create.isoformat() if p.gmt_create else None,
            }
            for p in rows
        ]
        return {"success": True, "data": permissions}


@router.post("/scoped")
async def grant_scoped_permission(
    body: ScopedPermissionGrantBody,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """授予资源范围权限。

    例如：授予角色对特定智能体的 read 权限
    ```json
    {
        "role_id": 2,
        "resource_type": "agent",
        "resource_id": "financial-advisor",
        "action": "read",
        "effect": "allow"
    }
    ```
    """
    role = _get_role_or_404(body.role_id)
    _ensure_role_mutable(role)

    try:
        p = _dao.add_role_permission(
            role_id=body.role_id,
            resource_type=body.resource_type,
            action=body.action,
            resource_id=body.resource_id,
            effect=body.effect,
        )
        _svc.invalidate_cache()
        return {"success": True, "data": p}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Permission already exists")


@router.delete("/scoped")
async def revoke_scoped_permission(
    role_id: int = Query(..., gt=0),
    resource_type: str = Query(..., min_length=1, max_length=64),
    resource_id: str = Query(..., min_length=1, max_length=255),
    action: str = Query(..., min_length=1, max_length=32),
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """撤销资源范围权限。

    例如：撤销角色对特定智能体的 read 权限。
    示例请求：`DELETE /api/v1/permissions/scoped?...`
    """
    from derisk_app.feature_plugins.permissions.models import RolePermissionEntity

    with db.session() as s:
        p = (
            s.query(RolePermissionEntity)
            .filter(
                RolePermissionEntity.role_id == role_id,
                RolePermissionEntity.resource_type == resource_type,
                RolePermissionEntity.resource_id == resource_id,
                RolePermissionEntity.action == action,
            )
            .first()
        )
        if not p:
            raise HTTPException(status_code=404, detail="Permission not found")
        role = _get_role_or_404(p.role_id)
        _ensure_role_mutable(role)
        s.delete(p)
        _svc.invalidate_cache()
        return {"success": True, "data": None}


# ========== Permission Definition Management ==========
class PermissionDefCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=500)
    resource_type: str = Field(..., min_length=1, max_length=32)
    resource_id: str = Field(default="*", max_length=128)
    action: str = Field(..., min_length=1, max_length=32)
    effect: str = Field(default="allow", pattern="^(allow|deny)$")


class PermissionDefUpdateBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=500)
    resource_type: Optional[str] = Field(None, min_length=1, max_length=32)
    resource_id: Optional[str] = Field(None, max_length=128)
    action: Optional[str] = Field(None, min_length=1, max_length=32)
    effect: Optional[str] = Field(None, pattern="^(allow|deny)$")
    is_active: Optional[bool] = None


class RolePermissionDefBody(BaseModel):
    permission_def_id: int


@router.get("/definitions")
async def list_permission_definitions(
    resource_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    _user: UserRequest = Depends(require_permission("system", "read")),
):
    """列出权限定义"""
    definitions = _def_svc.list_permission_definitions(
        resource_type=resource_type,
        action=action,
        is_active=is_active,
    )
    return {"success": True, "data": definitions}


@router.post("/definitions")
async def create_permission_definition(
    body: PermissionDefCreateBody,
    _user: UserRequest = Depends(require_permission("system", "write")),
):
    """创建权限定义"""
    try:
        p = _def_svc.create_permission_definition(
            name=body.name,
            description=body.description,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            action=body.action,
            effect=body.effect,
        )
        return {"success": True, "data": p}
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Permission definition name already exists"
        )


@router.get("/definitions/{definition_id}")
async def get_permission_definition(
    definition_id: int,
    _user: UserRequest = Depends(require_permission("system", "read")),
):
    """获取权限定义详情"""
    p = _def_svc.get_permission_definition(definition_id)
    if not p:
        raise HTTPException(status_code=404, detail="Permission definition not found")
    return {"success": True, "data": p}


@router.put("/definitions/{definition_id}")
async def update_permission_definition(
    definition_id: int,
    body: PermissionDefUpdateBody,
    _user: UserRequest = Depends(require_permission("system", "write")),
):
    """更新权限定义"""
    try:
        p = _def_svc.update_permission_definition(
            definition_id=definition_id,
            name=body.name,
            description=body.description,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            action=body.action,
            effect=body.effect,
            is_active=body.is_active,
        )
        if not p:
            raise HTTPException(
                status_code=404, detail="Permission definition not found"
            )
        return {"success": True, "data": p}
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Permission definition name already exists"
        )


@router.delete("/definitions/{definition_id}")
async def delete_permission_definition(
    definition_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """删除权限定义"""
    success = _def_svc.delete_permission_definition(definition_id)
    if not success:
        raise HTTPException(status_code=404, detail="Permission definition not found")
    return {"success": True, "data": None}


# ========== Role - Permission Definition Association ==========
@router.get("/roles/{role_id}/permission-defs")
async def get_role_permission_defs(
    role_id: int,
    _user: UserRequest = Depends(require_permission("system", "read")),
):
    """获取角色关联的权限定义"""
    # 验证角色存在
    if not _dao.get_role(role_id):
        raise HTTPException(status_code=404, detail="Role not found")
    defs = _def_svc.get_role_permission_defs(role_id)
    return {"success": True, "data": defs}


@router.post("/roles/{role_id}/permission-defs")
async def add_permission_def_to_role(
    role_id: int,
    body: RolePermissionDefBody,
    _user: UserRequest = Depends(require_permission("system", "write")),
):
    """为角色添加权限定义"""
    role = _get_role_or_404(role_id)
    _ensure_role_mutable(role)
    # 验证权限定义存在
    if not _def_svc.get_permission_definition(body.permission_def_id):
        raise HTTPException(status_code=404, detail="Permission definition not found")
    try:
        r = _def_svc.add_permission_def_to_role(role_id, body.permission_def_id)
        return {"success": True, "data": r}
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Permission definition already assigned to role",
        )


@router.delete("/roles/{role_id}/permission-defs/{def_id}")
async def remove_permission_def_from_role(
    role_id: int,
    def_id: int,
    _user: UserRequest = Depends(require_permission("system", "write")),
):
    """移除角色的权限定义"""
    role = _get_role_or_404(role_id)
    _ensure_role_mutable(role)
    success = _def_svc.remove_permission_def_from_role(role_id, def_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Permission definition not found for this role"
        )
    return {"success": True, "data": None}
