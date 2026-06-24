# RFC 004: Tool 协议（内置 Tool + MCP Tool）

- **状态**: Draft
- **作者**: Knowledge Team
- **创建日期**: 2026-06-23
- **关联**: RFC 001 (三层数据模型), RFC 002 (VaultFS), RFC 003 (schema.md)

## 1. 背景

OpenDerisk 现有知识接入方式（`derisk-serve/agent/resource/knowledge.py:92` `KnowledgeSpaceRetrieverResource`）把检索逻辑塞进 Resource 内部，`_retrieve` 直接调 `KnowledgeSpaceRetriever`。这种设计与 llm-wiki.md spec 第 33 行精神不符——spec 强调 LLM 应该直接操作 wiki，不应该有"检索"中间层。

本 RFC 定义新的三层模型：**Resource（挂载配置）+ 内置 Tool（Agent 直接操作）+ MCP Tool（外部工具接入）**。同一份 tool handler 实现两种暴露方式。

## 2. 三层职责

```
Agent
  ├─ Resources（声明挂载哪些知识空间）
  │    └─ KnowledgeSpaceResource(space_slug="risk-wiki")
  │       └─ 携带 space 上下文 + schema.md 摘要
  └─ Tools（操作挂载的 resource）
       ├─ doc_search(space_slug, query, ...)
       ├─ space_search(space_slug, query, mode=hybrid)
       ├─ graph_traverse(space_slug, start, hop)
       └─ verbatim_get(space_slug, id)
```

### 2.1 Resource 层

**职责**：声明"这个 Agent 能用哪些 space"，携带 space 上下文（slug、schema.md 摘要）。

**不做**：不实现检索逻辑、不持有 retriever 实例。

**对应 spec**：等价于"人在 Obsidian 里打开一个 vault 目录"——spec 第 15 行「I have the LLM agent open on one side and Obsidian open on the other」。

### 2.2 内置 Tool 层

**职责**：Agent 在对话里直接调用，操作挂载的 KnowledgeSpaceResource。

**注册机制**：通过 OpenDerisk `ToolRegistry`（`derisk-core/agent/tools/registry.py:242`）注册为 `ToolSource.SYSTEM`，分类 `ToolCategory.SEARCH` / `ToolCategory.DATABASE`。

**参数来源**：tool 接收 `space_slug` 参数，从 `ToolContext` 拿 Agent 挂载的 resource 列表，校验 `space_slug` 在列表里。

### 2.3 MCP Tool 层

**职责**：外部 Claude Code / Cursor / Codex 等通过 MCP 协议接入。

**注册机制**：复用 OpenDerisk `derisk-serve/mcp/` 框架，stdio + HTTP loopback 双形态。

**参数来源**：tool 直接接 `space_slug` 参数，靠 MCP server 端鉴权控制能访问哪些 space。

### 2.4 Handler 共用

内置 Tool 和 MCP Tool 共用同一份 handler 实现（`derisk-core/knowledge/tools/handlers.py`），只是参数来源和鉴权方式不同。

## 3. KnowledgeSpaceResource

### 3.1 定义

