# 工具框架统一迁移完成报告

## 概述
本文档记录了 OpenDeRisk 项目中工具框架的完整迁移过程，包括：
1. 从 `core_v2/tools_v2` 迁移到统一框架
2. 从装饰器系统迁移到统一框架
3. 旧版代码清理

## 迁移完成状态

### ✅ 所有迁移任务已完成 (8/8)

| 任务 | 状态 |
|------|------|
| 搜索装饰器定义和使用位置 | ✅ 完成 |
| 迁移装饰器定义的工具 | ✅ 完成 |
| 清理旧版工具代码和装饰器 | ✅ 完成 |
| 迁移 analysis_tools | ✅ 完成 |
| 迁移 mcp_tools | ✅ 完成 |
| 迁移 action_tools | ✅ 完成 |
| 迁移 task_tools | ✅ 完成 |
| 验证迁移后的工具 | ✅ 完成 |

## 统一工具框架结构

```
derisk/agent/tools/
├── __init__.py              # 主导出文件
├── base.py                  # ToolBase 统一基类
├── metadata.py              # ToolMetadata 元数据
├── registry.py              # ToolRegistry 注册表
├── context.py               # ToolContext 执行上下文
├── result.py                # ToolResult 执行结果
├── decorators.py            # 统一装饰器（新增）
├── tool_manager.py          # 工具分组管理（新增）
├── runtime_loader.py        # 运行时加载器（新增）
└── builtin/                 # 内置工具
    ├── __init__.py          # 统一注册
    ├── file_system/         # 文件系统工具
    │   ├── read.py
    │   ├── write.py
    │   ├── edit.py
    │   ├── glob.py
    │   ├── grep.py
    │   ├── list_files.py    # ✅ 新增
    │   └── search.py        # ✅ 新增
    ├── shell/               # Shell 工具
    ├── network/             # 网络工具 ✅ 新增
    │   └── __init__.py
    ├── interaction/         # 交互工具 ✅ 新增
    │   └── __init__.py
    ├── reasoning/           # 推理工具 ✅ 新增
    │   └── __init__.py
    ├── analysis/            # 分析工具 ✅ 新增
    │   └── __init__.py
    ├── mcp/                 # MCP工具 ✅ 新增
    │   └── __init__.py
    ├── action/              # Action工具 ✅ 新增
    │   └── __init__.py
    ├── task/                # Task工具 ✅ 新增
    │   └── __init__.py
    └── agent/               # Agent工具
```

## 已迁移工具统计

### 核心内置工具（22个）

#### 文件系统工具（7个）
- ReadTool ✅
- WriteTool ✅
- EditTool ✅
- GlobTool ✅
- GrepTool ✅
- ListFilesTool ✅ 新增
- SearchTool ✅ 新增

#### 网络工具（2个）
- WebFetchTool ✅ 新增
- WebSearchTool ✅ 新增

#### 交互工具（6个）
- QuestionTool ✅ 新增
- ConfirmTool ✅ 新增
- NotifyTool ✅ 新增
- ProgressTool ✅ 新增
- AskHumanTool ✅ 新增
- FileSelectTool ✅ 新增

#### 推理工具（1个）
- ThinkTool ✅ 新增

#### 分析工具（7个）
- AnalyzeDataTool ✅ 新增
- AnalyzeLogTool ✅ 新增
- AnalyzeCodeTool ✅ 新增
- ShowChartTool ✅ 新增
- ShowTableTool ✅ 新增
- ShowMarkdownTool ✅ 新增
- GenerateReportTool ✅ 新增

#### MCP 工具（1个适配器）
- MCPToolAdapter ✅ 新增
- MCPToolRegistry ✅ 新增

#### Action 工具（1个适配器）
- ActionToolAdapter ✅ 新增

#### Task 工具（1个）
- TaskTool ✅ 新增

### 装饰器兼容层

创建了统一的装饰器系统，支持向后兼容：

```python
from derisk.agent.tools import (
    tool,
    derisk_tool,
    system_tool,
    sandbox_tool,
    shell_tool,
    file_read_tool,
    file_write_tool,
    network_tool,
    agent_tool,
    interaction_tool,
)
```

## 创建的文件列表

