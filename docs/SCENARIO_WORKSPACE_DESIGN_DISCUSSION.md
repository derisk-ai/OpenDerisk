# Scenario Workspace — 设计讨论原始记录

> 本文档是 2026 年 6 月 Scenario Workspace 功能在 OpenDerisk 项目上落地之前，用户与助手之间的原始设计讨论记录。它捕获了**设计思考的过程**——问题如何被发现、方案如何被反复打磨、哪些选项被考虑又被否决、用户在关键节点做了哪些纠偏——而不是最终的实施计划。
>
> 实施计划本身记录在 `docs/SCENARIO_WORKSPACE_MVP.md` 与 `~/.claude/plans/proud-orbiting-shamir.md` 中；最终的设计文档是 `docs/SCENARIO_WORKSPACE_DESIGN.md`。本文档是这两个文档的"前传"——它记录的是"为什么是这样设计"的思考过程。
>
> 讨论以中文为主，关键用户原话保留中文原文。

---

## 1. 设计问题陈述：是什么触发了这次工作

### 1.1 用户最初的洞察

整个讨论由用户的开场问题触发。用户指出 OpenDerisk 当前的产品形态过于技术化，缺少真实使用者的视角：

> **用户（开场）**：「讨论一个产品设计和演进方向，现在整个 OpenDerisk 的产品设计是一个 Agent 开发管理平台，所有的逻辑都是在做如何配置管理使用一个 Agent，包括要开发配置 Agent 所要用到的相关资源、功能管理等模块。但是如果站在一个具体的业务场景，用户角度来看整个产品、页面、功能设计太技术化了。」
>
> 「我在思考整个 Agent 系统应该是分两个视角——Agent 视角，用户视角。在 Agent 视角下的产品是围绕如何构建、使用、管理 Agent 来做（如当前）；另一个是用户视角，用户登录后，是给用户构建了一个个人空间，在这个空间里他管理使用自己的 Agent 完成需求，产出交付内容，并能持续维护进行自己的个人空间。」
>
> 「面对 Agent 视角是一个 Agent 如何配置，完成了多少次需求。站在个人视角应该是——我有哪些任务，每个任务由哪些 Agent 做了什么任务最终完成，交付什么。」

### 1.2 助手对问题的概括

助手把这个洞察提炼为一句话：

> **「当前产品的根本问题是"以 Agent 为中心组织信息架构"，而真实用户的心智是"以我要完成的任务为中心"——Agent 只是手段，交付物才是结果。」**

### 1.3 现状分析：OpenDerisk 当前架构的"种子"与"缺口"

用户要求先做深度分析再讨论方案：

> **用户**：「你有看下当前系统的架构设计 和当前的 产品模块吗？先做个深度分析 再讨论下可行方案设计。」

助手分析了 `packages/` 后端分层、`web/` 前端路由、35 张数据库表后，识别出几个关键事实：

**已有的"种子"（不需要从零开始）**：

1. `knowledge-vault` 的 Space 概念——每个 Space 绑定 `default_agent_id`、`llm_model`、`embedder_model`，是"个人/团队工作空间"的雏形，只是当前只装了知识。
2. `gpts_conversations.user_code`——对话已经归属用户，只是没人把它当成"用户工作流"来组织。
3. `gpts_plans` / `gpts_kanban` / `gpts_work_log`——执行轨迹已经记录"Agent 做了什么"，但缺一个上层 Task 实体把它们聚合成"一次需求交付"。
4. `db_learning_task` / `db_learning_subtask`——这是代码里已经存在的 Task + Subtask 模型，可以作为通用 Task 实体的参考模板。
5. `feature_plugins/permissions/` 的 RBAC plugin——多租户权限的底座已经搭好。
6. `gpts_app_config` 已有 `is_published` / `version_info` / `agent_version`——Agent 发布流已经具备雏形。

**主要缺口**：

| 缺口 | 影响 |
|---|---|
| 没有 Task 实体 | 用户视角的"我有哪些需求在进行"无法表达 |
| 没有 Artifact 实体 | Agent 产出混在 chat_history 里，无法独立版本化、分享、复用 |
| 没有 User Workspace | 用户登录后没有"我的空间"，只有"和某个 Agent 聊" |
| Agent 无订阅/安装关系 | Builder 发的 Agent 无法被 Consumer "装进我的空间" |
| `gpts_app_config.owner` 只是字符串列 | 没有硬性所有权关系，多用户场景下 Agent 归属模糊 |
| 执行轨迹散落 | plans/kanban/work_log 各自为政，没有一个"Task 视图"聚合 |

**一个被忽视的信号**：`serve_initialization.py` 里有 TODO 标注 knowledge 模块正在从 `derisk-app` 迁移到 `derisk-serve`——这表明项目正在把"配置型模块"下沉到 serve 层，正是演进 Consumer 视角的好时机。

### 1.4 第一轮方案：双视角 + 个人空间

助手最初提出的方案是 **Builder Shell + Consumer Shell + 个人 Workspace**，核心叙事是"用户登录后第一屏看到的不是 Agent 列表，而是我正在进行中的任务 + 待我处理的 Agent 产出"。

这个方案在第二轮就被用户否决了（见下文）。

---

## 2. 用户视角的关键纠偏：从"个人空间"到"场景空间"

### 2.1 用户对"个人空间"的否决

第一轮方案提了"个人 Workspace"作为产品主轴，用户立即反驳：

> **用户**：「不过好像个人空间这个是伪命题吧。如果我都个人了我直接本地直接部署一个个人 Agent 如 Hermes / Claude Code 就行了，没必要在一个 web 服务上使用。或者说一个企业级的原生 Agent 产品，应该是要以组织、部门或者具体事情场景来构建空间，大家在这个空间共同在云端使用 AI 完成任务，构建出一个可成长的 AI 团队空间？你觉得哪种方向和思考更有道理？」

### 2.2 助手对"个人空间伪命题"的论证

助手接受了这个纠偏，并把论点精确化：

> **「本地 AI 工具（Claude Code / Hermes / Cursor）在"个人单机使用"这个场景上，对云端 web 服务是降维打击——更快、更隐私、更可控、更便宜（不交订阅费）、能直接改本地文件。一个人如果只是要"用 AI 完成自己的事"，没有理由去用一个云端 SaaS。」**
>
> 「**但"个人空间"作为产品主轴是伪命题，不等于"个人视图"不存在**。它的正确位置是团队空间内的一个子视图（我的草稿、我的任务、我的私有 Agent），就像 Slack 有 DM、Notion 有 My Workspace、Linear 有 My Issues——这些都是团队产品里的个人子视图，不是独立产品。」

### 2.3 单位不是"组织"也不是"部门"，是"场景/任务域"

用户问"AI 原生的场景空间怎么设计"，助手进一步精确化空间的颗粒度：

> **「按部门建空间（"市场部空间""工程部空间"）会陷入和 Notion / 飞书一样的同质化竞争，因为部门是横向容器，没有任务结构。更有差异化的单位是"场景空间"：」**
>
> - 事故响应空间（SRE + 代码 + 日志 + 复盘报告）
> - 季度经营分析空间（数据 + 报表 + 结论）
> - 客户上线空间（合同 + 配置 + 验收）
> - 风险排查空间（OpenDerisk 当前主场景，其实已经是这个形态）
>
> 「每个场景空间里：成员（人 + Agent）、知识、Agent 模板、任务历史、产出物都**为这个场景量身定制**，并随使用积累。这是"可成长"的真正含义——不是泛泛地"积累聊天记录"，而是某个场景的 Agent 团队、SOP、知识库、模板产出在反复使用中越来越成熟。」
>
> 「**部门是行政归属，场景是工作发生的真实单位。AI 团队空间的颗粒度应该贴场景，不贴部门。**」

### 2.4 修正后的核心定位

> **「OpenDerisk 是面向场景的 AI 团队空间平台。每个空间是一个组织单元（按场景/任务域划分），人与 Agent 在其中协作完成任务，沉淀的知识、Agent 模板、产出物让团队在同类场景下越来越高效。」**

---

## 3. 用两个场景验证设计：SRE + 数据运营

用户主动用两个具体场景来"压测"设计是否成立。这是整个讨论中最重要的验证手法——所有抽象结论都被这两个场景反复打磨。

### 3.1 SRE 场景（用户提出）

