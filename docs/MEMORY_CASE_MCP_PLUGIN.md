# 案例记忆 MCP 可插拔接入设计

## 概述

案例记忆（Case Memory）是一个跨会话的知识积累系统，Agent 在故障排查过程中可调用记忆工具搜索相似历史案例，并在任务完成后将新案例写入知识库。本文档描述如何通过标准 MCP ToolPack 机制，让 BAIZE 等任何 Agent 以可插拔方式接入案例记忆。

## 架构

```
┌─────────────────────────────────────────────────┐
│  Agent (BAIZE / react_reasoning / 任意 Agent)    │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │  ReAct Loop                              │    │
│  │  Think → Act → Observe → ...            │    │
│  │       ↓ tool_call                        │    │
│  │  ┌─────────────────────────────────┐    │    │
│  │  │  MemoryCaseToolPack              │    │    │
│  │  │  ├─ memory_case_search           │    │    │
│  │  │  ├─ memory_case_upsert           │    │    │
│  │  │  ├─ memory_case_feedback         │    │    │
│  │  │  └─ memory_case_render           │    │    │
│  │  └──────────┬──────────────────────┘    │    │
│  └─────────────┼───────────────────────────┘    │
└────────────────┼────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│  MemoryCasePluginService (内置 MCP 服务)         │
│                                                  │
│  ┌──────────────┐  ┌────────────────────────┐   │
│  │ MemoryCaseDao │  │ ChromaDB VectorIndex   │   │
│  │ (SQLite/DB)   │  │ (语义搜索)              │   │
│  └──────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## 设计理念

| 维度 | 说明 |
|------|------|
| 耦合方式 | 标准 ToolPack，Agent 自主调用，无 monkey-patch |
| 接入方式 | 内置 MCP 可视化选择，用户在 UI 中按需载入 |
| 工具可见性 | Agent 在工具列表中看到工具，自主决策调用时机 |
| 召回时机 | Agent 在 ReAct 循环中按需调用 `memory_case_search` |
| 回写时机 | Agent 主动调用 `memory_case_upsert` |
| 扩展性 | 任意 Agent 通过 UI 选择接入，无需代码改动 |

## 工具列表

### memory_case_search

按范围和查询搜索相似案例。

```json
{
  "scope": {
    "tenant_id": "xxx",
    "team_id": "xxx",
    "app_code": "my-app",
    "environment": "production"
  },
  "query": "Pod CrashLoopBackOff OOMKilled",
  "top_k": 5
}
```

返回：匹配的 `CandidateCase` 列表，按置信度排序。

### memory_case_upsert

创建或更新案例。

```json
{
  "case": {
    "case_id": "case-myapp-abc123",
    "tenant_id": "xxx",
    "app_code": "my-app",
    "environment": "production",
    "symptom_summary": "Pod OOMKilled 导致服务不可用",
    "hypotheses": ["内存泄漏", "资源配置不足"],
    "actions": ["检查内存使用趋势", "调整资源 limit"],
    "resolution": "调整 Pod 内存 limit 至 4Gi",
    "confidence": 0.85
  }
}
```

### memory_case_feedback

对案例进行反馈，调整置信度和生命周期。

```json
{
  "case_id": "case-myapp-abc123",
  "helpful": true,
  "signal": "success"
}
```

### memory_case_render

将案例渲染为 Markdown 格式，便于注入到 Prompt 中。

```json
{
  "cases": [...],
  "case_ids": ["case-myapp-abc123"]
}
```

## 接入方式

### 方式一：UI 可视化选择（推荐）

案例记忆作为内置 MCP 插件，在应用构建器（Application Builder）的「技能」Tab 和对话连接器（ConnectorsModal）中可见。用户按需选择即可载入，无需任何配置。

**流程：**
1. 在 MCP 列表中找到「案例记忆」（标记为 Built-in）
2. 选择/启用该 MCP
3. 系统自动以 `tool(memory_case)` 资源类型注入到 Agent
4. Agent 构建时通过 `MemoryCaseToolPack` 加载 4 个工具

**资源类型路由：**
- UI 选择 → `tool(memory_case)` 类型 → `MemoryCaseToolPack`（进程内调用）
- 若以 `mcp(derisk)` 类型传入（兼容旧数据），后端自动归一化为 `tool(memory_case)`

### 方式二：resource_tool 声明

在 `resource_tool` 中显式添加 `tool(memory_case)` 资源：

```json
{
  "app_code": "my-rca-agent",
  "agent": "BAIZE",
  "resource_tool": [
    {
      "type": "tool(memory_case)",
      "name": "memory_case",
      "value": "{\"name\":\"memory_case\",\"mcp_name\":\"memory_case\"}"
    }
  ]
}
```

> **注意：** `value` 中必须包含 `name` 字段，否则 `ResourceParameters` 构造会失败。

### 方式三：代码直接创建

```python
from derisk_serve.agent.resource.tool.memory_case import MemoryCaseToolPack

