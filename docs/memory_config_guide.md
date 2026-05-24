# BAIZE Agent 记忆系统配置指南

## 一、配置文件结构

OpenDerisk 使用 TOML 格式配置文件，通常位于项目根目录的 `config.toml`。
记忆系统涉及三个配置区块：

```
[models]          ← LLM 模型 + 向量模型 + 重排序模型
[rag.storage.memory]  ← MemPalace 存储配置
[agent.llm]       ← Agent 使用的 LLM 配置（可选，默认用全局）
```

---

## 二、完整配置示例

```toml
# ============================================
# 1. LLM 模型配置
# ============================================
# 方式一：全局 LLM 配置（Agent 未单独配置时使用）
[models]
default_llm = "gpt-4o"
default_embedding = "bge-m3"

[[models.llms]]
model = "gpt-4o"
model_type = "chat"
provider = "openai"
api_base = "https://api.openai.com/v1"
api_key = "sk-xxx"

[[models.embeddings]]
model = "bge-m3"
provider = "openai"
api_base = "https://api.openai.com/v1"
api_key = "sk-xxx"

# 方式二：Agent 级别 LLM 配置（推荐）
# 在 Agent Builder 中为每个 Agent 配置 LLM，记忆系统自动复用 Agent 的 LLM
# 无需在 [models] 中配置，记忆提取会直接使用 Agent 绑定的模型

# ============================================
# 2. MemPalace 存储配置
# ============================================
[rag.storage.memory]
type = "mempalace"                    # 存储类型，固定为 mempalace
palace_path = "~/.mempalace/palace"   # 数据存储路径
enable_kg = true                      # 是否启用知识图谱
default_wing = "default"              # 默认记忆分区名称
use_builtin_embedding = false         # false = 使用 [models] 中的向量模型

# 自动记忆提取配置
auto_memory = true                    # 是否自动从对话中提取记忆
auto_memory_top_k = 5                 # 每次对话前检索的记忆条数
auto_memory_max_distance = 0.4        # 检索的最大向量距离阈值
```

---

## 三、各配置项详细说明

### 3.1 MemPalace 配置（`[rag.storage.memory]`）

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `type` | string | `"mempalace"` | 存储类型，目前支持 `mempalace`、`letta` |
| `palace_path` | string | `~/.mempalace/palace` | 记忆数据存储目录，ChromaDB 数据存放于此 |
| `enable_kg` | bool | `true` | 是否启用知识图谱（实体三元组存储） |
| `default_wing` | string | `"default"` | 默认记忆分区名，相当于用户/会话标识 |
| `use_builtin_embedding` | bool | `false` | **关键配置**：<br>`false`：使用 `[models]` 中配置的向量模型<br>`true`：使用 MemPalace 内置的 `all-MiniLM-L6-v2`（无需额外配置向量模型） |
| `auto_memory` | bool | `true` | 是否自动从对话中提取并写入记忆 |
| `auto_memory_top_k` | int | `5` | 每次对话前检索的记忆数量 |
| `auto_memory_max_distance` | float | `0.4` | 检索的最大向量距离阈值（越小越精确） |

### 3.2 LLM 配置（记忆提取用的 LLM）

记忆系统使用 LLM 的场景：
- **记忆提取**：从对话中提取关键内容（`MemoryProcessor.extract_key_content`）
- **记忆融合**：新旧记忆合并去重（`MemoryProcessor.consolidate_memories`）
- **重要性评分**：评估记忆重要性（`MemoryProcessor.score_importance`）
- **三元组提取**：提取知识图谱三元组（`MemoryProcessor.extract_triples`）

**LLM 来源优先级**：

1. **Agent 自身 LLM 配置（推荐）**：记忆系统自动复用 Agent 绑定的 `llm_config`。
   在 Agent Builder 中配置 Agent 的 LLM 即可，记忆提取自动使用同一个模型。

2. **全局 `[models]` 配置（回退）**：如果 Agent 没有单独配置 LLM，回退到全局 LLM client。

这意味着**不需要在 `[models]` 中额外配置 LLM 供记忆系统使用**，只要 Agent 自身有可用的 LLM 即可。

### 3.3 向量模型配置（`[models]`）

