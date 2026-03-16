---
name: OAuth2 Login Plugin
overview: 在 设置->系统配置 中增加 OAuth2 插件配置，支持 GitHub 及自定义 OAuth2 服务器。默认关闭，开启后实现基于 OAuth 2.0 协议的用户登录鉴权，与现有逻辑完全向前兼容。
todos:
  - id: schema-oauth2
    content: 在 derisk_core config schema 中新增 OAuth2ProviderConfig、OAuth2Config，扩展 AppConfig
    status: completed
  - id: user-ddl
    content: 扩展 user 表 DDL（oauth_provider、oauth_id、email、avatar）
    status: completed
  - id: auth-module
    content: 新建 derisk_app/auth 模块（OAuth 流程、session 管理、用户服务）
    status: completed
  - id: auth-api
    content: 新建 auth_api.py，实现 login/callback/me/logout 路由，并注册到 api_v1
    status: completed
  - id: config-api-oauth2
    content: 扩展 config_api 支持 oauth2 配置读写
    status: completed
  - id: settings-oauth2-card
    content: 在 settings/config 页 VisualConfig 中新增 OAuth2 插件配置 Card
    status: completed
  - id: login-page
    content: 新建 /login 页面，展示 OAuth 登录按钮
    status: completed
  - id: auth-callback-page
    content: 新建 /auth/callback 页面处理 OAuth 回调
    status: completed
  - id: auth-service
    content: 新建 web services/auth.ts，封装 auth/me、oauth/status 等 API 调用
    status: completed
  - id: layout-auth
    content: 修改 layout.tsx 鉴权逻辑，OAuth 开启时校验登录状态并支持重定向
    status: completed
isProject: false
---

# OAuth2 登录插件配置方案

## 一、架构设计原则

- **协议优先**：采用标准 OAuth 2.0 / OpenID Connect 协议，不绑定任何特定系统
- **可插拔**：OAuth2 为可选开关，默认关闭时行为与当前完全一致
- **用户模块**：建立独立的用户与权限管理模块，登录可接入外部 OAuth2 协议
- **第一版范围**：仅实现用户登录鉴权，不与 LLM key、tool 鉴权关联

## 二、当前状态分析


| 模块     | 现状                                                                                                         |
| ------ | ---------------------------------------------------------------------------------------------------------- |
| 配置存储   | [derisk_core/config](packages/derisk-core/src/derisk_core/config/schema.py) 的 AppConfig，持久化到 `derisk.json` |
| 配置 API | [config_api.py](packages/derisk-app/src/derisk_app/openapi/api_v1/config_api.py) 提供 `/api/v1/config/`*     |
| 设置页面   | [settings/config/page.tsx](web/src/app/settings/config/page.tsx) 含模型、Agent、沙箱、授权、工具等 Tab                   |
| 登录逻辑   | [layout.tsx](web/src/app/layout.tsx) 中 `handleAuth` 为 MOCK，直接设置假用户到 localStorage                           |
| 用户表    | `user` 表存在（id, name, fullname），可扩展用于 OAuth 用户                                                              |


## 三、配置结构设计

在 AppConfig 中新增 `oauth2` 字段（默认关闭）：

```python
# OAuth2 配置结构
oauth2:
  enabled: false                    # 开关，默认 false
  providers:
    - id: "github"                  # 预设：github
      type: "github"                # github | custom
      client_id: ""
      client_secret: ""
      # custom 类型额外需要：
      # authorization_url, token_url, userinfo_url, scope
```

- **GitHub 预设**：固定使用 `https://github.com/login/oauth/authorize` 等标准端点
- **自定义**：支持任意 OAuth2 兼容服务器（authorization_url、token_url、userinfo_url）

## 四、实现模块

### 4.1 后端

**1. 配置 Schema 扩展**

- 文件：[packages/derisk-core/src/derisk_core/config/schema.py](packages/derisk-core/src/derisk_core/config/schema.py)
- 新增 `OAuth2ProviderConfig`、`OAuth2Config`，在 `AppConfig` 中增加 `oauth2: Optional[OAuth2Config] = None`

**2. OAuth2 认证 API**

- 新建 `packages/derisk-app/src/derisk_app/openapi/api_v1/auth_api.py`
- 路由：
  - `GET /api/v1/auth/oauth/login?provider=github`：生成 state，重定向到 OAuth 授权页
  - `GET /api/v1/auth/oauth/callback`：处理回调，用 code 换 token，拉取用户信息
  - `GET /api/v1/auth/me`：返回当前登录用户（校验 session/token）
  - `POST /api/v1/auth/logout`：登出

