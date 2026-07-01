# Scenario Workspace MVP — 设计与实现文档

> 状态：MVP 已完整交付（2026-06-25）
> 适用版本：OpenDerisk 当前主干
> 主题：在 Agent-centric 平台上叠加 Scenario Workspace 层，让 SME 数据运营与 SRE 团队以"空间"为单位组织工作

---

## 1. 背景与动机

OpenDerisk 当前是 Agent-centric 配置平台：用户在 HomeChat 或 Application Builder 里配置 Agent + Skill + MCP + Knowledge Vault，然后通过 chat 完成。这对个人/单任务场景够用，但对 SME 团队场景有三大缺口：

1. **没有"团队组织单元"**：数据运营组、SRE 组各自的工作流、数据源、知识沉淀混在一起，没法按场景隔离
2. **没有"工作统一入口"**：定时任务、webhook、告警触发的 Agent 运行散落在 cron 模块和外部脚本里，没有"Task"作为统一抽象
3. **没有"经验沉淀机制"**：每次 Agent 跑完产出报告，下次同类任务又从零开始，没有把产出物和案例沉淀为可复用的"资产"

MVP 的目标是**叠加**一个 Scenario Workspace 层，**不动现有模块**（HomeChat / Application Builder / Agent / Skill / MCP / DataResource / Knowledge Vault 全部保持原状），让 SME 团队可以：

- 以 workspace 为单元组织成员、绑定资源、配置默认 Agent
- 通过 Playbook（极简 YAML DSL）声明"做什么、用什么、产出什么、沉淀什么"
- 通过 Task 作为工作统一入口（4 种触发：timer / webhook / alert / manual）
- 强制 distill：Task close 前必须把经验沉淀为 Asset，下次同类任务 Agent 自动加载（Agent 专精）
- 通过 Review 介入让人在异常时看一眼再 close

两个 design partner 场景验证：
- **数据运营周报**：每周一 9 点自动跑，产出报告邮件给 ops-team，沉淀为 historical_artifact
- **SRE 容量巡检**：每天 2 点自动跑，发现异常飞书通知 oncall，沉淀为 historical_artifact + case

---

## 2. 核心概念

```
┌──────────────────────────────────────────────────────────────────┐
│                       Scenario Workspace                         │
│  ──────────────────────────────────────────────────────────────  │
│  Members: owner / contributor / approver / viewer                │
│  Resources: data_source / knowledge_space / environment /        │
│             mcp / skill / llm_model (引用现有原子能力)            │
│  Default Agent: app_code (复用现有 Application Builder 配置)     │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Trigger Sources (timer/webhook/alert/manual)            │   │
│  │           ↓ fire                                          │   │
│  │  Task (状态机: draft → pending_trigger → running →        │   │
│  │         awaiting_human → delivered → closed)              │   │
│  │           ↓ run                                          │   │
│  │  Playbook Runtime (组装上下文 → 调 app_chat → 校验产出)   │   │
│  │           ↓                                              │   │
│  │  Agent (workspace_context 已注入 system prompt)           │   │
│  │           ↓                                              │   │
│  │  Artifact (report/analysis/dataset)                      │   │
│  │           ↓                                              │   │
│  │  Delivery (notify: email/feishu/in_app)                  │   │
│  │           ↓                                              │   │
│  │  Intervention (review) — 异常时人看一眼                  │   │
│  │           ↓ resolve (含 distillation)                    │   │
│  │  Asset (historical_artifact / case) ← 沉淀               │   │
│  │           ↑                                              │   │
│  │  下次同类 Task 启动时加载 ← Agent 专精                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.1 Workspace（空间）

组织单元，**不是个人空间**。一个 workspace 对应一个团队或一个场景（数据运营组、SRE 组、风控组等）。包含：

- 基本信息：workspace_code (unique) / name / description / type (scenario/team) / scenario_type (sre/data_ops/...)
- 成员表：user_id + role (owner/contributor/approver/viewer)，MVP 用成员表判断权限，不扩 RBAC
- 资源表：引用现有原子能力（connect_config 数据源 / 知识空间 slug / mcp / skill / llm_model）
- 默认 Agent：app_code（指向 Application Builder 已配置的 Agent）
- 会话链接表：`conv_uid ↔ workspace_id` 映射（**不动 chat_history 核心表**）

### 2.2 Task（任务）

工作统一入口。4 种触发方式：

| 触发 | 来源 | Task type |
|------|------|-----------|
| timer | CronService 调度 | routine |
| webhook | 外部 webhook | adhoc |
| alert | 监控告警 webhook | incident |
| manual | 用户手动 | adhoc |

状态机：`draft → pending_trigger → running → awaiting_human → blocked → delivered → closed → archived`（+ `failed`）

**关键约束**：`close` 端点服务端强制校验 distill 完整性，未完成返回 409（`Result.failed(msg=..., err_code="E4091")`）。校验逻辑：所有关联 intervention 必须 `resolved` 且 `distillation_json` 非空。

### 2.3 Playbook（剧本）

策略声明，**不是工作流 DSL**。极简 YAML/JSON 四块：

```yaml
playbook:
  name / scenario_type / task_type
  trigger: { type: timer/webhook/alert/manual, ... }
  skills: [ref(resource:skill_code), ...]              # 直接引用 skill，不做 SkillBundle
  context:
    assets_required: [{type, ref|query}]               # 启动前加载的 Asset
    resources: [ref(resource:resource_name), ...]      # 数据源/环境
  deliverables:
    - { type: report/analysis/dataset, delivery: [{category: notify, channel: email/feishu/in_app, target}] }
  distill:
    forced: true
    produce: [{ type: historical_artifact/case, from: deliverable.X|when: ... }]
