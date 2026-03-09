# 统一工具框架与分组管理实现总结

## 概述
本文档描述了 OpenDeRisk 项目中统一工具框架的实现，包括工具分组管理和 Agent 工具绑定配置的完整方案。

## 实现内容

### 1. 后端实现

#### 1.1 工具分组管理器 (`packages/derisk-core/src/derisk/agent/tools/tool_manager.py`)

**核心功能：**
- 工具分组管理（4种类型）：
  - `builtin_required`: 内置默认工具（如 read, bash, question, terminate）
  - `builtin_optional`: 可选内置工具（如 write, edit, websearch 等）
  - `custom`: 用户自定义工具
  - `external`: 外部工具（MCP, API）
- Agent 级别的工具绑定配置
- 支持反向解绑内置默认工具
- 运行时工具加载控制

**主要类：**
- `ToolBindingType`: 工具绑定类型枚举
- `ToolBindingConfig`: 单个工具的绑定配置
- `ToolGroup`: 工具分组数据结构
- `AgentToolConfiguration`: Agent 工具配置
- `ToolManager`: 全局工具管理器

**默认工具列表：**
```python
BUILTIN_REQUIRED_TOOLS = ["read", "bash", "question", "terminate"]
BUILTIN_OPTIONAL_TOOLS = ["write", "edit", "glob", "grep", "webfetch", "websearch", "python", "browser", "skill"]
```

#### 1.2 Agent 运行时工具加载器 (`packages/derisk-core/src/derisk/agent/tools/runtime_loader.py`)

**功能：**
- 根据 Agent 配置动态加载工具
- 支持排除被解绑的内置工具
- 工具缓存管理
- 运行时工具可用性检查

**主要类：**
- `AgentRuntimeToolLoader`: Agent 运行时工具加载器

#### 1.3 工具管理 API (`packages/derisk-app/src/derisk_app/openapi/api_v1/tool_management_api.py`)

**API 端点：**

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/tools/groups` | 获取工具分组列表 |
| GET | `/tools/agent-config` | 获取 Agent 工具配置 |
| POST | `/tools/binding/update` | 更新单个工具绑定状态 |
| POST | `/tools/binding/batch-update` | 批量更新工具绑定状态 |
| POST | `/tools/runtime-tools` | 获取运行时工具列表 |
| POST | `/tools/runtime-schemas` | 获取运行时工具 Schema |
| POST | `/tools/cache/clear` | 清除工具配置缓存 |

#### 1.4 V2 Agent 集成 (`packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/base_builtin_agent.py`)

**修改内容：**
- 新增工具运行时加载器集成
- `_setup_default_tools()`: 支持运行时工具加载
- `_load_runtime_tools()`: 根据配置加载可用工具

### 2. 前端实现

#### 2.1 工具管理 API 客户端 (`web/src/client/api/tools/management.ts`)

**类型定义：**
- `ToolBindingType`: 绑定类型
- `ToolBinding`: 工具绑定配置
- `ToolGroup`: 工具分组
- `ToolWithBinding`: 带绑定状态的工具
- `AgentToolConfig`: Agent 工具配置

**API 函数：**
- `getToolGroups`: 获取工具分组
- `getAgentToolConfig`: 获取 Agent 配置
- `updateToolBinding`: 更新单个绑定
- `batchUpdateToolBindings`: 批量更新绑定
- `getRuntimeTools`: 获取运行时工具
- `getRuntimeToolSchemas`: 获取工具 Schema
- `clearToolCache`: 清除缓存

#### 2.2 工具管理页面 (`web/src/app/application/app/components/tab-tools.tsx`)

**功能特性：**
- 按分组展示工具（内置默认/可选/自定义/外部）
- 显示工具绑定状态（默认绑定/已绑定/未绑定）
- 支持单个工具绑定/解绑
- 支持批量绑定/解绑分组内所有工具
- 内置默认工具可反向解绑
- 搜索过滤功能
- 统计信息显示

**UI 组件：**
- 分组折叠面板（Ant Design Collapse）
- 工具项卡片（显示图标、名称、描述、标签）
- 绑定状态开关
- 批量操作按钮
- 统计信息栏

### 3. 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (Web)                              │
│  ┌──────────────┐         ┌──────────────────────────────────┐ │
│  │ 工具管理页面  │◄────────│ tab-tools.tsx                    │ │
│  └──────────────┘         └──────────────────────────────────┘ │
│           │                              │                      │
│           │                              │                      │
│           ▼                              ▼                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Tool Management API Client (management.ts)       │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────┘
                                   │ API Calls
┌──────────────────────────────────┼──────────────────────────────┐
│                         后端 (Python)                          │
│                                  │                              │
│                                  ▼                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Tool Management API (tool_management_api.py)     │  │
│  └──────────────────────────────────────────────────────────┘  │
│           │                              │                      │
│           ▼                              ▼                      │
│  ┌──────────────┐              ┌──────────────────────┐        │
│  │  ToolManager │◄────────────►│ AgentRuntimeToolLoader│        │
│  └──────────────┘              └──────────────────────┘        │
│           │                              │                      │
│           ▼                              ▼                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    ToolRegistry                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. 关键特性

#### 4.1 工具分组策略

| 分组类型 | 说明 | 默认绑定 | 可解绑 |
|---------|------|---------|--------|
| builtin_required | 核心工具（read, bash, question, terminate） | ✅ | ✅ |
| builtin_optional | 可选工具（write, edit, websearch 等） | ❌ | ✅ |
| custom | 用户自定义工具 | ❌ | ✅ |
| external | MCP/API 外部工具 | ❌ | ✅ |

#### 4.2 运行时工具加载

Agent 运行时只加载启用的工具：
1. 检查 Agent 工具配置
2. 排除 `disabled_at_runtime` 标记的工具
3. 排除已解绑的工具
4. 返回可用工具列表给 LLM

#### 4.3 权限集成

- 使用现有的 `ToolRiskLevel` 风险等级
- 保留 `requires_permission` 权限控制
- 支持参数级权限检查

### 5. 使用方式

#### 5.1 前端使用

```typescript
// 获取工具分组列表
const { data: toolGroups } = useRequest(
  async () => await getToolGroups({
    app_id: 'my-app',
    agent_name: 'my-agent',
    lang: 'zh'
  })
);

