# 知识/记忆框架对比分析:跨文档关系与内容索引

> 对比对象:llm_wiki、llmwiki、hermes-agent、mempalace 四套框架,聚焦"跨文档关系处理"与"完整内容索引构建"。
> 目的:判断 OpenDerisk 当前知识框架要如何演进,才能同时支撑"个人知识空间管理"与"Agent 记忆空间管理"两种形态。
> 全部结论基于源码实测(file:line),非二手资料。
> 配套实施计划见 [RFC-005](./rfc-005-cross-doc-relation-and-dual-space.md)。

---

## 一、定位与形态对比

| 维度 | llm_wiki | llmwiki | hermes-agent | mempalace |
|---|---|---|---|---|
| 本质 | 个人知识库(Tauri 桌面应用) | 个人知识库(MCP/Web/Chrome) | 通用 Agent 框架,记忆是子系统 | 本地优先的个人 AI 记忆框架 |
| 形态 | 单形态:个人知识库 | 单形态:同一空间内 raw + wiki 两层 | 隐性三态:USER.md / MEMORY.md / state.db | 个人知识 + Agent 记忆,wing 为统一隔离原语 |
| 接入 | 本地 HTTP + MCP 只读 | MCP 写入 + HTTP | MemoryProvider 插件化(内置 + 至多一个外部) | 独立 CLI/MCP,与 OpenDerisk 无耦合 |
| 是否区分个人/Agent | 否 | 否(path + source_kind 软分) | 概念上分,无显式隔离 | wing 命名约定区分,数据模型同构 |
| 存储后端 | markdown 文件 + LanceDB 向量 | SQLite/Postgres + FTS(无向量) | 文件 + SQLite FTS5 + 外部 provider | ChromaDB(可插拔)+ SQLite KG + JSON 边 |
| 与 OpenDerisk 关系 | 无 | 无 | 无 | **已不集成**(2026-06-24 移除) |

**关键判断**:

- 四者里只有 hermes-agent 和 mempalace 在概念上区分了"个人"与"Agent 记忆",但实现上都没有真正的形态抽象——hermes 靠文件堆 + 单外部 provider,mempalace 靠 wing 命名约定。
- llm_wiki / llmwiki 都是单一空间,靠 LLM 自觉维护。
- mempalace 曾是 OpenDerisk 的 Agent 记忆后端设计目标,但适配层 `MemPalaceMemoryStore` 已在提交 `cebb78b5` 整体删除,`derisk-ext/pyproject.toml:80` 明确注释 `storage_mempalace = []  # removed`。当前 OpenDerisk 无任何运行代码 `import mempalace`,残留仅有失效测试 `tests/test_memory_integration.py`(引用已删文件)和旧设计文档 `.claude/plans/mempalace-integration.md`。

### 各框架要点速览

- **llm_wiki**:基于 Karpathy LLM Wiki 模式的桌面应用,核心理念"反 RAG"——不是每次查询都从原始文档检索,而是 LLM 增量构建并维护持久的 markdown wiki,知识"编译一次、持续更新"。三层:Raw sources / Wiki(entities/concepts/sources/queries/synthesis/comparisons)/ Schema。三种操作:Ingest / Query / Lint。
- **llmwiki**:Karpathy 模式的开源产品化实现,MCP server + Web + Chrome 扩展。强调"自主维护"——Claude Routine 定时消化新增资料并更新受影响 wiki 页。架构:Claude/Web/Chrome → MCP/HTTP → VaultFS(local: SQLite+文件系统 / hosted: Postgres+S3)。`wiki/` 是普通 markdown(用户所有),`.llmwiki/` 是可重建派生层。
- **hermes-agent**:Nous Research 的自改进 Agent 框架,记忆是其子系统之一(其余还有 skills 自创建、cron、子 Agent 委派、多平台网关、RL 训练管线)。记忆栈是插件化单选后端:内置 `builtin`(文件式 MEMORY.md/USER.md)+ 至多一个外部 `MemoryProvider`(8 个实现:honcho/hindsight/holographic/mem0/openviking/retaindb/byterover/supermemory)。**代码与文档中不存在 "hermes 4-tier" 统一记忆工作流**——唯一的分层是 OpenViking 的 L0/L1/L2(内容读取粒度)和 prompt 的 stable/context/volatile 三层缓存区。
- **mempalace**:独立的 PyPI 包(v3.5.0, MIT),以"记忆宫殿/卡片盒"隐喻组织对话与文档原文。严格 verbatim(不摘要、不抽取、不 paraphrase)。层级:WING(person/project) → ROOM(day/topic) → DRAWER(verbatim chunk),外加 AAAK 压缩指针索引层(closets)和独立 SQLite KG。