> **用户**：「你的分析很完整，我拿一个具体的场景来讨论，比如现在是一个 SRE 场景，具体在这个场景要做的事情是，线上变更部署、应急运维、容量管理。每个具体的工作都会有自己独立的 workflow 也就是 skill。在这个空间里可能是通过定时任务触发了容量巡检、也可能是一个 PR 提交触发了上线部署，或者一个监控告警触发了应急，或者用户主动发起了一次线上定位。我理解站在这个 SRE 业务空间的视角，核心是管理业务需求也就是各种渠道进来的任务？和解决各种任务的资源（Agent、skill、mcp、知识库等）？然后在需要的时候把人链接进来进行授权、确认吗？」

### 3.2 助手对 SRE 场景的拆解：三步重要洞察

#### 洞察一：四种触发不是四种任务，是同一个 Task 模型的四种入口

> **「触发源（定时/webhook/告警/人）→ 统一进 Task 队列 → Task 类型决定走哪个 Playbook → Playbook 编排 Agent 团队 + 资源 + 介入点 → 产出 Artifact → 部分沉淀回 Asset。」**
>
> 「**为什么必须统一**：因为同一个线上问题，可能从告警进来（Incident），也可能从用户主动定位进来（Incident），也可能从例行巡检发现异常升级而来（Routine → Incident）。如果按触发源分四种 Task，升级和关联就做不了。**Task 的本质是"一次需要被完成的工作"，触发源只是它的一个属性**。」

#### 洞察二：四类工作不是孤立任务，是"三类工作流 × 四种触发"的交叉

| 类别 | 例子 | 特征 |
|---|---|---|
| **Routine 例行型** | 容量巡检、每日健康检查、配置漂移检测 | 重复执行、可比较、异常才升级。**价值在历史对比，不在单次执行** |
| **Pipeline 流水线型** | 上线部署、变更审批、回滚 | 多阶段、强顺序、每段有明确 gate。**价值在 SOP 的稳定性** |
| **Incident 应急型** | 监控告警应急、线上定位 | 时间紧、信息缺、决策重、要复盘。**价值在响应速度 + 经验复用** |

> 「**Routine 型核心是基线和对比**——这次巡检的指标要和上次比、和阈值比、和趋势比。光跑 Agent 没用，得有"历史这次巡检的结论"作为上下文。
> **Pipeline 型核心是检查门和回滚**——每段都要能验证、能停、能回滚。Agent 不是主角，SOP 才是主角。
> **Incident 型核心是记忆调用 + 决策加速**——应急时最值钱的是"上次同类事故怎么处理的"。Agent 现场推理永远比不过"调用上次事故的复盘结论"。」

#### 洞察三：资源不是"管理对象"，是"Playbook 的可编排组件"

> 「**空间不直接"拥有 Agent"，空间拥有 Playbook，Playbook 引用 Agent**。同一个 SRE-Agent 在"容量巡检 Playbook"里只读不写，在"应急 Playbook"里有写权限——权限和角色是 Playbook 给的，不是空间全局给的。」
>
> 「**资源层（Agent/Skill/MCP/知识库）保持现有 derisk-serve 的设计**，空间层只通过 Playbook 引用它们。**空间不重复造资源管理，空间造的是 Playbook 和 Asset**。这是省力的关键，也是边界清晰的关键。」

#### 洞察四：人不是来"授权"的，是来"判断"和"教"的

> 「如果人只做授权确认，那人在空间里就是个人肉盖章机，AI 越强人越累（因为要确认的决策越来越多）。」
>
> 「**重点是最后那一列**。人介入的"动作"不值钱，人介入后**留下的结构化沉淀**才值钱。如果没有这一步，人在空间里做的所有事都随着离职流失——这恰恰是传统运维体系最大的问题：老 SRE 走了，经验也走了。」
>
> 「所以 SRE 空间里人的设计原则是：**每次人的介入都必须有一个"沉淀动作"配套**。审批了要记理由、纠正了要写规则、接管了要留轨迹、复盘了要改剧本。**强制沉淀是空间进化的硬约束**，不是可选 nicety。」

### 3.3 数据运营场景（用户提出）

> **用户**：「嗯你说的很对，再用一个数据运营空间来举例。运营财务相关人员需要在空间里使用 Agent 去当前的在线系统数据库里分析，整理数据，给出数据报表、文档等。可能要定时出数据报表发邮件，也可能需要临时用户上来提分析需求。在这个空间下之前的空间维度设计是否能很好的覆盖？」

### 3.4 数据运营场景暴露的两个盲点

助手回答："**覆盖度大概 70%，但暴露了之前设计里两个被 SRE 场景掩盖的盲点——产出物的"使用方式"和"复用口径"**"。

#### 盲点一：产出物的"使用方式"被忽略了

> 「SRE 场景的 Artifact（巡检报告、复盘结论、runbook）大多**在空间内消费**——人看、人用、沉淀进 Asset。产出完就完了，"发到哪去"不是核心问题。
>
> 数据运营不一样。报表的"使用方式"是产出流程的**一部分**，不是事后动作：
>
> | 产出 | 使用方式 | 频率 |
> |---|---|---|
> | 月度经营报表 | 邮件发给高管 + 存档 + 入 BI | 每月固定 |
> | 临时分析结论 | 飞书/钉钉给提需求的人 + 存档 | 按需 |
> | 对账差异报告 | 触发审批流给财务负责人 | 异常时 |
> | 数据口径定义 | 进 Asset 库 + 同步到数据字典系统 | 偶尔 |
>
> **Artifact 不能只"生成 + 沉淀"，还要"分发"**。分发对象、分发渠道、分发格式（PDF/Excel/BI 链接/消息卡片）是产出流程的一等公民。」

**修正方向**：Playbook 的最后一步不该只是"生成 Artifact"，而要显式声明 **Delivery**——发邮件 / 推消息 / 写 BI / 触发下游 Playbook。Artifact 是"被产出了什么"，Delivery 是"它去了哪、被谁以什么形式消费"。

#### 盲点二：复用口径比复用流程更值钱

> 「SRE 的 Asset 主要是 **runbook + 案例 + 模板**——复用的是"流程怎么走"和"上次怎么处理的"。
>
> 数据运营场景里，**比流程更值钱的是"口径"**：
> - "活跃用户"怎么定义？口径定下来，所有报表都用同一个
> - "GMV" 包不包含退款？跨报表必须一致
> - "月度"是自然月还是 28 天？财务月 vs 运营月不一样
> - 某个指标的计算 SQL 上次是怎么写的？为什么那么写？
>
> 这些口径是**跨任务复用**的资产，不是单次 Task 的产出。如果每个临时分析需求都让 Agent 重新理解"活跃用户是什么"，结果一定不一致，财务会疯掉。」

**修正方向**：Asset 层必须显式有一类 **Semantic Asset（语义资产）**——Metric / Dimension / Catalog / Lineage。**关键：这些语义资产是 Agent 生成 SQL/报表前的强制上下文**。靠 Agent 自觉是不行的，必须在 Playbook 层强制注入。

#### 数据运营还暴露了新的人介入模式

> 「数据场景多一种独特的人介入模式：**对账（Reconcile）**。财务报表的特殊性在于：Agent 算出来的数字必须和某个权威来源对得上，否则不能发出。这不是 Approve（人做判断要不要继续），是 **Verify（人和 Agent 独立算一遍，看是否一致）**。」
>
> 「还有一种：**背书（Attest）**。报表发出去前需要财务负责人签字确认"这个数据我认"。和 Approve 的区别是——Approve 是决策"要不要做下一步"，Attest 是责任承担"这个数字我背书"。这种动作要留下不可篡改的审计痕迹。」

### 3.5 第三个场景：市场/售前（用于进一步压测）

后续讨论中又加入了第三个场景——市场售前可能要交付调研 web 程序，进一步逼出了 **Host 类交付**的概念（见 §4.7）。

---

## 4. 核心设计概念及其推理过程

### 4.1 Workspace（场景空间）

**核心定位的转变**：
- 第一轮：个人 Workspace（被否决，伪命题）
- 第二轮：组织/部门空间（被否决，会陷入 Notion / 飞书同质化）
- 第三轮：**Scenario Workspace（场景空间）**——颗粒度贴场景不贴部门

**空间不是"装东西的文件夹"，是"一个有剧本的 AI 团队"**：

> 「把空间想象成一个长期共事的项目组：它有自己的成员（人 + Agent）、自己的工作套路（SOP）、自己的记忆（"上次这种事我们是怎么处理的"）、自己的产出习惯（模板、口径、格式）。新成员（人或 Agent）加入时，是被"onboard 进这个上下文"的，而不是从零开始。」

**空间的五层结构**：

