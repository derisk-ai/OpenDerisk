# OpenDerisk 可插拔用户权限架构设计

## Context

当前 OpenDerisk 没有真正的权限控制：`get_user_from_headers()` 始终返回 mock admin 用户，所有 API 无认证无鉴权。项目已有 OAuth2 登录系统和 user_groups 数据模型，但未形成完整的权限闭环。需要设计一套**默认关闭、开启即生效**的可插拔 RBAC 权限架构。

### 现状分析

| 组件 | 现状 | 问题 |
|------|------|------|
| `get_user_from_headers()` | 始终返回 `{user_id: "001", role: "admin"}` | 无真实认证 |
| OAuth2 登录 | 已实现 GitHub/自定义 Provider + JWT session | 仅控制登录，不控制权限 |
| UserEntity | id/name/email/role(normal/admin) | role 字段未实际使用 |
| user_groups 插件 | 已有组+成员数据模型 | 无权限关联逻辑 |
| API 端点 | 无 middleware 校验 session | 任何人可调用任何 API |

---

## 设计原则

1. **默认关闭** -- 不配置时行为与现在完全一致（mock 用户、无登录要求）
2. **开关即生效** -- 通过 `feature_plugins.permissions.enabled = true` 启用，需重启
3. **最小侵入** -- 利用 FastAPI `Depends()` 注入，业务代码改动最小化
4. **复用现有基础设施** -- feature_plugins 机制、BaseDao、UserEntity、user_groups 表
5. **渐进式采纳** -- 认证(authn)和授权(authz)分层，可逐步给端点加权限控制

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI Endpoint                   │
│   Depends(get_user_from_headers)  -- 认证(Tier 1)    │
│   Depends(require_permission(...)) -- 授权(Tier 2)   │
└──────────────┬──────────────────────┬────────────────┘
               │                      │
      ┌────────▼────────┐    ┌────────▼────────┐
      │ permissions OFF  │    │ permissions ON   │
      │ → mock admin     │    │ → validate JWT   │
      │ → allow all      │    │ → load permissions│
      └─────────────────┘    │ → check RBAC      │
                              └─────────────────┘
                                       │
                              ┌────────▼────────┐
                              │ PermissionService│
                              │ (60s in-mem cache)│
                              └────────┬────────┘
                                       │
            ┌──────────┬───────────┬───┴────┐
            │user_role │group_role │role_perm│
            └──────────┴───────────┴────────┘
```

### 三层控制模型

| 层级 | 机制 | 侵入性 | 适用场景 |
|------|------|--------|---------|
| **Tier 1 (认证)** | `get_user_from_headers()` 内部条件分支 | **零** -- 已有端点无需改动 | 所有已使用该依赖的端点自动生效 |
| **Tier 2 (授权)** | `require_permission("resource", "action")` | **低** -- 替换一个 Depends | 需要细粒度权限控制的端点 |
| **Tier 3 (资源级)** | `resource_id` 参数检查 | **中** -- 端点内加判断 | 需要控制到具体资源实例 |

---

## 二、数据模型

### 新增 4 张表（在 permissions 插件内定义）

```sql
-- 角色表
CREATE TABLE role (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        VARCHAR(64) UNIQUE NOT NULL,   -- "viewer", "editor", "admin"
    description TEXT,
    is_system   INTEGER DEFAULT 0,             -- 1=内置不可删除
    gmt_create  DATETIME,
    gmt_modify  DATETIME
);

-- 角色-权限表（核心：定义角色对资源的操作权限）
CREATE TABLE role_permission (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id       INTEGER NOT NULL,             -- FK role.id
    resource_type VARCHAR(64) NOT NULL,         -- "agent","datasource","knowledge","tool","model","system","*"
    resource_id   VARCHAR(255) DEFAULT '*',     -- 具体资源 ID 或 "*" 表示全部
    action        VARCHAR(32) NOT NULL,         -- "read","write","execute","admin"
    effect        VARCHAR(16) DEFAULT 'allow',  -- "allow" / "deny"
    gmt_create    DATETIME,
    UNIQUE(role_id, resource_type, resource_id, action)
);

