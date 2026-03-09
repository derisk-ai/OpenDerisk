# 安妮工具框架改进计划 - 完整开发文档

## 概述

本改进计划完成了统一工具框架与应用编辑工具Tab的完整集成，打通了从工具注册到运行时加载的全流程。

## 已完成的工作

### 1. i18n翻译完善 ✅

**问题**：工具Tab显示i18n key而非翻译文本

**修复**：
- 在 `web/src/locales/zh/common.ts` 添加了工具管理相关翻译
- 在 `web/src/locales/en/common.ts` 添加了英文翻译

**添加的翻译key**：
```typescript
// 工具管理
builder_tool_management: '工具管理'
builder_search_tools_placeholder: '搜索工具名称、描述或标签...'
builder_no_tools: '暂无工具'
builder_tools_total: '共'
builder_tools_bound: '已绑定'
builder_tools_default_bound: '默认绑定'
builder_tools_count: '个工具'
builder_tool_bound_success: '工具绑定成功'
builder_tool_unbound_success: '工具解绑成功'
builder_tool_disassociated: '工具已取消关联'
builder_tool_associated: '工具已关联'
builder_tool_toggle_error: '操作失败'
builder_tool_high_risk: '高风险工具'
builder_tool_requires_permission: '需要权限确认'
builder_builtin_required_tip: '默认绑定工具'
builder_builtin_required_desc: '这些工具是 Agent 默认绑定的核心工具，您可以反向解除绑定，但可能会影响 Agent 的基础功能。'
builder_bind_all: '全部绑定'
builder_unbind_all: '全部解绑'
builder_batch_bound_success: '批量绑定成功'
builder_batch_unbound_success: '批量解绑成功'
builder_batch_toggle_error: '批量操作失败'
builder_expand_all: '展开全部'
builder_collapse_all: '收起全部'
builder_create_local_tool: '创建本地工具'
builder_create_local_tool_desc: '编写自定义工具函数'
builder_tools_associated: '已关联'

// 工具状态
tool_status_default: '默认'
tool_status_bound: '已绑定'
tool_status_unbound: '未绑定'
tool_status_default_bound: '默认绑定'
tool_status_disabled: '已禁用'
tool_permission_required: '需权限'
tool_action_bind: '点击绑定'
tool_action_unbind: '点击解绑'
builder_selected: '已选'
```

### 2. 后端API完善 ✅

**问题**：工具列表为空，后端未正确初始化工具

**修复**：
- 修改了 `packages/derisk-app/src/derisk_app/openapi/api_v1/tool_management_api.py`
- 添加了 `ensure_tools_initialized()` 函数，确保所有API端点在使用前初始化工具

**修改的端点**：
1. `GET /api/tools/groups` - 获取工具分组列表
2. `GET /api/tools/agent-config` - 获取Agent工具配置
3. `POST /api/tools/binding/update` - 更新工具绑定状态
4. `POST /api/tools/binding/batch-update` - 批量更新工具绑定
5. `POST /api/tools/runtime-tools` - 获取运行时工具列表
6. `POST /api/tools/runtime-schemas` - 获取运行时工具Schema
7. `GET /api/tools/list` - 列出所有工具
8. `GET /api/tools/{tool_id}` - 获取工具详情
9. `POST /api/tools/cache/clear` - 清除工具缓存

**关键代码**：
```python
def ensure_tools_initialized():
    """确保工具已初始化"""
    if not hasattr(tool_registry, "_initialized") or not tool_registry._initialized:
        register_builtin_tools()
```

### 3. 工具集成模块 ✅

**新增文件**：`packages/derisk-core/src/derisk/agent/tools/integration.py`

**功能**：
- `ToolIntegrationManager` - 工具集成管理器
- `initialize_tools_on_startup()` - 启动时初始化
- `bind_tools_to_app()` - 绑定工具到应用
- `unbind_tools_from_app()` - 解绑工具
- `get_app_runtime_tools()` - 获取运行时工具

### 4. 统一工具框架架构

**核心组件**：

```
derisk.agent.tools/
├── base.py              # ToolBase基类、ToolCategory、ToolRiskLevel等枚举
├── registry.py          # ToolRegistry全局注册表
├── tool_manager.py      # ToolManager分组管理和绑定配置
├── resource_manager.py  # ToolResourceManager资源管理
├── integration.py       # 工具集成模块（新增）
├── metadata.py          # ToolMetadata元数据定义
├── result.py            # ToolResult执行结果
├── context.py           # ToolContext执行上下文
└── builtin/             # 内置工具
    ├── file_system/     # 文件系统工具
    ├── shell/           # Shell工具
    ├── network/         # 网络工具
    ├── interaction/     # 交互工具
    ├── reasoning/       # 推理工具
    ├── agent/           # Agent工具
    └── sandbox/         # Sandbox工具
```

### 5. 工具分类体系

**16个主分类**：
1. `builtin` - 内置
2. `file_system` - 文件系统
3. `code` - 代码
4. `shell` - Shell
5. `sandbox` - 沙箱
6. `user_interaction` - 用户交互
7. `visualization` - 可视化
8. `network` - 网络
9. `database` - 数据库
10. `api` - API
11. `mcp` - MCP
12. `search` - 搜索
13. `analysis` - 分析
14. `reasoning` - 推理
15. `utility` - 工具
16. `plugin` - 插件
17. `custom` - 自定义

**4个绑定类型**：
1. `builtin_required` - 内置默认（必须）
2. `builtin_optional` - 内置可选
3. `custom` - 自定义
4. `external` - 外部（MCP/API）

### 6. 权限体系

