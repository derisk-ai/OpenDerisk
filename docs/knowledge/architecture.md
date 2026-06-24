# 知识系统架构与实现总览

- **状态**: 实现 v1（local + distributed 双模式全功能对等）
- **作者**: Knowledge Team
- **最后更新**: 2026-06-24
- **范围**: 把 RFC 001–004 落到代码后的最终态说明，包含整体架构、关键实现逻辑、本地与分布式两种模式的差异

---

## 0. 设计原理（spec 出处）

**本系统的设计原理直接源自 [`llm-wiki.md`](./llm-wiki.md) spec**（拷贝于 `docs/knowledge/llm-wiki.md`，下称"spec"）。spec 描述了一种"LLM 增量维护持久化 wiki"的模式，区别于传统 RAG 的"查询时再发现"。原文第 11 行：

> Instead of just retrieving from raw documents at query time, the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources.

spec 第 27-33 行给出三件套架构（**Raw sources / The wiki / The schema**），本系统的三层模型直接对应：

| spec 层 | 性质 | 本系统对应 |
|---|---|---|
| Raw sources（不可变真相源） | 数据层 | **L0 Verbatim**（`raw/{sources,convos,clips}/`） |
| The wiki（LLM 维护的 markdown） | 数据层 | **L1 Document**（`wiki/<type>/<slug>.md`） |
| The schema（CLAUDE.md / AGENTS.md） | 配置层 | **schema.md**（`<root>/schema.md`，每个 space 一份） |

spec 第 33 行强调 schema 是"key configuration file — it's what makes the LLM a disciplined wiki maintainer rather than a generic chatbot"。本系统把 schema.md 从"给 LLM 读的 prompt"升级为"运行时配置"——`doc_create` 写入时校验 type 必须在 schema.md Page Types 内，`edge_add` 写入时校验 predicate 必须在 Relation Types 内，**用户编辑 schema.md 即可扩展，无需改代码**。

spec 第 75 行明说"Everything mentioned above is optional and modular"，允许扩展。本系统在 spec 三件套基础上做了两项工程化扩展（服务化场景需要）：

1. **L2 Graph 物化**：spec 把 graph 当 Obsidian 运行时视图；本系统物化 L2 以支持 BFS 遍历、时效边、lint。**约束**：L2 必须可从 L1 重建（`reindex(layer="L2")`），不是独立真相源。
2. **L0 扩展到 agent 对话片段**：spec 的 Raw sources 举例是 articles/papers/images；本系统扩展到 `extract_mode="convo"` 的对话片段，作为 agent 短期记忆（替代 mempalace 集成）。

spec 第 15 行的协作姿势"the LLM agent open on one side and Obsidian open on the other"也直接映射到本系统的 Tool 协议：Agent 通过内置 Tool 直接操作 wiki（`doc_create` / `doc_edit` / `edge_add`），前端做"Obsidian 那一侧"的可视化（三视图 + 搜索）。

**spec 没有的、本系统主动做对的工程化决策**（反 llmwiki 反模式）：

| 反模式来源 | 反模式 | 本系统对策 |
|---|---|---|
| llmwiki | `UNIQUE(user_id)` 单 KB（本地模式残废） | RFC 002 conformance 测试强制两 backend 等价 |
| llmwiki | `_db` 全局可变状态 | per-space VaultFS 实例，禁止模块级单例 |
| llmwiki | 关系类型硬编码 `cites` / `links_to` | schema.md `## Relation Types` 用户可扩展 |
| 旧 OpenDerisk RAG | `ChunkStrategy` 枚举硬编码 | schema.md `## Page Types` 驱动 type 路由 |
| 旧 OpenDerisk RAG | `EmbeddingFactory` 无 model identity 校验 | `embedder_identity` 表 + 三态状态机 + `force_swap` |

---

## 1. 概览

OpenDerisk 新知识系统（模块名 `derisk_serve.knowledge` + `derisk_ext.knowledge`）替换了原有四套分叉存储抽象（`derisk-core/rag` + `derisk-ext/rag` + `derisk-serve/rag` + `mempalace`），统一到一套 VaultFS 接口下，本地模式与分布式模式功能对等。

### 1.1 spec 原则到实现的映射

每条 spec 原则在实现层都有落点：

| spec 原则 | spec 行号 | 实现落点 |
|---|---|---|
| "the wiki is a persistent, compounding artifact" | §13 | L1 Document 表 + 版本号 + `reindex(layer="L2")` 重建衍生层 |
| "LLM owns this layer entirely" | §31 | `_generate_wiki` in `ingest.py` —— LLM 写 frontmatter + markdown，调 `vault.doc_create` |
| "Raw sources... immutable" | §29 | `Verbat` 表 `content` 字段永不修改；`deprecated=True` 软删除；`UNIQUE(space_id, content_hash)` 去重 |
| "schema tells the LLM how the wiki is structured" | §33 | `schema.py:parse_schema` 运行时解析；`doc_create` 校验 type；`edge_add` 校验 predicate |
| "I have the LLM agent open on one side and Obsidian open on the other" | §15 | Tool 协议（RFC 004）+ 前端三视图（RawView / WikiView / GraphView） |
| "Ingest... A single source might touch 10-15 wiki pages" | §37 | `IngestOrchestrator._generate_wiki` 一次调用 = 一个 verbat → 一份 L1 doc + 自动建 L2 边（`derived-from` + wikilinks + footnotes） |
| "good answers can be filed back into the wiki as new pages" | §39 | `doc_create` tool + `doc_append_log` tool，agent 可把对话产物固化进 wiki |

### 1.2 模块边界

```
derisk-core/src/derisk/knowledge/         协议层（types / schema 解析 / frontmatter / SQLite schema）
derisk-ext/src/derisk_ext/knowledge/      扩展层（VaultFS 实现 + Tool + Extractor + Embedder factory）
derisk-serve/src/derisk_serve/knowledge/  服务层（Service + API + Ingest + Config）
web/src/components/knowledge-vault/       前端（三视图 + 搜索 + 设置 + Lint）
```

---

## 2. 整体架构