---

## 二、跨文档关系处理对比(核心问题)

### 2.1 关系来源机制

| 机制 | llm_wiki | llmwiki | hermes-agent | mempalace |
|---|---|---|---|---|
| 关系来源 | LLM 读 index 自判 + 生 wikilink | 正则解析脚注/wikilink | 几乎没有(builtin 零关系);外部 provider 各做各的 | 实体共现(hallway)+ 跨 wing 同实体(tunnel)+ KG 三元组 |
| 实体抽取 | LLM 抽(产 entity 页,无三元组) | 无(entity 是手写页面分类) | Holographic 正则(只认大写词组/英文),Hindsight 服务端 | 正则 + COCA 滤网(中文几乎失效) |
| 三元组/属性图 | 无 | 无(cites/links_to 两种边) | Holographic fact-entity 双表(非 (s,p,o)) | KG 三元组 (s,p,o) 带 valid_from/to |
| 实体归并/消歧 | LLM 自判 + 事后 dedup(LLM-driven 离线) | 文件名 basename 小写匹配(取第一个,会错并) | name + aliases(LIKE),aliases 有 schema 无写入路径(半成品) | name.lower() 归一化自动合并;disambiguate 仅处理人名/普通词混淆 |
| supersedes/merged-into | 无(页级合并+备份) | 无(最后写入胜出) | 无(append,无版本) | **无显式关系边**(只有 KG valid_to 失效) |
| 跨文档连接 | 4-Signal(source overlap ×4.0 / wikilink / 向量 / Adamic-Adar) | 仅脚注/wikilink + 1 跳 backlink | Holographic HRR reason(多实体组合查询)+ contradict(矛盾检测) | entity tunnel(跨 wing 同实体)+ hallway(共现) |
| 图算法 | Louvain 社区(可视化,非建图) | 无 | 无(Jaccard + HRR 相似度做矛盾检测) | 无社区发现(对称哈希防重复边) |
| 多跳遍历 | 宣称 2-hop,实际 1-hop 固定 3 邻居 | 无多跳(1 跳 backlink) | 非遍历式,是代数解构 | tunnel/hallway 各自导航,无统一图遍历 |

### 2.2 各框架关系机制详解

**llm_wiki** — 两步 CoT ingest(`src/lib/ingest.ts:797-883`):

- Step1 分析:LLM 读源文档 + 当前 `wiki/index.md` + `purpose.md`,产出结构化分析,显式要求 "Connections to Existing Wiki"、"Contradictions & Tensions"、对每个实体判断 "Whether it likely already exists in the wiki (check the index)"。**关联是 LLM 读 index 后自行判断**,非规则匹配。
- Step2 生成:LLM 生 `[[wikilink]]` 跨引用、生 entity/concept 页(frontmatter 写 `sources:[]`/`related:[]`)、更新 `index.md`/`overview.md`。
- 页级合并(`src/lib/page-merge.ts:89-181`):同路径页 frontmatter 数组字段取并集 + 正文差异交 LLM 重写合并 + 锁定 type/title/created。
- 去重器(手动触发,`src/lib/dedup.ts`):LLM 识别同义 slug 组 → 用户确认 → `mergeDuplicateGroup` 合并正文 + 确定性合并 frontmatter + 跨全 wiki 改写 wikilink/related。**事后离线消歧**,非 ingest 实时。
- 4-Signal 图(`src/lib/graph-relevance.ts:30-43`):wikilink backlink + source overlap(权重 ×4.0)+ 向量相似(召回用,不建边)+ Adamic-Adar 共同邻居(检索时动态算)。**边不持久化,每次查询从文件 + frontmatter 派生**(内存缓存)。

**llmwiki** — 纯显式语法驱动(`api/services/references.py`、`mcp/tools/references.py`):

