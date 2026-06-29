# 场景空间产品形态设计（Scenario Workspace Product Form）

| 字段 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-06-29 |
| 作者 | yhjun1026 + Claude |
| 关联文档 | `docs/SCENARIO_WORKSPACE_DESIGN.md`（架构设计）、`docs/SCENARIO_WORKSPACE_MVP.md`（MVP 实施）、`docs/SCENARIO_WORKSPACE_DESIGN_DISCUSSION.md`（讨论前传） |

---

## 0. 文档定位

本文档定义**优秀的 AI 场景空间产品的终态形态**——用户看到什么、怎么用、产品叙事如何落地、核心能力如何组织。

- DESIGN 文档是**架构文档**——回答"系统由什么组成、怎么运转"
- MVP 文档是**实施文档**——回答"MVP 阶段交付什么"
- 本文档是**产品形态文档**——回答"终态产品是什么样"

**关键原则**：本文档按产品愿景定义终态，不按当前 MVP 已交付能力约束设计。落地节奏（P0/P1/P2）是第 8 节的事，不影响第 1-7 节的终态定义。design partner 是验证手段，不是设计上限。

---

## 1. 产品愿景

### 1.1 一句话愿景

> **场景空间是面向场景的 AI 团队协作产品——团队在空间里以剧本协作完成任务，产出物栖居在空间里被托管运行，沉淀的知识与案例让空间越用越懂这个团队。**

### 1.2 愿景的三个支柱

| 支柱 | 含义 | 反例（退化形态） |
|---|---|---|
| **场景化协作** | 人与 Agent 在剧本上演各自角色，介入点是剧本字段不是临时请求 | 退化成"和 Agent 临时对话"的 chatbot |
| **栖居式交付** | 产出物不只是发出去，还在空间里被托管、展示、部署运行 | 退化成"chat 里最后一条消息"就结束 |
| **可成长的团队记忆** | 跑过的任务变 Asset，交付物进图谱，下次同类任务自动加速 | 退化成"跑一万次还是第一天那么笨" |

**判断标准**：三支柱任何一维缺失，产品就退化回普通 Agent 平台。三支柱都立住，才是"优秀的 AI 场景空间产品"。

### 1.3 与本地工具的差异化

本地工具（Claude Code / Hermes / Cursor）在"个人单机"场景对云端是降维打击。场景空间的差异化在"团队场景"——本地工具无法覆盖的维度：

- **多人协作**：一个空间多成员多角色，本地工具是单人的
- **剧本复用**：团队 SOP 沉淀为 Playbook，本地工具每次从零
- **栖居式交付**：交付物在空间里托管运行，本地工具产出即结束
- **团队记忆**：空间越用越懂团队，本地工具是个人记忆不是团队记忆

**因此**：场景空间不做"个人空间"主轴，颗粒度贴场景/任务域，不贴部门也不贴个人。

---

## 2. 产品定位与边界

### 2.1 核心立场

**场景空间是 OpenDerisk 里长出来的独立产品，不是 OpenDerisk 的改造层。**

| 维度 | 确认 |
|---|---|
| 不动 | HomeChat (`/`) / Application Builder (`/application/app/`) / Agent / Skill / MCP / Knowledge Vault / DataResource 全部保持原状 |
| 复用 | 默认用标准 Agent 模板 BAIZE，空间可选通过 `default_agent_app_code` 覆盖为指定 Agent；通过 `workspace_resource(type=skill/mcp/knowledge_space/data_source/llm_model)` 引用现有原子能力；通过 `agent_chat.aggregation_chat` 接入 `workspace_context` |
| 自建 | workspace / task / playbook / artifact / workspace_asset / delivery / intervention / trigger 八个 serve 模块；前端 `/workspaces` 自治 |
| 入口 | 顶层导航单独一个"场景空间"入口（与 HomeChat、Application 并列），不接管登录默认页 |
| 用户 | 一个用户可加入多个 workspace；workspace 是组织单元不是个人容器 |

### 2.2 关键立场

- **不抢 HomeChat 位置**：HomeChat 是"和 Agent 聊天"的通用入口；场景空间是"团队在场景里协作完成任务、栖居交付、沉淀记忆"的独立产品。两条产品线并存。
- **空间不强制配 Agent**：默认用标准 Agent 模板 BAIZE，剧本（Playbook）声明 skills/context/gates/deliverables/distill——加载剧本即变成 BAIZE 的实际运行实例。空间可选通过 `default_agent_app_code` 覆盖为指定 Agent，但不是必须。空间默认只要有剧本就能运行。
- **Builder 在 Application Builder 建原子能力**：Skill / MCP / 数据源 / 知识库都是原子能力，归 Builder 管。Builder 不需要为每个空间配 Agent。场景空间只做编排和沉淀。
- **场景空间不抢 Builder 的活**：不在空间里配 Agent system prompt，不在空间里开发 Skill。

### 2.3 Builder 与 Consumer 的解耦

```
Builder（少数人）
  ↓ 在 Application Builder 开发 Skill / MCP / 数据源 / 知识库（原子能力）
  ↓ 发布到组织级原子能力库
  ↓（不需要为每个空间配 Agent，默认用 BAIZE）
  ↓
Consumer（多数人）
  ↓ 在场景空间创建 Workspace（创建即带内置剧本，立即可跑）
  ↓ workspace_resource 引用 Builder 建的原子能力
  ↓ Playbook 编排这些能力（剧本加载即变成 BAIZE 运行实例）
  ↓ 跑 Task → 产出 Artifact → Artifact 进 llm-wiki 图谱化 + Task close 强制 distill 沉淀 Asset
  ↓ 空间越用越懂团队
```

### 2.4 能力归属边界

| 能力 | 在哪建 | 场景空间的角色 |
|---|---|---|
| Agent 配置（system prompt / 模型 / 工具） | Application Builder (`/application/app/`) | 默认不配，用标准模板 BAIZE；空间可选通过 `default_agent_app_code` 覆盖。剧本加载即变成 BAIZE 的实际运行实例 |
| Skill 开发 | Agent Skills (`/agent-skills/`) | 通过 `workspace_resource(type=skill)` 引用 |
| MCP server 注册 | MCP (`/mcp/`) | 通过 `workspace_resource(type=mcp)` 引用 |
| 数据源注册 | Database (`/database/`) | 通过 `workspace_resource(type=data_source)` 引用 |
| 知识库 | Knowledge Vault (`/knowledge-vault/`) | 通过 `workspace_resource(type=knowledge_space)` 引用 |
| **Playbook 编排** | **场景空间内** | 自建，空间核心能力 |
| **Trigger 配置** | **场景空间内** | 自建 |
| **Asset 沉淀 + llm-wiki 图谱** | **场景空间内** | 自建（详见 §5.7） |
| **空间资源 overlay** | **场景空间内** | 自建（引用 + 配置 overlay，不重造物理资源） |

---

## 3. 核心范式：场景空间的主体不是 chat，是任务工作台

### 3.1 范式对比

| 维度 | HomeChat 范式 | 场景空间范式 |
|---|---|---|
| 主体 | 对话流 | **任务工作台** |
| 用户看的 | 每次工具调用、输入输出（过程透明） | **进展 + 交付**（结果导向） |
| 对话的角色 | 主体 | **任务的内嵌面板**（沟通记录） |
| 输入框的角色 | 产生对话 | **发指令**（创建/推进任务） |
| 工具调用细节 | 一等公民 | **二等公民**（默认折叠成进展步骤） |

