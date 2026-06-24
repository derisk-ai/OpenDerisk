# RFC 002: VaultFS 统一存储抽象

- **状态**: Draft
- **作者**: Knowledge Team
- **创建日期**: 2026-06-23
- **关联**: RFC 001 (三层数据模型), RFC 003 (schema.md)

## 1. 背景

OpenDerisk 现有四套独立存储抽象（`derisk-core/storage/vector_store/base.py` + `full_text/base.py` + `graph_store/base.py` + `memory/base.py`），各自为政，本地模式与托管模式功能不对等（llmwiki 的 `UNIQUE(user_id)` 单 KB 反模式）。

本 RFC 定义统一 `VaultFS` 接口，覆盖 L0/L1/L2 三层 + 横切关注点（向量、全文、锁、事件、监听），两个实现（`LocalVaultFS` / `DistributedVaultFS`）必须通过同一份 conformance 测试。

## 2. 设计目标

1. **统一接口**：上层代码不感知存储后端，LocalVaultFS 和 DistributedVaultFS 通过同一份 `VaultFS` Protocol
2. **功能对等**：两个实现必须功能等价，CI conformance 测试强制（杜绝 llmwiki 本地模式残废反模式）
3. **文件即真相**：L0/L1 文件优先，DB 是衍生层，可 `reindex` 重建（符合 llm-wiki.md spec 精神）
4. **per-space 隔离**：每个 space 一个 VaultFS 实例，禁止模块级全局单例（杜绝 llmwiki `_db` 全局可变状态反模式）
5. **可插拔**：通过 entry-point 注册新 backend，第三方可扩展

## 3. VaultFS Protocol