- 从页面正文正则解析两种引用:`[^1]: paper.pdf, p.3`(cites,带页码)和 `[文字](other-page.md)`(links_to)。
- 每次写完调 `_sync_references` → **删该文档所有出边 → 重解析正文 → 重建出边**(`references.py:113-121`),文档级增量重建。
- `build_lookup_maps` 建 filename/basename/相对路径三张查找表,lower-case + basename 回退匹配。同路径页取第一个(`setdefault`),**会产生错误归并**。
- 边表 `document_references(source_document_id, target_document_id, reference_type, page)`,CHECK 约束 `reference_type IN ('cites','links_to')`(`shared/sqlite_schema.sql:42-49`)。**只有两种边,1 跳,无多跳,无图算法**。
- 写完返回影响面("3 page(s) reference this document — consider updating",`write.py:293-306`),把维护图变成 LLM 自然行为。

**hermes-agent** — 关系能力极度依赖外部 provider,builtin 零关系:

- builtin `MemoryStore`(`tools/memory_tool.py`):新记忆追加进 `MEMORY.md` 是平铺列表,条目间唯一关系是 `§` 分隔符和字符配额竞争(~2200 字符硬限),`add` 仅做精确去重和容量检查,**无关联**。
- Holographic(本地唯一有实现的 provider):
  - 实体抽取纯正则(`store.py:398-431`):只认大写词组/引号词/aka 模式,**对中文几乎失效**。
  - 三元组式存储:`facts` ↔ `fact_entities` ↔ `entities`(单 SQLite 库,非图数据库)。
  - 实体归并 `_resolve_entity`(`store.py:433-461`):name LIKE + aliases LIKE,但 `aliases` 列有 schema **无写入路径**(半成品)。
  - HRR 向量符号架构(`holographic.py`):SHA-256 确定性 phase encoding + bind/unbind/bundle 代数。`reason(多实体 AND 组合查询)`、`contradict(实体 Jaccard≥0.3 + content HRR 相似度低 ⇒ 矛盾)` —— 这是 embedding DB 做不到的,且 SNR 容量告警给可解释退化阈值。
- Hindsight 的 entity resolution / knowledge graph 在服务端,本仓库只是 client,不可审计。
- **无 merged-into/supersedes/版本链**;去重仅靠 `facts.content UNIQUE`。

**mempalace** — 关系机制最丰富但碎片化:

- 实体元数据抽取(`miner.py:884-938`):`known_entities.json` 大小写不敏感匹配 + 内容前 N 字符里出现 ≥2 次的 capitalized 词(经 COCA 内容词滤网 + known-systems 复合词预处理,英文导向)。
- mine 完一个 wing 后做三件事(`miner.py:1744-1789`):
  1. **Topic tunnels**(跨 wing):基于 TOPIC 标签重叠,`kind="topic"` tunnel。
  2. **Hallways**(wing 内):`compute_hallways_for_wing`(`hallways.py:198-365`)对 drawer 的 `entities` 元数据做**实体共现**统计,共现 ≥2 生成 hallway。
  3. **Entity tunnels**(跨 wing):`entity_tunnels_for_wing`(`palace_graph.py:879-951`)同一实体出现在多 wing 的 hallways 里时跨 wing 建边。
- KG(`knowledge_graph.py`):真正 (subject→predicate→object) 三元组,带 `valid_from/valid_to/confidence/source_closet/source_drawer_id`,SQLite `entities`+`triples` 两表。**但 miner 不自动抽 KG 三元组**,需显式 `kg.add_triple`/`seed_from_entity_facts`——被动 ingest 流程里 KG 基本是空的。
- 实体归并(`knowledge_graph.py:219-220`):`_entity_id(name)=name.lower().replace(" ","_").replace("'","")`,同名实体以小写归一化为唯一 id 自动合并(`INSERT OR IGNORE`)。disambiguate 仅处理"既是人名又是普通词"混淆。
- **三套边模型互不复用**:JSON(tunnel,room-based)+ JSON(hallway,entity-pair co-occurrence)+ SQLite(KG,entity-predicate-entity triple),三套 API、三套语义,导航 API 各自分开(`tool_traverse_graph`/`tool_find_tunnels` vs `tool_list_hallways` vs `tool_kg_query`)。无统一图遍历,无社区发现,无 supersedes 显式关系边。

### 2.3 关系/边存储结构

| 框架 | 边存储 | 持久化方式 |
|---|---|---|
| llm_wiki | **不持久化图**,每次查询从文件 + frontmatter 派生(内存缓存) | markdown frontmatter 字段(sources/related/wikilink) |
| llmwiki | SQLite/Postgres `document_references` 表 | 两类边 `cites`/`links_to`,增量重建(删出边→重解析) |
| hermes-agent | Holographic SQLite facts/entities/fact_entities | 单库,无图数据库;外部 provider 各自云存储 |
| mempalace | **三套碎片化**:JSON(tunnel)+ JSON(hallway)+ SQLite(KG) | 互不复用,三套 API、三套语义,导航 API 各自分开 |

