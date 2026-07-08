# RFC-005:跨文档实体关联与双形态空间(个人知识 / Agent 记忆)

> 状态:草案
> 配套对比分析见 [memframe-comparison](./memframe-comparison.md)。本 RFC 接续 [RFC-001](./rfc-001-three-layer-data-model.md)(三层数据模型)、[RFC-002](./rfc-002-vaultfs.md)(VaultFS)、[RFC-003](./rfc-003-schema-md.md)(schema.md)、[RFC-004](./rfc-004-tool-protocol.md)(工具协议)。

## Context(为什么要做)

当前 OpenDerisk 知识空间上传文档后"自动整理 wiki 和 graph",但源码核实显示这只是表象:

- ingest pipeline(`ingest.py:_run_pipeline` :207-325)只做"文件 → verbat → 每 verbat 各生成一篇 wiki → 加一条 `derived-from` 边",**没有实体抽取、没有跨 verbat/文档合并步骤**。
- L2 图的"节点"其实是文档标题字符串,边只有 `cites`/`links-to`/`derived-from` 三种(`local.py:_rebuild_doc_edges` :719-792),跨文档连接只能靠 wikilink 撞名(弱且无消歧)。
- 规划文档自己写着 `knowledge_graph_nodes: 0  # P0 占位,P1 接入 llm-wiki`。
- `MEMORY_RELATION_TYPES`(`schema.py:178-185`,含 merged-into/supersedes/about/relates-to)已定义但**无中心路径调用**;`Space` 无 type 字段;溯源/时效/置信无承载字段。

对比四套框架(详见 [memframe-comparison](./memframe-comparison.md))后的结论:OpenDerisk 的三层数据模型 + Edge schema 在数据模型层是最完备的,缺的是三件事——跨文档关系是空的、无汇总性节点、双形态无抽象。

**目标**:让 OpenDerisk 同时支持个人知识空间管理与 Agent 记忆空间管理两种形态,并在两种形态下都具备真正的跨文档实体关联。

**已选定方向**(对比分析后确认):

1. 跨文档关联走 **LLM-assisted 实体页归并**(抄 llm_wiki,不引入图数据库、不做完整三元组抽取)。
2. 形态区分走 **空间类型 + 溯源字段**(不拆两套存储,复用已预留的 schema)。
3. 实体归并 **ingest 后自动跑**(个人知识空间默认开)。
4. **三阶段全做**(形态抽象 → 实体页归并 → 检索召回增强)。

## 设计原则

- **复用已预留的 schema,不另起炉灶**:`MEMORY_RELATION_TYPES` 已定义本方案需要的全部谓词,只需让 agent_memory space 启用它。
- **最小 schema 改动**:溯源/时效/置信放 `Document.frontmatter`(已是自由 dict)和 `Verbat.metadata`(已是自由 dict),**不给 dataclass 加新字段、不动 SQL 表结构**。唯一需要修的是 `_edge_insert` 的 `valid_to` bug(这是既存 bug,且是前置依赖)。
- **不引入图数据库**:沿用现有 SQLite Edge 表 + LanceDB 向量 + LLM 生成实体页。
- **三阶段可独立交付**:每阶段有独立验证标准,失败可回退。

## 现状锚点(核实过的关键位置)

- 上传入口:`packages/derisk-serve/src/derisk_serve/knowledge/api/endpoints.py:398` `upload_file`
- pipeline:`packages/derisk-serve/src/derisk_serve/knowledge/ingest.py:207` `_run_pipeline`、`:373` `_generate_wiki`、`:363` `WIKI_SYSTEM_PROMPT`
- 边构建:`packages/derisk-ext/src/derisk_ext/knowledge/vaultfs/local.py:719` `_rebuild_doc_edges`、`:638` `_edge_insert`
- 数据类:`packages/derisk-core/src/derisk/knowledge/types.py:221` `Edge`、`:180` `Document`、`:97` `Space`
- schema:`packages/derisk-core/src/derisk/knowledge/schema.py:107` `DEFAULT_RELATION_TYPES`、`:178` `MEMORY_RELATION_TYPES`、`:188` `default_memory_schema_md`、`:95` `DEFAULT_PAGE_TYPES`
- VaultFS 公共 API:`packages/derisk-ext/src/derisk_ext/knowledge/vaultfs/base.py:329` doc_create、`:728` edge_add、`:766` graph_query、`:788` graph_traverse、`:504` doc_search
- service:`packages/derisk-serve/src/derisk_serve/knowledge/service/service.py:585` create_space、`:414` _persist_space_config