```
┌────────────────────────────────────────────────────────────────────┐
│                   Agent / 前端 / Claude Code / Cursor               │
└─────────────┬───────────────────────────────────┬──────────────────┘
              │ HTTP (/api/v1/serve/knowledge)    │ MCP / 内置 Tool
              ▼                                   ▼
┌─────────────────────────────────┐  ┌──────────────────────────────┐
│  FastAPI endpoints              │  │  ToolRegistry                │
│  (endpoints.py)                │  │  doc_search / doc_create ... │
│  /spaces /wiki /graph /search   │  │  (~20 个 tool，见 §10)        │
└─────────────┬───────────────────┘  └──────────────┬───────────────┘
              │                                      │
              ▼                                      ▼
┌──────────────────────────────────────────────────────────────────┐
│  Service (service.py)                                            │
│  - Vault registry（slug → VaultFS 实例，lazy init + cache）       │
│  - Space config 持久化（local: SQLite spaces 表；distributed:     │
│    registry.json + SQLAlchemy spaces 表）                         │
│  - _make_vault(space) 根据 backend 选 LocalVaultFS / Distributed │
│  - _configure_embedder_hint()：把 space.embedder_model 或         │
│    ServeConfig.default_embedder_model 注入 vault                  │
└─────────────┬────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────┐
│  BaseVaultFS (base.py，ABC)                                      │
│  ─ 高层编排（path 校验 / schema 验证 / event 发布 / write_lock）  │
│  ─ doc_create / doc_edit / doc_search / reindex / edge_add       │
│  ─ 惰性 embedder 身份 provisioning（_ensure_embedder_identity）  │
│  ─ 向量 upsert/query/delete 便捷方法 + 自动 chunk embed 钩子    │
└──────┬──────────────────────────────┬───────────────────────────┘
       │ abstractmethod               │ abstractmethod
       ▼                              ▼
┌──────────────────────┐   ┌──────────────────────────────────────┐
│  LocalVaultFS        │   │  DistributedVaultFS                  │
│  (local.py)          │   │  (distributed.py)                    │
│                      │   │                                      │
│  FS（raw/ + wiki/）  │   │  S3FileStore (files/s3_store.py)     │
│  + SQLite            │   │  + SQLAlchemyRelationalStore         │
│  + LanceDB 向量      │   │    (relational/sqlalchemy_store.py)  │
│  + flock             │   │  + 可插拔向量存储                   │
│  + watchfiles        │   │    (pgvector/milvus/chroma/lance)    │
│                      │   │  + SQLAdvisoryLock (lock/sql_lock)  │
└──────────────────────┘   └──────────────────────────────────────┘
```

### 2.1 三层调用栈

调用栈自上而下，每层职责清晰：

1. **HTTP / Tool 层**：参数解析、鉴权、序列化。HTTP 用 FastAPI，Tool 用 OpenDerisk `ToolBase`。
2. **Service 层**：管理 vault 生命周期（lazy create + cache），把 space 配置注入 vault。
3. **BaseVaultFS 层**：所有 backend 共享的高层逻辑（schema 校验、path normalize、event publish、lock 编排、向量惰性 provisioning）。
4. **具体 backend 层**：实现 `@abstractmethod` 的存储原语（`_doc_insert`、`_chunks_replace_for_doc`、`_edge_insert`、`_make_vector_store` 等）。

---

## 3. 三层数据模型

### 3.1 层级职责

| 层 | 角色 | 可变 | 可删 | 可重建 |
|---|---|---|---|---|
| **L0 Verbatim** | 真相源（不可变原文） | ❌ append-only | ❌ 仅 deprecated | ❌ |
| **L1 Document** | LLM 维护的 markdown | ✅ | ✅（log/overview/schema/purpose 受保护） | ✅ 从 L0 ingest |
| **L1 Chunks** | FTS / 向量派生 | ❌ 衍生 | ✅ | ✅ `reindex --layer=chunks` |
| **L2 Edges** | 物化图（带时效） | ✅ valid_to 失效 | ❌ 仅失效 | ✅ `reindex --layer=L2` |
| **L1 Vectors** | 嵌入向量 | ✅ upsert | ✅ | ✅ `reindex --layer=vectors` |

### 3.2 L0 Verbatim

```python
@dataclass
class Verbat:
    id: VerbatId                # "v_<ulid>"
    space_id: SpaceId
    source_file: str            # basename（防泄露宿主机路径）
    source_path: str            # 完整路径，内部用
    content: str                # 原文，绝不摘要
    content_hash: str           # SHA256，去重 key
    extract_mode: ExtractMode   # mine | clip | upload | convo | legacy_chunk
    content_date: datetime      # 原文产生时间
    filed_at: datetime          # 入库时间
    deprecated: bool = False    # 软删除标记
```

约束：
- `UNIQUE(space_id, content_hash)` — 同 space 内相同内容只存一份，重复 add 返回已有 id
- 写入后 `content` 永不修改
- `deprecated=True` 仅标记；L0 永不物理删除
- 大于 `INLINE_THRESHOLD = 32 KiB` 的 verbat 把 content 落到 FS/S3 blob，DB 只存 `content_ref` 指针（local: `raw/<mode>/<id>.txt`；distributed: `s3://<bucket>/<mode>/<id>`）

### 3.3 L1 Document

```markdown
---
type: concept              # 必须在 schema.md Page Types 声明
title: Attention Mechanism
tags: [transformer]
related: [[transformer]]   # wikilink → L2 links-to edge
sources: [v_01HZ...]       # 指向 L0 verbat
confidence: high
status: verified
created: 2026-06-23
updated: 2026-06-23
---
# Markdown 正文
[[transformer]] 提出 attention [^1]。
[^1]: vaswani2017.pdf, p.3
```

Frontmatter 解析容错（`frontmatter.py:parse_markdown`）：
1. 先 strict（文件首 `---` 围栏）
2. 失败则 anywhere-fallback（扫任意位置的 YAML 块）
3. 自动修复裸 `[[a]], [[b]]` 列表（加引号）
4. 自动补全缺失的结束 `---` 围栏

写入时：
- `type` 必须在 schema.md Page Types 内，否则拒绝
- `[[wikilink]]` / `related` / `[^N]` 脚注 / `sources` 自动解析成 L2 edges
- `sources` 同时写入 `document_sources` 表（L1→L0 指针）

### 3.4 L2 Edge（带时效的物化图）

```python
@dataclass
class Edge:
    id: EdgeId                  # "e_<ulid>"
    subject: str                # entity 字符串
    predicate: str              # schema.md Relation Types 声明
    object: str
    valid_from: datetime        # 边生效
    valid_to: datetime | None   # NULL = 当前有效
    source_document_id: DocId | None   # L1 出处
    source_verbat_id: VerbatId | None  # L0 出处
    weight: float = 1.0
    created_at: datetime
```

边的来源：

| 来源 | predicate | 触发点 |
|---|---|---|
| `[[wikilink]]` 解析 | `links-to` | L1 写入时 |
| `[^N]` 脚注解析 | `cites` | L1 写入时 |
| `related: []` frontmatter | `links-to` | L1 写入时 |
| `sources: []` frontmatter | `derived-from` | L1 写入时 |
| Ingest LLM 抽取 | 自定 | ingest pipeline Step1 |
| 手工 `edge_add` tool | 自定 | agent 主动调用 |

时效语义：
- 新增边：`valid_from=now, valid_to=NULL`
- 失效边：不删除，`valid_to=now`（保留历史可回溯）
- `graph_timeline(entity)` 返回该 entity 时序变化
- 同 `(subject, predicate, object)` 多条 `valid_to=NULL` → lint 报警 `contradiction_detection`

---

## 4. Local 与 Distributed 模式差异

这是用户最关心的视角。两套模式**功能完全等价**（同一份 conformance 测试强制），但底层技术栈完全不同。

### 4.1 存储映射对比

