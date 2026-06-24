# 场景空间架构设计（Scenario Workspace）

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-06-24 |
| 作者 | yhjun1026 + Claude |
| 关联 RFC | RFC-004（Scene Profile）、RFC-005 ~ RFC-010（待立项） |

---

## 0. 文档定位

本文档是 OpenDerisk 从"Agent 配置平台"演进为"场景化 AI 团队空间"的总体设计与落地蓝图。目标读者：架构 / 后端 / 前端 / 产品。读完应能回答：

1. 场景空间是什么、由什么组成、怎么运转、怎么进化
2. 哪些复用现有能力（Agent / Skill / MCP / DataResource / Scheduler / Channels），哪些必须新增
3. 数据模型、API、前端 IA 长什么样
4. 分几个阶段落地，每阶段交付什么、能验证什么

实施层面更细的机制（Playbook DSL、Asset 模型、Task 状态机等）将拆为独立 RFC（见第 14 节路线图），本文档只锁定方向与边界。

---

## 1. 用户视角：用户进入系统看到什么

> 本章回答一个具体问题：一个普通用户（不是 Builder、不是管理员）登录 OpenDerisk 后，看到的世界是什么样的。

### 1.1 核心立场

**场景空间是组织/团队的工作单元，不是个人的。** 但用户作为"参与者"会同时存在于多个空间中，每个用户还有一个轻量的"个人视图"作为跨空间的入口。

回顾第 0 章的命题：本地工具（Claude Code / Hermes）在"个人单机"场景上对云端服务是降维打击。所以 OpenDerisk **不把"个人空间"作为产品主轴**，但保留一个**"我的视图"**（My View）作为跨空间的总入口——它是过滤器，不是独立的 Workspace 实体。

### 1.2 用户的 Workspace 关系

```
用户 User
  │
  ├── 我的视图（My View）= 跨空间聚合，非实体
  │   - 我在哪些空间
  │   - 各空间里待我处理的介入
  │   - 我发起/参与的任务
  │   - 我最近的产出
  │
  ├── 加入的 Workspace（多对多，按角色）
  │   - SRE 应急空间（contributor）
  │   - 数据运营空间（approver）
  │   - 容量巡检子空间（owner）
  │   - ...
  │
  └── Personal Sandbox（可选，仅 Builder 角色开启）
      - 用户私有空间，用于 prototype Agent / 试验 Playbook
      - 验证后可"发布"到团队空间
      - 默认不开启，按需申请
```

**关键设计取舍**：

| 问题 | 取舍 | 理由 |
|---|---|---|
| 一个用户能加入多个空间吗？ | **能**，多对多关系，每个空间有独立角色 | 用户在现实工作中跨团队、跨场景是常态 |
| 用户有"个人空间"吗？ | **默认没有**；只有 Builder 角色可申请 Personal Sandbox | 个人主轴是伪命题，但 Builder 需要 prototype 场所 |
| 是否支持"小团队单空间"？ | **支持**，3-5 人小团队 Workspace type=`team`，无场景类型约束 | 创业团队/小部门场景，空间最小单元 |
| 谁能创建空间？ | admin / 有 `workspace.creator` 权限的角色 | 防止空间碎片化；普通用户只能加入 |
| 空间能被归档吗？ | **能**，归档后只读，资产保留可检索 | 场景结束时归档而非删除 |

### 1.3 登录后的默认路径

```
登录
  ↓
判断用户角色
  ├── 普通用户（contributor/approver）
  │     ↓
  │   上次活跃的 Workspace？
  │     ├── 是 → /workspaces/{last_active_id}（空间首页 = workspace-aware chat）
  │     └── 否 → /workspaces（我加入的空间列表）
  │
  └── Builder（开了 Personal Sandbox）
        ↓
      上次活跃的 Workspace？
        ├── 是 → /workspaces/{last_active_id}
        └── 否 → /workspaces（列表顶部显示 Personal Sandbox + 加入的团队空间）
```

### 1.4 Chat 是 workspace 的主入口，不是退化子页

> **关键修正**：早期设计把 HomeChat 退化为"workspace 内的子页"，这是错的。Agentic 时代 chat 是 THE interface——用户通过 chat 发起任务、查询进展、订阅能力、触发介入。**chat 不是和 workspace 并列的另一个 UI，chat 是 workspace 的主入口**。

**workspace-aware chat 的特征**（这是 P1-P2 验证的核心标准）：

| 用户在 chat 里说的话 | chat 应该做什么 |
|---|---|
| "跑一次容量巡检" | 创建 Task，匹配 Playbook，触发执行 |
| "我有哪些任务在进行" | 查询当前 workspace 的 Task 列表回答 |
| "上次巡检的报告在哪" | 检索 Asset 库返回 historical_artifact |
| "帮我订阅容量巡检 Skill 包" | 配置 SkillBundle 挂载 + 设置 Trigger |
| "这个 Approve 我同意" | 解锁 HumanIntervention，Task 继续 |
| "这个异常升级到应急" | 派生 Incident Task，关联为子任务 |
| "把这份报告发给 SRE 组" | 创建 Notify 类 Delivery |

**判断 P1-P2 成功的正确标准**：

- ❌ 错误标准："用户是否使用 workspace UI 而非 chat"
- ✅ 正确标准："用户的 chat 是否 workspace-aware（能创建 Task、查询进展、引用 Asset、触发介入、配置 Trigger）"

如果用户用 chat 但每次从零开始（像用 ChatGPT 一样），那是失败；如果用户用 chat 且 chat 自动感知 workspace 上下文（任务/Asset/Playbook/资源），那是成功。

**前端实现要点**：workspace 首页就是 workspace-aware chat + 侧栏（待办/任务/产出）。不是"工作台 + 单独的 chat 子页"。chat 旁边常驻侧栏展示当前 workspace 的状态，用户可以一边聊一边看任务进展。

### 1.5 空间切换

三种切换方式，覆盖不同场景：

1. **顶部空间切换器**（全局）：所有页面顶部一个下拉，列出"我加入的空间 + Personal Sandbox（如有）"，点击直接切。当前空间名常驻显示。这是主切换入口。
2. **"我的视图"入口**（全局）：顶部一个"我的"图标，进入跨空间聚合视图。这里不是某个空间，是"所有空间里关于我的事"。用户在这里看到所有空间的待办、任务、产出，可以跳转到具体空间处理。
3. **空间内 deeplink**：来自通知（飞书/邮件/站内）的链接，带 `workspace_id` + `task_id` / `intervention_id`，直接跳到目标位置。这是事件驱动的入口。

**切换的体验原则**：空间切换是"上下文切换"不是"页面跳转"。切换后 chat 的 workspace 上下文、侧栏的任务列表、可见的 Skill/Asset/Playbook 全部跟着切。用户始终知道自己"在哪个空间里和 Agent 对话"。

### 1.6 "我的视图"具体长什么样

```
┌─────────────────────────────────────────────────┐
│ 我的视图（跨空间聚合）                           │
├─────────────────────────────────────────────────┤
│ 待我处理（跨所有空间）                           │
│  - [SRE 空间] task_123 应急复盘 Review (2h)     │
│  - [数据运营] intervention_45 月报对账 Reconcile │
│  - [SRE 空间] intervention_46 上线 gate Approve │
├─────────────────────────────────────────────────┤
│ 我发起的任务                                     │
│  - [数据运营] 临时分析 Q3 GMV 异常  running     │
│  - [SRE 空间]   线上定位 redis 慢查询  closed   │
├─────────────────────────────────────────────────┤
│ 我参与的产出                                     │
│  - [数据运营] Q3 经营报表 v2 (我 Attest)        │
│  - [SRE 空间]   容量巡检报告 06-24 (我 Review)  │
├─────────────────────────────────────────────────┤
│ 我加入的空间                                     │
│  - SRE 应急空间     12 成员 / 5 Agent / 38 任务 │
│  - 数据运营空间      8 成员 / 4 Agent / 22 任务 │
│  - 容量巡检子空间    3 成员 / 2 Agent / 15 任务 │
└─────────────────────────────────────────────────┘
```

"我的视图"不是空间，是聚合过滤器。它的价值是：**用户不需要挨个空间翻待办**，所有需要他处理的事在一处。这是"用户视角"在产品里的具体落地。

### 1.7 角色与可见性

空间内角色（复用 RBAC，与 `feature_plugins/permissions/` 对齐）：

| 角色 | 能做什么 |
|---|---|
| **Owner** | 空间设置、成员管理、删空间、归档 |
| **Contributor** | 发起任务、参与 Playbook 执行、产出 Artifact |
| **Approver** | Contributor 权限 + 审批介入权（Approve/Attest） |
| **Viewer** | 只读，看任务/产出/资产，不参与 |

**跨空间角色**（组织级）：

| 角色 | 能做什么 |
|---|---|
| **Admin** | 创建空间、管理组织级 Agent 库、看全局审计 |
| **Workspace Creator** | 创建空间（但不能管全局） |
| **Builder** | 可申请 Personal Sandbox、发布 Agent 到组织库 |
| **User** | 默认，只能加入空间 |

### 1.8 Builder 的特殊路径

Builder 在产品里有一条独立路径，但**不是产品的默认叙事**：

```
Personal Sandbox（Builder 私有）
  ↓ 在此 prototype Agent / 试验 Playbook
  ↓ 验证通过
发布到
  ↓
组织级 Agent 库 / Playbook 模板库
  ↓ 其他 Workspace 订阅
  ↓
团队 Workspace 使用
```

Builder Console（现有 `application/app/` 改造）从"我的视图"或顶部"开发者"入口进入，是次级路径。普通用户看不到 Builder Console。

### 1.9 隐私与边界

- **Personal Sandbox 是私有的**：里面的 Agent / Playbook / Asset 只有 Builder 自己可见。发布到组织库才对其他空间可见。
- **Workspace 内的产出默认对成员可见**：成员能看到所有 Task / Artifact / Asset，但能操作的权限由角色决定。
- **跨空间隔离**：Workspace A 的 Asset 默认 Workspace B 看不到，除非通过组织级 Asset 提升（P8 阶段）。
- **个人痕迹保护**：用户在空间内的活动（介入记录、产出归属）归空间所有；用户离开空间后活动记录保留，但用户身份脱敏（按合规要求）。

### 1.10 用户视角的设计原则总结

| 原则 | 含义 |
|---|---|
| **空间是工作单元，不是个人容器** | 个人主轴是伪命题，空间贴场景/团队 |
| **用户是参与者，多空间并行** | 一个用户加入多个空间，按角色参与 |
| **"我的视图"是聚合器，不是空间** | 跨空间待办/任务/产出一处可见 |
| **Chat 是 workspace 的主入口** | workspace-aware chat 是首页，不是退化子页；P1-P2 验证 chat 是否 workspace-aware |
| **切换是上下文切换** | 顶部切换器 + 我的视图 + deeplink 三种入口 |
| **Builder 路径独立** | Personal Sandbox + Builder Console 是次级路径 |
| **空间内成员可见，跨空间隔离** | 隐私边界清晰 |
| **SkillBundle 是能力载体，非 Agent 订阅** | 一个强 Agent + 多 SkillBundle 适配场景，不需要订阅多个 Agent |

---

## 2. 背景与问题

### 2.1 现状

OpenDerisk 当前的信息架构以 `gpts_app_config`（Agent 应用）为脊柱：用户登录后第一屏是 HomeChat，所有功能模块（application / knowledge-vault / models / database / mcp / agent-skills）都围绕"如何配置和使用一个 Agent"展开。已有能力包括：

- **Agent 体系**：`derisk-core/agent/` 提供多 Agent 协作、记忆、计划、看板；`derisk-serve/agent/` 提供 App 管理、版本、发布
- **Skill 系统**：可复用的能力封装（`derisk_serve.skill`）
- **MCP 集成**：`derisk_serve.mcp` 已支持外部 MCP server 注册与调用
- **DataResource**：`connect_config` / `db_spec` / `table_spec` / `db_learning_task` 数据源与数据学习任务
- **Scheduler**：`derisk_app/initialization/scheduler.py`（APScheduler）
- **Channels**：`derisk-core/agent/channels/` 已具备多渠道接入能力
- **Knowledge Vault**：L0/L1/L2 三层知识 + Space 概念（`web/src/app/knowledge-vault/`）
- **RBAC**：`feature_plugins/permissions/` 已落地（commit `d0e8d67d`）
- **Hook 系统**：RFC-001 已立项落地

### 2.2 问题

1. **Agent-centric 而非 Work-centric**：用户心智是"我要完成的事"，产品叙事是"我有什么 Agent"——错位
2. **任务之间孤立**：`gpts_conversations` 之间无关联，跑一万次也不会"越来越懂这个团队"
3. **产出物混在对话里**：没有独立的 Artifact 实体，无法版本化、无法分发、无法复用
4. **SOP 在代码里**：multi-agent 协作流程 hardcode 在代码中，无法由用户/场景自定义
5. **Agent 归属模糊**：`gpts_app_config.creator` 是字符串列，无硬性所有权，无法支撑"团队空间内私有 / 跨空间订阅"
6. **人介入被动**：人只在 Agent 主动请求时出现，无显式介入点，介入结果不沉淀
7. **执行轨迹散落**：`gpts_plans` / `gpts_kanban` / `gpts_work_log` 各自为政，无 Task 维度聚合视图

### 2.3 命题

> **OpenDerisk 是面向场景的 AI 团队空间平台。每个空间是一个组织单元（按场景/任务域划分），人与 Agent 按剧本协作完成任务，沉淀的知识、口径、模板、案例让团队在同类场景下越来越高效。**

"个人空间"不是主轴（本地工具如 Claude Code 在单机场景对云端服务是降维打击）。场景空间贴的是**场景/任务域**，不是部门。

---

## 3. 设计原则

| 原则 | 含义 | 反例 |
|---|---|---|
| **场景优先于通用** | 先在一个场景（SRE / 数据运营）跑通再泛化；不为想象中的场景做抽象 | 一上来做"通用 Playbook 模板市场" |
| **剧本优先于资源** | 空间管理 Playbook，Playbook 引用 Agent/Skill/MCP；资源层保持现状不重复造 | 空间直接管 Agent 列表，每次任务重新组装 |
| **沉淀优先于产出** | Task 完成必须强制沉淀 Asset；不沉淀的产出等于没产出 | 默认所有 chat_history 都进 Asset 库 |
| **介入显式化** | 人的介入点由 Playbook 声明，介入结果强制回流到 Asset | 人被动响应 Agent 请求，纠正内容不记录 |
| **复用而非重写** | Agent / Skill / MCP / Knowledge / Scheduler / Channels 保持现状，空间层只在其上加编排与沉淀 | 把 agent 体系搬到 workspace 模块下重写 |
| **统一 Task 入口** | 定时 / Webhook / 告警 / 主动 四种触发都进同一 Task 模型，触发源是字段不是类型 | 按触发源分四套 Task 表 |
| **声明式剧本** | Playbook 用 DSL 描述，可版本化、可 diff、可回滚 | 用 Python 代码写工作流 |
| **不做什么写明** | 见第 16 节 | —— |