```

**v1 不做 gates**（不在中间触发介入，只在 close 时校验）。

每个 Playbook 有版本表，create 记 v1，update 持久化新版本（含 changelog）。`validate_declaration()` 服务端校验四块完整性：skills/deliverables/distill 必填；distill.forced=true 时 produce 必须非空。

`assemble_context(playbook, task)` 返回 dict（skills/context/deliverables/distill/task_input），供 playbook_runtime 注入 Agent prompt。

### 2.4 Artifact（产出物）

Task 的独立产出物，type=report/analysis/dataset。带版本表（每次 update 自增 current_version + 记录新版本）。provenance_json 记录来源（哪个 Agent、用哪些 skill、引用哪些数据）。

### 2.5 Asset（资产 / 空间记忆）

Task distill 后沉淀的知识，type=historical_artifact/case。带版本表。TaskAssetLink 表记录 Task 与 Asset 的 consumed/produced 关系。

**Asset 是 Agent 专精的核心**：下次同类 Task 启动时，`context_builder` 会查询 workspace 下最近 N 个 Asset，作为"空间记忆摘要"注入 Agent system prompt。

> **命名冲突说明**：仓库已有的 `derisk_serve.asset` 是知识库搜索模块（搜索 knowledge_base / document），与 MVP 的"沉淀资产"语义冲突。MVP 模块命名为 `derisk_serve.workspace_asset` 避免冲突，表名 `server_app_workspace_asset`。

### 2.6 Delivery（投递）

把 Artifact 落地到目标渠道。MVP 只做 **notify 类**（email / feishu / in_app）：

- email：SMTP（ServeConfig 配置 smtp_host/port/user/password/from）
- in_app：写站内信（MVP stub）
- feishu：复用 `derisk_ext.channels.FeishuChannelHandler`（MVP 未完整接入，留接口）

明确不做：Execute delivery（重启/部署/改配置，SME 不敢用）、Host delivery（5 种托管运行时，工程量过大）。

### 2.7 Intervention（介入）

人在环中（Human-in-the-loop）。MVP 只做 **review** 一种类型。其他 5 种（approve / draft / co-author / escalate / abort）留接口不做。

介入流程：
1. Task running 中遇到需要人看的点 → 创建 Intervention（status=requested）
2. 用户在介入中心处理：填决策 + distillation + 关联 Asset → resolve
3. resolve 时自动创建 Asset 并 link 到 Task
4. Task 可继续 → close 时校验所有 Intervention 已 resolve 且 distillation 非空

### 2.8 Trigger（触发源）

把外部触发（timer/webhook/alert/manual）转换为 Task。`TriggerService.fire()` 创建一个 `pending_trigger` 状态的 Task，自动关联到 target_playbook_id。

- timer：config.cron 存储调度表达式（MVP 不自动注册到 CronService，靠外部 cron 调用 fire 端点；后续接入）
- webhook：对接 `agent_input_queue`（MVP stub）
- alert：对接监控 webhook（MVP stub）
- manual：直接创建 Task

---

## 3. 关键架构决策

### 3.1 并存模式，不动现有模块

**决策**：Workspace 层**叠加**在现有平台之上，所有现有模块（HomeChat / Application Builder / Agent / Skill / MCP / Knowledge Vault / DataResource）保持原状。

**Why**：现有模块是 Workspace 层的"原子能力"。Workspace 不重新实现 Agent/Skill，而是引用 app_code / skill_code / connect_config.id。这样既保护已有投入，又让 Workspace 聚焦在"组织 + 工作流 + 沉淀"层面。

**How**：
- 新增 8 个 serve 模块（workspace / task / playbook / artifact / workspace_asset / delivery / intervention / trigger）
- 现有 `asset` 模块（知识库搜索）保持原状，MVP 的沉淀资产模块命名为 `workspace_asset`
- `gpts_conversations` 加 `workspace_id` 列（NULL for legacy），老对话完全不受影响
- 不动 `chat_history` 核心表，新建 `server_app_workspace_conv_link` 映射表

### 3.2 强制 distill 是硬约束

**决策**：Task `close` 端点服务端校验 distill 完整性，未完成返回 409，UI 不放行。

**Why**：distill 是 Agent 专精的命脉。如果允许跳过，Asset 库永远是空的，下次同类 Task 还是从零开始，Workspace 的"沉淀价值"消失。强制 distill 让团队养成"做完事就沉淀"的习惯。

**How**：
- `TaskService.close(TaskCloseRequest)` 接受 `distill_completed: bool`，必须 true
- `InterventionService.is_task_distill_completed(task_id)` 检查所有 intervention resolved + distillation_json 非空
- close 时若校验失败，返回 `Result.failed(msg=str(e), err_code="E4091")`
- 前端 close Modal 内嵌 distill 表单（asset_name / asset_type / summary），引导用户填完再 close

### 3.3 Agent 专精上下文注入

**决策**：在 `aggregation_chat` 调用前，组装空间记忆摘要（workspace + members + resources + recent same-type tasks + recent assets），拼到 system prompt。

**Why**：让同一个通用 Agent（chat_normal 或用户配置的 app_code）在不同 workspace 表现出不同专精。SRE workspace 的 Agent 自动看到最近容量巡检 Asset；数据运营 workspace 的 Agent 自动看到上周周报 Asset。

**How**：
- `derisk_serve/workspace/context_builder.py` 提供 `build_workspace_context(system_app, workspace_id, task) -> dict`
- `render_workspace_context_summary(ctx) -> str` 把 dict 渲染成紧凑文本（# Workspace Context / # Bound Resources / # Recent Similar Tasks / # Workspace Memory）
- `agent_chat.py aggregation_chat` 在 `app_detail` 之后检查 `ext_info.workspace_id`，存在则注入：
  ```python
  ws_ctx = build_workspace_context(self.system_app, int(workspace_id))
  ext_info["workspace_context"] = ws_ctx
  ext_info["system_prompt"] = (existing_sys_prompt + "\n\n" + render_workspace_context_summary(ws_ctx)).strip()
  ```
- 前端 `use-chat.ts` 的 `data.ext_info` 已含 `workspace_id`；`home-chat.tsx` 两个 `newDialogue` 调用也带上 `workspace_id`

### 3.4 workspace-aware chat

**决策**：workspace 详情页用 iframe 嵌入现有 `/chat/?app_code=...&workspace_id=...`，**不重写 chat 组件**。

**Why**：现有 chat 页面（`web/src/app/chat/page.tsx` + `home-chat.tsx` + `use-chat.ts` + `ChatContentContainer`）复杂度极高（轮询恢复、SSE、vis parser、manus layout 等），重写 ROI 极低且引入回归风险。iframe 复用最简单。

**How**：
- workspace 详情页右侧栏加载 workspace info + 待处理介入 + 进行中任务
- 主体 iframe src = `/chat/?app_code=${ws.default_agent_app_code}&workspace_id=${ws.id}`
- `/chat/page.tsx` 的 chat 调用读取 `window.location.search` 中的 `workspace_id`，注入 `ext_info.workspace_id`
- `newDialogue` 也带 `workspace_id`，后端 `dialogue_new` 接受 `workspace_id` 查询参数，调用 `WorkspaceService.link_conversation()` 建立映射

### 3.5 不做 RBAC 资源类型扩展

**决策**：MVP 用 workspace_member 表判断权限，不扩 `feature_plugins/permissions/` 的资源类型。

**Why**：现有 RBAC 是针对 Application / Skill / MCP 等资源类型设计的。Workspace 的权限模型更简单（owner/contributor/approver/viewer 4 种角色），用成员表判断够用。等 design partner 真有跨空间共享需求再扩。

### 3.6 表自动创建，不用 alembic

**决策**：每个 serve 模块的 `before_start()` 用 `DatabaseManager.build_from(db, base=Model).create_all()` 自动建表。

**Why**：与 skill / mcp 等现有 serve 模块一致，简化部署。schema DDL 同步到 `assets/schema/derisk.sql` 供新部署使用。

---

## 4. 架构拓扑

### 4.1 后端 serve 模块

```
packages/derisk-serve/src/derisk_serve/
├── workspace/              # 空间 + 成员 + 资源 + 会话链接
│   ├── __init__.py / config.py / serve.py
│   ├── api/{endpoints,schemas}.py
│   ├── models/models.py
│   ├── service/service.py
│   └── context_builder.py  # Agent 专精上下文注入器
├── task/                   # 任务 + 任务关系（状态机 + 强制 distill）
├── playbook/               # 剧本 + 版本（策略声明 DSL）
│   └── builtin_examples.py # 两个内置示例
├── artifact/               # 产出物 + 版本
├── workspace_asset/        # 沉淀资产 + 版本 + Task-Asset 链接（避开 asset 命名冲突）
├── delivery/               # 投递（notify: email/feishu/in_app）
├── intervention/           # 介入（review only）
└── trigger/                # 触发源（timer/webhook/alert/manual → Task）
```

每个模块都遵循 skill/ 模板：
- `config.py`：APP_NAME / SERVE_APP_NAME / SERVER_APP_TABLE_NAME / ServeConfig(BaseServeConfig)
- `serve.py`：Serve(BaseServe) 的 init_app / on_init / before_start
- `api/endpoints.py`：APIRouter + Result.succ/failed + check_api_key
- `api/schemas.py`：Request / Response / ListFilter (pydantic)
- `models/models.py`：Entity(Model) + Dao(BaseDao) + from_request/to_request/to_response
- `service/service.py`：Service(BaseService) 业务逻辑

注册点：`packages/derisk-app/src/derisk_app/initialization/serve_initialization.py`
- `scan_serve_configs()` 列表加 8 个新模块
- 每个 serve 一段 `system_app.register(Serve, config=get_config(...))` 块

### 4.2 前端路由

```
web/src/app/
├── workspaces/
│   ├── page.tsx                          # 列表 + 新建 Modal
│   └── [id]/
│       ├── page.tsx                      # workspace-aware chat（iframe + 右侧栏）
│       ├── tasks/
│       │   ├── page.tsx                  # 任务列表
│       │   └── [tid]/page.tsx            # 任务详情（5 tab + close with distill）
│       ├── playbooks/
│       │   ├── page.tsx                  # 剧本列表 + Seed Built-in
│       │   └── [pid]/page.tsx            # 剧本编辑器（JSON DSL + validate + fire）
│       ├── artifacts/page.tsx            # 产出物库（按类型 tab）
│       ├── assets/page.tsx               # 资产库（空间记忆）
│       ├── resources/page.tsx            # 资源管理（绑定/解绑）
│       ├── interventions/page.tsx        # 介入中心（含强制 distill 表单）
│       └── settings/page.tsx             # 空间设置（基本信息 + 成员）
└── me/
    └── page.tsx                          # 我的视图（跨空间聚合）