tool_pack = MemoryCaseToolPack(system_app=system_app)
await tool_pack.preload_resource()

# tool_pack._resources 包含 4 个工具
# 将 tool_pack 绑定到 Agent 即可
```

## MCP 服务层

案例记忆 MCP 服务随项目自动启动，无需额外配置。

| 配置项 | 位置 | 默认值 | 说明 |
|--------|------|--------|------|
| `memory_plugin_enabled` | `ServeConfig` (mcp/config.py) | `True` | MCP 服务层基础设施开关，控制 `MemoryCasePluginService` 初始化和虚拟条目可见性 |
| `memory_plugin_timeout` | `ServeConfig` (mcp/config.py) | `10` | MCP 工具调用超时（秒） |

> **注意：** `memory_plugin_enabled` 控制的是插件基础设施是否可用（服务是否启动、虚拟条目是否在 MCP 列表可见），而非自动注入。用户需通过 UI 选择或 resource_tool 声明来接入。

**API 端点：** `/api/v1/serve/mcp/`

| 端点 | 方法 | 用途 |
|------|------|------|
| `/health` | POST | 健康检查，传 `{"name": "memory_case"}` |
| `/connect` | POST | 连接 MCP，传 `{"name": "memory_case"}` 或 `{"name": "案例记忆"}` |
| `/tool/list` | POST | 列出工具，传 `{"name": "memory_case"}` 或 `{"name": "案例记忆"}` |
| `/tool/run` | POST | 调用工具，传 `{"name": "memory_case", "params": {"name": "memory_case_search", "arguments": {...}}}` |

> `memory_case` 是内置 MCP 插件，不需要外部 SSE 连接，直接进程内调用。API 同时接受 `mcp_code`（`"memory_case"`）和显示名（`"案例记忆"`）。

## 核心组件

### MemoryCaseToolPack

**文件：** `packages/derisk-serve/src/derisk_serve/agent/resource/tool/memory_case.py`

继承 `ToolPack`，在 `preload_resource()` 时从 `MemoryCasePluginService` 获取工具列表，通过 `add_command()` 注册为 Agent 可调用的工具。

- `type()` → `"tool(memory_case)"`
- `type_alias()` → `"tool(memory_case)"`
- 自动从 `McpService` 获取已初始化的 `MemoryCasePluginService` 实例

### Scope 自动注入机制

**设计目标：** 每个 Agent 只能看到自己 scope 的案例，LLM 无需手动传递 scope 参数。

Scope（`app_code` + `environment`）是案例记忆的多租户隔离维度。搜索时通过 `WHERE app_code = ? AND environment = ?` 过滤，确保不同应用的案例互不干扰。

**自动注入流程：**

```
Agent 构建时                          Agent 工具调用时
─────────────                        ──────────────
agent_chat.py                        LLM 调用 memory_case_search({})
  │                                    │
  ├─ set_memory_case_scope(            ├─ _make_caller("memory_case_search")
  │    app_code="main-orchestrator",   │    └─ _resolve_scope(kwargs)
  │    conv_id="xxx"                   │        ├─ 1. LLM 传入的 scope（优先）
  │  )                                 │        ├─ 2. thread-local scope context
  │                                    │        └─ 3. 兜底默认值 "default"
  │                                    │
  └─ build Agent                      └─ kwargs["scope"] = {
       └─ MemoryCaseToolPack                "app_code": "main-orchestrator",
         └─ _make_caller()                    "environment": "default",
           └─ _resolve_scope()                "conv_id": "xxx"
                                            }