---

## 4. 整体架构

### 4.1 分层

```
┌─────────────────────────────────────────────────────────┐
│ Frontend                                                │
│ Scenario Workspace Shell (Next.js, 复用现有 web/)       │
│ - Workspace 首页 / Task 详情 / Playbook 编辑器          │
│ - Artifact 库 / Asset 库 / 介入中心                     │
├─────────────────────────────────────────────────────────┤
│ API Layer (derisk_app/openapi/api_v2/)                  │
│ 新增: workspace_api / task_api / playbook_api /         │
│       artifact_api / asset_api / delivery_api /         │
│       intervention_api                                  │
├─────────────────────────────────────────────────────────┤
│ New Serve Layer (packages/derisk-serve/src/derisk_serve)│
│ workspace / task / playbook / artifact / asset /        │
│ delivery / intervention                                 │
├─────────────────────────────────────────────────────────┤
│ Existing Resource Layer (REUSED, 不动)                  │
│ agent / skill / mcp / knowledge / conversation /        │
│ datasource / scheduler / channels / hook                │
├─────────────────────────────────────────────────────────┤
│ Engine (derisk-core)                                    │
│ Agent / Operator / Flow / Memory / Sandbox              │
└─────────────────────────────────────────────────────────┘
```

### 4.2 与现有 `gpts_app_config` 的关系

**不推翻，叠加**：

- `gpts_app_config` 保持为 Agent 定义实体，新增 `owner_user_id`（迁移自 `creator` 字符串）、`workspace_id`（可空，归属的空间）
- `gpts_conversations` 新增 `task_id`（可空），所有对话挂到 Task 下
- `gpts_plans` / `gpts_work_log` 新增 `task_id`，被 Task 聚合
- Agent 不再是产品主轴，但仍是一等公民——只是被 Playbook 引用而非被用户直接面对

### 4.3 关键边界

| 边界 | 跨边界契约 |
|---|---|
| 空间层 ↔ 资源层 | 空间只通过 Playbook 引用资源；资源层不知道空间存在 |
| 空间层 ↔ 引擎层 | Task 执行通过现有 `derisk_serve.agent` 启动 AgentRun；空间层不直接调 Agent |
| Task ↔ Conversation | Task 1:N Conversation；Conversation 仍由现有 chat serve 管理，只多挂一个 `task_id` |
| Artifact ↔ Storage | Artifact 元数据在 DB，`content_ref` 指向对象存储（S3/MinIO/本地文件） |
| Playbook ↔ Hook | Playbook 的介入点通过现有 Hook 系统触发，不另造 hook 机制 |

---

## 5. 核心概念模型

### 5.1 实体关系总览

```
Workspace ─┬─ has Members (User + Role)
           ├─ owns WorkspaceResources ── (3 类，见 5.3)
           │              ├─ Generic Capability (Skill / SkillBundle / MCP / Model)
           │              ├─ Scenario-bound Physical (DataSource/Environment/Repo/...)
           │              └─ Scenario-specific Logical (SLO/OnCall/Pipeline/Dashboard)
           ├─ references Knowledge Spaces (作为 WorkspaceResource 的一种)
           ├─ owns Playbooks ── version ── PlaybookVersion
           │              (策略声明: skills + context + gates + deliverables)
           ├─ owns Tasks ─┬─ triggered_by TriggerSource
           │              ├─ runs Playbook (snapshot version)
           │              ├─ has AgentRuns (link to gpts_conversations)
           │              ├─ has HumanInterventions
           │              ├─ produces Artifacts ── version ── ArtifactVersion
           │              │              (含 operation_plan / operation_result / code_project 等类型)
           │              └─ has Deliveries ── (3 类，见 10.3)
           │                              ├─ Notify (email/feishu/...)
           │                              ├─ Publish (bi/repo/table/asset_library)
           │                              └─ Execute (action_executor: 重启/部署/回滚/...)
           └─ owns Assets ── version ── AssetVersion
                          ├─ (Process) Runbook / Case
                          ├─ (Semantic) Metric / Dimension / Catalog / Lineage
                          ├─ (Template) ReportTemplate / SqlTemplate
                          └─ (Output) HistoricalArtifact
```

> **范式说明**：旧设计的"AgentSubscription / Agent Marketplace"已移除。Agentic 时代是"一个强 Agent + 多 Skill 适配多场景"，不是"多 Agent 实例订阅"。空间通过挂载 **SkillBundle**（一组协同 Skill）获得场景能力，不通过订阅多个 Agent。详见 5.3。

### 5.2 九个一等实体

| 实体 | 角色 | 关键属性 |
|---|---|---|
| **Workspace** | 场景空间，组织单元 | `type=scenario/team`, `owner`, `default_agent` |
| **WorkspaceResource** | 空间内可管理的资源（3 类，见 5.3） | `type`, `physical_ref`, `config_json`, `access_mode` |
| **Task** | 一次需要被完成的工作，统一入口 | `type=routine/pipeline/incident/adhoc`, `triggered_by`, `playbook_id`, `status` |
| **Playbook** | **策略声明**（skills + context + gates + deliverables），非工作流脚本 | `scenario_type`, `trigger`, `declaration_dsl`, `version` |
| **AgentRun** | Agent 的一段执行，链接到现有 conversation | `task_id`, `conv_uid`, `triggered_gates[]` |
| **Artifact** | Task 的产出物（含报告/数据/代码/操作计划/操作结果） | `type`, `content_ref`, `version`, `provenance` |
| **Delivery** | 产出物的分发动作（含通知/发布/执行三类） | `category`, `channel`, `target`, `format`, `status` |
| **Asset** | 空间沉淀的可复用资产 | `type`, `scope=workspace/org`, `source_task_id` |
| **HumanIntervention** | 人的介入记录 + 强制沉淀 | `type`, `decision`, `distillation`, `linked_asset_id` |

### 5.3 WorkspaceResource：空间的三类资源

> SRE 空间管线上环境，数据运营空间管来源库/数仓——这些都是空间资源。统一用 `workspace_resource` 表表达，物理资源仍归各自 serve 模块，空间只做引用 + 配置 overlay。

| 类别 | 例子 | 物理归属 | 空间层角色 |
|---|---|---|---|
| **① 通用能力资源** | **Skill / SkillBundle** / MCP server / LLM Model / Embedder | 全局（现有 serve 模块） | 空间"挂载"，SkillBundle 是场景能力的核心载体 |
| **② 场景绑定物理资源** | 数据源（DB/数仓）、生产环境（K8s 集群/命名空间）、代码仓库、API endpoint | 全局有物理注册（`connect_config` 等），但需空间视图 | 空间引用 + 空间特化配置（显示名/访问模式/默认用于哪个 Playbook） |
| **③ 场景专属逻辑资源** | SLO 定义、on-call 轮值、数据流水线、BI 看板、runbook 目标对象 | 无全局注册，本质属于空间 | 空间内自建，type-specific JSON 配置 |

**关键变化（Agentic 范式）**：
- **SkillBundle 是空间能力的核心单位**：一个空间挂载"SRE 容量巡检 SkillBundle"就具备这个场景的能力——Bundle 内含一组协同 Skill（db_query / baseline_compare / anomaly_detect / report）。Agent 读 Skill 自描述编排，不需要为每个场景造一个 Agent。
- **Agent 不再是空间订阅的资源**：空间只配置 `default_agent`（用哪个通用 Agent 跑），不"订阅多个 Agent"。一个强 Agent + 不同 SkillBundle 适配所有场景。
- **MCP / Model 仍是空间资源**：但定位是"工具/底座"，不是"场景能力"——场景能力由 SkillBundle 表达。

**统一模型**：`workspace_resource` 表，`type` 区分类别，`physical_ref` 指向全局物理实体（类别 ②用），`config_json` 装空间特化配置（类别 ②③都用）。

**与现有表的关系**：
- `connect_config`（数据源）保持全局物理注册不变；空间通过 `workspace_resource(type=data_source, physical_ref=connect_config.id)` 引用
- `workspace_knowledge_link` 统一并入 `workspace_resource(type=knowledge_space, physical_ref=knowledge_space_id)`
- **`agent_subscription` 表删除**——空间配置 `default_agent` 字段即可，不需要订阅关系表
- **新增 `workspace_resource(type=skill_bundle)`**——SkillBundle 是 Skill 的集合，物理 ref 指向 Skill 注册表的 bundle id
- 类别 ③ 没有 physical_ref，纯靠 `config_json`

这样空间资源有统一入口，但**不重造物理资源层**——物理注册仍在各自 serve 模块，空间只做"引用 + 视图 + 配置 overlay"。详见 6.9。

---

## 6. 数据模型设计

> 本节给核心表的字段定义。完整 DDL 在实施时按 RFC 拆分，每个 RFC 给对应迁移脚本。所有表带 `id / created_at / updated_at / created_by / updated_by` 标准列，下文省略。

### 6.1 Workspace

```sql
CREATE TABLE workspace (
  id BIGINT PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  description TEXT,
  type VARCHAR(32) NOT NULL,              -- scenario / team
  scenario_type VARCHAR(64),              -- sre / data_ops / compliance / ...
  owner_user_id BIGINT NOT NULL,
  default_agent_app_code VARCHAR(128),    -- 空间默认用哪个通用 Agent（不是订阅多个）
  settings_json JSON,                     -- default_llm, default_embedder, notification_channels
  is_archived BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (owner_user_id) REFERENCES user(id)
);

CREATE TABLE workspace_member (
  id BIGINT PRIMARY KEY,
  workspace_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  role VARCHAR(32) NOT NULL,              -- owner / contributor / approver / viewer
  joined_at TIMESTAMP,
  UNIQUE(workspace_id, user_id)
);

-- 注：workspace_knowledge_link 和 agent_subscription 已统一并入 workspace_resource（见 6.9）
-- 旧表保留兼容期后下线
```

**关键说明**：
- `default_agent_app_code` 是空间"用哪个 Agent"的配置，**不是订阅关系**。Agentic 时代一个强 Agent + 不同 SkillBundle 适配多场景，不需要订阅多个 Agent。
- `workspace_knowledge_link` 和 `agent_subscription` 旧表数据迁移到 `workspace_resource` 后下线。

### 6.2 Task

```sql
CREATE TABLE task (
  id BIGINT PRIMARY KEY,
  workspace_id BIGINT NOT NULL,
  parent_task_id BIGINT,                  -- 支持子任务 / 派生
  type VARCHAR(32) NOT NULL,              -- routine / pipeline / incident / adhoc
  title VARCHAR(256) NOT NULL,
  description TEXT,
  status VARCHAR(32) NOT NULL,            -- draft / pending_trigger / running / awaiting_human
                                          -- / blocked / delivered / closed / archived
  priority VARCHAR(16),
  triggered_by VARCHAR(32),               -- timer / webhook / alert / manual
  trigger_ref VARCHAR(128),               -- timer_id / webhook_id / alert_id
  playbook_id BIGINT,                     -- nullable for adhoc
  playbook_version_id BIGINT,             -- 锁定执行时的剧本版本
  created_by_user_id BIGINT,
  assigned_agents_json JSON,              -- [app_code, ...]
  context_json JSON,                      -- 任务级上下文（初始输入、参数）
  due_at TIMESTAMP,
  started_at TIMESTAMP,
  closed_at TIMESTAMP,
  FOREIGN KEY (workspace_id) REFERENCES workspace(id),
  FOREIGN KEY (playbook_id) REFERENCES playbook(id)
);

CREATE TABLE task_relation (
  parent_task_id BIGINT NOT NULL,
  child_task_id BIGINT NOT NULL,
  relation_type VARCHAR(32),              -- spawned_by / escalated_to / blocked_by
  PRIMARY KEY(parent_task_id, child_task_id)
);

-- 改造现有表（迁移脚本）
ALTER TABLE gpts_conversations ADD COLUMN task_id BIGINT;
ALTER TABLE gpts_app_config ADD COLUMN workspace_id BIGINT;
ALTER TABLE gpts_app_config ADD COLUMN owner_user_id BIGINT;
ALTER TABLE gpts_plans ADD COLUMN task_id BIGINT;
ALTER TABLE gpts_work_log ADD COLUMN task_id BIGINT;
```

### 6.3 Playbook

```sql
CREATE TABLE playbook (
  id BIGINT PRIMARY KEY,
  workspace_id BIGINT NOT NULL,
  name VARCHAR(128) NOT NULL,
  scenario_type VARCHAR(64) NOT NULL,
  task_type VARCHAR(32) NOT NULL,         -- routine / pipeline / incident / adhoc
  trigger_json JSON,                      -- 触发条件（timer/webhook/alert/manual）
  declaration_dsl_json JSON NOT NULL,     -- 策略声明 DSL（skills/context/gates/deliverables/distill），见第 7 节
  current_version INT NOT NULL DEFAULT 1,
  is_active BOOLEAN DEFAULT TRUE,
  created_by_user_id BIGINT NOT NULL
);

CREATE TABLE playbook_version (
  id BIGINT PRIMARY KEY,
  playbook_id BIGINT NOT NULL,
  version INT NOT NULL,
  declaration_dsl_json JSON NOT NULL,
  changelog TEXT,
  created_by_user_id BIGINT NOT NULL,
  created_at TIMESTAMP,
  UNIQUE(playbook_id, version)
);
```

> **注**：字段从 `workflow_dsl_json` 改为 `declaration_dsl_json`，反映从"工作流脚本"到"策略声明"的范式转变。不再单独存 `human_intervention_points / artifact_schema / delivery_schema`——这些都在 declaration DSL 的 `gates / deliverables` 块里表达。

### 6.4 AgentRun

```sql
CREATE TABLE agent_run (
  id BIGINT PRIMARY KEY,
  task_id BIGINT NOT NULL,
  parent_run_id BIGINT,                   -- 多轮迭代或子任务关系
  agent_app_code VARCHAR(128) NOT NULL,   -- 通常是 workspace.default_agent
  conv_uid VARCHAR(128),                  -- 链接现有 gpts_conversations
  skills_loaded_json JSON,                -- 本次运行加载的 Skill 清单（从 SkillBundle 解析）
  gates_triggered_json JSON,              -- 触发过的 gate 记录（gate_id / triggered_at / intervention_id）
  input_json JSON,
  output_json JSON,                       -- Agent 最终输出（含结构化字段供 gate condition 匹配）
  status VARCHAR(32),                     -- pending / running / awaiting_human / success / failed / aborted
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  FOREIGN KEY (task_id) REFERENCES task(id),
  FOREIGN KEY (conv_uid) REFERENCES gpts_conversations(conv_uid)
);
```

