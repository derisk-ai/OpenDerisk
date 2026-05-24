"""HTTP API for RBAC permission management."""

from datetime import datetime
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


# ========== Permission Request Management ==========
class PermissionRequestCreateBody(BaseModel):
    """创建权限申请"""
    request_type: str = Field(
        ...,
        pattern="^(role_assign|permission_grant|account_activation)$",
        description="申请类型",
    )
    role_id: Optional[int] = Field(None, description="角色ID (role_assign)")
    resource_type: Optional[str] = Field(None, description="资源类型 (permission_grant)")
    resource_id: Optional[str] = Field(None, description="资源ID (permission_grant)")
    action: Optional[str] = Field(None, description="操作类型 (permission_grant)")
    reason: Optional[str] = Field(None, max_length=500, description="申请理由")


class PermissionRequestReviewBody(BaseModel):
    """审批权限申请"""
    review_comment: Optional[str] = Field(None, max_length=500, description="审批意见")


class PermissionRequestListQuery(BaseModel):
    """查询权限申请"""
    status: Optional[str] = Field(None, pattern="^(pending|approved|rejected|cancelled)$")
    user_id: Optional[int] = None
    request_type: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


@router.post("/requests")
async def create_permission_request(
    body: PermissionRequestCreateBody,
    user: UserRequest = Depends(get_user_from_headers),
):
    """用户申请权限/角色/账号激活。

    - role_assign: 申请分配角色
    - permission_grant: 申请特定权限
    - account_activation: 申请账号激活
    """
    # Get user_id
    user_id = None
    for raw in (user.user_no, user.user_id):
        if raw is not None and raw != "":
            try:
                user_id = int(str(raw).strip())
                break
            except ValueError:
                continue

    if user_id is None:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Validate request type specific fields
    if body.request_type == "role_assign":
        if not body.role_id:
            raise HTTPException(status_code=400, detail="role_id required for role_assign")
        role = _dao.get_role(body.role_id)
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        # Check if already has this role
        user_roles = _dao.get_user_roles(user_id)
        if any(r["id"] == body.role_id for r in user_roles):
            raise HTTPException(status_code=409, detail="Already have this role")
        # Check if already has pending request for this role
        if _dao.has_pending_role_request(user_id, body.role_id):
            raise HTTPException(status_code=409, detail="Already have pending request for this role")

    elif body.request_type == "permission_grant":
        if not body.resource_type or not body.action:
            raise HTTPException(
                status_code=400,
                detail="resource_type and action required for permission_grant"
            )

    try:
        req = _dao.create_permission_request(
            user_id=user_id,
            request_type=body.request_type,
            role_id=body.role_id,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            action=body.action,
            reason=body.reason,
        )
        return {"success": True, "data": req}
    except Exception as e:
        logger.error(f"Failed to create permission request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create request")