### 3.2 关键判断

1. **场景空间没有"chat 页"，只有"任务工作台"**——对话是任务的内嵌面板（默认折叠摘要，展开看全），不是主体
2. **输入框常驻底部、跨任务通用**——是"指令入口"（产生任务/指令），不是"对话消息产生器"
3. **工具调用折叠成进展步骤**——用户看"做到哪了"，不看"Agent 怎么调工具"

### 3.3 与 HomeChat 的本质区别

| | HomeChat | 场景空间 |
|---|---|---|
| 进来看到 | 空对话或历史对话列表 | 空间大厅（任务/交付/介入概览） |
| 输入框产生 | 对话消息 | 任务或指令 |
| 主体 | 对话流 | 任务工作台 |
| 工具调用 | 平铺展示 | 折叠成进展步骤 |
| 历史叫什么 | 对话历史 | 任务历史（对话是任务的子标签） |

### 3.4 任务工作台组件的工程量

任务工作台是新组件，不复用 HomeChat 代码：

| 工作项 | 工程量 |
|---|---|
| 新任务工作台组件（`web/src/app/workspaces/detail/` 下重写） | 大 |
| 后端 Agent 回复需带结构化事件 payload（不只是文本，还有 event_type + payload） | 中——需改 `aggregation_chat` 流式输出协议 |
| 进展步骤实时更新（Task 状态变化推送） | 中——需 SSE 或轮询 |
| 双向联动（侧栏 ↔ 任务工作台锚点） | 小 |
| 不破坏现有 HomeChat | 0——独立组件，不动 `/chat` |

这是产品形态的核心投入。不付这个代价，"chat 是 workspace 主入口"就是空话。

---

## 4. IA 与导航

### 4.1 顶层导航

```
顶层导航（所有页面顶部）
├── HomeChat           /                    （现有，不动）
├── Application        /application/app/    （现有 Builder Console，不动）
├── 场景空间            /workspaces          （独立产品入口）
└── 我的                /me                  （跨空间聚合视图）
```

### 4.2 路由结构（终态完整）

```
/workspaces                          空间大厅（lobby）— 我加入的空间列表
  ├── 空间卡片网格（我加入的 + 我能加入的）
  ├── 顶部："+ 创建空间"
  └── 进入空间 → /workspaces/{id}

/workspaces/{id}                     空间首页 = 空间大厅（默认）⇄ 任务工作台（选中任务时）
/workspaces/{id}/tasks               任务列表
/workspaces/{id}/tasks/{tid}         任务详情（协作时间线 + 介入 + 产出 + 引用 Asset）
/workspaces/{id}/playbooks           剧本库
/workspaces/{id}/playbooks/{pid}     剧本详情（可视化编辑器 + DSL + 版本 + 演化提议）
/workspaces/{id}/triggers            触发源
/workspaces/{id}/interventions       介入中心（待我处理 + 历史，六种介入模式）
/workspaces/{id}/artifacts           产出物库（按类型 tab）
/workspaces/{id}/deliveries          交付中心（Notify/Publish/Execute/Host 四类）
/workspaces/{id}/hosted              托管应用中心（Host 类交付实例）
/workspaces/{id}/hosted/{hid}        托管实例访问（web 程序/看板/数据探索/notebook/文档站）
/workspaces/{id}/assets              资产库（historical_artifact / case / metric / ...）
/workspaces/{id}/knowledge           空间知识图谱（llm-wiki 可视化，复用 knowledge-vault 前端）
/workspaces/{id}/resources           空间资源管理（引用现有原子能力）
/workspaces/{id}/settings            空间设置（default_agent / 成员 / 通知渠道 / 托管资源限额）

/me                                  我的视图（跨空间聚合）
```

### 4.3 空间切换器

空间内所有页面顶部常驻下拉，列出"我加入的空间"，点击直接切。当前空间名常驻显示。**切换是上下文切换，不是页面跳转**——切换后任务工作台上下文、侧栏、可见资源全部跟着切。

---

## 5. 关键页面终态形态

### 5.1 空间大厅（进空间默认页）

进空间不是空对话，是"看我的空间有什么动静"。