| 层 | 内容 | 作用 |
|---|---|---|
| **Cast 成员层** | 人（按角色：owner / approver / contributor）+ Agent 团队 | 决定"谁在这个场景里干活" |
| **Playbook 剧本层** | 场景的 SOP，声明式定义 | 决定"事情怎么被推进" |
| **Memory 记忆层** | 知识库（L0 原文 / L1 Wiki / L2 图谱）+ 历史任务 + 历史决策 | 决定"这个空间懂多少" |
| **Work 工作层** | 进行中的 Task + Task 下的 AgentRun + 对话 + 计划看板 | 当下在发生什么 |
| **Asset 资产层** | 可复用的产出物 + 可复用的 Agent 配置 | 决定"下次做同类事能多快" |

**关键立场**：

> 「Work 层是流动的，Asset 层是沉淀的。很多产品把这两层混在一起（聊天记录就是资产），结果既不能复用也检索不动。空间设计必须显式区分"工作流过的水"和"沉淀下来的结晶"——**Task 完成时必须有一个"沉淀到 Asset"的动作**，不能默认所有东西都留下来。」

### 4.2 Task（任务）

**核心设计取舍**：四种触发统一进 Task 队列，触发源是 Task 的属性而非类型。

**Task 状态机**（MVP 简化版）：`draft / running / awaiting_human / closed / archived`

**Task 之间可关联、升级、派生子任务**——这是"Routine → Incident"跨类型升级的基础。

### 4.3 Playbook（剧本）—— 这个设计里最重要的概念转变

**Playbook 的设计经历了整个讨论中最大的范式转变**：

#### 第一版（被否决）：Workflow 脚本

最初 Playbook 被设计为 YAML 步骤脚本：

```yaml
# 第一版（被否决）— workflow 思维
steps:
  - id: fetch_metrics
    agent: sre_data_agent
    skill: db_query_skill
  - id: compare_baseline
    agent: sre_analyst_agent
```

#### 用户的纠偏

> **用户**：「好的你的分析给了我很多启发。DSL 或者说 workflow 在这个设计里被作为很重要的一个设计，但是当前阶段 Agentic 时代大家基本不太使用 DSL/workflow 来做硬流程逻辑编码了，都是在 Skill 里写自己的工作流程，然后让 Agent/LLM 读 Skill 然后根据 skill 指导工作。这样回到 DSL 的设计是不是在开时代的倒车？」

#### 第二版（最终）：策略声明

> 「你说得对。Agentic 时代的范式是：**一个强 Agent + 一组自描述的 Skill，LLM 读 Skill 描述自己编排**。Claude Code、Cursor、Manus、Devin 全是这个路子。」
>
> 「我在文档里设计的 Playbook DSL……是**经典 workflow 思维**——把人脑子里的 SOP 硬编码成步骤序列。这确实是开倒车。它的问题：
> - LLM 编排比任何 DSL 都灵活
> - 现实和剧本不符就崩
> - 改流程要改 DSL，维护负担重
> - 最关键：**把 Agent 降级成了步骤执行器**，浪费了 LLM 的动态决策能力」
>
> 「**正确的重构是：Playbook 不是 workflow 脚本，是"策略 + Skill 包 + 不变量"的声明**。Agent 在约束内自由编排。」

第二版 DSL 示例：

```yaml
# Playbook = 策略声明，不是步骤脚本
scenario: sre_capacity_routine
trigger: timer(0 2 * * *)
skills: [db_query, baseline_compare, anomaly_detect, report]  # 可用 Skill 包
assets_required: [catalog_prod_db, metric_p99, latest_capacity_report]

# 不变量——硬约束，LLM 不能自作主张
gates:
  - after: anomaly_detection
    if: anomalies_found
    intervention: review           # 必须人 Review 才能继续
    blocks: delivery

deliverables:
  - type: report
    delivery: [email:sre-team, asset_library]

distill:
  forced: true
  produce: [historical_artifact]
```

**Playbook 只声明四件事**：
1. 这个场景能用哪些 Skill
2. 必须加载哪些 Asset
3. 哪些关卡必须人介入（不变量）
4. 必须产出什么、沉淀什么

> 「**这是从"剧本编排"到"剧本约束"的范式转变**。Skill 承载工作流知识，Playbook 承载策略边界。这和 Agentic 时代的方向是一致的，不是倒车。」

### 4.4 Artifact（产出物）

Artifact 是 Task 的产出物，独立持久化、可版本化、可分享。

**Artifact 类型随场景扩展**：
- 初始：report / analysis / dataset
- SRE 场景加入：runbook / case / operation_plan / operation_result / code_project
- Host 类加入：deliverable_app / notebook / dashboard

**Artifact 是"被产出了什么"，Delivery 是"它去了哪"**——这个区分是数据运营场景逼出来的。

### 4.5 Asset（资产）—— 空间进化的燃料

**Asset 的分类随场景压测而扩展**：

| 大类 | 子类 | 主用场景 |
|---|---|---|
| Process Asset | Runbook / Case | SRE |
| Semantic Asset | Metric / Dimension / Catalog / Lineage | 数据运营 |
| Template Asset | Report Template / SQL Template | 通用 |
| Output Asset | 历史 Artifact 归档 | 通用 |

**Asset 沉淀是 Task close 的硬约束**——这是整个设计最核心的差异化点。

### 4.6 Delivery（交付）—— 从 1 类到 4 类的演进

Delivery 类别在整个讨论中扩展了三次：

**v1**：只有"产出 Artifact"
**v2**（数据运营场景逼出）：分为 Generate（产出）→ Deliver（分发）→ Distill（沉淀）三段
**v3**（用户提出操作型交付）：扩展为 Notify / Publish / Execute 三类
**v4**（用户提出 Host 类）：扩展为 Notify / Publish / Execute / Host 四类

#### 用户对操作型交付的提出

> **用户**：「理论上 场景空间也要做资产管理维护吧。比如运营要管理来源数据库，数仓；运维要管线上环境？这些是否也会作为场景空间资源？然后关于交付。我理解交付的除了报告、文件外也可能是一次操作吧。比如重启服务，部署代码等。也可能是一次邮件发送？也可能是交付一个代码项目？」

#### 用户对 Host 类交付的提出

> **用户**：「先完成之前任务，然后看下还有这里对交付的思考也是，一个空间理论上交付的内容应该很丰富，和所属的业务场景相关，比如 SRE 交付的是变更、运维操作、文档。运营交付的是数据、分析报告、邮件等等。市场售前可能要交付调研 web 程序等等。这里要面向最终交付构建空间，在这个空间里能托管、展示、部署运行各种交付结果。」

#### 助手对 Host 类交付的提炼

> 「你提的是**"留下来"**的视角：SRE 的变更记录/运维操作历史要在空间里可查；运营的数据集/报告要在空间里可浏览；市场售前的调研 web 程序要在空间里能跑。交付物不只是"发出去就完了"，**很多交付物本身就是空间要长期托管、展示、甚至部署运行的产出**。」
>
> 「交付物在空间里有三种命运：
> - **发出去**（Notify/Publish/Execute 到外部）——之前已设计
> - **托管在空间**（作为可浏览/可检索的产出物库）——之前 Artifact 表有，但没强调"展示"
> - **部署运行在空间**（web 程序、dashboard、定时任务）——**这是全新维度，之前完全没有**」

#### 四类交付最终定义

| 类别 | 本质 | 例子 |
|---|---|---|
| **Notify** | 信息流动 | 邮件 / 飞书 / 钉钉 |
| **Publish** | 资产发布 | BI 看板 / 数仓表 / git 仓库 / 对象存储 |
| **Execute** | 改变世界 | 重启 / 部署 / 回滚 / 改配置 / 执行 SQL |
| **Host** | 托管运行 | web_runtime / dashboard_viewer / data_explorer / doc_site / notebook_runtime |

#### Execute 类的四重保护

> 「操作型交付（Execute）是普通 Agent 平台不敢碰的——它涉及"改变世界"，必须强制 Approve、强制回滚计划、不自动重试。但恰恰是这一类让场景空间真正能完成 SRE 和数据运营的核心工作（重启服务、部署代码、回填数据），而不是只产出报告。这是 OpenDerisk 区别于"又一个 chatbot 套壳"的关键。」

四重保护：强制 Approve / Dry-run 预览 / 回滚计划强制 / 执行结果沉淀 / 失败升级。

### 4.7 Intervention（人的介入）