### 2.4 核心结论

**四个框架本质上都没有完整的"跨文档实体级关联"链路**(实体抽取 + 消歧 + 归并 + 全局图)。它们的跨文档关系建立在四种弱机制上:

1. **显式语法引用**(脚注/wikilink)——靠 LLM 或人"恰好引用了"别的文档,人工标注级。llmwiki 最纯粹走这条路,能力最弱(1 跳、撞名)。
2. **LLM 读全局目录自判**——llm_wiki 让 LLM 读 `index.md` 判断实体是否已存在,中等规模(~100 源)性价比高,但规模一上来不可靠(README 自承)。
3. **规则共现/同名归并**——mempalace 的 hallway/tunnel 是最接近"自动跨文档"的,但实体抽取是正则、中文失效,且三套边互不复用。
4. **外包给云 provider**——hermes 把关系能力外包,丧失可审计性;本地 Holographic 用 HRR 做了一件独特的事(代数式多实体查询 + 矛盾检测),但抽取层太弱。

**mempalace 的关系机制是四者里最丰富的**(hallway 共现 + entity tunnel + KG 时序三元组),但:

- 实体抽取正则对中文几乎失效(COCA 滤网、known-systems 都是英文导向)
- 三套边模型(tunnel/hallway/KG)互不复用,无统一图遍历
- 单写者租约(per-palace writer lock,`mcp_server.py:299-`),多 Agent 并发写会退化为只读
- miner 写入时**不自动从原文抽 KG 三元组**(KG 三元组需显式 `kg.add_triple`),被动 ingest 流程里 KG 基本是空的

**这正是 OpenDerisk 当初移除 mempalace 的合理性所在**:单写者锁 + 正则抽取中文弱 + 无 LLM 摘要层,不适合 OpenDerisk 的多 Agent + 中文场景。但 mempalace 的"实体共现建边"和"跨条目同实体归并"两个思路值得借鉴——用 LLM-assisted 抽实体能直接超越 mempalace 的正则方案,且统一进现有 Edge 表(不搞三套碎片)。

---

## 三、完整内容索引构建对比

### 3.1 索引模型

| 维度 | llm_wiki | llmwiki | hermes-agent | mempalace |
|---|---|---|---|---|
| 索引模型 | 三套并行:LLM 摘要目录(index.md) + tokenized 关键词 + LanceDB 向量 chunk | 一套:chunk + FTS5/PGroonga 全文检索(**无向量**) | 多套并行孤岛:FTS5 会话 + HRR facts + 外部 provider | chunk + embedding 向量 + AAAK 压缩指针(closet)+ KG/hallway/tunnel 导航 |
| 汇总性节点 | **强**:entities/concepts/synthesis/comparisons/overview,LLM 生成并持续合并 | 中:overview/concepts/entities,LLM 按 guide 手写 | 无统一汇总节点(builtin 全量注入,无索引) | 无 LLM 摘要(verbatim 原则禁了);L1 仅 top-N 截断;closet 是指针 |
| 概念页/实体页 | 一等公民,跨文档内容浓缩到一张页 | LLM 手写,高连通度枢纽 | 无 | wing/room/drawer,无实体页层 |
| 增量机制 | SHA256 缓存 + 长文档 checkpoint + 页级合并 + 向量 upsert | chunk 增量(触发器)+ 引用图文档级增量重建 | FTS5 触发器 + Holographic 每次 add 全量重建 category bank | drawer id 确定性 → re-mine idempotent upsert;hallway/tunnel 保留其他 wing |
| 全量重建 | 手动 re-index | reindex CLI + /graph/rebuild(5min 冷却) | Holographic rebuild_all_vectors(迁移用) | **无全量重建命令**(违背 verbatim 增量原则) |

### 3.2 各框架索引机制详解

**llm_wiki** — 三套并行索引:

- `wiki/index.md`:LLM 维护的内容目录,每次 ingest 强制更新,按类别列出所有页 + 一句话描述。检索时裁剪后进 prompt。
- Tokenized 关键词索引(`src-tauri/src/commands/search.rs:130-272`):全量扫描 `wiki/`,文件名精确 +200、标题短语 +50、标题 token ×5、正文 ×1。CJK bigram。**全量扫描,无倒排**。
- LanceDB 向量 chunk(`vectorstore.rs:460-527`):`chunkMarkdown` 切块 → embedding → upsert `wiki_chunks_v2` 表。搜索 over-fetch topK×3 → 按 page_id 聚合(max + 0.3×尾部)。
- **汇总节点**:`entities/*.md`/`concepts/*.md`/`synthesis/*.md`/`comparisons/*.md`/`overview.md`(每次 ingest 强制重生成)/`index.md`。`page-merge.ts` 保证同一实体页多源贡献时合并而非覆盖。
- 检索四阶段(`chat-panel.tsx:215-408`):关键词+向量 RRF → **图扩展(1-hop,getRelatedNodes)** → 预算装配。

**llmwiki** — 单套 chunk + FTS(无向量):

- chunk 切分(`mcp/services/chunker.py:21-105`):~512 token、~128 重叠,跟踪 Markdown header breadcrumb。
- 本地 SQLite FTS5(`porter unicode61`,触发器同步);hosted Postgres PGroonga(`&@~`/`pgroonga_score`)。**无 embedding/pgvector**。
- 巧妙设计:chunk `content` 是"materialized"形式(原文 + 用户高亮/批注),但保留 `source_content`(不可变原文)和 `annotations_text`,搜索结果区分命中来自原文还是用户笔记(`mcp/tools/search.py:236-265` 的 `[matched: note]`/`[matched: source+note]`/`[annotated]` 标记)。
- 文件系统是真理之源,`.llmwiki/` 是可重建派生层。写先落盘再更新索引。

**hermes-agent** — 多套并行孤岛,无统一索引:

- 内置会话检索(`hermes_state.py:253-306`):`messages_fts`(unicode61)+ `messages_fts_trigram`(CJK 子串)两张 FTS5,触发器同步 `content+tool_name+tool_calls`。跨 session 聚合 → `_resolve_to_parent` 把 delegation 子会话归并到根 → 并行 LLM 摘要。
- 内置 curated memory:MEMORY.md/USER.md 硬限 ~2200/~1375 字符,**全量塞进 system prompt**,无索引无需检索。"冻结快照"模式(会话开始拍快照,写盘不动 prompt,保 prefix cache)。
- 外部 provider 各自:Holographic FTS5+Jaccard+HRR 三路加权(`final=(0.4·fts+0.3·jaccard+0.3·hrr)·trust·temporal_decay`);Hindsight 服务端 semantic+graph+reranking;OpenViking L0/L1/L2 读取粒度分层。

**mempalace** — chunk 向量 + AAAK 指针 + 多套导航:

- Drawer(原文 chunk)入 ChromaDB `mempalace_drawers`(向量 + wing/room/source_file/date/entities 元数据)。
- **Closet(AAAK 压缩指针索引层)**(`dialect.py`):写 drawer 后生成 closet 行入 `mempalace_closets` collection。Closet 是"指向 drawer 位置的压缩指针",让 LLM 扫描 closet 快速定位 drawer 而非读全部原文。
- 检索 `search_memories`(`searcher.py:1036-1307`):**Hybrid** = drawer 向量召回(over-fetch n×3)→ closet 命中按 rank 加权 boost(`CLOSET_RANK_BOOST=[0.40,0.25,0.15,0.08,0.04]`)→ BM25 重排。设计为"closet 是排序信号而非门控"(weak closet 只能帮忙不能藏住 drawer)。
- L0–L3(`layers.py:39-446`):L0 Identity(~50tok 始终)/ L1 Essential Story(top-15 高 importance drawer 按 room 聚合)/ L2 On-Demand(wing/room 过滤取回)/ L3 Deep Search(全 palace 向量)。**这是"加载成本"四层,非"原文/摘要/图"三层**,L1 不做 LLM 摘要(违反 verbatim 原则)。

### 3.3 检索召回

| 框架 | 召回方式 | 跨文档召回 |
|---|---|---|
| llm_wiki | 关键词 + 向量 RRF → **图扩展(1-hop)** → 预算装配 | 图扩展是跨文档关键(source overlap + Adamic-Adar + wikilink 拉邻居) |
| llmwiki | chunk FTS(天然跨文档) + 1 跳 backlink | chunk 维度跨文档,但无多跳 |
| hermes-agent | session 历史聚合 → LLM 摘要 | 跨条目(非遍历),多 provider 孤岛无统一召回 |
| mempalace | drawer 向量召回 + closet rank boost + BM25 重排 | 默认跨条目;但 tunnel/hallway 是单独工具,不在默认 search 自动展开 |

