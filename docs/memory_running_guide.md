# BAIZE Agent + MemPalace 记忆系统运行指南

## 运行前准备清单

### 1. 安装依赖

```bash
# MemPalace 核心库（必须）
pip install mempalace>=3.3.0

# ChromaDB（统一 embedding 模式需要）
pip install chromadb>=0.4.22

# 如果使用 Letta Provider（可选）
pip install letta-client
```

**LLM 不需要额外配置**：记忆系统自动复用 Agent 的 `llm_config`（即 Agent Builder 中为该 Agent 配置的模型），无需在 `[models]` 中单独配置。

### 2. 配置嵌入模型

记忆系统默认使用 OpenDerisk 的统一嵌入模型。确保配置文件中设置了 embedding：

```toml
# config.toml 或相应配置文件
[rag.embedding]
default_embedding = "your_embedding_model_name"
```

如果未配置嵌入模型，MemPalace 会自动回退到内置的 `all-MiniLM-L6-v2`。

### 3. 配置 MemPalace 存储路径（可选）

默认存储路径为 `~/.mempalace/palace`，可在配置中自定义：

```toml
[rag.storage.memory]
type = "mempalace"
palace_path = "/your/custom/path/to/palace"
enable_kg = true
default_wing = "default"
use_builtin_embedding = false
```

---

## 使用流程

### Step 1: 创建 Memory 类型知识空间

**方式一：前端创建**

1. 进入「知识空间」页面
2. 点击「创建知识空间」
3. 存储类型选择 **Memory**
4. 填写名称和描述
5. 保存

**方式二：API 创建**

```bash
curl -X POST http://localhost:8000/knowledge/space/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "项目记忆空间",
    "desc": "存储项目决策和偏好",
    "vector_type": "Memory",
    "storage_type": "Memory",
    "owner": "admin"
  }'
```

返回的 `knowledge_id` 就是后续绑定 Agent 的空间 ID。

### Step 2: 在 Agent Builder 中绑定记忆空间

1. 进入 **Agent Builder** 页面
2. 编辑目标 Agent
3. 切换到 **「记忆」Tab**
4. 列表中会显示所有 `storage_type=Memory` 的知识空间
5. 点击目标空间，右侧出现 ✅ 表示已绑定
6. 配置顶部选项：
   - **自动记忆**（auto_memory）：对话后自动提取写入，默认开启
   - **知识图谱**（enable_kg）：提取三元组写入 KG，默认开启
   - **检索数量**（top_k）：每次对话前检索的记忆条数，默认 5
7. 保存 Agent

**数据格式（保存在 `gpts_app_config.resource_memory`）：**

```json
[
  {
    "type": "memory",
    "name": "memory",
    "value": "{\"memories\":[{\"memory_id\":\"xxx\",\"memory_name\":\"项目记忆空间\"}],\"auto_memory\":true,\"enable_kg\":true,\"top_k\":5}",
    "version": "v2"
  }
]
```

### Step 3: 与 Agent 对话

绑定记忆空间后，Agent 对话自动具备记忆能力：

```
用户提问 → 记忆检索（HybridSearch） → 注入系统 Prompt → Agent 推理 → 回答
                                                            │
                                                            ▼
                                              自动提取关键内容 → 写入记忆空间
```

**无需手动操作**，记忆系统在以下节点自动运行：

| 节点 | 触发时机 | 执行内容 |
|------|---------|---------|
| Session Start | 新对话开始 | HybridSearch 检索 + Frozen Snapshot 捕获 |
| Turn End | 每次 Agent 回复完成 | LLM 提取关键内容 → 融合 → 写入 |
| Session End | 对话结束 | 三阶段晋升（Light→REM→Deep） |

### Step 4: 查看记忆内容

**通过工具查看**（Agent 对话中）：
- `memory_search`：搜索记忆
- `kg_query`：查询知识图谱

**通过数据库查看**：
- MemPalace 的 ChromaDB 数据存储在 `{palace_path}/derisk_chroma/` 目录下
- KG 数据可通过 `kg_query` 工具查询

---

## 验证记忆系统是否正常工作

### 检查 StorageManager 是否注册

```python
from derisk.component import SystemApp
from derisk_serve.rag.storage_manager import StorageManager

system_app = SystemApp.get_instance()
manager = system_app.get_component("storage_manager", StorageManager)
print(f"StorageManager: {manager is not None}")
```

### 检查记忆空间是否可用

```python
store = manager.create_memory_store("your_knowledge_id")
print(f"Store type: {type(store).__name__}")
print(f"Store ready: {store is not None}")
```

### 检查 Agent 是否正确加载记忆

在 Agent 对话的日志中查找以下关键字：

```
[CoreV2Component] 加载记忆空间: xxx -> xxx
[CoreV2Component] MemoryIntegrationBundle 创建成功
[LongTermMemory] Retrieved X memories from Y spaces
[LongTermMemory] Processed X memories for space xxx
```

### 手动测试记忆读写

```python
import asyncio
from derisk.component import SystemApp
from derisk_serve.rag.storage_manager import StorageManager

async def test_memory():
    system_app = SystemApp.get_instance()
    manager = system_app.get_component("storage_manager", StorageManager)

    # 创建 store
    store = manager.create_memory_store("your_knowledge_id")

    # 写入
    entry = await store.awrite_memory(
        content="测试记忆内容",
        wing="default",
        room="general",
    )
    print(f"写入成功: id={entry.id}")

    # 检索
    results = await store.asearch_memory(query="测试", top_k=5)
    print(f"检索到 {len(results)} 条结果")
    for r in results:
        print(f"  - {r.content[:50]}... (score: {r.score:.3f})")

asyncio.run(test_memory())
```

---

## 架构文件清单

所有新增/修改的文件（17 个，全部通过语法检查）：

| 文件 | 状态 |
|------|------|
| `derisk-core/.../storage/memory/processor.py` | ✅ 新建 |
| `derisk-core/.../storage/memory/strategy.py` | ✅ 新建 |
| `derisk-core/.../storage/memory/recall_tracker.py` | ✅ 新建 |
| `derisk-core/.../storage/memory/hybrid_search.py` | ✅ 新建 |
| `derisk-core/.../storage/memory/lifecycle.py` | ✅ 新建 |
| `derisk-core/.../storage/memory/snapshot.py` | ✅ 新建 |
| `derisk-core/.../storage/memory/promotion.py` | ✅ 新建 |
| `derisk-core/.../unified_memory/longterm_manager.py` | ✅ 增强 |
| `derisk-core/.../unified_memory/store_adapter.py` | ✅ 新建 |
| `derisk-core/.../unified_memory/pipeline.py` | ✅ 新建 |
| `derisk-core/.../unified_memory/__init__.py` | ✅ 更新 |
| `derisk-ext/.../memory/llm_processor.py` | ✅ 新建 |
| `derisk-ext/.../memory/__init__.py` | ✅ 新建 |
| `derisk-ext/.../storage/memory/letta_adapter.py` | ✅ 新建 |
| `derisk-ext/.../storage/memory/__init__.py` | ✅ 更新 |
| `derisk-serve/.../agent/core_v2_adapter.py` | ✅ 增强 |
| `derisk-serve/.../agent/app_to_v2_converter.py` | ✅ 增强 |