---

## Phase 1:形态抽象(SpaceType + 溯源)

### 目标

同一个 VaultFS 既承载个人知识空间,又承载 Agent 记忆空间,仅靠 space 级 type 决定 schema/写入门禁/时效策略。不拆两套存储。

### 改动

**a) `Space` dataclass 加 `space_type` 字段**(`types.py:97-122`)

```python
space_type: str = "personal"  # "personal" | "agent_memory"
```

字符串而非法,降低耦合。持久化进 space 配置(`_persist_space_config` 已把 Space 序列化)。

**b) Space 初始化时按 type 选 schema**(`service.py` 的 `create_space` :585-644 + `_persist_space_config` :414)

- `space_type="personal"` → 用 `default_schema_md()`(含 `DEFAULT_RELATION_TYPES`)
- `space_type="agent_memory"` → 用 `default_memory_schema_md(app_name)`(`schema.py:188-242`,已定义但当前无中心路径调用——本方案补上这一处)。这会把 `merged-into/supersedes/about/relates-to` 谓词写入 schema.md,使 `edge_add` 能验证通过。

**c) 溯源/时效/置信用 frontmatter 约定键**(不动 Document dataclass)

在 `_generate_wiki`(`ingest.py:373-448`)和 Agent 写入路径里,约定写如下 frontmatter 键:

| 键 | personal | agent_memory |
|---|---|---|
| `provenance` | `human` | `agent` |
| `author_agent_id` | 不写 | 写 agent_id |
| `confidence` | 不写(默认 1.0) | 0..1 |
| `valid_from` | 不写 | 写 |
| `valid_to` | 不写(永久) | 写(可空=未过期) |

`Verbat.metadata` 已是自由 dict,Agent 写入时塞 `conv_id`/`turn_round`/`agent_id`(代码里已有 `_verbat_find_by_session` 查 `conv_session_id` 的先例,types.py:144 注释已说明会带这些键)。

**d) 验证**

- 创建 personal space 和 agent_memory space 各一个。
- 读取两个 space 的 schema.md,断言 agent_memory space 的 relation_types 含 `merged-into/supersedes/about/relates-to`,personal space 不含。
- 在 agent_memory space 调 `edge_add(predicate="supersedes")` 应成功;在 personal space 同样调用应被 `validate_predicate` 拒绝。

---

## Phase 2:跨文档实体页归并(LLM-assisted,核心)

### 目标

ingest 完一篇 wiki 后,LLM 抽取关键实体 → 读 space 内已有 entity 页索引 → 判断 已存在/新建/矛盾 → 合并或建新页,并通过 `about`/`supersedes` 边把多文档锚定到同一实体。这是跨文档关联的真正来源,替代当前"标题撞名"。

### 改动

**a) 修复 `_edge_insert` 的 `valid_to` bug(Phase 2 前置,也是既存 bug)**

`packages/derisk-ext/src/derisk_ext/knowledge/vaultfs/local.py:638-659`:当前 SQL `VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)` 硬编码 `valid_to=NULL`,`Edge.valid_to` 字段对新边实际失效。改为绑定 `e.valid_to`。supersedes 边要靠 valid_to 表达旧实体页失效,这是前置依赖。同步检查 `distributed.py` 的等价实现是否有同样问题。

**b) ingest pipeline 增加一步 `_curate_entities`**(`ingest.py`)

在 `_run_pipeline`(:207-325)的 wiki 生成循环(:287-306)**之后**、返回 job 之前,加:

```python
if space.space_type in ("personal", "agent_memory"):  # 可配置开关
    for verbat_id, doc_id in generated_pairs:
        await self._curate_entities(space, vault, doc_id, llm_model)
```

顺序执行(沿用 :287 注释 "sequential to avoid hammering the LLM" 的既定风格)。

**c) `_curate_entities` 方法**(新增,放 `ingest.py`)

逻辑(对齐 llm_wiki 的两步 CoT):

1. 读刚生成的 wiki 文档(`vault.doc_read(path)`)。
2. LLM 调用(新 prompt `ENTITY_CURATE_PROMPT`):输入 = wiki 正文 + space 内现有 entity 页索引(从 `doc_list(type="entity")` 取 title + 一句描述)。输出严格 JSON:
   ```json
   {"entities": [
     {"name": "风控模型A", "action": "new|merge|supersede",
      "existing_path": "entities/风控模型a.md",
      "summary": "...", "contradicts_existing": "..."}
   ]}
   ```