```
┌──────────────────────────────────────────────────────────────────┐
│ [场景空间 ▾ SRE 应急空间]   [我的]    成员 12 / 任务 38 / 剧本 6  │
├──────────────────────────────────────────────────────────────────┤
│ Signal Chain: timer → 容量巡检剧本 → Review → Task → 报告        │
│ Loop:        queued 3 │ running 5 │ needs review 2 │ delivered 38│
├──────────────────────────────────┬───────────────────────────────┤
│                                  │  待我处理 (2)                 │
│  📋 进行中任务 (5)  [全部]       │   - task_123 应急复盘 Review  │
│  ┌────────────────────────────┐  │   - intv_45 上线 gate Approve│
│  │ task_124 容量巡检           │  │                               │
│  │ ◐ 报告生成中  · 2 项异常    │  │  本月空间成长                 │
│  │ timer · 06-24 02:00         │  │   - 沉淀 Asset 12 个          │
│  └────────────────────────────┘  │   - Playbook 演化提议 1 项    │
│  ┌────────────────────────────┐  │   - 处理任务 38 次 (+15%)     │
│  │ task_120 PR 部署             │  │   - 知识图谱节点 47 个        │
│  │ ⚠️ 待 Approve  · 等待 12m   │  │                               │
│  │ webhook · 06-24 10:30       │  │  最近交付物                   │
│  └────────────────────────────┘  │  ┌────────────────────────┐  │
│                                  │  │ 📄 容量巡检报告 06-24   │  │
│  🏠 栖居的交付物 (4)  [全部]     │  │ delivered · 2h ago     │  │
│  ┌──────────┐ ┌──────────┐      │  │ [打开]                  │  │
│  │ 📊 容量  │ │ 🔧 运维  │      │  └────────────────────────┘  │
│  │ 看板     │ │ 历史站   │      │  ┌────────────────────────┐  │
│  │ running  │ │ running  │      │  │ 📄 事故复盘报告 06-23   │  │
│  │ [打开]   │ │ [打开]   │      │  │ delivered · 1d ago     │  │
│  └──────────┘ └──────────┘      │  │ [打开]                  │  │
│                                  │  └────────────────────────┘  │
│  📨 最近交付 (3)  [全部]         │                               │
│  ┌────────────────────────────┐  │  最近介入 (5)  [全部]         │
│  │ 📄 容量巡检报告 06-24       │  │   - intv_45 上线 Approve     │
│  │ delivered · email · 2h ago  │  │   - intv_44 对账 Reconcile   │
│  └────────────────────────────┘  │   - intv_43 复盘 Review      │
│                                  │                               │
│  ⚡ 快捷发起                     │                               │
│  [+ 容量巡检]  [+ 应急响应]      │                               │
│  [+ 临时分析]  [+ 自定义]        │                               │
├──────────────────────────────────┴───────────────────────────────┤
│  [输入框 常驻底部]                                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 发起新任务...                                  [发送]      │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**关键设计**：
- **四块主线**：进行中任务 / 栖居的交付物 / 最近交付 / 快捷发起。栖居交付物是"面向最终交付构建空间"的可见性——空间不只是工作发生的地方，还是交付物栖居运行的地方
- **快捷发起**：基于空间挂载的 Playbook，一键发起。解决冷启动
- **侧栏四块**：待我处理 / 本月空间成长 / 最近交付物 / 最近介入。"本月空间成长"含知识图谱节点数，体现进化机制
- **输入框默认语义**："发起新任务..."

点任务卡片 → 主体切换为任务工作台（同一路由，不是新页面）。

### 5.2 任务工作台（主体切换态）

```
┌──────────────────────────────────────────────────────────────────┐
│ [场景空间 ▾ SRE 应急空间]   [我的]    成员 12 / 任务 38          │
├──────────────────────────────────────────────────────────────────┤
│ ← 返回大厅     task_124 容量巡检   timer · 06-24 02:00           │
├──────────────────────────────────┬───────────────────────────────┤
│                                  │  待我处理 (2)                 │
│  📊 进展                          │   - task_123 应急复盘 Review  │
│  ─────────────────────────       │   - intv_45 上线 gate Approve│
│  ✓ 取数完成  (db_query)    2m   │                               │
│    └ 12 项指标, 3 项偏离基线     │  本月空间成长                 │
│  ✓ 基线对比  (baseline_compare) │   - 沉淀 Asset 12 个          │
│  ✓ 异常检测  (anomaly_detect)   │   - Playbook 演化提议 1 项    │
│    └ 发现 2 项异常               │   - 处理任务 38 次 (+15%)     │
│  ◐ 报告生成中  (report)         │                               │
│  ○ 待 Review                      │  最近交付物                   │
│  ○ 待 Delivery                    │   - 容量巡检报告 06-24        │
│                                  │   - 事故复盘报告 06-23        │
│  📦 交付物                        │                               │
│  ┌────────────────────────────┐  │  本次任务引用的 Asset         │
│  │ 📄 容量巡检报告 06-24       │  │  ┌────────────────────────┐  │
│  │ 草稿 · v1                   │  │  │ 📚 asset_78 上次报告   │  │
│  │ [预览][发送][沉淀为 Asset]  │  │  │   historical_artifact  │  │
│  │ [托管为看板]                │  │  │   06-23                 │  │
│  └────────────────────────────┘  │  └────────────────────────┘  │
│                                  │  ┌────────────────────────┐  │
│  💬 协作对话 (3)  [展开完整对话] │  │ 📚 metric_p99_latency  │  │
│  > 用户: 跑一次容量巡检          │  │   metric · p99<200ms   │  │
│  > Agent: 已创建任务，加载 Skill │  └────────────────────────┘  │
│  > 用户: 上次报告在哪            │                               │
│  > Agent: 找到 asset_78，已引用  │  知识图谱关联                 │
│                                  │  ┌────────────────────────┐  │
│  📜 执行轨迹  [完整日志]         │  │ 🌐 本任务关联 5 个节点 │  │
│  AgentRun #3 · running · 3m      │  │   [查看图谱]            │  │
│  Skill 加载: db_query,           │  └────────────────────────┘  │
│    baseline_compare, anomaly_..  │                               │
├──────────────────────────────────┴───────────────────────────────┤
│  [输入框 常驻底部]                                                │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 给 task_124 下指令...                          [发送]      │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**关键设计**：
- **进展是 checklist 形态**——`✓ 取数完成 (db_query) 2m`，工具调用名是括号注脚，不是主体。点开可看工具输入输出（默认折叠）
- **交付物卡片常驻**——产出物一等公民，[预览][发送][沉淀为 Asset][托管为看板] 四个动作直接在卡片上。"托管为看板"是 Host 类交付的入口
- **协作对话默认折叠**——只显示最近 3 条摘要，点"展开完整对话"才看全。对话是任务的子标签
- **执行轨迹**——AgentRun 列表，想看 Agent 内部细节的人点进去。默认不展开
- **侧栏含本次任务引用的 Asset + 知识图谱关联**——Asset 是结构化快照，llm-wiki 图谱是关联知识
- **输入框语义切换**："给 task_124 下指令..."

### 5.3 主体的三种状态

输入框永远在底部，但主体根据状态切换：

| 状态 | 主体显示 | 输入框语义 |
|---|---|---|
| **无当前任务**（进空间默认） | 空间大厅 | "发起新任务..." |
| **有当前任务** | 任务工作台（进展 + 交付 + 对话） | "给这个任务下指令..." |
| **多任务并行** | 任务列表（每个一行进展摘要），点选某个进入工作台 | "发起新任务..." |

### 5.4 剧本库 + 可视化编辑器（终态）

剧本是空间的"能力配置"。终态含可视化编辑器。

**剧本库**（`/workspaces/{id}/playbooks`）：
- 卡片网格：剧本名 / scenario_type / task_type / trigger / 当前版本 / 上次运行 / 运行次数 / 演化提议数
- 卡片操作：[编辑] [查看运行历史]
- 顶部："+ 新建剧本"

**剧本详情**（`/workspaces/{id}/playbooks/{pid}`）：
- Tabs：[可视化编辑] [DSL] [运行历史] [演化提议] [版本]

**可视化编辑器终态**（四块声明可视化）：
```
┌──────────────────────────────────────────────────────────────────┐
│ 剧本: 容量巡检  v3                            [版本历史] [激活]  │
├──────────────────────────────────────────────────────────────────┤
│ Tabs: [可视化编辑] [DSL] [运行历史] [演化提议] [版本]            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─── ① Skills（可用能力包）──────────────────────────────────┐ │
│  │ ☑ db_query        ☑ baseline_compare                       │ │
│  │ ☑ anomaly_detect  ☑ report                                 │ │
│  │ [+ 添加 Skill]                                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─── ② Context（执行前加载）────────────────────────────────┐ │
│  │ Assets Required:                                            │ │
│  │   - type: historical_artifact | query: type=capacity_report│ │
│  │     LIMIT 1                          [+ 添加]              │ │
│  │ Resources:                                                  │ │
│  │   - ref(resource:prod_core_db)      [+ 添加]              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─── ③ Gates（不变量）──────────────────────────────────────┐ │
│  │ [+] 添加 Gate                                               │ │
│  │ ┌────────────────────────────────────────────────────────┐ │ │
│  │ │ review_if_anomaly                                      │ │ │
│  │ │ after_skill: anomaly_detect                            │ │ │
│  │ │ condition: anomalies_detected == true                  │ │ │
│  │ │ intervention: Review "检测到异常，是否升级为应急？"    │ │ │
│  │ │ blocks: [deliverables]                  [删除]          │ │ │
│  │ └────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─── ④ Deliverables + Distill ─────────────────────────────┐  │
│  │ Deliverables:                                              │  │
│  │   - type: report | delivery: notify/email/sre-team@...    │  │
│  │                                    [+ 添加]                │  │
│  │ Distill (forced: ☑):                                      │  │
│  │   - type: historical_artifact | from: deliverable.report  │  │
│  │   - type: case | when: anomalies_detected == true         │  │
│  │                                    [+ 添加]                │  │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ [校验]  [保存为新版本]  [激活]                                  │
└──────────────────────────────────────────────────────────────────┘
```

