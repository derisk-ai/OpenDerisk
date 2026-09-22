---
name: memory-case-agent
description: >-
  指导 Agent 何时、如何调用内置「案例记忆」(memory_case) 工具：先检索历史案例再深入排查，
  收尾沉淀 RCA；正确使用 scope、query、diagnosis 自由叙述与 feedback 闭环。适用于故障诊断、
  SRE 复盘、AIOps 根因分析等已接入 tool(memory_case) 或 MCP「案例记忆」的场景。
type: workflow
author: derisk
version: "2.0"
category: sre
tags:
  - memory-case
  - case-memory
  - mcp
  - rca
  - sre
  - aiops
---

# 案例记忆 Agent 使用技能

## 何时加载本技能

当对话或应用已暴露 **`memory_case_search` / `memory_case_upsert` / `memory_case_feedback` / `memory_case_render`**（内置 MCP「案例记忆」或资源 **`tool(memory_case)`**），且任务涉及 **故障排查、根因分析、线上应急处置、复盘沉淀** 时，按本技能约束调用工具。

## 核心原则（必读）

1. **先搜后钻**：在 **`read` / `bash` 读本地 skill 包、`pilot/data/skill` 或展开长推理之前**，必须先 **`memory_case_search`** 一次。用短自然语言描述「场景 + 现象 + 服务/产品」（例：`华为云 节前巡检 管控`），看是否有可复用案例。
2. **两步交互**：`memory_case_search` 返回的是**轻量摘要**（~500 字符/条，含 symptom / diagnosis 前 300 字 / root_cause / resolution）。确定哪条相关后，用 `memory_case_render` 按需加载完整 Markdown。**不要直接把 search 结果当完整案例注入上下文**。
3. **收尾必写**：任务得到结论或明确阶段性结果后，评估是否 **`memory_case_upsert`** 写入案例库（先 `search` 近重复再决定 merge）。
4. **反馈闭环**：若检索结果确实帮助缩小范围或验证假设，调用 **`memory_case_feedback`**（`helpful=true/false`）。系统自动累计跨会话反馈，单次 `helpful` 不会立刻让案例从 DRAFT 变为 ACCEPTED——需要多次独立验证。
5. **不把案例当剧本**：`diagnosis` 是 **自由叙述的排查过程**（假设、动作、死胡同、推理链），**不是**要求后续 Agent 逐步照抄的 SOP。目的是启发思路，不是照搬步骤。

## 工具一览与调用节奏

| 工具 | 典型时机 | 要点 |
|------|----------|------|
| `memory_case_search` | 会话早期、开始深诊断前 | STEP 1/2；短查询；返回摘要（symptom + diagnosis preview 300 字 + root_cause + resolution + confidence + feedback 统计） |
| `memory_case_render` | search 之后需要深入阅读某条案例时 | STEP 2/2；传 `case_ids` 加载完整 Markdown；不要把 search 摘要当完整案例 |
| `memory_case_upsert` | 任务收尾、RCA/处置 playbook 可复用时 | 填 `symptom_summary` / `diagnosis` / `resolution` / `root_cause` / `confidence`；`fingerprint` 可省略（服务端派生） |
| `memory_case_feedback` | 使用过某条检索案例之后 | `case_id` + `helpful`；可选 `signal`（如 stale / success / rollback）；单次 helpful 不改 lifecycle |

推荐节奏：**search → render（按需深入）→ 正常排查 → upsert →（若用过案例）feedback**。

## `memory_case_search`

**STEP 1/2** — 返回轻量摘要，不是完整案例。

- **query**：一两句中文/英文即可，包含 **关键症状 + 服务或产品名**（例：`POD OOM Java 堆内存`）。避免超长粘贴。
- **top_k**：默认 5；可 1–20。结果弱时 **收窄 query 再搜**，而不是一次塞满关键词。
- **scope**：通常由系统从 Agent 上下文注入（`app_code` / `environment`），与案例 `case_context` 对齐；**仅在需要覆盖默认作用域时再传**。
- 返回摘要包含：`case_id`、`symptom_summary`、`diagnosis_preview`（前 300 字）、`diagnosis_len`、`root_cause`、`resolution`、`confidence`、`lifecycle`、`similar_count`、`feedback_h`/`feedback_u`/`feedback_cv_count`。
- 返回里可能有 **`degraded: true`**：表示语义向量不可用，仅 DB/词法检索；仍应阅读 `cases`。
- 选中某条后调用 `memory_case_render` 获取完整 Markdown（含完整 `diagnosis` 和 `similar_cases`）。