```

侧栏入口：`web/src/components/layout/side-bar.tsx` 加 `workspaces` + `me` 两项（TeamOutlined / UserOutlined）。

### 4.3 API 客户端

```
web/src/client/api/
├── workspace/index.ts
├── task/index.ts
├── playbook/index.ts          # 含 seedBuiltinPlaybooks
├── artifact/index.ts
├── workspace-asset/index.ts   # 含 search + task link
├── delivery/index.ts
├── intervention/index.ts
└── trigger/index.ts           # 含 fire
```

全部在 `web/src/client/api/index.ts` re-export。

### 4.4 数据库表

16 张新表 + 1 个 ALTER：

| 表名 | 模块 | 用途 |
|------|------|------|
| server_app_workspace | workspace | 空间主表 |
| server_app_workspace_member | workspace | 成员 |
| server_app_workspace_resource | workspace | 资源绑定 |
| server_app_workspace_conv_link | workspace | 会话↔空间映射 |
| server_app_task | task | 任务主表 |
| server_app_task_relation | task | 任务关系（spawned_by/escalated_to/blocked_by） |
| server_app_playbook | playbook | 剧本主表 |
| server_app_playbook_version | playbook | 剧本版本 |
| server_app_artifact | artifact | 产出物主表 |
| server_app_artifact_version | artifact | 产出物版本 |
| server_app_workspace_asset | workspace_asset | 沉淀资产主表 |
| server_app_workspace_asset_version | workspace_asset | 资产版本 |
| server_app_task_asset_link | workspace_asset | Task↔Asset 链接 |
| server_app_delivery | delivery | 投递记录 |
| server_app_intervention | intervention | 介入记录 |
| server_app_trigger_source | trigger | 触发源 |
| gpts_conversations.workspace_id | conversation | ALTER 加列（NULL for legacy） |

DDL 在 `assets/schema/derisk.sql` 末尾，运行时也会通过 `create_all()` 自动建表。

---

## 5. 内置 Playbook 示例

文件：`packages/derisk-serve/src/derisk_serve/playbook/builtin_examples.py`

可通过 `POST /api/v1/serve_playbook_service/playbooks/seed_builtin?workspace_id=X` 一键导入（幂等，按 name 去重）。前端 Playbooks 页有 "Seed Built-in Examples" 按钮。

### 5.1 数据运营周报

```yaml
name: Data Operations Weekly Report
scenario_type: data_ops
task_type: routine
trigger:
  type: timer
  cron: "0 9 * * 1"   # 每周一 9 点