@router.get("/requests")
async def list_permission_requests(
    status: Optional[str] = Query(None, pattern="^(pending|approved|rejected|cancelled)$"),
    user_id: Optional[int] = Query(None),
    reviewer_id: Optional[int] = Query(None),
    request_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """管理员查看权限申请列表"""
    requests, total = _dao.list_permission_requests(
        status=status,
        user_id=user_id,
        reviewer_id=reviewer_id,
        request_type=request_type,
        page=page,
        page_size=page_size,
    )

    # Enrich with user and role info
    from derisk_app.auth.user_service import UserService
    user_svc = UserService()
    enriched = []
    for req in requests:
        item = req.copy()
        # Add user info
        user_info = user_svc.get_user(req["user_id"])
        if user_info:
            item["user_name"] = user_info.get("name", "")
            item["user_email"] = user_info.get("email", "")
        # Add role info
        if req["role_id"]:
            role = _dao.get_role(req["role_id"])
            if role:
                item["role_name"] = role["name"]
        # Add reviewer info
        if req["reviewer_id"]:
            reviewer_info = user_svc.get_user(req["reviewer_id"])
            if reviewer_info:
                item["reviewer_name"] = reviewer_info.get("name", "")
        enriched.append(item)

    return {
        "success": True,
        "data": {
            "items": enriched,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/requests/my")
async def list_my_permission_requests(
    status: Optional[str] = Query(None, pattern="^(pending|approved|rejected|cancelled)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserRequest = Depends(get_user_from_headers),
):
    """用户查看自己的权限申请"""
    user_id = None
    for raw in (user.user_no, user.user_id):
        if raw is not None and raw != "":
            try:
                user_id = int(str(raw).strip())
                break
            except ValueError:
                continue

    if user_id is None:
        raise HTTPException(status_code=401, detail="User not authenticated")

    requests, total = _dao.list_permission_requests(
        status=status,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )

    # Enrich with role info
    enriched = []
    for req in requests:
        item = req.copy()
        if req["role_id"]:
            role = _dao.get_role(req["role_id"])
            if role:
                item["role_name"] = role["name"]
        enriched.append(item)

    return {
        "success": True,
        "data": {
            "items": enriched,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/requests/{request_id}")
async def get_permission_request(
    request_id: int,
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """管理员查看申请详情"""
    req = _dao.get_permission_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Enrich with user and role info
    from derisk_app.auth.user_service import UserService
    user_svc = UserService()
    item = req.copy()

    user_info = user_svc.get_user(req["user_id"])
    if user_info:
        item["user_name"] = user_info.get("name", "")
        item["user_email"] = user_info.get("email", "")

    if req["role_id"]:
        role = _dao.get_role(req["role_id"])
        if role:
            item["role_name"] = role["name"]

    if req["reviewer_id"]:
        reviewer_info = user_svc.get_user(req["reviewer_id"])
        if reviewer_info:
            item["reviewer_name"] = reviewer_info.get("name", "")

    return {"success": True, "data": item}


@router.post("/requests/{request_id}/approve")
async def approve_permission_request(
    request_id: int,
    body: PermissionRequestReviewBody,
    reviewer: UserRequest = Depends(require_permission("system", "admin")),
):
    """管理员审批通过权限申请"""
    # Get reviewer_id
    reviewer_id = None
    for raw in (reviewer.user_no, reviewer.user_id):
        if raw is not None and raw != "":
            try:
                reviewer_id = int(str(raw).strip())
                break
            except ValueError:
                continue

    if reviewer_id is None:
        raise HTTPException(status_code=401, detail="Reviewer not authenticated")

    req = _dao.get_permission_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req['status']}")

    try:
        result = _dao.approve_permission_request(
            request_id=request_id,
            reviewer_id=reviewer_id,
            review_comment=body.review_comment,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Request not found")

        # Invalidate permission cache for affected user
        _svc.invalidate_cache(req["user_id"])

        logger.info(f"Permission request {request_id} approved by admin {reviewer_id}")

        return {"success": True, "data": result}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Role already assigned")
    except Exception as e:
        logger.error(f"Failed to approve request {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve request")


@router.post("/requests/{request_id}/reject")
async def reject_permission_request(
    request_id: int,
    body: PermissionRequestReviewBody,
    reviewer: UserRequest = Depends(require_permission("system", "admin")),
):
    """管理员审批拒绝权限申请"""
    reviewer_id = None
    for raw in (reviewer.user_no, reviewer.user_id):
        if raw is not None and raw != "":
            try:
                reviewer_id = int(str(raw).strip())
                break
            except ValueError:
                continue

    if reviewer_id is None:
        raise HTTPException(status_code=401, detail="Reviewer not authenticated")

    req = _dao.get_permission_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req['status']}")

    result = _dao.reject_permission_request(
        request_id=request_id,
        reviewer_id=reviewer_id,
        review_comment=body.review_comment,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Request not found")

    logger.info(f"Permission request {request_id} rejected by admin {reviewer_id}")

    return {"success": True, "data": result}


@router.post("/requests/{request_id}/cancel")
async def cancel_permission_request(
    request_id: int,
    user: UserRequest = Depends(get_user_from_headers),
):
    """用户取消自己的权限申请"""
    user_id = None
    for raw in (user.user_no, user.user_id):
        if raw is not None and raw != "":
            try:
                user_id = int(str(raw).strip())
                break
            except ValueError:
                continue

    if user_id is None:
        raise HTTPException(status_code=401, detail="User not authenticated")

    result = _dao.cancel_permission_request(request_id=request_id, user_id=user_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Request not found or not owned by you or not pending"
        )

    return {"success": True, "data": result}


@router.get("/requests/pending-count")
async def get_pending_requests_count(
    _user: UserRequest = Depends(require_permission("system", "admin")),
):
    """管理员获取待审批申请数量"""
    requests, total = _dao.list_permission_requests(status="pending", page_size=1000)
    return {"success": True, "data": {"count": total}}