> **注**：移除 `playbook_step_id`——策略声明范式下没有"步骤"概念。新增 `skills_loaded_json`（记录实际加载的 Skill）和 `gates_triggered_json`（记录 gate 触发），用于 Playbook 演化分析。

### 6.5 Artifact & Delivery & Hosting

> **本节回应"面向最终交付构建空间"**：交付物不只是"发出去"，很多要在空间里被**托管、展示、部署运行**。SRE 的运维操作历史、运营的数据/报表、市场售前的 web 程序——都是空间要长期栖居的交付物。除 notify/publish/execute 三类 Delivery 外，新增 `host` 类（托管）。

```sql
CREATE TABLE artifact (
  id BIGINT PRIMARY KEY,
  task_id BIGINT NOT NULL,
  type VARCHAR(32) NOT NULL,              -- 见下方类型表（含 deliverable_app / dashboard / hosted_content 等可托管类型）
  title VARCHAR(256),
  content_ref VARCHAR(512),               -- s3://... / file://... / db://... / git://...
  content_text TEXT,                      -- 全文检索纯文本；operation_plan / app_manifest 存结构化 JSON
  current_version INT NOT NULL DEFAULT 1,
  created_by_agent VARCHAR(128),
  created_by_user BIGINT,
  provenance_json JSON,                   -- 输入、agent_runs、引用的 assets
  is_shared BOOLEAN DEFAULT FALSE,
  workspace_id BIGINT NOT NULL,
  hosting_status VARCHAR(16),             -- 托管状态：none / hosted / running / stopped / failed
  hosting_ref VARCHAR(512),               -- 托管后的访问入口（URL / 路由 / 容器 ID）
  FOREIGN KEY (task_id) REFERENCES task(id)
);

CREATE TABLE artifact_version (
  id BIGINT PRIMARY KEY,
  artifact_id BIGINT NOT NULL,
  version INT NOT NULL,
  content_ref VARCHAR(512),
  diff_summary TEXT,
  created_by VARCHAR(128),
  created_at TIMESTAMP,
  UNIQUE(artifact_id, version)
);

CREATE TABLE delivery (
  id BIGINT PRIMARY KEY,
  artifact_id BIGINT NOT NULL,
  task_id BIGINT NOT NULL,
  category VARCHAR(16) NOT NULL,          -- notify / publish / execute / host
  channel VARCHAR(32) NOT NULL,           -- notify: email/feishu/dingtalk/webhook/in_app
                                          -- publish: bi_dashboard/data_table/code_repo/file_store/asset_library
                                          -- execute: action_executor/downstream_playbook
                                          -- host: web_runtime/dashboard_viewer/data_explorer/doc_site
  target VARCHAR(512),                    -- 收件人 / 群 ID / URL / 下游 playbook_id / 托管路由
  format VARCHAR(32),                     -- pdf / excel / bi_link / message_card / git_diff / dry_run_preview / app_url
  status VARCHAR(32),                     -- pending / awaiting_approval / executing / sent / published
                                          -- / executed / failed / rolled_back / hosted / running / stopped
  require_intervention VARCHAR(16),       -- none / approve / attest（execute 类强制 approve）
  intervention_id BIGINT,                 -- 关联的 human_intervention
  rollback_delivery_id BIGINT,            -- execute 类失败时的回滚 delivery（自引用）
  scheduled_at TIMESTAMP,
  sent_at TIMESTAMP,
  result_json JSON,                       -- 投递结果 / 外部资产 ref / 执行结果 / 托管入口 URL
  FOREIGN KEY (artifact_id) REFERENCES artifact(id)
);

-- 托管实例表：记录每个被托管部署的交付物实例（一个 Artifact 可能有多个版本被托管）
CREATE TABLE artifact_hosting (
  id BIGINT PRIMARY KEY,
  artifact_id BIGINT NOT NULL,
  artifact_version_id BIGINT NOT NULL,
  workspace_id BIGINT NOT NULL,
  host_type VARCHAR(32) NOT NULL,         -- web_app / dashboard / data_explorer / doc_site / notebook / api_service
  access_url VARCHAR(512),                -- 托管后的访问 URL
  internal_route VARCHAR(256),            -- 空间内路由（如 /workspaces/{id}/hosted/{hid}）
  runtime_config_json JSON,               -- 端口/环境变量/资源限额/数据源连接
  status VARCHAR(16),                     -- deploying / running / stopped / failed / archived
  deployed_at TIMESTAMP,
  stopped_at TIMESTAMP,
  last_accessed_at TIMESTAMP,
  access_count INT DEFAULT 0,
  FOREIGN KEY (artifact_id) REFERENCES artifact(id)
);
```

**Artifact 类型说明（扩展版）**：

| type | 用途 | 可托管的交付形态 |
|---|---|---|
| `report` / `document` / `email_content` | 文档型产出（Notify） | 可托管为可浏览文档（doc_site） |
| `dataset` | 数据集产出 | 可托管为可探索数据表（data_explorer） |
| `dashboard` | 看板定义 | 可托管为空间内看板（dashboard_viewer） |
| `code_project` | 代码项目 | 可托管为可运行 web 程序（web_app） |
| **`deliverable_app`** | **可交付的 web 应用**（市场售前调研站、demo、内部工具） | **可托管部署运行**（web_runtime） |
| `operation_plan` | 操作计划（Execute，待执行） | 不托管 |
| `operation_result` | 执行结果记录 | 可托管为可查询运维历史 |
| `analysis` / `decision` | 分析结论/决策记录 | 可托管为可浏览分析报告 |
| **`notebook`** | 数据分析 notebook | 可托管为可交互运行环境 |

**关键说明**：

- **`hosting_status` / `hosting_ref`**：Artifact 表加托管状态字段，让"这个产出物现在是否在空间里跑着"一眼可见
- **`artifact_hosting` 表**：记录托管实例，一个 Artifact 可能有多个版本被托管（如售前 demo 的 v1/v2 并存）
- **`host_type` 决定运行时**：web_app 走容器化部署，dashboard 走渲染服务，data_explorer 走查询服务，notebook 走 Jupyter 内核
- **访问控制**：托管实例继承 workspace 成员 RBAC，外部访问需显式发布（生成带 token 的公开链接）
- **生命周期管理**：托管实例可停可启可归档，长期未访问的可自动归档释放资源





### 6.6 Asset

```sql
CREATE TABLE asset (
  id BIGINT PRIMARY KEY,
  workspace_id BIGINT NOT NULL,
  type VARCHAR(32) NOT NULL,              -- runbook / case / metric / dimension / catalog
                                          -- / lineage / report_template / sql_template
                                          -- / historical_artifact
  name VARCHAR(256) NOT NULL,
  description TEXT,
  scope VARCHAR(16) NOT NULL DEFAULT 'workspace', -- workspace / organization
  content_ref VARCHAR(512),
  content_text TEXT,
  current_version INT NOT NULL DEFAULT 1,
  source_task_id BIGINT,                  -- 由哪个 Task 沉淀而来
  tags_json JSON,
  is_published BOOLEAN DEFAULT FALSE,     -- 是否已提升为组织级
  created_by VARCHAR(128)
);

CREATE TABLE asset_version (
  id BIGINT PRIMARY KEY,
  asset_id BIGINT NOT NULL,
  version INT NOT NULL,
  content_ref VARCHAR(512),
  diff_summary TEXT,
  changelog TEXT,
  created_by VARCHAR(128),
  created_at TIMESTAMP,
  UNIQUE(asset_id, version)
);

-- 语义资产特化表（Metric / Dimension）
CREATE TABLE asset_metric (
  asset_id BIGINT PRIMARY KEY,
  metric_name VARCHAR(128) NOT NULL,
  business_definition TEXT NOT NULL,
  definition_sql TEXT,
  dimensions_json JSON,                   -- 关联的维度
  valid_from DATE,
  valid_to DATE,                          -- 口径变更后置 valid_to
  owner VARCHAR(128)
);

CREATE TABLE task_asset_link (
  task_id BIGINT NOT NULL,
  asset_id BIGINT NOT NULL,
  link_type VARCHAR(16),                  -- consumed / produced
  PRIMARY KEY(task_id, asset_id, link_type)
);
```

### 6.7 HumanIntervention

```sql
CREATE TABLE human_intervention (
  id BIGINT PRIMARY KEY,
  task_id BIGINT NOT NULL,
  playbook_step_id VARCHAR(64),
  type VARCHAR(32) NOT NULL,              -- approve / coach / escalate / review
                                          -- / reconcile / attest
  status VARCHAR(32),                     -- requested / resolved / aborted
  requested_at TIMESTAMP,
  requested_by VARCHAR(32),               -- system / agent / user
  question_json JSON,                     -- Agent 抛给人的问题、选项、上下文
  resolved_by_user_id BIGINT,
  resolved_at TIMESTAMP,
  decision_json JSON,                     -- 人的决策
  distillation_json JSON,                 -- 强制沉淀内容
  linked_asset_id BIGINT,                 -- 沉淀产出的 asset
  FOREIGN KEY (task_id) REFERENCES task(id)
);
```

### 6.8 TriggerSource（包装现有调度能力）

```sql
CREATE TABLE trigger_source (
  id BIGINT PRIMARY KEY,
  workspace_id BIGINT NOT NULL,
  type VARCHAR(32) NOT NULL,              -- timer / webhook / alert / manual
  config_json JSON,                       -- cron / webhook_url / alert_filter
  target_playbook_id BIGINT,
  is_active BOOLEAN DEFAULT TRUE,
  last_fired_at TIMESTAMP
);
```

`trigger_source.config_json` 中的 timer 类型直接对接现有 APScheduler；webhook 类型对接 `agent_input_queue`；alert 类型对接监控告警 webhook。

### 6.9 WorkspaceResource（空间资源）

> 回应用户问题：SRE 空间管线上环境、数据运营空间管来源库/数仓——这些都是空间资源。统一用 `workspace_resource` 表表达，物理资源仍归各自 serve 模块，空间只做引用 + 配置 overlay。

```sql
CREATE TABLE workspace_resource (
  id BIGINT PRIMARY KEY,
  workspace_id BIGINT NOT NULL,
  type VARCHAR(32) NOT NULL,               -- 资源类型，见下方枚举
  name VARCHAR(128) NOT NULL,              -- 空间内显示名（如"生产核心库"）
  category VARCHAR(16) NOT NULL,           -- generic / scenario_bound / scenario_specific
  physical_ref VARCHAR(128),               -- 引用全局物理实体（类别 ②用）
                                           -- connect_config.id / knowledge_space_id / app_code / mcp_server_id
  config_json JSON,                        -- 空间特化配置 overlay
  access_mode VARCHAR(16),                 -- read / write / admin
  bound_playbook_ids JSON,                 -- 默认用于哪些 Playbook（可选）
  owner_user_id BIGINT,                    -- 空间内资源负责人
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE(workspace_id, type, name)
);
```

**资源类型枚举（type 字段）**：

| type | category | physical_ref 指向 | config_json 示例 |
|---|---|---|---|
| **`skill_bundle`** | generic | `skill_bundle.id`（Skill 注册表的 bundle id） | `{"skills": ["db_query","baseline_compare","anomaly_detect","report"]}` |
| `skill` | generic | `skill.id` | `{}` |
| `mcp` | generic | `mcp_server.id` | `{}` |
| `llm_model` | generic | `model.id` | `{}` |
| `knowledge_space` | scenario_bound | `knowledge_space.id` | `{"default_for_playbook": "pb_xxx"}` |
| `data_source` | scenario_bound | `connect_config.id` | `{"alias": "生产核心库", "schema_filter": ["orders","users"]}` |
| `environment` | scenario_bound | (外部 CMDB / K8s) | `{"cluster": "prod-cn-1", "namespace": "payment"}` |
| `code_repo` | scenario_bound | (Git 仓库 URL) | `{"url": "...", "default_branch": "main"}` |
| `api_endpoint` | scenario_bound | (URL) | `{"base_url": "...", "auth_ref": "..."}` |
| `slo` | scenario_specific | NULL | `{"metric": "p99_latency", "target": 200, "window": "5m"}` |
| `oncall_rotation` | scenario_specific | NULL | `{"members": [...], "schedule": "weekly"}` |
| `data_pipeline` | scenario_specific | NULL | `{"source": "...", "target": "...", "schedule": "..."}` |
| `bi_dashboard` | scenario_specific | NULL | `{"url": "...", "owner": "..."}` |
| `runbook_target` | scenario_specific | NULL | `{"service": "...", "restart_cmd": "..."}` |

> **注**：`agent` 不再作为 workspace_resource 类型——空间用 `workspace.default_agent_app_code` 配置即可。Agentic 时代一个强 Agent + 多 SkillBundle 适配场景，不需要把 Agent 当订阅资源管。

**SkillBundle 是场景能力的核心载体**：

```sql
-- 全局 SkillBundle 注册表（在 derisk_serve.skill 下）
CREATE TABLE skill_bundle (
  id BIGINT PRIMARY KEY,
  name VARCHAR(128) NOT NULL,              -- "SRE 容量巡检 Skill 包"
  description TEXT,
  skills_json JSON NOT NULL,               -- ["db_query","baseline_compare","anomaly_detect","report"]
  scenario_type VARCHAR(64),               -- sre / data_ops / ...
  version INT NOT NULL DEFAULT 1,
  is_published BOOLEAN DEFAULT FALSE,
  created_by VARCHAR(128)
);
```

空间通过 `workspace_resource(type=skill_bundle, physical_ref=skill_bundle.id)` 挂载 SkillBundle，获得这个场景的能力。Playbook 引用 `ref(resource:sre_capacity_bundle)` 即可让 Agent 加载这组 Skill。

**与现有表的迁移**：

```sql
-- 旧表迁移到统一模型
INSERT INTO workspace_resource (workspace_id, type, name, category, physical_ref, config_json, access_mode)
  SELECT workspace_id, 'knowledge_space', '知识空间', 'scenario_bound', knowledge_space_id, '{}', access_mode
  FROM workspace_knowledge_link;

-- agent_subscription 不迁移——空间改用 workspace.default_agent_app_code
-- 旧 agent_subscription 表保留兼容期后下线

-- 旧表保留兼容期，新代码读 workspace_resource
```

**Playbook DSL 引用资源**（配合第 7 章策略声明 DSL）：

```yaml
# Playbook 声明可用 Skill 包（不是步骤）
skills:
  - ref(resource:sre_capacity_bundle)    # SkillBundle 引用

context:
  resources:                              # 可调用的物理资源
    - ref(resource:prod_core_db)          # 数据源
    - ref(resource:prod_cn1)              # 环境
```