**关键设计**：
- **可视化编辑器是终态**——四块声明各一个区块，结构化表单编辑，不用手写 YAML
- **DSL tab 仍保留**——可视化与 DSL 双向同步，高级用户可改 DSL
- **演化提议 tab**——Agent 实际行为偏差 → 系统提议改剧本 → 人在此审批
- **版本管理**——新版本需"激活"才生效，旧版本可回滚
- **剧本库显示运行统计**——让剧本"活"起来

### 5.5 介入中心（六种介入模式终态）

人在剧本上演角色的可见入口。终态含六种介入模式（Approve / Coach / Escalate / Review / Reconcile / Attest）。

```
┌──────────────────────────────────────────────────────────────────┐
│ 介入中心              [待处理 (5)] [历史 (38)] [按类型筛选 ▾]    │
├──────────────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ ⚠️ intv_45 · Approve                                       │  │
│ │ task_120 PR 部署                                            │  │
│ │ 触发剧本: pb_sre_deploy_pipeline                            │  │
│ │ ───────────────────────────────                             │  │
│ │ 问题: 即将部署 payment_svc v2.3.1，预计 5s 抖动，确认执行？│  │
│ │                                                              │  │
│ │ 📦 关联 Artifact: operation_plan                            │  │
│ │   actions: [restart payment_svc, scale to 5]                │  │
│ │   rollback: [scale to 3, restart v2.3.0]                    │  │
│ │   [查看 dry-run 预览]                                       │  │
│ │                                                              │  │
│ │ 决策: ◉ Approve  ○ Reject  ○ Escalate                      │  │
│ │ 决策理由: ___________________________________________       │  │
│ │                                                              │  │
│ │ 📝 强制沉淀（distill）                                       │  │
│ │   沉淀为 Asset 类型: [Case ▾]                               │  │
│ │   案例标题: _________________________________________        │  │
│ │   摘要: _______________________________________________     │  │
│ │                                                              │  │
│ │ [处理]                                                      │  │
│ └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**六种介入模式**：

| 模式 | 场景 | 人做什么 | 强制沉淀 |
|---|---|---|---|
| **Approve** | 上线 gate、回滚决策 | 看证据做决策 | 决策理由 → Asset（case） |
| **Coach** | Agent 方向错了 | 纠正、补上下文 | 纠正规则 → Asset（runbook / case） |
| **Escalate** | Agent 卡住 | 接手最难部分 | 接管轨迹 → Asset（case） |
| **Review** | Incident 结束、Routine 异常 | 复盘根因 | 复盘结论 → Asset（runbook + case） |
| **Reconcile** | 数据对账 | 人独立算一遍核对 | 差异说明 → Asset（lineage） |
| **Attest** | 财务报表签字 | 责任背书 | 签字记录 → Artifact 版本绑定（不可篡改） |

**关键设计**：
- 介入是结构化表单，不是聊天——决策 + 理由 + 强制 distill 三段
- 关联 Artifact 可预览——Execute 类的 operation_plan 必须可看 dry-run + rollback
- 强制 distill 内嵌——不填完不放行 resolve，硬约束
- 从空间大厅/任务工作台/侧栏待我处理都可进入——多个入口

### 5.6 交付中心（四类交付终态）

终态含四类 Delivery（Notify / Publish / Execute / Host），交付中心是四类交付的统一管理入口。

#### 5.6.0 交付链路的职责分层

交付分两段，Agent 与程序职责清晰分工：

```
Generate 段（Agent 主导）
  Agent 产出 Artifact（报告/operation_plan/deliverable_app/...）
  Agent 识别交付意图（"发给 SRE 组" / "部署运行"）
       ↓
Deliver 段（程序主导，Agent 不参与执行）
  程序按 Playbook 声明或 Agent 解析的意图调用 Delivery 服务
  Delivery 服务按 channel 执行（notify/publish/execute/host）
  Execute 类强制 Approve + rollback 保护
  Host 类走生命周期管理
       ↓
结果回流
  delivery.result_json 记录结果
  Execute 产出 operation_result Artifact
  失败走重试/回滚/告警（工程化路径）
```

**Deliver 段四类交付都程序完成，Agent 不参与执行**：

| 交付类别 | 谁执行 | 理由 |
|---|---|---|
| **Notify** | 程序 | 确定性操作（收件人/格式/渠道都是 Playbook 声明的），Agent 来做只是多一次 LLM 调用，慢且不可靠 |
| **Publish** | 程序 | 确定性操作（写入目标/格式/外部资产 ref 都是声明好的），程序调适配器即可 |
| **Execute** | 程序（Agent 最不该做） | operation_plan 已人 Approve，执行就是按 plan 调 action_executor。Agent 介入会引入"临时改主意"风险，破坏 Approve 的确定性，审计失效 |
| **Host** | 程序 | 确定性部署（构建+部署+健康检查），工程化流程，Agent 来做没价值 |

**Agent 在 Deliver 段的角色**：只做"意图解析 + 调用 Delivery 服务"，不做执行。即使临时交付（用户在对话里说"把这份报告发给老板"，无预设 Playbook），也走程序化 Delivery 服务——Agent 解析意图传 `artifact_id + channel + target`，程序执行。所有 Deliver 路径统一，可审计。

**为什么 Deliver 段不该 Agent 做**：
- 确定性丢失：Playbook 声明 `delivery: notify/email/sre-team@...`，程序按声明执行是确定的。Agent 可能"临时觉得飞书更合适"就改渠道，破坏声明式契约
- 可审计性破坏：Execute 类必须可追溯"按 Approve 的 plan 执行"，Agent 介入执行 = 执行过程不可预测 = 审计失效
- 性能与成本：发邮件这种确定性操作调 LLM 是浪费
- 失败处理复杂化：程序失败走重试/回滚/告警是工程化路径，Agent 失败要处理 LLM 不确定性，复杂度爆炸



**交付中心**（`/workspaces/{id}/deliveries`）：
```
┌──────────────────────────────────────────────────────────────────┐
│ 交付中心              [Notify (12)] [Publish (8)] [Execute (3)] [Host (4)]│
├──────────────────────────────────────────────────────────────────┤
│ Notify 类                                                        │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ 📨 email → sre-team@... · 容量巡检报告 06-24 · sent · 2h   │  │
│ │ 📨 feishu → oncall 群 · 应急通知 · sent · 1h                │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ Publish 类                                                       │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ 📤 bi_dashboard → 高管看板 · Q3 经营报表 · published · 1d   │  │
│ │ 📤 code_repo → demo 仓库 · 售前 demo v2 · pushed · 2d       │  │
│ │ 📤 asset_library · 容量巡检报告 · published · 2h            │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ Execute 类                                                       │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ ⚡ action_executor · 重启 payment_svc · executed · 1h       │  │
│ │   └ operation_result: 成功 · 5s 抖动 · 已 distill 为 case  │  │
│ │ ⚡ action_executor · 扩缩容 · rolled_back · 2h              │  │
│ │   └ 失败回滚 · 已 distill 为 case                           │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ Host 类（栖居交付物）                                            │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ 🏠 web_runtime · 售前 demo 站 · running · 2d · [打开][停止]│  │
│ │ 🏠 dashboard_viewer · 容量看板 · running · 5d · [打开]     │  │
│ │ 🏠 data_explorer · Q3 数据集 · running · 1d · [打开]       │  │
│ │ 🏠 notebook_runtime · 临时分析 · stopped · 3d · [启动]     │  │
│ │ 🏠 doc_site · 运维历史站 · running · 7d · [打开]           │  │
│ └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**四类交付**：