| 数据 | LocalVaultFS | DistributedVaultFS |
|---|---|---|
| L0 verbatim 原文 | FS：`<root>/raw/{sources,convos,clips}/` | S3：`s3://<bucket>/<space_id>/raw/<mode>/<vid>` |
| L1 document markdown | FS：`<root>/wiki/<type>/<slug>.md` | S3：`s3://<bucket>/<space_id>/wiki/<path>` |
| schema.md | FS：`<root>/schema.md` | S3：`s3://<bucket>/<space_id>/schema.md` |
| L0/L1 元数据 + chunks + edges | SQLite：`<root>/.ks/index.db`（WAL） | Postgres / MySQL（per-space 行） |
| 向量 | LanceDB：`<root>/.ks/vectors.lance/` | 4 选 1：pgvector / milvus / chroma / lance-on-S3 |
| Embedder identity | SQLite `embedder_identity` 表 | SQL `embedder_identity` 表 |
| Writer lock | `flock(<root>/.ks/writer.lock)` | `pg_advisory_xact_lock` / MySQL `GET_LOCK` |
| 事件推送 | in-process `asyncio.Queue`（默认） | in-process `asyncio.Queue`（v1；LISTEN/NOTIFY 延后） |
| 文件变更监听 | `watchfiles`（inotify) | ❌ 不支持（S3 Event Notification 延后） |

### 4.2 目录布局

**Local**（每 space 一个目录）：
```
~/.derisk/spaces/<slug>/
├── schema.md               # 配置层
├── purpose.md              # 空间目标
├── raw/
│   ├── sources/            # upload / mine
│   ├── convos/             # extract_mode="convo"
│   └── clips/              # 浏览器剪藏
├── wiki/
│   ├── index.md            # 内容目录（受保护）
│   ├── log.md              # 时间线（受保护）
│   ├── overview.md         # 全局摘要（受保护）
│   ├── entities/
│   ├── concepts/
│   └── ...                 # schema.md 定义的其他 type
└── .ks/                    # 衍生层，可删可重建
    ├── index.db            # SQLite
    ├── vectors.lance/      # LanceDB（仅有向量操作时）
    ├── chats/
    └── writer.lock         # flock
```

**Distributed**（无本地目录，全部托管）：
```
s3://<bucket>/<space_id>/
├── schema.md
├── purpose.md
├── raw/<mode>/<vid>
└── wiki/<path>

Postgres / MySQL（一个 schema 服务所有 space）:
├── spaces                  # 一行 = 一个 space
├── verbats                  # 按 space_id 分区
├── documents
├── document_chunks          # 含 chunk_hash + (PG-only: embedding vector 列)
├── document_sources
├── edges                    # 含 valid_from / valid_to
├── embedder_identity        # 按 space_id
└── ks_vectors_<space_id>   # 仅 pgvector：每 space 独立表

可选：独立向量存储
├── Milvus collection: ks_<space_id_suffix>
├── Chroma collection: ks_vectors_<space_id>
└── LanceDB on S3: s3://<bucket>/knowledge-vectors/<space_id>
```

### 4.3 关键技术点对比

| 维度 | LocalVaultFS | DistributedVaultFS |
|---|---|---|
| 异步 SQLite/SQL 驱动 | `aiosqlite` | `create_async_engine`（asyncpg / asyncmy） |
| 全文索引 | SQLite FTS5（`porter unicode61`，CJK bigram 应用层实现） | Postgres：`ILIKE` + GIN trigram；MySQL：`FULLTEXT` |
| 向量索引 | LanceDB HNSW（Rust 实现，per-space 目录） | pgvector HNSW / Milvus / Chroma / LanceDB-on-S3 |
| 锁粒度 | `flock` 文件锁，进程崩溃自动释放 | `pg_advisory_xact_lock(hash(space_id))`，事务结束自动释放 |
| Schema 升级 | `init_schema()` 跑全 DDL（含 `chunk_hash` migration via PRAGMA） | `SQLAlchemyRelationalStore.init()` idempotent：Postgres `ADD COLUMN IF NOT EXISTS`，MySQL `information_schema.columns` 检查 |
| 文件原子写 | 写到临时文件再 rename | S3 multipart upload |
| 并发读 | SQLite WAL | MVCC |

### 4.4 共享逻辑（两套模式都不重写）

`BaseVaultFS` 把下列高层方法放在共享层，两套模式都不需要重写：

- `verbat_add` / `verbat_get` / `verbat_search` / `verbat_deprecate` — L0 编排
- `doc_create` / `doc_edit` / `doc_read` / `doc_delete` / `doc_search` — L1 编排
- `edge_add` / `edge_invalidate` / `graph_query` / `graph_traverse` / `graph_timeline` — L2 编排
- `reindex(layer)` — 重建 chunks / L2 / vectors
- `vector_upsert` / `vector_query` / `vector_delete` / `vector_upsert_text` / `vector_query_text` — 向量便捷方法
- `set_embedder_identity` / `get_embedder_identity` — embedder 状态机
- `_embed_chunks_for_doc` / `_delete_doc_vectors` — 写/删时的向量钩子
- `_ensure_embedder_identity` — 惰性 embedder provisioning
- `write_lock()` context manager — 跨进程锁编排

子类只需实现存储原语（`_doc_insert`、`_chunks_replace_for_doc`、`_edge_insert`、`_make_vector_store`、`_acquire_distributed_lock` 等）。BaseVaultFS 总共声明约 35 个 `@abstractmethod`，每个 backend 各实现一套。

---

## 5. VaultFS 接口与 BaseVaultFS

### 5.1 类层次

```
VaultFS (Protocol, runtime_checkable)        ← derisk-core/knowledge/vaultfs.py
  ▲
  │ implements
  │
BaseVaultFS (ABC, base.py)                  ← derisk-ext/knowledge/vaultfs/base.py
  ▲
  │ extends
  ├┴───────────────┐
LocalVaultFS      DistributedVaultFS        ← 各自子类
```

### 5.2 BaseVaultFS 关键方法（高层编排）

**L0 Verbatim**：
```python
async def verbat_add(self, v: Verbat) -> VerbatId
async def verbat_get(self, vid: VerbatId) -> Verbat | None
async def verbat_list(self, extract_mode=None, limit=100, offset=0) -> list[Verbat]
async def verbat_search(self, query, limit=10, extract_mode=None) -> list[VerbatHit]
async def verbat_deprecate(self, vid: VerbatId) -> None
```

**L1 Document**：
```python
async def doc_create(self, path, content, frontmatter=None) -> DocId
async def doc_edit(self, path, content) -> None
async def doc_read(self, path) -> Document | None
async def doc_delete(self, path) -> None        # 受保护文件拒绝删除
async def doc_list(self, type=None, limit=100, offset=0) -> list[DocumentMeta]
async def doc_search(self, query, mode="documents", limit=10) -> list[DocHit]
async def doc_append_log(self, entry: str) -> None
```

`doc_search` 4 个 mode：
| mode | 实现 | 用途 |
|---|---|---|
| `documents`（默认） | FTS5 / SQL LIKE | 关键词检索 |
| `references` | L2 edges 反链 | 找引用某 entity 的文档 |
| `semantic` | 向量召回（cosine） | 概念查询 |
| `hybrid` | FTS + 向量 RRF 融合（k=60） | 最佳默认 |