```

**关键实现：**

1. **`set_memory_case_scope(app_code, conv_id)`** — 线程局部变量，在 Agent 构建时由 `agent_chat.py`（V1）或 `core_v2_adapter.py`（V2）调用设置
2. **`get_memory_case_scope()`** — 在 `_resolve_scope()` 中读取，获取当前线程的 app_code
3. **`_resolve_scope(kwargs)`** — 三级优先级合并：
   - LLM 显式传入的 scope 字段（最高优先级）
   - thread-local scope context 中的 app_code / conv_id
   - 兜底默认值 `"default"`
4. **`_make_caller(tool_name)`** — 对 `memory_case_search` 和 `memory_case_upsert` 自动注入 scope

**对 upsert 的影响：**

当 LLM 调用 `memory_case_upsert` 写入案例时，`_make_caller` 会自动填充 `case` 中的 `app_code`、`environment`、`source_conv_id`，确保写入的案例归属于正确的 scope。

### ResourceResolver 扩展

**文件：** `packages/derisk-core/src/derisk/agent/core_v2/agent_binding.py`

新增 `tool(memory_case)` / `memory_case` 资源类型解析，返回 `{"type": "memory_case", "mcp_name": "memory_case"}` 信息供 ToolPack 实例化使用。

### ResourceManager 注册

**文件：** `packages/derisk-app/src/derisk_app/component_configs.py`

```python
rm.register_resource(MemoryCaseToolPack, resource_type=ResourceType.Tool)
```

### MemoryCasePluginService（已有）

**文件：** `packages/derisk-serve/src/derisk_serve/mcp/memory_case/service.py`

内置 MCP 服务，提供 4 个工具的完整实现，包括：
- DB 持久化（`MemoryCaseDao` → `derisk_serve_mcp_memory_case` 表）
- 向量索引（`ChromaCandidateCaseVectorIndex` → `memory_case_candidate` collection）
- 置信度管理和生命周期状态机（DRAFT → ACCEPTED / REJECTED / STALE）

## 数据模型

### CandidateCase

| 字段 | 类型 | 说明 |
|------|------|------|
| case_id | str | 唯一标识，格式 `case-{app_code}-{fingerprint[:12]}` |
| tenant_id | str | 租户 ID |
| team_id | str | 团队 ID |
| app_code | str | 应用代码，用于作用域隔离 |
| environment | str | 环境（production/staging 等） |
| fingerprint | str | SHA1 去重指纹 |
| symptom_summary | str | 症状摘要 |
| hypotheses | List[str] | 假设列表 |
| actions | List[str] | 采取的行动列表 |
| resolution | str | 最终解决方案 |
| confidence | float | 置信度 0.0-1.0 |
| lifecycle | CandidateCaseLifecycle | DRAFT/ACCEPTED/REJECTED/STALE |
| source_conv_id | str | 来源会话 ID |
| markdown_summary | str | Markdown 格式摘要 |

### 作用域（Scope）

搜索时通过 `app_code` + `environment` 隔离，确保不同应用、不同环境的案例互不干扰。

**自动注入：** scope 由系统自动从 Agent 上下文（`agent_app_code` / `conv_id`）注入，LLM 无需手动传递。详见 [Scope 自动注入机制](#scope-自动注入机制)。

| 字段 | 来源 | 默认值 | 说明 |
|------|------|--------|------|
| `app_code` | Agent 上下文 `agent_app_code` | `"default"` | 应用级隔离，每个 App 只能看到自己的案例 |
| `environment` | 系统配置 | `"default"` | 环境级隔离（production/staging） |
| `conv_id` | Agent 上下文 `conv_id` | `None` | 会话追踪，写入案例时记录来源会话 |
| `tenant_id` | LLM 传入或默认 | `None` | 租户级隔离（可选） |
| `team_id` | LLM 传入或默认 | `None` | 团队级隔离（可选） |

## Agent Prompt 建议

接入案例记忆后，建议在 Agent 的 System Prompt 中添加引导语：

```
你已接入案例记忆系统，可以通过以下工具访问历史经验：