```python
# packages/derisk-core/src/derisk/knowledge/resource.py

@dataclasses.dataclass
class KnowledgeSpaceResourceParameters(ResourceParameters):
    """挂载知识空间的参数。"""
    space_slug: str = dataclasses.field(
        metadata={"help": _("Knowledge space slug to mount")}
    )

class KnowledgeSpaceResource(Resource[KnowledgeSpaceResourceParameters]):
    """挂载一个知识空间给 Agent。

    职责：
    1. 携带 space_slug 上下文
    2. 提供 schema.md 摘要给 LLM（通过 get_prompt）
    3. 校验 tool 调用时的 space_slug 是否匹配

    不做：
    - 不实现检索（旧 RetrieverResource 的 retrieve 方法废弃）
    - 不持有 retriever 实例
    """

    def __init__(self, name: str, space_slug: str, system_app: SystemApp = None):
        self._name = name
        self._space_slug = space_slug
        self._system_app = system_app
        self._schema_cache: Schema | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def space_slug(self) -> str:
        return self._space_slug

    @classmethod
    def type(cls) -> ResourceType:
        return ResourceType.Knowledge  # 复用现有枚举

    @classmethod
    def resource_parameters_class(cls, **kwargs):
        return KnowledgeSpaceResourceParameters

    async def get_prompt(
        self,
        *,
        lang: str = "en",
        prompt_type: str = "default",
        question: str | None = None,
        resource_name: str | None = None,
        **kwargs,
    ) -> tuple[str, dict | None]:
        """注入 schema.md 摘要到 LLM prompt。"""
        schema = await self._get_schema()
        prompt = self._build_prompt(schema, lang)
        return prompt, {"space_slug": self._space_slug, "schema_hash": schema.raw_hash}

    def _build_prompt(self, schema: Schema, lang: str) -> str:
        if lang == "zh":
            return (
                f"知识空间: {self._space_slug}\n"
                f"用途: {schema.purpose}\n"
                f"页面类型: {', '.join(schema.page_types.keys())}\n"
                f"关系类型: {', '.join(schema.relation_types.keys())}\n"
                f"可用工具: doc_search, doc_read, doc_create, doc_edit, "
                f"space_search, graph_traverse, verbatim_get, ..."
                f"\n请使用工具直接操作此知识空间。"
            )
        return (
            f"Knowledge Space: {self._space_slug}\n"
            f"Purpose: {schema.purpose}\n"
            f"Page Types: {', '.join(schema.page_types.keys())}\n"
            f"Relation Types: {', '.join(schema.relation_types.keys())}\n"
            f"Available tools: doc_search, doc_read, doc_create, doc_edit, "
            f"space_search, graph_traverse, verbatim_get, ..."
            f"\nUse tools to operate on this knowledge space directly."
        )

    async def _get_schema(self) -> Schema:
        """从 VaultFS 读 schema.md 并解析，5s 缓存。"""
        if self._schema_cache is None:
            vault = await get_vault_fs(self._space_slug)
            content = await vault.read_schema_md()
            self._schema_cache = parse_schema(content)
        return self._schema_cache
```

### 3.2 替换关系

| 旧 | 新 |
|---|---|
| `derisk-serve/agent/resource/knowledge.py:KnowledgeSpaceRetrieverResource` | `derisk-core/knowledge/resource.py:KnowledgeSpaceResource` |
| `derisk-serve/agent/resource/knowledge_pack.py:KnowledgePackResource` | 删除，多 space 通过挂载多个 `KnowledgeSpaceResource` 实现 |
| `derisk-core/agent/resource/knowledge.py:RetrieverResource` 基类 | 删除（仅保留 `Resource` 基类） |

### 3.3 注册

复用 `derisk_app/component_configs.py` 的注册机制：

```python
# packages/derisk-app/src/derisk_app/component_configs.py
rm.register_resource(KnowledgeSpaceResource)  # 替换原 KnowledgeSpaceRetrieverResource
```

## 4. 内置 Tool

### 4.1 Tool 完整列表

按 L0/L1/L2/Space/Admin 分组，约 20 个：

#### L0 Verbatim Tools

| tool name | 参数 | 说明 |
|---|---|---|
| `verbatim_add` | `space_slug, content, source_file?, extract_mode="convo"` | Agent 主动归档对话片段 |
| `verbatim_get` | `space_slug, verbat_id` | 读取 verbatim 原文 |
| `verbatim_search` | `space_slug, query, limit=10, extract_mode?` | 搜索 verbatim |

#### L1 Document Tools

| tool name | 参数 | 说明 |
|---|---|---|
| `doc_create` | `space_slug, path, content, frontmatter?` | 新建文档 |
| `doc_edit` | `space_slug, path, content` | 编辑文档（自动重建 L2） |
| `doc_read` | `space_slug, path` | 读文档 |
| `doc_delete` | `space_slug, path` | 删文档（log.md / overview.md 受保护） |
| `doc_list` | `space_slug, type?, limit=100` | 列文档 |
| `doc_search` | `space_slug, query, mode="documents", limit=10` | 搜文档 |
| `doc_lint` | `space_slug, path?` | lint 检查 |

#### L2 Graph Tools

| tool name | 参数 | 说明 |
|---|---|---|
| `graph_query` | `space_slug, entity?, predicate?, hop=1` | 查询子图 |
| `graph_traverse` | `space_slug, start, hop=2, mode="bfs"` | BFS/DFS 遍历 |
| `graph_add_edge` | `space_slug, subject, predicate, object, valid_from?` | 新增边 |
| `graph_invalidate_edge` | `space_slug, edge_id` | 失效边（设 valid_to=now） |
| `graph_timeline` | `space_slug, entity` | 实体时序变化 |

#### Space Tools

