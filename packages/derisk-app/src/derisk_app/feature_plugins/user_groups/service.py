"""CRUD for user groups and membership."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func

from derisk.storage.metadata.db_manager import db
from derisk_app.feature_plugins.user_groups.models import (
    UserGroupEntity,
    UserGroupMemberEntity,
)

logger = logging.getLogger(__name__)


class UserGroupService:
    def list_groups(self) -> List[Dict[str, Any]]:
        with db.session(commit=False) as s:
            rows = s.query(UserGroupEntity).order_by(UserGroupEntity.id.asc()).all()
            return [self._group_row(g) for g in rows]

    def get_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        with db.session(commit=False) as s:
            g = s.query(UserGroupEntity).filter(UserGroupEntity.id == group_id).first()
            return self._group_row(g) if g else None

    def create_group(self, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        try:
            with db.session() as s:
                g = UserGroupEntity(name=name.strip(), description=description or None)
                s.add(g)
                s.flush()
                s.refresh(g)
                return self._group_row(g)
        except Exception as e:
            logger.exception("create_group failed: %s", e)
            raise

    def update_group(
        self, group_id: int, name: Optional[str] = None, description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            with db.session() as s:
                g = s.query(UserGroupEntity).filter(UserGroupEntity.id == group_id).first()
                if not g:
                    return None
                if name is not None:
                    g.name = name.strip()
                if description is not None:
                    g.description = description
                s.flush()
                s.refresh(g)
                return self._group_row(g)
        except Exception as e:
            logger.exception("update_group failed: %s", e)
            raise

    def delete_group(self, group_id: int) -> bool:
        try:
            with db.session() as s:
                g = s.query(UserGroupEntity).filter(UserGroupEntity.id == group_id).first()
                if not g:
                    return False
                s.query(UserGroupMemberEntity).filter(
                    UserGroupMemberEntity.group_id == group_id
                ).delete()
                s.delete(g)
                return True
        except Exception as e:
            logger.exception("delete_group failed: %s", e)
            raise

    def list_members(self, group_id: int) -> List[Dict[str, Any]]:
        with db.session(commit=False) as s:
            rows = (
                s.query(UserGroupMemberEntity)
                .filter(UserGroupMemberEntity.group_id == group_id)
                .order_by(UserGroupMemberEntity.id.asc())
                .all()
            )
            return [self._member_row(m) for m in rows]

    def add_members(self, group_id: int, user_ids: List[int]) -> Tuple[int, List[int]]:
        try:
            with db.session() as s:
                g = s.query(UserGroupEntity).filter(UserGroupEntity.id == group_id).first()
                if not g:
                    return 0, []
                added = 0
                for uid in user_ids:
                    exists = (
                        s.query(UserGroupMemberEntity)
                        .filter(
                            UserGroupMemberEntity.group_id == group_id,
                            UserGroupMemberEntity.user_id == uid,
                        )
                        .first()
                    )
                    if exists:
                        continue
                    s.add(UserGroupMemberEntity(group_id=group_id, user_id=uid))
                    added += 1
                return added, []
        except Exception as e:
            logger.exception("add_members failed: %s", e)
            raise

    def remove_member(self, group_id: int, user_id: int) -> bool:
        try:
            with db.session() as s:
                row = (
                    s.query(UserGroupMemberEntity)
                    .filter(
                        UserGroupMemberEntity.group_id == group_id,
                        UserGroupMemberEntity.user_id == user_id,
                    )
                    .first()
                )
                if not row:
                    return False
                s.delete(row)
                return True
        except Exception as e:
            logger.exception("remove_member failed: %s", e)
            raise

    def count_members(self, group_id: int) -> int:
        with db.session(commit=False) as s:
            n = (
                s.query(func.count(UserGroupMemberEntity.id))
                .filter(UserGroupMemberEntity.group_id == group_id)
                .scalar()
            )
            return int(n or 0)

    @staticmethod
    def _group_row(g: UserGroupEntity) -> Dict[str, Any]:
        return {
            "id": g.id,
            "name": g.name,
            "description": g.description or "",
            "gmt_create": g.gmt_create.isoformat() if g.gmt_create else None,
            "gmt_modify": g.gmt_modify.isoformat() if g.gmt_modify else None,
        }

    @staticmethod
    def _member_row(m: UserGroupMemberEntity) -> Dict[str, Any]:
        return {
            "id": m.id,
            "group_id": m.group_id,
            "user_id": m.user_id,
            "gmt_create": m.gmt_create.isoformat() if m.gmt_create else None,
        }
