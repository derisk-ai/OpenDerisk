"""Seed data initialization for built-in roles and default admin user."""

import logging

from sqlalchemy import or_

from .dao import PermissionDao

logger = logging.getLogger(__name__)

# Default permission definitions that can be assigned to roles
SEED_PERMISSION_DEFINITIONS = [
    # Agent permissions
    {"name": "agent_read_all", "description": "可读取所有智能体", "resource_type": "agent", "resource_id": "*", "action": "read"},
    {"name": "agent_chat_all", "description": "可与所有智能体对话", "resource_type": "agent", "resource_id": "*", "action": "chat"},
    {"name": "agent_write_all", "description": "可管理所有智能体配置", "resource_type": "agent", "resource_id": "*", "action": "write"},
    {"name": "agent_admin_all", "description": "可完全管理所有智能体", "resource_type": "agent", "resource_id": "*", "action": "admin"},
    # Tool permissions
    {"name": "tool_read_all", "description": "可读取所有工具", "resource_type": "tool", "resource_id": "*", "action": "read"},
    {"name": "tool_execute_all", "description": "可执行所有工具", "resource_type": "tool", "resource_id": "*", "action": "execute"},
    {"name": "tool_manage_all", "description": "可管理所有工具", "resource_type": "tool", "resource_id": "*", "action": "manage"},
    # Knowledge permissions
    {"name": "knowledge_read_all", "description": "可读取所有知识库", "resource_type": "knowledge", "resource_id": "*", "action": "read"},
    {"name": "knowledge_query_all", "description": "可检索所有知识库", "resource_type": "knowledge", "resource_id": "*", "action": "query"},
    {"name": "knowledge_write_all", "description": "可管理所有知识库", "resource_type": "knowledge", "resource_id": "*", "action": "write"},
    # Model permissions
    {"name": "model_read_all", "description": "可读取所有模型", "resource_type": "model", "resource_id": "*", "action": "read"},
    {"name": "model_chat_all", "description": "可使用所有模型对话", "resource_type": "model", "resource_id": "*", "action": "chat"},
    {"name": "model_manage_all", "description": "可管理所有模型", "resource_type": "model", "resource_id": "*", "action": "manage"},
    # System permissions
    {"name": "system_admin", "description": "系统管理员权限", "resource_type": "system", "resource_id": "*", "action": "admin"},
]

SEED_ROLES = [
    {
        "name": "guest",
        "description": "访客（仅可查看模型和监控，不能查看智能体/工具/知识库）",
        "is_system": 1,
        "permissions": [
            ("model", "read"),
            ("model", "chat"),
        ],
    },
    {
        "name": "viewer",
        "description": "只读访问所有资源（可查看界面和详情，但不能对话/执行/编辑）",
        "is_system": 1,
        "permissions": [
            ("agent", "read"),
            ("tool", "read"),
            ("knowledge", "read"),
            ("model", "read"),
        ],
    },
    {
        "name": "operator",
        "description": "操作员（可查看、对话、执行工具、检索知识库，但不能编辑配置）",
        "is_system": 1,
        "permissions": [
            ("agent", "read"),
            ("agent", "chat"),
            ("tool", "read"),
            ("tool", "execute"),
            ("knowledge", "read"),
            ("knowledge", "query"),
            ("model", "read"),
            ("model", "chat"),
        ],
    },
    {
        "name": "editor",
        "description": "编辑者（可查看、使用、编辑所有资源配置）",
        "is_system": 1,
        "permissions": [
            ("agent", "read"),
            ("agent", "chat"),
            ("agent", "write"),
            ("tool", "read"),
            ("tool", "execute"),
            ("tool", "manage"),
            ("knowledge", "read"),
            ("knowledge", "query"),
            ("knowledge", "write"),
            ("model", "read"),
            ("model", "chat"),
            ("model", "manage"),
        ],
    },
    {
        "name": "admin",
        "description": "完全管理权限",
        "is_system": 1,
        "permissions": [
            ("agent", "read"),
            ("agent", "chat"),
            ("agent", "write"),
            ("agent", "admin"),
            ("tool", "read"),
            ("tool", "execute"),
            ("tool", "manage"),
            ("tool", "admin"),
            ("knowledge", "read"),
            ("knowledge", "query"),
            ("knowledge", "write"),
            ("knowledge", "admin"),
            ("model", "read"),
            ("model", "chat"),
            ("model", "manage"),
            ("model", "admin"),
            ("system", "admin"),
        ],
    },
]


