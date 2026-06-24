# RFC 001: 三层数据模型

- **状态**: Draft
- **作者**: Knowledge Team
- **创建日期**: 2026-06-23
- **关联**: llm-wiki.md spec, RFC 002 (VaultFS), RFC 003 (schema.md), RFC 004 (Tool 协议)

## 1. 背景

OpenDerisk 现有 RAG 模块（`derisk-core/rag/` + `derisk-ext/rag/` + `derisk-serve/rag/`）存在以下问题：

1. **L0 缺失**：`document_chunk` 表是派生物不是真相源，原文与派生 chunk 混在同一表里，无法区分不可变原文与可重建索引
2. **L2 不带时效**：`knowledge_space_graph_relation` 表没有 `valid_from/valid_to`，无法表达"边失效"
3. **schema 硬编码**：`ChunkStrategy` 枚举和关系类型都在代码里，用户无法通过编辑配置文件扩展
4. **embedder identity 缺失**：`EmbeddingFactory` 没有 model identity 校验，换 model 会静默失配

本 RFC 定义新的三层数据模型，作为新 `knowledge` 模块的基础契约。

## 2. 设计原则

### 2.1 遵循 llm-wiki.md spec

严格遵守 spec 定义的三件套（`llm-wiki.md:27-33`）：

| spec 层 | 性质 | 本系统层 |
|---|---|---|
| Raw sources（不可变真相源） | 数据层 | L0 Verbatim |
| The wiki（LLM 维护的 markdown） | 数据层 | L1 Document |
| The schema（配置文件） | 配置层 | schema.md |

spec 第 75 行明说「Everything mentioned above is optional and modular」，允许扩展。

### 2.2 扩展点（超出 spec，服务化场景需要）

- **L2 Graph 物化**：spec 没要求，spec 把 graph 当 Obsidian 运行时视图。本系统物化 L2 以支持图遍历 BFS、时效边、4-signal 相关性打分。**约束**：L2 必须可从 L1 重建（`reindex` 命令），不是独立真相源
- **L0 扩展到 agent 对话片段**：spec 的 "Raw sources" 举例是 articles/papers/images，本系统扩展到 `extract_mode="convo"` 的对话片段，作为 agent 短期记忆（替代 mempalace 集成）

### 2.3 三层职责

```
Space (知识空间)
 ├─ schema.md          (配置层，spec 第三件套)
 ├─ purpose.md         (空间目标)
 ├─ L0  Verbatim       (不可变真相源，append-only)
 ├─ L1  Document       (LLM 维护的 markdown，可重建衍生层)
 └─ L2  Graph          (物化图，可从 L1 重建)
```

**L0、L1、L2 的真相性**：
- L0：**真相源**，永不修改永不删除（可标 deprecated），丢不得
- L1：**衍生层**，可由 L0 通过 ingest pipeline 重建
- L2：**衍生层**，可由 L1 通过 `reindex` 命令重建（扫 `[[wikilink]]` + `[^1]` 脚注 + `related` + `sources`）

## 3. L0 Verbatim

### 3.1 数据结构

```python
@dataclass
class Verbat:
    id: VerbatId                     # "v_<ulid>"，全局唯一
    space_id: SpaceId
    source_file: str                 # basename，不泄露绝对路径（学 mempalace）
    source_path: str                 # 完整路径，内部用
    content: str                     # 原文，绝不摘要（verbatim 承诺）
    content_hash: str                # SHA256，去重用
    extract_mode: Literal[
        "mine",        # 项目文件/对话 transcript 主动挖掘
        "clip",        # 浏览器剪藏
        "upload",      # 用户上传
        "convo",       # agent 对话片段（替代 mempalace drawer）
        "legacy_chunk" # 旧 RAG 数据迁移
    ]
    content_date: datetime           # 原文产生时间
    filed_at: datetime               # 入库时间
    source_mtime: int | None         # 原始文件 mtime，用于增量
    normalize_version: int           # 文本归一化版本，便于重建索引
    deprecated: bool = False         # 软删除标记，内容保留
```