| 类别 | 做什么 | 副作用 | 例子 |
|---|---|---|---|
| **Notify** | 把 Artifact 推给某人/某群 | 信息流动 | 邮件/飞书/钉钉/站内信 |
| **Publish** | 把 Artifact 写入外部持久系统 | 创建/更新外部资产 | BI 看板/数仓表/代码 repo/对象存储/Asset 库 |
| **Execute** | 把 operation_plan 在真实世界执行 | 改变系统状态 | 重启/部署/扩缩容/回滚/改配置/执行 SQL |
| **Host** | 把 Artifact 在空间内托管运行 | 空间内常驻可访问 | web 程序/看板/数据探索/notebook/文档站 |

**Execute 类的特殊保护**（产品形态终态要求）：
- 强制 Approve，无例外——operation_plan 无 approve 介入点的 Playbook，DSL 校验拒绝
- Dry-run 预览——执行前必须能预览会发生什么
- 回滚计划强制——operation_plan.rollback_plan 不可为空，DSL 校验拒绝空回滚
- 执行结果沉淀为 Artifact——operation_result 必须 distill 成 case
- 失败升级——Execute 失败自动触发 downstream_playbook（应急 Playbook）

**Host 类的生命周期管理**（产品形态终态要求）：
- 完整生命周期：deploying → running → stopped → archived（+ failed）
- 访问控制分层：空间内访问 / 组织内发布 / 对外发布（需 Approve）
- 资源限额与成本控制——长期未访问自动休眠或归档
- 版本化托管——一个 Artifact 可有多个版本被托管
- 健康检查与自愈——deliverable_app 的 health_check 字段
- 托管即 Asset——长期有价值的托管实例可提升为 Asset

### 5.7 资产库 + llm-wiki 知识图谱（双路径终态）

场景空间的知识沉淀是**双路径**——结构化快照（WorkspaceAsset）+ 非结构化图谱（llm-wiki），职责不同，并存不硬结合。

**双路径分工**：

| 路径 | 职责 | 数据流 | 检索方式 |
|---|---|---|---|
| **Task close → WorkspaceAsset** | 结构化快照燃料 | Task close 强制 distill → historical_artifact / case / metric / ... → 下次同类任务启动时 context_builder 加载注入 prompt | 按 type / source_task_id 查询，直接注入 |
| **Artifact → llm-wiki** | 交付内容图谱化 | Artifact 产出 → ingest pipeline（L0 verbatim → L1 wiki 页 + wikilink → L2 图谱边）→ Agent 通过 graph_query / doc_search 检索 | 图谱查询（traverse/backlinks/timeline）+ 语义检索 |

**资产库**（`/workspaces/{id}/assets`）：
- 按类型 tab：Runbook / Case / Metric / Dimension / Catalog / Lineage / ReportTemplate / SqlTemplate / HistoricalArtifact
- Metric 类有专属"口径管理"子页（valid_from / valid_to 时间版本）
- 每个 Asset 带版本历史

**空间知识图谱**（`/workspaces/{id}/knowledge`）：
- 复用 knowledge-vault 前端（RawView / WikiView / GraphView / SchemaEditor / LintView）
- 展示 Artifact 自动 ingest 形成的图谱：交付物之间引用关系、实体关联、演化脉络
- Agent 专精上下文注入时检索此图谱

**为什么不独立建交付内容管理、也不硬结合**：
- llm-wiki 已是完整知识系统（L0/L1/L2 + vaultfs + 4 种检索 + 图谱查询 + 20 个 Tool），独立建是重造且更弱
- WorkspaceAsset 是"快照"范式（冻结、版本化、直接注入），llm-wiki 是"演化"范式（关联、脉络、图谱检索），两个范式不该塞进同一张表
- Artifact 直接进 llm-wiki（不双写 Asset），避免同步问题

**Agent 专精上下文注入**（双路径都查）：
- WorkspaceAsset 提供结构化快照（"上次容量巡检报告说 X"）
- llm-wiki 提供图谱化知识（"X 这个指标关联了哪些维度、派生了哪些报表"）

### 5.8 我的视图（`/me`，跨空间聚合）

