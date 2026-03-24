"""HTTP API for user groups (only mounted when feature plugin user_groups is enabled)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from derisk_serve.utils.auth import UserRequest, get_user_from_headers
from derisk_app.feature_plugins.user_groups.service import UserGroupService

router = APIRouter(prefix="/user-groups", tags=["UserGroups"])

_svc = UserGroupService()


class GroupCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=2000)


class GroupUpdateBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=2000)


class MembersAddBody(BaseModel):
    user_ids: List[int] = Field(..., min_length=1)


@router.get("/groups")
async def list_groups(_user: UserRequest = Depends(get_user_from_headers)):
    groups = _svc.list_groups()
    for g in groups:
        g["member_count"] = _svc.count_members(g["id"])
    return {"success": True, "data": groups}


@router.post("/groups")
async def create_group(
    body: GroupCreateBody,
    _user: UserRequest = Depends(get_user_from_headers),
):
    try:
        g = _svc.create_group(body.name, body.description)
        return {"success": True, "data": g}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Group name already exists")


@router.get("/groups/{group_id}")
async def get_group(
    group_id: int,
    _user: UserRequest = Depends(get_user_from_headers),
):
    g = _svc.get_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    g["member_count"] = _svc.count_members(group_id)
    return {"success": True, "data": g}


@router.put("/groups/{group_id}")
async def update_group(
    group_id: int,
    body: GroupUpdateBody,
    _user: UserRequest = Depends(get_user_from_headers),
):
    try:
        g = _svc.update_group(group_id, name=body.name, description=body.description)
        if not g:
            raise HTTPException(status_code=404, detail="Group not found")
        return {"success": True, "data": g}
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Group name already exists")


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    _user: UserRequest = Depends(get_user_from_headers),
):
    ok = _svc.delete_group(group_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"success": True, "data": None}


@router.get("/groups/{group_id}/members")
async def list_members(
    group_id: int,
    _user: UserRequest = Depends(get_user_from_headers),
):
    if not _svc.get_group(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    members = _svc.list_members(group_id)
    return {"success": True, "data": members}


@router.post("/groups/{group_id}/members")
async def add_members(
    group_id: int,
    body: MembersAddBody,
    _user: UserRequest = Depends(get_user_from_headers),
):
    if not _svc.get_group(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    added, _ = _svc.add_members(group_id, body.user_ids)
    return {"success": True, "data": {"added": added}}


@router.delete("/groups/{group_id}/members/{member_user_id}")
async def remove_member(
    group_id: int,
    member_user_id: int,
    _user: UserRequest = Depends(get_user_from_headers),
):
    ok = _svc.remove_member(group_id, member_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Membership not found")
    return {"success": True, "data": None}