Agent 读 SkillBundle 中每个 Skill 的自描述，自主决定调用顺序。

**关键设计点**：

- **物理资源不重复注册**：`connect_config` 等全局表不动，`workspace_resource.physical_ref` 引用即可
- **空间视图独立**：同一个物理数据源可在 SRE 空间叫"prod_core_db"、在数据运营空间叫"生产核心库"——互不影响
- **权限双层**：物理资源权限由原 serve 模块管（RBAC），空间资源权限由空间 RBAC 管（成员角色）
- **资源可被多个 Playbook 引用**：`bound_playbook_ids` 是数组，一个数据源可被多个 Playbook 用
- **scenario_specific 类无 physical_ref**：纯靠 config_json，由对应类型的 serve 模块解析
- **SkillBundle 是场景能力的载体**：空间挂载 SkillBundle 即获得场景能力，不需要为每个场景造 Agent

**资源管理的 UI**（第 13 章前端 IA 补）：空间设置里有"资源"tab，按 category 分组展示（通用能力 / 场景绑定 / 场景专属），支持新增/编辑/绑定 Playbook/测试连通性。SkillBundle 有专属子页，展示包内 Skill 清单与版本。

---

## 7. Playbook 设计：从"工作流脚本"到"策略声明"

> **本章是范式转变的关键章节。** 早期设计把 Playbook 当 workflow DSL（steps/agent/when），但在 Agentic 时代这是开倒车——LLM 自己编排比任何 DSL 都灵活。重构后的 Playbook **不是步骤脚本，是"策略 + Skill 包 + 不变量"的声明**：Skill 承载工作流知识，Agent 在约束内自由编排，Playbook 只声明边界。

### 7.1 范式对比

| 维度 | 旧范式（workflow DSL） | 新范式（策略声明） |
|---|---|---|
| **谁来编排步骤** | DSL 硬编码步骤序列 | Agent 读 Skill 自主编排 |
| **Skill 角色** | 步骤执行器 | 工作流知识载体（自描述） |
| **Agent 角色** | 多个专精 Agent 各演一段 | 一个强 Agent 通用，按 Skill 适配 |
| **Playbook 表达** | `steps: [fetch → compare → review → ...]` | `skills + gates + deliverables + distill` |
| **变化应对** | 改 DSL → 改版本 → 回滚 | Agent 动态决策，无需改 Playbook |
| **失败模式** | 现实与剧本不符就崩 | Agent 自适应，受 gates 约束 |

**核心立场**：Playbook **不规定怎么做事**，只规定**做这件事必须满足什么约束、能用什么资源、必须产出什么**。怎么做让 Agent 决定。

### 7.2 设计取舍

- **声明式 YAML**，可版本化、可 diff、可回滚
- **不图灵完备**：无 `steps`、无 `when`、无控制流——只有"可用什么 Skill / 必须满足什么 gate / 必须产出什么"
- **Skill 是工作流载体**：每个 Skill 自描述（YAML frontmatter + markdown 指引），Agent 读 Skill 知道怎么用
- **不变量是硬约束**：`gates` 声明的介入点、`distill` 声明的沉淀项是 Playbook 强制执行的，Agent 不能绕过
- **资源引用而非内嵌**：Skill / MCP / Knowledge / DataSource 都用 `ref(resource:xxx)` 引用 `workspace_resource`
- **产出与分发声明式**：`deliverables` 声明"必须产出什么 + 怎么分发"，不规定"产出过程"

### 7.3 DSL 结构（四块声明）

```yaml
playbook:
  id: pb_sre_capacity_routine
  name: 容量巡检
  scenario_type: sre
  task_type: routine
  trigger:
    type: timer
    cron: "0 2 * * *"

  # ① Skill 包——这个场景能用哪些 Skill（Agent 自己选怎么用）
  skills:
    - ref(resource:db_query_skill)
    - ref(resource:baseline_compare_skill)
    - ref(resource:anomaly_detect_skill)
    - ref(resource:report_skill)

  # ② 上下文——执行前强制加载的 Asset 和 Resource
  context:
    assets_required:
      - type: catalog
        ref: catalog_production_db
      - type: metric
        ref: metric_p99_latency
      - type: historical_artifact
        query: "type=capacity_report LIMIT 1"   # 上次报告作为基线
    resources:                                   # 可调用的物理资源
      - ref(resource:prod_core_db)
      - ref(resource:prod_cn1)

  # ③ Gates——不变量，Agent 必须满足的硬约束
  gates:
    - id: review_if_anomaly
      after_skill: anomaly_detect_skill          # 触发时机（语义化，非步骤序号）
      condition: "anomalies_detected == true"    # Agent 输出的结构化字段
      intervention:
        type: review
        question: "检测到异常，是否升级为应急任务？"
      blocks: [deliverables]                     # 未满足则不允许进入交付

    - id: approve_before_execute
      applies_to: deliverables.category=execute  # Execute 类交付强制 Approve
      intervention:
        type: approve
        show_dry_run: true
        show_rollback_plan: true

  # ④ Deliverables——必须产出什么、怎么分发、怎么沉淀
  deliverables:
    - type: report
      template: ref(asset:report_template_capacity)
      delivery:
        - category: notify
          channel: email
          target: sre-team@company.com
        - category: publish
          channel: asset_library

  distill:
    forced: true
    produce:
      - type: historical_artifact
        from: deliverable.report                 # 从产出物沉淀
      - type: case
        when: "anomalies_detected == true"
```

### 7.4 四块声明的语义

| 块 | 作用 | 谁来执行 |
|---|---|---|
| **`skills`** | 声明这个场景可用的 Skill 包 | Agent 读 Skill 描述，自主决定调用顺序与次数 |
| **`context`** | 声明执行前必须加载的 Asset 和 Resource | 空间层在 Agent 启动前注入 prompt 与工具 |
| **`gates`** | 声明不变量——某些条件下必须人介入、某些关卡必须 Approve | 空间层监控 Agent 执行，触发 gate 时挂起 Task |
| **`deliverables` + `distill`** | 声明必须产出什么、怎么分发、必须沉淀什么 | 空间层在 Task 关闭前校验产出与沉淀完整性 |

**Agent 的自由度**：在 `skills` 列表内自由选择、自由组合、自由迭代；读 Skill 自描述决定怎么用；读 `context` 知道有哪些资源和历史 Asset 可用。

**Agent 的约束**：不能绕过 `gates`（gate 触发时 Task 自动挂起）；不能跳过 `deliverables`（关闭前校验产出完整性）；不能逃避 `distill`（关闭前校验沉淀）。

### 7.5 Skill 是工作流知识载体（关键）

Agentic 时代的 Skill 不是"函数"，是**"自描述的工作流指引"**。一个 `baseline_compare_skill` 长这样：

```markdown
---
name: baseline_compare_skill
description: 对比当前指标与历史基线，识别异常
inputs:
  current_metrics: object
  baseline_ref: asset_ref
outputs:
  diff_report: object
  anomalies_detected: boolean
  anomaly_list: array
---

# 基线对比 Skill

## 何时使用
当需要判断当前指标是否异常时使用。通常在 `db_query_skill` 取数后调用。

## 如何工作
1. 从 `baseline_ref` 加载历史基线（通常是上次的 historical_artifact）
2. 对比 current_metrics 与基线，计算偏差
3. 偏差超过阈值（见 metric asset 定义）则标记 anomaly
4. 输出结构化 diff_report 和 anomalies_detected 字段

## 注意
- 如果基线缺失，先输出 warning 但不阻塞
- anomaly_list 必须包含 metric_name / current_value / baseline_value / deviation
```

Agent 读这个 Skill 知道**什么时候用、怎么用、输出什么**。Playbook 不需要规定"第 2 步调用 baseline_compare_skill"——Agent 根据目标自己决定。

**Skill 的版本化与共享**：Skill 是空间资源（`workspace_resource.type=skill`），可版本化、可跨空间引用（未来）。Skill 包 = 一组协同 Skill 的集合（如 "SRE 容量巡检 Skill 包"），空间挂载 Skill 包就具备这个场景的能力。

### 7.6 执行引擎映射

| DSL 元素 | 执行时映射 |
|---|---|
| `skills` | 空间层把 Skill 包的描述注入 Agent system prompt + 工具列表 |
| `context.assets_required` | 启动前从 Asset 层加载，注入 prompt（Agent 专精上下文） |
| `context.resources` | 注入为 Agent 可调用的工具/MCP |
| `gates` | 空间层监控 AgentRun 输出，匹配 condition 时创建 `human_intervention`，Task 进入 `awaiting_human` |
| `deliverables` | Task 关闭前校验：是否产出了声明类型的 Artifact？是否执行了声明渠道的 Delivery？ |
| `distill` | Task 关闭前校验：是否完成了声明类型的 Asset 沉淀？未完成不允许 close |

**执行流**：
```
Trigger 触发 → 创建 Task（绑定 Playbook 快照版本）
  ↓
空间层组装上下文：加载 assets_required + 注入 skills 描述 + 注入 resources
  ↓
启动 Agent（一个通用 Agent，按 Skill 适配场景）
  ↓
Agent 自主编排：读 Skill → 调工具 → 产出中间结果 → 触发 gate 时挂起
  ↓
gate 触发 → 创建 HumanIntervention → 等人处理 → 解除挂起 → Agent 继续
  ↓
Agent 完成 → 校验 deliverables 完整性 → 校验 distill 完成 → Task close
```

### 7.7 与传统 workflow 的关键区别

| 问题 | workflow DSL | 策略声明 Playbook |
|---|---|---|
| Agent 想多查一个指标 | 改 DSL 加步骤 | Agent 自己查，无需改 Playbook |
| 现实流程和剧本不符 | 剧本崩，Task 失败 | Agent 自适应，只要满足 gates 就行 |
| 新场景复用 | 拷贝 DSL 改步骤 | 换 Skill 包 + 调 gates，Playbook 结构不变 |
| LLM 编排能力升级 | DSL 不变，享受不到 | 直接享受，Playbook 是声明不限制 |
| 调试 | 看步骤执行日志 | 看 AgentRun + gate 触发记录 |
| 维护 | 改流程改 DSL，需版本管理 | 流程在 Skill 里，Skill 独立版本化 |

### 7.8 什么时候还需要显式步骤？

**极少**。只有两种情况保留"步骤"语义：

1. **合规审计场景**：法规要求"必须按特定顺序执行"（如财务月结的固定阶段）——这时用 `gates.after_skill` 表达顺序约束，但仍不硬编码步骤
2. **Execute 类操作的前置校验**：执行前必须 dry-run、必须 Approve、必须可回滚——这是 gate，不是步骤

**绝大多数场景下，Skill 自描述 + Agent 自主编排 + gates 约束 = 足够**。把"步骤思维"留给 Skill 内部的 markdown 指引，不要上升到 Playbook 层。

### 7.9 Playbook 演化机制（更新）

第 10.2 节说的"Playbook 自演化"在策略声明范式下更自然：

- **旧范式演化**：对比 DSL 步骤与实际执行步骤 → 提议加/删步骤
- **新范式演化**：统计 Skill 实际调用模式 → 提议：
  - 哪些 Skill 从未被调用 → 提议从 `skills` 移除
  - 哪些 Skill 总是被一起调用 → 提议合并为 Skill 包
  - 哪些 gate 总是被触发但通过率低 → 提议调整 condition
  - 哪些 deliverable 总是产出但从未被 delivery → 提议移除

演化提议基于**Agent 实际行为统计**，不是步骤偏差。这更符合 Agentic 范式。

---

## 8. 四类工作流的执行机制

| 类型 | 触发 | 执行特征 | 介入点 | 沉淀重点 |
|---|---|---|---|---|
| **Routine 例行型** | 定时 | 可对比、异常才升级；强制加载历史 Asset 作为基线 | Review（异常时） | historical_artifact + case |
| **Pipeline 流水线型** | Webhook / 主动 | 多阶段、强顺序、每段有 gate；支持回滚 | Approve（每 gate）、Reconcile（对账） | template + lineage |
| **Incident 应急型** | 告警 / 升级 | 信息缺、决策重；强制调用历史案例 | Escalate（低置信时）、Review（结束必做） | case + runbook |
| **Ad-hoc 临时型** | 用户主动 | 无预设 Playbook 或基于模板微调 | Coach（用户全程参与） | template（可选） |

### 8.1 跨类型升级（关键机制）

Pipeline 步骤失败、Routine 异常、对账不一致 → **自动派生 Incident Task**，引用原 Task 为 `parent_task_id`，关系类型 `escalated_to`。这是数据运营场景"对账失败触发排查"和 SRE 场景"巡检异常触发应急"的共同机制，必须支持。

### 8.2 Task 状态机

```
draft → pending_trigger → running → awaiting_human → running → delivered → closed → archived
                                  ↘ blocked         ↘ failed
```

- `awaiting_human` 可重入（一个 Task 可多次等人）
- `closed` 触发 `distill` 强制检查；未完成 distill 不能 closed
- `archived` 后 Asset 仍可被检索，但不再出现在 Workspace 默认视图

---

## 9. 人的介入机制

### 9.1 六种介入模式

| 模式 | 场景 | 人做什么 | 强制沉淀 |
|---|---|---|---|
| **Approve** | 上线 gate、回滚决策 | 看证据做决策 | 决策理由 → Asset（case） |
| **Coach** | Agent 方向错了 | 纠正、补上下文 | 纠正规则 → Asset（runbook / case） |
| **Escalate** | Agent 卡住 | 接手最难部分 | 接管轨迹 → Asset（case） |
| **Review** | Incident 结束、Routine 异常 | 复盘根因 | 复盘结论 → Asset（runbook + case） |
| **Reconcile** | 数据对账 | 人独立算一遍核对 | 差异说明 → Asset（lineage） |
| **Attest** | 财务报表签字 | 责任背书 | 签字记录 → Artifact 版本绑定（不可篡改） |

### 9.2 介入点的实现

- Playbook DSL 中 `intervention` 块声明介入点
- 执行引擎到达介入点时，通过现有 Hook 系统触发 `human_intervention` 创建
- Task 状态切到 `awaiting_human`，Workspace 首页"待我处理"推送
- 人在 UI 中处理 → 写 `decision_json` + `distillation_json`
- **distill 未填写的介入，UI 不允许标完成**——这是强制沉淀的硬约束

### 9.3 通知渠道

复用现有 `derisk-core/agent/channels/`：飞书 / 钉钉 / 邮件 / 站内信。介入请求通过 channels 推送，DeepLink 回到 Workspace 处理。

---

## 10. 三大核心机制：协作 / 进化 / 交付