3. 按 action 分发:
   - `new` → `vault.doc_create(path=f"entities/{slug}.md", content=entity_md)` + `edge_add(predicate="about", subject=f"doc:{entity_doc_id}", object=f"doc:{source_doc_id}")`。
   - `merge` → `vault.doc_edit(path=existing_path, content=merged_md)`(merged_md 由 LLM 输出合并后正文,沿用 llm_wiki `page-merge` 思路:frontmatter 取并集 + 正文 LLM 合并)+ `edge_add(predicate="about", ...)` 追加 source。
   - `supersede` → `vault.doc_create` 新版 + `edge_add(predicate="supersedes", subject=new, object=old)` + `edge_invalidate` 旧版相关边。
4. 同步更新 `wiki/entities/index` 列表页(若 LLM 漏写,沿用 :952-1031 `buildAggregateRepairPrompt` 的 repair 机制补写)。

**d) `ENTITY_CURATE_PROMPT`**(新常量,放 `ingest.py` 类常量区 :363 附近)

参考 `WIKI_SYSTEM_PROMPT` 的写法,要求:

- 只抽"关键实体"(限制 3-8 个,控成本)
- 对每个实体必须判断 `action`(显式给出现有 entity 索引)
- 输出严格 JSON(便于解析,避免再解析 markdown)
- merge 时输出完整合并后正文

**e) entity 页路径与 PageType**

`PageType("entity")` 已在 `DEFAULT_PAGE_TYPES`(`schema.py:95-105`)定义,路径前缀 `entities/` 已是约定。无需新增 PageType。

**f) agent 工具**(可选,Phase 2 后期)

在 `packages/derisk-ext/src/derisk_ext/knowledge/tools/l2.py` 补一个 `EntityCurateTool`(手工触发,供 Agent 在对话中维护实体页)。Phase 2 的核心是 ingest 自动跑,工具可后置。

**g) 验证(强成功标准,可独立循环)**

1. 上传文档 D1(讲"风控模型A")到 personal space → 断言生成 `entities/风控模型a.md` + 一条 `about` 边连 D1。
2. 上传文档 D2(也讲"风控模型A",不矛盾)到同 space → 断言**没有**新建第二个 entity 页,而是 `entities/风控模型a.md` 被 `doc_edit` 合并(正文含两份来源),且有第二条 `about` 边连 D2。
3. 上传文档 D3(讲"风控模型A"但与现有内容矛盾)→ 断言新建 `entities/风控模型a-v2.md` + `supersedes` 边连旧版,旧版 `about` 边被 `edge_invalidate`(valid_to 非空)。
4. `graph_query(entity="doc:<entity页id>", hop=1)` 返回的子图含所有被 about 的源文档——**这是跨文档关联的可验证证据**。

---

## Phase 3:检索召回增强(图扩展 + 分层装配)

### 目标

检索时不仅召回命中关键词的单文档,还通过实体图把"语义邻居"文档拉进来(跨文档召回),并对 Agent 记忆空间应用时效策略。

### 改动

**a) `doc_search` 加 `mode="graph"`**(`base.py:504-515` 的 `doc_search`,以及 local.py 实现)

新流程:

1. 先用现有 `mode="hybrid"`(FTS + vector RRF,已实现)取 top-K 种子文档。
2. 对每个种子,用 `graph_traverse(entity=f"doc:{seed_doc_id}", hop=1)`(`base.py:788-811`,已实现 BFS)拿到 `about`/`relates-to` 边连接的实体页,再取实体页 `about` 的其他源文档作为"图扩展邻居"。
3. 合并入结果,图扩展项标注 `source="graph_expansion"` 并降权(避免噪声淹没直接命中)。

预算装配可借鉴 llm_wiki `context-budget.ts`,但 OpenDerisk 是后端,先做简单上限(top-K + 邻居上限 N),不做复杂 token 预算。

**b) Agent 记忆空间专属过滤**

检索 agent_memory space 时,在 `doc_search` 加过滤逻辑:

- `valid_to` 过期且 `include_invalid=False` 的条目不返回(沿用 `Edge.is_active` types.py:237-244 + `graph_query(include_invalid=False)`)。
- `supersedes` 链中只返回最新版。
- 结果按 `confidence` frontmatter 降序(个人空间无此键则默认 1.0)。

**c) HTTP endpoint**(`endpoints.py:765-797` 的 `POST /spaces/{slug}/search`)

`SearchRequest.mode` 已是字符串,直接接受新值 `"graph"`,无需改 schema。

**d) 验证**

