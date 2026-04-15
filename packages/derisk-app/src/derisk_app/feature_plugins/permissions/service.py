"""Permission service with in-memory caching."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .dao import PermissionDao


@dataclass
class UserPermissions:
    """用户的聚合权限快照"""

    user_id: int
    role_names: List[str]
    permissions_map: Dict[str, List[str]]  # resource_type -> [action, ...]
    loaded_at: float = field(default_factory=time.time)


class PermissionService:
    """权限核心逻辑，负责聚合用户权限并提供内存缓存。"""

    _cache: Dict[int, UserPermissions] = {}
    _cache_ttl = 60  # 缓存有效期（秒）

    def __init__(self):
        self._dao = PermissionDao()

    def get_user_permissions(self, user_id: int) -> UserPermissions:
        """加载用户的全部有效权限（直接角色 + 用户组角色），60s 缓存"""
        user_id_int = int(user_id) if user_id else 0
        cached = self._cache.get(user_id_int)
        if cached and (time.time() - cached.loaded_at) < self._cache_ttl:
            return cached

        # 1. 获取直接角色
        direct_roles = self._dao.get_user_roles(user_id_int)
        # 2. 获取通过用户组继承的角色
        group_roles = self._dao.get_user_group_roles(user_id_int)

        # 合并角色（去重）
        all_roles = {r["id"]: r["name"] for r in direct_roles + group_roles}
        role_ids = list(all_roles.keys())
        role_names = list(all_roles.values())

        # 3. 聚合所有角色的权限
        permissions_map: Dict[str, List[str]] = {}
        if role_ids:
            perms = self._dao.get_permissions_for_roles(role_ids)
            for p in perms:
                if p["effect"] == "allow":
                    rt = p["resource_type"]
                    act = p["action"]
                    permissions_map.setdefault(rt, [])
                    if act not in permissions_map[rt]:
                        permissions_map[rt].append(act)

        result = UserPermissions(
            user_id=user_id_int,
            role_names=role_names,
            permissions_map=permissions_map,
        )
        self._cache[user_id_int] = result
        return result

    def invalidate_cache(self, user_id: Optional[int] = None) -> None:
        """清除缓存。管理 API 修改角色/权限后调用。"""
        if user_id is not None:
            self._cache.pop(user_id, None)
        else:
            self._cache.clear()

    def check_permission(self, user_id: int, resource_type: str, action: str) -> bool:
        """检查用户是否拥有指定权限（通配符模式）"""
        return self.check_scoped_permission(user_id, resource_type, "*", action)

    def check_scoped_permission(
        self,
        user_id: int,
        resource_type: str,
        resource_id: str,
        action: str,
    ) -> bool:
        """检查用户是否拥有指定资源的权限。

        权限检查优先级：
        1. superadmin 绕过所有检查
        2. 精确匹配 resource_id 的权限（如 agent:financial-advisor）
        3. 通配符 resource_id="*" 的权限（如 agent:* 或简化为 agent）
        """
        perms = self.get_user_permissions(user_id)

        # superadmin 绕过所有检查
        if "superadmin" in perms.role_names:
            return True

        # 1. 检查精确匹配（resource_id 指定的资源）
        if resource_id and resource_id != "*":
            scoped_key = f"{resource_type}:{resource_id}"
            scoped_actions = perms.permissions_map.get(scoped_key, [])
            if action in scoped_actions or "admin" in scoped_actions:
                return True

        # 2. 检查通配符权限（resource_id="*"）
        allowed = perms.permissions_map.get(resource_type, [])
        wildcard = perms.permissions_map.get("*", [])

        return (
            action in allowed
            or "admin" in allowed
            or action in wildcard
            or "admin" in wildcard
        )


class PermissionDefinitionService:
    """权限定义服务，用于管理独立权限定义"""

    def __init__(self):
        self._dao = PermissionDao()

    def list_permission_definitions(
        self,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict]:
        """列出权限定义"""
        return self._dao.list_permission_definitions(
            resource_type=resource_type,
            action=action,
            is_active=is_active,
        )

    def get_permission_definition(self, definition_id: int) -> Optional[Dict]:
        """获取权限定义详情"""
        return self._dao.get_permission_definition(definition_id)

    def create_permission_definition(
        self,
        name: str,
        resource_type: str,
        action: str,
        resource_id: str = "*",
        effect: str = "allow",
        description: Optional[str] = None,
    ) -> Dict:
        """创建权限定义"""
        return self._dao.create_permission_definition(
            name=name,
            resource_type=resource_type,
            action=action,
            resource_id=resource_id,
            effect=effect,
            description=description,
        )

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
    ) -> Optional[Dict]:
        """更新权限定义"""
        return self._dao.update_permission_definition(
            definition_id=definition_id,
            name=name,
            description=description,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            effect=effect,
            is_active=is_active,
        )

    def delete_permission_definition(self, definition_id: int) -> bool:
        """删除权限定义"""
        return self._dao.delete_permission_definition(definition_id)

    def get_role_permission_defs(self, role_id: int) -> List[Dict]:
        """获取角色关联的权限定义"""
        return self._dao.get_role_permission_defs(role_id)

    def add_permission_def_to_role(
        self, role_id: int, permission_def_id: int
    ) -> Optional[Dict]:
        """为角色添加权限定义"""
        return self._dao.add_permission_def_to_role(role_id, permission_def_id)

    def remove_permission_def_from_role(
        self, role_id: int, permission_def_id: int
    ) -> bool:
        """移除角色的权限定义"""
        return self._dao.remove_permission_def_from_role(role_id, permission_def_id)
