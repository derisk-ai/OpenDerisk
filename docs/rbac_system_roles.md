# RBAC 系统角色说明（当前实现）

本文档说明 OpenDerisk 当前内置（系统）角色的职责边界。  
系统角色由 `permissions/seed.py` 初始化，`is_system=1`，默认不可删除、不可修改、不可重新配置权限。

## 1. 角色清单

当前系统内置 5 个角色：

- `guest`
- `viewer`
- `operator`
- `editor`
- `admin`

## 2. 各角色功能说明

### `guest`（访客）

- 目标：提供最小可用访问能力
- 允许：`model:read`、`model:chat`
- 不允许：智能体、工具、知识库相关权限
- 典型场景：只使用模型对话，不参与平台配置

### `viewer`（只读观察者）

- 目标：全局只读可见
- 允许：`agent/tool/knowledge/model` 的 `read`
- 不允许：对话、执行、编辑、管理
- 典型场景：审计、查看、巡检

### `operator`（操作员）

- 目标：可操作运行态能力，但不改配置
- 允许：
  - `agent:read/chat`
  - `tool:read/execute`
  - `knowledge:read/query`
  - `model:read/chat`
- 不允许：`write/manage/admin`
- 典型场景：值班、日常操作、问题排查

### `editor`（编辑者）

- 目标：可管理业务资源配置，但不具备系统级管理
- 允许：
  - `agent:read/chat/write`
  - `tool:read/execute/manage`
  - `knowledge:read/query/write`
  - `model:read/chat/manage`
- 不允许：`system:admin`（系统级管理）
- 典型场景：应用配置维护、资源管理

### `admin`（管理员）

- 目标：平台完全管理
- 允许：
  - `agent/tool/knowledge/model` 全能力（含 `admin`）
  - `system:admin`
- 典型场景：平台管理员、权限管理员

## 3. 变更约束（本次规则）

为防止误操作，系统角色新增只读保护：

- 前端：系统角色不再展示“配置权限/编辑/删除”操作入口
- 后端：针对系统角色，以下接口写操作会被拒绝（HTTP 400）
  - 更新角色信息
  - 增删角色权限（含资源级权限）
  - 增删角色关联的权限定义

## 4. 推荐使用方式

- 需要个性化权限时，请新建“自定义角色”
- 系统角色建议作为权限基线模板使用，不直接改动
- 生产环境优先采用“用户组 + 角色”分配，减少逐用户授权的维护成本