### 3.4 分层记忆

| 框架 | 是否有 L0/L1/L2 分层 | 实现方式 |
|---|---|---|
| llm_wiki | 隐式:raw → wiki(entities/concepts) → overview | LLM 生成汇总页 |
| llmwiki | 隐式:raw → wiki → overview | LLM 手写汇总页 |
| hermes-agent | **显式但非存储层**:OpenViking L0/L1/L2(读取粒度);Honcho 双层注入(注入节流) | 不是"原文/摘要/图"三层 |
| mempalace | **有 L0–L3**(layers.py),但这是"加载成本"四层,非"原文/摘要/图" | L1 是 top-N drawer 截断拼接,**不做 LLM 摘要**(verbatim 原则) |

### 3.5 时效性 / 版本 / 冷热

| 维度 | llm_wiki | llmwiki | hermes-agent | mempalace |
|---|---|---|---|---|
| valid_from/to | 无 | 无 | 无 | 仅 KG 三元组有;drawer 无 |
| 版本链/supersedes | 无(页级合并+备份) | 无(最后写入胜出) | 无(append) | 无显式 supersedes(KG 用 valid_to 失效) |
| 冷热分层 | 无 | 无 | builtin 快照冻结(为 prefix cache) | 无 |
| 增量 idempotent | SHA256 缓存 | 触发器式 | 触发器式 | drawer id 确定性,re-mine idempotent |

**核心结论**:**没有任何一套框架同时具备** L0原文/L1摘要/L2图 的明确分层 + 跨文档实体归并 + 时效性 + 冷热压缩。

- llm_wiki 最完整(LLM 生成汇总节点 + 图扩展 + 增量),但无时效性、无版本链。
- mempalace 有 verbatim + 可插拔后端 + AAAK 指针索引层(工程最扎实),但无 LLM 摘要层(违反 verbatim 原则)、无冷热分层、drawer 无时效。
- llmwiki 砍掉向量,中文检索弱。
- hermes-agent 没有统一索引,是三套孤岛,同一事实多份副本无单一真相源。

---

## 四、OpenDerisk 当前知识框架的真实状态(源码核实)

### 4.1 上传 pipeline

`packages/derisk-serve/src/derisk_serve/knowledge/ingest.py:_run_pipeline`(:207-325):

1. MIME 探测 → 取 Extractor(`extractors/builtin.py`,6 种:文本/PDF/DOCX/PPTX/图片/音频,**只产纯文本 verbatim,不抽实体**)
2. `extractor.extract(...)` → `List[VerbatimSpec]`
3. `vault.verbat_add(Verbat.create(...))` 入 L0
4. **每个 verbat 各调一次 LLM** 生成一篇 wiki(`_generate_wiki` :373-448,**逐 verbat 独立,互不感知**)
5. 加一条 `edge_add(predicate="derived-from", subject=f"doc:{doc_id}", object=f"verbat:{vid}")`(:433-446)

**没有实体抽取、没有跨 verbat/文档合并步骤。** `WIKI_SYSTEM_PROMPT`(:363-371)只要求输出 markdown + frontmatter,不产实体/三元组。

### 4.2 边构建(唯一的关系来源)

`packages/derisk-ext/src/derisk_ext/knowledge/vaultfs/local.py:_rebuild_doc_edges`(:719-792),固定 3 种 predicate:

| predicate | 来源 | subject → object |
|---|---|---|
| `links-to` | markdown `[[wikilink]]` / frontmatter `related:` | 当前文档标题 → wikilink 目标标题 |
| `cites` | markdown `[^脚注]` | 当前文档标题 → 脚注 source |
| `derived-from` | frontmatter `sources[]` | 当前文档 → 源 verbat |

**所有边 subject 恒为当前文档标题**,object 是当前文档内的东西或源 verbat。处理完一篇后,**没有任何一步去读空间内其他文档归并/消歧/连边**。跨文档连接只能靠 wikilink 撞名(弱且无消歧)。

### 4.3 数据模型(已预留但未启用)

`packages/derisk-core/src/derisk/knowledge/types.py`:

- `Edge`(:221-244)已含 `space_id / valid_from / valid_to / source_document_id / source_verbat_id / weight`,predicate 是 str,由 schema.md 校验。
- `Document`(:180-200)**无** provenance/author/confidence/valid_from/to 字段,只有 `frontmatter`(自由 dict)可塞。
- `Verbat`(:124-172)有 `metadata`(自由 dict),注释说明可带 author/conv_id/turn_round。
- `Space`(:97-122)**无 type 字段**,只有 `backend: str` 和 `visibility`。

### 4.4 schema(关键发现)

`packages/derisk-core/src/derisk/knowledge/schema.py`:

- `DEFAULT_RELATION_TYPES`(:107-115,7 种):cites/links-to/derived-from/depends-on/causes/contradicts/part-of。**不含** merged-into/supersedes/about/relates-to。
- `MEMORY_RELATION_TYPES`(:178-185,6 种):derived-from/**merged-into/supersedes/about/relates-to**/part-of。**已定义但无中心路径调用**——`default_memory_schema_md(app_name)`(:188-242)是库函数,没有 service 路径在创建 space 时按 type 调用它。
- `PageType("entity")` 已在 `DEFAULT_PAGE_TYPES`(:95-105)定义,路径前缀 `entities/` 是约定。

### 4.5 现有能力清单(可复用,不必重写)

| 能力 | 位置 |
|---|---|
| `doc_create/doc_edit/doc_delete` | `base.py:329-474` |
| `edge_add/edge_invalidate` | `base.py:728-761` |
| `graph_query/graph_traverse/graph_backlinks` | `base.py:766-823`(`graph_query` 的 hop 被忽略,多跳用 `graph_traverse`) |
| `doc_search(mode="hybrid")` FTS+vector RRF | `base.py:504-515` |
| `_call_llm/_make_model_caller` | `ingest.py:499-589` |
| `buildAggregateRepairPrompt` 聚合页修复 | `ingest.py:952-1031` |

### 4.6 两个待修 bug(演进方案带出)

1. **`_edge_insert` 硬编码 `valid_to=NULL`**(`local.py:638-659`):SQL `VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)` 硬编码 NULL,`Edge.valid_to` 字段对新边实际失效。supersedes 关系要靠 valid_to 表达旧实体页失效,这是前置依赖。同步检查 `distributed.py` 等价实现。
2. **`default_memory_schema_md` 无调用方**(`schema.py:188-242`):需要 service 在 create_space 按 space_type 调用。

### 4.7 与 mempalace 的关系(确认已解耦)

- `packages/derisk-ext/pyproject.toml:80`:`storage_mempalace = []  # removed: mempalace integration dropped, short-term memory uses SimpleSQLite`
- `packages/derisk-ext/src/derisk_ext/storage/memory/__init__.py`:仅导出 `SimpleSQLiteMemoryStore`/`KnowledgeVaultMemoryStore`/`LettaMemoryStore`,无 `MemPalaceMemoryStore`(源文件已删,仅残留 `__pycache__/*.pyc`)
- 仓库无任何 `import mempalace` 运行代码;`configs/derisk-proxy-openai.toml:97` 仍引用 `type="mempalace"`(配置残留,后端已删);`tests/test_memory_integration.py` 引用已删文件(死测试)
- mempalace 仓库反向 grep `derisk`/`openderisk` 命中为 0,两项目代码层零耦合
- 当前 OpenDerisk 的 Agent 记忆路线(`storage/memory/__init__.py` 注释):route agent conversation fragments as L0 verbats with `extract_mode='convo'` into a designated knowledge space(RFC 001 §3.3),即用自研 KnowledgeVault 而非 mempalace

---

## 五、OpenDerisk 要解决的核心矛盾

回到需求:"同时支持个人知识空间管理 和 Agent 记忆空间管理"。

把四框架教训投影到 OpenDerisk,其 [RFC-001](./rfc-001-three-layer-data-model.md) 三层数据模型(L0 verbat / L1 wiki / L2 graph)+ Edge schema(已含 `space_id / valid_from/to / merged-into / supersedes / about / relates-to`)在**数据模型层已是五者里最完备的**。真正缺三件事:

### 缺口 1:跨文档关系是"空的"——只有容器没有内容

当前 ingest 只产 3 种文档级边,L2 图节点不是实体而是文档标题。