```
┌──────────────────────────────────────────────────────────────────┐
│ 我的视图                                                          │
├──────────────────────────────────────────────────────────────────┤
│ 📋 待我处理（跨所有空间）  (5)                                   │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ [SRE 空间] task_123 应急复盘 Review              2h ago    │  │
│ │ [数据运营] intv_45 月报对账 Reconcile            30m ago   │  │
│ │ [SRE 空间] intv_46 上线 gate Approve             12m ago   │  │
│ └────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│ 🚀 我发起的任务  (3 running / 12 closed)                          │
├──────────────────────────────────────────────────────────────────┤
│ 📦 我参与的产出  (8)                                              │
├──────────────────────────────────────────────────────────────────┤
│ 🏠 我访问过的栖居交付物  (3)                                      │
├──────────────────────────────────────────────────────────────────┤
│ 🏠 我加入的空间  (3)                                              │
│ ┌──────────────────────────┐ ┌──────────────────────────┐      │
│ │ SRE 应急空间             │ │ 数据运营空间             │      │
│ │ 12 成员 / 38 任务 / 4 栖居│ │ 8 成员 / 22 任务 / 2 栖居│      │
│ │ [进入]                   │ │ [进入]                   │      │
│ └──────────────────────────┘ └──────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

五块：待我处理 / 我发起的任务 / 我参与的产出 / 我访问过的栖居交付物 / 我加入的空间。

---

### 5.9 触发与调度

场景空间有两类定时/事件需求，走两条不同的路。**`derisk_serve.cron` 是通用基础模块，不耦合业务逻辑**——所有业务语义（workspace / trigger / 维护作业）在业务层。

#### 5.9.1 两类需求的本质区分

| 类别 | 例子 | 本质 | 归属模块 |
|---|---|---|---|
| **A. 任务触发型** | 定时跑容量巡检、IM 消息触发任务、API 触发任务、监控告警触发任务 | **创建一个 Task**，走 Playbook 执行 | `derisk_serve.trigger`（已有 workspace_id + target_playbook_id） |
| **B. 空间维护型** | 定期整理 Asset、生成 Playbook 演化提议、llm-wiki 知识结构化、归档长期未访问的托管实例 | **不创建 Task**，是空间自身的后台维护作业 | `derisk_serve.workspace.automation`（新增子模块） |

**关键区分**：
- A 类是"用户配置意图 → 定时/事件触发任务"——trigger 模块本职，已有 workspace 维度
- B 类是"空间自己定期整理自己"——不是任务，是维护作业，跟 Playbook/Task 无关
- 两类塞进同一模块会混乱：A 类有 target_playbook_id，B 类没有；A 类创建 Task，B 类不创建；A 类用户配置，B 类空间内置

#### 5.9.2 A 类：任务触发（trigger 模块，补 timer 自调度）

现状 trigger 的 timer 不自调度（MVP 留的口子，config.cron 只存不执行）。需补：
- trigger 创建/更新 timer 类型时，**注册到 `derisk_serve.cron`**（cron payload 是"调 trigger.fire 端点"）
- cron 到点只负责"回调这个 payload"，不关心 payload 是什么业务
- trigger.fire 被回调后创建 Task，走 Playbook 执行
- 删 trigger 时同步删 cron job

四类触发方式：

| 触发方式 | 现状 | 终态 |
|---|---|---|
| **timer** | config.cron 只存不执行，靠外部 cron 调 fire | 注册到 cron 模块自调度，到点自动 fire |
| **webhook** | `/triggers/{id}/webhook` 公开端点，已有 | IM 平台（飞书/钉钉）配回调 URL 到此端点 → fire → Task |
| **alert** | `/triggers/{id}/alert` 公开端点，已有 | 监控告警 webhook POST 到此端点 → fire → Task |
| **manual** | 已有 | 用户在空间大厅快捷发起 / 任务工作台输入框发指令 → Task |

**IM 触发**：复用 trigger 现有 webhook 端点，不新接。IM 平台侧配回调 URL 即可。
**API 触发**：复用 `/triggers/fire`（API key 鉴权），外部系统调即可。

#### 5.9.3 B 类：空间维护（workspace automation 子模块）

空间维护作业是空间业务概念，归 `derisk_serve.workspace.automation` 管，不塞进通用 cron 模块：

- workspace serve 新增 `automation` 子模块
- 空间创建时，automation 注册一组"空间维护作业"到 `derisk_serve.cron`（cron payload 是"调 workspace automation 的某个维护方法"）
- cron 到点回调，automation 负责实际维护逻辑
- cron 模块保持通用（只管"到点回调 payload"），不知道 workspace、不知道"整理 Asset"、不知道业务语义

空间内置维护作业：

| 维护作业 | 做什么 | 频率 |
|---|---|---|
| **Asset 归档** | 长期未引用的 Asset 归档（content_ref 指向对象存储，DB 只存元数据） | 每周 |
| **Playbook 演化提议** | 扫描 Skill 调用统计 + gate 触发分析，生成演化提议（只提议不自动改） | 每周 |
| **llm-wiki 知识结构化** | 定期把散落 L0 加工成 L1/L2，反哺 Asset 检索 | 每日 |
| **托管实例休眠** | 长期未访问的 Host 实例自动休眠或归档，释放资源 | 每日 |
| **空间成长统计** | 计算"本月空间成长"卡片数据（沉淀数/演化提议数/任务趋势/图谱节点数） | 每日 |

#### 5.9.4 分层原则

```
通用基础层：derisk_serve.cron
  职责：到点回调 payload（at/every/cron 三种调度）
  不做：不知道 workspace、不知道业务语义
  ─────────────────────────────────────
业务层：derisk_serve.trigger / derisk_serve.workspace.automation
  trigger：任务触发（timer 注册到 cron，fire 创建 Task）
  automation：空间维护（注册到 cron，回调执行维护方法）
  ─────────────────────────────────────
死代码：derisk_app/initialization/scheduler.py
  全项目无人用，建议清理（另提 issue，不在本 spec 范围）