**L2 Graph**：
```python
async def edge_add(self, e: Edge) -> EdgeId
async def edge_invalidate(self, eid, valid_to=None) -> None
async def graph_query(self, entity=None, predicate=None, hop=1, include_invalid=False) -> Subgraph
async def graph_traverse(self, start, hop=2, mode="bfs") -> Subgraph
async def graph_timeline(self, entity) -> list[Edge]
async def graph_backlinks(self, entity) -> list[Edge]
```

**Reindex**：
```python
async def reindex(self, layer="all") -> ReindexReport
# layer ∈ {"chunks", "L2", "vectors", "all"}
# ReindexReport: chunks_built / edges_built / vectors_rebuilt / duration_seconds / errors
```

### 5.3 Write Lock 编排

```python
# base.py
async def acquire_write_lock(self, timeout=30) -> _BaseWriteLock:
    # 1. In-process asyncio.Lock（防同进程并发）
    await asyncio.wait_for(self._async_lock.acquire(), timeout=timeout)
    # 2. Cross-process lock（防多进程并发）
    try:
        handle = await self._acquire_distributed_lock(timeout)  # abstract
    except Exception:
        self._async_lock.release()
        raise
    return _BaseWriteLock(..., release_fn=self._release_distributed_lock)
```

子类实现 `_acquire_distributed_lock`：
- LocalVaultFS：`fcntl.flock(dup_fd, LOCK_EX | LOCK_NB)` + 重试到 timeout
- DistributedVaultFS：`pg_advisory_xact_lock(hash(space_id))` / `GET_LOCK(space_id, timeout)`

### 5.4 事件总线

```python
async def publish_event(self, event: ChangeEvent) -> None:
    for queue in list(self._subscribers):
        queue.put_nowait(event)  # 满了 drop + warning

async def subscribe_events(self, callback) -> Subscription:
    queue = asyncio.Queue(maxsize=1000)
    self._subscribers.add(queue)
    task = asyncio.create_task(_pump(queue, callback))
    return _BaseSubscription(queue, self._subscribers, task)
```

Local 和 Distributed 共用这套 in-process 实现。未来 Distributed 升级到 Postgres `LISTEN/NOTIFY` 时，`publish_event` 会同时 broadcast 到 SQL channel，subscriber 走 SQL LISTEN 而非 in-process queue。

---

## 6. 向量系统（4 种 backend + 惰性 embedder）

向量层是这次 v1 的核心增强。4 种 backend 通过 `VectorStore` Protocol 抽象，按 space 维度可独立选择。

### 6.1 VectorStore Protocol

```python
@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, id: str, embedding: list[float], meta: dict) -> None: ...
    async def query(self, embedding, top_k=10, filter=None) -> list[VectorHit]: ...
    async def delete(self, id: str) -> None: ...
    async def clear(self) -> None: ...
```

`id` 是 caller 决定的稳定 key（本系统用 `doc:{doc_id}:chunk:{hash}`）。

### 6.2 四种实现

| 类 | 模块 | 适用 | 关键技术 |
|---|---|---|---|
| `PgVectorStore` | `pg_vector_store.py` | Distributed（Postgres 集群） | asyncpg + pgvector + HNSW (`vector_cosine_ops`)，per-space 独立表 `ks_vectors_<space_id>` |
| `MilvusVectorStore` | `vector_milvus.py` | Distributed（Milvus 集群） | pymilvus + HNSW，per-space collection `ks_<space_id>` |
| `ChromaVectorStore` | `vector_chroma.py` | Distributed（Chroma server） | chromadb HttpClient（强制 server 模式，禁止 embedded） |
| `LanceVectorStore` | `vector_lancedb.py` | Local | LanceDB Rust binding，per-space `.ks/vectors.lance/` 目录 |
| `LanceS3VectorStore` | `vector_lance_s3.py` | Distributed（共享 Lance on S3） | LanceDB + S3 backing，多进程共享同一 vector set |

LocalVaultFS 用 LanceVectorStore；DistributedVaultFS 在 `_make_vector_store` 里按 `vector_store_config["type"]` 派发到 4 种之一。

### 6.3 惰性 Embedder 身份（lazy provisioning）

每个 space 有一个 `embedder_identity` 记录，存 `model_name / dimension / state / updated_at`。`state` 三态：

| state | 含义 | 进入条件 |
|---|---|---|
| `KNOWN_MATCH` | 当前 embedder 与存储一致 | 首次 set / 匹配的 set |
| `KNOWN_MISMATCH` | 检测到不一致，需 force_swap | 不匹配的 set（force_swap=False） |
| `UNKNOWN` | 从未设置（初始） | 表无记录 |

**懒加载流程**（`BaseVaultFS._ensure_embedder_identity`）：

```
首次向量操作（doc_create / doc_edit）触发：
  1. 读 embedder_identity
  2. 若 KNOWN_MATCH → 返回缓存 embedder，结束
  3. 若无记录：
     a. 读 hint（space.embedder_model or ServeConfig.default_embedder_model）
     b. 若 hint 空 → 返回 None（向量 ops 跳过，FTS 仍工作）
     c. 若 hint 有值：
        - 用 hint 实例化 embedder
        - embed "dimension probe" 探测维度（一次 embed 调用）
        - set_embedder_identity(model=hint, dimension=dim)
        - 写入 KNOWN_MATCH，返回 embedder
  4. 若 KNOWN_MISMATCH → 警告 + 返回 None（需 admin 调 force_swap）
```

**强制切换**（admin 调 `set_embedder_identity(force_swap=True)`）：
```
1. 校验 admin 上下文
2. UPSERT embedder_identity 为新 model + KNOWN_MATCH
3. self._vector_store.clear()  # 清空所有旧向量
4. self._vector_store = None   # 强制下次重新构造（dimension 可能变）
5. 触发 reindex(layer="vectors") 由 admin 显式调用
```

### 6.4 Chunk 切分 + 稳定向量 ID

`chunk_text(text, max_chars=2000) -> list[tuple[int, str, str]]` 返回 `(chunk_index, chunk_text, content_hash)`，其中 `content_hash = sha256(chunk_text)[:16]`。

向量 ID 规则：`doc:{doc_id}:chunk:{content_hash}` — **稳定跨 re-chunk**：
- 编辑文档追加一段 → 老段落 hash 不变 → 老向量 ID 不变 → upsert 幂等
- 编辑文档改一段 → 那段 hash 变 → 老向量 stale（但 `doc_delete` 时按 hash 清理也会带走）

`document_chunks` 表加 `chunk_hash` 列（含 dialect-aware migration：Postgres `ADD COLUMN IF NOT EXISTS`，MySQL `INFORMATION_SCHEMA` check，SQLite `PRAGMA table_info`）。

### 6.5 写入 / 删除 / 重建钩子