-- 用户-角色关联表（直接分配）
CREATE TABLE user_role (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,                -- FK user.id
    role_id    INTEGER NOT NULL,                -- FK role.id
    gmt_create DATETIME,
    UNIQUE(user_id, role_id)
);

-- 用户组-角色关联表（通过组继承，复用已有 user_group 表）
CREATE TABLE group_role (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL,                -- FK user_group.id
    role_id    INTEGER NOT NULL,                -- FK role.id
    gmt_create DATETIME,
    UNIQUE(group_id, role_id)
);
```

### ER 关系

```
User ──1:N── user_role ──N:1── Role ──1:N── role_permission
  │                              ▲
  │                              │
  └─1:N── user_group_member ──N:1── user_group ──1:N── group_role ──N:1─┘
```

### 权限生效路径

```
用户最终权限 = 直接角色权限(user_role) ∪ 用户组角色权限(group_role)
```

取并集，任一路径有权限即放行。

### 内置种子角色

| 角色 | is_system | resource_type | action | 说明 |
|------|-----------|--------------|--------|------|
| viewer | 1 | * | read | 只读访问所有资源 |
| editor | 1 | * | read, write, execute | 可编辑和执行 |
| admin | 1 | * | read, write, execute, admin | 完全管理权限 |

### 资源类型与操作定义

| resource_type | 说明 | 支持的 action |
|--------------|------|-------------|
| `agent` | Agent 应用 | read, write, execute, admin |
| `datasource` | 数据源 | read, write, execute, admin |
| `knowledge` | 知识库 | read, write, execute, admin |
| `tool` | 工具 | read, write, execute, admin |
| `model` | LLM 模型 | read, write, admin |
| `system` | 系统设置 | read, admin |
| `*` | 通配符（所有资源） | read, write, execute, admin |

---

## 三、后端实现

### 3.1 新增文件结构

```
packages/derisk-app/src/derisk_app/feature_plugins/permissions/
├── __init__.py
├── models.py       # RoleEntity, RolePermissionEntity, UserRoleEntity, GroupRoleEntity
├── dao.py          # PermissionDao - 数据访问层
├── service.py      # PermissionService - 权限聚合 + 内存缓存
├── checker.py      # require_permission() FastAPI 依赖工厂
├── api.py          # 管理 API（角色/权限/用户角色/组角色 CRUD）
└── seed.py         # 内置角色种子数据初始化
```

### 3.2 核心修改：`get_user_from_headers()` 条件分支

**文件**: `packages/derisk-serve/src/derisk_serve/utils/auth.py`

**改动思路**：在现有函数内添加一个运行时分支，检查 permissions 插件是否启用。关闭时行为完全不变，开启时验证 JWT session 并加载权限。

```python
from typing import Dict, List, Optional

from fastapi import Header, HTTPException, Request

from derisk._private.pydantic import BaseModel


class UserRequest(BaseModel):
    user_id: Optional[str] = None
    user_no: Optional[str] = None
    real_name: Optional[str] = None
    user_name: Optional[str] = None
    user_channel: Optional[str] = None
    role: Optional[str] = "normal"
    nick_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    nick_name_like: Optional[str] = None
    # ── 新增字段（插件关闭时为 None，表示不做权限检查）──
    permissions: Optional[Dict[str, List[str]]] = None  # resource_type -> [actions]
    roles: Optional[List[str]] = None                    # 用户拥有的角色名列表


def _is_permissions_enabled() -> bool:
    """检查 permissions 插件是否启用（运行时读取配置，有缓存）"""
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
    user_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> UserRequest:
    """统一用户解析入口。

    permissions OFF: 返回 mock admin（现有行为，完全不变）
    permissions ON:  验证 JWT session → 加载 RBAC 权限
    """
    if not _is_permissions_enabled():
        # ===== 插件关闭：保持现有行为 =====
        if user_id:
            return UserRequest(
                user_id=user_id, role="admin",
                nick_name=user_id, real_name=user_id,
            )
        return UserRequest(
            user_id="001", role="admin",
            nick_name="derisk", real_name="derisk",
        )

    # ===== 插件开启：验证 JWT session =====
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
    perms = PermissionService().get_user_permissions(user_data["id"])

    return UserRequest(
        user_id=str(user_data.get("id", "")),
        user_no=str(user_data.get("id", "")),
        real_name=user_data.get("name", ""),
        nick_name=user_data.get("name", ""),
        email=user_data.get("email", ""),
        avatar_url=user_data.get("avatar", ""),
        role=user_data.get("role", "normal"),
        permissions=perms.permissions_map,
        roles=perms.role_names,
    )