- memory_case_search: 搜索相似的历史案例，在分析问题前先查询是否有相关经验
- memory_case_upsert: 将新发现写入案例库，供未来参考
- memory_case_feedback: 对已有案例进行反馈
- memory_case_render: 将案例渲染为 Markdown

建议工作流：
1. 收到告警/问题时，先用 memory_case_search 搜索相似案例
2. 参考历史经验制定排查方案
3. 问题解决后，用 memory_case_upsert 记录新案例
4. 用 memory_case_feedback 标记历史案例是否有帮助
```

> **注意：** `scope` 参数由系统自动注入（app_code、environment、conv_id），LLM 无需手动传递。如果 LLM 显式传入 scope，系统会合并而非覆盖自动注入的值。

## 故障排查

| 症状 | 原因 | 解决方案 |
|------|------|----------|
| MCP 列表中看不到「案例记忆」 | `memory_plugin_enabled=false` 或服务未启动 | 检查 ServeConfig 中 `memory_plugin_enabled` 是否为 True |
| Agent 工具列表中没有 memory_case 工具 | 未在 UI 中选择或 resource_tool 中未声明 | 在应用构建器→技能→内置 MCP 中选择「案例记忆」 |
| `PackResourceParameters.__init__() missing 'name'` | `AgentResource.value` 中缺少 `name` 字段 | 确保 value 为 `{"name":"memory_case","mcp_name":"memory_case"}` |
| `无法找到当前mcp服务[memory_case]` | 以 `mcp(derisk)` 类型传入，DB 中无此行 | 后端自动归一化：`mcp(derisk):memory_case` → `tool(memory_case)` |
| `[MISSING_SCOPE] scope is required` | 旧版本 `scope` 为必填参数 | 已修复：`scope` 改为可选，自动从 Agent 上下文注入 |
| 案例写入后其他 Agent 看不到 | scope 隔离，不同 `app_code` 的案例互不可见 | 这是设计行为，确保多租户隔离 |

## 文件清单

| 文件 | 说明 |
|------|------|
| `packages/derisk-serve/src/derisk_serve/agent/resource/tool/memory_case.py` | MemoryCaseToolPack 实现 |
| `packages/derisk-serve/src/derisk_serve/mcp/memory_case/service.py` | MemoryCasePluginService + BUILTIN_MEMORY_MCP 常量 |
| `packages/derisk-serve/src/derisk_serve/mcp/memory_case/models.py` | CandidateCase 数据模型 |
| `packages/derisk-serve/src/derisk_serve/mcp/memory_case/vector_index.py` | 向量索引 |
| `packages/derisk-serve/src/derisk_serve/mcp/memory_case/markdown.py` | Markdown 渲染/解析 |
| `packages/derisk-serve/src/derisk_serve/mcp/models/memory_case_models.py` | DB 实体和 DAO |
| `packages/derisk-serve/src/derisk_serve/mcp/service/service.py` | MCP 服务层（虚拟条目注入、内置路由） |
| `packages/derisk-serve/src/derisk_serve/mcp/config.py` | ServeConfig（memory_plugin_enabled 基础设施开关） |
| `packages/derisk-core/src/derisk/agent/core_v2/agent_binding.py` | ResourceResolver 扩展（tool(memory_case) 类型解析） |
| `packages/derisk-app/src/derisk_app/component_configs.py` | ResourceManager 注册 |
| `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` | V1 路径：资源归一化 + scope 上下文设置 |
| `packages/derisk-serve/src/derisk_serve/agent/core_v2_adapter.py` | V2 路径：资源归一化 + scope 上下文设置 |