### 后端文件

| 文件路径 | 说明 |
|---------|------|
| `derisk/agent/tools/decorators.py` | 统一装饰器兼容层 |
| `derisk/agent/tools/tool_manager.py` | 工具分组管理器 |
| `derisk/agent/tools/runtime_loader.py` | 运行时工具加载器 |
| `derisk/agent/tools/builtin/network/__init__.py` | 网络工具 |
| `derisk/agent/tools/builtin/interaction/__init__.py` | 交互工具 |
| `derisk/agent/tools/builtin/reasoning/__init__.py` | 推理工具 |
| `derisk/agent/tools/builtin/analysis/__init__.py` | 分析工具 |
| `derisk/agent/tools/builtin/mcp/__init__.py` | MCP工具适配器 |
| `derisk/agent/tools/builtin/action/__init__.py` | Action工具适配器 |
| `derisk/agent/tools/builtin/task/__init__.py` | Task工具 |
| `derisk/agent/tools/builtin/file_system/list_files.py` | 列出文件工具 |
| `derisk/agent/tools/builtin/file_system/search.py` | 搜索工具 |

### 前端文件

| 文件路径 | 说明 |
|---------|------|
| `web/src/client/api/tools/management.ts` | 工具管理API客户端 |
| `web/src/app/application/app/components/tab-tools.tsx` | 工具管理页面 |

### 兼容层文件（向后兼容）

| 文件路径 | 说明 |
|---------|------|
| `derisk/core/tools/decorators.py` | 重定向到统一框架 |
| `derisk/agent/resource/tool/base.py` | 重定向到统一框架 |

## 使用方式

### 1. 使用统一工具框架

```python
from derisk.agent.tools import (
    ToolBase,
    ToolMetadata,
    ToolCategory,
    ToolRiskLevel,
    ToolSource,
    tool_registry,
    register_builtin_tools,
)

# 注册所有内置工具
register_builtin_tools(tool_registry)

# 获取工具
tool = tool_registry.get("read")
```

### 2. 使用装饰器

```python
from derisk.agent.tools import tool, system_tool

@tool(description="My custom tool")
def my_tool(input: str) -> str:
    return f"Processed: {input}"

@system_tool
def admin_tool():
    ...
```

### 3. 使用工具管理器

```python
from derisk.agent.tools import tool_manager

# 获取工具分组
groups = tool_manager.get_tool_groups(app_id="my-app", agent_name="my-agent")

# 获取运行时工具
tools = tool_manager.get_runtime_tools(app_id="my-app", agent_name="my-agent")
```

### 4. 前端使用

```typescript
import { getToolGroups, updateToolBinding } from '@/client/api/tools/management';

// 获取工具分组
const { data: groups } = await getToolGroups({
  app_id: 'my-app',
  agent_name: 'my-agent'
});

// 更新绑定
await updateToolBinding({
  app_id: 'my-app',
  agent_name: 'my-agent',
  tool_id: 'webfetch',
  is_bound: true
});
```

## 迁移要点

### 基类差异

| 旧框架 | 统一框架 |
|--------|----------|
| `_define_metadata()` 返回 parameters | `_define_parameters()` 单独定义 |
| `get_openai_spec()` | `to_openai_tool()` |
| `context: Optional[Dict[str, Any]]` | `context: Optional[ToolContext]` |

### 元数据扩展

统一框架增加了以下字段：
- `display_name`: 显示名称
- `category`: 工具分类
- `risk_level`: 风险等级
- `source`: 工具来源
- `tags`: 标签
- `timeout`: 超时时间

## 总结

✅ **工具框架统一迁移已完成**

- **核心工具**: 22个工具已迁移
- **装饰器系统**: 已创建兼容层
- **前端界面**: 工具分组管理页面已完成
- **API 端点**: 7个工具管理API已完成
- **向后兼容**: 旧代码可继续工作

所有工具现已统一到 `derisk.agent.tools` 框架下，支持：
1. ✅ 统一的工具基类和注册表
2. ✅ 工具分组管理（内置默认/可选/自定义/外部）
3. ✅ Agent 级别的工具绑定配置
4. ✅ 运行时工具动态加载
5. ✅ 向后兼容的装饰器系统