**初始 4 种**（SRE 场景）：Approve / Coach / Escalate / Review
**数据运营加入 2 种**：Reconcile / Attest
**MVP 简化为 1 种**：Review

详见 §5.3 的"砍掉项"分析。

### 4.8 Trigger（触发源）

**4 种触发模式**：timer / webhook / alert / manual

**关键设计**：触发源是 Task 的属性，不是 Task 的类型。同一个线上问题可能从告警进来，也可能从用户主动定位进来，也可能从例行巡检升级而来——必须用同一个 Task 模型才能做关联和升级。

### 4.9 WorkspaceResource（空间资源）

**三类划分**：

| 类别 | 例子 | 处理方式 |
|---|---|---|
| 通用可复用 | Agent / Skill / MCP / Model | 全局物理，空间订阅 |
| 场景绑定物理 | DataSource / Environment / CodeRepo / API | 全局有物理注册，空间加视图与配置 overlay |
| 场景专属逻辑 | SLO / OnCall / Pipeline / Dashboard / runbook_target | 纯空间内自建 |

**关键立场**：物理资源层（`connect_config` 等）不动，空间只做"引用 + 视图 + overlay"，不重造。

> 「一个物理数据源在 SRE 空间叫"prod_core_db"、在数据运营空间叫"生产核心库"——互不影响。」

---

## 5. 被考虑又被否决的选项（以及为什么）

这是整个讨论中最有价值的部分——记录了哪些设计选项被认真考虑过，又被否决了，以及否决的理由。

### 5.1 SkillBundle（在 MVP 阶段被砍掉）

**最初设计**：因为 Agentic 时代是"一个 Agent + 多 Skill 适配多场景"，所以引入 SkillBundle 作为"挂载到空间的核心资源"——一个空间挂一组 Skill 包，对应一个场景。

**MVP 阶段的决定**：砍掉 SkillBundle 抽象，直接引用现有 Skill。

> 「**SkillBundle 概念砍掉**——直接引用现有 Skill，MVP 不需要 Bundle 抽象。」

**理由**：MVP 阶段单场景只需要少量 Skill，Bundle 抽象是过度设计。

### 5.2 多 Agent 协作（在 MVP 阶段被砍掉）

**讨论过程**：早期设计里有"SRE-Agent + Code-Agent + Report-Agent 的协作模板"这种多 Agent 团队概念。

**用户的关键纠偏**：

> **用户**：「当前时代的 Agent 架构大家都是在一个 Agent 架构下用不同的 skill 指导不同场景工作，反而不会创建那么多 Agent 实例了，所以不需要复杂的设计一个 marketplace。」

**最终立场**：

> 「**一个强 Agent + SkillBundle 适配所有场景**——这个假设依赖 LLM 自主编排能力。」
>
> 「**AgentSubscription 概念过度设计**——一个空间不需要"订阅多个 Agent"，它只需要一个 Agent + 一组 Skill。」

**MVP 阶段**：一个通用 Agent + Skill 直接引用。

### 5.3 六种介入模式（在 MVP 阶段砍到 1 种）

**最初 6 种**：Approve / Coach / Escalate / Review / Reconcile / Attest

**助手的自我批评**：

> 「**六大介入模式**——分类清晰，但模式之间边界模糊（Coach vs Escalate、Review vs Reconcile 实操会混）。可以先做 3 种（Approve / Review / Coach）验证。」
>
> 「**六种人介入模式**——前四种通用，后两种（Reconcile/Attest）明显是为数据运营场景硬塞的。可能放到"场景插件"里更合适，而不是核心介入模式。」

**MVP 阶段**：只保留 Review 一种（异常时人看一眼再 close）。

### 5.4 Asset 语义子类型（在 MVP 阶段被砍掉）

**最初设计**：Asset 分 4 大类 9 子类——Process（Runbook/Case）/ Semantic（Metric/Dimension/Catalog/Lineage）/ Template / Output。

**助手的批评**：

> 「**Asset 的九种子类型**——这是用 SRE + 数据运营两个场景压测出来的，但**没经过第三个场景验证**。很可能第三个场景（如合规审计、客户成功）会暴露"子类型设计不够通用"或"子类型太多用户分不清"。建议先实现到 4 大类，子类型按需扩展。」

**MVP 阶段**：只做 `historical_artifact`（必做，基线对比用）和 `case`（可选，异常案例）。

### 5.5 跨工作空间 Asset 共享 / 提升机制

**讨论过程**：数据运营场景暴露了"活跃用户"这种指标定义可能跨空间复用——数据运营空间用，增长团队空间也用，老板看板空间也用。

**决定**：推迟到很后期。

> 「**Asset 不能完全属于单个空间**。需要一个"组织级 Asset 库"，空间内的 Asset 可以选择"提升为组织级"，其他空间订阅引用。这是从"单空间"扩展到"多空间协作"时绕不过去的——OpenDerisk 当前是单空间产品，但演进到多空间时这一层必须有。」
>
> 「**但这是现在要做的事吗？不是。先把单空间内的 Asset 模型设计对，提升到组织级是后面的事**。提前设计会过度抽象。」

**MVP 阶段**：单空间内 Asset 即可，不做跨空间共享。

### 5.6 Personal Sandbox / Builder Console（在 MVP 阶段被砍掉）

**讨论过程**：第一轮提出的 Builder/Consumer 双视角，包括"Builder 在场景空间外有一个 personal sandbox 去 prototype Agent"。

**决定**：MVP 不做。

> 「**Personal Sandbox / Builder Console**——SME 不需要。」

**理由**：中小企业没有专职 Builder 角色，不需要单独的 sandbox。

### 5.7 Execute 类交付（在 MVP 阶段被砍掉）

**这是反直觉的决定**——Execute 类是设计中最有差异化的部分之一，但 MVP 不做。

> 「中小企业 SRE/运维的真相是：线上就几台机器、一个云账号、几个核心服务。重启服务/部署代码这类操作：
> 1. 风险承受力低，老板不会让 AI 操作线上
> 2. 团队小，操作频次低，手动重启 5 分钟的事不值得做系统
> 3. 合规与责任边界不清——出了事谁背
>
> Execute 是大企业才用得起、必须用的能力。中小企业做了没人用。**放在 MVP 之后，等真有 design partner 提需求再做**。」

### 5.8 Host 类交付的 5 种运行时（在 MVP 阶段被砍掉）

**讨论过程**：用户提出"面向最终交付构建空间"，助手设计了 5 种 Host 运行时（web_runtime / dashboard_viewer / data_explorer / doc_site / notebook_runtime）。

**助手的自我批评**：

> 「**Host 类交付**——"面向最终交付构建空间"的洞察是真的，但落到 P8 五种托管运行时（web_runtime / dashboard_viewer / data_explorer / doc_site / notebook_runtime），光一个 notebook_runtime 就是独立产品级别。5-7 周做不完。」

**MVP 阶段**：完全砍掉 Host 类。

> 「**Host delivery（5 种运行时）—— 极高成本，SME 有外部 BI**。中小企业有现成的 BI（Metabase / Superset / 飞书多维表格）和报表分发渠道（飞书/邮件/PDF），不需要在 OpenDerisk 里再做一遍。」
>
> 「**真做也只做一种——dashboard_viewer，且放在 MVP 之后**。」

### 5.9 Playbook 自演化（在 MVP 阶段被砍掉）

**讨论过程**：Playbook 演化被设计为"每次 Task 跑完后，对比剧本预设的步骤和实际执行的步骤，识别偏差。多次同类偏差后，空间提议修改 Playbook（必须人审批）"。

**助手的批评**：

> 「**Playbook 自演化**——这是最有差异化的机制，几乎没有产品做到。但文档自己也承认"几乎无产品做到"，但没追问"为什么没有"。原因大概率是：用户不信任 AI 提议、提议质量难保证、即使有提议用户也不会决策。这是个"看起来性感但 ROI 存疑"的特性。」
>
> 「**Playbook 自演化——低价值（SME 不会审批提议）、高成本**。中小企业 Playbook 总数可能就 5-10 个。系统花精力做"提议改 Playbook"，用户根本不会审批——中小企业老板不是 SRE 专家，看到"建议增加 baseline_compare_skill 调用"这种提议会直接关掉。」

**MVP 阶段**：砍掉，放到 P9+。

### 5.10 Agent Marketplace（P8 砍掉）

**讨论过程**：早期设计里有 Builder/Consumer 双向流动 + Marketplace 的概念。

**用户的纠偏**：

