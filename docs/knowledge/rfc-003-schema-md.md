# RFC 003: schema.md 规范

- **状态**: Draft
- **作者**: Knowledge Team
- **创建日期**: 2026-06-23
- **关联**: RFC 001 (三层数据模型), RFC 002 (VaultFS)

## 1. 背景

llm-wiki.md spec 第 33 行定义 schema 层："a document (e.g. CLAUDE.md for Claude Code or AGENTS.md for Codex) that tells the LLM how the wiki is structured, what the conventions are, and what workflows to follow when ingesting sources, answering questions, or maintaining the wiki."

OpenDerisk 现有 RAG 把 chunk 策略硬编码在 `ChunkStrategy` 枚举（`derisk-core/rag/knowledge/base.py:215`），用户改不了。llm_wiki 的 `wiki-schema.ts:27-92` 实现了 schema.md 驱动 page type 路由但没做 relation type。llmwiki 的关系类型硬编码 `cites` / `links_to` 两种。

本 RFC 定义 schema.md 规范，同时支持 page type 路由 + relation type 声明 + ingest 工作流配置，**用户编辑 schema.md 即可扩展，无需改代码**。

## 2. schema.md 文件位置

```
~/.ks/spaces/<slug>/schema.md     # 本地模式
s3://ks-<tenant>/spaces/<slug>/schema.md  # 分布式模式
```

每个 space 一份 schema.md，是 space 的配置文件（非数据）。

## 3. schema.md 完整规范

### 3.1 顶层结构

```markdown
# <Space Name> Schema

## Purpose
<空间目标、关键问题、研究范围的一段话描述>

## Page Types
| type | dir | description |
|---|---|---|
| entity | wiki/entities/ | 人/公司/论文/产品 |
| concept | wiki/concepts/ | 抽象概念 |
| ... | ... | ... |

## Relation Types
| type | inverse | description |
|---|---|---|
| cites | cited-by | 引用关系 |
| depends-on | depends-on | 依赖关系（自反） |
| ... | ... | ... |

## Ingest Workflow
<ingest 工作流的一段话描述，LLM 读这段决定怎么处理新源>

## Lint Rules
- orphan_pages: true
- stale_edges: true
- contradiction_detection: true
```

### 3.2 `## Purpose` 段

自由文本，描述空间目标。注入到 ingest pipeline 的 LLM prompt 和 agent system prompt。

### 3.3 `## Page Types` 段（必填）

markdown 表格，三列：

| 列 | 含义 | 示例 |
|---|---|---|
| `type` | page 类型标识符 | `entity` |
| `dir` | 该类型文档存放目录（相对 `wiki/`） | `wiki/entities/` |
| `description` | 人可读描述，告诉 LLM 何时用此类型 | "人/公司/论文/产品" |

约束：
- `type` 必须是小写字母 + 数字 + 短横线，正则 `^[a-z][a-z0-9-]*$`
- `dir` 必须以 `wiki/` 开头，以 `/` 结尾
- `type` 在同 space 内唯一
- `dir` 在同 space 内唯一

### 3.4 `## Relation Types` 段（必填）

markdown 表格，三列：

| 列 | 含义 | 示例 |
|---|---|---|
| `type` | 关系类型标识符 | `cites` |
| `inverse` | 反向关系名（自反填同 type） | `cited-by` 或 `depends-on` |
| `description` | 人可读描述 | "引用关系" |

约束：
- `type` 和 `inverse` 必须满足正则 `^[a-z][a-z0-9-]*$`
- `type` 在同 space 内唯一
- 写入 L2 edge 时 `predicate` 必须在此表内，否则拒绝

### 3.5 `## Ingest Workflow` 段（可选）

自由文本，描述 ingest 工作流。注入到两阶段 CoT 的 LLM prompt。示例：