### 3.2 约束

- **append-only**：写入后 `content` 永不修改，`content_hash` 用于去重
- **软删除**：`deprecated=True` 仅标记，不物理删除
- **唯一约束**：`UNIQUE(space_id, content_hash)`，同一 space 内相同内容只存一份
- **path 隔离**：返回给 agent 时 `source_path` 截断为 `source_file` basename，防止泄露宿主机绝对路径

### 3.3 来源

| `extract_mode` | 来源 | 触发方式 |
|---|---|---|
| `mine` | 项目代码、文档、PDF | `ingest_trigger` tool / 后台 watcher |
| `clip` | 网页剪藏 | 浏览器扩展 → clip server |
| `upload` | 用户上传 | HTTP API `POST /files/upload` |
| `convo` | agent 对话片段 | Agent 调 `verbatim_add` 主动归档 / `Save to Wiki` 按钮 |
| `legacy_chunk` | 旧 RAG 迁移 | 一次性 `ks-migrate-from-derisk` 脚本 |

## 4. L1 Document

### 4.1 文件结构

```markdown
---
type: entity | concept | source | comparison | synthesis | query | finding | thesis | methodology | <schema.md 自定义>
title: Human-readable title
tags: []
related: []                  # [[wikilink]] 显式关联，指向同 space 其他文档
sources: [v_xxx, v_yyy]      # 指向 L0 的 verbat id，spec 第 125 行要求
confidence: low | medium | high
status: speculative | verified | deprecated
created: 2026-06-23
updated: 2026-06-23
---
# Markdown 正文
[[transformer]] 提出了 attention 机制 [^1]。
[^1]: paper.pdf, p.3
```

### 4.2 Frontmatter 字段规范

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | string | 是 | schema.md `## Page Types` 定义 |
| `title` | string | 是 | 人可读标题 |
| `tags` | string[] | 否 | 扁平标签数组 |
| `related` | string[] | 否 | `[[wikilink]]` 列表，写完解析为 L2 `links_to` 边 |
| `sources` | string[] | 否 | L0 verbat id 列表，L1→L0 指针 |
| `confidence` | enum | 否 | `low` / `medium` / `high` |
| `status` | enum | 否 | `speculative` / `verified` / `deprecated` |
| `created` | date | 是 | YYYY-MM-DD |
| `updated` | date | 是 | YYYY-MM-DD |

### 4.3 路径路由

路径由 `schema.md` 的 `## Page Types` 表驱动：

```markdown
## Page Types
| type | dir | description |
|---|---|---|
| entity | wiki/entities/ | 人/公司/论文/产品 |
| concept | wiki/concepts/ | 抽象概念 |
| source | wiki/sources/ | 源摘要 |
| comparison | wiki/comparisons/ | 对比分析 |
| synthesis | wiki/synthesis/ | 综合分析 |
| query | wiki/queries/ | 保存的问答 |
| finding | wiki/findings/ | 研究发现 |
| thesis | wiki/thesis/ | 论点 |
| methodology | wiki/methodology/ | 方法论 |
```

`type → dir` 映射由 `schema.py` 解析，写入时校验路径必须落在对应目录。**用户编辑 schema.md 即可扩展新 page type，无需改代码**（学 llm_wiki `wiki-schema.ts:27-92`）。

### 4.4 容错解析

LLM 写 frontmatter 经常出错，解析器必须容错（学 llm_wiki `frontmatter.ts:76-130`）：

1. **双策略定位**：先 strict（文件首 `---` 围栏），失败则 anywhere-fallback（扫任意位置的 YAML 块）
2. **wikilink 列表修复**：`repairWikilinkLists` 自动给裸 `[[a]], [[b]]` 列表加引号（YAML 把 `[a, b]` 当 flow sequence，但 LLM 常写成 `[[a]], [[b]]` 不带引号导致解析失败）
3. **YAML 围栏修复**：自动补全缺失的 `---` 结束围栏