**写入**（`doc_create` / `doc_edit`）：
```python
async with self.write_lock():
    await self._wiki_write(norm_path, raw_md)
    await self._doc_insert(...)               # L1 元数据
    await self._chunks_replace_for_doc(doc_id, body)   # L1 chunks → FTS
    await self._doc_invalidate_edges(doc_id, now_iso)   # 老 L2 失效
    await self._rebuild_doc_edges(doc_id, fm, body)     # 新 L2 入库
    await self._embed_chunks_for_doc(doc_id, norm_path, body)  # 向量（best-effort）
```

`_embed_chunks_for_doc` 的 best-effort 语义：
- 没 embedder → 跳过（FTS 仍工作）
- embedder 失败 → log warning + 跳过
- 某个 chunk embed 失败 → log warning + 停止 embed 该 doc 的其余 chunks（systemic error）

**删除**（`doc_delete`）：
```python
async with self.write_lock():
    chunk_hashes = await self._doc_list_chunk_hashes(doc_id)  # 先抓 hash
    await self._wiki_delete(norm_path)
    await self._doc_invalidate_edges(doc_id, now_iso)
    await self._doc_delete_row(doc_id)
    await self._delete_doc_vectors(doc_id, chunk_hashes)  # best-effort 清向量
```

**重建**（`reindex(layer="vectors")`）：
```python
async def _reindex_vectors(self, report):
    store = await self._get_vector_store()
    await store.clear()                       # 清空
    self._vector_store = None                 # 重建实例
    docs = await self.doc_list(limit=10000)
    for meta in docs:
        doc = await self.doc_read(meta.path)
        await self._embed_chunks_for_doc(doc.id, doc.path, doc.content)
        report.vectors_rebuilt += 1
```

### 6.6 Hybrid 检索（RRF 融合）

```python
async def _doc_search_hybrid(self, query, limit):
    fts_hits, sem_hits = await asyncio.gather(
        self._doc_search_documents(query, limit * 2),
        self._doc_search_semantic(query, limit * 2),
        return_exceptions=True,
    )
    # 容错：FTS 或向量任一失败，用空 list 退化

    rrf_k = 60
    scores = {}
    for rank, h in enumerate(fts_hits):
        scores[h.document_id] += 1.0 / (rrf_k + rank)
    for rank, h in enumerate(sem_hits):
        scores[h.document_id] += 1.0 / (rrf_k + rank)
    # 排序、limit、构造 DocHit
```

---

## 7. Schema.md 驱动层

### 7.1 文件结构

```markdown
# <Space Name> Schema

## Purpose
<自由文本：空间目标、关键问题、研究范围>

## Page Types
| type | dir | description |
|---|---|---|
| entity | wiki/entities/ | 人/组织/产品/论文 |
| concept | wiki/concepts/ | 抽象概念 |
| ... | ... | ... |

## Relation Types
| type | inverse | description |
|---|---|---|
| cites | cited-by | 引用关系 |
| links-to | linked-by | wikilink 关联 |
| depends-on | depends-on | 依赖关系（自反） |
| ... | ... | ... |

## Ingest Workflow
<自由文本：ingest 流程描述，注入 LLM prompt>

## Lint Rules
- orphan_pages: true
- stale_edges: true
- contradiction_detection: true
- uncited_sources: true
- dangling_links: true
- frontmatter_required: [type, title, created, updated]
```

### 7.2 解析与校验（`schema.py`）

- `parse_schema(content) -> Schema`：容错，缺失 `## Page Types` 用默认 9 种，缺失 `## Relation Types` 用默认 7 种
- `validate_predicate(schema, predicate)`：`edge_add` 时校验 predicate 必须在 Relation Types 内
- `route_path(schema, page_type, slug)`：根据 page type 路由到 `wiki/<dir>/<slug>.md`
- 5s TTL 缓存，key 是 `raw_hash`，schema.md 改了缓存自动失效

### 7.3 用户扩展流程（无需改代码）

新增 page type：
1. 编辑 schema.md 在 `## Page Types` 加一行
2. 下次 `doc_create(type="new_type", ...)` 立即生效

新增 relation type：
1. 编辑 schema.md 在 `## Relation Types` 加一行
2. 下次 `edge_add(predicate="new_rel", ...)` 立即生效

---

## 8. Ingest Pipeline

### 8.1 Pipeline 步骤（`ingest.py:IngestOrchestrator`）

```
HTTP POST /spaces/{slug}/files (multipart)
  ↓
endpoints.upload_file()
  - 保存到 temp 文件
  - 调 orchestrator.ingest_file(space, vault, file_path, ...)
  - 立即返回 {job_id, verbat_ids: [], wiki_doc_ids: []}（异步）
  ↓
_run_pipeline (background asyncio.Task):
  1. 检测 MIME（mimetypes + 扩展名 fallback）
  2. 从 ExtractorRegistry 取 extractor（按 mime glob 匹配）
  3. 解析 model：caller override → space.{llm,multimodal}_model → ModelConfigCache default
  4. extractor.extract(path, mime, model, model_caller) → list[VerbatimSpec]
  5. 对每个 spec 调 vault.verbat_add(Verbat.create(...))
     - 按 content_hash 去重，已存在返回旧 id
  6. 对每个新 verbat：_generate_wiki(space, vault, verbat_id)
  7. 全部完成后更新 job.status="done"
  8. 失败任一阶段：job.status="failed", error=str(e)
```

### 8.2 Extractor 协议

```python
@runtime_checkable
class Extractor(Protocol):
    name: str
    mime_patterns: list[str]   # glob：["application/pdf"] 或 ["image/*"]
    async def extract(self, path, mime, model, model_caller) -> list[VerbatimSpec]: ...
```

`@extractor(name, mime_patterns)` 类装饰器注册到全局 registry。`registry_init.py:register_builtin_extractors()` 在 Service 启动时注册内置 extractor：

| name | mime_patterns | 用途 |
|---|---|---|
| `text` | `text/*`, `application/json`, `application/x-yaml`, `application/xml` | UTF-8 直读 |
| `pdf` | `application/pdf` | pdfplumber（页分隔） |
| `docx` | `application/vnd.openxmlformats-...wordprocessingml` | python-docx |
| `pptx` | `application/vnd.openxmlformats-...presentationml` | python-pptx |
| `image` | `image/*`, `image/webp` | model_caller 调多模态模型描述 |
| `audio` | `audio/*` | model_caller 调 Whisper 或类似 |

重 deps（pdfplumber / python-docx / python-pptx）按需 lazy import，模块本体 import 不挂。

### 8.3 Wiki 生成（Option A：one-shot LLM）

```
_generate_wiki(space, vault, verbat_id):
  1. verbat = vault.verbat_get(verbat_id)
  2. 查现有 doc 是否 source_verbat=<id>（幂等）
     - 存在且 force_rebuild=False → skip
     - 存在且 force_rebuild=True → vault.doc_delete(old_path)
  3. 读 schema.md，列出 page types 给 LLM
  4. system_prompt = WIKI_SYSTEM_PROMPT（要求输出 frontmatter + markdown）
  5. user_prompt = verbatim content[:12000]
  6. _call_llm(model, system, user) → markdown
  7. _ensure_frontmatter：保证 source_verbat 字段在
  8. vault.doc_create(path="sources/<slug>.md", content=markdown)
  9. vault.edge_add(subject=doc_id, predicate="derived-from", object=verbat_id)
```