```python
from typing import Protocol, runtime_checkable
from datetime import datetime
from .types import (
    SpaceId, VerbatId, DocId, EdgeId,
    Verbat, Document, Edge, Subgraph,
    VerbatHit, DocHit, VectorHit, FtsHit,
    ChangeEvent, WriteLock, ReindexReport,
)


@runtime_checkable
class VaultFS(Protocol):
    """统一存储抽象，覆盖 L0/L1/L2 + 横切关注点。

    每个 Space 持有一个 VaultFS 实例，禁止跨 Space 共享。
    """

    # ----- 元信息 -----
    @property
    def space_id(self) -> SpaceId: ...
    @property
    def backend_type(self) -> str: ...    # "local" | "distributed"

    # ===== L0 Verbatim =====
    async def verbat_add(self, v: Verbat) -> VerbatId:
        """新增 verbatim。同 space 内 content_hash 重复时返回已有 id，不报错。"""
        ...

    async def verbat_get(self, vid: VerbatId) -> Verbat | None: ...
    async def verbat_list(
        self,
        extract_mode: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Verbat]: ...
    async def verbat_search(
        self, query: str, limit: int = 10, extract_mode: str | None = None
    ) -> list[VerbatHit]: ...
    async def verbat_deprecate(self, vid: VerbatId) -> None: ...

    # ===== L1 Document =====
    async def doc_create(
        self,
        path: str,                       # 相对 wiki/ 的路径
        content: str,                    # markdown 全文（含 frontmatter）
        frontmatter: dict | None = None, # 可选显式传入，否则从 content 解析
    ) -> DocId: ...
    async def doc_edit(self, path: str, content: str) -> None:
        """编辑文档。frontmatter 重新解析，L2 edges 重建。"""
        ...
    async def doc_read(self, path: str) -> Document | None: ...
    async def doc_delete(self, path: str) -> None:
        """删除文档。log.md / overview.md 受保护，拒绝删除。"""
        ...
    async def doc_list(
        self, type: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]: ...
    async def doc_search(
        self,
        query: str,
        mode: str = "documents",         # documents | references
        limit: int = 10,
    ) -> list[DocHit]: ...
    async def doc_lint(self, path: str | None = None) -> list[LintIssue]: ...

    # ===== L2 Graph =====
    async def edge_add(self, e: Edge) -> EdgeId: ...
    async def edge_invalidate(self, eid: EdgeId, valid_to: datetime | None = None) -> None: ...
    async def graph_query(
        self,
        entity: str | None = None,
        predicate: str | None = None,
        hop: int = 1,
        include_invalid: bool = False,
    ) -> Subgraph: ...
    async def graph_traverse(
        self, start: str, hop: int = 2, mode: str = "bfs"
    ) -> Subgraph: ...
    async def graph_timeline(self, entity: str) -> list[Edge]: ...

    # ===== 横切：向量 =====
    async def vector_upsert(
        self, id: str, embedding: list[float], meta: dict
    ) -> None: ...
    async def vector_query(
        self,
        embedding: list[float],
        top_k: int = 10,
        filter: dict | None = None,
    ) -> list[VectorHit]: ...
    async def vector_delete(self, id: str) -> None: ...

    # ===== 横切：全文 =====
    async def fts_search(
        self, query: str, limit: int = 10, filter: dict | None = None
    ) -> list[FtsHit]: ...

    # ===== 横切：锁 =====
    async def acquire_write_lock(self, timeout: int = 30) -> WriteLock:
        """Space-level writer lock。同一 space 同时只允许一个写操作。

        LocalVaultFS: flock(space_path/.ks/writer.lock)
        DistributedVaultFS: pg_advisory_xact_lock(hash(space_id))
        """
        ...

    # ===== 横切：事件 =====
    async def publish_event(self, event: ChangeEvent) -> None:
        """发布变更事件。

        LocalVaultFS: in-process asyncio.Queue
        DistributedVaultFS: Postgres LISTEN/NOTIFY
        """
        ...
    async def subscribe_events(
        self, callback: Callable[[ChangeEvent], None]
    ) -> Subscription: ...

    # ===== 横切：文件变更监听 =====
    async def watch_changes(
        self, callback: Callable[[ChangeEvent], None]
    ) -> Watcher:
        """监听外部对 raw/ 和 wiki/ 的修改。

        LocalVaultFS: watchfiles (Python) / notify (Rust)
        DistributedVaultFS: S3 Event Notification → SQS/EventBridge
        """
        ...

    # ===== 重建 =====
    async def reindex(self, layer: str = "all") -> ReindexReport:
        """重建衍生层。layer ∈ {chunks, L2, all}。L0 永不重建。"""
        ...

    # ===== Embedder Identity =====
    async def get_embedder_identity(self) -> EmbedderIdentity: ...
    async def set_embedder_identity(
        self, model_name: str, dimension: int, force_swap: bool = False
    ) -> None:
        """设置或强制切换 embedder。force_swap=True 会触发向量重建。"""
        ...
```

## 4. LocalVaultFS 实现

### 4.1 存储映射

| 数据 | 位置 |
|---|---|
| L0 verbatim 原文 | `~/.ks/spaces/<slug>/raw/{sources,convos,clips}/` |
| L1 document markdown | `~/.ks/spaces/<slug>/wiki/<type>/<slug>.md` |
| L1 元数据 + chunks + edges | `~/.ks/spaces/<slug>/.ks/index.db` (SQLite) |
| 向量 | `~/.ks/spaces/<slug>/.ks/vectors.lance` (LanceDB) |
| schema.md | `~/.ks/spaces/<slug>/schema.md` |
| 聊天历史 | `~/.ks/spaces/<slug>/.ks/chats/{id}.json` |
| embedder identity | SQLite `embedder_identity` 表 |
| writer lock | `flock(~/.ks/spaces/<slug>/.ks/writer.lock)` |

### 4.2 目录结构

```
~/.ks/spaces/<slug>/
├── schema.md
├── purpose.md
├── raw/
│   ├── sources/          # upload / mine 的文件
│   ├── convos/           # extract_mode="convo" 的对话片段
│   └── clips/            # 浏览器剪藏
├── wiki/
│   ├── index.md
│   ├── log.md
│   ├── overview.md
│   ├── entities/
│   ├── concepts/
│   └── ...               # schema.md 定义的 type 目录
├── graph/                # 可选导出（.jsonld）
└── .ks/                  # 衍生层，可删可重建
    ├── index.db          # SQLite
    ├── vectors.lance     # LanceDB
    ├── chats/
    ├── reviews/
    └── writer.lock       # flock
```