> **用户**：「⑦ Builder/Consumer 双向流动（P8）。这是平台化叙事的标配，但 OpenDerisk 当前没有"Agent 数量足够多到需要市场"的规模。提前做 Marketplace 是过度设计——文档把它放到 P8 是对的，但要在 P1-P7 验证出"用户真的需要订阅别人的 Agent"后再投入。」这个我觉得说的很对。当前时代的 Agent 架构大家都是在一个 Agent 架构下用不同的 skill 指导不同场景工作，反而不会创建那么多 Agent 实例了，所以不需要复杂的设计一个 marketplace。」

**最终决定**：Marketplace 砍掉，Builder/Consumer 降级为"造 Skill"（不是造 Agent）。

### 5.11 Playbook 作为 workflow DSL（范式级否决）

详见 §4.3。这是最大的范式转变——从"workflow 编排"到"策略声明"。

### 5.12 个人空间作为主轴（早期否决）

详见 §2。

### 5.13 "P1-P2 验证用户是否直奔聊天"作为成功标准（用户纠偏）

**助手的原话**：

> 「**P1-P2 阶段能否验证用户真的需要"场景空间"叙事——如果用户登录后还是直奔"和 Agent 聊天"，那场景空间就是工程师的想象，要果断调整。**」

**用户的纠偏**：

> **用户**：「这个判断不明白，理论上用户进来可能通过对话开启一个订阅，通过对话看下整体结果进展这些也是会话吧。」

**助手的修正**：

> 「你这个反驳是对的，我之前把"chat 界面"和"无状态 chat"混为一谈了。
>
> **正确的判断标准不是"用户用不用 chat"，而是"chat 是不是 workspace-aware 的"**：
>
> | 现象 | 判断 |
> |---|---|
> | 用户用 chat 发起任务，chat 自动创建 Task、挂到 Workspace | 成功 |
> | 用户用 chat 问"我的任务进展如何"，chat 能回答（基于 Task/AgentRun 数据） | 成功 |
> | 用户用 chat 说"订阅容量巡检 Skill 包"，chat 帮他配置 Trigger | 成功 |
> | 用户用 chat 像用 ChatGPT 一样，每次从零开始，无记忆无任务 | 失败 |
>
> **chat 是 THE interface to workspace，不是和 workspace 并列的另一个 UI**。」
>
> 「所以 P1-P2 的验证标准要改：
> - 错误标准："用户是否使用 workspace UI 而非 chat"
> - 正确标准："用户的 chat 是否 workspace-aware（能创建 Task、查询进展、引用 Asset、触发介入）"」

### 5.14 助手提出的 6-8 周分阶段 MVP（用户隐式否决）

**助手提议**：6-8 周 MVP，分阶段交付，启动前用 1 周做三件事——design partner 范围对齐、Playbook schema 定稿、Agent 复用方式确定。

**用户的回应**：

> **用户**：「好的我明白了，现在按照之前的讨论开始在当前项目上直接进行开发吧。」

这是隐式否决——用户没有否定 6-8 周的范围，但跳过了"启动前 1 周准备"和"design partner 对齐"环节，直接要求开始开发。这表明用户更看重快速进入实施，而不是严格按 6-8 周节奏走。

---

## 6. 浮现出来的关键设计原则

### 6.1 Playbook 是策略声明，不是 workflow DSL

> 「**Playbook 不是 workflow 脚本，是"策略 + Skill 包 + 不变量"的声明**。Agent 在约束内自由编排。」

详见 §4.3。

### 6.2 强制 distill 是 Task close 的硬约束

> 「**强制 distill 作为 Task close 的硬约束**——这是真正区别于"chatbot + 记忆"的设计。市面上绝大多数"AI 团队空间"都停留在"自动总结 chat history 进知识库"，结果就是垃圾堆。强制显式沉淀 + 未完成不放行 close，是把"沉淀"从 nice-to-have 变成 workflow 一等公民。**这是少数真正可能形成差异化的点**。」

### 6.3 一个强 Agent + 多个 Skill（不要 SkillBundle，不要 Agent Marketplace）

> 「**核心单位从"Agent 订阅"变成"Skill 包挂载"**。一个空间挂一组 Skill 包，对应一个场景。」
>
> 「Agentic 时代的范式是：**一个强 Agent + 一组自描述的 Skill，LLM 读 Skill 描述自己编排**。Claude Code、Cursor、Manus、Devin 全是这个路子。」

### 6.4 Agentic 时代 vs workflow 时代

这是整个讨论中最深刻的范式判断。用户的纠偏把整个设计从"workflow 时代"拉回到"Agentic 时代"：

| 维度 | workflow 时代 | Agentic 时代 |
|---|---|---|
| 编排 | 人写 DSL/脚本 | LLM 读 Skill 自己编排 |
| Agent 角色 | 步骤执行器 | 自主决策者 |
| Agent 实例 | 多个专用 Agent | 一个通用 Agent + 多 Skill |
| 流程知识载体 | DSL/脚本 | Skill（YAML frontmatter + markdown） |
| 不变量 | 步骤间的 when/parallel | gates（硬约束，LLM 不能自作主张） |
| 复用单位 | Agent 模板 | Skill 包 |

### 6.5 空间是工作单元不是个人容器

> 「**"空间是工作单元不是个人容器"——这个立场正确，避开了"个人 AI 助手"这个伪命题（本地 Claude Code 类工具对云端个人助手是降维打击）。聚焦组织/场景是对的。**」

### 6.6 Work 层流动，Asset 层沉淀

> 「很多产品把这两层混在一起（聊天记录就是资产），结果既不能复用也检索不动。空间设计必须显式区分"工作流过的水"和"沉淀下来的结晶"。」

### 6.7 物理资源不重造，空间只做引用 + overlay

> 「物理资源全局注册不动，空间只做引用 + 视图 + overlay。一个物理数据源在 SRE 空间叫"prod_core_db"、在数据运营空间叫"生产核心库"——互不影响。」

### 6.8 chat 是 workspace 的主入口，不是退化子页

> 「**chat 是 THE interface to workspace，不是和 workspace 并列的另一个 UI**。这恰恰和 Agentic 时代的方向一致——Agent 是入口，workspace 是 Agent 的上下文和记忆。」
>
> 「Workspace 首页可以就是"workspace-aware 的 chat"+ 旁边的任务/待办侧栏。」

### 6.9 人介入后留下的结构化沉淀比介入动作本身值钱

> 「人介入的"动作"不值钱，人介入后**留下的结构化沉淀**才值钱。如果没有这一步，人在空间里做的所有事都随着离职流失——这恰恰是传统运维体系最大的问题：老 SRE 走了，经验也走了。」

### 6.10 砍掉一半抽象先跑通一个场景，胜过所有抽象都半成品

> 「**砍掉一半抽象先跑通 SRE 一个场景，比把所有抽象都实现但每个都半成品要强得多**。」
>
> 「**这个设计不是 over-engineering，但接近 over-engineering 的边缘**。文档里 18 章、9 个一等实体、6 种介入模式、3 类交付、9 种 Asset 子类——信息密度很高，但落地时每多一个未经验证的抽象，失败概率就累加一分。」

### 6.11 技术特征验证容易过，业务价值验证难作弊

> 「P1-P2 的成功标准是"chat 是否 workspace-aware"。但这是技术特征不是用户价值。真正的验证应该是：
> - SRE 用了之后 MTTR（事故响应时间）是否真的下降？
> - 数据运营用了之后月报周期是否真的缩短？
> - 用户是否愿意把现有工作迁移过来？
>
> 技术特征验证容易过，业务价值验证难作弊。」

---

## 7. 用户的显式反馈与纠偏

整个讨论中，用户在关键节点多次做出显式纠偏。这些纠偏决定了设计的最终形态。

### 7.1 否决"个人空间"作为产品主轴

> **用户**：「不过好像个人空间这个是伪命题吧。如果我都个人了我直接本地直接部署一个个人 Agent 如 Hermes ClaudeCode 就行了，没必要在一个 web 服务上使用。」

**影响**：从"个人 Workspace"转向"Scenario Workspace（场景空间）"。

### 7.2 否决 Playbook 作为 workflow DSL

> **用户**：「DSL 或者说 workflow 在这个设计里被作为很重要的一个设计，但是当前阶段 Agentic 时代大家基本不太使用 DSL/workflow 来做硬流程逻辑编码了，都是在 Skill 里写自己的工作流程，然后让 Agent/LLM 读 Skill 然后根据 skill 指导工作。这样回到 DSL 的设计是不是在开时代的倒车？」

