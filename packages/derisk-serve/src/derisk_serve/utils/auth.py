import logging
from typing import Any, Dict, List, Optional

from fastapi import Header, HTTPException, Request

from derisk._private.pydantic import BaseModel

logger = logging.getLogger(__name__)


class UserRequest(BaseModel):
    user_id: Optional[str] = None
    user_no: Optional[str] = None
    real_name: Optional[str] = None
    # same with user_id
    user_name: Optional[str] = None
    user_channel: Optional[str] = None
    role: Optional[str] = "normal"
    nick_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    nick_name_like: Optional[str] = None
    # 新增字段（插件关闭时为 None，表示不做权限检查）
    permissions: Optional[Dict[str, List[str]]] = None  # resource_type -> [actions]
    roles: Optional[List[str]] = None  # 用户拥有的角色名列表


def _is_permissions_enabled() -> bool:
    """检查 permissions 插件是否启用（运行时读取配置）"""
    try:
        from derisk_core.config import ConfigManager

        cfg = ConfigManager.get()
        entry = (cfg.feature_plugins or {}).get("permissions")
        if entry is None:
            return False
        if hasattr(entry, "enabled"):
            return bool(entry.enabled)
        if isinstance(entry, dict):
            return bool(entry.get("enabled"))
        return False
    except Exception:
        return False


def get_user_from_headers(
    request: Request = None,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    authorization: Optional[str] = Header(None),
) -> UserRequest:
    """统一用户解析入口。

    permissions OFF: 返回 mock admin（现有行为，完全不变）
    permissions ON:  验证 JWT session → 加载 RBAC 权限
                     但如果 X-User-ID 为 'admin'，则允许 bypass（本地开发模式）
    """
    try:
        if not _is_permissions_enabled():
            # ===== 插件关闭：保持现有行为 =====
            if x_user_id:
                return UserRequest(
                    user_id=x_user_id,
                    role="admin",
                    nick_name=x_user_id,
                    real_name=x_user_id,
                )
            return UserRequest(
                user_id="001",
                role="admin",
                nick_name="derisk",
                real_name="derisk",
            )

        # ===== 插件开启：优先检查 X-User-ID header (本地开发 bypass) =====
        # 支持本地开发：设置 X-User-ID: admin 可 bypass OAuth
        if x_user_id == "admin":
            from derisk_app.feature_plugins.permissions.service import PermissionService
            perms = PermissionService().get_user_permissions(3)  # admin user ID=3
            return UserRequest(
                user_id="3",
                user_no="admin",
                real_name="System Admin",
                nick_name="System Admin",
                role="admin",
                permissions=perms.permissions_map,
                roles=perms.role_names,
            )

        # ===== 验证 JWT session =====
        token = None
        if request:
            token = request.cookies.get("derisk_session")
        if not token and authorization:
            token = authorization.replace("Bearer ", "")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        from derisk_app.auth.session import verify_session_token

        user_data = verify_session_token(token)
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        # 加载用户权限（带 60s 缓存）
        from derisk_app.feature_plugins.permissions.service import PermissionService

        user_id = user_data.get("id", 0)
        perms = PermissionService().get_user_permissions(user_id)

        # 获取用户的 role 字段（从数据库）
        user_role = "normal"
        try:
            from derisk_app.auth.user_service import UserEntity
            from derisk.storage.metadata.db_manager import db

            with db.session(commit=False) as s:
                user_obj = s.query(UserEntity).filter(UserEntity.id == user_id).first()
                if user_obj and user_obj.role:
                    user_role = user_obj.role
        except Exception:
            pass

        return UserRequest(
            user_id=str(user_data.get("id", "")),
            user_no=str(user_data.get("id", "")),
            real_name=user_data.get("name", ""),
            nick_name=user_data.get("name", ""),
            email=user_data.get("email", ""),
            avatar_url=user_data.get("avatar", ""),
            role=user_role,
            permissions=perms.permissions_map,
            roles=perms.role_names,
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Authentication failed!")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


def format_permissions_summary(
    permissions: Optional[Dict[str, List[str]]], rbac_enabled: bool
) -> str:
    """将权限映射格式化为人类可读的摘要字符串。

    Args:
        permissions: 资源类型到操作列表的映射，如 {"agent": ["read", "chat"]}
        rbac_enabled: RBAC 是否启用

    Returns:
        格式化的权限摘要字符串
    """
    if not rbac_enabled:
        return "全部权限 (RBAC 未启用)"

    if not permissions:
        return "none"

    parts = []
    for resource_type, actions in permissions.items():
        if actions:
            parts.append(f"{resource_type}: {', '.join(actions)}")

    return "; ".join(parts) if parts else "none"


def build_user_context(
    user_request: UserRequest, rbac_enabled: bool
) -> Dict[str, Any]:
    """从 UserRequest 构建用户上下文字典，用于注入到 AgentContext.extra 中。

    Args:
        user_request: 当前请求的用户信息
        rbac_enabled: RBAC 权限插件是否启用

    Returns:
        用户上下文字典，包含 user_id, name, email, avatar_url, role,
        roles, permissions_map, permissions_summary, rbac_enabled
    """
    name = user_request.real_name or user_request.nick_name or user_request.user_id or "未知"

    if not rbac_enabled:
        return {
            "user_id": user_request.user_id or "001",
            "name": name,
            "email": None,
            "avatar_url": None,
            "role": user_request.role or "admin",
            "roles": [user_request.role or "admin"],
            "permissions_map": None,
            "permissions_summary": format_permissions_summary(None, rbac_enabled=False),
            "rbac_enabled": False,
        }

    return {
        "user_id": user_request.user_id or "",
        "name": name,
        "email": user_request.email,
        "avatar_url": user_request.avatar_url,
        "role": user_request.role or "normal",
        "roles": user_request.roles or [user_request.role or "normal"],
        "permissions_map": user_request.permissions,
        "permissions_summary": format_permissions_summary(
            user_request.permissions, rbac_enabled=True
        ),
        "rbac_enabled": True,
    }