> **本章是场景空间区别于普通 Agent 平台的真正壁垒。** 第 5-9 章定义了空间里"有什么"，本章回答"空间凭什么比单机 Agent 工具更有价值"——答案是这三件事做到极致：**协作让人与 Agent 共同工作、进化让空间越来越懂团队、交付让产出真正落地为业务价值**。这三件事不是 feature，是空间的"生命体征"。任何一维缺失，空间就退化回 chatbot。

### 10.0 三机制总览

| 维度 | 一句话 | 核心问题 | 主要载体 |
|---|---|---|---|
| **协作 Collaboration** | 人与 Agent 在剧本上共同工作 | 谁做什么、何时介入、如何接力 | Playbook + HumanIntervention + 任务派发 |
| **进化 Evolution** | 空间越用越懂这个团队 | 跑过的任务如何变成下次的加速 | Asset 沉淀 + Playbook 演化 + Agent 专精 |
| **交付 Delivery** | 产出物真正落到业务 | 产出怎么去该去的地方、被谁以什么形式消费 | Artifact + Delivery + 强制签收与追溯 |

三机制不是孤立的——**协作产生执行轨迹，轨迹喂养进化，进化提升协作效率；协作和进化的产出最终都要通过交付落地**。这是一个闭环。

---

### 10.1 协作机制（Collaboration）

#### 10.1.1 协作的本质：剧本上的分工，不是 ad-hoc 对话

普通 Agent 平台的协作是"人和 Agent 临时对话"。场景空间的协作是**"人和 Agent 都在剧本里演各自的角色"**——剧本定义了谁在哪一步出现、做什么、何时交接。这是协作可预期、可追溯、可复用的前提。

四种协作关系，覆盖所有工作场景：

| 关系 | 含义 | 例子 |
|---|---|---|
| **Agent → Agent** | Agent 之间分工协作 | SRE-Agent 取日志 → Code-Agent 分析代码 → Report-Agent 出报告 |
| **Agent → Human** | Agent 在介入点把人拉进来 | 部署到 gate，Agent 抛 Approve 请求等运维确认 |
| **Human → Agent** | 人发起/接管任务，Agent 执行 | 用户发起临时分析，Agent 跑取数；用户 Coach 纠正方向 |
| **Human → Human** | 任务在人之间流转（Agent 辅助） | 应急时 oncall 接力，前一班把上下文交给下一班，Agent 整理交接材料 |

#### 10.1.2 协作的五个设计要点

**① 角色显式化**：空间成员有角色（Owner/Contributor/Approver/Viewer），Agent 也有"职能角色"（fetcher/analyzer/reporter/coordinator）。Playbook 引用角色而非具体身份——同一个"reporter 角色"在不同 Task 可以是不同的 Agent 实例。这让团队配置和剧本解耦。

**② 介入点是剧本的字段，不是临时请求**。第 9 章已定义的六种介入模式（Approve/Coach/Escalate/Review/Reconcile/Attest）都通过 Playbook DSL 的 `intervention` 块声明。**没有声明介入点的步骤，Agent 自己跑完不等人**——这是避免"人被 Agent 拖着走"的关键。

**③ 任务接力有显式交接物**。Agent → Human 接力时，Agent 必须输出一个"交接上下文"（当前进展/关键证据/需要人决策的问题）；Human → Agent 接力时，人填的"补上下文"会被注入下一步 Agent 的 prompt。交接物是结构化的，存到 `human_intervention.question_json` 和 `decision_json`，不是聊天记录。

**④ 多人协作支持**。一个 Task 可以有多个 HumanIntervention 并行（如对账需要两人复核），Playbook DSL 支持 `intervention.quorum: 2` 声明需要 N 人同意。这是财务/合规场景的刚需。

**⑤ 协作全程可追溯**。每个 AgentRun、每次 HumanIntervention、每个 Task 关系都带 `task_id`。Task 详情页能完整还原"谁在何时做了什么、基于什么证据、产出什么"——这是事后复盘和审计的基础。

#### 10.1.3 协作的具体场景化

| 场景 | 典型协作形态 |
|---|---|
| SRE 应急 | Agent 取证 → Escalate 给 oncall → oncall Coach 方向 → Agent 继续跑 → Review 复盘（多人） |
| SRE 上线 | Agent 跑部署 → Approve gate 给 SRE 负责人 → 失败自动 Escalate → 回滚需 Approve |
| 数据运营月报 | Agent 取数 → Reconcile 对账（两人复核）→ Attest 财务签字 → Deliver 发高管 |
| 临时分析 | Human 发起 → Agent 跑 → Human Coach → Agent 再跑 → Deliver 给需求方 |

#### 10.1.4 协作的反模式（明确不做）

- **不做"无介入点的关键决策"**：涉及钱、涉及线上变更、涉及对外承诺的步骤，必须有介入点。Agent 自主决策是红线。
- **不做"介入不沉淀"**：第 9 章已明确——介入必须强制 distill。
- **不做"角色硬编码到 Playbook"**：Playbook 引用"角色"不是具体用户。具体用户在 Task 创建时绑定到角色。
- **不做"Agent 之间隐式协作"**：Agent → Agent 必须通过 Playbook 编排，不能 Agent A 直接调 Agent B。否则不可追溯、不可回滚。

---

### 10.2 进化机制（Evolution）

#### 10.2.1 进化的本质：跑过的任务变成下次的加速

如果跑一万次任务空间还是第一天那么笨，那就不是进化，是垃圾堆。**真正的进化是：每次任务的执行智慧以结构化方式沉淀，下次同类任务能直接复用，让团队越用越快越准。**

四种进化机制，按成熟度排：

| 机制 | 触发 | 实现位置 | 成熟度 |
|---|---|---|---|
| **Asset 沉淀** | 每次 Task 关闭 | `distill` DSL 块 + `task_asset_link` | 基础，必做 |
| **Agent 专精** | Agent 调用前 | 注入"空间记忆摘要" + 检索 Asset 作为 RAG 上下文 | 中等 |
| **Playbook 演化** | 同类 Task 多次偏差 | 定期 Job 扫描，提议修改（人审批） | 进阶，差异化 |
| **知识结构化** | 定期 | 复用 knowledge-vault L0→L1→L2 流水线 | 长期 |

#### 10.2.2 Asset 沉淀（基础机制）

每次 Task 关闭前强制 `distill`：

- **强制项**：本次产出物是否进 Asset 库（historical_artifact 类）
- **可选项**：是否新增 case / 是否更新 runbook / 是否更新 metric 口径
- **distill 表单极简**：3 个字段内（"产出/是否新增案例/备注"），提供"无沉淀"选项但需填理由
- **未完成 distill 不允许 close Task**——这是硬约束，UI 不放行

Asset 类型分布（第 6 章已定义）：

| 类型 | SRE 空间用 | 数据运营用 | 复用方式 |
|---|---|---|---|
| runbook | ✅ 主用 | 偶尔 | 应急时自动检索 |
| case | ✅ 主用 | ✅ | 同类任务参考 |
| metric | — | ✅ 主用 | SQL 生成时强制引用 |
| dimension | — | ✅ 主用 | 报表切分按统一口径 |
| catalog | ✅ | ✅ | Agent 查表时自动加载 |
| lineage | 偶尔 | ✅ 主用 | 跨时间对比校准 |
| report_template | ✅ | ✅ | 新报告基于模板 |
| sql_template | ✅ | ✅ | SQL 复用 |
| historical_artifact | ✅ | ✅ | 基线对比、报告参考 |

#### 10.2.3 Agent 专精（上下文注入）

Agent 调用前，空间层组装 prompt 上下文：

```
[空间记忆摘要]
本空间是 SRE 应急空间，历史共处理 47 次事故，最近 5 次：...
常用 runbook: ref(runbook_db_failover), ref(runbook_network_split)
常用案例: ref(case_2025_q4_redis_oom), ...

[本次任务相关 Asset]
Metric: metric_p99_latency = ...
Catalog: orders 表 status 字段含义...
上次同类 Task: task_12345（结论：...）
```

实现位置：`derisk_serve.workspace.context_builder`，作为 Agent 启动前的 prompt 注入器。

**专精的边界**：注入的是"空间记忆"不是"个人记忆"——同一个空间的所有 Agent 看到的是同一份空间记忆，这是"团队知识"不是"个人知识"。个人知识在 Personal Sandbox。

#### 10.2.4 Playbook 演化（差异化关键，几乎无产品做到）

**这是 OpenDerisk 的核心差异化机制**。流程：

1. 定期扫描某 Playbook 最近 N 次执行
2. 对比 `workflow_dsl` 中声明的步骤 与 `agent_run` 表中实际执行的步骤
3. 识别"反复出现的额外步骤"（Agent 每次都自己加的）或"反复被跳过的步骤"（声明了但没人做）
4. 生成 Playbook 修改提议（创建 `playbook_version` 草稿，状态 `proposed`）
5. 推送给 Playbook owner 审批
6. 通过后 `current_version` 切换，旧版本保留可回滚

**例子**：容量巡检 Playbook 第 3 步是"查日志"，但最近 5 次执行 Agent 都额外查了某个新指标 X。空间提议把"查 X"加进 Playbook 第 3 步。owner 审批通过后，下次执行自动包含。

**演化的硬约束**：
- **AI 不能自动改剧本**：所有提议必须人审批后才生效。这是红线（第 16 章"不做什么"已明确）。
- **演化是提议驱动的**：空间识别偏差、推送提议，但不强制。owner 可以拒绝、可以延后。
- **演化提议也是 Asset**：被拒绝的提议也沉淀，避免重复提议同样的事。

#### 10.2.5 知识结构化（长期机制）

复用 knowledge-vault L0→L1→L2 流水线：
- L0 原文：聊天记录、Artifact 全文
- L1 Wiki：定期由 Agent 自动总结成结构化摘要
- L2 图谱：实体关系、事件因果

**这个加工是空间自己跑的**，不是人手动整理。定期 Job 触发，把散落的 L0 加工成 L1/L2，反哺给 Asset 检索。

#### 10.2.6 进化的反模式

- **不做"所有 chat_history 自动进 Asset"**：垃圾堆 ≠ 知识库。必须显式 distill。
- **不做"AI 自动改 Playbook"**：演化只识别 + 提议，永远人审批。
- **不做"进化只进不出"**：长期未被引用的 Asset 要能归档，不能只增不减。
- **不做"个人记忆污染团队"**：Personal Sandbox 的产出默认不进团队 Asset，必须显式提升。

---

### 10.3 交付机制（Delivery）

#### 10.3.1 交付的本质：产出物落到该去的地方——可能是给人看，可能是发布成资产，可能是改变世界的动作，也可能是栖居在空间里被托管运行

普通 Agent 平台的产出停在"chat 里的最后一条消息"。场景空间的交付是**"产出物从生成到落地为业务价值的完整链路"**。关键澄清：**交付 ≠ 发邮件 / 出报告**。交付有四种本质不同的形态：

| 交付类别 | 做什么 | 副作用 | 例子 |
|---|---|---|---|
| **Notify 通知类** | 把 Artifact 内容推给某人/某群 | 无（只是信息流动） | 邮件发报告、飞书推卡片、站内信 |
| **Publish 资产发布类** | 把 Artifact 写入外部持久系统 | 创建/更新外部资产 | 报表入 BI、数据写数仓表、代码 push 到 repo、看板注册到 BI |
| **Execute 执行类** | 把"操作计划"Artifact 在真实世界执行 | **改变系统状态** | 重启服务、部署代码、扩缩容、回滚、改配置 |
| **Host 托管类** | 把 Artifact 在空间内托管、展示、部署运行 | **空间内常驻可访问的交付物** | 售前调研 web 程序、运营 BI 看板、SRE 运维历史、分析 notebook |

**为什么必须四类**（回应用户洞察）：交付物的命运不是只有"发出去"。SRE 空间要长期托管运维操作历史与 runbook；运营空间要托管数据集/报表/看板供团队随时查；市场售前空间要托管调研 web 程序让客户直接访问。**"面向最终交付构建空间"意味着空间不只是工作发生的地方，还是交付物栖居的地方**——用户进空间不只看到任务，还看到这个空间托管了什么、运行着什么。

**四类必须用同一个 Delivery 模型表达**，因为它们都是"Task 产出落地"的动作，都有状态/签收/追溯的需求；但 Execute 类和 Host 类有特殊约束（Execute 必须 Approve/可回滚；Host 有生命周期管理）。

**关键立场**：Delivery 是独立实体，不是 Artifact 的附属属性。同一个 Artifact 可以有多条 Delivery——例如一份 `code_project` 既 git push 到 repo（Publish），又在空间内托管为 web 程序运行（Host），还发邮件通知相关人（Notify）。

#### 10.3.2 Artifact 类型扩展（支撑四类交付）

| Artifact 类型 | 用于哪类交付 | 说明 |
|---|---|---|
| `report` / `document` / `email_content` | Notify / Host | 文档型产出；可托管为可浏览文档站 |
| `dataset` | Publish / Host | 数据集；可托管为可探索数据表 |
| `dashboard` | Publish / Host | 看板定义；可托管为空间内看板 |
| `code_project` | Publish / Host | 代码项目；可托管为可运行 web 程序 |
| **`deliverable_app`** | **Host** | **可交付的 web 应用**（调研站、demo、内部工具、API 服务） |
| **`notebook`** | **Host** | 数据分析 notebook，可托管为交互运行环境 |
| `operation_plan` | Execute | **操作计划**：待执行的具体步骤 |
| `operation_result` | Execute | 执行结果记录，作为新 Artifact 沉淀 |
| `analysis` / `decision` | Notify / Attest / Host | 分析结论、决策记录；可托管为可浏览报告 |

**`operation_plan` 的结构化内容**（关键）：

```json
{
  "type": "operation_plan",
  "actions": [
    {"kind": "restart_service", "target": "ref(resource:payment_svc)", "reason": "内存泄漏"},
    {"kind": "scale", "target": "ref(resource:payment_deploy)", "replicas": 5}
  ],
  "dry_run_preview": {...},
  "rollback_plan": [...],
  "risk_level": "medium",
  "estimated_impact": "5s 短暂抖动"
}
```

`operation_plan` 是 Agent 产出但**不能直接执行**——必须走 Execute 交付 + 强制 Approve。

**`deliverable_app` 的结构化内容**（关键，新增）：

```json
{
  "type": "deliverable_app",
  "app_kind": "web_app",                  // web_app / api_service / static_site
  "entrypoint": "index.html",             // 入口文件
  "runtime": "nodejs18",                  // 运行时
  "build_cmd": "npm run build",
  "start_cmd": "npm start",
  "port": 3000,
  "env": {"API_BASE": "ref(resource:backend_api)"},
  "resources": {"cpu": "0.5", "memory": "512Mi"},
  "health_check": "/health"
}
```

`deliverable_app` 是 Agent 产出的可运行应用——通过 Host 交付在空间内部署运行，用户通过浏览器访问。