LLM 调用走 `AIWrapper` + `ModelConfigCache`（OpenDerisk Agent 系统标准路径），支持多模态（图/音）。

---

## 9. 服务层与 API

### 9.1 Service（`service.py`）

`Service(BaseComponent)` 一个实例管所有 space。核心职责：

**Vault registry**（slug → VaultFS，lazy + cache）：
```python
async def get_vault(self, slug: str) -> VaultFS:
    if slug in self._vaults:
        return self._vaults[slug]
    reg = self._registry_lookup(slug)   # JSON registry 文件
    if reg and reg.get("backend") == "distributed":
        space = Space(backend="distributed", ...)
    else:
        space = Space(backend="local", ...)
    vault = self._make_vault(space)
    await vault.initialize()
    self._vaults[slug] = vault
    return vault
```

**Backend 选择**（`_make_vault`）：
- `space.backend == "distributed"` → DistributedVaultFS
- 否则 → LocalVaultFS

**Embedder hint 注入**（`_configure_embedder_hint`）：
```python
hint = space.embedder_model or self._serve_config.default_embedder_model
vault.configure_embedder_hint(hint, system_app=self._system_app)
```
vault 第一次做向量 op 时读这个 hint 懒初始化 embedder_identity。

**Distributed 配置解析**（`_resolve_distributed_config`）：
- `relational_dsn`：从 `[service.web.database]` 取，sync 驱动自动翻译成 async（`mysql+pymysql` → `mysql+asyncmy`，`postgresql+psycopg2` → `postgresql+asyncpg`）
- `vector_store_config`：按 `vector_store_type` 构造 dict
  - `pgvector`：dsn 默认复用 relational_dsn（单 DB 模式），可显式 split
  - `milvus`：`{type, uri, collection_prefix}`
  - `chroma`：`{type, uri}`（强制 HTTP server，禁 embedded）
  - `lance`：`{type, s3_uri}`
- `s3_bucket`：`[knowledge.distributed] s3_bucket` → fallback `ServeConfig.uploads_bucket`

**Space 注册表**：
- Local：扫描 `~/.derisk/spaces/<slug>/` 目录（启发式：含 `schema.md` 或 `.ks/` 即视为 space）
- Distributed：`<local_root>/registry.json` 记录所有分布式 space 元数据

### 9.2 HTTP API（`endpoints.py`）

挂载于 `/api/v1/serve/knowledge`。

| Endpoint | 方法 | 用途 |
|---|---|---|
| `/spaces` | GET | 列出所有 space（local 扫盘 + distributed 查 registry.json） |
| `/spaces` | POST | 创建 space（local 直接建目录；distributed 写 registry + 校验配置） |
| `/spaces/{slug}` | PATCH | 改 space 配置（agent / LLM / embedder model） |
| `/spaces/{slug}/raw/tree` | GET | L0 文件树（depth=2） |
| `/spaces/{slug}/verbats` | GET | L0 verbat 列表（分页） |
| `/spaces/{slug}/verbats/{vid}` | GET / DELETE | 读/软删 verbat |
| `/spaces/{slug}/files` | POST | 上传文件 → ingest pipeline（异步） |
| `/spaces/{slug}/verbats/{vid}/rebuild-wiki` | POST | 重生成单 verbat 的 wiki |
| `/spaces/{slug}/rebuild-wiki` | POST | 重生成所有 verbats 的 wiki |
| `/spaces/{slug}/ingest-jobs` | GET | ingest job 列表（状态轮询） |
| `/spaces/{slug}/wiki/tree` | GET | L1 文件树（depth=3） |
| `/spaces/{slug}/docs` | GET | L1 doc 列表（分页） |
| `/spaces/{slug}/docs/read` | GET | 读单个 doc（path 参数） |
| `/spaces/{slug}/docs` | POST | doc_create |
| `/spaces/{slug}/docs` | PUT | doc_edit |
| `/spaces/{slug}/search` | POST | doc_search（4 mode） |
| `/spaces/{slug}/graph` | GET | L2 子图查询 |
| `/spaces/{slug}/graph/traverse` | GET | L2 BFS 遍历 |
| `/spaces/{slug}/graph/backlinks` | GET | L2 反链 |
| `/spaces/{slug}/schema` | GET / PUT | schema.md 读/写 |
| `/spaces/{slug}/lint` | GET | 结构 lint（orphan / broken wikilink / uncited） |
| `/spaces/{slug}/embedder-identity` | POST | 强制 set embedder identity（admin） |

---

## 10. Agent 内置 Tool 协议（RFC 004）

### 10.1 三层职责

```
Agent
  ├─ Resources（声明挂载哪些 space）
  │    └─ KnowledgeSpaceResource(space_slug="risk-wiki")
  │         携带 space 上下文 + schema.md 摘要 → 注入 LLM prompt
  └─ Tools（操作挂载的 resource）
       ├─ doc_search / doc_read / doc_create / doc_edit / doc_delete
       ├─ graph_query / graph_traverse / graph_add_edge
       ├─ verbatim_add / verbatim_get / verbatim_search
       └─ space_status / reindex
```

### 10.2 Tool 列表（按层分组）

| Tool | 风险 | 用途 |
|---|---|---|
| **L0** | | |
| `verbatim_add` | LOW | Agent 主动归档对话片段 |
| `verbatim_get` | SAFE | 读 verbat 原文 |
| `verbatim_search` | SAFE | FTS 搜 verbat |
| **L1** | | |
| `doc_create` | MEDIUM | 新建文档（type 校验、向量 embed） |
| `doc_edit` | MEDIUM | 编辑文档（version 自增、L2 重建、向量重 embed） |
| `doc_read` | SAFE | 读文档 |
| `doc_delete` | HIGH | 删文档（log/overview 等受保护拒删） |
| `doc_list` | SAFE | 列文档 |
| `doc_search` | SAFE | 4 mode 搜文档 |
| `doc_append_log` | LOW | 追加 log.md 条目 |
| **L2** | | |
| `graph_query` | SAFE | 查询子图 |
| `graph_traverse` | SAFE | BFS 遍历 |
| `graph_add_edge` | MEDIUM | 新增边（predicate 校验） |
| `graph_backlinks` | SAFE | 反链 |
| **Admin** | | |
| `set_embedder_identity` | HIGH | 强制切 embedder（force_swap 清向量） |
| `reindex` | HIGH | 重建衍生层 |

所有 Tool 返回结构化 JSON，不返 markdown 文本（避免 LLM 在结构化调用里夹带 markdown 解释性文字，保持 tool 调用边界清晰）。

### 10.3 鉴权矩阵

| 调用方 | space_slug 来源 | 鉴权 |
|---|---|---|
| 内置 Tool（OpenDerisk Agent） | tool 参数 | 校验 slug 在 Agent 挂载的 `KnowledgeSpaceResource` 列表 |
| HTTP API（Web UI） | URL path `/spaces/{slug}` | OpenDerisk JWT |
| MCP stdio（单 space） | 启动 `--space` 指定 | 进程级隔离，无需运行时鉴权 |
| MCP HTTP（多 space） | tool 参数 | MCP server token + ACL |

