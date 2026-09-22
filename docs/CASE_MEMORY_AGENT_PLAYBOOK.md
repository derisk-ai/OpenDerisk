# 案例记忆 Agent 使用手册（MemPalace 式节奏）

本文说明如何让 Agent **稳定地**使用内置 **`memory_case_*`** 工具，节奏参考 [MemPalace OpenClaw SKILL](https://github.com/MemPalace/mempalace/blob/develop/integrations/openclaw/SKILL.md) 的「先查证、再叙述、后归档」协议，**不引入** MemPalace MCP。

---

## 为什么模型会「不搜库只读文件」

若应用里同时挂了 **资料类 skill**（`pilot/data/skill/...` 的 Markdown）和 **案例记忆**，模型常优先用 `read` 打开本地文件，因为路径具体、符合「查 SOP」直觉；**「经验丰富」「沉淀经验」不会自动触发 `memory_case_search`**。对策：在应用 System Prompt 或本仓库的 `memory-case-agent` 技能里写死 **先 `memory_case_search` 再读 skill 文件**；并确认对话已挂载 **`tool(memory_case)`**（工具列表里可见四个 `memory_case_*`）。

## 与 MemPalace 的对应关系（概念）

| MemPalace 习惯 | 案例记忆中的做法 |
|----------------|------------------|
| Wake 时 `mempalace_status` | 接到**可复现故障/排查类**任务时，先 **`memory_case_search`**（必要时再 **`memory_case_render`**） |
| 回答前人/事/史前先 `mempalace_search` | 给出**与历史处置强相关**的结论前，先 **search**，避免凭对话幻觉编造「以前都这么修」 |
| 不确定就说「让我查一下」 | 检索结果空或矛盾时，**明确说未命中案例库**，再基于当前证据推理 |
| Session 结束 `mempalace_diary_write` | 任务收尾时判断是否 **`memory_case_upsert`**；若参考了某条案例，**`memory_case_feedback`** |
| 事实变更 invalidate + add | 旧结论被推翻：对旧案例 **`memory_case_feedback`**（如 `stale` / 降置信）+ 对新结论 **upsert** 或合并 `case_id` |
| `mempalace_check_duplicate` | **无单独工具**：用 **`memory_case_search`** 同一 `query`/症状做近重复检查，再决定新建还是带 **`case_id`** 合并 |

---

## 建议会话协议（FOLLOW EVERY TASK）

1. **任务开始（排查 / 告警 / RCA）**  
   - 调用 **`memory_case_search`**：`query` = 现象关键词 + 组件/服务名 + 关键操作（短句），`top_k` 建议 **5～8**。  
   - 命中多条时用 **`memory_case_render`** 整理可读片段再进入主分析。  
   - **不要**把整段系统提示或超长日志塞进 `query`。

2. **分析过程中**  
   - 根因范围或症状描述明显变化 → **再 search** 一次（收紧 `query`）。  
   - 对某条历史案例**实际采纳或否决** → 记下 `case_id`，收尾时用 **`memory_case_feedback`**。

3. **准备下结论或对外建议前**  
   - 若结论依赖「历史上是否出现过类似」→ **必须先有 search 证据**；没有则声明未检索或未命中。

4. **任务结束**  
   - 有可沉淀的 RCA / 处置步骤 / 明确结论 → **`memory_case_upsert`**。  
   - **写库前**：用 search 做近重复检查；高度相似则 **带上已有 `case_id` 合并**，避免碎片案例。  
   - 不值得写入（纯闲聊、无新信息）→ 在回复里一句话说明即可。

5. **案例被新证据推翻**  
   - 对旧条目 **`memory_case_feedback`**（如 `helpful: false`、`signal: stale` 等，按你们策略）  
   - 再 **upsert** 新叙述或合并更新。

---

## 工具速查

| 工具 | 何时用 |
|------|--------|
| `memory_case_search` | 开场与线索变化时；兼作「查重」入口 |
| `memory_case_render` | 需要把命中案例变成 Markdown 再推理或展示 |
| `memory_case_upsert` | 收尾沉淀；合并时带 `case_id` |
| `memory_case_feedback` | 引用某条案例后的质量闭环 |

`scope`（`app_code` / `environment` / `conv_id`）通常由宿主注入，**不要随意伪造**。

---

## 给应用构建者的 System Prompt 片段（可选粘贴）

```
你已接入案例记忆（memory_case_*）。对故障/排查类任务：在深入分析前必须先 memory_case_search；
引用历史结论前须有检索结果支撑；收尾时评估是否 memory_case_upsert，并在参考过某条案例后
酌情 memory_case_feedback。query 保持简短，勿粘贴整段系统提示或完整日志。
```

更完整的设计背景见 [MEMORY_CASE_MCP_PLUGIN.md](./MEMORY_CASE_MCP_PLUGIN.md)。