**影响**：Playbook 从"workflow 脚本"重写为"策略声明"——这是整个设计中最大的范式转变。

### 7.3 否决 Agent Marketplace

> **用户**：「当前时代的 Agent 架构大家都是在一个 Agent 架构下用不同的 skill 指导不同场景工作，反而不会创建那么多 Agent 实例了，所以不需要复杂的设计一个 marketplace。」

**影响**：Marketplace 砍掉，Builder/Consumer 降级，AgentSubscription 概念过度设计被识别。

### 7.4 否决"用户是否直奔聊天"作为验证标准

> **用户**：「这个判断不明白，理论上用户进来可能通过对话开启一个订阅，通过对话看下整体结果进展这些也是会话吧。」

**影响**：验证标准从"用 chat vs 用 UI"改为"chat 是否 workspace-aware"；chat 从"退化子页"升为"workspace 主入口"。

### 7.5 提出"操作型交付"

> **用户**：「关于交付。我理解交付的除了报告、文件外也可能是一次操作吧。比如重启服务，部署代码等。也可能是一次邮件发送？也可能是交付一个代码项目？」

**影响**：Delivery 从 1 类扩展到 3 类（Notify / Publish / Execute）。

### 7.6 提出"Host 类交付"

> **用户**：「一个空间理论上交付的内容应该很丰富，和所属的业务场景相关……这里要面向最终交付构建空间，在这个空间里能托管、展示、部署运行各种交付结果。」

**影响**：Delivery 从 3 类扩展到 4 类（Notify / Publish / Execute / Host）。

### 7.7 提出"资源管理"

> **用户**：「理论上 场景空间也要做资产管理维护吧。比如运营要管理来源数据库，数仓；运维要管线上环境？这些是否也会作为场景空间资源？」

**影响**：WorkspaceResource 成为第 9 个一等实体，分三类。

### 7.8 提出"协作/进化/交付作为重点设计"

> **用户**：「这里的场景空间核心是要在领域那有协作，进化，交付机制。这个也要作为重点设计体现在文档里。」

**影响**：文档新增独立章节"三大核心机制：协作 / 进化 / 交付"。

### 7.9 要求并存而非替代

> **用户**：「我希望是并存，因为现有模块很多都是新的这个场景空间的基础原子能力。」

**影响**：MVP 架构决定为"新模块叠加在现有原子能力之上，不动现有用户"。

### 7.10 隐式否决"启动前 1 周准备"

> **用户**：「好的我明白了，现在按照之前的讨论开始在当前项目上直接进行开发吧。」

**影响**：跳过 design partner 对齐 / Playbook schema 定稿 / Agent 复用方式确定这"启动前 1 周准备"环节，直接进入开发。

---

## 8. 设计中的关键 ASCII 图与结构示意

### 8.1 整体架构（叠加而非重写）

```
┌─────────────────────────────────────┐
│ 新增: Scenario Workspace 模块        │
│ (workspace/task/playbook/           │
│  artifact/asset/delivery)           │
├─────────────────────────────────────┤
│ 复用（不动）: 现有原子能力           │
│ Agent / Skill / MCP / DataResource  │
│ Scheduler / Channels / RBAC / Hook  │
└─────────────────────────────────────┘
```

### 8.2 SRE 场景空间的完整形态

```
SRE 场景空间
│
├── Trigger 层（任务入口）
│   ├── 定时（容量巡检、健康检查）
│   ├── Webhook（PR 触发部署、变更 webhook）
│   ├── 告警（监控、SLO、人工上报）
│   └── 主动（用户发起定位）
│
├── Task 层（统一任务流）
│   - 所有触发统一进 Task 队列
│   - Task 类型 = Routine / Pipeline / Incident（决定走哪个 Playbook）
│   - Task 之间可关联、升级、派生子任务
│
├── Playbook 层（剧本，空间的核心）
│   - 容量巡检 Playbook
│   - 上线部署 Playbook（含 gate 和回滚）
│   - 应急响应 Playbook（含升级路径）
│   - 线上定位 Playbook
│   每个 Playbook 声明：步骤 / 每步用哪些 Agent+Skill / 介入点 / 产出 Artifact
│
├── Resource 层（被 Playbook 引用，不独立管理）
│   Agent / Skill / MCP / 模型 —— 现有 derisk-serve 设计保留
│
├── Human 层（四种介入模式 + 强制沉淀）
│   Approve / Coach / Escalate / Review
│
└── Asset 层（沉淀，空间进化的燃料）
    ├── 知识：复盘结论、runbook、基线、口径
    ├── 模板：巡检报告模板、应急报告模板、变更方案模板
    └── 案例：历史 Task 的执行轨迹 + 决策 + 产出
```

### 8.3 Asset 层分类（适配 SRE + 数据运营两场景）

```
Asset 层
├── Process Asset 流程资产（SRE 主用）
│   ├── Runbook       事故处理手册
│   └── Case          历史案例
│
├── Semantic Asset 语义资产（数据运营主用）
│   ├── Metric        指标定义
│   ├── Dimension     维度定义
│   ├── Catalog       数据字典
│   └── Lineage       口径变更历史
│
├── Template Asset 模板资产（两边都用）
│   ├── Report Template   报告模板
│   └── SQL Template      SQL 范式
│
└── Output Asset 产出资产（两边都用）
    └── 历史 Artifact 归档（可被未来 Task 检索引用）
```

### 8.4 Playbook 末段的三段（数据运营场景逼出的扩展）

```
Playbook 末段
├── Generate  产出 Artifact
├── Deliver   分发（邮件/消息/BI/下游 Playbook）  ← 数据运营场景逼出
└── Distill   沉淀回 Asset（含强制对账/Review）
```

### 8.5 容量巡检在场景空间里怎么跑（对照"任务+资源+授权"版）

**任务+资源+授权版**：定时器触发 → SRE-Agent 跑一遍取指标 → 输出"正常/异常" → 异常就告警叫人。每次都一样，跑一年空间也没变聪明。

**场景空间版**：
1. 定时触发 → 生成容量巡检 Task（Routine 型）
2. Task 匹配"容量巡检 Playbook"
3. Playbook 步骤：取指标 → **从 Asset 取上次巡检基线** → 对比 → 识别异常 → **检索历史同类异常的处理案例** → 生成报告 Artifact
4. 报告里附"上次同类异常怎么处理的"作为参考
5. 异常升级 → 派生一个 Incident Task → 走应急 Playbook
6. 应急结束 → **强制 Review**：人复盘写根因 → 沉淀进 Asset（更新 runbook、新增案例）
7. **下次巡检自动引用这次沉淀的结论**——这才是成长

> 「差别在哪？第三步"从 Asset 取基线"、第四步"检索历史案例"、第六步"强制 Review 沉淀"、第七步"下次引用"——这四个动作在"任务+资源+授权"模型里都不存在，因为没有 Playbook 和 Asset 这两层。」

### 8.6 4 种触发统一进 Task 队列

```
触发源（定时/webhook/告警/人）
      ↓
   统一进 Task 队列
      ↓
Task 类型决定走哪个 Playbook
      ↓
Playbook 编排 Agent 团队 + 资源 + 介入点
      ↓
产出 Artifact → 部分沉淀回 Asset
```

### 8.7 实体关系图（v1 含 AgentSubscription，后降级）

```
User ──owns──> Workspace ──contains──> Task ──produces──> Artifact
                       │                     │
                       └──subscribes──> Agent <──used by──┘
                                          │
                                          └──runs──> AgentRun (现有 conversation/messages 的投影)
```

后续调整：AgentSubscription 降级（一个空间不需要订阅多个 Agent），改为 `workspace.default_agent_app_code` 绑定现有 Agent 实例。

---

## 9. "Design Partner"框定与 MVP 决策

### 9.1 用户的两个 design partner

在 MVP 决策环节，助手问"有没有真实团队愿意用早期版本验证"，用户回答：

> **用户**：「问题回答，问题1: 数据运营 和 周报 和运维都有真实团队要用。问题2: 我希望是并存，因为现有模块很多都是新的这个场景空间的基础原子能力。」

两个 design partner 是：

| 团队 | 现状痛点 | MVP 验证指标 |
|---|---|---|
| 数据运营 - 周报 | 手动跑数 + 整理 + 发邮件，每月 N 小时 | MVP 上线后月报周期缩短到 X 小时 |
| 运维 - 告警处理 | 告警来了从零开始排查 | MVP 上线后同类告警 MTTR 下降 X% |