---

## 11. 配置参考

### 11.1 Local 模式（最小配置）

```toml
[derisk.serve.knowledge]
local_root = "~/.derisk/spaces"
default_backend = "local"
default_embedder_model = "text-embedding-3-small"   # 可选；空 = 向量 ops 关闭
uploads_bucket = "knowledge-uploads"                # FileStorageClient 默认 bucket
```

### 11.2 Distributed 模式（pgvector 单 DB）

```toml
[service.web.database]
type = "postgresql"
driver = "psycopg2"
host = "localhost"
port = 5432
user = "derisk"
password = "..."
database = "derisk"

[derisk.serve.knowledge]
default_backend = "distributed"
default_embedder_model = "text-embedding-3-small"
uploads_bucket = "derisk-knowledge"

[derisk.serve.knowledge.distributed]
enabled = true
vector_store_type = "pgvector"        # 默认；vector_dsn 空 = 复用 relational
s3_bucket = ""                        # 空 = 复用 uploads_bucket
```

Postgres 集群需先建扩展：`CREATE EXTENSION IF NOT EXISTS vector;`

### 11.3 Distributed 模式（MySQL relational + Postgres pgvector 分离）

```toml
[service.web.database]
type = "mysql"
driver = "pymysql"
host = "..."
port = 3306

[derisk.serve.knowledge.distributed]
enabled = true
vector_store_type = "pgvector"
vector_dsn = "postgresql+asyncpg://user:pwd@pg-host:5432/derisk_vec"
```

### 11.4 Distributed 模式（Milvus 向量）

```toml
[derisk.serve.knowledge.distributed]
enabled = true
vector_store_type = "milvus"
milvus_uri = "localhost:19530"
milvus_collection_prefix = "ks_"
```

### 11.5 Distributed 模式（Chroma / Lance）

```toml
# chroma
[derisk.serve.knowledge.distributed]
enabled = true
vector_store_type = "chroma"
chroma_uri = "http://localhost:8000"   # 必须 server 模式，禁 embedded

# lance（S3 backing，多进程共享）
[derisk.serve.knowledge.distributed]
enabled = true
vector_store_type = "lance"
lance_s3_uri = "s3://derisk-vectors/knowledge"
```

---

## 12. 测试策略

### 12.1 Conformance 测试（强制两 backend 对等）

`packages/derisk-ext/tests/knowledge/vaultfs/conformance.py` 定义约 30 个测试，LocalVaultFS 和 DistributedVaultFS **必须全部通过**。覆盖：

- L0：dedup、immutable、deprecate、search by extract_mode
- L1：frontmatter 容错、edit 重建 L2、delete 受保护文件、4 mode search
- L2：edge valid_from/to、invalidate 保留历史、BFS traverse、timeline、从 L1 重建
- 横切：vector upsert/query、write_lock 互斥、event publish/subscribe、embedder identity mismatch 报错、force_swap 清向量

### 12.2 Local 单元测试

`tests/knowledge/vaultfs/test_local_*.py` — 不需外部依赖（SQLite + 临时 FS + LanceDB），CI 默认跑。

### 12.3 Distributed 集成测试（skipped without env vars）

`tests/knowledge/vaultfs/test_distributed_conformance.py` 和 `test_vector_lifecycle.py` — 需要真实 Postgres + pgvector + S3。本地无 env vars 时 skip，CI 矩阵里跑：

```bash
KNOWLEDGE_RELATIONAL_DSN=postgresql+asyncpg://... \
KNOWLEDGE_VECTOR_DSN=postgresql+asyncpg://... \
KNOWLEDGE_S3_BUCKET=derisk-test \
KNOWLEDGE_EMBEDDER_MODEL=text-embedding-3-small \
pytest packages/derisk-ext/tests/knowledge/vaultfs/test_vector_lifecycle.py
```

### 12.4 向量生命周期测试（`test_vector_lifecycle.py`）

6 个测试覆盖完整向量 wiring：

1. `test_doc_create_writes_vectors` — doc_create 后向量入库
2. `test_semantic_search_returns_doc` — `doc_search(mode="semantic")` 命中
3. `test_hybrid_search_fuses_results` — `doc_search(mode="hybrid")` RRF 融合命中
4. `test_doc_delete_removes_vectors` — doc_delete 清向量
5. `test_reindex_vectors_rebuilds` — `reindex(layer="vectors")` 重建
6. `test_doc_edit_keeps_stable_vector_ids` — 编辑后未变 chunk 仍可搜

### 12.5 当前测试状态

```
pytest packages/derisk-ext/tests/knowledge/ -q
→ 39 passed, 17 skipped（6 向量 + 11 distributed conformance，本地无 env vars 时 skip）
```

前端：`cd web && npx tsc --noEmit` — knowledge-vault 相关无 type 错误。

---

## 13. 关键文件清单

### 13.1 后端

**协议层（derisk-core）**：
- `src/derisk/knowledge/types.py` — Verbat / Document / Edge / DocHit / EmbedderIdentity / ReindexReport 等数据类
- `src/derisk/knowledge/schema.py` — schema.md 解析与校验
- `src/derisk/knowledge/schema_sql.py` — SQLite DDL + chunk_hash migration
- `src/derisk/knowledge/frontmatter.py` — 容错 frontmatter / wikilink / footnote 解析
- `src/derisk/knowledge/vaultfs.py` — VaultFS Protocol

**扩展层（derisk-ext）**：
- `src/derisk_ext/knowledge/vaultfs/base.py` — BaseVaultFS（共享编排，~1200 行）
- `src/derisk_ext/knowledge/vaultfs/local.py` — LocalVaultFS
- `src/derisk_ext/knowledge/vaultfs/distributed.py` — DistributedVaultFS
- `src/derisk_ext/knowledge/vaultfs/_util.py` — chunk_text + path 工具
- `src/derisk_ext/knowledge/vaultfs/vector_store.py` — VectorStore Protocol
- `src/derisk_ext/knowledge/vaultfs/pg_vector_store.py` — pgvector adapter
- `src/derisk_ext/knowledge/vaultfs/vector_milvus.py` — Milvus adapter
- `src/derisk_ext/knowledge/vaultfs/vector_chroma.py` — Chroma adapter
- `src/derisk_ext/knowledge/vaultfs/vector_lancedb.py` — Local LanceDB adapter
- `src/derisk_ext/knowledge/vaultfs/vector_lance_s3.py` — Lance on S3 adapter
- `src/derisk_ext/knowledge/vaultfs/relational/sqlalchemy_store.py` — Postgres/MySQL relational store
- `src/derisk_ext/knowledge/vaultfs/files/s3_store.py` — S3 blob store
- `src/derisk_ext/knowledge/vaultfs/lock/sql_lock.py` — SQL advisory lock
- `src/derisk_ext/knowledge/extractors/__init__.py` — Extractor Protocol + Registry
- `src/derisk_ext/knowledge/extractors/builtin.py` — text/pdf/docx/pptx/image/audio
- `src/derisk_ext/knowledge/embedder_factory.py` — EmbedderCache + get_embedder
- `src/derisk_ext/knowledge/tools/{l0,l1,l2,admin,space,base}.py` — Agent tools