```

**关键点**：函数签名新增 `request` 和 `authorization` 参数（FastAPI 自动注入），现有调用方 `Depends(get_user_from_headers)` 无需任何修改。

### 3.3 权限检查依赖工厂

**文件**: `permissions/checker.py`

```python
from fastapi import Depends, HTTPException

from derisk_serve.utils.auth import UserRequest, get_user_from_headers


def require_permission(resource_type: str, action: str, resource_id: str = "*"):
    """FastAPI 依赖工厂 - 检查用户是否拥有指定权限。

    使用方式:
        @router.post("/agents")
        async def create_agent(
            user: UserRequest = Depends(require_permission("agent", "write")),
        ):
            ...

    插件关闭时：直接放行（user.permissions 为 None）
    插件开启时：检查 RBAC，无权限返回 403
    """
    def dependency(user: UserRequest = Depends(get_user_from_headers)) -> UserRequest:
        # 插件关闭 → permissions 为 None → 不做检查
        if user.permissions is None:
            return user

        # superadmin 角色绕过所有权限检查
        if "superadmin" in (user.roles or []):
            return user

        # 检查权限：先查具体资源类型，再查通配符
        allowed = user.permissions.get(resource_type, [])
        wildcard = user.permissions.get("*", [])

        if (action in allowed or "admin" in allowed or
                action in wildcard or "admin" in wildcard):
            return user

        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: {action} on {resource_type}",
        )

    return dependency


def require_admin():
    """快捷方式：要求 system admin 权限"""
    return require_permission("system", "admin")
```

### 3.4 PermissionService（带内存缓存）

**文件**: `permissions/service.py`

```python
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


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

    def get_user_permissions(self, user_id: int) -> UserPermissions:
        """加载用户的全部有效权限（直接角色 + 用户组角色），60s 缓存"""
        cached = self._cache.get(user_id)
        if cached and (time.time() - cached.loaded_at) < self._cache_ttl:
            return cached

        from .dao import PermissionDao
        dao = PermissionDao()

        # 1. 获取直接角色
        direct_roles = dao.get_user_roles(user_id)
        # 2. 获取通过用户组继承的角色
        group_roles = dao.get_user_group_roles(user_id)

        all_roles = {r["id"]: r["name"] for r in direct_roles + group_roles}
        role_ids = list(all_roles.keys())
        role_names = list(all_roles.values())

        # 3. 聚合所有角色的权限
        permissions_map: Dict[str, List[str]] = {}
        if role_ids:
            perms = dao.get_permissions_for_roles(role_ids)
            for p in perms:
                if p["effect"] == "allow":
                    rt = p["resource_type"]
                    act = p["action"]
                    permissions_map.setdefault(rt, [])
                    if act not in permissions_map[rt]:
                        permissions_map[rt].append(act)

        result = UserPermissions(
            user_id=user_id,
            role_names=role_names,
            permissions_map=permissions_map,
        )
        self._cache[user_id] = result
        return result

    def invalidate_cache(self, user_id: Optional[int] = None):
        """清除缓存。管理 API 修改角色/权限后调用。"""
        if user_id is not None:
            self._cache.pop(user_id, None)
        else:
            self._cache.clear()
```

### 3.5 种子数据初始化

**文件**: `permissions/seed.py`

```python
"""首次启动时创建内置角色和权限。"""

import logging
from .dao import PermissionDao

logger = logging.getLogger(__name__)