#### 10.3.3 Delivery 的四类渠道

```sql
-- delivery 表的 category 和 channel 字段
category VARCHAR(16) NOT NULL,    -- notify / publish / execute / host
channel  VARCHAR(32) NOT NULL     -- 见下表
```

| category | channel | 做什么 | 复用什么 |
|---|---|---|---|
| **notify** | `email` / `feishu` / `dingtalk` / `webhook` / `in_app` | 把 Artifact 格式化后推送 | 现有 `derisk-core/agent/channels/` |
| **publish** | `bi_dashboard` | 注册看板到 BI 系统 | BI 适配器 |
| **publish** | `data_table` | 写入数仓表 | 现有 `connect_config` 数据源 |
| **publish** | `code_repo` | git push 代码项目 | Git 适配器 |
| **publish** | `file_store` | 写入对象存储 | 现有 `derisk_serve.file` |
| **publish** | `asset_library` | 沉淀到本空间 Asset 库 | `derisk_serve.asset` |
| **execute** | `action_executor` | **执行 operation_plan** | MCP / Skill / 现有工具体系 |
| **execute** | `downstream_playbook` | 触发另一个 Playbook 派生新 Task | `derisk_serve.task` |
| **host** | `web_runtime` | **部署运行 deliverable_app / code_project** | 容器运行时（K8s/Docker） |
| **host** | `dashboard_viewer` | 渲染展示 dashboard Artifact | 看板渲染服务 |
| **host** | `data_explorer` | 托管 dataset 供交互探索 | 数据查询服务 |
| **host** | `doc_site` | 托管文档/report 供浏览 | 文档渲染服务 |
| **host** | `notebook_runtime` | 托管 notebook 供交互运行 | Jupyter 内核服务 |

#### 10.3.4 交付的五层（沿用，但 Execute 类有强化）

| 层 | Notify 类 | Publish 类 | Execute 类 | Host 类 |
|---|---|---|---|---|
| **Generate** | Artifact (report/...) | Artifact (dataset/code_project/...) | Artifact (**operation_plan**) | Artifact (**deliverable_app/dashboard/notebook**) |
| **Format** | PDF/Card/JSON | 表格/文件/git diff | dry_run 预览 + 影响评估 | 构建产物 + 运行时配置 |
| **Deliver** | 调 channels 推送 | 写外部系统 | **必须先 Approve** → action_executor 执行 | 部署到托管运行时 |
| **Attest** | 涉及责任时人签 | 发布到生产环境前人签 | **强制 Approve**（无例外） | 对外发布前人签（可选） |
| **Trace** | 投递记录 | 发布记录 + 外部资产 ref | **执行记录 + operation_result + 回滚链路** | **托管实例记录 + 访问日志 + 生命周期状态** |

#### 10.3.5 Execute 类交付的特殊机制（重点）

执行类交付涉及"改变世界"，必须有四重保护：

**① 强制 Approve，无例外**

`operation_plan` Artifact 走 Execute 交付时，Playbook 必须声明 `intervention.type=approve` 介入点。**DSL 校验时若无 approve 介入点直接拒绝执行**——这是硬约束，不允许"AI 自主执行操作"。

```yaml
- id: execute_restart
  input_artifact: ${steps.plan_restart.output}   # operation_plan
  delivery:
    category: execute
    channel: action_executor
    require_intervention: approve                 # 强制
    intervention:
      type: approve
      question: "即将重启 payment_svc，预计 5s 抖动，确认执行？"
      show_dry_run: true
      show_rollback_plan: true
```

**② Dry-run 预览**

执行前必须能预览"会发生什么"。`operation_plan.dry_run_preview` 在 Approve 界面展示。高风险操作（如生产环境变更）可强制要求 dry-run 通过才能进 Approve。

**③ 回滚计划强制**

`operation_plan.rollback_plan` 不可为空（DSL 校验）。执行失败时自动触发回滚 Delivery（也是 execute 类，但走简化 Approve——失败回滚不需再次审批，因为审批时已授权）。

**④ 执行结果沉淀为 Artifact**

执行后生成 `operation_result` Artifact，记录：实际执行了什么、耗时、是否成功、副作用观测。**这个 Artifact 必须强制 distill 成 case Asset**——下次同类操作可参考"上次重启 payment_svc 的实际影响"。

**⑤ 失败升级**

Execute 交付失败 → 自动触发 `downstream_playbook`（通常是应急 Playbook）派生 Incident Task。这是 Pipeline 失败升级机制在 Execute 类的延伸。

#### 10.3.6 交付的具体场景化（扩展版，含 Host 类）

| 场景 | 交付链路 | 类别 |
|---|---|---|
| 月度经营报表 | Agent 生成 report → PDF → 邮件给高管 + BI 入库 → CFO Attest → 发出 | Notify + Publish |
| 容量巡检报告 | Agent 生成 report → 邮件给 SRE 组 + 异常时飞书推 oncall + 入 Asset 库 | Notify + Publish |
| **应急重启服务** | Agent 生成 **operation_plan** → dry-run 预览 → Approve → action_executor 执行 → **operation_result** 沉淀 → 失败触发应急 Playbook | **Execute** |
| **上线部署代码** | Agent 生成 **operation_plan** (含 manifest + rollback) → Approve → action_executor 部署 → 部署报告 Artifact + operation_result → 失败自动回滚 + 触发应急 | **Execute** |
| **交付代码项目** | Agent 生成 **code_project** Artifact (多文件) → Approve → git push 到 code_repo → 通知相关人 | **Publish** |
| 临时分析结论 | Agent 生成 analysis → 飞书给需求方 | Notify |
| 应急复盘报告 | Agent 生成 report → Review（多人）→ 定版 → 邮件 + runbook 提议进 Asset | Notify + Publish |
| **数据回填** | Agent 生成 **operation_plan** (含 SQL) → Approve → action_executor 执行 SQL → operation_result（影响行数）→ 入 Asset | **Execute** |
| **市场售前调研站** | Agent 生成 **deliverable_app**（调研 web 程序）→ 构建产物 → **Host 部署运行** → 生成访问 URL → 客户通过 URL 访问 → 邮件发客户链接 | **Host + Notify** |
| **运营数据看板** | Agent 生成 **dashboard** Artifact → **Host 托管为空间内看板** → 团队随时浏览 → 异常时飞书推卡片带看板链接 | **Host + Notify** |
| **运营数据探索** | Agent 生成 **dataset** → **Host 托管为可探索数据表** → 团队交互查询筛选 | **Host** |
| **SRE 运维历史** | Agent 整理 operation_result 序列 → **Host 托管为可查询运维历史站** → 团队按服务/时间检索 | **Host** |
| **数据分析 notebook** | Agent 生成 **notebook**（含代码 + 结果）→ **Host 托管为交互环境** → 团队可重跑/修改 | **Host** |
| **合规证据链站** | Agent 生成 **deliverable_app**（证据链展示站）→ **Host 部署** → 审计员/监管访问 | **Host** |

#### 10.3.7 Host 类交付的特殊机制（重点，新增）

Host 类交付是"面向最终交付构建空间"的核心——交付物栖居在空间里，被托管、展示、部署运行。机制设计：

**① 托管实例有完整生命周期**

```
deploying → running → stopped → archived
                ↓            ↑
              failed ────────┘
```

- `deploying`：构建 + 部署中
- `running`：运行中，可访问
- `stopped`：人手动停或自动休眠（长期未访问）
- `failed`：部署/运行失败，可重试或归档
- `archived`：归档释放资源，Artifact 仍可重新托管

**② 访问控制分层**

- **空间内访问**：托管实例默认只对 workspace 成员可见，通过 `/workspaces/{id}/hosted/{hid}` 路由访问
- **组织内发布**：可生成带 token 的内部链接，同组织其他空间成员可访问
- **对外发布**：可生成公开链接（带 rate limit + 过期时间），用于客户/外部访问——这一步需 Approve（防泄露）

**③ 资源限额与成本控制**

托管实例有资源限额（CPU/内存/带宽），长期未访问的自动休眠或归档。空间有"托管成本"仪表盘，让 Owner 看到资源消耗，避免无限增长。

**④ 版本化托管**

一个 Artifact 可有多个版本被托管（如售前 demo v1 给老客户、v2 给新客户），每个版本独立实例、独立 URL。新版本部署后老版本可保留可切换。

**⑤ 数据源连接**

托管的应用（如 dashboard、data_explorer、deliverable_app）需要连数据源时，通过 `runtime_config_json` 引用 `workspace_resource(type=data_source)`——复用空间资源管理，不重新配连接。

**⑥ 健康检查与自愈**

`deliverable_app` 的 `health_check` 字段声明健康端点。托管运行时定期检查，失败自动重启（有限次），仍失败告警让人介入。

**⑦ 托管即 Asset**

长期有价值的托管实例，可"提升为 Asset"（如团队常用的 dashboard、售前 demo 模板）——提升后进入 Asset 库，其他 Task 可引用、其他空间可订阅（未来）。

#### 10.3.8 交付的关键设计

**① Artifact → Delivery 解耦**：一个 Artifact 可以有多条 Delivery（如 code_project 既 git push 到 repo，又在空间内 Host 运行，还发邮件通知），每条独立状态。某条失败不影响其他。

**② 渠道复用现有能力**：notify 类复用 `channels/`；publish 类的 `data_table` 复用 `connect_config`，`file_store` 复用 `derisk_serve.file`；execute 类的 `action_executor` 复用现有 MCP / Skill / 工具体系；**host 类复用容器运行时（K8s/Docker）和现有 `derisk_serve.file` 存构建产物**——不重造执行/托管通道。

**③ Attest 不可篡改**：财务/合规/生产变更的交付，签收记录绑定到 Artifact 特定 version。即使 Artifact 后续有新版本，旧版本签收记录不动。

**④ Downstream Playbook 作为 Execute 渠道**：一个 Task 的 operation_plan 执行失败可触发另一个 Playbook 启动新 Task。这是空间内"任务流"的承接机制。

**⑤ 失败重试与降级**：Delivery 失败自动重试 N 次，重试失败降级到 fallback 渠道 + 告警。**Execute 类不自动重试**（操作可能已部分执行，重试有风险）——Execute 失败必须走回滚或人工介入。**Host 类部署失败可自动重试**（部署是幂等的），但运行时失败走健康检查自愈机制。

**⑥ 交付时间控制**：notify/publish 支持定时/立即/延迟；**execute 仅支持立即或定时，不支持延迟**（延迟执行的操作计划容易过期失效）；**host 支持立即/定时部署，支持定时停止**（如售前 demo 在客户访问窗口期运行）。

**⑦ Publish 类的"外部资产 ref"**：发布到外部系统的 Artifact，`delivery.result_json` 记录外部资产引用（如 BI 看板 URL、数仓表名、git commit SHA），未来 Task 可通过 ref 引用这些外部资产。

**⑧ Host 类的"空间内栖居"**：托管实例通过 `artifact_hosting` 表记录生命周期，访问 URL 通过 `internal_route` 在空间内有固定路由。用户进空间就能看到"这个空间托管了什么"，不需要去外部系统。

#### 10.3.9 交付的反模式

- **不做"产出即结束"**：生成 Artifact 不算交付完成，必须显式 Deliver。
- **不做"无签收的责任交付"**：涉及钱/合规/对外承诺/生产变更的产出必须 Attest 或 Approve。
- **不做"AI 自主 Execute"**：所有 execute 类交付必须人 Approve，无例外（红线）。
- **不做"无回滚的 Execute"**：operation_plan 必须含 rollback_plan，DSL 校验拒绝空回滚。
- **不做"Execute 自动重试"**：执行类失败走回滚或人工，不自动重试。
- **不做"交付即不可追溯"**：所有交付记录可回溯，包括失败记录和 operation_result。
- **不做"Delivery 耦合 Artifact"**：Delivery 独立实体，支持多对多。
- **不做"AI 自主 Attest"**：所有 Attest 必须人签（第 16 章已明确）。
- **不做"Host 无生命周期管理"**：托管实例必须有停止/归档机制，不能只部署不回收，否则资源无限增长。
- **不做"Host 对外发布无 Approve"**：托管实例生成公开链接需人 Approve，防止敏感数据意外泄露。
- **不做"Host 实例直连外部数据源"**：托管应用连数据源必须通过 `workspace_resource` 引用，不能在应用配置里硬编码连接串。

---

### 10.4 三机制的闭环关系

```
       ┌─────────────────────────────────────┐
       │                                     │
       │   协作 Collaboration                │
       │   (人在剧本上演角色)                │
       │                                     │
       └────────┬──────────────────┬─────────┘
                │                  │
        产生执行轨迹          产出 Artifact
                │                  │
                ▼                  ▼
       ┌─────────────────────────────────────┐
       │                                     │
       │   进化 Evolution                    │
       │   (轨迹变 Asset, 偏差变 Playbook 提议)│
       │                                     │
       └────────┬──────────────────┬─────────┘
                │                  │
        下次任务加速          Asset 可被 Delivery 引用
                │                  │
                ▼                  ▼
       ┌─────────────────────────────────────┐
       │                                     │
       │   交付 Delivery                     │
       │   (产出落到业务, 签收, 追溯)        │
       │                                     │
       └─────────────────────────────────────┘
                │
        交付结果触发新事件 → 回到协作
```

**闭环举例（SRE 应急）**：
1. 告警触发 → **协作**：Agent 团队按应急 Playbook 协作，oncall 在 Escalate 介入点接管
2. 处理完成 → **进化**：Review 强制 distill，沉淀 case + runbook；Playbook 演化识别"这次额外查的指标"提议加进步骤
3. 复盘报告 → **交付**：邮件给相关方 + runbook 提议进 Asset + 下次同类告警 Agent 专精上下文自动加载本次案例

下一次同类告警进来，空间已经不是第一次那么笨了——这就是"可成长的 AI 团队空间"。

### 10.5 三机制在产品里的可见性

三机制不能只是后台跑，必须让用户感知到，否则价值不可见：

| 机制 | 用户可见形态 |
|---|---|
| 协作 | Task 详情页的"协作时间线"（谁/Agent 在何时做了什么）；介入中心的待办列表 |
| 进化 | 空间首页"本月空间成长"卡片（沉淀 Asset 数 / Playbook 演化提议数 / 任务处理趋势）；Playbook 编辑器的"演化提议"标签 |
| 交付 | Artifact 详情页的"交付链路"图（生成→格式化→分发→签收）；Delivery 状态时间线 |

**让用户每次进空间都看到"这个空间在成长、在交付、在让我参与"**——这是产品叙事的核心。

---

## 11. 与现有系统的关系

### 11.1 复用（不动）