```

---

### 5.10 Playbook 与 Agent 动态能力的结合

**这是空间能力的命脉**。Agent 架构已支持运行时动态传入 MCP / Skill / 子 Agent / 数据源 / 知识库 / 自定义资源，Playbook 是声明层——两者结合 = "声明即运行"。

#### 5.10.1 Agent 动态资源能力现状（已支持）

`aggregation_chat` 通过两条并行通道接收运行时动态资源：

| 通道 | 传入方式 | 支持的资源类型 |
|---|---|---|
| `chat_in_params: List[ChatInParamValue]` | 结构化，每项含 param_type/sub_type/param_value | Skill / MCP / 数据源 / 知识库 / 文件 / 模型策略 / Temperature / MaxNewTokens |
| `ext_info["extraTools"]` / `["dynamic_resources"]` / `["extra_agents"]` | 直接传已构建对象 | 工具（MCP/HTTP/LOCAL/SKILL）/ 动态资源 / 子 Agent |
| `ResourceManager.register_resource` | 注册新 type | **自定义资源类型**（场景专属） |

**已支持运行时动态传入**：工具（MCP/HTTP/LOCAL/SKILL）、数据库、Skill、子 Agent、知识库、文件、模型策略、自定义资源类型。
**仍是静态配置**：App 本身的 agent 类型 / team_mode / system_prompt_template / Sandbox / LLM 渠道。

#### 5.10.2 核心缺口（必须补）

> `workspace_resource.physical_ref` 到 `AgentResource` 的自动物化链路**未实现**——当前 `build_workspace_context` 只把 `physical_ref` 作为字符串塞进 system_prompt，没有实际物化成 Agent 可调用的工具/资源。

**现状**：空间挂载资源（`workspace_resource` 表存了 skill/mcp/knowledge_space/data_source 的 physical_ref），Agent 运行时只看到 prompt 里的 ref 字符串，**不能实际调用**。空间资源是"装饰"不是"能力"。

**终态**：空间挂载资源是 Playbook 声明，运行时物化成 Agent 实际工具/能力，Agent 能直接调用。空间资源是"能力"。

#### 5.10.3 Playbook DSL → Agent 运行时注入的映射

Playbook runtime 的职责：把 `workspace_resource.physical_ref` 解析成 `AgentResource`，组装 `chat_in_params` + `dynamic_resources` + `extra_agents`，注入 `aggregation_chat`。

| Playbook DSL 声明 | → | Agent 运行时注入 |
|---|---|---|
| `skills: [ref(resource:sre_capacity_bundle)]` | → | `chat_in_params.sub_type="agent_skill"` × N（SkillBundle 展开成多个 skill） |
| `context.resources: [ref(resource:prod_core_db)]` | → | `chat_in_params.sub_type="datasource"` |
| `context.resources: [ref(resource:k8s_mcp)]` | → | `chat_in_params.sub_type="mcp(derisk)"`（get_mcp_info 取 mcp_servers/headers/source/timeout） |
| `context.resources: [ref(resource:ops_knowledge)]` | → | `chat_in_params` 走 knowledge ResourceManager |
| `context.resources: [ref(resource:analyzer_agent)]` | → | `ext_info["extra_agents"]`（动态子 Agent，`_build_extra_employees` 构建） |
| `context.resources: [ref(resource:custom_slo)]` | → | 自定义资源类型（ResourceManager.register_resource 注册） |
| `gates: [...]` | → | 空间层监控 AgentRun 输出（不改 Agent） |
| `deliverables: [...]` | → | 空间层校验产出完整性（不改 Agent） |
| `distill: [...]` | → | 空间层强制沉淀（不改 Agent） |

#### 5.10.4 SkillBundle 与动态 Skill 的关系

SkillBundle 是空间层的**能力包抽象**（一组协同 Skill），不是新机制：
- 空间挂载 SkillBundle = 管理一组协同 Skill 的打包
- 运行时物化时，SkillBundle 展开成多个 `chat_in_params.sub_type="agent_skill"` 项
- Agent 架构本来就能动态接收多个 Skill——SkillBundle 是空间层对这些 Skill 的"组织抽象"，运行时展开

这样 SkillBundle 不重复造 Agent 的 Skill 加载机制，只是空间层的管理单元。

#### 5.10.5 自定义资源类型

Agent 架构支持 `ResourceManager.register_resource` 注册新 type。场景空间可定义场景专属资源类型：
- SRE 场景：`slo` / `oncall_rotation` / `runbook_target`
- 数据运营：`data_pipeline` / `bi_dashboard`
- 市场售前：`api_endpoint` / `code_repo`

注册成 Agent 可识别的资源类型后，Agent 能直接调用这些场景资源（如查 SLO、查 oncall、触发流水线），不只是看 prompt 字符串。

**扩展机制**：`ResourceManager.register_resource` 注册新 type，subclass 实现 `resource_parameters_class`。`chat_in_params` 中未识别的 `sub_type` 会尝试包成 `AgentResource.from_dict` 透传。

#### 5.10.6 空间层约束不改 Agent

`gates` / `deliverables` / `distill` 是空间层约束，通过监控 AgentRun 输出实现，不改 Agent 架构：

- `gates`：空间层监控 AgentRun 输出的结构化字段，匹配 condition 时创建 `human_intervention`，Task 进入 `awaiting_human`
- `deliverables`：Task 关闭前空间层校验产出完整性（是否产出了声明类型的 Artifact？是否执行了声明渠道的 Delivery？）
- `distill`：Task 关闭前空间层校验沉淀完整性（是否完成了声明类型的 Asset 沉淀？）

**关键立场**：Agent 架构负责"动态加载资源 + 自主编排"，空间层负责"声明资源 + 监控约束 + 校验产出"。两者职责清晰，不互相侵入。

#### 5.10.7 结合的产品价值

- **声明即运行**：Playbook 声明 `ref(resource:xxx)`，运行时自动物化成 Agent 实际能力，不需要用户手动配 Agent 工具
- **空间资源是真能力**：空间挂载的资源 Agent 能直接调用，不是 prompt 装饰
- **SkillBundle 是组织抽象**：空间层管理协同 Skill 包，运行时展开成 Agent 动态 Skill
- **场景资源可扩展**：场景专属资源（SLO/oncall/pipeline）注册成 Agent 可识别类型
- **Agent 架构不被侵入**：gates/deliverables/distill 是空间层约束，不改 Agent

**这是"空间越用越懂团队"的命脉**——如果空间挂载的资源 Agent 用不了，Playbook 就只是文档；运行时物化链路打通后，Playbook 是可执行的能力配置。

---

## 6. 三机制在产品里的完整可见性

三机制（协作 / 进化 / 交付）是产品愿景的三个支柱，必须在 UI 上可见，否则价值不可感知。

| 机制 | 可见形态 |
|---|---|
| **协作** | 任务工作台的"协作对话"+"执行轨迹"；介入中心的待办列表；Task 详情的协作时间线（谁/Agent 在何时做了什么） |
| **进化** | 空间大厅侧栏"本月空间成长"卡片（沉淀 Asset 数 / Playbook 演化提议数 / 任务处理趋势 / 知识图谱节点数）；剧本编辑器的"演化提议" tab；资产库的版本历史 |
| **交付** | 空间大厅"栖居的交付物"区；任务工作台交付物卡片（[预览][发送][沉淀][托管]）；交付中心四类 tab；托管应用中心 |

**让用户每次进空间都看到"这个空间在成长、在交付、在让我参与"**——这是产品叙事的核心。

---

## 7. 冷启动路径

**最大风险**：空空间 = 没价值。

### 7.1 冷启动路径

1. **创建空间即带内置剧本，立即可跑**：SRE 场景空间创建时预置"容量巡检""应急响应"剧本；数据运营空间预置"周报""对账"剧本。模板来自 MVP 已交付的 `builtin_examples.py`。**不需要 Builder 先配 Agent**——默认用 BAIZE，剧本加载即运行实例
2. **快捷发起按钮**：空间大厅的"快捷发起"基于已挂载的内置剧本，一键发起，不需要用户写 YAML
3. **第一次跑就有产出**：Playbook 跑完产出 Artifact + Delivery（邮件/飞书），用户立刻看到价值
4. **强制 distill 引导**：第一次 close Task 时引导填 distill，让 Asset 库开始有内容
5. **Artifact 自动进 llm-wiki 图谱化**：第一次产出 Artifact 后自动 ingest 进 llm-wiki，空间知识图谱开始积累

### 7.2 关键判断

冷启动不靠"Builder 先配 Agent"，也不靠"产品自己长出来"，靠"内置剧本 + BAIZE 默认 + 快捷发起"。Builder 只在有新 Skill / MCP 需求时介入，不为每个空间配 Agent。

---

## 8. 落地路径

终态定义在第 1-7 节。本节是分阶段落地路径，**每项都指向第 5 节已定义的终态**。分档是落地节奏，不是产品形态完整性边界。

### 8.1 P0（叙事翻盘，必做）

| 落地项 | 指向终态 | 改动 |
|---|---|---|
| **场景空间 chat 重写为任务工作台** | §5.2 | 新组件，主体是进展+交付+对话折叠，输入框常驻底部 |
| **空间大厅作为进空间默认页** | §5.1 | 主体切换为大厅（进行中任务/栖居交付物/最近交付/快捷发起） |
| **本月空间成长卡片** | §5.1 侧栏 | 新查询 + 新卡片（沉淀数/演化提议数/任务趋势/知识图谱节点数）。注：演化提议 P2 才做生成，P0 期间此项恒为 0，卡片先占位 |
| **顶部 workspace 切换器** | §4.3 | 顶部下拉，列我加入的空间 |
| **workspace_resource 物化链路** | §5.10 | Playbook runtime 把 `physical_ref` 解析成 `AgentResource`，组装 `chat_in_params` + `dynamic_resources` + `extra_agents` 注入 aggregation_chat。这是空间能力的命脉——没有它空间资源是装饰 |

### 8.2 P1（产品形态完整度，应做）

| 落地项 | 指向终态 | 改动 |
|---|---|---|
| **任务工作台进展 checklist** | §5.2 | 工具调用折叠成步骤化 checklist，需后端带结构化事件 payload |
| **交付物卡片常驻任务工作台** | §5.2 | 任务工作台主体常驻交付物卡片 + [预览][发送][沉淀][托管] |
| **协作对话默认折叠** | §5.2 | 任务工作台对话区默认 3 条摘要，展开看全 |
| **快捷发起按钮** | §5.1 | 空间大厅基于已挂载 Playbook 一键发起 |
| **我的视图扩成跨空间工作面板** | §5.8 | 5 块：待我处理/我发起的/我参与的产出/我访问过的栖居交付物/我加入的空间 |
| **交付内容图谱化（结合 llm-wiki）** | §5.7 | 新增 artifact extract_mode + Artifact 创建后触发 ingest + context_builder 查询 llm-wiki 图谱 |
| **trigger timer 自调度** | §5.9.2 | trigger 创建/更新 timer 时注册到 `derisk_serve.cron`，cron 到点回调 trigger.fire。cron 保持通用不耦合业务 |

### 8.3 P2（终态能力落地，按 DESIGN 路线图）

| 落地项 | 指向终态 | 备注 |
|---|---|---|
| **Playbook 可视化编辑器** | §5.4 | 四块声明可视化编辑，DSL 双向同步 |
| **六种介入模式完整支持** | §5.5 | Approve/Coach/Escalate/Review/Reconcile/Attest 全实现 |
| **Execute 类交付** | §5.6 | operation_plan + 强制 Approve + dry-run + rollback + operation_result distill |
| **Host 类交付与托管运行时** | §5.6 + §5.1 栖居区 | artifact_hosting 表 + web_runtime/dashboard_viewer/data_explorer/doc_site/notebook_runtime + 托管应用中心 UI + 生命周期管理 |
| **Playbook 自演化** | §5.4 演化提议 tab | Skill 调用统计 + gate 触发分析 + 演化提议生成 + 版本审批 |
| **空间维护作业（workspace automation）** | §5.9.3 | workspace.automation 子模块 + 空间内置维护作业（Asset 归档/演化提议/llm-wiki 结构化/托管休眠/成长统计）注册到 cron |
| **自定义资源类型注册** | §5.10.5 | 场景专属资源（slo/oncall/pipeline 等）通过 ResourceManager.register_resource 注册成 Agent 可识别类型 |
| **跨空间 Asset 共享** | §5.7 | 先让单空间跑通后再做 |
| **Asset 语义子类型完整** | §5.7 | Metric/Dimension/Catalog/Lineage/Template 等完整子类型 |

### 8.4 P0+P1+P2 全部完成 = 第 5 节终态成立

P0 是叙事翻盘，P1 是完整度，P2 是终态能力。三档全部完成，第 5 节定义的优秀 AI 场景空间产品终态成立。

---

## 9. 不做什么（产品形态层面否决）

以下是在产品形态层面**永久否决**的设计方向，不是落地推后。理由是这些方向与产品愿景冲突。

1. **不做"个人空间"作为主轴**：本地工具（Claude Code / Hermes / Cursor）在个人单机场景对云端是降维打击。个人空间只在两种情况下作为子视图存在——Builder 的 personal sandbox、小团队的 minimal 单元。不为单用户场景单独设计产品线。
2. **不做"Agent Marketplace / AgentSubscription"**：Agentic 时代是"一个强 Agent + 多 SkillBundle 适配场景"，不是"多 Agent 实例订阅"。空间用 `default_agent` 配置即可（默认 BAIZE，可选覆盖），不建订阅关系表，不做 Agent 市场。
3. **不做"Playbook 作为 workflow DSL"**：Playbook 是策略声明（skills + context + gates + deliverables + distill），不是步骤脚本。无 steps、无 when、无控制流。Skill 承载工作流知识，Agent 自主编排。把 Playbook 当 workflow 脚本写是开 Agentic 时代的倒车。
4. **不做"图灵完备的 Playbook DSL"**：无循环、无函数、无求值。复杂逻辑用 Skill 内的 markdown 指引 + Agent ReAct loop 表达，不用 DSL 表达。
5. **不做"所有 chat_history 自动进 Asset"**：Asset 必须显式 distill，默认不沉淀。垃圾堆 ≠ 知识库。
6. **不做"全自动 Playbook 演化"**：演化只识别 + 提议，永远人审批。AI 改自己的剧本是红线。
7. **不做"无介入的 Attest 类场景"**：涉及责任背书的产出必须人签字，不允许 Agent 自动 Attest。
8. **不做"AI 自主 Execute"**：所有 Execute 类交付必须人 Approve，无例外。operation_plan 无 approve 介入点的 Playbook，DSL 校验直接拒绝。
9. **不做"无回滚的 Execute"**：operation_plan 必须含 rollback_plan，DSL 校验拒绝空回滚。
10. **不做"重造物理资源层"**：workspace_resource 只做引用 + 配置 overlay，不复制 connect_config / mcp_server 等全局物理注册。物理资源仍归各自 serve 模块。
11. **不做"WorkspaceResource 类型无限扩展"**：type 字段是固定枚举，新增类型需 RFC 评审，不允许业务侧自定义 type。
12. **不做"组织级部门空间"**：颗粒度贴场景，不贴部门组织架构树。部门是行政归属不是工作单元。
13. **不做"把 chat 退化为子页"**：任务工作台是空间主入口，不是 `/workspaces/{id}/chat` 子页。空间首页就是任务工作台 + 侧栏。
14. **不做"重造知识系统"**：交付内容图谱化结合 llm-wiki，不独立建。WorkspaceAsset 与 llm-wiki 双路径并存，不硬结合。
15. **不动 HomeChat / Application Builder / Agent / Skill / MCP / Knowledge Vault**：独立产品边界，场景空间只复用 Agent 框架作为引擎。
16. **不重造调度器/不耦合 cron 通用模块**：`derisk_serve.cron` 是通用基础模块（只管"到点回调 payload"），不耦合 workspace / trigger / 业务语义。任务触发走 trigger（timer 注册到 cron），空间维护走 workspace.automation（注册到 cron），cron 模块保持通用。
17. **不让 Agent 参与 Deliver 段执行**：Deliver 段四类交付（Notify/Publish/Execute/Host）都程序完成。Agent 只做 Generate 段（产出 Artifact + 识别交付意图），Deliver 段只解析意图调 Delivery 服务，不执行。Execute 类尤其不能 Agent 做——Approve 后必须按 plan 确定执行。
18. **不让 Agent 侵入空间层约束**：gates / deliverables / distill 是空间层约束，通过监控 AgentRun 输出实现，不改 Agent 架构。Agent 架构负责"动态加载资源 + 自主编排"，空间层负责"声明资源 + 监控约束 + 校验产出"，两者职责清晰不互相侵入。

---

## 10. 产品形态一句话

> **场景空间是 OpenDerisk 里长出来的独立产品——默认用标准 Agent 模板 BAIZE + 剧本加载即运行（不强制配 Agent），以"任务工作台"为主体（不是 chat），输入框常驻底部跨任务通用，进空间默认看到空间大厅（任务/栖居交付物/介入概览），创建空间即带内置剧本立即可跑；Playbook 声明的资源运行时物化成 Agent 动态能力（声明即运行，空间资源是真能力不是 prompt 装饰），四类交付（Notify/Publish/Execute/Host）由程序确定性执行让产出真正栖居落地，Artifact 进 llm-wiki 图谱化 + Task close 强制 distill 沉淀 Asset，触发与空间维护复用通用 cron 调度器但业务语义在业务层，让空间越用越懂团队。HomeChat、Application Builder 保持原状，场景空间只复用 Agent 框架作为引擎。**

---

## 11. 下一步

1. 本文档 review 通过后，对 P0 四项落地项立项 issue + PR
2. P0 验证"叙事翻盘"——design partner 登录后看到的是空间大厅不是 HomeChat，任务工作台主体是进展+交付不是平铺对话
3. P0 + P1 完成后，场景空间作为独立产品形态成立（终态的 P0+P1 子集）
4. P2 各项按 DESIGN 文档路线图推进，逐步逼近第 5 节定义的终态
