# Core_v2 Agent 完整集成方案

## 一、版本切换机制

### 1. 应用编辑页面

在应用编辑页面 (tab-overview.tsx) 中添加了 Agent Version 选择器：

```
┌─────────────────────────────────────────────────────┐
│ Agent Config                                        │
├─────────────────────────────────────────────────────┤
│ Agent Type: [选择 Agent 类型]                       │
│                                                     │
│ Agent Version:                                      │
│ ┌─────────────────┐ ┌─────────────────┐            │
│ │ ⚡ V1 Classic   │ │ 🚀 V2 Core_v2   │            │
│ │   PDCA Agent    │ │  Canvas+Progress│            │
│ └─────────────────┘ └─────────────────┘            │
│                                                     │
│ LLM Strategy: [选择 LLM 策略]                       │
└─────────────────────────────────────────────────────┘
```

### 2. 自动数据流

```
应用编辑页面设置 agent_version
        ↓
保存到 GptsApp.agent_version
        ↓
前端读取 appInfo.agent_version
        ↓
useChat hook 根据 agent_version 切换 API
        ↓
V1 → /api/v1/chat/completions
V2 → /api/v2/chat
```

## 二、修改的文件

### 后端
1. `derisk_app/app.py` - 注册 Core_v2 路由和组件
2. `schema_app.py` - 添加 agent_version 字段

### 前端
1. `tab-overview.tsx` - 添加版本选择器 UI
2. `use-chat.ts` - 支持 V1/V2 API 切换
3. `chat-content.tsx` - 传递 agent_version

## 三、服务启动

V1/V2 共存，使用原有启动方式：

```bash
python -m derisk_app.derisk_server -c configs/derisk-siliconflow.toml
```

## 四、验证步骤

1. 启动服务
2. 打开应用编辑页面
3. 选择 Agent Version (V1 或 V2)
4. 保存应用
5. 开始对话，自动使用对应版本的 API

## 五、特性对比

| 特性 | V1 Classic | V2 Core_v2 |
|-----|-----------|------------|
| API | /api/v1/chat/completions | /api/v2/chat |
| 会话管理 | 隐式 | Session API |
| 可视化 | VisConverter | Canvas + Progress |
| 工具 | 原有工具 | V2 Tool System |
| 权限 | 原有权限 | PermissionRuleset |

## 六、API 端点

服务启动后可用：

**V1 API:**
- POST /api/v1/chat/completions

**V2 API:**
- POST /api/v2/session
- POST /api/v2/chat
- GET /api/v2/session/:id
- DELETE /api/v2/session/:id
- GET /api/v2/status