**三层权限**：
1. **工具级权限** - `derisk.core.authorization`
   - AuthorizationEngine - 核心引擎
   - RiskAssessor - 风险评估
   - AuthorizationCache - 权限缓存

2. **Agent级权限** - `derisk.agent.core.agent_info`
   - PermissionRuleset - 规则集
   - PermissionAction - allow/deny/ask

3. **执行时权限** - `derisk.agent.core_v2.permission`
   - PermissionManager - 多Agent权限管理
   - PermissionChecker - 细粒度检查

### 7. 数据流

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Web)                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  TabTools组件                                         │  │
│  │  - 调用 getToolGroups() 获取工具列表                   │  │
│  │  - 调用 updateToolBinding() 绑定/解绑工具              │  │
│  │  - 按分类展示工具 (builtin_required/optional/custom)   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │ API调用
┌─────────────────────────▼───────────────────────────────────┐
│                      后端 (API)                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  tool_management_api.py                               │  │
│  │  - ensure_tools_initialized() 确保工具已初始化         │  │
│  │  - get_tool_groups() 返回分组后的工具列表              │  │
│  │  - update_tool_binding() 更新绑定状态                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   工具框架核心                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ ToolRegistry │  │ ToolManager  │  │ ToolBase         │  │
│  │ - 工具注册    │  │ - 分组管理    │  │ - 工具基类        │  │
│  │ - 工具查找    │  │ - 绑定配置    │  │ - 执行逻辑        │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 8. 工具扩展机制

**方式1：继承ToolBase**
```python
from derisk.agent.tools import ToolBase, ToolMetadata, ToolResult

class MyTool(ToolBase):
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="my_tool",
            display_name="我的工具",
            description="工具描述",
            category=ToolCategory.UTILITY,
        )
    
    async def execute(self, args, context) -> ToolResult:
        return ToolResult(success=True, output="结果")
```

**方式2：使用装饰器**
```python
from derisk.agent.tools import tool

@tool(name="my_tool", category=ToolCategory.UTILITY)
async def my_tool(input: str) -> str:
    return f"processed: {input}"
```

**方式3：自动注册**
```python
from derisk.agent.tools import register_tool, ToolSource

@register_tool(tool_registry, source=ToolSource.USER)
class MyTool(ToolBase):
    ...
```

### 9. 前端组件改进

**TabTools组件** (`web/src/app/application/app/components/tab-tools.tsx`)：

**功能**：
- 按分组展示工具（builtin_required/optional/custom/external）
- 搜索过滤工具
- 单个工具绑定/解绑
- 批量绑定/解绑
- 显示绑定状态统计
- 风险等级标识

**关键特性**：
- 使用 `useRequest` 获取工具数据
- 支持搜索过滤
- 分组折叠/展开
- 绑定状态实时更新

### 10. API端点列表

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/tools/groups` | 获取工具分组列表 |
| GET | `/api/tools/agent-config` | 获取Agent工具配置 |
| POST | `/api/tools/binding/update` | 更新工具绑定状态 |
| POST | `/api/tools/binding/batch-update` | 批量更新绑定 |
| POST | `/api/tools/runtime-tools` | 获取运行时工具列表 |
| POST | `/api/tools/runtime-schemas` | 获取工具Schema |
| GET | `/api/tools/list` | 列出所有工具 |
| GET | `/api/tools/{tool_id}` | 获取工具详情 |
| POST | `/api/tools/cache/clear` | 清除工具缓存 |

## 使用指南

### 启动时初始化工具

```python
from derisk.agent.tools.integration import initialize_tools_on_startup

# 在应用启动时调用
await initialize_tools_on_startup()
```

### 绑定工具到应用

```python
from derisk.agent.tools.integration import bind_tools_to_app

result = await bind_tools_to_app(
    app_id="my_app",
    agent_name="default",
    tool_ids=["read", "write", "bash"]
)
```

### 获取应用运行时工具

```python
from derisk.agent.tools.integration import get_app_runtime_tools

tools = await get_app_runtime_tools(
    app_id="my_app",
    agent_name="default",
    format_type="openai"  # 或 "anthropic"
)
```

### 前端使用

```typescript
import { getToolGroups, updateToolBinding } from '@/client/api/tools/management';

// 获取工具列表
const { data: toolGroups } = useRequest(
  async () => {
    const res = await getToolGroups({
      app_id: appCode,
      agent_name: agentName,
      lang: 'zh',
    });
    return res.data;
  }
);

// 绑定/解绑工具
await updateToolBinding({
  app_id: appCode,
  agent_name: agentName,
  tool_id: toolId,
  is_bound: true,
});
```

## 后续优化建议

1. **数据持久化**：当前工具绑定配置保存在内存中，需要实现数据库存储
   - 添加 `agent_tool_bindings` 表
   - 实现 `save_tool_config()` 和 `load_tool_config()`

2. **权限细化**：
   - 支持基于角色的工具权限
   - 支持细粒度的参数级权限控制

3. **工具市场**：
   - 支持从市场安装第三方工具
   - 工具版本管理

4. **工具调试**：
   - 添加工具测试界面
   - 支持参数预验证

5. **性能优化**：
   - 工具列表缓存策略
   - 懒加载大量工具

## 总结

本次改进计划完成了：
1. ✅ 统一工具框架的设计和实现
2. ✅ 工具注册、绑定、运行时加载的全流程打通
3. ✅ 前端工具Tab的i18n和布局修复
4. ✅ 后端API的完善和初始化机制
5. ✅ 权限体系的整合

工具框架现在已经可以：
- 正确显示工具列表（按分类）
- 支持工具绑定/解绑
- 运行时动态加载工具
- 支持权限验证
- 支持工具扩展