- llmwiki 教训:纯靠显式脚注/wikilink 也能成图,但只能 1 跳、靠撞名,规模受限。
- llm_wiki 启示:LLM 读全局 index 自判"实体是否已存在"是中等规模(~100源)下性价比最高的方案,比上场就堆三元组抽取现实得多。
- hermes/mempalace 教训:实体抽取/消歧外包给云 provider 丧失可审计性;本地正则抽取对中文失效。

### 缺口 2:没有"汇总性节点"——内容无法浓缩

四者里只有 llm_wiki 真正把 `entities/concepts/overview` 当一等公民。OpenDerisk 每篇 wiki 各自独立,没有"实体页"聚合多文档。这是"完整内容索引"缺失的根因。

### 缺口 3:两种形态没有抽象——个人 vs Agent 混在一起

hermes 用三态勉强分,storage 层没抽象;mempalace 用 wing 命名约定软分;llmwiki 用 source_kind + path 前缀软分。OpenDerisk 的 `space_id` 是天然隔离边界,但**没有在 space 内区分"人写的知识"和"Agent 写的记忆"**。

---

## 六、设计借鉴与规避清单

### 值得借鉴

| 来源 | 借鉴点 |
|---|---|
| llm_wiki | 两步 CoT ingest;entities/concepts/overview 汇总节点;page-merge 三层合并;4-signal 图扩展;SHA256 增量缓存 |
| llmwiki | 文件系统是真理之源、索引是派生层;写入先落盘再更新索引;写完返回影响面;"写→更新图→lint 兜底"闭环;chunk 同时索引原文+批注 |
| hermes-agent | MemoryProvider 11 个生命周期钩子(尤其 on_pre_compress 压缩前抢救);provenance metadata;`<memory-context>` fence 防递归污染;快照冻结保 prefix cache |
| mempalace | 可插拔后端契约 + PalaceRef 隔离;AAAK 压缩指针索引层;drawer id 确定性 idempotent upsert;实体共现建边(hallway)思想;跨条目同实体归并(tunnel)思想;原子写 + fsync;embedder identity 防静默降级 |

### 必须规避

| 来源 | 规避点 |
|---|---|
| llm_wiki | LLM 读 index 自判规模上限(~100源);图扩展只有 1-hop 无衰减;无时效性 |
| llmwiki | 无向量检索(中文 FTS 弱);跨文档靠文件名匹配会错并;最后写入胜出无版本 |
| hermes-agent | 跨条目关系外包丧失可审计性;单外部 provider 硬限制阻碍组合;多套索引孤岛无单一真相源;本地正则抽取中文失效 |
| mempalace | 三套边模型碎片化无统一图遍历;正则抽取中文失效;单写者锁不适合多 Agent 并发;无 LLM 摘要层(verbatim 限制);drawer 无时效 |

### OpenDerisk 不做(明确边界)

- 不引入图数据库(TuGraph/Neo4j)——实体页 + Edge 表足够
- 不做完整三元组抽取——LLM 实体页已覆盖,成本更低
- 不做社区发现(Louvain/Leiden)——暂不需要
- 不重新集成 mempalace(已确认移除)
- 不动 Document/Verbat dataclass 字段(溯源走 frontmatter/metadata 约定),避免 SQL 迁移成本

---

## 七、解决方向(摘要)

(详细实施计划见 [RFC-005](./rfc-005-cross-doc-relation-and-dual-space.md)。)

1. **形态抽象**:`Space` 加 `space_type` 字段,create_space 按 type 选 schema(personal → `default_schema_md`;agent_memory → `default_memory_schema_md` 启用 merged-into/supersedes/about/relates-to);溯源/时效/置信走 frontmatter/metadata 约定键,不改 dataclass、不动 SQL。两种形态共用同一套 L0/L1/L2 + 检索。

2. **跨文档关联**:ingest 完 wiki 后增加 `_curate_entities` 步骤——LLM 抽关键实体(3-8 个)→ 读 space 现有 entity 页索引 → 判断 已存在/新建/矛盾 → merge/supersede/new。entity 页作为高连通度枢纽,通过 `about` 边连回多份源文档,形成真正跨文档关联。借鉴 llm_wiki 两步 CoT + page-merge,mempalace 的"跨条目同实体归并"思想用 LLM 而非正则实现。

3. **检索召回**:`doc_search` 加 `mode="graph"`(hybrid 种子 → `graph_traverse` 1-hop 经 `about` 边拉实体页邻居);agent_memory space 检索时 valid_to 过期过滤、supersedes 链只返回最新、confidence 降序。