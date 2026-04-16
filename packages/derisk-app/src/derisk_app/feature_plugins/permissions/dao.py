"""Data access layer for RBAC permission tables."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from derisk.storage.metadata.db_manager import db

from .models import (
    GroupRoleEntity,
    PermissionDefinitionEntity,
    RoleEntity,
    RolePermissionDefEntity,
    RolePermissionEntity,
    UserRoleEntity,
)

logger = logging.getLogger(__name__)


class PermissionDao:
    """权限数据访问层"""

    # ========== Role CRUD ==========
    def list_roles(self) -> List[Dict[str, Any]]:
        with db.session(commit=False) as s:
            rows = s.query(RoleEntity).order_by(RoleEntity.id.asc()).all()
            return [self._role_row(r) for r in rows]

    def get_role(self, role_id: int) -> Optional[Dict[str, Any]]:
        with db.session(commit=False) as s:
            r = s.query(RoleEntity).filter(RoleEntity.id == role_id).first()
            return self._role_row(r) if r else None

    def get_role_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with db.session(commit=False) as s:
            r = s.query(RoleEntity).filter(RoleEntity.name == name).first()
            return self._role_row(r) if r else None

    def create_role(
        self, name: str, description: Optional[str] = None, is_system: int = 0
    ) -> Dict[str, Any]:
        with db.session() as s:
            r = RoleEntity(
                name=name.strip(), description=description, is_system=is_system
            )
            s.add(r)
            s.flush()
            s.refresh(r)
            return self._role_row(r)

    def update_role(
        self,
        role_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with db.session() as s:
            r = s.query(RoleEntity).filter(RoleEntity.id == role_id).first()
            if not r:
                return None
            if name is not None:
                r.name = name.strip()
            if description is not None:
                r.description = description
            s.flush()
            s.refresh(r)
            return self._role_row(r)

    def delete_role(self, role_id: int) -> bool:
        with db.session() as s:
            r = s.query(RoleEntity).filter(RoleEntity.id == role_id).first()
            if not r or r.is_system == 1:
                return False
            # 级联删除关联数据
            s.query(RolePermissionEntity).filter(
                RolePermissionEntity.role_id == role_id
            ).delete()
            s.query(UserRoleEntity).filter(UserRoleEntity.role_id == role_id).delete()
            s.query(GroupRoleEntity).filter(GroupRoleEntity.role_id == role_id).delete()
            s.delete(r)
            return True

    # ========== Role Permission CRUD ==========
    def list_role_permissions(self, role_id: int) -> List[Dict[str, Any]]:
        with db.session(commit=False) as s:
            rows = (
                s.query(RolePermissionEntity)
                .filter(RolePermissionEntity.role_id == role_id)
                .order_by(RolePermissionEntity.id.asc())
                .all()
            )
            return [self._perm_row(p) for p in rows]

    def add_role_permission(
        self,
        role_id: int,
        resource_type: str,
        action: str,
        resource_id: str = "*",
        effect: str = "allow",
    ) -> Dict[str, Any]:
        with db.session() as s:
            p = RolePermissionEntity(
                role_id=role_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                effect=effect,
            )
            s.add(p)
            s.flush()
            s.refresh(p)
            return self._perm_row(p)

    def remove_role_permission(self, permission_id: int) -> bool:
        with db.session() as s:
            p = (
                s.query(RolePermissionEntity)
                .filter(RolePermissionEntity.id == permission_id)
                .first()
            )
            if not p:
                return False
            s.delete(p)
            return True

    def get_permissions_for_roles(self, role_ids: List[int]) -> List[Dict[str, Any]]:
        """获取多个角色的所有权限"""
        if not role_ids:
            return []
        with db.session(commit=False) as s:
            rows = (
                s.query(RolePermissionEntity)
                .filter(RolePermissionEntity.role_id.in_(role_ids))
                .all()
            )
            return [self._perm_row(p) for p in rows]

    # ========== User Role Assignment ==========
    def get_user_roles(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户的直接角色（通过 user_role 表）"""
        with db.session(commit=False) as s:
            rows = (
                s.query(RoleEntity)
                .join(UserRoleEntity, UserRoleEntity.role_id == RoleEntity.id)
                .filter(UserRoleEntity.user_id == user_id)
                .all()
            )
            return [self._role_row(r) for r in rows]

    def assign_role_to_user(self, user_id: int, role_id: int) -> Dict[str, Any]:
        with db.session() as s:
            ur = UserRoleEntity(user_id=user_id, role_id=role_id)
            s.add(ur)
            s.flush()
            s.refresh(ur)
            return {"id": ur.id, "user_id": ur.user_id, "role_id": ur.role_id}

    def remove_user_role(self, user_id: int, role_id: int) -> bool:
        with db.session() as s:
            ur = (
                s.query(UserRoleEntity)
                .filter(
                    UserRoleEntity.user_id == user_id,
                    UserRoleEntity.role_id == role_id,
                )
                .first()
            )
            if not ur:
                return False
            s.delete(ur)
            return True

    def list_user_role_assignments(self, user_id: int) -> List[Dict[str, Any]]:
        with db.session(commit=False) as s:
            rows = (
                s.query(UserRoleEntity, RoleEntity)
                .join(RoleEntity, RoleEntity.id == UserRoleEntity.role_id)
                .filter(UserRoleEntity.user_id == user_id)
                .all()
            )
            return [
                {"id": ur.id, "role_id": r.id, "role_name": r.name} for ur, r in rows
            ]

    # ========== Group Role Assignment ==========
    def get_user_group_roles(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户通过用户组继承的角色"""
        with db.session(commit=False) as s:
            # 需要关联 user_group_member 和 group_role
            from derisk_app.feature_plugins.user_groups.models import (
                UserGroupMemberEntity,
            )

            rows = (
                s.query(RoleEntity)
                .join(GroupRoleEntity, GroupRoleEntity.role_id == RoleEntity.id)
                .join(
                    UserGroupMemberEntity,
                    UserGroupMemberEntity.group_id == GroupRoleEntity.group_id,
                )
                .filter(UserGroupMemberEntity.user_id == user_id)
                .all()
            )
            return [self._role_row(r) for r in rows]

    def assign_role_to_group(self, group_id: int, role_id: int) -> Dict[str, Any]:
        with db.session() as s:
            gr = GroupRoleEntity(group_id=group_id, role_id=role_id)
            s.add(gr)
            s.flush()
            s.refresh(gr)
            return {"id": gr.id, "group_id": gr.group_id, "role_id": gr.role_id}

    def remove_group_role(self, group_id: int, role_id: int) -> bool:
        with db.session() as s:
            gr = (
                s.query(GroupRoleEntity)
                .filter(
                    GroupRoleEntity.group_id == group_id,
                    GroupRoleEntity.role_id == role_id,
                )
                .first()
            )
            if not gr:
                return False
            s.delete(gr)
            return True

    def list_group_role_assignments(self, group_id: int) -> List[Dict[str, Any]]:
        with db.session(commit=False) as s:
            rows = (
                s.query(GroupRoleEntity, RoleEntity)
                .join(RoleEntity, RoleEntity.id == GroupRoleEntity.role_id)
                .filter(GroupRoleEntity.group_id == group_id)
                .all()
            )
            return [
                {"id": gr.id, "role_id": r.id, "role_name": r.name} for gr, r in rows
            ]

    # ========== Helper Methods ==========
    @staticmethod
    def _role_row(r: RoleEntity) -> Dict[str, Any]:
        return {
            "id": r.id,
            "name": r.name,
            "description": r.description or "",
            "is_system": r.is_system,
            "gmt_create": r.gmt_create.isoformat() if r.gmt_create else None,
            "gmt_modify": r.gmt_modify.isoformat() if r.gmt_modify else None,
        }

    @staticmethod
    def _perm_row(p: RolePermissionEntity) -> Dict[str, Any]:
        return {
            "id": p.id,
            "role_id": p.role_id,
            "resource_type": p.resource_type,
            "resource_id": p.resource_id,
            "action": p.action,
            "effect": p.effect,
            "gmt_create": p.gmt_create.isoformat() if p.gmt_create else None,
        }

    # ========== Permission Definition CRUD ==========
    def list_permission_definitions(
        self,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """列出权限定义"""
        with db.session(commit=False) as s:
            query = s.query(PermissionDefinitionEntity)
            if resource_type:
                query = query.filter(
                    PermissionDefinitionEntity.resource_type == resource_type
                )
            if action:
                query = query.filter(PermissionDefinitionEntity.action == action)
            if is_active is not None:
                query = query.filter(
                    PermissionDefinitionEntity.is_active == is_active
                )
            rows = query.order_by(PermissionDefinitionEntity.id.asc()).all()
            return [self._perm_def_row(r) for r in rows]

    def get_permission_definition(
        self, definition_id: int
    ) -> Optional[Dict[str, Any]]:
        """获取权限定义详情"""
        with db.session(commit=False) as s:
            p = (
                s.query(PermissionDefinitionEntity)
                .filter(PermissionDefinitionEntity.id == definition_id)
                .first()
            )
            return self._perm_def_row(p) if p else None

    def create_permission_definition(
        self,
        name: str,
        resource_type: str,
        action: str,
        resource_id: str = "*",
        effect: str = "allow",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建权限定义"""
        with db.session() as s:
            p = PermissionDefinitionEntity(
                name=name.strip(),
                description=description,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                effect=effect,
                is_active=True,
            )
            s.add(p)
            s.flush()
            s.refresh(p)
            return self._perm_def_row(p)

    def update_permission_definition(
        self,
        definition_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        effect: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """更新权限定义"""
        with db.session() as s:
            p = (
                s.query(PermissionDefinitionEntity)
                .filter(PermissionDefinitionEntity.id == definition_id)
                .first()
            )
            if not p:
                return None
            if name is not None:
                p.name = name.strip()
            if description is not None:
                p.description = description
            if resource_type is not None:
                p.resource_type = resource_type
            if resource_id is not None:
                p.resource_id = resource_id
            if action is not None:
                p.action = action
            if effect is not None:
                p.effect = effect
            if is_active is not None:
                p.is_active = is_active
            s.flush()
            s.refresh(p)
            return self._perm_def_row(p)

    def delete_permission_definition(self, definition_id: int) -> bool:
        """删除权限定义"""
        with db.session() as s:
            p = (
                s.query(PermissionDefinitionEntity)
                .filter(PermissionDefinitionEntity.id == definition_id)
                .first()
            )
            if not p:
                return False
            # 删除关联的角色权限定义
            s.query(RolePermissionDefEntity).filter(
                RolePermissionDefEntity.permission_def_id == definition_id
            ).delete()
            s.delete(p)
            return True

    # ========== Role Permission Definition Association ==========
    def get_role_permission_defs(self, role_id: int) -> List[Dict[str, Any]]:
        """获取角色关联的权限定义"""
        with db.session(commit=False) as s:
            rows = (
                s.query(PermissionDefinitionEntity)
                .join(
                    RolePermissionDefEntity,
                    RolePermissionDefEntity.permission_def_id
                    == PermissionDefinitionEntity.id,
                )
                .filter(RolePermissionDefEntity.role_id == role_id)
                .all()
            )
            return [self._perm_def_row(r) for r in rows]

    def add_permission_def_to_role(
        self, role_id: int, permission_def_id: int
    ) -> Optional[Dict[str, Any]]:
        """为角色添加权限定义"""
        with db.session() as s:
            # 检查是否已存在
            existing = (
                s.query(RolePermissionDefEntity)
                .filter(
                    RolePermissionDefEntity.role_id == role_id,
                    RolePermissionDefEntity.permission_def_id == permission_def_id,
                )
                .first()
            )
            if existing:
                return {
                    "id": existing.id,
                    "role_id": existing.role_id,
                    "permission_def_id": existing.permission_def_id,
                }
            rpd = RolePermissionDefEntity(
                role_id=role_id, permission_def_id=permission_def_id
            )
            s.add(rpd)
            s.flush()
            s.refresh(rpd)
            return {
                "id": rpd.id,
                "role_id": rpd.role_id,
                "permission_def_id": rpd.permission_def_id,
            }

    def remove_permission_def_from_role(
        self, role_id: int, permission_def_id: int
    ) -> bool:
        """移除角色的权限定义"""
        with db.session() as s:
            rpd = (
                s.query(RolePermissionDefEntity)
                .filter(
                    RolePermissionDefEntity.role_id == role_id,
                    RolePermissionDefEntity.permission_def_id == permission_def_id,
                )
                .first()
            )
            if not rpd:
                return False
            s.delete(rpd)
            return True

    @staticmethod
    def _perm_def_row(p: PermissionDefinitionEntity) -> Dict[str, Any]:
        return {
            "id": p.id,
            "name": p.name,
            "description": p.description or "",
            "resource_type": p.resource_type,
            "resource_id": p.resource_id,
            "action": p.action,
            "effect": p.effect,
            "is_active": p.is_active,
            "gmt_create": p.gmt_create.isoformat() if p.gmt_create else None,
            "gmt_modify": p.gmt_modify.isoformat() if p.gmt_modify else None,
        }