### 4.5 特殊文件

| 文件 | 用途 | spec 依据 |
|---|---|---|
| `wiki/index.md` | 内容目录，按 type 分组列出所有页面 | spec 第 47 行 |
| `wiki/log.md` | 追加式时间线，每行 `## [YYYY-MM-DD] ingest\| Title` 便于 grep | spec 第 49 行 |
| `wiki/overview.md` | 全局摘要，LLM 自动维护 | spec 第 31 行 |
| `purpose.md` | 空间目标、关键问题、研究范围 | llm_wiki README |
| `schema.md` | 类型路由、关系类型定义 | spec 第 33 行 |

`log.md` 和 `overview.md` 受保护，`doc_delete` tool 拒绝删除（学 llmwiki `delete` 工具的保护规则）。

## 5. L2 Graph

### 5.1 数据结构

```python
@dataclass
class Edge:
    id: EdgeId                       # "e_<ulid>"
    space_id: SpaceId
    subject: str                     # entity 字符串，如 "transformer"
    predicate: str                   # schema.md ## Relation Types 定义
    object: str                      # entity 字符串
    valid_from: datetime | None      # 边生效时间（学 mempalace KG 时效）
    valid_to: datetime | None        # 边失效时间，NULL = 当前有效
    source_document_id: DocId | None # 指向 L1，证明这条边的出处
    source_verbat_id: VerbatId | None # 可选指向 L0
    weight: float = 1.0              # 4-signal 相关性打分用
    created_at: datetime
```

### 5.2 关系类型

由 `schema.md` `## Relation Types` 定义：

```markdown
## Relation Types
| type | inverse | description |
|---|---|---|
| cites | cited-by | 引用关系 |
| links-to | linked-by | wikilink 关联 |
| depends-on | depends-on | 依赖关系（自反） |
| causes | caused-by | 因果关系 |
| contradicts | contradicts | 矛盾关系（自反） |
| part-of | has-part | 包含关系 |
```

`predicate` 必须在 schema.md 里声明，写入时校验。**关系类型可扩展**——用户编辑 schema.md 即可新增（这是 llm_wiki 没做、llmwiki 硬编码、本系统要做对的点）。

### 5.3 边的来源

| 来源 | 触发 | `source_document_id` | `source_verbat_id` |
|---|---|---|---|
| `[[wikilink]]` 解析 | L1 写入时 | 当前文档 | NULL |
| `[^1]` 脚注解析 | L1 写入时 | 当前文档 | NULL（脚注指向的源文件单独建 verbat） |
| `related: []` frontmatter | L1 写入时 | 当前文档 | NULL |
| `sources: []` frontmatter | L1 写入时 | 当前文档 | 对应 verbat |
| LLM 显式抽取 | ingest Step1 分析 | 生成 L1 时关联 | 可选 |
| 手工 `graph_add_edge` tool | agent 主动调用 | 可选 | 可选 |

### 5.4 时效语义

- **新增边**：`valid_from=now, valid_to=NULL`
- **失效边**：不删除，设 `valid_to=now`（保留历史，可回溯）
- **矛盾检测**：同一 (subject, predicate, object) 出现多条 `valid_to=NULL` 的边时，触发 lint 告警
- **时间线查询**：`graph_timeline(entity)` 返回该 entity 所有边的时序变化

### 5.5 重建算法

`reindex --layer=L2` 命令：

```
1. 清空 edges 表（按 space_id）
2. 遍历所有 L1 document
3. 对每个 document 解析：
   - [[wikilink]] → predicate="links-to"
   - [^N] 脚注 → predicate="cites" + 页码
   - frontmatter related → predicate="links-to"
   - frontmatter sources → predicate="derived-from" + source_verbat_id
4. 写入 edges 表，valid_from=doc.updated, valid_to=NULL
5. 触发 4-signal 相关性重算
```

L2 永远可丢可重建，不是真相源。

## 6. 4-signal 图相关性