| tool name | 参数 | 说明 |
|---|---|---|
| `space_list` | (无) | 列出当前 Agent 挂载的所有 space |
| `space_status` | `space_slug` | 空间统计（L0/L1/L2 计数 + embedder identity） |
| `space_schema_get` | `space_slug` | 读 schema.md |
| `space_schema_update` | `space_slug, content` | 更新 schema.md（触发 L2 重建建议） |
| `space_search` | `space_slug, query, mode="hybrid", top_k=10` | 4 阶段 RAG 检索 |
| `space_wake_up` | `space_slug` | 返回 L0–L3 上下文栈，注入 agent prompt |

#### Admin Tools

| tool name | 参数 | 说明 |
|---|---|---|
| `ingest_trigger` | `space_slug, source_path` | 触发 ingest pipeline |
| `reindex` | `space_slug, layer="all"` | 重建衍生层 |

### 4.2 Handler 共用实现

```python
# packages/derisk-core/src/derisk/knowledge/tools/handlers.py

async def _get_vault(space_slug: str, context: ToolContext | None = None) -> VaultFS:
    """从 context 拿挂载的 resource，校验 space_slug，返回 VaultFS。

    内置 tool 调用：context 携带 Agent 挂载的 KnowledgeSpaceResource 列表。
    MCP tool 调用：context 为 None，直接按 space_slug 查（鉴权由 MCP server 处理）。
    """
    if context is not None:
        # 内置 tool 路径：校验 space_slug 在 Agent 挂载列表里
        mounted = [
            r for r in context.resources
            if isinstance(r, KnowledgeSpaceResource) and r.space_slug == space_slug
        ]
        if not mounted:
            raise PermissionError(
                f"Space '{space_slug}' is not mounted on this Agent. "
                f"Mounted spaces: {[r.space_slug for r in context.resources if isinstance(r, KnowledgeSpaceResource)]}"
            )
    # MCP tool 路径：MCP server 已鉴权，直接放行
    return await get_vault_fs(space_slug)


async def handle_doc_search(
    space_slug: str,
    query: str,
    mode: str = "documents",
    limit: int = 10,
    context: ToolContext | None = None,
) -> dict:
    """doc_search handler，内置 tool 和 MCP tool 共用。"""
    vault = await _get_vault(space_slug, context)
    hits = await vault.doc_search(query=query, mode=mode, limit=limit)
    return {
        "space_slug": space_slug,
        "mode": mode,
        "hits": [
            {
                "path": h.path,
                "title": h.title,
                "type": h.type,
                "score": h.score,
                "snippet": h.snippet,
                "verbatim_ids": h.verbats,  # L0 回跳指针
            }
            for h in hits
        ],
    }
```

### 4.3 内置 Tool 注册

```python
# packages/derisk-core/src/derisk/knowledge/tools/builtin.py

from derisk.agent.tools import ToolBase, ToolMetadata, ToolCategory, ToolSource
from derisk.agent.tools.registry import tool_registry

class DocSearchTool(ToolBase):
    def _define_metadata(self):
        return ToolMetadata(
            name="doc_search",
            description="Search documents in a knowledge space by keywords or references.",
            category=ToolCategory.SEARCH,
            risk_level=ToolRiskLevel.LOW,
        )

    def _define_parameters(self):
        return {
            "type": "object",
            "properties": {
                "space_slug": {"type": "string", "description": "Knowledge space slug"},
                "query": {"type": "string", "description": "Search query"},
                "mode": {
                    "type": "string",
                    "enum": ["documents", "references"],
                    "default": "documents",
                },
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
            },
            "required": ["space_slug", "query"],
        }

    async def execute(self, args: dict, context=None):
        from .handlers import handle_doc_search
        result = await handle_doc_search(context=context, **args)
        return ToolResult(success=True, output=result, tool_name=self.name)


def register_knowledge_tools():
    """注册全部内置知识 tool。在 component_configs.py 调用。"""
    tools = [
        DocSearchTool(),
        DocReadTool(),
        DocCreateTool(),
        # ... 全部 20 个
    ]
    for t in tools:
        tool_registry.register(t, source=ToolSource.SYSTEM)
```

### 4.4 调用方校验

内置 tool 调用时，`ToolContext` 携带 Agent 挂载的 resource 列表：