## `memory_case_render`

**STEP 2/2** — 按需加载完整案例 Markdown。

- 传 `case_ids`（字符串数组）或 `cases`（search 返回的 JSON 对象数组）。
- 返回完整 Markdown：case_context + symptom + 完整 diagnosis + root_cause + resolution + metadata。
- 自动附带 `similar_cases` 关联案例（带有 `relation` 类型和 `struct_match` 标志）。
- 单次最多渲染 5 条。

## `memory_case_upsert`

`case` 对象建议包含：

- **`symptom_summary`**：一两句话描述现象（如 "order-svc Pod OOMKilled，JVM 堆内存溢出"）。
- **`diagnosis`（自由 Markdown）**：用自然语言叙述排查过程——怀疑了什么、试了什么、哪些方向走不通、最终如何定位根因。不要写成结构化 checklist，写的是**推理链**。
- **`resolution`**：最终解决方案一句话。
- **`root_cause`**：已确认的话写一句根因；未确认可留空。
- **`confidence`（0–1）**：对案例质量的自我评估。
- **`metadata.case_context`**：路由和跨案例匹配关键字段——
  - `app_code` / `environment`（系统自动注入，无需手动填）
  - `application_name` / `region` / `tags` / `data_sources`（描述用途）
  - **CRITICAL for cross-case matching**：`failure_layer`（jvm/k8s/network/db/application）、`runtime`（java/go/python/nodejs）、`related_services`（受影响的服务列表）、`middleware`（dubbo/spring-boot/gin 等）。这些字段帮助系统自动区分「文本相似但排查路径不同」的案例。
- **`case_id`**：更新已有案例时传入；新建可省略（服务端生成 `case-{uuid}`）。
- **`fingerprint`**：可省略，由服务端根据 scope + summary 派生。

写入前 **先 `memory_case_search`** 看是否已有近似案例，避免重复造轮子；有则合并更新同一 `case_id`。**系统自动丢弃 LLM 传入的 `fb` 和 `similar_cases`**（由服务端唯一入口管控），无需手动管理。

## `memory_case_feedback`

- 必传 **`case_id`**（来自 search 或 upsert 返回）。
- **`helpful: true/false`**：是否对本次排查有帮助。
- **`signal`**：可选——`stale`（标记过时）、`success`（验证有效）、`rollback`（回滚建议）。
- DRAFT 案例需**跨会话**积累 2 次以上 `helpful=true` + confidence >= 0.8 才会自动升级为 ACCEPTED，单次 feedback 不改 lifecycle。
- 同会话反馈（`conv_id == source_conv_id`）只调 confidence，不累计跨会话计数。

## 反模式（不要做）

- 用 **整页日志、完整配置、超长 prompt** 当 `query` 做 search。
- **跳过 search** 直接长篇分析（除非用户明确禁止访问案例库）。
- 把 **search 返回的摘要当完整案例**，跳过 `memory_case_render` 直接用摘要做决策。
- 把 **`diagnosis` 写成必须逐步执行的 checklist** 并暗示后续 Agent「逐步执行」。
- 在 **未读返回 `cases`** 的情况下声称「库中没有类似案例」。
- 把 **不同 `case_context`（含 app_code / environment）** 的案例混谈为同一上下文（scope 隔离是设计行为）。
- 尝试在 `metadata` 中写入 `fb` 或 `similar_cases` 字段（系统自动丢弃，唯一入口是 `_feedback` 和 `_find_similar_cases`）。

## 与用户协作时的说明话术（可选）

若用户问「案例记忆怎么用」：简要说明 **先搜后钻、两步交互（search→render）、短 query、收尾 upsert、用过就 feedback**，并强调 **案例是参考不是标准作业程序，feedback 积累后案例可靠性会自然提升**。

---

**维护**：与 `MemoryCasePluginService` 工具列表及 `docs/MEMORY_CASE_MCP_PLUGIN.md` 保持一致；工具名或字段变更时请同步更新本文件。
