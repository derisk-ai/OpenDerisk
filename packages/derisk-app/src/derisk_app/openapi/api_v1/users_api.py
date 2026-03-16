"""User management API - list, get, and update users."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])


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
async def get_user(user_id: int):
    """Get user by id."""
    svc = _get_user_service()
    user = svc.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return JSONResponse(content={"success": True, "data": user})


@router.patch("/{user_id}")
async def update_user(user_id: int, body: UpdateUserRequest):
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