SEED_ROLES = [
    {
        "name": "viewer",
        "description": "Read-only access to all resources",
        "is_system": 1,
        "permissions": [("*", "read")],
    },
    {
        "name": "editor",
        "description": "Read, write, and execute on all resources",
        "is_system": 1,
        "permissions": [("*", "read"), ("*", "write"), ("*", "execute")],
    },
    {
        "name": "admin",
        "description": "Full access including administration",
        "is_system": 1,
        "permissions": [("*", "read"), ("*", "write"), ("*", "execute"), ("*", "admin")],
    },
]


def ensure_default_roles():
    """Idempotent: create seed roles if they don't exist."""
    dao = PermissionDao()
    for role_def in SEED_ROLES:
        existing = dao.get_role_by_name(role_def["name"])
        if existing:
            continue
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
```

### 3.6 管理 API

**文件**: `permissions/api.py`

```
GET    /api/v1/permissions/roles                            列出所有角色
POST   /api/v1/permissions/roles                            创建角色
PUT    /api/v1/permissions/roles/{role_id}                  更新角色
DELETE /api/v1/permissions/roles/{role_id}                  删除角色（is_system=1 禁止删除）
GET    /api/v1/permissions/roles/{role_id}/permissions      查看角色权限列表
POST   /api/v1/permissions/roles/{role_id}/permissions      添加权限到角色
DELETE /api/v1/permissions/roles/{role_id}/permissions/{id}  移除角色权限
GET    /api/v1/permissions/users/{user_id}/roles            查看用户角色
POST   /api/v1/permissions/users/{user_id}/roles            分配角色给用户
DELETE /api/v1/permissions/users/{user_id}/roles/{role_id}  移除用户角色
GET    /api/v1/permissions/groups/{group_id}/roles          查看用户组角色
POST   /api/v1/permissions/groups/{group_id}/roles          分配角色给用户组
DELETE /api/v1/permissions/groups/{group_id}/roles/{role_id} 移除用户组角色
GET    /api/v1/permissions/me                               获取当前用户的有效权限
```

所有管理端点使用 `Depends(require_permission("system", "admin"))` 保护，`/me` 仅需认证。

### 3.7 插件注册

**修改 `feature_plugins/catalog.py`** -- 在 `_MANIFESTS` 中添加：

```python
"permissions": FeaturePluginManifest(
    id="permissions",
    title="RBAC 权限管理",
    description="基于角色的访问控制，支持用户/用户组-角色-权限模型。启用后需配合 OAuth2 登录使用。",
    category="access_control",
    requires_restart=True,
    settings_schema={
        "type": "object",
        "properties": {
            "default_policy": {
                "type": "string",
                "enum": ["allow_authenticated", "deny_all"],
                "default": "allow_authenticated",
            },
            "superadmin_users": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Login names that bypass all permission checks",
            },
        },
    },
    suggest_oauth2_admin=True,
),
```

**修改 `feature_plugins/bootstrap.py`** -- 添加注册逻辑：

```python
if _enabled("permissions"):
    from derisk_app.feature_plugins.permissions.api import router as permissions_router
    app.include_router(permissions_router, prefix="/api/v1")
    logger.info("Feature plugin mounted: permissions at /api/v1/permissions")

    from derisk_app.feature_plugins.permissions.seed import ensure_default_roles
    ensure_default_roles()
```

### 3.8 配置方式

在 `~/.derisk/derisk.json` 的 `feature_plugins` 中添加：

```json
{
  "feature_plugins": {
    "permissions": {
      "enabled": true,
      "settings": {
        "default_policy": "allow_authenticated",
        "superadmin_users": ["admin_login_name"]
      }
    }
  }
}
```

无需修改 `FeaturePluginEntry` schema -- 现有 `settings: Dict[str, Any]` 字段已支持任意配置。

---

## 四、前端实现

### 4.1 权限 Hook

**新文件**: `web/src/hooks/use-permissions.ts`

```typescript
import { STORAGE_USERINFO_KEY } from '@/utils/constants';

interface UserInfo {
  permissions?: Record<string, string[]>;  // resource_type -> [actions]
  roles?: string[];
  [key: string]: any;
}