记忆系统的向量检索使用 `[models.default_embedding]` 指定的嵌入模型。

| 配置项 | 说明 |
|--------|------|
| `default_embedding` | 默认向量模型名，必须与 `[[models.embeddings]]` 中的 `model` 字段匹配 |
| `[[models.embeddings]]` | 向量模型部署配置 |

**如果不想单独配置向量模型**，设置 `use_builtin_embedding = true`，MemPalace 会使用内置的 `all-MiniLM-L6-v2` 模型（本地运行，无需 API）。

---

## 四、最小可运行配置

**方式一：Agent 已有 LLM 配置（推荐）**

在 Agent Builder 中为 Agent 配置 LLM 后，记忆系统自动复用，只需配置存储：

```toml
[rag.storage.memory]
type = "mempalace"
use_builtin_embedding = true   # 使用内置向量模型，无需额外配置
enable_kg = false               # 关闭知识图谱
```

**方式二：Agent 没有 LLM 配置，需要全局回退**

```toml
[models]
default_llm = "gpt-4o"

[[models.llms]]
model = "gpt-4o"
model_type = "chat"
provider = "openai"
api_base = "https://api.openai.com/v1"
api_key = "sk-xxx"

[rag.storage.memory]
type = "mempalace"
use_builtin_embedding = true   # 使用内置向量模型，无需额外配置
enable_kg = false               # 关闭知识图谱
```

**说明**：
- `use_builtin_embedding = true` 意味着不需要配置 `[[models.embeddings]]`
- `enable_kg = false` 意味着不需要配置知识图谱
- 只要 Agent 有可用 LLM（自身配置或全局回退），记忆提取即可工作

---

## 五、生产环境推荐配置

```toml
[models]
default_llm = "qwen-plus"
default_embedding = "text-embedding-v3"

[[models.llms]]
model = "qwen-plus"
model_type = "chat"
provider = "dashscope"
api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "sk-xxx"

[[models.embeddings]]
model = "text-embedding-v3"
provider = "dashscope"
api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "sk-xxx"

[rag.storage.memory]
type = "mempalace"
palace_path = "/data/mempalace/palace"  # 生产环境使用持久化路径
enable_kg = true
default_wing = "production"
use_builtin_embedding = false           # 使用统一的向量模型
auto_memory = true
auto_memory_top_k = 10
auto_memory_max_distance = 0.3
```

---

## 六、配置验证

启动服务后，检查日志输出：

```
# 1. 检查 StorageManager 注册
[CoreV2Component] async_after_start called

# 2. 检查嵌入模型初始化
Register remote RemoteEmbeddingFactory

# 3. 检查记忆空间加载
[CoreV2Component] 加载记忆空间: xxx -> xxx
[CoreV2Component] MemoryIntegrationBundle 创建成功

# 4. 检查对话时记忆检索
[LongTermMemory] Retrieved X memories from Y spaces
```

---

## 七、常见问题

**Q: 记忆系统必须配置 `[models]` 中的 LLM 吗？**
A: 不需要。记忆系统优先复用 Agent 自身的 `llm_config`。只要在 Agent Builder 中为 Agent 配置了 LLM，记忆提取就自动使用该模型。`[models]` 中的 LLM 仅作为回退。

**Q: 不配置向量模型能用吗？**
A: 可以。设置 `use_builtin_embedding = true`，MemPalace 使用内置的 `all-MiniLM-L6-v2`。但效果不如统一配置的向量模型好。

**Q: 记忆提取必须用 LLM 吗？**
A: 是的。`MemoryProcessor.extract_key_content` 需要调用 LLM。LLM 来源：
1. Agent 自身的 `llm_config`（推荐，自动复用）
2. 全局 LLM client（回退，需在 `[models]` 配置）
如果两者都不可用，会自动回退到关键词匹配（效果差）。

**Q: 知识图谱（KG）必须开吗？**
A: 不是。`enable_kg = false` 可以关闭 KG。KG 主要用于实体关系追踪，不是记忆检索的核心依赖。

**Q: Letta Provider 怎么配？**
A: 将 `type` 改为 `letta`，并配置 `agent_id` 和 `api_key`：
```toml
[rag.storage.memory]
type = "letta"
# Letta 不使用 palace_path，使用 agent_id 标识
```