skills: [db_query_skill, report_skill]
context:
  assets_required:
    - { type: historical_artifact, query: "type=weekly_report LIMIT 1" }
  resources:
    - { ref: "resource:prod_core_db" }
deliverables:
  - type: report
    delivery:
      - { category: notify, channel: email, target: ops-team@company.com }
distill:
  forced: true
  produce:
    - { type: historical_artifact, from: deliverable.0 }
```

### 5.2 SRE 容量巡检

```yaml
name: SRE Capacity Inspection
scenario_type: sre
task_type: routine
trigger:
  type: timer
  cron: "0 2 * * *"   # 每天 2 点
skills:
  - db_query_skill
  - baseline_compare_skill
  - anomaly_detect_skill
  - report_skill
context:
  assets_required:
    - { type: historical_artifact, query: "type=capacity_report LIMIT 1" }
  resources:
    - { ref: "resource:monitor_db" }
    - { ref: "resource:prod_cn1" }
deliverables:
  - type: report
    delivery:
      - { category: notify, channel: feishu, target: oncall_group }
distill:
  forced: true
  produce:
    - { type: historical_artifact, from: deliverable.0 }
    - { type: case, from: deliverable.0, when: "anomalies_detected == true" }
```

---

## 6. 关键文件清单

### 6.1 新建后端（8 个 serve 模块）

```
packages/derisk-serve/src/derisk_serve/
├── workspace/{__init__,config,serve}.py
├── workspace/api/{__init__,endpoints,schemas}.py
├── workspace/models/{__init__,models}.py
├── workspace/service/{__init__,service}.py
├── workspace/context_builder.py
├── task/...（同上结构）
├── playbook/... + builtin_examples.py
├── artifact/...
├── workspace_asset/...
├── delivery/...
├── intervention/...
└── trigger/...
```

### 6.2 修改后端

| 文件 | 改动 |
|------|------|
| `packages/derisk-app/src/derisk_app/initialization/serve_initialization.py` | scan_serve_configs 加 8 个模块；注册 8 个 Serve |
| `packages/derisk-serve/src/derisk_serve/conversation/api/schemas.py` | ServeRequest 加 workspace_id 字段 |
| `packages/derisk-serve/src/derisk_serve/conversation/api/endpoints.py` | dialogue_new 接受 workspace_id 查询参数，link_conversation |
| `packages/derisk-serve/src/derisk_serve/agent/agents/chat/agent_chat.py` | aggregation_chat 注入 workspace_context 到 system prompt |
| `assets/schema/derisk.sql` | 追加 16 张表 DDL + gpts_conversations.workspace_id 列 |

### 6.3 新建前端

```
web/src/app/workspaces/page.tsx
web/src/app/workspaces/[id]/page.tsx
web/src/app/workspaces/[id]/{tasks,playbooks,artifacts,assets,resources,interventions,settings}/page.tsx
web/src/app/workspaces/[id]/tasks/[tid]/page.tsx
web/src/app/workspaces/[id]/playbooks/[pid]/page.tsx
web/src/app/me/page.tsx
web/src/client/api/{workspace,task,playbook,artifact,workspace-asset,delivery,intervention,trigger}/index.ts
web/src/locales/{en,zh}/workspaces.ts
```

### 6.4 修改前端

| 文件 | 改动 |
|------|------|
| `web/src/client/api/index.ts` | re-export 8 个新模块 |
| `web/src/client/api/request.ts` | newDialogue 带 workspace_id 查询参数 |
| `web/src/components/layout/side-bar.tsx` | 加 workspaces + me 侧栏入口（TeamOutlined/UserOutlined） |
| `web/src/components/chat/content/home-chat.tsx` | 两处 newDialogue 调用带 workspace_id |
| `web/src/app/chat/page.tsx` | chat 调用 ext_info 注入 workspace_id |
| `web/src/types/chat.ts` | NewDialogueParam 加 workspace_id 字段 |
| `web/src/locales/{en,zh}/index.ts` | 注册 workspaces |

---

## 7. 端到端验证清单

### 7.1 MVP 核心闭环

- [ ] 创建 workspace → `server_app_workspace` 有记录，`server_app_workspace_member` 自动加 owner
- [ ] `/workspaces` 列表只显示当前用户加入的空间
- [ ] `/workspaces/{code}` 页面加载 workspace + iframe chat + 右侧栏
- [ ] workspace-aware chat 发消息 → `gpts_conversations.workspace_id` 正确落库（通过 conv_link 映射）
- [ ] 切换 workspace 后 chat 上下文跟着切（不同 app_code、不同会话列表）
- [ ] 资源管理页能绑定现有 `connect_config` 数据源
- [ ] 创建 Playbook（JSON DSL）通过 schema 校验
- [ ] Playbooks 页 "Seed Built-in Examples" 一键导入两个示例
- [ ] Playbook 编辑器 "Fire Task" 创建 Task（pending_trigger 状态）
- [ ] Task 详情 5 个 tab 正确展示产出物/投递/介入/关联资产
- [ ] Task close 前强制 distill，未完成返回 E4091
- [ ] distill 完成后 Asset 库有新记录（historical_artifact）
- [ ] 第二次跑同类 Task，Agent system prompt 包含上次 Asset（专精注入生效）
- [ ] Review 介入触发后侧栏"待我处理"出现，resolve 后 Task 能继续

### 7.2 回归测试

- [ ] 现有 HomeChat（`/`）能正常聊天
- [ ] 现有 Application Builder（`/application/app`）能正常配置 Agent
- [ ] 现有 `gpts_conversations` 不带 workspace_id 时行为与改动前一致（NULL，老对话不受影响）
- [ ] 现有 Agent / Skill / MCP / Knowledge Vault / DataResource 模块功能不受影响
- [ ] 现有 `derisk_serve.asset`（知识库搜索）模块不受影响

### 7.3 启动验证

```bash
# 后端
cd packages/derisk-app && python -m derisk_app
# 8 个新 serve 自动注册，16 张新表通过 before_start() 的 create_all() 自动建表