### 4.3 关键技术点

- **SQLite**：WAL 模式（`PRAGMA journal_mode=WAL`），单连接 + `aiosqlite` 异步包装
- **LanceDB**：Rust crate 通过 Python binding 调用，per-space 一个 lance 目录
- **FTS5**：`tokenize='porter unicode61'`，CJK bigram 在应用层实现（参考 llm_wiki `search.rs`）
- **watchfiles**：Python 库，监听 `raw/` 和 `wiki/` 目录变更
- **flock**：`fcntl.flock` 文件锁，进程退出自动释放

## 5. DistributedVaultFS 实现

### 5.1 存储映射

| 数据 | 位置 |
|---|---|
| L0 verbatim 原文 | S3 `s3://ks-<tenant>/spaces/<slug>/raw/...` |
| L1 document markdown | S3 `s3://ks-<tenant>/spaces/<slug>/wiki/...` |
| L1 元数据 + chunks + edges | Postgres（per-tenant schema） |
| 向量 | Postgres `document_chunks.embedding` 列（pgvector） |
| schema.md | S3 `s3://ks-<tenant>/spaces/<slug>/schema.md` |
| 聊天历史 | Postgres `chats` 表 |
| embedder identity | Postgres `embedder_identity` 表 |
| writer lock | `pg_advisory_xact_lock(hash(space_id))` |

### 5.2 Postgres Schema

表结构与 RFC 001 §8.1 SQLite schema 相同，差异：

```sql
-- PGroonga 全文索引（替代 FTS5）
CREATE INDEX chunks_fts_idx ON document_chunks
  USING pgroonga (content);

-- pgvector 向量列
ALTER TABLE document_chunks
  ADD COLUMN embedding vector(384);
CREATE INDEX chunks_vector_idx ON document_chunks
  USING ivfflat (embedding vector_cosine_ops);

-- 行级安全
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY documents_isolation ON documents
  USING (space_id IN (
    SELECT id FROM spaces WHERE owner_id = current_user_id()
  ));

-- LISTEN/NOTIFY 事件
CREATE OR REPLACE FUNCTION notify_change() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('space_' || NEW.space_id, row_to_json(NEW)::text);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_notify AFTER INSERT OR UPDATE OR DELETE ON documents
  FOR EACH ROW EXECUTE FUNCTION notify_change();
```

### 5.3 关键技术点

- **S3 客户端**：`aioboto3` 异步 S3 访问，multipart upload 支持大文件
- **Postgres**：`asyncpg` 异步驱动，连接池 `min_size=2, max_size=10`
- **pgvector**：`pgvector` Python 库，HNSW 或 IVFFlat 索引
- **PGroonga**：全文索引，CJK 友好
- **事件推送**：`LISTEN/NOTIFY` → WebSocket 推送到前端
- **文件变更监听**：S3 Event Notification → SQS → worker（不支持 inotify）

## 6. Conformance 测试

### 6.1 测试套件

`packages/derisk-ext/src/derisk_ext/knowledge/vaultfs/conformance.py` 定义一组通用测试，两个实现必须全过：

```python
class VaultFSConformance(Protocol):
    """所有 VaultFS 实现必须通过的测试套件。"""

    # L0
    def test_verbat_add_dedup(self): ...          # 相同 content_hash 去重
    def test_verbat_immutable(self): ...           # 写入后 content 不可改
    def test_verbat_deprecate_keeps_content(self): ...
    def test_verbat_search_by_extract_mode(self): ...

    # L1
    def test_doc_create_with_frontmatter(self): ...
    def test_doc_edit_rebuilds_l2(self): ...
    def test_doc_delete_protected_files(self): ... # log.md / overview.md 拒删
    def test_doc_search_documents_mode(self): ...
    def test_doc_search_references_mode(self): ...
    def test_doc_lint_orphan_and_stale(self): ...

    # L2
    def test_edge_add_with_validity(self): ...
    def test_edge_invalidate_keeps_history(self): ...
    def test_graph_traverse_bfs(self): ...
    def test_graph_timeline(self): ...
    def test_reindex_l2_from_l1(self): ...         # 关键：L2 必须可从 L1 重建

    # 横切
    def test_vector_upsert_query(self): ...
    def test_fts_search_cjk(self): ...             # CJK bigram 必须工作
    def test_write_lock_exclusion(self): ...       # 并发写互斥
    def test_event_publish_subscribe(self): ...
    def test_embedder_identity_mismatch_raises(self): ...
    def test_embedder_force_swap(self): ...
```