def _ensure_system_role_permissions(
    dao: PermissionDao, role_id: int, expected_permissions: list[tuple[str, str]]
) -> None:
    """Ensure built-in system role has all expected wildcard permissions."""
    current = dao.list_role_permissions(role_id)
    current_keys = {
        (p.get("resource_type"), p.get("action"), p.get("resource_id", "*"))
        for p in current
    }

    for resource_type, action in expected_permissions:
        key = (resource_type, action, "*")
        if key in current_keys:
            continue
        try:
            dao.add_role_permission(
                role_id=role_id,
                resource_type=resource_type,
                action=action,
                resource_id="*",
            )
            logger.info(
                "Added missing permission %s:%s(*) to system role id=%s",
                resource_type,
                action,
                role_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to add missing permission %s:%s to role id=%s: %s",
                resource_type,
                action,
                role_id,
                e,
            )


def ensure_default_roles() -> None:
    """Idempotent: 创建内置角色（如果不存在）并创建默认 admin 用户。"""
    dao = PermissionDao()

    # 1. 创建默认角色
    admin_role_id = None
    for role_def in SEED_ROLES:
        existing = dao.get_role_by_name(role_def["name"])
        if existing:
            logger.debug(f"Seed role already exists: {role_def['name']}")
            # Align existing system role permissions with current seed definition.
            _ensure_system_role_permissions(
                dao,
                existing["id"],
                role_def["permissions"],
            )
            if role_def["name"] == "admin":
                admin_role_id = existing["id"]
            continue
        try:
            role = dao.create_role(
                name=role_def["name"],
                description=role_def["description"],
                is_system=role_def["is_system"],
            )
            for resource_type, action in role_def["permissions"]:
                dao.add_role_permission(
                    role_id=role["id"],
                    resource_type=resource_type,
                    action=action,
                )
            logger.info(f"Seed role created: {role_def['name']}")
            if role_def["name"] == "admin":
                admin_role_id = role["id"]
        except Exception as e:
            logger.exception(f"Failed to create seed role {role_def['name']}: {e}")

    # 2. 创建默认 admin 用户并分配角色
    if admin_role_id:
        try:
            from derisk_app.auth.user_service import UserEntity
            from derisk.storage.metadata.db_manager import db
            from datetime import datetime

            with db.session(commit=True) as s:
                # 检查是否已存在 admin 用户（通过 oauth_id 或 name）
                existing_admin = s.query(UserEntity).filter(
                    or_(
                        UserEntity.oauth_id == "admin",
                        UserEntity.name == "admin",
                    )
                ).first()

                if existing_admin:
                    logger.debug(f"Admin user already exists: {existing_admin.name}")
                    admin_user_id = existing_admin.id
                    # 检查是否已分配 admin 角色
                    user_roles = dao.get_user_roles(admin_user_id)
                    has_admin_role = any(r.get("id") == admin_role_id for r in user_roles)
                    if not has_admin_role:
                        dao.assign_role_to_user(admin_user_id, admin_role_id)
                        logger.info("Assigned admin role to existing admin user")
                else:
                    # 创建新的 admin 用户
                    user = UserEntity(
                        name="admin",
                        fullname="System Administrator",
                        oauth_provider="local",
                        oauth_id="admin",
                        email="admin@derisk.local",
                        role="admin",
                        is_active=1,
                        gmt_create=datetime.utcnow(),
                        gmt_modify=datetime.utcnow(),
                    )
                    s.add(user)
                    s.flush()  # 获取 ID
                    admin_user_id = user.id
                    s.commit()

                    # 分配 admin 角色
                    dao.assign_role_to_user(admin_user_id, admin_role_id)
                    logger.info(f"Created default admin user (ID={admin_user_id}) and assigned admin role")
                    logger.info("=" * 60)
                    logger.info("DEFAULT ADMIN USER CREATED:")
                    logger.info("  Username: admin")
                    logger.info("  OAuth Provider: local (bypass OAuth for local admin)")
                    logger.info(f"  User ID: {admin_user_id}")
                    logger.info("  Note: Use OAuth2 login or set X-User-ID: admin header for testing")
                    logger.info("=" * 60)
        except Exception as e:
            logger.warning(f"Failed to create/assign admin user: {e}")

    # 3. 创建默认权限定义
    _ensure_default_permission_definitions(dao)


def _ensure_default_permission_definitions(dao: PermissionDao) -> None:
    """Idempotent: 创建默认权限定义（如果不存在）。"""
    for perm_def in SEED_PERMISSION_DEFINITIONS:
        # Check if already exists by name
        existing = None
        try:
            all_defs = dao.list_permission_definitions()
            existing = next((d for d in all_defs if d["name"] == perm_def["name"]), None)
        except Exception:
            pass

        if existing:
            logger.debug(f"Seed permission definition already exists: {perm_def['name']}")
            continue

        try:
            dao.create_permission_definition(
                name=perm_def["name"],
                description=perm_def["description"],
                resource_type=perm_def["resource_type"],
                resource_id=perm_def["resource_id"],
                action=perm_def["action"],
                effect="allow",
            )
            logger.info(f"Seed permission definition created: {perm_def['name']}")
        except Exception as e:
            logger.warning(f"Failed to create seed permission definition {perm_def['name']}: {e}")