| 现有能力 | 在新架构中的角色 |
|---|---|
| `derisk-core/agent/` | Agent 执行引擎，被 AgentRun 调用 |
| `derisk_serve.agent` | Agent 注册、版本、发布；空间通过 `default_agent_app_code` 配置，不作为 WorkspaceResource 订阅 |
| `derisk_serve.skill` | Skill 注册 + **SkillBundle 管理**（场景能力核心载体）；作为 WorkspaceResource `type=skill_bundle` / `type=skill` 引用 |
| `derisk_serve.mcp` | MCP server 管理，作为 WorkspaceResource `type=mcp` 引用；execute 类交付的 action_executor 通过 MCP 执行操作 |
| `derisk_serve.knowledge` | knowledge-vault Space 作为 WorkspaceResource `type=knowledge_space` 引用 |
| `derisk_serve.conversation` | 对话管理，新增 `task_id` 关联 |
| `derisk_app/initialization/scheduler.py` | APScheduler 作为 TriggerSource 的 timer 实现 |
| `derisk-core/agent/channels/` | 介入通知 + Notify 类 Delivery 渠道 |
| `feature_plugins/permissions/` | Workspace 成员 RBAC + WorkspaceResource 访问权限 |
| `RFC-001 Hook 系统` | 介入点触发机制（含 Execute 类 Approve） |
| `gpts_app_config` | Agent 定义，新增 `owner_user_id` / `workspace_id` |
| `gpts_conversations` / `gpts_plans` / `gpts_work_log` | 执行轨迹，新增 `task_id` |
| `agent_input_queue` | Webhook / Alert 触发的消息总线 |
| `connect_config` / `db_spec` / `table_spec` | 数据源物理注册，被 WorkspaceResource `type=data_source` 引用 |
| `derisk_serve.file` | 文件存储，Publish 类 `file_store` 渠道复用 |
| `db_learning_task` / `db_learning_subtask` | Task + Subtask 模型的参考模板 |

### 11.2 新增（在 derisk-serve 层）

```
derisk_serve.workspace         # Workspace CRUD + 成员
derisk_serve.workspace_resource # 统一资源管理（3 类资源，引用现有物理资源）
derisk_serve.task              # Task 生命周期 + 状态机 + 关系
derisk_serve.playbook          # Playbook CRUD + 版本 + 策略声明 DSL 校验
derisk_serve.playbook_runtime  # 策略声明执行 + AgentRun 调度（Agent 自主编排，受 gates 约束）
derisk_serve.artifact          # Artifact + 版本 + 检索（含 operation_plan/result/code_project/deliverable_app/notebook）
derisk_serve.delivery          # 四类交付执行（notify/publish/execute/host）
derisk_serve.asset             # Asset CRUD + 版本 + 语义资产特化
derisk_serve.intervention      # 介入请求 + 强制沉淀
derisk_serve.trigger           # TriggerSource 包装调度能力
derisk_serve.action_executor   # execute 类交付的执行器（调 MCP/Skill 执行 operation_plan）
derisk_serve.skill_bundle      # SkillBundle 注册与管理（场景能力载体）
derisk_serve.hosting_runtime   # host 类交付的托管运行时（web_runtime/dashboard_viewer/data_explorer/doc_site/notebook_runtime）
```

**关键说明**：

- `workspace_resource` 是**统一资源入口**，但物理资源仍在各自 serve 模块——它只做"引用 + 视图 + 配置 overlay"
- `delivery` 服务按 category 分发：notify 调 channels，publish 调对应适配器（BI/Git/数仓），execute 调 `action_executor`
- `action_executor` 是 execute 类交付的核心：接收 `operation_plan` Artifact，调 MCP/Skill 执行，生成 `operation_result` Artifact，失败触发回滚 delivery

### 11.3 改造（小改动）

| 文件 / 模块 | 改动 |
|---|---|
| `gpts_app_config` 表 | 加 `owner_user_id` / `workspace_id` 列；backfill 自 `creator` |
| `gpts_conversations` 表 | 加 `task_id` 列 |
| `gpts_plans` / `gpts_work_log` | 加 `task_id` 列 |
| `derisk_app/openapi/api_v2/api_v2.py` | 注册新 router（含 workspace / workspace_resource / delivery 等） |
| `derisk_app/initialization/serve_initialization.py` | 注册新 serve 模块 |
| `web/src/app/` | 新增 `workspace/` 顶级路由；HomeChat 改造为 workspace-aware chat（不是子页） |
| `workspace_knowledge_link` | 数据迁移到 `workspace_resource(type=knowledge_space)`，旧表保留兼容期后下线 |
| `agent_subscription` | **删除**——空间用 `workspace.default_agent_app_code` 配置，不建订阅关系表 |

---

## 12. API 设计要点

### 12.1 路由组织（api_v2 下新增）

```
/api/v2/workspaces                         # CRUD
/api/v2/workspaces/{id}/members            # 成员管理
/api/v2/workspaces/{id}/tasks              # 任务列表/创建
/api/v2/workspaces/{id}/playbooks          # 剧本管理
/api/v2/workspaces/{id}/artifacts          # 产出物
/api/v2/workspaces/{id}/assets             # 资产
/api/v2/workspaces/{id}/triggers           # 触发源
/api/v2/workspaces/{id}/interventions      # 待办介入
/api/v2/workspaces/{id}/feed               # 活动流（任务/介入/产出聚合）

/api/v2/tasks/{id}                         # 任务详情/状态变更
/api/v2/tasks/{id}/runs                    # 执行轨迹
/api/v2/tasks/{id}/artifacts
/api/v2/tasks/{id}/interventions
/api/v2/tasks/{id}/close                   # 关闭（触发 distill 校验）

/api/v2/playbooks/{id}                     # 剧本详情
/api/v2/playbooks/{id}/versions            # 版本管理
/api/v2/playbooks/{id}/propose_change      # 演化提议（系统调）

/api/v2/interventions/{id}/resolve         # 处理介入（含 distill）

/api/v2/assets/{id}
/api/v2/assets/{id}/versions
/api/v2/assets/search                      # 跨资产检索（Agent 专精用）

/api/v2/artifacts/{id}
/api/v2/artifacts/{id}/deliver

/api/v2/workspaces/{id}/hosted              # 托管实例列表
/api/v2/workspaces/{id}/hosted/{hid}        # 托管实例详情/启停/归档
/api/v2/workspaces/{id}/hosted/{hid}/publish # 对外发布（需 Approve）
/api/v2/workspaces/{id}/hosted/{hid}/access # 访问托管实例（返回 URL 或 iframe token）
```

### 12.2 关键 API 约定

- 所有 Workspace 内 API 走 RBAC（复用 `feature_plugins/permissions/`）
- Task `close` 端点服务端强制校验 `distill` 完成；未完成返回 409
- Artifact 上传走 `derisk_serve.file` 现有文件服务，返回 `content_ref`
- Playbook DSL 提交时做 schema 校验，非法 DSL 直接 400，不允许保存

---

## 13. 前端 IA 设计

### 13.1 顶层路由调整

```
/login                          # 登录
/                               # 重定向到当前默认 Workspace
/workspaces                     # 我加入的空间列表
/workspaces/{id}                # 空间首页 = workspace-aware chat + 侧栏 + 交付物展示区
/workspaces/{id}/tasks          # 任务列表
/workspaces/{id}/tasks/{tid}    # 任务详情（执行轨迹/介入/产出/资产）
/workspaces/{id}/playbooks      # 剧本库
/workspaces/{id}/playbooks/{pid}# 剧本编辑器（策略声明 DSL 可视化）
/workspaces/{id}/artifacts      # 产出物库（按类型 tab，含可托管类型）
/workspaces/{id}/assets         # 资产库（按类型 tab）
/workspaces/{id}/resources      # 空间资源管理（SkillBundle/数据源/环境/...）
/workspaces/{id}/hosted         # 托管应用中心（所有 Host 类交付实例）
/workspaces/{id}/hosted/{hid}   # 托管实例访问（web 程序/看板/数据探索/notebook/文档站）
/workspaces/{id}/interventions  # 待我处理
/workspaces/{id}/members        # 成员
/workspaces/{id}/settings       # 空间设置（default_agent / 触发源 / 通知渠道 / 托管资源限额）
/me                             # 我的视图（跨空间聚合）
```

> **注**：移除了 `/workspaces/{id}/chat` 子页——chat 就是 workspace 首页本身，不是子页。现有 `application/app/`（Agent Builder）调整为 Builder Console，从 Workspace 设置进入或基于角色显式入口，不再是登录后默认页。

### 13.2 空间首页 = workspace-aware chat + 侧栏 + 交付物展示区

```
┌──────────────────────────────────────────────────────────────┐
│ [SRE 应急空间 ▾]  [我的]                  成员 12 / 任务 38  │
├──────────────────────────────┬───────────────────────────────┤
│  Chat（workspace-aware）     │  侧栏（实时刷新）              │
│                              │                               │
│  用户: 跑一次容量巡检        │  待我处理（3）                │
│  Agent: 已创建 task_124,     │   - task_123 应急复盘 Review  │
│         匹配容量巡检 Playbook│   - intv_45 上线 gate Approve │
│         开始执行...          │   - intv_46 对账 Reconcile    │
│                              │                               │
│  用户: 上次巡检报告在哪      │  进行中任务（5）              │
│  Agent: 找到 06-23 的报告    │   - task_124 容量巡检 running │
│         (asset_78)，要打开吗 │   - task_120 PR 部署 awaiting │
│                              │                               │
│  用户: 发给 SRE 组           │  本月空间成长                 │
│  Agent: 已创建邮件 Delivery  │   - 沉淀 Asset 12 个          │
│         状态 sent            │   - Playbook 演化提议 1 项    │
│                              │   - 处理任务 38 次（+15%）    │
│  [输入框]                    │                               │
│                              │  最近产出物                   │
│                              │   - 容量巡检报告 06-24        │
│                              │   - 事故复盘报告 06-23        │
├──────────────────────────────┴───────────────────────────────┤
│  交付物展示区（空间栖居的产出）                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ 📊 容量  │ │ 🔧 运维  │ │ 📋 复盘  │ │ 🌐 售前  │         │
│  │ 看板     │ │ 历史站   │ │ 报告库   │ │ Demo     │         │
│  │ running  │ │ running  │ │ hosted   │ │ running  │         │
│  │ [打开]   │ │ [打开]   │ │ [打开]   │ │ [打开]   │         │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
└──────────────────────────────────────────────────────────────┘
```

**关键设计**：

- **chat 是主交互区**，用户通过自然语言完成绝大多数操作（发起任务、查询进展、触发介入、配置订阅、分发产出、部署托管应用）
- **侧栏常驻**，展示当前 workspace 的实时状态——用户一边聊一边看任务进展，不需要切换页面
- **chat 是 workspace-aware 的**：自动感知当前 workspace 上下文（任务/Asset/Playbook/资源/托管应用），不是无状态对话
- **侧栏可点击跳转**：点待办项跳到介入处理，点任务跳到 Task 详情，点产出跳到 Artifact 查看
- **Chat 历史即 Task 历史**：chat 里的每次"有意义对话"自动挂到 Task 下，不重复存储
- **交付物展示区**（底部常驻）：展示空间内当前托管运行的交付物（看板/应用/文档站/notebook），点击直接打开。**让"空间栖居了什么"一眼可见**——这是"面向最终交付构建空间"在 UI 上的落地

### 13.3 关键页面

- **Task 详情**：时间线（AgentRun + gate 触发）+ 介入记录 + 产出物 + 引用/产出的 Asset。产出物若已托管，直接内嵌预览（如 dashboard 在 Task 详情内可看）。一个 Task 的全貌。从 chat 或侧栏待办进入。
- **Playbook 编辑器**：策略声明 DSL 可视化（四块：skills / context / gates / deliverables+distill）。支持版本 diff、回滚、演化提议审批。**不是步骤图**——没有步骤概念。
- **Asset 库**：按类型 tab（Runbook / Case / Metric / Template / Historical），支持搜索。Metric 类有专属"口径管理"子页。
- **产出物库**（artifacts）：按类型 tab（报告 / 数据集 / 看板 / 代码项目 / 可交付应用 / notebook / 操作记录）。已托管的产出物显示"running/hosted"标签 + 打开按钮。
- **资源管理**（resources）：按 category 分组（通用能力含 SkillBundle / 场景绑定物理 / 场景专属逻辑）。SkillBundle 展示包内 Skill 清单与版本。支持新增/编辑/绑定 Playbook/测试连通性。
- **托管应用中心**（hosted）：所有 Host 类交付实例的列表 + 状态（deploying/running/stopped/failed）+ 访问入口 + 生命周期管理（启停/归档/对外发布）。支持按类型筛选（web_app / dashboard / data_explorer / doc_site / notebook）。
- **托管实例访问**（hosted/{hid}）：直接打开托管的应用/看板/notebook。web_app 渲染为内嵌 iframe 或新窗口；dashboard 内嵌渲染；notebook 内嵌 Jupyter 环境；data_explorer 内嵌查询界面。
- **介入中心**：聚合所有待处理介入，支持快捷处理 + 强制 distill 表单。可从 chat 侧栏或独立页进入。
- **我的视图**（跨空间）：聚合所有空间的待办、我发起的任务、我参与的产出、我访问过的托管应用。workspace 切换器在顶部。

---

## 14. 落地路线图

### 14.1 阶段划分

| 阶段 | 周期 | 交付 | 验证目标 |
|---|---|---|---|
| **P1: Task 薄层 + workspace-aware chat** | 2-3 周 | Task 表/服务/API；`gpts_conversations.task_id`；chat 能创建/查询 Task | chat 不再是无状态对话，能感知 Task 上下文 |
| **P2: Workspace 骨架** | 3-4 周 | Workspace 表/服务/API；成员 RBAC；登录默认进 Workspace；knowledge-vault Space 收编为 workspace_resource | 用户视角叙事成立：登录后是"我的空间" |
| **P3: Playbook 策略声明 + 执行引擎** | 5-6 周 | Playbook declaration DSL（skills/gates/deliverables/distill）；runtime 引擎；AgentRun 表；SkillBundle 挂载 | SRE 容量巡检 + 数据运营月报两个 Playbook 实际跑起来，Agent 自主编排 |
| **P4: Artifact + Delivery** | 3-4 周 | Artifact 表/版本；三类 Delivery（notify/publish/execute）；action_executor | 产出物从对话里独立出来，能分发；Execute 类操作可执行 |
| **P5: Asset + 强制沉淀** | 4-5 周 | Asset 表/版本；语义资产特化；Task close distill 强制；Agent 专精上下文注入 | 跑过的 Task 真的沉淀下 Asset，下次 Task 能引用 |
| **P6: 人的介入机制** | 3-4 周 | HumanIntervention 表；介入模式 UI；介入中心；强制 distill | 人在显式 gate 介入，介入结果回流 Asset |
| **P7: Playbook 演化** | 4-6 周 | Skill 调用统计；gate 触发分析；演化提议生成；版本审批 UI | 空间能基于 Agent 实际行为提议改 Playbook，团队可审批 |
| **P8: Host 类交付与托管运行** | 5-7 周 | `artifact_hosting` 表；Host 类 Delivery 渠道（web_runtime/dashboard_viewer/data_explorer/doc_site/notebook_runtime）；托管应用中心 UI；生命周期管理；对外发布 Approve | 空间能托管/展示/部署运行交付物——售前 demo 能跑、运营看板能看、SRE 运维历史能查 |