```python
# Agent 执行 tool 时的 context 构造
context = ToolContext(
    resources=agent.resources,  # 含 KnowledgeSpaceResource 实例
    user_id=agent.user_id,
    ...
)

# tool handler 内部校验
vault = await _get_vault(space_slug, context)
# 若 space_slug 不在挂载列表 → PermissionError
```

## 5. MCP Tool

### 5.1 复用 OpenDerisk MCP 框架

```python
# packages/derisk-serve/src/derisk_serve/knowledge/mcp.py

from derisk_serve.mcp import McpServer, McpTool

class KnowledgeMcpServer(McpServer):
    """知识空间 MCP server，暴露给外部 Claude Code / Cursor 等。"""

    name = "derisk-knowledge"

    def get_tools(self) -> list[McpTool]:
        return [
            McpTool(
                name="doc_search",
                description="Search documents in a knowledge space.",
                input_schema={...},  # 同 DocSearchTool._define_parameters()
                handler=self._wrap_handler(handle_doc_search),
            ),
            # ... 全部 20 个
        ]

    async def _wrap_handler(self, handler):
        """MCP 调用 handler，context=None（鉴权由 MCP server 处理）。"""
        async def wrapped(args: dict):
            # MCP server 端鉴权：检查 client token 是否能访问 args["space_slug"]
            await self._authorize(args.get("space_slug"))
            return await handler(context=None, **args)
        return wrapped

    async def _authorize(self, space_slug: str | None):
        """根据 MCP client token 鉴权。"""
        if space_slug is None:
            return
        # 查 space 的 visibility / ACL
        space = await get_space_by_slug(space_slug)
        if not self._client_can_access(space):
            raise PermissionError(f"Cannot access space '{space_slug}'")
```

### 5.2 暴露形态

| 形态 | 启动命令 | 适用场景 |
|---|---|---|
| stdio | `derisk mcp knowledge --space <slug>` | Claude Desktop / Claude Code 配置 mcp.json |
| HTTP loopback | `derisk mcp knowledge --http --port 7780` | Cursor / Codex 等 HTTP MCP 客户端 |

### 5.3 外部工具接入示例

Claude Code `.claude/mcp.json`：

```json
{
  "mcpServers": {
    "derisk-knowledge": {
      "command": "derisk",
      "args": ["mcp", "knowledge", "--space", "risk-wiki"]
    }
  }
}
```

Cursor 配置（HTTP）：

```json
{
  "mcpServers": {
    "derisk-knowledge": {
      "url": "http://localhost:7780/mcp"
    }
  }
}
```

### 5.4 端口规划

- `7777`：OpenDerisk 主服务（FastAPI，已有）
- `7780`：知识空间 MCP server（HTTP loopback，新）
- `7781`：clip server（浏览器扩展，新）

## 6. Tool 返回格式

**所有 tool 返回结构化 JSON**，不返回 markdown 文本（学 llmwiki，规避 llm_wiki `mcp-server/src/index.ts:285-305` 返 markdown 带 emoji 的槽点）。

### 6.1 doc_search 返回示例

```json
{
  "space_slug": "risk-wiki",
  "mode": "documents",
  "hits": [
    {
      "path": "wiki/concepts/attention.md",
      "title": "Attention Mechanism",
      "type": "concept",
      "score": 0.87,
      "snippet": "Attention mechanism allows models to focus on...",
      "verbatim_ids": ["v_01HZ...", "v_01HZ..."]
    }
  ]
}
```

### 6.2 space_search（4 阶段 RAG）返回示例

```json
{
  "space_slug": "risk-wiki",
  "mode": "hybrid",
  "phases": {
    "keyword": {"hits": 5, "token_budget": 1200},
    "vector": {"hits": 8, "token_budget": 2000},
    "graph_expansion": {"hits": 3, "signal_scores": {...}},
    "context_assembly": {"total_tokens": 3800, "budget_allocation": {"L1": "60%", "L0": "20%", "L2": "5%", "log_overview": "15%"}}
  },
  "context": "assembled markdown context for LLM",
  "citations": [
    {"id": 1, "path": "wiki/concepts/attention.md", "verbatim_id": "v_01HZ..."}
  ]
}
```

## 7. 鉴权矩阵

| 调用方 | space_slug 来源 | 鉴权方式 |
|---|---|---|
| 内置 Tool（OpenDerisk Agent） | tool 参数 | 校验 `space_slug` 在 Agent 挂载的 `KnowledgeSpaceResource` 列表里 |
| MCP stdio（单 space 模式） | 启动时 `--space` 指定 | 不需要运行时鉴权，进程级隔离 |
| MCP HTTP（多 space 模式） | tool 参数 | MCP server 端 token 鉴权 + space ACL |
| HTTP API（Web UI 用） | URL path `/spaces/{id}` | OpenDerisk 现有 JWT 鉴权 |