```markdown
## Ingest Workflow
新源 ingest 时：
1. 先判断 type：如果是论文 → source + 提取实体 + 提取概念；如果是故障报告 → incident + 提取根因 + 关联 runbook
2. 写 source 页（summary + key findings）
3. 更新或新建相关 entity / concept 页
4. 在 log.md 追加 `## [YYYY-MM-DD] ingest | <Title>`
5. 更新 index.md 和 overview.md
```

### 3.6 `## Lint Rules` 段（可选）

YAML 列表，控制 lint 行为：

```markdown
## Lint Rules
- orphan_pages: true              # 检查无反链的页面
- stale_edges: true               # 检查 valid_to 过期的边
- contradiction_detection: true   # 检查同 (s,p,o) 多条有效边
- uncited_sources: true           # 检查 L0 verbat 未被任何 L1 引用
- dangling_links: true            # 检查 [[wikilink]] 指向不存在的页面
- frontmatter_required: [type, title, created, updated]
```

### 3.7 默认 schema.md

新建 space 时自动生成默认 schema.md：

```markdown
# <Space Name> Schema

## Purpose
<待用户填写>

## Page Types
| type | dir | description |
|---|---|---|
| entity | wiki/entities/ | 人/组织/产品/论文 |
| concept | wiki/concepts/ | 抽象概念、理论、方法 |
| source | wiki/sources/ | 源文件摘要 |
| comparison | wiki/comparisons/ | 对比分析 |
| synthesis | wiki/synthesis/ | 跨源综合分析 |
| query | wiki/queries/ | 保存的问答与研究 |
| finding | wiki/findings/ | 研究发现 |
| thesis | wiki/thesis/ | 论点 |
| methodology | wiki/methodology/ | 方法论 |

## Relation Types
| type | inverse | description |
|---|---|---|
| cites | cited-by | 引用关系 |
| links-to | linked-by | wikilink 关联 |
| derived-from | source-of | 从某 verbatim 派生 |
| depends-on | depends-on | 依赖关系（自反） |
| causes | caused-by | 因果关系 |
| contradicts | contradicts | 矛盾关系（自反） |
| part-of | has-part | 包含关系 |

## Ingest Workflow
新源 ingest 时：
1. Step1 分析：抽取实体、识别 type、找关联
2. Step2 生成：写 L1 markdown 页 + frontmatter + sources[]
3. 自动建图：解析 [[wikilink]] / [^N] 脚注 / related / sources
4. 更新 index.md / log.md / overview.md

## Lint Rules
- orphan_pages: true
- stale_edges: true
- contradiction_detection: true
- uncited_sources: true
- dangling_links: true
- frontmatter_required: [type, title, created, updated]
```

## 4. 解析器

### 4.1 模块位置

`packages/derisk-core/src/derisk/knowledge/schema.py`

### 4.2 接口

```python
@dataclass
class PageType:
    type: str
    dir: str
    description: str

@dataclass
class RelationType:
    type: str
    inverse: str
    description: str

@dataclass
class LintRules:
    orphan_pages: bool = True
    stale_edges: bool = True
    contradiction_detection: bool = True
    uncited_sources: bool = True
    dangling_links: bool = True
    frontmatter_required: list[str] = field(
        default_factory=lambda: ["type", "title", "created", "updated"]
    )

@dataclass
class Schema:
    purpose: str
    page_types: dict[str, PageType]      # type → PageType
    relation_types: dict[str, RelationType]  # type → RelationType
    ingest_workflow: str
    lint_rules: LintRules
    raw_hash: str                         # schema.md 内容 hash

def parse_schema(content: str) -> Schema:
    """解析 schema.md 内容。容错：缺失的段使用默认值。"""
    ...

def validate_schema(schema: Schema) -> list[str]:
    """返回错误信息列表，空列表表示合法。"""
    ...

def route_path(schema: Schema, page_type: str, slug: str) -> str:
    """根据 page_type 路由出完整路径，如 entity + attention → wiki/entities/attention.md"""
    ...

def validate_predicate(schema: Schema, predicate: str) -> bool:
    """检查 predicate 是否在 relation_types 里。"""
    ...
```