> 「**这两个指标比"chat 是否 workspace-aware"硬 10 倍**。MVP 出来后 2-4 周内能拿到真实数据，决定是否继续投入。」

### 9.2 用户的 MVP 决策提问

> **用户**：「如果让你来决策，选择其中价值最高的部分先实现一个最小可用版本，你怎么决策选择？考虑的是中小企业的数据运营，系统运维场景。」

### 9.3 助手的 MVP 决策

**定位**：workspace-aware chat + 定时报表/巡检 + 强制沉淀。让一个中小企业团队装上之后，"每月/每天的固定报表与巡检不用人手动跑了，跑过的事下次能复用"。

**价值密度排序（中小企业视角）**：

| 能力 | 用户感知价值 | 实现成本 | ROI |
|---|---|---|---|
| workspace-aware chat + 数据源绑定 | 极高 | 中 | ★★★★★ |
| 定时 Task + 简单 Playbook | 极高 | 中 | ★★★★★ |
| Artifact 独立 + 强制 distill | 高 | 中 | ★★★★ |
| Notify delivery | 高 | 低 | ★★★★ |
| Asset 库（历史报告 + 案例） | 高 | 中 | ★★★★ |
| 简单介入（Approve/Review） | 中 | 低 | ★★★ |
| **Execute delivery** | **低（SME 不敢让 AI 操作线上）** | **高** | ★ |
| **Host delivery（5 种运行时）** | **中（SME 用外部 BI 即可）** | **极高** | ★ |
| **Playbook 自演化** | **低（SME 不会审批提议）** | **高** | ★ |
| **SkillBundle / 多 Agent / Marketplace** | **低** | **高** | ★ |

### 9.4 MVP 保留范围

```
Workspace ── 成员
   │
   ├── WorkspaceResource（只 3 种 type）
   │     - data_source（复用 connect_config）
   │     - knowledge_space（复用现有）
   │     - environment（仅 metadata，用于运维场景上下文）
   │
   ├── Task（4 种触发：timer/webhook/alert/manual）
   │     - 状态机简化为：draft/running/awaiting_human/closed/archived
   │
   ├── Playbook（策略声明 DSL，但极简）
   │     - 只有 skills / context.resources / deliverables / distill 四块
   │     - 没有 gates（v1 不做介入触发，只做 close 时校验）
   │     - 没有 SkillBundle，直接引用 skill
   │
   ├── Artifact（只 3 种 type）
   │     - report（报表/巡检报告）
   │     - analysis（临时分析）
   │     - dataset（数据集，可选）
   │
   ├── Asset（只 2 种 type）
   │     - historical_artifact（必做，基线对比用）
   │     - case（可选，异常案例）
   │
   ├── Delivery（只 notify 类）
   │     - email / feishu / in_app
   │
   └── 强制 distill（Task close 硬约束）
```

### 9.5 MVP 两个场景的覆盖度

| 场景 | MVP 能做什么 | 不能做什么 |
|---|---|---|
| **数据运营** | 定时月报/周报；临时查询分析；邮件/飞书发报告；下次同类报表自动加载上次作为基线 | 自动 BI 看板托管；自动入数仓；财务 Attest 签字 |
| **系统运维** | 定时巡检报告（CPU/内存/慢查询）；告警来了 Agent 自动诊断出报告；运维案例沉淀下次参考 | 自动重启服务；自动部署；自动扩缩容 |

> 「两个场景共享同一套核心，差别只在 Skill 包和 WorkspaceResource 类型。」

### 9.6 用户对技术选型的提问

> **用户**：「如果不考虑已有的代码，整个功能重新架构技术选型，你更建议 python + TS 还是 纯 TS 的项目？」

### 9.7 助手的技术选型决策：Python + TS

> 「**结论：Python（后端）+ TypeScript（前端），不是纯 TS**。」

**关键判断依据**：

1. **AI 生态是 Python-first，这不是偏好问题，是事实**——LLM SDK 首发、Agent 框架（LangChain/LlamaIndex/AutoGen/CrewAI）、向量库、模型推理、Eval/可观测、学术/算法实现都是 Python 优先。**对 Agentic 架构尤其关键**：Skill 调用、Agent 编排、上下文组装、RAG、Tool 调用——这一层 Python 生态领先 TS 至少 2-3 年。

2. **OpenDerisk 已经在 Python 路径上**——`derisk-core` / `derisk-serve` / `derisk_app` 全是 Python，现有 Agent / Skill / MCP / Scheduler / Knowledge Vault 全是 Python。"不考虑已有代码"是假设性问题，但真实决策不能假设。

3. **数据运营场景特别吃 Python**——查数据库 / 跑 SQL / 生成报表（pandas / sqlalchemy / DuckDB）、数据分析 notebook（Jupyter）、数据探索 / 异常检测、跨数据源 join / 离线计算。用 TS 做这些会非常痛苦。

4. **系统运维场景也偏向 Python**——K8s client、Prometheus client、告警处理 / 自动诊断脚本，运维自动化历史包袱基本是 Python / Shell。

5. **纯 TS 唯一的真实优势**：前后端同语言，类型共享，全栈一个人写。但这个优势在 OpenDerisk 这种已经成熟到有 design partner、要做场景空间平台的项目上，**前后端分离的工程模型更健康**。

**纯 TS 何时更优**（诚实承认）：
- 纯 SaaS 协作工具（Notion / Linear 类）——没有重 AI 编排，没有数据分析
- 纯前端产品 + 轻后端
- 小团队 MVP 验证想法——一两周内跑通 demo
- 团队只有 JS 工程师

**OpenDerisk 都不属于这些**。

**反警告：不要用 Streamlit / Gradio 做"全 Python 全栈"**：

> 「AI 团队喜欢用 Streamlit / Gradio / NiceGUI 做"全 Python 全栈"。**对 OpenDerisk 这类产品坚决不推荐**：复杂交互会卡死、性能瓶颈明显、部署/运维体验差、扩展性差。前端必须用 TS + React 生态。这是不可妥协的。」

**推荐技术栈**：

```
后端 (Python)
├── FastAPI（API 层，OpenDerisk 已在用）
├── Pydantic v2（数据校验/序列化）
├── SQLAlchemy 2.0（ORM）
├── APScheduler（定时触发，已在用）
├── LangGraph 或自研轻量编排（Agent 编排）
├── LiteLLM（多模型适配，避免锁死单一厂商）
├── Pydantic AI 或自研（Agent / Tool 抽象）
├── DuckDB（数据分析/临时查询，数据运营场景刚需）
└── Celery / RQ（异步任务，Task 执行）

前端 (TypeScript)
├── Next.js 14+（App Router，OpenDerisk 已在用）
├── TanStack Query（API 状态）
├── Zustand（客户端状态）
├── shadcn/ui + Tailwind（组件库）
├── Vercel AI SDK（流式 chat 体验，前端侧）
└── Monaco Editor（Playbook YAML 编辑）

共享
├── OpenAPI schema（FastAPI 自动生成）→ 前端类型生成
├── Pydantic 模型 → TypeScript 类型（datamodel-code-generator）
└── WebSocket（Task 进度推送）
```

> 「**前后端类型同步靠 OpenAPI 自动生成，不是手写共享**——这是 Python+TS 的标准做法，比纯 TS 手写类型更安全。」

### 9.8 用户决定开始开发

> **用户**：「好的我明白了，现在按照之前的讨论开始在当前项目上直接进行开发吧。」

讨论阶段结束，进入实施阶段。

---

## 10. 整个讨论的脉络：9 轮反复打磨

把整个设计讨论的演进过程梳理出来，可以看清楚每一轮纠偏如何塑造了最终设计：