**3. 用户模块**

- 扩展 `user` 表：`oauth_provider`、`oauth_id`、`email`、`avatar`（通过 DDL 升级）
- 首次 OAuth 登录时创建/更新本地用户
- 新建 `packages/derisk-app/src/derisk_app/auth/`：OAuth 流程、session 管理、用户服务

**4. 配置 API 扩展**

- 在 [config_api.py](packages/derisk-app/src/derisk_app/openapi/api_v1/config_api.py) 中支持读写 `oauth2` 配置
- 或通过现有 `import_config` 的 `extra` 机制透传（需保证 schema 校验）

### 4.2 前端

**1. 设置页 OAuth2 配置卡片**

- 文件：[web/src/app/settings/config/page.tsx](web/src/app/settings/config/page.tsx)
- 在 `VisualConfig` 中新增 Card「OAuth2 登录配置」
- 内容：Switch（enabled）、Provider 列表（GitHub + 自定义）、表单（client_id、client_secret 等）

**2. 登录页**

- 新建 `web/src/app/login/page.tsx`
- 根据配置展示「使用 GitHub 登录」「使用 XXX 登录」等按钮
- 点击后跳转到 `/api/v1/auth/oauth/login?provider=xxx`

**3. 回调页**

- 新建 `web/src/app/auth/callback/page.tsx`
- 接收后端重定向，从 URL 获取 token/session 信息并写入 localStorage，再跳转到首页

**4. Layout 鉴权逻辑**

- 文件：[web/src/app/layout.tsx](web/src/app/layout.tsx)
- 调用 `GET /api/v1/auth/oauth/status` 或 `GET /api/v1/auth/me` 判断是否启用 OAuth 及是否已登录
- 当 OAuth 关闭：保持现有 MOCK 逻辑（或直接视为已登录）
- 当 OAuth 开启且未登录：重定向到 `/login`

## 五、数据流示意

```mermaid
flowchart TB
    subgraph Config [配置层]
        A[settings/config]
        A --> B[oauth2.enabled=false]
        A --> C[oauth2.providers]
    end

    subgraph AuthFlow [OAuth 开启时]
        D[用户访问] --> E{已登录?}
        E -->|否| F[重定向 /login]
        F --> G[点击 GitHub 登录]
        G --> H[/auth/oauth/login]
        H --> I[OAuth 授权页]
        I --> J[/auth/oauth/callback]
        J --> K[创建/更新用户]
        K --> L[写入 Session]
        L --> M[重定向首页]
        E -->|是| N[正常访问]
    end

    subgraph Compat [OAuth 关闭时]
        O[用户访问] --> P[沿用现有逻辑]
        P --> Q[无登录校验]
    end

    B -->|false| Compat
    B -->|true| AuthFlow
```



## 六、关键文件清单


| 操作  | 文件路径                                                                      |
| --- | ------------------------------------------------------------------------- |
| 修改  | `packages/derisk-core/src/derisk_core/config/schema.py`                   |
| 新建  | `packages/derisk-app/src/derisk_app/auth/`（oauth 流程、用户服务）                 |
| 新建  | `packages/derisk-app/src/derisk_app/openapi/api_v1/auth_api.py`           |
| 修改  | `packages/derisk-app/src/derisk_app/openapi/api_v1/api_v1.py`（注册 auth 路由） |
| 修改  | `web/src/app/settings/config/page.tsx`                                    |
| 新建  | `web/src/app/login/page.tsx`                                              |
| 新建  | `web/src/app/auth/callback/page.tsx`                                      |
| 修改  | `web/src/app/layout.tsx`                                                  |
| 新建  | `web/src/services/auth.ts`                                                |
| 修改  | `assets/schema/`（user 表 DDL 升级）                                           |


## 七、向后兼容与安全

- **默认关闭**：`oauth2.enabled` 默认为 `false`，不改变现有行为
- **Session 安全**：使用 HttpOnly Cookie 或 JWT，避免 token 暴露在前端
- **State 防 CSRF**：OAuth 流程中校验 state 参数
- **Secret 存储**：client_secret 仅存于服务端配置，不暴露给前端

## 八、后续扩展（本版不做）

- 与 LLM key、tool 鉴权的关联
- 权限/角色管理（RBAC）
- 多 OAuth 提供商同时启用时的策略选择