检索 Phase 2 图扩展用，打分公式（学 llm_wiki `graph-relevance.ts`）：

| signal | 权重 | 说明 |
|---|---|---|
| 直接链接 | ×3.0 | A 和 B 之间有直接 edge |
| 源重叠 | ×4.0 | A 和 B 的 `sources: []` 有交集 |
| Adamic-Adar | ×1.5 | 共同邻居的 `1/log(degree)` 之和 |
| 类型亲和 | ×1.0 | A 和 B 的 `type` 在亲和矩阵里得分 |

配合 Louvain 社区检测（`graphology` 库）做 cluster boost：同社区节点额外 +0.5。

## 7. Space（知识空间）

### 7.1 数据结构

```python
@dataclass
class Space:
    id: SpaceId                      # "s_<ulid>"
    slug: str                        # URL 友好，全局唯一
    name: str                        # 人可读名称
    description: str
    backend: Literal["local", "distributed"]
    schema_hash: str                 # schema.md 内容 hash，变更时触发 L2 重建
    embedder_model: str | None       # embedder identity
    embedder_dimension: int | None
    embedder_state: Literal["unknown", "known_match", "known_mismatch"]
    visibility: Literal["private", "shared", "public"]
    owner_id: str
    created_at: datetime
    updated_at: datetime
```

### 7.2 隔离

- 本地模式：一个 space = 一个目录 + 一个 SQLite DB（per-space 隔离，**不犯 llmwiki `UNIQUE(user_id)` 单 KB 错误**）
- 分布式模式：一个 space = S3 prefix + Postgres 行级隔离（RLS）

### 7.3 公开分享

`visibility="public"` 的 space 生成只读 URL `/<owner>/<slug>`，无鉴权可访问（学 llmwiki migration 006）。

## 8. 数据库 Schema

### 8.1 SQLite（本地模式）

```sql
-- L0
CREATE TABLE verbats (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_path TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    extract_mode TEXT NOT NULL,
    content_date TEXT,
    filed_at TEXT NOT NULL,
    source_mtime INTEGER,
    normalize_version INTEGER DEFAULT 1,
    deprecated INTEGER DEFAULT 0,
    UNIQUE(space_id, content_hash)
);
CREATE INDEX idx_verbats_space ON verbats(space_id, filed_at);
CREATE INDEX idx_verbats_extract_mode ON verbats(space_id, extract_mode);

-- L1
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    path TEXT NOT NULL,               -- 相对 wiki/ 的路径
    type TEXT NOT NULL,               -- schema.md 定义
    title TEXT NOT NULL,
    frontmatter TEXT,                 -- 原始 YAML
    content TEXT NOT NULL,            -- markdown 正文
    content_hash TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',     -- active | deprecated
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(space_id, path)
);
CREATE INDEX idx_documents_space_type ON documents(space_id, type);
CREATE INDEX idx_documents_updated ON documents(space_id, updated_at);

-- L1 → L0 指针
CREATE TABLE document_sources (
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    verbat_id TEXT NOT NULL REFERENCES verbats(id),
    PRIMARY KEY (document_id, verbat_id)
);

-- L1 chunks（FTS 用，可重建）
CREATE TABLE document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    UNIQUE(document_id, chunk_index)
);

-- L2
CREATE TABLE edges (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,                    -- NULL = 当前有效
    source_document_id TEXT REFERENCES documents(id),
    source_verbat_id TEXT REFERENCES verbats(id),
    weight REAL DEFAULT 1.0,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_edges_subj ON edges(space_id, subject, valid_to);
CREATE INDEX idx_edges_obj ON edges(space_id, object, valid_to);
CREATE INDEX idx_edges_pred ON edges(space_id, predicate);

-- Space 注册
CREATE TABLE spaces (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    backend TEXT NOT NULL,
    schema_hash TEXT,
    embedder_model TEXT,
    embedder_dimension INTEGER,
    embedder_state TEXT DEFAULT 'unknown',
    visibility TEXT DEFAULT 'private',
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    content,
    content='document_chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- 触发器同步 FTS（学 llmwiki schema）
CREATE TRIGGER chunks_fts_insert AFTER INSERT ON document_chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER chunks_fts_delete AFTER DELETE ON document_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER chunks_fts_update AFTER UPDATE ON document_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES('delete', old.rowid, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;
```