### 4.3 解析逻辑

1. **按 `##` 段切分**：用正则 `^## (.+)$` 切段
2. **解析 `## Page Types`**：扫 markdown 表格行，跳过表头和分隔行，每行 split `|` 取三列
3. **解析 `## Relation Types`**：同上
4. **解析 `## Lint Rules`**：YAML list 解析（每行 `- key: value`）
5. **解析 `## Purpose` / `## Ingest Workflow`**：取段内所有文本
6. **容错**：缺失 `## Page Types` 用默认 9 种；缺失 `## Relation Types` 用默认 7 种；其他段缺失用空字符串/默认值

### 4.4 缓存

- 解析结果缓存 5s TTL（学 llm_wiki `api_server.rs` 5s 配置缓存）
- 缓存 key 是 `raw_hash`，schema.md 变更时缓存自动失效
- 分布式模式缓存到 Redis，本地模式 in-process cache

## 5. schema.md 变更影响

### 5.1 新增 page type

- 立即生效，下次 `doc_create` 可用新 type
- 不触发重建

### 5.2 删除 page type

- 已有该 type 的 L1 文档不受影响（仍可读可编辑）
- 新建文档不能用此 type（`doc_create` 拒绝）
- lint 报告 "unknown_type" 警告

### 5.3 新增 relation type

- 立即生效，下次 `edge_add` 可用新 predicate
- 不触发重建

### 5.4 删除 relation type

- 已有该 predicate 的 L2 edges 不受影响（仍可查询）
- 新建 edge 不能用此 predicate
- lint 报告 "unknown_predicate" 警告

### 5.5 修改 page type 的 dir

- 已有文档不自动迁移
- lint 报告 "path_mismatch" 警告
- 用户需手动 `doc_edit` 改路径或运行 `reindex --layer=L1-paths`（未来功能）

## 6. 与 ingest pipeline 的集成

ingest Step1 LLM prompt 注入 schema.md 全文：

```
你是知识库维护者。当前空间的 schema.md 如下：

<schema.md 全文>

请分析以下源材料，抽取实体、识别 type、找关联。
type 必须在 schema.md 的 Page Types 表内。
predicate 必须在 schema.md 的 Relation Types 表内。

源材料：
<verbatim content>
```

## 7. 与 lint 的集成

`doc_lint` tool 读取 schema.md 的 `## Lint Rules` 段，按规则检查：

- `orphan_pages`：扫描所有 L1 文档，找出没有任何反链的页面
- `stale_edges`：扫描 `valid_to < now` 的边（其实 valid_to 已设，这是冗余检查）
- `contradiction_detection`：扫描同 (subject, predicate, object) 多条 `valid_to=NULL` 的边
- `uncited_sources`：扫描 L0 verbat 未被任何 L1 的 `sources: []` 引用的
- `dangling_links`：扫描 `[[wikilink]]` 指向不存在文档的
- `frontmatter_required`：扫描 L1 文档 frontmatter 缺字段的

## 8. 验收标准

- [ ] 默认 schema.md 生成正确
- [ ] 解析器对 5 种 LLM 写错的 schema.md 容错（缺段、表格错位、字段乱序等）
- [ ] 编辑 schema.md 新增 page type 后，`doc_create` 立即支持新 type
- [ ] 编辑 schema.md 新增 relation type 后，`edge_add` 立即支持新 predicate
- [ ] schema.md 变更触发 5s 内缓存失效
- [ ] lint 规则按 `## Lint Rules` 段配置生效

## 9. 开放问题

1. **schema.md 是否支持继承**：一个 space 的 schema.md 是否能 `extends` 另一个？MVP 不支持，每个 space 独立。
2. **schema.md 版本化**：是否需要 `schema_version` 字段？MVP 不需要，用 `raw_hash` 跟踪变更即可。
3. **多语言 schema.md**：是否支持 `schema.zh.md` / `schema.en.md`？MVP 不支持，多语言在 `## Purpose` 段内自由处理。