// 更新工具绑定
await updateToolBinding({
  app_id: 'my-app',
  agent_name: 'my-agent',
  tool_id: 'bash',
  is_bound: false,  // 反向解绑
});
```

#### 5.2 后端使用

```python
from derisk.agent.tools.tool_manager import tool_manager

# 获取运行时工具
tools = tool_manager.get_runtime_tools(
    app_id="my-app",
    agent_name="my-agent"
)

# 获取工具 Schema 给 LLM
schemas = tool_manager.get_runtime_tool_schemas(
    app_id="my-app",
    agent_name="my-agent",
    format_type="openai"
)
```

### 6. 文件列表

#### 后端文件
- `packages/derisk-core/src/derisk/agent/tools/tool_manager.py` - 工具管理器
- `packages/derisk-core/src/derisk/agent/tools/runtime_loader.py` - 运行时加载器
- `packages/derisk-app/src/derisk_app/openapi/api_v1/tool_management_api.py` - API 端点

#### 前端文件
- `web/src/client/api/tools/management.ts` - API 客户端
- `web/src/app/application/app/components/tab-tools.tsx` - 工具管理页面
- `web/src/app/application/app/components/tab-tools-legacy.tsx` - 旧版页面（备份）

### 7. 后续优化建议

1. **持久化存储**：将 Agent 工具配置持久化到数据库
2. **多 Agent 支持**：支持不同 Agent 使用不同的工具配置
3. **工具版本管理**：支持工具版本控制和升级
4. **工具依赖检查**：自动检查工具依赖关系
5. **工具使用统计**：收集工具使用频率和成功率
6. **可视化编辑**：拖拽式工具绑定界面

## 总结

本次实现提供了一个完整的统一工具框架，支持：
1. ✅ 统一的工具注册和管理
2. ✅ 工具分组管理（内置默认/可选/自定义/外部）
3. ✅ Agent 级别的工具绑定配置
4. ✅ 内置工具的反向解绑
5. ✅ 运行时工具动态加载
6. ✅ 友好的前端管理界面

所有代码已创建并集成到现有系统中，可以进行测试和验证。