### 8.2 Postgres（分布式模式）

表结构相同，差异：
- `chunks_fts` → PGroonga 索引
- 向量列：`document_chunks.embedding vector(384)`（pgvector）
- 行级安全：`CREATE POLICY ... USING (owner_id = current_user_id())`
- 事件：`LISTEN/NOTIFY` 推送文档变更

详细 schema 见 RFC 002。

## 9. 不变性约束

| 层 | 可变 | 可删 | 可重建 |
|---|---|---|---|
| L0 verbatim | ❌ append-only | ❌ 仅 deprecated 标记 | ❌ 真相源 |
| L1 document | ✅ LLM 维护 | ✅（`log.md` / `overview.md` 受保护） | ✅ 从 L0 ingest 重建 |
| L1 chunks | ❌ 衍生 | ✅ | ✅ `reindex --layer=chunks` |
| L2 edges | ✅ valid_to 失效 | ❌ 仅失效不删 | ✅ `reindex --layer=L2` |

## 10. 迁移与兼容

### 10.1 从旧 RAG 迁移

一次性脚本 `ks-migrate-from-derisk`：

```
1. 读 derisk.db 的 knowledge_document + document_chunk + knowledge_space_graph_relation
2. 对每个 knowledge_space：
   a. 创建新 Space
   b. document_chunk.source_content → L0 verbat (extract_mode="legacy_chunk")
   c. 聚合 chunk 拼回 markdown → L1 document (type="source")
   d. knowledge_space_graph_relation → L2 edges (valid_to=NULL)
3. 旧表保留只读，验证一致性后弃用
```

详见 RFC 005（迁移方案）。

### 10.2 与 mempalace 的关系

**完全替换 mempalace**：
- 删除 `derisk-core/storage/memory/` 整个目录
- 删除 `derisk-ext/storage/memory/mempalace_store.py` 等
- 删除 `pyproject.toml` 的 `mempalace>=3.3.0` 依赖
- agent 对话级记忆改走 L0 verbatim（`extract_mode="convo"`）

### 10.3 与 OpenDerisk Resource 系统的关系

保留 `ResourceType.Knowledge` 枚举（`derisk-core/agent/resource/base.py:40`），但替换实现：
- 删除 `derisk-serve/agent/resource/knowledge.py`（`KnowledgeSpaceRetrieverResource`）
- 删除 `derisk-serve/agent/resource/knowledge_pack.py`（`KnowledgePackResource`）
- 新建 `KnowledgeSpaceResource`（见 RFC 004），只声明挂载，不实现检索

## 11. 开放问题

1. **L0 verbatim 是否需要分块**：本 RFC 设计 L0 不分块（原文整块存），检索时按需切。是否需要 L0 chunk 表？倾向不加，先验证检索效果。
2. **L2 是否支持超图（一条边连 >2 个 entity）**：本 RFC 不支持，predicate 只能二元关系。如需超图未来扩展。
3. **schema.md 变更触发 L2 重建策略**：`schema_hash` 变更时自动重建还是手动 `reindex`？倾向手动，避免误操作。

## 12. 验收标准

- [ ] L0 verbatim 写入后 `content` 不可修改，重复内容去重
- [ ] L1 document frontmatter 容错解析通过测试用例（含 LLM 写错的 5 种典型场景）
- [ ] L2 edges 支持 `valid_from/valid_to` 时效查询
- [ ] `reindex --layer=L2` 能从 L1 完整重建 L2
- [ ] schema.md 编辑后新 page type 立即生效，无需改代码
- [ ] embedder identity 状态机三态正确切换，失配时报 `EmbedderIdentityMismatchError`