1. 上传 D1、D2(都讲实体 E,但 D2 不含查询关键词"评分卡")。
2. 搜索"风控模型A 评分卡",`mode="hybrid"` 只返回 D1;`mode="graph"` 通过 D1→entity E→D2 的 about 边,把 D2 也召回(标注 graph_expansion)。
3. agent_memory space 中,`valid_to` 已过期的记忆条目默认不返回,`include_invalid=true` 时返回。

---

## 关键复用清单(已存在、本 RFC 不重写)

| 已有能力 | 位置 | 复用方式 |
|---|---|---|
| `MEMORY_RELATION_TYPES`(merged-into/supersedes/about/relates-to) | `schema.py:178-185` | agent_memory space 启用 |
| `default_memory_schema_md(app_name)` | `schema.py:188-242` | space 创建时按 type 调用 |
| `PageType("entity")` | `schema.py:95-105` | 实体页类型,已定义 |
| `Edge.valid_from/valid_to/weight/source_document_id` | `types.py:221-244` | 实体关系边的语义全部已就绪 |
| `doc_create/doc_edit/doc_delete` | `base.py:329-474` | 实体页 CRUD |
| `edge_add/edge_invalidate` | `base.py:728-761` | 实体关系写入 |
| `graph_query/graph_traverse/graph_backlinks` | `base.py:766-823` | 跨文档召回(注:`graph_query` 的 hop 被忽略,Phase 3 用 `graph_traverse`) |
| `doc_search(mode="hybrid")` | `base.py:504-515` | Phase 3 种子召回 |
| `_call_llm` / `_make_model_caller` | `ingest.py:499-589` | 实体抽取 LLM 调用 |
| `buildAggregateRepairPrompt` 修复机制 | `ingest.py:952-1031` | entity index 漏写时补写 |

## 关键待修(本 RFC 带出)

| 问题 | 位置 | 修法 |
|---|---|---|
| `_edge_insert` 硬编码 `valid_to=NULL` | `local.py:638-659` | 改为绑定 `e.valid_to`;同步检查 `distributed.py` |
| `default_memory_schema_md` 无调用方 | `schema.py:188-242` | Phase 1 在 create_space 按 space_type 调用 |

---

## 整体验证(end-to-end)

Phase 1-3 全部完成后,跑端到端场景:

**场景 A:个人知识空间跨文档关联**

1. 创建 personal space。
2. 上传 3 篇讲同一主题(含 1 篇矛盾)的 PDF。
3. 断言:生成 2 个 entity 页(原版 + supersede 版),`about` 边连接 3 篇源文档,`supersedes` 边连接两个 entity 页。
4. 搜索相关词,`mode="graph"` 召回跨文档邻居。

**场景 B:Agent 记忆空间时效管理**

1. 创建 agent_memory space。
2. 模拟 Agent 写入一条记忆(带 valid_from/valid_to/confidence)+ 后续写入矛盾记忆(supersede)。
3. 断言:过期记忆默认不召回;被 supersede 的旧记忆默认不召回;`include_invalid=true` 可召回全部。
4. 断言:schema.md 含 `merged-into/supersede` 等 memory 谓词。

**场景 C:回归**

1. 现有 personal space 上传流程(无实体归并开关关时)行为不变(向后兼容)。
2. 现有 `edge_add`/`graph_query` agent 工具不受影响。

---

## 不做(超出本 RFC 范围)

- 不引入图数据库(TuGraph/Neo4j)——llm_wiki 路线用 markdown 实体页 + Edge 表足够,与 mempalace 三套碎片化的教训一致。
- 不做完整三元组(triple)抽取——LLM-assisted 实体页已覆盖关联需求,三元组成本高、失败率高(参考 hermes Holographic 正则方案局限)。后续如需更细粒度可再评估。
- 不做社区发现(Louvain/Leiden)——llm_wiki 仅用于可视化,本 RFC 暂不需要。
- 不重新集成 mempalace(已确认移除,且其单写者锁 + 正则抽取中文弱不适合)。
- 不动 Document/Verbat dataclass 字段(溯源走 frontmatter/metadata 约定键),避免 SQL 迁移成本。

---

## 实施顺序建议

1. Phase 1(space_type + schema 选择)——最小,1-2 文件改动,先落地。
2. 修 `_edge_insert` valid_to bug(Phase 2 前置)。
3. Phase 2(`_curate_entities` + prompt + entity 页归并)——核心,验证标准 A 场景。
4. Phase 3(检索模式 `graph` + agent_memory 过滤)——验证标准 B/C 场景。

每步独立可验证,失败可回退。