**服务层（derisk-serve）**：
- `src/derisk_serve/knowledge/config.py` — ServeConfig + DistributedConfig
- `src/derisk_serve/knowledge/service/service.py` — Service（registry + _make_vault + embedder hint）
- `src/derisk_serve/knowledge/api/endpoints.py` — FastAPI router
- `src/derisk_serve/knowledge/api/schemas.py` — Pydantic schemas
- `src/derisk_serve/knowledge/ingest.py` — IngestOrchestrator

### 13.2 前端

- `web/src/types/knowledge-vault.ts` — TypeScript 类型
- `web/src/client/api/knowledge-vault/index.ts` — API client
- `web/src/components/knowledge-vault/RawView.tsx` — L0 视图（drag-drop 上传 + rebuild）
- `web/src/components/knowledge-vault/WikiView.tsx` — L1 视图（编辑 + 搜索 UI 含 4 mode）
- `web/src/components/knowledge-vault/GraphView.tsx` — L2 视图
- `web/src/components/knowledge-vault/SchemaEditor.tsx` — schema.md 编辑器
- `web/src/components/knowledge-vault/SpaceSettings.tsx` — 空间配置
- `web/src/components/knowledge-vault/LintView.tsx` — Lint 报告

### 13.3 测试

- `packages/derisk-ext/tests/knowledge/vaultfs/test_local.py` — LocalVaultFS 单元
- `packages/derisk-ext/tests/knowledge/vaultfs/test_conformance.py` — 两 backend 共享 conformance
- `packages/derisk-ext/tests/knowledge/vaultfs/test_distributed_conformance.py` — Distributed 集成（skip without env）
- `packages/derisk-ext/tests/knowledge/vaultfs/test_vector_lifecycle.py` — 向量全生命周期（skip without env）

---

## 14. 已知边界与未来工作

### 14.1 当前 v1 未做

- **跨 space 向量搜索**：向量按 space 分表/分 collection，跨 space query 未实现
- **LLM rerank**：hybrid 仅用 RRF，未接 rerank 模型（spec 让 qmd 外部做 rerank）
- **L0 verbatim 向量**：按设计决定 L0 不 embed，只走 FTS（`verbat_search`）
- **Postgres LISTEN/NOTIFY**：Distributed 事件用 in-process queue，未跨进程推送
- **S3 Event Notification**：Distributed 不支持 `watch_changes`（文件外部修改感知）
- **多区域 / 多活**：MVP 单区域
- **AGE 图扩展**：未引入 Postgres 图库，L2 走关系表 + 应用层 BFS
- **Streaming ingest**：embed 同步发生在 doc_create 内，大 doc 有延迟
- **从旧 derisk.db 迁移脚本**：Task #3 仍 pending

### 14.2 待观察的开放问题

- **schema.md 变更触发 L2 自动重建**：当前 `schema_hash` 记录但未自动触发 reindex，需 admin 手工调
- **L0 chunk 表**：当前 L0 不分块，大 verbatim 检索时整块 LIKE 扫描；先观察再决定是否加
- **超图**：predicate 仅支持二元关系，未来如需一条边连 >2 entity 再扩
- **MCP server**：RFC 004 §5 设计完整，stdio + HTTP loopback 双形态，待实现
- **Tool 调用审计**：未记录到 `rag_span` 表，可观测性延后

---

## 15. 快速验证清单

启动开发环境后，按顺序跑一遍验证：

```bash
# 1. Local 单元测试（不需外部依赖）
pytest packages/derisk-ext/tests/knowledge/vaultfs/test_local.py -v

# 2. Conformance（LocalVaultFS + 内存仓库）
pytest packages/derisk-ext/tests/knowledge/vaultfs/test_conformance.py -v

# 3. 前端类型检查
cd web && npx tsc --noEmit

# 4. 启动 backend（配置好 ~/.derisk.toml）
python packages/derisk-app/src/derisk_app/dbgpts_cli.py webserver start

# 5. 起前端
cd web && pnpm dev

# 6. 浏览器手动 smoke：
#    - 创建 local space（勾选 backend=local）
#    - 上传一个 PDF → 看 ingest job 进度
#    - 等 done 后在 WikiView 看生成的 markdown
#    - 在搜索栏 mode=hybrid 搜关键词
#    - 在 GraphView 输入 entity 看子图
```

Distributed smoke（需配好 Postgres + pgvector + S3）：
```bash
# 起一个分布式 space（Postgres + pgvector + S3 bucket）
curl -X POST localhost:7777/api/v1/serve/knowledge/spaces \
  -H 'Content-Type: application/json' \
  -d '{"slug":"risk-dist","backend":"distributed","embedder_model":"text-embedding-3-small"}'

# 上传文件
curl -X POST localhost:7777/api/v1/serve/knowledge/spaces/risk-dist/files \
  -F 'file=@paper.pdf' -F 'extract_mode=upload'

# 等 done 后查询 pgvector
psql -d derisk -c "SELECT id, document_id FROM ks_vectors_<space_id> LIMIT 10;"

# Hybrid 搜索
curl -X POST localhost:7777/api/v1/serve/knowledge/spaces/risk-dist/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"attention mechanism","mode":"hybrid","limit":10}'
```

---

## 16. 相关文档

| 文档 | 角色 |
|---|---|
| [`llm-wiki.md`](./llm-wiki.md) | **本系统的设计原理源头** —— spec 描述的"LLM 增量维护持久化 wiki"模式，三层架构（Raw sources / The wiki / The schema）即本系统 L0/L1/schema.md 的直接来源 |
| [`rfc-001-three-layer-data-model.md`](./rfc-001-three-layer-data-model.md) | 三层数据模型 RFC（L0 Verbatim / L1 Document / L2 Graph 数据结构、约束、SQL schema） |
| [`rfc-002-vaultfs.md`](./rfc-002-vaultfs.md) | VaultFS 统一存储抽象 RFC（Protocol 定义、Local/Distributed 两实现、conformance 测试要求） |
| [`rfc-003-schema-md.md`](./rfc-003-schema-md.md) | schema.md 规范 RFC（Page Types / Relation Types / Lint Rules、解析器、扩展流程） |
| [`rfc-004-tool-protocol.md`](./rfc-004-tool-protocol.md) | Tool 协议 RFC（KnowledgeSpaceResource、20 个内置 Tool、MCP 接入、鉴权矩阵） |
| **本文档** | 把上述 RFC 落地到代码后的最终态说明 —— 架构、实现逻辑、Local vs Distributed 差异 |

**阅读顺序建议**：先读 [`llm-wiki.md`](./llm-wiki.md) 理解原始模式 → 再读本文档 §0 理解 spec 到实现的映射 → 再按需查 RFC 001-004 的细节。