### 6.2 CI 强制

```yaml
# .github/workflows/knowledge-conformance.yml
jobs:
  conformance:
    strategy:
      matrix:
        backend: [local, distributed]
    steps:
      - run: pytest tests/knowledge/conformance/ --backend=${{ matrix.backend }}
```

**任何实现功能缺失 = CI 失败 = 不允许合并**。这是堵死 llmwiki 反模式的硬约束。

## 7. Backend 注册

通过 entry-point 注册（学 mempalace `pyproject.toml:61-65`）：

```toml
# packages/derisk-ext/pyproject.toml
[project.entry-points."derisk.knowledge.backends"]
local = "derisk_ext.knowledge.vaultfs.local:LocalVaultFS"
distributed = "derisk_ext.knowledge.vaultfs.distributed:DistributedVaultFS"
```

加载：

```python
from importlib.metadata import entry_points

def get_vault_fs(backend: str, space_id: SpaceId, **kwargs) -> VaultFS:
    eps = entry_points(group="derisk.knowledge.backends")
    if backend not in eps:
        raise ValueError(f"Unknown backend: {backend}")
    cls = eps[backend].load()
    return cls(space_id=space_id, **kwargs)
```

## 8. 并发与一致性

### 8.1 Writer Lock 语义

- **粒度**：Space-level
- **范围**：所有 L0 写入、L1 编辑、L2 edge 变更、reindex
- **超时**：默认 30s，可配
- **失败行为**：抛 `WriteLockTimeout`，建议 caller 重试或排队

### 8.2 并发读

读操作不加锁，依赖 SQLite WAL / Postgres MVCC 保证一致性。

### 8.3 跨进程锁

| 模式 | 实现 |
|---|---|
| LocalVaultFS | `flock` 文件锁，进程崩溃自动释放 |
| DistributedVaultFS | `pg_advisory_xact_lock`，事务结束自动释放 |

## 9. 不做的事

- **不支持 NFS / 分布式文件系统**：FS 只在 LocalVaultFS 用，DistributedVaultFS 一律 S3 + Postgres
- **不引入独立图数据库**（Neo4j / Nebula）：L2 走 SQLite / Postgres，不强加图库依赖
- **不引入独立消息队列**作为 MVP：LocalVaultFS 用 in-process channel，DistributedVaultFS 用 Postgres LISTEN/NOTIFY（容量有限但够用）；规模上来再加 Redis Stream / SQS
- **不做多区域多活**：MVP 只支持单区域

## 10. 验收标准

- [ ] `LocalVaultFS` 通过全部 conformance 测试
- [ ] `DistributedVaultFS` 通过全部 conformance 测试
- [ ] 两个实现的性能基准测试差距 < 3x（除向量检索，pgvector 比 LanceDB 慢可接受）
- [ ] entry-point 注册机制可加载第三方 backend
- [ ] writer lock 在跨进程场景下正确互斥
- [ ] `reindex` 能从 L0+L1 完整重建 chunks + L2

## 11. 开放问题

1. **LanceDB vs sqlite-vec**：LanceDB 是 Rust 实现，性能好但依赖重；`sqlite-vec` 是 SQLite 扩展，轻量但功能弱。MVP 倾向 LanceDB。
2. **Postgres 是否用 AGE 图扩展**：AGE 支持图查询语法（Cypher），但增加运维复杂度。MVP 倾向不用，L2 走关系表 + 应用层图遍历。
3. **S3 事件通知延迟**：S3 Event Notification 有秒级延迟，是否影响实时性？MVP 可接受，未来加 Redis 缓存 schema 解析结果降低感知。