# 前端
cd web && yarn dev
# 侧栏出现 Workspaces / My View 入口
```

---

## 8. 明确不做（留给 MVP 之后）

| 项 | 原因 |
|----|------|
| Execute delivery（重启/部署/改配置） | SME 不敢用，需要审计与回滚机制 |
| Host delivery（5 种托管运行时） | 工程量过大，ROI 不明 |
| Playbook 自演化 | ROI 不明，等 MVP 数据 |
| SkillBundle 表 | 直接用 skill 引用够用 |
| 多 Agent 协作 | 一个通用 Agent + Skill 够用 |
| 6 种介入模式 | 只做 review，其他 5 种等需求 |
| Asset 语义子类型（metric/dimension/lineage/catalog） | 太复杂，historical_artifact + case 够用 |
| 跨空间 Asset 共享 / 提升 | 单空间够用 |
| Personal Sandbox / Builder Console | SME 不需要 |
| RBAC `workspace` 资源类型扩展 | 成员表判断够用 |
| Playbook gates（v1 不做介入触发，只做 close 时校验） | 简化 |
| Prompt 注入的复杂 RAG | MVP 只做"空间记忆摘要 + 历史同类 Task" |
| Timer trigger 自动注册到 CronService | MVP 靠外部 cron 调用 fire 端点，后续接入 |

---

## 9. 后续衔接

MVP 上线后，根据两个 design partner 的真实使用数据决定下一步：

- 如果验证"**强制 distill**"有价值 → 投入 Execute delivery（让 SME 也能自动操作）
- 如果验证"**空间记忆**"有价值 → 投入 Playbook 自演化（根据 Asset 库自动优化 DSL）
- 如果验证"**workspace-aware chat**"有价值 → 投入 Host delivery（看板托管）

**不要在 MVP 数据出来前提前投入这些方向。**

---

## 10. 设计决策时间线（关键讨论结论）

1. **场景选择**：中小企业的数据运营 + SRE 场景，不做大企业复杂场景
2. **并存而非替换**：现有模块是 Workspace 层的原子能力，全部保留
3. **技术栈**：Python（FastAPI 后端）+ TypeScript（Next.js 前端），与现有一致
4. **MVP 一次性交付**：不分阶段，9 大块一次性完成（用户明确要求"体现设计和思路的完整可用版本"）
5. **asset 命名冲突**：MVP 沉淀资产模块命名为 `workspace_asset`，避免与现有 `asset`（知识库搜索）冲突
6. **不动 chat_history**：用 `server_app_workspace_conv_link` 映射表，保护现有 chat 数据
7. **iframe 复用 chat**：不重写 chat 组件，iframe 嵌入 + 查询参数透传
8. **Service 类名修复**：原 workspace/task/playbook/artifact 的 endpoints.py 错误导入 `Service`（实际类名是 WorkspaceService/TaskService/...），MVP 实现时一并修复为 `as Service` 别名

---

## 附录 A：API 端点速查

### Workspace
- `POST /api/v1/serve_workspace_service/workspaces/{create,list,update,archive}`
- `GET  /api/v1/serve_workspace_service/workspaces/info?workspace_code=`
- `POST /api/v1/serve_workspace_service/members/{list,add,remove,update_role}`
- `POST /api/v1/serve_workspace_service/resources/{list,add,remove,update}`
- `POST /api/v1/serve_workspace_service/conversations/{link,list}`
- `GET  /api/v1/serve_workspace_service/conversations/lookup?conv_uid=`

### Task
- `POST /api/v1/serve_task_service/tasks/{create,list,update}`
- `GET  /api/v1/serve_task_service/tasks/info?task_id=`
- `POST /api/v1/serve_task_service/tasks/{id}/{start,close,archive,spawn}`

### Playbook
- `POST /api/v1/serve_playbook_service/playbooks/{create,list,update,validate,seed_builtin}`
- `GET  /api/v1/serve_playbook_service/playbooks/info?playbook_id=`
- `POST /api/v1/serve_playbook_service/playbooks/{id}/delete`
- `GET  /api/v1/serve_playbook_service/playbooks/{id}/versions`

### Artifact
- `POST /api/v1/serve_artifact_service/artifacts/{create,list,update}`
- `GET  /api/v1/serve_artifact_service/artifacts/info?artifact_id=`
- `GET  /api/v1/serve_artifact_service/artifacts/{id}/versions`

### Workspace Asset
- `POST /api/v1/serve_workspace_asset_service/assets/{create,list,update,search}`
- `GET  /api/v1/serve_workspace_asset_service/assets/info?asset_id=`
- `GET  /api/v1/serve_workspace_asset_service/assets/{id}/versions`
- `POST /api/v1/serve_workspace_asset_service/assets/link_task`
- `GET  /api/v1/serve_workspace_asset_service/assets/task_links?task_id=`

### Delivery
- `POST /api/v1/serve_delivery_service/deliveries/{create,list}`
- `GET  /api/v1/serve_delivery_service/deliveries/info?delivery_id=`
- `POST /api/v1/serve_delivery_service/deliveries/{id}/send`

### Intervention
- `POST /api/v1/serve_intervention_service/interventions/{create,list}`
- `GET  /api/v1/serve_intervention_service/interventions/info?intervention_id=`
- `POST /api/v1/serve_intervention_service/interventions/{id}/{resolve,abort}`

### Trigger
- `POST /api/v1/serve_trigger_service/triggers/{create,list,update}`
- `GET  /api/v1/serve_trigger_service/triggers/info?trigger_id=`
- `POST /api/v1/serve_trigger_service/triggers/{id}/delete`
- `POST /api/v1/serve_trigger_service/triggers/fire`

---

## 附录 B：Task 状态机

```
                  ┌──────────────────────────────────────────────┐
                  ↓                                              │
draft ──→ pending_trigger ──→ running ──→ delivered ──→ closed ──→ archived
                              │  ↑                                  ↑
                              │  └──────────────┐                   │
                              ↓                 │                   │
                         awaiting_human ───────┘                   │
                              │                                       │
                              ↓                                       │
                           blocked ──────────────────────────────────┘
                              │
                              ↓
                            failed
```

`close` 端点强制校验：所有关联 intervention 必须 resolved + distillation_json 非空，否则返回 `E4091`。
