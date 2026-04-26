"""User management API - list, get, update, and delete users."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from derisk_app.feature_plugins.permissions.checker import require_admin, require_permission
from derisk_app.feature_plugins.permissions.dao import PermissionDao
from derisk_app.feature_plugins.permissions.service import PermissionService
from derisk_serve.utils.auth import UserRequest, get_user_from_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

_dao = PermissionDao()
_svc = PermissionService()


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[int] = None


def _get_user_service():
    from derisk_app.auth.user_service import UserService
    return UserService()


@router.get("")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str = Query(default=""),
    _user: UserRequest = Depends(get_user_from_headers),
):
    """List users with pagination and optional keyword filter."""
    svc = _get_user_service()
    users, total = svc.list_users(page=page, page_size=page_size, keyword=keyword)
    return JSONResponse(content={
        "success": True,
        "data": {
            "list": users,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    })


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    _user: UserRequest = Depends(get_user_from_headers),
):
    """Get user by id."""
    svc = _get_user_service()
    user = svc.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return JSONResponse(content={"success": True, "data": user})


@router.patch("/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    _user: UserRequest = Depends(require_admin()),
):
    """Update user role or is_active status."""
    if body.role is None and body.is_active is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if body.role is not None and body.role not in ("normal", "admin"):
        raise HTTPException(
            status_code=400, detail="role must be 'normal' or 'admin'"
        )
    if body.is_active is not None and body.is_active not in (0, 1):
        raise HTTPException(
            status_code=400, detail="is_active must be 0 or 1"
        )
    svc = _get_user_service()
    user = svc.update_user(user_id, role=body.role, is_active=body.is_active)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return JSONResponse(content={"success": True, "data": user})


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: UserRequest = Depends(require_admin()),
):
    """Delete user (soft delete - set is_active=0).

    Only admin users can delete users. Users cannot delete themselves.
    """
    # Prevent self-deletion
    current_user_id = None
    for raw in (current_user.user_no, current_user.user_id):
        if raw is not None and raw != "":
            try:
                current_user_id = int(str(raw).strip())
                break
            except ValueError:
                continue

    if current_user_id is not None and current_user_id == user_id:
        raise HTTPException(
            status_code=400, detail="Cannot delete your own account"
        )

    svc = _get_user_service()

    # Check if user exists
    user = svc.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    # Perform soft delete
    success = svc.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete user")

    logger.info(f"User {user_id} deleted by admin {current_user_id}")
    return JSONResponse(
        content={"success": True, "message": f"User {user_id} deleted successfully"}
    )


@router.get("/{user_id}/permissions")
async def get_user_permissions(
    user_id: int,
    _user: UserRequest = Depends(get_user_from_headers),
):
    """Get user's effective permissions including scoped resource permissions.

    Returns permissions grouped by resource type, distinguishing between:
    - wildcard permissions (resource_id="*")
    - scoped permissions (resource_id=specific resource)

    Example response:
    ```json
    {
        "success": true,
        "data": {
            "user_id": 1,
            "roles": ["operator"],
            "permissions": {
                "agent": {
                    "wildcard": ["read"],
                    "scoped": {
                        "financial-advisor": ["read", "chat"],
                        "data-analyst": ["read"]
                    }
                },
                "tool": {
                    "wildcard": ["read"],
                    "scoped": {
                        "code_interpreter": ["read", "execute"]
                    }
                }
            }
        }
    }
    ```
    """
    from derisk_app.auth.user_service import UserService

    svc = UserService()
    user = svc.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get user's roles
    direct_roles = _dao.get_user_roles(user_id)
    group_roles = _dao.get_user_group_roles(user_id)
    role_names = list({r["name"] for r in direct_roles + group_roles})
    role_ids = list({r["id"] for r in direct_roles + group_roles})

    # Get all permissions for user's roles
    if role_ids:
        all_perms = _svc.get_user_permissions(user_id).permissions_map
    else:
        all_perms = {}

    # Organize permissions by resource type
    # Separate wildcard permissions from scoped permissions
    organized_perms: Dict[str, Dict[str, Any]] = {}

    for key, actions in all_perms.items():
        if ":" in key:
            # Scoped permission (e.g., "agent:financial-advisor")
            parts = key.split(":", 1)
            resource_type = parts[0]
            resource_id = parts[1]

            if resource_type not in organized_perms:
                organized_perms[resource_type] = {"wildcard": [], "scoped": {}}

            if resource_id == "*":
                # Wildcard permission
                organized_perms[resource_type]["wildcard"].extend(actions)
            else:
                # Scoped permission
                if resource_id not in organized_perms[resource_type]["scoped"]:
                    organized_perms[resource_type]["scoped"][resource_id] = []
                organized_perms[resource_type]["scoped"][resource_id].extend(actions)
        else:
            # Resource type level permission (treat as wildcard)
            resource_type = key
            if resource_type not in organized_perms:
                organized_perms[resource_type] = {"wildcard": [], "scoped": {}}
            organized_perms[resource_type]["wildcard"].extend(actions)

    # Remove duplicates
    for resource_type in organized_perms:
        organized_perms[resource_type]["wildcard"] = list(
            set(organized_perms[resource_type]["wildcard"])
        )
        for resource_id in organized_perms[resource_type]["scoped"]:
            organized_perms[resource_type]["scoped"][resource_id] = list(
                set(organized_perms[resource_type]["scoped"][resource_id])
            )

    return {
        "success": True,
        "data": {
            "user_id": user_id,
            "roles": role_names,
            "permissions": organized_perms,
        },
    }
