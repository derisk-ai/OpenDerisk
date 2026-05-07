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
│  derisk-serve: MCP 适配层                        │
│  McpService / MemoryCaseToolPack（装配与路由）   │
└────────────────────┬────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────┐
│  derisk_ext.plugin.memory_case                    │
│  MemoryCasePluginService（工具与领域逻辑）        │
│                                                  │
│  ┌──────────────┐  ┌────────────────────────┐   │
│  │ MemoryCaseDao │  │ ChromaDB VectorIndex   │   │
│  │ (`sqlalchemy_dao`) │ (ext `vector_index`) │   │
│  └──────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

**分层说明：** `CandidateCase`、`MemoryCasePluginService`、**Chroma 向量**、**SQLAlchemy DAO**（`MemoryCaseDao` / `MemoryCaseEntity`）、**`bind_memory_case_scope_for_agent`** 均在 **`packages/derisk-ext/.../plugin/memory_case/`**。`McpService` 在启动时注入 serve 的 `StorageManager`（实现 `MemoryCaseVectorStoreSource` 协议）以创建向量库。

## 设计理念

| 维度 | 说明 |
|------|------|
| 耦合方式 | 标准 ToolPack，Agent 自主调用，无 monkey-patch |
| 接入方式 | 内置 MCP 可视化选择，用户在 UI 中按需载入 |
| 工具可见性 | Agent 在工具列表中看到工具，自主决策调用时机 |
| 召回时机 | 故障/排查类任务：**先** `memory_case_search` 再深入分析（见下方会话协议） |
| 回写时机 | 任务收尾 **评估后** `memory_case_upsert`；引用过的案例用 `memory_case_feedback` 闭环 |
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
    "symptom_summary": "Pod OOMKilled 导致服务不可用",
    "hypotheses": ["内存泄漏", "资源配置不足"],
    "actions": ["检查内存使用趋势", "调整资源 limit"],
    "resolution": "调整 Pod 内存 limit 至 4Gi",
    "confidence": 0.85,
    "metadata": {
      "case_context": {
        "application_name": "订单服务",
        "data_sources": ["Prometheus", "Loki"],
        "related_services": ["checkout-api"]
      }
    }
  }
}
```

（`app_code` / `environment` 等也可写在 `metadata.case_context`；若写在顶层，服务端会迁入 `case_context`。运行时仍会通过 `scope` 自动补全路由字段。）

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
- UI / `resource_tool` 必须使用 **`tool(memory_case)`**（或别名 `memory_case`）→ `MemoryCaseToolPack`（进程内调用）
- **不再支持**将 `mcp(derisk)` + `memory_case` 在后端改写为 `tool(memory_case)`；客户端与存量配置应直接使用 `tool(memory_case)`

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
from derisk_ext.plugin.memory_case import MemoryCaseToolPack

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

**内置 MCP 列表 / `get` 行为（不落表）：** `memory_case` **不必**存在于 `derisk_serve_mcp` 表中。[`McpService`](packages/derisk-serve/src/derisk_serve/mcp/service/service.py) 使用单一工厂方法 **`_builtin_memory_case_server_response()`** 构造与 DB 行同构的 `ServerResponse`（含 `sse_url` 指向本机 `/mcp/sse` 网关），供 **`get()`** 与 **`filter_list_page()`**（首屏去重注入）复用；**`delete()`** 对 `memory_case` 短路拒绝，避免误删内置项。

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

**实现：** `packages/derisk-ext/src/derisk_ext/plugin/memory_case/tool_pack.py`

继承 `ToolPack`，在 `preload_resource()` 时通过 **`register_memory_case_plugin_resolver`**（由 [`McpService.init_app`](packages/derisk-serve/src/derisk_serve/mcp/service/service.py) 注册）解析到已初始化的 `MemoryCasePluginService`，再 `add_command()` 注册为 Agent 工具。

- `type()` → `"tool(memory_case)"`
- `type_alias()` → `"tool(memory_case)"`
- 单测等场景可 **`pack._plugin = ...`** 注入假插件，或调用 `register_memory_case_plugin_resolver` / `clear_memory_case_plugin_resolver`

### Scope 自动注入机制

**设计目标：** 每个 Agent 只能看到自己 scope 的案例，LLM 无需手动传递 scope 参数。

Scope（工具入参里的 `app_code` / `environment` 等）与持久化中的 **`metadata.case_context`** 对齐，用于隔离检索；SQL 层对 MySQL/SQLite 使用 `JSON_EXTRACT(metadata_json, '$.case_context.*')` 条件（其它方言见 DAO 回退）。

**自动注入流程：**

```
Agent 构建时                          Agent 工具调用时
─────────────                        ──────────────
agent_chat / core_v2_adapter         LLM 调用 memory_case_search({})
  │                                    │
  ├─ bind_conversation_scope_for_agent( ├─ _make_caller("memory_case_search")
  │    app_code="main-orchestrator",   │    └─ _resolve_scope(kwargs)
  │    conv_id="xxx"                   │        ├─ 1. LLM 传入的 scope（优先）
  │  )  → set_memory_case_scope(...)   │        ├─ 2. ContextVar scope（async 友好）
  │     (derisk_serve.agent.memory_   │        └─ 3. 兜底默认值 "default"
  │      case_scope)                   │
  │                                    │
  └─ build Agent                      └─ kwargs["scope"] = {
       └─ MemoryCaseToolPack                "app_code": "main-orchestrator",
         └─ _make_caller()                    "environment": "default",
           └─ _resolve_scope()                "conv_id": "xxx"
                                            }
