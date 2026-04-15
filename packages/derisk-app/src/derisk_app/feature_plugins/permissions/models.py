"""ORM models for RBAC permission tables."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from derisk.storage.metadata import Model


# Resource types
RESOURCE_AGENT = "agent"
RESOURCE_TOOL = "tool"
RESOURCE_KNOWLEDGE = "knowledge"
RESOURCE_MODEL = "model"
RESOURCE_SYSTEM = "system"

# Permission actions by resource type
AGENT_ACTIONS = ["read", "chat", "write", "admin"]  # read → chat → write
TOOL_ACTIONS = ["read", "execute", "manage", "admin"]  # read → execute → manage
KNOWLEDGE_ACTIONS = ["read", "query", "write", "admin"]  # read → query → write
MODEL_ACTIONS = ["read", "chat", "manage", "admin"]  # read → chat → manage

# All resource-action mappings
RESOURCE_ACTIONS = {
    RESOURCE_AGENT: AGENT_ACTIONS,
    RESOURCE_TOOL: TOOL_ACTIONS,
    RESOURCE_KNOWLEDGE: KNOWLEDGE_ACTIONS,
    RESOURCE_MODEL: MODEL_ACTIONS,
    RESOURCE_SYSTEM: ["admin"],
}


class RoleEntity(Model):
    """角色表"""

    __tablename__ = "role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, comment="角色名")
    description = Column(Text, nullable=True, comment="角色描述")
    is_system = Column(Integer, default=0, comment="1=内置不可删除")
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False)
    gmt_modify = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RolePermissionEntity(Model):
    """角色-权限表"""

    __tablename__ = "role_permission"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "resource_type", "resource_id", "action", name="uk_role_perm"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, nullable=False, index=True, comment="role.id")
    resource_type = Column(
        String(64),
        nullable=False,
        comment="agent/datasource/knowledge/tool/model/system/*",
    )
    resource_id = Column(String(255), default="*", comment="具体资源ID或*表示全部")
    action = Column(String(32), nullable=False, comment="read/write/execute/admin")
    effect = Column(String(16), default="allow", comment="allow/deny")
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserRoleEntity(Model):
    """用户-角色关联表"""

    __tablename__ = "user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uk_user_role"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="user.id")
    role_id = Column(Integer, nullable=False, index=True, comment="role.id")
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False)


class GroupRoleEntity(Model):
    """用户组-角色关联表"""

    __tablename__ = "group_role"
    __table_args__ = (UniqueConstraint("group_id", "role_id", name="uk_group_role"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, nullable=False, index=True, comment="user_group.id")
    role_id = Column(Integer, nullable=False, index=True, comment="role.id")
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False)


class PermissionDefinitionEntity(Model):
    """权限定义表（独立权限）"""

    __tablename__ = "permission_definition"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False, comment="权限名称")
    description = Column(Text, nullable=True, comment="权限描述")
    resource_type = Column(String(32), nullable=False, comment="资源类型")
    resource_id = Column(String(128), default="*", comment="资源ID，*表示所有资源")
    action = Column(String(32), nullable=False, comment="操作类型")
    effect = Column(String(16), default="allow", comment="allow/deny")
    is_active = Column(Boolean, default=True, comment="是否启用")
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False)
    gmt_modify = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RolePermissionDefEntity(Model):
    """角色-权限定义关联表"""

    __tablename__ = "role_permission_def"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_def_id", name="uk_role_perm_def"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, nullable=False, index=True, comment="role.id")
    permission_def_id = Column(
        Integer, nullable=False, index=True, comment="permission_definition.id"
    )
    gmt_create = Column(DateTime, default=datetime.utcnow, nullable=False)