> **注**：原"Agent Marketplace"已砍掉。Agentic 时代是"一个强 Agent + 多 SkillBundle"，不是"多 Agent 实例订阅"，没有规模也没有必要做 Marketplace。SkillBundle 的跨空间共享（如需要）放到 P8 之后单独评估。

### 14.2 P1-P2 可独立上线，验证后投入 P3+

**P1 + P2 完成后产品叙事就变了**——从"无状态 chat"变成"workspace-aware chat"。这是定位转变的关键节点。

**P1-P2 验证标准**（关键修正）：
- ❌ 错误标准："用户是否使用 workspace UI 而非 chat"
- ✅ 正确标准："用户的 chat 是否 workspace-aware"——能创建 Task、查询进展、引用 Asset、触发介入、配置 Trigger

如果用户用 chat 但每次从零开始（像 ChatGPT），那是失败；如果 chat 自动感知 workspace 上下文，那是成功。**先验证这个再投入 P3+**。

### 14.3 单场景验证策略

- P3-P5 期间全程在 SRE 场景验证（容量巡检 + 应急响应）
- P6 后引入数据运营场景（月报 + 对账）作为第二验证场景
- 两个场景都能覆盖后，再找第三个差异大的场景（合规审计 / 客户成功）做架构通用性压测

### 14.4 RFC 拆分对应

| RFC 编号 | 标题 | 对应阶段 |
|---|---|---|
| RFC-005 | Workspace 与成员模型 + WorkspaceResource | P2 |
| RFC-006 | Playbook 策略声明 DSL 与执行引擎 | P3 |
| RFC-007 | Artifact 与四类 Delivery（notify/publish/execute/host） | P4 |
| RFC-008 | Asset 模型与强制沉淀 | P5 |
| RFC-009 | Human Intervention 机制 | P6 |
| RFC-010 | Playbook 自演化（基于 Skill 调用统计） | P7 |
| RFC-011 | Host 类交付与托管运行时 | P8 |

P1（Task 薄层 + workspace-aware chat）改动小，直接走 issue + PR，不立 RFC。

---

## 15. 关键风险与取舍

| 风险 | 应对 |
|---|---|
| **`gpts_app_config.creator` 是字符串，backfill `owner_user_id` 可能丢用户** | 双写过渡：先加列双写，跑一个月确认稳定后再切查询 |
| **Playbook DSL 设计过复杂，用户不会写** | P3 同步做可视化编辑器；DSL 主要由"导出场景模板"产生，用户改不写 |
| **强制 distill 引起用户反感** | distill 表单极简化（"本次产出 / 是否新增案例 / 备注"三字段内）；提供"无沉淀"选项但需填理由 |
| **Asset 库膨胀** | content_ref 指向对象存储，DB 只存元数据；定期归档"未被引用 N 个月"的 Asset |
| **多空间共享 Asset 复杂度** | P8 之前不做跨空间 Asset；先让单空间跑通 |
| **Playbook 自演化误提议** | P7 只做"识别 + 推送提议"，不做自动改；人审批后才生效 |
| **执行引擎性能（多 Agent 并行）** | 复用现有 `derisk_serve.agent` 并行能力；DSL 的并行块映射到现有并行执行 |
| **执行轨迹跨表查询慢** | `task_id` 在 `gpts_conversations / gpts_plans / agent_run` 上建索引；Task 详情页用异步聚合 |

---

## 16. 不做什么（明确反向）

1. **不做"个人空间"作为主轴**：个人空间只在两种情况下作为子视图存在——Builder 的 personal sandbox、小团队的 minimal 单元。不为单用户场景单独设计产品线。
2. **不做"通用 Playbook 模板市场"**：Playbook 在 Workspace 内创建和管理；不做跨组织的 Playbook 商店。
3. **不重写 Agent / Skill / MCP / Knowledge 体系**：这些保持现状，空间层只引用不重造。重写会破坏现有用户。
4. **不做"workflow 编排型 DSL"**（关键修正）：Playbook **不规定步骤**，只声明 `skills + context + gates + deliverables + distill`。无 `steps`、无 `when`、无控制流。Skill 承载工作流知识，Agent 自主编排。把 Playbook 当 workflow 脚本写是开 Agentic 时代的倒车。
5. **不做"图灵完备的 Playbook DSL"**：无循环、无函数、无求值。复杂逻辑用 Skill 内的 markdown 指引 + Agent ReAct loop 表达，不用 DSL 表达。
6. **不做"所有 chat_history 自动进 Asset"**：Asset 必须显式沉淀，默认不沉淀。垃圾堆 ≠ 知识库。
7. **不做"全自动 Playbook 演化"**：演化只识别 + 提议，永远人审批。AI 改自己的剧本是红线。
8. **不做"无介入的 Attest 类场景"**：涉及责任背书的产出必须人签字，不允许 Agent 自动 Attest。
9. **不做"跨空间实时协作"**：空间是边界；跨空间只通过 Asset 提升与 SkillBundle 共享，不做实时多空间协作。
10. **不在 P3 之前做 Playbook 可视化编辑器**：先用 YAML/JSON 写，验证 DSL 设计正确后再投入可视化。
11. **不做"组织级部门空间"**：颗粒度贴场景，不贴部门组织架构树。部门是行政归属不是工作单元。
12. **不做"AI 自主 Execute"**：所有 execute 类交付（重启/部署/回滚/改配置/执行 SQL）必须人 Approve，无例外。`operation_plan` Artifact 无 approve 介入点的 Playbook，DSL 校验直接拒绝。
13. **不做"无回滚的 Execute"**：`operation_plan` 必须含 `rollback_plan`，DSL 校验拒绝空回滚。失败自动回滚不需二次 Approve（首次已授权）。
14. **不做"Execute 自动重试"**：执行类失败走回滚或人工介入，不自动重试（操作可能已部分执行，重试有风险）。
15. **不做"重造物理资源层"**：`workspace_resource` 只做引用 + 配置 overlay，不复制 `connect_config` / `mcp_server` 等全局物理注册。物理资源仍归各自 serve 模块。
16. **不做"WorkspaceResource 类型无限扩展"**：type 字段是固定枚举（见 6.9），新增类型需 RFC 评审，不允许业务侧自定义 type。
17. **不做"Agent Marketplace / AgentSubscription"**（关键修正）：Agentic 时代是"一个强 Agent + 多 SkillBundle 适配场景"，不是"多 Agent 实例订阅"。空间用 `default_agent` 配置即可，不建订阅关系表，不做 Agent 市场。SkillBundle 的跨空间共享如有需要，单独评估。
18. **不做"把 chat 退化为子页"**（关键修正）：chat 是 workspace 的主入口，不是 `/workspaces/{id}/chat` 子页。workspace 首页就是 workspace-aware chat + 侧栏。判断 P1-P2 成功的标准是"chat 是否 workspace-aware"，不是"用户是否离开 chat 用其他 UI"。

---

## 17. 附录：SRE 场景与数据运营场景的覆盖验证

### 17.1 SRE 场景

**空间资源**（WorkspaceResource）：
- `environment` 类：prod-cn-1 集群、payment 命名空间、核心交易环境
- `data_source` 类：监控库、日志库、CMDB
- `slo` 类：核心接口 p99<200ms、可用性 99.99%
- `oncall_rotation` 类：SRE 周轮值表
- `runbook_target` 类：各服务的重启/扩缩容命令模板
- `skill_bundle` / `skill` / `mcp` 类：SRE SkillBundle（巡检/应急/部署 Skill 包）/ K8s MCP

**工作流覆盖**：
- **容量巡检（Routine）**：TriggerSource timer → Playbook `pb_sre_capacity_routine` → AgentRun 取指标 → 加载 Asset 基线对比 → 异常则 Review 介入 → 生成报告 Artifact → 邮件 Delivery（Notify）+ **看板 Host 托管** → 强制 distill historical_artifact ✅
- **上线部署（Pipeline，含 Execute 交付）**：TriggerSource webhook (PR merge) → Playbook `pb_sre_deploy_pipeline` → 生成 `operation_plan`（含 manifest + rollback）→ Approve → `action_executor` 执行部署（Execute）→ `operation_result` Artifact → 失败自动回滚 + 触发应急 → 强制 distill case ✅
- **应急响应（Incident，含 Execute + Host 交付）**：TriggerSource alert → Playbook `pb_sre_incident` → 加载历史 case → Agent 生成 `operation_plan` → Approve → 执行 → `operation_result` 沉淀 → **运维历史站 Host 托管**（团队可按服务/时间检索）→ Escalate 介入 → 复盘 Review → 强制 distill runbook + case ✅
- **线上定位（Ad-hoc）**：用户从 workspace-aware chat 发起 → 关联 Playbook 模板 → Coach 介入 → 产出 analysis Artifact → 可选 distill ✅

### 17.2 数据运营场景

**空间资源**（WorkspaceResource）：
- `data_source` 类：业务库、数仓 ODS/DWD/ADS 层、实时数仓
- `data_pipeline` 类：日同步任务、实时 ingestion
- `bi_dashboard` 类：高管看板、运营看板（外部 BI）
- `slo` 类：数据新鲜度 <1h、准确率 99.9%
- `knowledge_space` 类：指标口径库、维度字典
- `skill_bundle` / `skill` / `mcp` 类：数据运营 SkillBundle（取数/对账/报表 Skill 包）/ 数仓 MCP

**工作流覆盖**：
- **月度经营报表（Routine + Pipeline + Publish + Host 交付）**：定时触发 → 加载 Metric/Dimension Asset → 多阶段取数 → Reconcile 对账 → Attest 签字 → 邮件 Delivery（Notify）+ BI 入库（Publish）+ **看板 Host 托管**（团队随时浏览）→ distill historical_artifact ✅
- **临时分析（Ad-hoc + Host 交付）**：用户从 chat 发起 → 关联 Metric Asset → Coach 介入 → 产出 analysis Artifact → 飞书 Delivery（Notify）+ **notebook Host 托管**（可重跑/修改分析）✅
- **数据回填（Pipeline，含 Execute 交付）**：用户发起 → Agent 生成 `operation_plan`（含回填 SQL）→ Approve → `action_executor` 执行 → `operation_result` → 入 Asset ✅
- **交付代码项目（Publish + Host 交付）**：Agent 生成 `code_project`（数据处理脚本）→ Approve → git push（Publish）+ **数据探索应用 Host 托管**（团队交互查询数据）✅
- **对账差异排查（Incident，派生自 Pipeline 失败）**：对账不一致 → 派生 Incident Task → 走应急 Playbook → Review 复盘 → distill case + lineage ✅
- **口径变更（Template + Lineage Asset）**：用户在 Asset 库改 Metric 定义 → 生成新 Asset 版本 → 历史 Artifact 引用旧版本不受影响 ✅

### 17.3 市场售前场景（第三覆盖验证）

**空间资源**（WorkspaceResource）：
- `data_source` 类：客户 CRM、市场调研库、竞品数据库
- `code_repo` 类：demo 项目仓库
- `api_endpoint` 类：客户系统 API、内部 LLM API
- `knowledge_space` 类：产品资料库、案例库
- `skill_bundle` / `skill` / `mcp` 类：售前 SkillBundle（调研/方案/demo 生成 Skill 包）/ Web 构建 MCP

**工作流覆盖**：
- **客户调研报告（Ad-hoc + Host 交付）**：销售从 chat 发起"调研 X 公司" → Agent 用售前 SkillBundle → 产出 report Artifact → **调研站 Host 托管**（销售/客户可浏览交互式报告）→ 邮件发客户链接（Notify，对外发布需 Approve）✅
- **售前 demo 站搭建（Pipeline + Host 交付）**：销售发起 → Agent 生成 `deliverable_app`（基于产品模板 + 客户定制）→ Approve → **Host 部署运行** → 生成访问 URL → 飞书发销售带 URL 的卡片 → demo 结束后定时停止 ✅
- **方案建议书（Ad-hoc + Publish 交付）**：Agent 生成 report → 内部 Review → PDF 发客户（Notify）+ 入 Asset 库（Publish）✅
- **竞品对比看板（Routine + Host 交付）**：定时更新 → Agent 生成 dashboard Artifact → **Host 托管** → 销售随时查最新对比 ✅

### 17.4 验证结论

三个差异较大的场景（SRE / 数据运营 / 市场售前）的**工作流 / 触发模式 / 介入模式 / 产出形态 / 沉淀类型 / 资源管理 / 交付类别**都能被同一套架构覆盖：

- **资源管理**：SRE 的环境/SLO/oncall、数据运营的数仓/流水线、市场售前的 CRM/调研库/code_repo，统一用 `workspace_resource` 表达
- **交付类别**：四类 Delivery 覆盖三个场景全部交付形态：
  - SRE：Execute（重启/部署）+ Host（运维历史站）+ Notify（告警通知）
  - 数据运营：Publish（BI/数仓）+ Host（看板/notebook）+ Notify（邮件）
  - 市场售前：**Host（调研站/demo 站）** + Notify（客户邮件）+ Publish（代码入库）
- **SkillBundle 适配**：每个场景挂自己的 SkillBundle，一个强 Agent 通用，不为场景造专精 Agent
- **Asset 子类型差异**：SRE 主用 Process + Template，数据运营主用 Semantic + Template，市场售前主用 Template + Historical——架构通过 Asset type 字段区分，不冲突
- **Host 类交付是关键差异化**：三个场景都有"交付物栖居在空间"的刚需——SRE 的运维历史、数据运营的看板/notebook、市场售前的调研站/demo。没有 Host 类，这些场景要么靠外部系统（破坏空间内聚），要么做不出来。

**架构成立**。三类资源 + **四类交付** + 四类工作流 + 六种介入 + 九种 Asset 子类型，构成完整的场景空间能力矩阵。**Host 类交付让"面向最终交付构建空间"真正落地**——空间不只是工作发生的地方，还是交付物栖居、展示、运行的地方。

---

## 18. 下一步

1. 本文档 review 通过后，立项 RFC-005 ~ RFC-010
2. P1（Task 薄层）直接进入实施，2-3 周内上线验证
3. P1 + P2 验证用户行为后，决定是否投入 P3+
4. P3 启动前需锁定 Playbook DSL v1 schema（RFC-006）