## 8. 与 OpenDerisk ToolBase 集成

`ToolBase`（`derisk-core/agent/tools/base.py:81`）已提供完整基类，新 tool 直接继承：

```python
class DocSearchTool(ToolBase):
    def _define_metadata(self) -> ToolMetadata: ...
    def _define_parameters(self) -> dict: ...
    async def execute(self, args: dict, context=None) -> ToolResult: ...
```

注册到全局 `tool_registry`（`registry.py:242`），自动暴露给 OpenDerisk Agent 系统。

### 8.1 不使用 `@tool` 装饰器

`base.py:302` 的 `@tool` 装饰器把函数转 tool，但参数类型推断粗糙（只支持基础类型）。三层模型 tool 参数含 enum、嵌套对象，必须手写 JSON Schema，所以用类继承方式。

### 8.2 ToolCategory 选择

| tool 类别 | ToolCategory |
|---|---|
| 检索类（doc_search / space_search / verbatim_search） | `ToolCategory.SEARCH` |
| 读写类（doc_create / doc_edit / verbatim_add） | `ToolCategory.DATABASE` |
| 图遍历类（graph_query / graph_traverse） | `ToolCategory.SEARCH` |
| 管理类（reindex / ingest_trigger） | `ToolCategory.UTILITY` |

### 8.3 ToolRiskLevel

| 风险 | tool |
|---|---|
| `SAFE` | doc_read / doc_list / doc_search / graph_query / space_status |
| `LOW` | verbatim_add / verbatim_get / verbatim_search / space_search / space_wake_up |
| `MEDIUM` | doc_create / doc_edit / graph_add_edge / ingest_trigger |
| `HIGH` | doc_delete / graph_invalidate_edge / reindex / space_schema_update |

## 9. 删除清单

实现新 Tool 系统时，删除以下旧代码：

| 文件 | 内容 | 替换为 |
|---|---|---|
| `derisk-serve/agent/resource/knowledge.py` | `KnowledgeSpaceRetrieverResource` | `KnowledgeSpaceResource` |
| `derisk-serve/agent/resource/knowledge_pack.py` | `KnowledgePackResource` | 多个 `KnowledgeSpaceResource` |
| `derisk-core/agent/resource/knowledge.py` | `RetrieverResource` / `RetrieverResourceParameters` | `Resource` 基类直接用 |
| `derisk-serve/rag/retriever/knowledge_space.py` | `KnowledgeSpaceRetriever` | 删除（检索逻辑移到 tool handler） |
| `derisk-serve/rag/service/service.py` 的 `retrieve` / `knowledge_search` 方法 | 旧检索服务 | tool handler 内部调 VaultFS |

## 10. 验收标准

- [ ] `KnowledgeSpaceResource` 注册到 `ResourceType.Knowledge`，能挂载到 Agent
- [ ] 20 个内置 tool 全部注册到 `tool_registry`，能被 Agent 调用
- [ ] 内置 tool 调用时校验 `space_slug` 在挂载列表里，未挂载时抛 `PermissionError`
- [ ] MCP server 同时支持 stdio 和 HTTP loopback 两种形态
- [ ] 同一份 handler 实现内置 tool 和 MCP tool 共用
- [ ] 所有 tool 返回结构化 JSON，不返回 markdown 文本
- [ ] Claude Code 通过 mcp.json 接入后能调用 `doc_search` / `space_search` 等
- [ ] 删除旧 `RetrieverResource` / `KnowledgeSpaceRetrieverResource` / `KnowledgePackResource` 后 OpenDerisk 启动正常

## 11. 开放问题

1. **Tool 数量是否过多**：20 个 tool 对 LLM 可能负担重。是否合并？比如 `doc_search` 和 `space_search` 合并？倾向不合并，职责清晰更重要，LLM 通过 schema.md 摘要知道何时用哪个。
2. **MCP 是否支持多 space**：stdio 模式启动时 `--space` 指定单个，HTTP 模式支持多 space。是否 stdio 也支持多 space？倾向不支持，stdio 模式保持简单。
3. **Tool 调用审计**：是否记录每次 tool 调用到 `rag_span` 表？MVP 不记录，未来加可观测性。
