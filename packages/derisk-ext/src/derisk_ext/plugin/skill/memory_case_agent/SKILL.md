---
name: memory-case-agent
description: >-
  指导 Agent 何时、如何调用内置「案例记忆」(memory_case) 工具：先检索历史案例再深入排查，
  收尾沉淀 RCA；正确使用 scope、query、handling_path 自由叙述与 feedback 闭环。适用于故障诊断、
  SRE 复盘、AIOps 根因分析等已接入 tool(memory_case) 或 MCP「案例记忆」的场景。
type: workflow
author: derisk
version: "1.0"
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

1. **先搜后钻**：在 **`read` / `bash` 读本地 skill 包、`pilot/data/skill` 或展开长推理之前**，必须先 **`memory_case_search`** 一次（用户说「经验丰富」「结合过往」也指本库，不是只读磁盘上的 Markdown）。用短自然语言描述「场景 + 现象 + 服务/产品」（例：`华为云 节前巡检 管控`），看是否有可复用案例。
2. **收尾必写**：任务得到结论或明确阶段性结果后，评估是否 **`memory_case_upsert`** 写入案例库（先 `search` 近重复再决定 merge）。
3. **反馈闭环**：若检索结果确实帮助缩小范围或验证假设，调用 **`memory_case_feedback`**；若案例过时或误导，用合适 `signal` 标记。
4. **不把案例当剧本**：`handling_path` 是 **自由叙述的参考过程**（分支、尝试、弯路），**不是**要求后续 Agent 逐步照抄的 SOP。

## 工具一览与调用节奏

| 工具 | 典型时机 | 要点 |
|------|----------|------|
| `memory_case_search` | 会话早期、开始深诊断前 | 短查询；勿粘贴整段日志或 system prompt |
| `memory_case_upsert` | 任务收尾、RCA/处置 playbook 可复用时 | 填 `symptom_summary` / `hypotheses` / `actions` / `resolution` / `confidence`；`handling_path` 用自然语言概括过程；`fingerprint` 可省略（服务端会派生） |
| `memory_case_feedback` | 使用过某条检索案例之后 | `case_id` + `helpful`；可选 `signal`（如 stale / success / rollback） |
| `memory_case_render` | 需要把多条案例整理成 Markdown 展示时 | 传 `cases` 或 `case_ids` |

推荐节奏：**search →（阅读 cases）→ 正常排查 → upsert →（若用过案例）feedback**。

## `memory_case_search`

- **query**：一两句中文/英文即可，包含 **关键症状 + 服务或产品名**（例：`POD OOM maestro Dubbo 线程 WAITING`）。避免超长粘贴。
- **top_k**：默认 5；可 1–20。结果弱时 **收窄 query 再搜**，而不是一次塞满关键词。
- **scope**：通常由系统从 Agent 上下文注入（`app_code` / `environment` 等），并与持久化里的 **`metadata.case_context`** 对齐；**仅在需要覆盖默认作用域时再传**。
- 返回里可能有 **`degraded: true`**：表示语义向量不可用，仅 DB/词法检索；仍应阅读 `cases`，不要因无向量就跳过检索。

## `memory_case_upsert`

`case` 对象建议包含：

- **叙事与结构**：`symptom_summary`、`hypotheses`（假设列表）、`actions`（已做动作）、`resolution`、`confidence`（0–1）。
- **`handling_path`（字符串）**：用 **段落或列表式自然语言** 写「当时怎么想的、试过哪些方向、哪些排除了、哪些待验证」——**多种可能路径可以都写进去**；目的是给后人 **启发与参考**，不是固定步骤清单。
- **`root_cause`**：若已确认，写一句话根因；未确认可留空或写「待确认」。
- **`incident_title`**：可选，短标题便于列表展示。
- **`case_id`**：更新已有案例时传入；新建可省略（服务端生成）。
- **`fingerprint`**：可省略，由服务端根据 scope + 摘要等派生。

写入前 **先 `memory_case_search`** 看是否已有近似案例，避免重复造轮子；有则合并更新同一 `case_id`。

## `memory_case_feedback`

- 必传 **`case_id`**（来自 search 或 upsert 返回）。
- **`helpful: true/false`**：是否对本次排查有帮助。
- **`signal`**：可选，用于生命周期/置信调整（如 `stale`、`success`、`rollback` 等，以产品说明为准）。

## `memory_case_render`

将检索到的 `cases` JSON 或 `case_ids` 转成可读 Markdown，适合汇报或会话内展示；**不替代**你自己对上下文的推理。

## 反模式（不要做）

- 用 **整页日志、完整配置、超长 prompt** 当 `query` 做 search。
- **跳过 search** 直接长篇分析（除非用户明确禁止访问案例库）。
- 把 **`handling_path` 写成必须逐步执行的 checklist** 并暗示后续 Agent「逐步执行」。
- 在 **未读返回 `cases`** 的情况下声称「库中没有类似案例」。
- 把 **不同 `case_context`（含 app_code / environment）** 的案例混谈为同一上下文（scope 隔离是设计行为）。

## 与用户协作时的说明话术（可选）

若用户问「案例记忆怎么用」：简要说明 **先搜后写、短 query、收尾 upsert、用过就 feedback**，并强调 **案例是参考不是标准作业程序**。

---

**维护**：与 `MemoryCasePluginService` 工具列表及 `docs/MEMORY_CASE_MCP_PLUGIN.md` 保持一致；工具名或字段变更时请同步更新本文件。