function getUserInfo(): UserInfo | null {
  try {
    const raw = localStorage.getItem(STORAGE_USERINFO_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function usePermissions() {
  const userInfo = getUserInfo();

  const hasPermission = (resource: string, action: string): boolean => {
    // 插件关闭时 permissions 不存在 → 允许所有
    if (!userInfo?.permissions) return true;
    const actions = userInfo.permissions[resource] || userInfo.permissions['*'] || [];
    return actions.includes(action) || actions.includes('admin');
  };

  const isAdmin = (): boolean => {
    return (userInfo?.roles || []).some(r => ['admin', 'superadmin'].includes(r));
  };

  return { hasPermission, isAdmin, permissions: userInfo?.permissions, roles: userInfo?.roles };
}
```

### 4.2 权限守卫组件

**新文件**: `web/src/components/permission-guard.tsx`

```tsx
import React from 'react';
import { usePermissions } from '@/hooks/use-permissions';

interface Props {
  resource: string;
  action: string;
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

export function PermissionGuard({ resource, action, fallback, children }: Props) {
  const { hasPermission } = usePermissions();
  if (!hasPermission(resource, action)) {
    return <>{fallback ?? null}</>;
  }
  return <>{children}</>;
}
```

**使用示例**：

```tsx
import { PermissionGuard } from '@/components/permission-guard';

// 隐藏无权限的按钮
<PermissionGuard resource="agent" action="write">
  <Button onClick={createAgent}>Create Agent</Button>
</PermissionGuard>

// 页面级权限控制
const { hasPermission } = usePermissions();
if (!hasPermission("system", "admin")) {
  return <Result status="403" title="No Permission" />;
}
```

### 4.3 layout.tsx 增强

在 `checkAuth()` 中增加权限获取逻辑：

```typescript
// OAuth 启用且已认证时
const me = await authService.getMe();
// 新增：获取用户权限
try {
  const permsResp = await GET('/api/v1/permissions/me');
  if (permsResp.data?.success) {
    user.permissions = permsResp.data.data.permissions;
    user.roles = permsResp.data.data.roles;
  }
} catch {
  // permissions 插件未启用时接口不存在，忽略
}

// OAuth 关闭时存入全量 admin 权限
const user = {
  user_channel: "derisk",
  user_no: "001",
  nick_name: "derisk",
  permissions: { "*": ["read", "write", "execute", "admin"] },
  roles: ["admin"],
};
```

### 4.4 Axios 响应拦截器

**修改**: `web/src/client/api/index.ts`

```typescript
ins.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      // Session 过期 → 跳转登录
      const path = window.location.pathname;
      if (!path.startsWith('/login') && !path.startsWith('/auth/callback')) {
        window.location.href = '/login';
      }
    }
    // 403 由各页面自行处理（Toast 或 Result 组件）
    return Promise.reject(error);
  },
);
```

---

## 五、实现分期

### Phase 1：后端权限核心（不破坏任何现有功能）

| 步骤 | 文件 | 说明 |
|------|------|------|
| 1 | `permissions/models.py` | 4 张表的 ORM 实体 |
| 2 | `permissions/dao.py` | 数据访问层（BaseDao 风格） |
| 3 | `permissions/service.py` | 权限聚合逻辑 + 60s 内存缓存 |
| 4 | `permissions/seed.py` | 内置角色种子数据 |
| 5 | `permissions/checker.py` | `require_permission()` 依赖工厂 |
| 6 | `catalog.py` + `bootstrap.py` | 插件注册 |

### Phase 2：认证网关

| 步骤 | 文件 | 说明 |
|------|------|------|
| 7 | `auth.py` | 修改 `get_user_from_headers()`，添加条件分支 |
| 8 | `auth.py` | `UserRequest` 扩展 `permissions` + `roles` 字段 |

### Phase 3：管理 API

| 步骤 | 文件 | 说明 |
|------|------|------|
| 9 | `permissions/api.py` | 角色/权限 CRUD + `/me` 端点 |

### Phase 4：前端

| 步骤 | 文件 | 说明 |
|------|------|------|
| 10 | `hooks/use-permissions.ts` | 权限 Hook |
| 11 | `components/permission-guard.tsx` | 权限守卫组件 |
| 12 | `layout.tsx` | 获取并缓存用户权限 |
| 13 | `client/api/index.ts` | 401/403 响应拦截 |

### Phase 5：渐进式端点接入

按优先级逐步将关键端点的 `Depends(get_user_from_headers)` 替换为 `Depends(require_permission(...))`:

1. 系统设置/配置端点 → `require_permission("system", "admin")`
2. Agent CRUD → `require_permission("agent", "write")`
3. 数据源管理 → `require_permission("datasource", "write")`
4. 知识库管理 → `require_permission("knowledge", "write")`
5. 模型管理 → `require_permission("model", "admin")`

---

## 六、设计决策说明

### Q: 为什么修改 `get_user_from_headers()` 而不是用 Middleware？

Middleware 需要知道每个路由的权限要求，会将路由和授权耦合。依赖注入方式是 FastAPI 惯用模式，权限要求与端点声明在一起，可组合可测试。修改 `get_user_from_headers()` 使用运行时分支，关闭时代码路径与现在完全相同。

### Q: 为什么不在 Middleware 层做统一 Session 验证？

Middleware 会对所有请求生效（包括 /login、/health、静态文件），需要维护白名单。依赖注入方式只在声明了依赖的端点上生效，更精确。如果未来需要全局认证，可以作为增强在 Middleware 层添加。

### Q: 为什么用进程内存缓存而不是 Redis？

权限数据变更频率低，60s TTL 的进程内存缓存在单节点部署（当前默认模式）下足够。分布式部署场景可升级为 Redis 缓存，只需修改 PermissionService 的缓存实现。

### Q: 如何处理已有的 `role` 字段（UserEntity.role）？

保持兼容。`UserEntity.role` (normal/admin) 继续作为用户的基础角色标识。RBAC 系统通过 `user_role` 表提供更细粒度的角色分配，两套机制并存，不冲突。

---

## 七、验证方式

| 场景 | 预期行为 |
|------|---------|
| 插件关闭（默认） | 所有 API 行为不变，mock admin 用户 |
| 插件开启 + 未登录 | API 返回 401 Unauthorized |
| 插件开启 + viewer 角色 | GET 请求正常，POST/PUT/DELETE 返回 403 |
| 插件开启 + editor 角色 | 读写执行正常，管理操作返回 403 |
| 插件开启 + admin 角色 | 所有操作正常 |
| 前端 - 插件关闭 | 所有按钮/菜单正常显示 |
| 前端 - viewer 角色 | 写入/删除按钮隐藏，403 Toast 提示 |
| 关闭插件后重启 | 行为完全恢复到修改前 |

---

## 八、关键文件清单

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `packages/derisk-serve/src/derisk_serve/utils/auth.py` | **修改** | 核心：条件认证 + UserRequest 扩展 |
| `packages/derisk-app/src/derisk_app/feature_plugins/catalog.py` | **修改** | 添加 permissions manifest |
| `packages/derisk-app/src/derisk_app/feature_plugins/bootstrap.py` | **修改** | 注册 permissions 路由 + 种子数据 |
| `packages/derisk-app/src/derisk_app/feature_plugins/permissions/__init__.py` | **新增** | 模块入口 |
| `packages/derisk-app/src/derisk_app/feature_plugins/permissions/models.py` | **新增** | 4 张表 ORM 实体 |
| `packages/derisk-app/src/derisk_app/feature_plugins/permissions/dao.py` | **新增** | 数据访问层 |
| `packages/derisk-app/src/derisk_app/feature_plugins/permissions/service.py` | **新增** | 权限聚合 + 缓存 |
| `packages/derisk-app/src/derisk_app/feature_plugins/permissions/checker.py` | **新增** | require_permission() 依赖 |
| `packages/derisk-app/src/derisk_app/feature_plugins/permissions/api.py` | **新增** | 管理 API |
| `packages/derisk-app/src/derisk_app/feature_plugins/permissions/seed.py` | **新增** | 种子数据 |
| `web/src/hooks/use-permissions.ts` | **新增** | 前端权限 Hook |
| `web/src/components/permission-guard.tsx` | **新增** | 前端权限守卫 |
| `web/src/app/layout.tsx` | **修改** | 获取并缓存用户权限 |
| `web/src/client/api/index.ts` | **修改** | 401/403 拦截器 |