| 轮次 | 触发 | 关键变化 |
|---|---|---|
| **Round 1** | 用户开场提出"双视角 + 个人空间" | 助手提出 Builder Shell + Consumer Shell + 个人 Workspace |
| **Round 2** | 用户否决"个人空间" | 转向"Scenario Workspace"——颗粒度贴场景不贴部门 |
| **Round 3** | 用户用 SRE 场景压测 | 逼出"四种触发统一进 Task"、"三类工作流"、"人不是来授权是来教的" |
| **Round 4** | 用户用数据运营场景压测 | 逼出 Delivery 层、Semantic Asset（Metric/Dimension/Catalog/Lineage）、Reconcile/Attest 介入模式 |
| **Round 5** | 用户要求"完整方案文档" | 写出 17 章 SCENARIO_WORKSPACE_DESIGN.md |
| **Round 6** | 用户要求补"用户视角 + 协作/进化/交付" | 新增第 1 章（用户视角）+ 第 10 章（三大核心机制） |
| **Round 7** | 用户提出"资源管理 + 操作型交付" | 新增 WorkspaceResource 第 9 实体 + Delivery 扩展为 Notify/Publish/Execute 三类 |
| **Round 8** | 用户挑战"DSL 开倒车 + Marketplace 过度设计 + 验证标准错了" | Playbook 从 workflow 脚本重写为策略声明；Marketplace 砍掉；chat 升为 workspace 主入口 |
| **Round 9** | 用户提出"Host 类交付" | Delivery 扩展为 4 类（Notify/Publish/Execute/Host） |
| **Round 10** | 用户问"设计有价值吗" | 助手诚实评估：有真东西但被范围拖累，建议砍 P7 + 收敛 P8 |
| **Round 11** | 用户问"MVP 怎么选" | 助手决策：6-8 周 workspace-aware chat + 定时报表/巡检 + 强制沉淀 |
| **Round 12** | 用户回答"两个 design partner + 并存" | MVP 路径明确，验证标准从技术特征升级为业务指标 |
| **Round 13** | 用户问"Python+TS 还是纯 TS" | 决定 Python + TS |
| **Round 14** | 用户说"开始开发吧" | 进入实施阶段 |

---

## 11. 助手在讨论中的诚实反方观点

讨论并非单向颂扬，助手多次提出尖锐的反方观点，这些反方观点对设计的成熟至关重要。

### 11.1 "这个设计接近 over-engineering 的边缘"

> 「**这个设计不是 over-engineering，但接近 over-engineering 的边缘**。文档里 18 章、9 个一等实体、6 种介入模式、3 类交付、9 种 Asset 子类——信息密度很高，但落地时每多一个未经验证的抽象，失败概率就累加一分。**砍掉一半抽象先跑通 SRE 一个场景，比把所有抽象都实现但每个都半成品要强得多**。」

### 11.2 "范围严重超载"

> 「P1–P8 合计 30+ 周，几乎是 6-9 个月的工程量。文档没有讨论团队规模、是否有商业化压力、与现有 OpenDerisk 用户的迁移成本。**这个量级的设计要么是大团队 + 有明确融资/商业化支撑，要么是分阶段小步验证——文档目前是后者包装前者的体量**。」

### 11.3 "关键假设的赌注"

> 「整个方案的核心赌注是 **"一个强 Agent + SkillBundle 适配所有场景"**。这个假设依赖 LLM 自主编排能力。如果实际能力达不到，Playbook 策略声明范式就需要回退到更结构化的工作流——这个回退不是局部修改，是范式级别的回退。文档没有讨论 Plan B。」

### 11.4 "商业化路径缺失"

> 「OpenDerisk 是开源项目还是商业产品？目标客户是中型企业？大企业？自部署？这影响多租户、计费、SLA、合规等大量设计，但文档完全没提。30 周工程量没有回报模型是危险的。」

### 11.5 "竞品分析缺位"

> 「市场已经非常拥挤：
> - Agent 平台：Coze / Dify / FastGPT / n8n / LangFlow
> - SRE AIOps：PagerDuty / Incident.io / Datadog
> - 数据运营：dbt / Monte Carlo
> - AI Workspace：Slack AI / Notion AI / Linear AI
>
> 文档没有正面回答"OpenDerisk 相对这些产品的差异化在哪"。"协作/进化/交付"是机制叙事不是用户能感知的差异化。」

### 11.6 "Playbook 自演化的 ROI 存疑"

> 「**Playbook 自演化**——叙事漂亮，但拆开看每个单点都有成熟竞品。组合起来是否有壁垒，要看执行，不能在文档里预设。"Playbook 自演化"尤其需要警惕——文档自己也承认"几乎无产品做到"，但没追问"为什么没有"。原因大概率是：用户不信任 AI 提议、提议质量难保证、即使有提议用户也不会决策。这是个"看起来性感但 ROI 存疑"的特性。」

### 11.7 "强制 distill 用户接受度的风险"

> 「**强制 distill 用户接受度**（企业知识管理系统的老大难，体验做不好要么空库要么垃圾库）」

### 11.8 "看漏的"

> 「- 多模态交互（语音/屏幕共享/共同浏览）在场景空间的角色
> - 跨组织协作（供应商/客户进入空间）的场景
> - 模型成本与速度的快速变化对编排范式的影响」

### 11.9 一句话结论

> 「**这个设计有真东西，但被自己的范围拖累了。** 砍掉 P7 + 收敛 P8 + 聚焦一个场景验证业务指标后，是一个值得推进的方案；按当前全量范围推进，6 个月内做不完，做完也很难证明价值。」

---

## 12. 必须保住的三件事（设计的"灵魂"）

整个讨论收敛到最后，助手明确指出哪些是不能砍的"灵魂"：

> 「**如果你只能保住一件事，保住 Playbook + 强制沉淀 + Execute 类交付 这三件——其他都可以砍。这三件是这套设计的灵魂，其他是支撑。**」

后来 Execute 类交付在 MVP 阶段被砍（因为 SME 不敢用），所以最终 MVP 的灵魂收敛为：

> **Playbook（策略声明版）+ 强制沉淀 + workspace-aware chat**

这三件保住，MVP 在中小企业就有真实价值；这三件保不住，再多 P7 P8 也救不回来。

---

## 附录 A：讨论中浮现的关键中文术语对照

| 中文 | 英文 | 含义 |
|---|---|---|
| 场景空间 | Scenario Workspace | 按场景/任务域划分的组织单元，不是个人空间也不是部门空间 |
| 剧本 | Playbook | 场景的策略声明（不是 workflow 脚本） |
| 任务 | Task | 一次需要被完成的工作，4 种触发统一进 Task 队列 |
| 产出物 | Artifact | Task 的产出，可版本化、可分享 |
| 资产 | Asset | 沉淀下来可复用的产出，空间进化的燃料 |
| 交付 | Delivery | Artifact 去哪、以什么形式、给谁——4 类：Notify/Publish/Execute/Host |
| 沉淀 | Distill | 把工作流的产出结晶为可复用 Asset 的动作 |
| 介入 | Intervention | 人在空间里的参与——4-6 种模式 |
| 触发源 | Trigger | Task 的入口——timer/webhook/alert/manual |
| 空间资源 | WorkspaceResource | 空间引用的物理/逻辑资源，分 3 类 |
| 强制沉淀 | Forced Distill | Task close 的硬约束——不放行 close 直到完成沉淀 |
| workspace-aware chat | — | chat 是 workspace 的主入口，能创建 Task、查询进展、引用 Asset |
| 设计合作伙伴 | Design Partner | 愿意用早期版本验证的真实团队 |

## 附录 B：被考虑过又被否决的完整清单

| 选项 | 否决理由 | MVP 是否做 |
|---|---|---|
| 个人空间作为主轴 | 本地工具降维打击 | 不做 |
| Playbook 作为 workflow DSL | Agentic 时代开倒车 | 改为策略声明 |
| Agent Marketplace (P8) | 当前规模不需要，过度设计 | 不做 |
| AgentSubscription | 一个 Agent + Skill 即可 | 降级为 default_agent_app_code |
| SkillBundle 抽象 | MVP 不需要 Bundle 抽象 | 直接引用 Skill |
| 多 Agent 协作 | 一个通用 Agent + Skill 足够 | 不做 |
| 6 种介入模式 | 边界模糊，前 4 种通用后 2 种硬塞 | 只做 Review |
| Asset 9 子类 | 未经过第三个场景验证 | 只做 historical_artifact + case |
| 跨空间 Asset 共享 | 提前设计会过度抽象 | 不做 |
| Personal Sandbox / Builder Console | SME 不需要 | 不做 |
| Execute delivery | SME 不敢用、用不起 | 不做（等 design partner 提需求） |
| Host delivery 5 种运行时 | 每种是独立产品级 | 不做（真做也只做 dashboard_viewer） |
| Playbook 自演化 | SME 不会审批提议，ROI 存疑 | 砍到 P9+ |
| 启动前 1 周 design partner 对齐 | 用户隐式跳过 | 直接进入开发 |

---

**文档定位**：本文档是 Scenario Workspace 设计讨论的原始记录，捕获了"为什么是这样设计"的思考过程。最终的设计文档是 `docs/SCENARIO_WORKSPACE_DESIGN.md`，MVP 实施计划是 `docs/SCENARIO_WORKSPACE_MVP.md`。本文档是这两个文档的"前传"。