```

**关键实现：**

1. **`bind_memory_case_scope_for_agent(app_code, conv_id)`**（`derisk_ext/plugin/memory_case/scope_binding.py`）— 在 **`ensure_memory_case_resource_resolver_registered()`** 中通过 **`derisk.agent.conversation_scope_hooks.register_conversation_scope_hook`** 注册；`agent_chat.py`（V1）与 `core_v2_adapter.py`（V2）只调用 **`bind_conversation_scope_for_agent`**（core 遍历已注册 hooks），不直接依赖 `derisk_ext`。内部调用 **`set_memory_case_scope`**
2. **`set_memory_case_scope` / `get_memory_case_scope()`** — 使用 **`contextvars.ContextVar`** 保存 `app_code` / `conv_id`，在 `_resolve_scope()` 中读取
3. **`_resolve_scope(kwargs)`** — 三级优先级合并：
   - LLM 显式传入的 scope 字段（最高优先级）
   - ContextVar 中的 app_code / conv_id
   - 兜底默认值 `"default"`
4. **`_make_caller(tool_name)`** — 对 `memory_case_search` 和 `memory_case_upsert` 自动注入 scope

**对 upsert 的影响：**

当 LLM 调用 `memory_case_upsert` 写入案例时，`_make_caller` 会把 `scope` 中的路由字段合并进 **`case.metadata.case_context`**，并设置 **`source_conv_id`**，保证检索维度一致。

### ResourceResolver 可扩展解析

**Core：** `packages/derisk-core/src/derisk/agent/core_v2/agent_binding.py` 中 `ResourceResolver.register_custom_resource_resolver(resource_type, async_fn)`，用于注册任意资源类型的异步解析函数（core 不依赖 `derisk-ext`）。

**memory_case 注册：** `packages/derisk-ext/src/derisk_ext/plugin/memory_case/integration.py` 的 **`ensure_memory_case_resource_resolver_registered()`** 为 `tool(memory_case)` / `memory_case` 注册解析器，返回 `{"type": "memory_case", "mcp_name": "memory_case"}` 供 ToolPack 实例化；并在同一入口注册 **conversation scope hook**（`bind_memory_case_scope_for_agent`）。应用在 **`component_configs.initialize_components`** 开头、**`McpService.init_app`** 中会各调用一次（幂等）。

### ResourceManager 注册

**文件：** `packages/derisk-app/src/derisk_app/component_configs.py`

```python
rm.register_resource(MemoryCaseToolPack, resource_type=ResourceType.Tool)
```

### MemoryCasePluginService

**实现：** `packages/derisk-ext/src/derisk_ext/plugin/memory_case/service.py`

内置 MCP 插件核心，提供 4 个工具的领域逻辑；持久化与 Chroma 向量由 serve 侧注入：
- DB 持久化（`MemoryCaseDao` → `derisk_plugin_memory_case` 表；InnoDB FULLTEXT；路由字段在 `metadata_json.case_context`）
- 向量索引（`ChromaCandidateCaseVectorIndex` → `memory_case_candidate` collection，见 ext `plugin/memory_case/vector_index.py`）
- 置信度管理和生命周期状态机（DRAFT → ACCEPTED / REJECTED / STALE）

安装带语义索引的环境时，可为 `derisk-serve` 选择 optional **`memory_case`**（传递 `derisk-ext[storage_chromadb]`）。

## 数据模型

### CandidateCase

| 字段 | 类型 | 说明 |
|------|------|------|
| case_id | str | 唯一标识，常用 `case-{uuid}` |
| metadata | dict | 案例元信息；**路由与溯源**放在 `metadata.case_context`（如 `app_code`、`environment`、`tenant_id`、`team_id`、`application_name`、`data_sources`、`related_services`、`region`、`tags` 等）；其余键可存反馈、人工复核等 |
| fingerprint | str | 内容指纹（未传时由 `case_context` + 摘要等自动派生） |
| incident_title | str | 短标题，列表/卡片展示（可选） |
| symptom_summary | str | 症状摘要 |
| hypotheses | List[str] | 假设列表 |
| actions | List[str] | 采取的行动列表 |
| resolution | str | 最终解决方案 |
| handling_path | str | 处理过程自由叙述：尝试分支、走弯路、经验提示等（仅供参考，非固定步骤剧本） |
| root_cause | str | 确认根因一句话（可选） |
| confidence | float | 置信度 0.0-1.0 |
| lifecycle | CandidateCaseLifecycle | DRAFT/ACCEPTED/REJECTED/STALE |
| source_conv_id | str | 来源会话 ID |
| markdown_summary | str | Markdown 格式摘要 |

### 作用域与检索规则（表无 `app_code` / `environment` 列）

**表结构：** `derisk_plugin_memory_case` **没有** `app_code`、`environment`、`tenant_id`、`team_id` 等列；路由与业务元信息只存在于 **`metadata_json`** 解析后的 **`metadata.case_context`**（JSON）。

**`memory_case_search` 规则：**

1. **可选窄化（`scope`）** — 仅对 `metadata_json` 做 `JSON_EXTRACT(..., '$.case_context.<key>')` 等值比较。  
   - `app_code` / `environment`：在 `scope` 中为 **缺省、空串或字面量 `default`**（不区分大小写）时，**不对该键过滤**（通配）。传入其它值则与库里 `case_context` 精确匹配。  
   - `tenant_id` / `team_id`：仅在 `scope` 中 **显式传入非空** 时参与过滤。

2. **词法 `query`** — MySQL 使用 InnoDB **FULLTEXT**（索引列与代码常量 `FULLTEXT_LEXICAL_COLUMNS` 一致，含 `hypotheses`、`actions`）；失败 **1191** 时回退 **LIKE**。其它方言用 **LIKE**。

3. **语义分支** — 若启用 Chroma，向量检索的 metadata 过滤与 (1) 的通配规则一致；结果与 (2) 合并。

**自动注入（upsert）：** 运行时把 `app_code` / `conv_id` 等合并进 **`case.metadata.case_context`**，见 [Scope 自动注入机制](#scope-自动注入机制)。

| 概念 | 来源 | 默认值 | 说明 |
|------|------|--------|------|
| `case_context.app_code` | Agent 上下文合并进 metadata | `"default"` | 检索时若 `scope.app_code` 为缺省/`default`，**不按 app_code 过滤**；传入非 default 则精确匹配 |
| `case_context.environment` | 工具 `scope` / LLM | `"default"` | 检索时若 `scope.environment` 为缺省/`default`，**不按 environment 过滤** |
| `source_conv_id` | Agent 上下文 `conv_id` | `None` | 写入案例时记录来源会话 |
| `case_context.tenant_id` / `team_id` | LLM 或显式 `scope` | 可选 | 仅在 `scope` 非空时参与过滤 |

## Agent 使用方式（MemPalace 式节奏）

参考外部项目 **MemPalace** 的「先查证、再叙述、后归档」习惯，在 **不接入** MemPalace MCP 的前提下，为案例记忆约定固定节奏，减少「从不搜库」或「幻觉式引用历史」。

**详细手册（含与 MemPalace 概念对照、可复制 System Prompt 片段）：**  
[docs/CASE_MEMORY_AGENT_PLAYBOOK.md](./CASE_MEMORY_AGENT_PLAYBOOK.md)

**摘要：**

1. **开场**：可复现故障 / 排查类任务 → 先 `memory_case_search`（短 `query`，勿塞整段日志或系统提示）。  
2. **过程中**：线索变化 → 可再搜；需要可读上下文 → `memory_case_render`。  
3. **下结论前**：若依赖「历史上是否出现过」→ 须有 **search 结果** 支撑。  
4. **收尾**：值得沉淀 → `memory_case_upsert`；写库前用 **search 当查重**，高相似则带 **`case_id` 合并**。  
5. **引用过某条案例**：`memory_case_feedback`；旧结论被推翻 → feedback（如 stale）+ 新 upsert。

MCP 工具在 **`MemoryCasePluginService.list_tools()`** 中的 **description / 字段说明** 已按上述节奏加强，便于模型在工具列表中直接看到期望行为。

> **注意：** `scope` 中的路由键**不是表列**，只映射到 **`metadata.case_context`**。运行时注入的 `app_code` / `environment` 会与 LLM 显式传入合并；`app_code`/`environment` 为 `default` 时检索对该维度通配。

## 故障排查

| 症状 | 原因 | 解决方案 |
|------|------|----------|
| MCP 列表中看不到「案例记忆」 | `memory_plugin_enabled=false` 或服务未启动 | 检查 ServeConfig 中 `memory_plugin_enabled` 是否为 True |
| Agent 工具列表中没有 memory_case 工具 | 未在 UI 中选择或 resource_tool 中未声明 | 在应用构建器→技能→内置 MCP 中选择「案例记忆」 |
| `PackResourceParameters.__init__() missing 'name'` | `AgentResource.value` 中缺少 `name` 字段 | 确保 value 为 `{"name":"memory_case","mcp_name":"memory_case"}` |
| `无法找到当前mcp服务[memory_case]` / 资源未解析 | `memory_plugin_enabled=false` 或 `McpService.get` 未命中内置分支 | 打开插件开关；确认 `get_mcp_info` 走 `McpService`；新应用推荐 **`tool(memory_case)`** + `value` 含 `name` / `mcp_name` |
| `[MISSING_SCOPE] scope is required` | 旧版本 `scope` 为必填参数 | 已修复：`scope` 改为可选，自动从 Agent 上下文注入 |
| 案例写入后其它应用看不到 | 在 `scope` 中显式传了非 `default` 的 `app_code`/`environment` 时按 JSON 隔离 | 需要跨应用召回时勿传窄化 `scope`，或写入时统一 `case_context` |

## 文件清单

| 文件 | 说明 |
|------|------|
| `packages/derisk-ext/src/derisk_ext/plugin/memory_case/` | 核心：`MemoryCasePluginService`、模型、Markdown、**Chroma 向量与 `build_vector_index`**、`MemoryCaseToolPack`、`plugin_resolver`、`integration`（注册 ResourceResolver） |
| `docs/CASE_MEMORY_AGENT_PLAYBOOK.md` | Agent 使用手册（MemPalace 式会话协议，可复制进 System Prompt） |
| `packages/derisk-ext/src/derisk_ext/plugin/memory_case/sqlalchemy_dao.py` | DB 实体 `MemoryCaseEntity` 与 `MemoryCaseDao` |
| `packages/derisk-serve/src/derisk_serve/mcp/service/service.py` | MCP 服务层；内置列表/`get` 复用 **`_builtin_memory_case_server_response`**，虚拟注入 + `delete` 守卫 |
| `tests/test_mcp_builtin_memory_virtual.py` | 内置 `memory_case` 虚拟行与 `get`/`filter_list_page`/`delete` 行为单测 |
| `packages/derisk-serve/src/derisk_serve/mcp/config.py` | ServeConfig（memory_plugin_enabled 基础设施开关） |
| `packages/derisk-core/src/derisk/agent/core_v2/agent_binding.py` | `ResourceResolver` 与 **`register_custom_resource_resolver`** |
| `packages/derisk-app/src/derisk_app/component_configs.py` | ResourceManager 注册 + **`ensure_memory_case_resource_resolver_registered`** |
| `packages/derisk-ext/src/derisk_ext/plugin/memory_case/scope_binding.py` | `bind_memory_case_scope_for_agent`（单一入口） |
| `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` | V1：`bind_conversation_scope_for_agent`；`chat_in_params` 对任意 `tool(...)` 注入资源 |
| `packages/derisk-serve/src/derisk_serve/agent/core_v2_adapter.py` | V2：`bind_conversation_scope_for_agent` |