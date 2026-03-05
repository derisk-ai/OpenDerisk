# Derisk记忆系统、上下文管理与Agent架构深度分析报告

## 目录
1. [纠正之前错误理解](#1-纠正之前错误理解)
2. [记忆系统实际架构对比](#2-记忆系统实际架构对比)
3. [统一记忆框架设计方案](#3-统一记忆框架设计方案)
4. [上下文超限处理改进方案](#4-上下文超限处理改进方案)
5. [Core_v2 Agent完整架构设计](#5-core_v2-agent完整架构设计)
6. [实施路线图](#6-实施路线图)

---

## 1. 纠正之前错误理解

### 1.1 之前的错误总结

| 错误项 | 错误理解 | 实际情况 |
|--------|----------|----------|
| Derisk Core 记忆 | 简单列表存储 | **三层记忆架构 + 向量化存储** |
| 向量化支持 | Core无向量化 | **LongTermMemory使用VectorStoreBase** |
| 数据库持久化 | 无持久化 | **支持Chroma、PostgreSQL等向量数据库** |
| 上下文压缩 | 无自动压缩 | **SessionCompaction自动触发（80%阈值）** |
| Core_v2 压缩 | 未说明 | **MemoryCompactor支持4种压缩策略** |

### 1.2 实际架构确认

**Derisk Core 确实使用：**
```
三层记忆架构:
SensoryMemory (瞬时记忆, buffer_size=0)
    ↓ threshold_to_short_term=0.1
ShortTermMemory (短期记忆, buffer_size=5)
    ↓ transfer_to_long_term
LongTermMemory (长期记忆, vector_store: VectorStoreBase)
    └── TimeWeightedEmbeddingRetriever (时间加权向量检索)
```

**向量化存储实现：**
```python
# 实际代码路径：/packages/derisk-core/src/derisk/agent/core/memory/long_term.py
class LongTermMemory(Memory, Generic[T]):
    def __init__(
        self,
        vector_store: VectorStoreBase,  # ⚠️ 确实使用向量存储
        ...
    ):
        self.memory_retriever = LongTermRetriever(
            index_store=vector_store  # Chroma/PostgreSQL向量数据库
        )

# 配置示例
memory = HybridMemory.from_chroma(
    vstore_name="agent_memory",
    vstore_path="/path/to/vector_db",
    embeddings=OpenAIEmbeddings(),  # OpenAI嵌入模型
)
```

**GptsMemory 双层存储：**
```python
# 内存缓存 + 数据库持久化
class ConversationCache:
    """内存层"""
    messages: Dict[str, GptsMessage]
    files: Dict[str, AgentFileMetadata]
    file_key_index: Dict[str, str]  # 文件索引
    
class GptsMemory:
    """持久化层"""
    _file_metadata_db_storage: Optional[Any]  # 数据库存储后端
    _work_log_db_storage: Optional[Any]
    _kanban_db_storage: Optional[Any]
```

---

## 2. 记忆系统实际架构对比

### 2.1 Claude Code 记忆架构

```
┌────────────────────────────────────────────────────────────────┐
│                   Claude Code Memory System                     │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: Static Memory (CLAUDE.md)                            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 加载方式:                                                │  │
│  │ - 递归向上查找目录                                       │  │
│  │ - 子目录按需加载                                         │  │
│  │ - 完整加载（无截断）                                     │  │
│  │ - 支持 @path 导入语法                                    │  │
│  │                                                          │  │
│  │ 存储位置:                                                │  │
│  │ - Managed Policy (组织级): /etc/claude-code/CLAUDE.md   │  │
│  │ - Project (项目级): ./CLAUDE.md                          │  │
│  │ - User (用户级): ~/.claude/CLAUDE.md                     │  │
│  │ - Local (本地): ./CLAUDE.local.md                        │  │
│  │                                                          │  │
│  │ Git共享: ✓ (团队协作友好)                                │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Layer 2: Auto Memory (动态学习)                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 存储位置: ~/.claude/projects/<project>/memory/          │  │
│  │                                                          │  │
│  │ ├── MEMORY.md         # 索引 (前200行自动加载)           │  │
│  │ ├── debugging.md      # 调试笔记                        │  │
│  │ ├── api-conventions.md # API约定                        │  │
│  │ └── patterns.md       # 代码模式                        │  │
│  │                                                          │  │
│  │ 特性:                                                    │  │
│  │ - Claude 自动写入学习内容                                │  │
│  │ - 按需读取主题文件                                       │  │
│  │ - 机器本地，不跨设备同步                                 │  │
│  │ - 子代理可独立记忆                                       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Layer 3: Rules System (.claude/rules/)                        │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 特性:                                                    │  │
│  │ - 路径特定规则 (paths frontmatter)                       │  │
│  │ - 条件加载（匹配文件时触发）                             │  │
│  │ - 模块化组织                                             │  │
│  │ - 支持符号链接共享                                       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  存储方式: 文件系统 (Markdown)                                  │
│  检索方式: 路径匹配 + 关键词                                    │
│  共享机制: Git 版本控制                                         │
│  语义搜索: ✗                                                    │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 2.2 Derisk Core 记忆架构

```
┌────────────────────────────────────────────────────────────────┐
│                   Derisk Core Memory System                     │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: SensoryMemory (瞬时记忆)                             │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 配置:                                                    │  │
│  │ - buffer_size: 0 (无限容量)                              │  │
│  │ - threshold_to_short_term: 0.1 (重要性过滤阈值)          │  │
│  │                                                          │  │
│  │ 功能:                                                    │  │
│  │ - 快速注册感知输入                                       │  │
│  │ - 重要性评分过滤                                         │  │
│  │ - 处理重复记忆                                           │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  Layer 2: ShortTermMemory (短期记忆)                           │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 基础实现:                                                │  │
│  │ - buffer_size: 5 (默认)                                  │  │
│  │ - 保留最近的记忆                                         │  │
│  │ - 溢出时转移到长期记忆                                   │  │
│  │                                                          │  │
│  │ 增强实现 (EnhancedShortTermMemory):                      │  │
│  │ - buffer_size: 10                                        │  │
│  │ - enhance_similarity_threshold: 0.7                      │  │
│  │ - enhance_threshold: 3                                   │  │
│  │ - 记忆合并与洞察提取                                     │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  Layer 3: LongTermMemory (长期记忆)                            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 存储: VectorStoreBase (向量数据库)                       │  │
│  │ - ChromaStore (默认推荐)                                 │  │
│  │ - PostgreSQL (pgvector)                                  │  │
│  │ - 其他向量数据库                                         │  │
│  │                                                          │  │
│  │ 检索器: LongTermRetriever                                │  │
│  │ - TimeWeightedEmbeddingRetriever                         │  │
│  │ - 时间衰减加权: decay_rate                               │  │
│  │ - 重要性加权: importance_weight                          │  │
│  │                                                          │  │
│  │ 评分公式:                                                │  │
│  │ score = α × similarity + β × importance + γ × recency   │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  GptsMemory (全局会话管理)                                      │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ TTL缓存: maxsize=200, ttl=10800 (3小时)                  │  │
│  │                                                          │  │
│  │ ConversationCache (内存层):                              │  │
│  │ - messages: Dict[str, GptsMessage]                       │  │
│  │ - actions: Dict[str, ActionOutput]                       │  │
│  │ - plans: Dict[str, GptsPlan]                             │  │
│  │ - files: Dict[str, AgentFileMetadata]  # 文件元数据     │  │
│  │ - file_key_index: Dict[str, str]       # 文件索引       │  │
│  │ - work_logs: List[WorkEntry]                              │  │
│  │ - kanban: Optional[Kanban]                                │  │
│  │ - todos: List[TodoItem]                                   │  │
│  │                                                          │  │
│  │ 持久化层:                                                │  │
│  │ - _file_metadata_db_storage: 数据库文件存储              │  │
│  │ - _work_log_db_storage: 数据库日志存储                   │  │
│  │ - _kanban_db_storage: 数据库看板存储                     │  │
│  │ - _todo_db_storage: 数据库任务存储                       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  存储方式: 向量数据库 + 关系数据库                              │
│  检索方式: 向量相似度 + 时间权重                                │
│  共享机制: 会话隔离                                             │
│  语义搜索: ✓                                                    │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 2.3 Derisk Core_v2 记忆架构

```
┌────────────────────────────────────────────────────────────────┐
│                   Derisk Core_v2 Memory System                  │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  VectorMemoryStore (向量化存储)                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 组件:                                                    │  │
│  │ - embedding_model: EmbeddingModel (向量嵌入)             │  │
│  │ - vector_store: VectorStore (向量存储)                   │  │
│  │ - auto_embed: bool = True                                │  │
│  │                                                          │  │
│  │ 方法:                                                    │  │
│  │ - add_memory(session_id, content, importance_score)      │  │
│  │ - search(query, top_k)                                   │  │
│  │ - search_by_embedding(embedding)                         │  │
│  │ - delete(session_id)                                     │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  MemoryCompactor (记忆压缩)                                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 压缩策略:                                                │  │
│  │ 1. LLM_SUMMARY - LLM摘要生成                             │  │
│  │ 2. SLIDING_WINDOW - 滑动窗口                             │  │
│  │ 3. IMPORTANCE_BASED - 基于重要性                         │  │
│  │ 4. HYBRID - 混合策略                                     │  │
│  │                                                          │  │
│  │ 组件:                                                    │  │
│  │ - ImportanceScorer (重要性评分)                          │  │
│  │ - KeyInfoExtractor (关键信息提取)                        │  │
│  │ - SummaryGenerator (摘要生成)                            │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ImportanceScorer (重要性评分)                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 评分维度:                                                │  │
│  │ - 角色评分: system(0.3), user(0.1), assistant(0.05)      │  │
│  │ - 内容评分: 关键词 + 模式匹配                            │  │
│  │ - 关键信息: has_critical_info (+0.3)                     │  │
│  │                                                          │  │
│  │ 关键词: important, critical, 关键, 重要, remember...    │  │
│  │ 模式: 日期, IP, 邮箱, URL...                             │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  KeyInfoExtractor (关键信息提取)                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 提取方式:                                                │  │
│  │ 1. 规则提取 (无LLM时)                                    │  │
│  │ 2. LLM提取 (有LLM时)                                     │  │
│  │                                                          │  │
│  │ 信息类型:                                                │  │
│  │ - fact: 事实信息                                         │  │
│  │ - decision: 决策                                         │  │
│  │ - constraint: 约束                                       │  │
│  │ - preference: 偏好                                       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 2.4 三方对比总结

| 维度 | Claude Code | Derisk Core | Derisk Core_v2 |
|------|-------------|-------------|----------------|
| **存储方式** | 文件系统 (Markdown) | 向量DB + 关系DB | 向量DB |
| **记忆层次** | 2层（静态+自动） | 3层（感官→短期→长期） | 1层（向量化） |
| **语义搜索** | ✗ | ✓ (向量相似度) | ✓ |
| **Git共享** | ✓ (团队友好) | ✗ (会话隔离) | ✗ |
| **文件索引** | 目录递归 | file_key_index | ✗ |
| **自动压缩** | ✓ (95%) | ✓ (80%) | ✓ (可配置) |
| **压缩策略** | 1种 | 1种 | 4种 |
| **持久化** | 文件 | 内存+数据库 | 向量存储 |

---

## 3. 统一记忆框架设计方案

### 3.1 设计目标

```
目标：
1. 结合Claude Code的Git友好共享机制
2. 保留Derisk的向量化语义搜索能力
3. 统一Core和Core_v2的记忆接口
4. 支持文件系统 + 向量数据库双层存储
```

### 3.2 统一记忆框架架构

```
┌────────────────────────────────────────────────────────────────┐
│                  UnifiedMemoryFramework                         │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                  MemoryInterface (统一接口)              │  │
│  │                                                          │  │
│  │  async def write(content, metadata) -> MemoryID          │  │
│  │  async def read(query, options) -> List[MemoryItem]      │  │
│  │  async def update(memory_id, content) -> bool            │  │
│  │  async def delete(memory_id) -> bool                     │  │
│  │  async def search(query, top_k, filters) -> List[...]    │  │
│  │  async def consolidate() -> ConsolidationResult          │  │
│  │  async def export(format) -> bytes                       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           │                                     │
│       ┌───────────────────┼───────────────────┐               │
│       │                   │                   │               │
│       ▼                   ▼                   ▼               │
│  ┌──────────┐       ┌──────────┐       ┌──────────┐          │
│  │ Layer 1  │       │ Layer 2  │       │ Layer 3  │          │
│  │ Working  │       │ Episodic │       │ Semantic │          │
│  │ Memory   │       │ Memory   │       │ Memory   │          │
│  └──────────┘       └──────────┘       └──────────┘          │
│       │                   │                   │               │
│       ▼                   ▼                   ▼               │
│  ┌──────────┐       ┌──────────┐       ┌──────────┐          │
│  │ Redis/   │       │ Vector   │       │ Knowledge│          │
│  │ KV Store │       │ DB       │       │ Graph    │          │
│  └──────────┘       └──────────┘       └──────────┘          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                  FileBackedStorage                        │  │
│  │                                                          │  │
│  │  功能:                                                   │  │
│  │  - Git友好的Markdown存储                                │  │
│  │  - 支持CLAUDE.md风格导入                                 │  │
│  │  - 团队共享                                             │  │
│  │  - @path 导入语法                                        │  │
│  │                                                          │  │
│  │  目录结构:                                               │  │
│  │  project_root/                                           │  │
│  │  ├── .agent_memory/                                      │  │
│  │  │   ├── PROJECT_MEMORY.md   # 项目共享记忆 (Git tracked) │  │
│  │  │   ├── TEAM_RULES.md       # 团队规则                  │  │
│  │  │   └── sessions/           # 会话记忆 (gitignored)     │  │
│  │  │       └── <session_id>/                               │  │
│  │  │           ├── MEMORY.md   # 会话索引                  │  │
│  │  │           └── topics/     # 主题文件                  │  │
│  │  └── .agent_memory.local/    # 本地覆盖 (gitignored)     │  │
│  │                                                          │  │
│  │  同步策略:                                               │  │
│  │  - write时同步写入文件和向量库                           │  │
│  │  - 启动时从文件加载共享记忆                              │  │
│  │  - 支持合并远程更新                                      │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 3.3 核心接口设计

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime
import os
from pathlib import Path

class MemoryType(str, Enum):
    WORKING = "working"        # 工作记忆 - 当前对话
    EPISODIC = "episodic"      # 情景记忆 - 历史对话
    SEMANTIC = "semantic"      # 语义记忆 - 知识提取
    SHARED = "shared"          # 共享记忆 - 团队共享


@dataclass
class MemoryItem:
    """统一记忆单元"""
    id: str
    content: str
    memory_type: MemoryType
    importance: float = 0.5
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    
    # 文件系统关联
    file_path: Optional[str] = None
    source: str = "agent"  # agent | user | project | team


@dataclass
class SearchOptions:
    """检索选项"""
    top_k: int = 5
    min_importance: float = 0.0
    memory_types: Optional[List[MemoryType]] = None
    time_range: Optional[tuple] = None
    sources: Optional[List[str]] = None


class UnifiedMemoryInterface(ABC):
    """统一记忆接口"""
    
    @abstractmethod
    async def write(
        self, 
        content: str, 
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_file: bool = True
    ) -> str:
        """写入记忆，返回MemoryID"""
        pass
    
    @abstractmethod
    async def read(
        self, 
        query: str, 
        options: Optional[SearchOptions] = None
    ) -> List[MemoryItem]:
        """检索记忆"""
        pass
    
    @abstractmethod
    async def search_similar(
        self, 
        query: str, 
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[MemoryItem]:
        """向量相似度搜索"""
        pass
    
    @abstractmethod
    async def consolidate(
        self,
        source_type: MemoryType,
        target_type: MemoryType,
        criteria: Optional[Dict[str, Any]] = None
    ) -> int:
        """记忆巩固 - 从一个层级转移到另一个层级"""
        pass
    
    @abstractmethod
    async def export(
        self, 
        format: str = "markdown",
        memory_types: Optional[List[MemoryType]] = None
    ) -> str:
        """导出记忆"""
        pass
    
    @abstractmethod
    async def import_from_file(
        self, 
        file_path: str,
        memory_type: MemoryType = MemoryType.SHARED
    ) -> int:
        """从文件导入记忆"""
        pass


class UnifiedMemoryManager(UnifiedMemoryInterface):
    """统一记忆管理器 - 实现双层存储"""
    
    def __init__(
        self,
        project_root: str,
        vector_store: "VectorStoreBase",
        embedding_model: "EmbeddingModel",
        working_store: Optional["KVStore"] = None,
    ):
        self.project_root = Path(project_root)
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.working_store = working_store
        
        # 文件存储路径
        self.memory_dir = self.project_root / ".agent_memory"
        self.shared_file = self.memory_dir / "PROJECT_MEMORY.md"
        
        # 初始化
        self._init_file_structure()
        
    def _init_file_structure(self):
        """初始化文件结构"""
        self.memory_dir.mkdir(exist_ok=True)
        (self.memory_dir / "sessions").mkdir(exist_ok=True)
        
        if not self.shared_file.exists():
            self.shared_file.write_text("# Project Memory\n\n")
    
    async def write(
        self, 
        content: str, 
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_file: bool = True
    ) -> str:
        """写入记忆 - 双写策略"""
        import uuid
        memory_id = str(uuid.uuid4())
        
        # 1. 向量化
        embedding = await self.embedding_model.embed(content)
        
        # 2. 创建记忆单元
        item = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            embedding=embedding,
            metadata=metadata or {},
        )
        
        # 3. 写入向量存储
        await self.vector_store.add([{
            "id": memory_id,
            "content": content,
            "embedding": embedding,
            "metadata": {
                **(metadata or {}),
                "memory_type": memory_type.value,
            }
        }])
        
        # 4. 写入文件系统（可选）
        if sync_to_file and memory_type in [MemoryType.SHARED, MemoryType.SEMANTIC]:
            await self._sync_to_file(item)
        
        return memory_id
    
    async def _sync_to_file(self, item: MemoryItem):
        """同步到文件系统"""
        if item.memory_type == MemoryType.SHARED:
            # 追加到共享文件
            with open(self.shared_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n## {datetime.now().isoformat()}\n")
                f.write(item.content)
        
        # 支持 @导入 语法
        if "imports" in item.metadata:
            for import_path in item.metadata["imports"]:
                full_path = self.project_root / import_path
                if full_path.exists():
                    content = full_path.read_text()
                    await self.write(
                        content, 
                        MemoryType.SHARED,
                        {"source": str(full_path)}
                    )
    
    async def search_similar(
        self, 
        query: str, 
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[MemoryItem]:
        """向量相似度搜索"""
        # 1. 查询向量化
        query_embedding = await self.embedding_model.embed(query)
        
        # 2. 向量检索
        results = await self.vector_store.similarity_search(
            query_embedding, 
            k=top_k,
            filters=filters
        )
        
        # 3. 转换为MemoryItem
        items = []
        for result in results:
            items.append(MemoryItem(
                id=result["id"],
                content=result["content"],
                embedding=result.get("embedding"),
                importance=result.get("metadata", {}).get("importance", 0.5),
                memory_type=MemoryType(result.get("metadata", {}).get("memory_type", "working")),
                metadata=result.get("metadata", {}),
            ))
        
        return items
    
    async def load_shared_memory(self) -> List[MemoryItem]:
        """加载共享记忆（启动时调用）"""
        items = []
        
        # 从共享文件加载
        if self.shared_file.exists():
            content = self.shared_file.read_text()
            # 解析 @导入
            resolved = self._resolve_imports(content)
            items.append(MemoryItem(
                id="shared_project",
                content=resolved,
                memory_type=MemoryType.SHARED,
                metadata={"source": str(self.shared_file)}
            ))
        
        return items
    
    def _resolve_imports(self, content: str) -> str:
        """解析 @导入 语法"""
        import re
        pattern = r'@([\w/.-]+)'
        
        def replace(match):
            path = match.group(1)
            full_path = self.project_root / path
            if full_path.exists():
                return full_path.read_text()
            return match.group(0)
        
        return re.sub(pattern, replace, content)
    
    async def consolidate(
        self,
        source_type: MemoryType,
        target_type: MemoryType,
        criteria: Optional[Dict[str, Any]] = None
    ) -> int:
        """记忆巩固"""
        # 例如：WORKING -> EPISODIC
        # 基于 importance 和 access_count 进行筛选
        pass
```

### 3.4 与Claude Code特性对齐

```python
# 实现 Claude Code 风格的功能

class ClaudeCodeCompatibleMemory(UnifiedMemoryManager):
    """Claude Code 兼容的记忆系统"""
    
    async def load_claudemd_style(self):
        """加载CLAUDE.md风格的配置"""
        # 递归向上查找
        for parent in self.project_root.parents:
            claude_md = parent / "CLAUDE.md"
            if claude_md.exists():
                content = claude_md.read_text()
                resolved = self._resolve_imports(content)
                await self.write(
                    resolved,
                    MemoryType.SHARED,
                    {"source": str(claude_md), "scope": "project"}
                )
        
        # 用户级
        user_claude = Path.home() / ".claude" / "CLAUDE.md"
        if user_claude.exists():
            content = user_claude.read_text()
            await self.write(
                content,
                MemoryType.SHARED,
                {"source": str(user_claude), "scope": "user"}
            )
    
    async def auto_memory(self, session_id: str, content: str):
        """自动记忆 - 模拟Claude Code的Auto Memory"""
        session_dir = self.memory_dir / "sessions" / session_id
        session_dir.mkdir(exist_ok=True)
        
        memory_file = session_dir / "MEMORY.md"
        
        # 检查行数限制
        if memory_file.exists():
            lines = memory_file.read_text().split("\n")
            if len(lines) > 200:
                # 移动详细内容到主题文件
                await self._archive_to_topic(session_dir, memory_file)
        
        # 追加新内容
        with open(memory_file, "a", encoding="utf-8") as f:
            f.write(f"\n{content}\n")
    
    async def _archive_to_topic(self, session_dir: Path, memory_file: Path):
        """归档到主题文件"""
        # 使用LLM提取主题
        content = memory_file.read_text()
        topics = await self._extract_topics(content)
        
        for topic_name, topic_content in topics.items():
            topic_file = session_dir / f"{topic_name}.md"
            with open(topic_file, "w", encoding="utf-8") as f:
                f.write(topic_content)
        
        # 更新索引文件
        with open(memory_file, "w", encoding="utf-8") as f:
            f.write("# Memory Index\n\n")
            for topic_name in topics.keys():
                f.write(f"- @{topic_name}.md\n")
```

---

## 4. 上下文超限处理改进方案

### 4.1 Claude Code 机制分析

```python
# Claude Code 压缩机制

class ClaudeCodeCompaction:
    """Claude Code 风格的压缩"""
    
    # 触发阈值
    AUTO_COMPACT_THRESHOLD = 0.95  # 95%
    
    # 特性
    # 1. 自动触发
    # 2. LLM生成摘要
    # 3. CLAUDE.md完整保留（压缩后重新加载）
    # 4. 子代理独立上下文
    
    async def compact(self, messages: List[Message]) -> List[Message]:
        # 1. 生成摘要
        summary = await self._generate_summary(messages[:-3])
        
        # 2. 保留最近消息
        recent = messages[-3:]
        
        # 3. 重新加载CLAUDE.md
        claude_md = await self._reload_claude_md()
        
        # 4. 构建新消息列表
        return [
            SystemMessage(content=claude_md),
            SystemMessage(content=f"[Previous context summary]\n{summary}"),
            *recent
        ]
```

### 4.2 Derisk Core 改进方案

```python
# 当前 Derisk Core SessionCompaction 分析

class CurrentSessionCompaction:
    """当前实现"""
    
    # 触发阈值: 80% (比Claude Code更早触发)
    DEFAULT_THRESHOLD_RATIO = 0.8
    
    # 保留策略: 最近3条消息
    RECENT_MESSAGES_KEEP = 3
    
    # 问题:
    # 1. 无CLAUDE.md重新加载机制
    # 2. 摘要生成不够智能
    # 3. 无关键信息保护


class ImprovedSessionCompaction:
    """改进方案 - 借鉴Claude Code"""
    
    def __init__(
        self,
        llm_client: LLMClient,
        context_window: int = 128000,
        threshold_ratio: float = 0.80,  # 保持80%阈值
        shared_memory_loader: Optional[Callable] = None,
    ):
        self.llm_client = llm_client
        self.context_window = context_window
        self.threshold = int(context_window * threshold_ratio)
        self.shared_memory_loader = shared_memory_loader
        
        # 新增：内容保护策略
        self.content_protector = ContentProtector()
        
    async def compact(
        self, 
        messages: List[AgentMessage],
        force: bool = False
    ) -> CompactionResult:
        """改进的压缩流程"""
        
        # 1. 检查是否需要压缩
        current_tokens = self._estimate_tokens(messages)
        if not force and current_tokens < self.threshold:
            return CompactionResult(success=False, messages_removed=0)
        
        # 2. 保护重要内容（新增）
        protected_content = await self.content_protector.extract(messages)
        
        # 3. 选择需要压缩的消息
        to_compact, to_keep = self._select_messages(messages)
        
        # 4. 生成智能摘要（改进）
        summary = await self._generate_smart_summary(to_compact)
        
        # 5. 重新加载共享记忆（新增，借鉴Claude Code）
        if self.shared_memory_loader:
            shared_memory = await self.shared_memory_loader()
            summary = f"{shared_memory}\n\n{summary}"
        
        # 6. 构建新消息列表
        new_messages = [
            AgentMessage(
                role="system",
                content="[Context Summary]\n" + summary,
                metadata={"type": "compaction_summary"}
            ),
            *protected_content,  # 保护的关键内容
            *to_keep
        ]
        
        return CompactionResult(
            success=True,
            compacted_messages=new_messages,
            original_tokens=current_tokens,
            new_tokens=self._estimate_tokens(new_messages),
        )
    
    async def _generate_smart_summary(
        self, 
        messages: List[AgentMessage]
    ) -> str:
        """智能摘要 - 结合LLM和规则"""
        
        # 1. 提取关键信息
        key_info = await self._extract_key_info(messages)
        
        # 2. LLM生成摘要
        prompt = f"""请总结以下对话的关键内容，保留：
- 重要的决策和结论
- 用户偏好和约束
- 关键的上下文信息

关键信息：{key_info}

对话记录：
{self._format_messages(messages)}

请生成简洁的摘要（不超过500字）："""

        summary = await self.llm_client.acompletion([
            {"role": "user", "content": prompt}
        ])
        
        return summary
    
    async def _extract_key_info(
        self, 
        messages: List[AgentMessage]
    ) -> Dict[str, Any]:
        """提取关键信息"""
        from derisk.agent.core_v2.memory_compaction import KeyInfoExtractor
        
        extractor = KeyInfoExtractor(self.llm_client)
        key_infos = await extractor.extract([
            {"role": m.role, "content": m.content} 
            for m in messages
        ])
        
        return {
            "facts": [k for k in key_infos if k.category == "fact"],
            "decisions": [k for k in key_infos if k.category == "decision"],
            "constraints": [k for k in key_infos if k.category == "constraint"],
        }


class ContentProtector:
    """内容保护器 - 保护重要内容不被压缩"""
    
    CODE_BLOCK_PATTERN = r'```[\s\S]*?```'
    THINKING_PATTERN = r'<thinking>[\s\S]*?</thinking>'
    FILE_PATH_PATTERN = r'["\']?(/[^\s"\']+)["\']?'
    
    async def extract(
        self, 
        messages: List[AgentMessage]
    ) -> List[AgentMessage]:
        """提取需要保护的内容"""
        import re
        
        protected = []
        
        for msg in messages:
            # 提取代码块
            code_blocks = re.findall(self.CODE_BLOCK_PATTERN, msg.content)
            
            # 提取思考链
            thinking_chains = re.findall(self.THINKING_PATTERN, msg.content)
            
            # 组合保护内容
            if code_blocks or thinking_chains:
                protected_content = ""
                if code_blocks:
                    protected_content += "\n\n[Protected Code]\n" + "\n".join(code_blocks)
                if thinking_chains:
                    protected_content += "\n\n[Protected Reasoning]\n" + "\n".join(thinking_chains)
                
                protected.append(AgentMessage(
                    role="system",
                    content=protected_content,
                    metadata={"type": "protected_content"}
                ))
        
        return protected
```

### 4.3 Core_v2 自动压缩配置

```python
# Core_v2 自动压缩配置

from dataclasses import dataclass
from enum import Enum

class CompactionTrigger(str, Enum):
    MANUAL = "manual"           # 手动触发
    THRESHOLD = "threshold"     # 阈值触发
    SCHEDULED = "scheduled"     # 定时触发
    ADAPTIVE = "adaptive"       # 自适应触发


@dataclass
class AutoCompactionConfig:
    """自动压缩配置"""
    
    # 触发方式
    trigger: CompactionTrigger = CompactionTrigger.THRESHOLD
    
    # 阈值触发配置
    threshold_ratio: float = 0.80           # 80%触发
    absolute_threshold: Optional[int] = None # 或绝对token数
    
    # 压缩策略
    strategy: str = "hybrid"                # llm_summary | sliding_window | importance_based | hybrid
    keep_recent: int = 3                     # 保留最近N条消息
    keep_important: bool = True              # 保留高重要性消息
    importance_threshold: float = 0.7        # 重要性阈值
    
    # 智能特性
    content_protection: bool = True          # 内容保护
    reload_shared_memory: bool = True        # 重新加载共享记忆
    key_info_extraction: bool = True         # 关键信息提取
    
    # 自适应触发配置
    adaptive_check_interval: int = 5         # 每5次对话检查一次
    adaptive_growth_threshold: float = 0.1   # 增长率阈值


class AutoCompactionManager:
    """自动压缩管理器"""
    
    def __init__(
        self,
        config: AutoCompactionConfig,
        memory: UnifiedMemoryInterface,
        llm_client: LLMClient,
    ):
        self.config = config
        self.memory = memory
        self.compactor = ImprovedSessionCompaction(
            llm_client=llm_client,
            threshold_ratio=config.threshold_ratio,
            shared_memory_loader=self._load_shared_memory if config.reload_shared_memory else None,
        )
        
        # 统计
        self._message_count = 0
        self._last_compaction_tokens = 0
        
    async def check_and_compact(
        self, 
        messages: List[AgentMessage],
        force: bool = False
    ) -> CompactionResult:
        """检查并执行压缩"""
        
        if self.config.trigger == CompactionTrigger.THRESHOLD:
            return await self._threshold_compact(messages, force)
        
        elif self.config.trigger == CompactionTrigger.ADAPTIVE:
            return await self._adaptive_compact(messages, force)
        
        return CompactionResult(success=False)
    
    async def _threshold_compact(
        self, 
        messages: List[AgentMessage],
        force: bool
    ) -> CompactionResult:
        """阈值触发压缩"""
        current_tokens = self.compactor._estimate_tokens(messages)
        threshold = int(self.compactor.context_window * self.config.threshold_ratio)
        
        if current_tokens >= threshold or force:
            return await self.compactor.compact(messages, force=force)
        
        return CompactionResult(success=False)
    
    async def _adaptive_compact(
        self, 
        messages: List[AgentMessage],
        force: bool
    ) -> CompactionResult:
        """自适应触发压缩"""
        self._message_count += 1
        
        # 定期检查
        if self._message_count % self.config.adaptive_check_interval != 0:
            return CompactionResult(success=False)
        
        current_tokens = self.compactor._estimate_tokens(messages)
        
        # 计算增长率
        if self._last_compaction_tokens > 0:
            growth_rate = (current_tokens - self._last_compaction_tokens) / self._last_compaction_tokens
            
            # 如果增长率过快，提前压缩
            if growth_rate > self.config.adaptive_growth_threshold:
                return await self.compactor.compact(messages, force=False)
        
        # 正常阈值检查
        threshold = int(self.compactor.context_window * self.config.threshold_ratio)
        if current_tokens >= threshold:
            result = await self.compactor.compact(messages, force=False)
            self._last_compaction_tokens = self.compactor._estimate_tokens(result.compacted_messages)
            return result
        
        return CompactionResult(success=False)
    
    async def _load_shared_memory(self) -> str:
        """加载共享记忆"""
        items = await self.memory.read(
            query="",
            options=SearchOptions(memory_types=[MemoryType.SHARED])
        )
        return "\n\n".join([item.content for item in items])
```

---

## 5. Core_v2 Agent完整架构设计

### 5.1 设计原则

```
设计原则：
1. 借鉴Claude Code的子代理机制和Agent Teams
2. 保留Core_v2的简洁接口(think/decide/act)
3. 增强多Agent协作能力
4. 统一记忆框架集成
5. 生产就绪的可靠性
```

### 5.2 完整架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Derisk Core_v2 完整架构                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                         AgentBase (核心)                           │ │
│  │                                                                    │ │
│  │  接口:                                                             │ │
│  │  ├── think(message) → AsyncIterator[str]     # 流式思考          │ │
│  │  ├── decide(message) → Decision              # 决策               │ │
│  │  ├── act(decision) → ActionResult            # 执行               │ │
│  │  └── run(message) → AsyncIterator[str]       # 主循环             │ │
│  │                                                                    │ │
│  │  状态机:                                                           │ │
│  │  IDLE → THINKING → DECIDING → ACTING → RESPONDING → IDLE          │ │
│  │                           ↓                                        │ │
│  │                       TERMINATED                                   │ │
│  │                                                                    │ │
│  │  配置驱动:                                                         │ │
│  │  ├── AgentInfo          # 声明式配置                               │ │
│  │  ├── PermissionRuleset  # 权限规则                                 │ │
│  │  └── ContextPolicy      # 上下文策略                               │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│       ┌──────────────────────┼──────────────────────┐                 │
│       │                      │                      │                 │
│       ▼                      ▼                      ▼                 │
│  ┌──────────┐          ┌──────────┐          ┌──────────┐            │
│  │Subagent  │          │  Team    │          │  Memory  │            │
│  │ Manager  │          │ Manager  │          │ Manager  │            │
│  └──────────┘          └──────────┘          └──────────┘            │
│       │                      │                      │                 │
│       │                      │                      │                 │
│       ▼                      ▼                      ▼                 │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                        协作层 (Collaboration)                       │ │
│  │                                                                    │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │ │
│  │  │  SubagentPool   │  │   AgentTeam     │  │  SharedMemory   │   │ │
│  │  │                 │  │                 │  │                 │   │ │
│  │  │ - delegate()    │  │ - spawn()       │  │ - read()        │   │ │
│  │  │ - resume()      │  │ - coordinate()  │  │ - write()       │   │ │
│  │  │ - terminate()   │  │ - broadcast()   │  │ - search()      │   │ │
│  │  │ - get_status()  │  │ - cleanup()     │  │ - export()      │   │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘   │ │
│  │                                                                    │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │                    TaskCoordination                          │ │ │
│  │  │                                                              │ │ │
│  │  │  TaskList:                                                   │ │ │
│  │  │  ├── pending_tasks: List[Task]                               │ │ │
│  │  │  ├── in_progress: Dict[agent_id, Task]                       │ │ │
│  │  │  ├── completed: List[TaskResult]                             │ │ │
│  │  │  └── dependencies: Dict[task_id, List[task_id]]              │ │ │
│  │  │                                                              │ │ │
│  │  │  方法:                                                       │ │ │
│  │  │  ├── claim_task(agent_id, task_id) → bool                    │ │ │
│  │  │  ├── complete_task(task_id, result)                          │ │ │
│  │  │  ├── get_next_task(agent_id) → Task                          │ │ │
│  │  │  └── resolve_dependencies()                                  │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                        执行层 (Execution)                           │ │
│  │                                                                    │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │ │
│  │  │  LLMAdapter     │  │  ToolRegistry   │  │  PermissionSys  │   │ │
│  │  │                 │  │                 │  │                 │   │ │
│  │  │ - acomplete()   │  │ - register()    │  │ - check()       │   │ │
│  │  │ - astream()     │  │ - execute()     │  │ - ask_user()    │   │ │
│  │  │ - count_tokens()│  │ - get_spec()    │  │ - deny()        │   │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘   │ │
│  │                                                                    │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │                  AutoCompaction                              │ │ │
│  │  │                                                              │ │ │
│  │  │  配置:                                                       │ │ │
│  │  │  - trigger: threshold | adaptive | scheduled                 │ │ │
│  │  │  - threshold_ratio: 0.80                                     │ │ │
│  │  │  - strategy: hybrid                                          │ │ │
│  │  │  - content_protection: true                                  │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                        存储层 (Storage)                             │ │
│  │                                                                    │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐   │ │
│  │  │ UnifiedMemory   │  │  FileStorage    │  │  VectorStore    │   │ │
│  │  │                 │  │                 │  │                 │   │ │
│  │  │ - write()       │  │ - save_file()   │  │ - add()         │   │ │
│  │  │ - read()        │  │ - read_file()   │  │ - search()      │   │ │
│  │  │ - search()      │  │ - list_files()  │  │ - delete()      │   │ │
│  │  │ - export()      │  │ - metadata()    │  │                 │   │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.3 核心代码实现

```python
# 完整的 Core_v2 Agent 实现

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, AsyncIterator, Callable
from datetime import datetime
import asyncio
from pathlib import Path

# ============== 状态定义 ==============

class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    DECIDING = "deciding"
    ACTING = "acting"
    RESPONDING = "responding"
    WAITING = "waiting"
    ERROR = "error"
    TERMINATED = "terminated"


class DecisionType(str, Enum):
    RESPONSE = "response"          # 直接回复
    TOOL_CALL = "tool_call"        # 工具调用
    SUBAGENT = "subagent"          # 委托子代理
    TEAM_TASK = "team_task"        # 团队任务分配
    TERMINATE = "terminate"        # 终止
    WAIT = "wait"                  # 等待


# ============== 数据结构 ==============

@dataclass
class Decision:
    """决策结果"""
    type: DecisionType
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    subagent_name: Optional[str] = None
    subagent_task: Optional[str] = None
    team_task: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


@dataclass
class ActionResult:
    """执行结果"""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentInfo:
    """Agent配置"""
    name: str
    description: str
    role: str = "assistant"
    
    # 能力配置
    tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    
    # 执行配置
    max_steps: int = 10
    timeout: int = 300
    
    # 模型配置
    model: str = "inherit"  # inherit | specific model name
    
    # 权限配置
    permission_ruleset: Optional[Dict[str, Any]] = None
    
    # 记忆配置
    memory_enabled: bool = True
    memory_scope: str = "session"  # session | project | user
    
    # 子代理配置
    subagents: List[str] = field(default_factory=list)
    
    # 团队配置
    can_spawn_team: bool = False
    team_role: str = "worker"  # coordinator | worker | specialist | reviewer


# ============== 核心接口 ==============

class AgentBase(ABC):
    """Agent基类 - think/decide/act 三阶段"""
    
    def __init__(
        self,
        info: AgentInfo,
        memory: Optional["UnifiedMemoryInterface"] = None,
        tools: Optional["ToolRegistry"] = None,
        permission_checker: Optional["PermissionChecker"] = None,
    ):
        self.info = info
        self.memory = memory
        self.tools = tools or ToolRegistry()
        self.permission_checker = permission_checker or PermissionChecker()
        
        # 状态
        self._state = AgentState.IDLE
        self._current_step = 0
        self._messages: List[Dict[str, Any]] = []
        
        # 子代理管理
        self._subagent_manager: Optional["SubagentManager"] = None
        self._team_manager: Optional["TeamManager"] = None
        
    @abstractmethod
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """思考阶段 - 流式输出"""
        pass
    
    @abstractmethod
    async def decide(self, context: Dict[str, Any], **kwargs) -> Decision:
        """决策阶段"""
        pass
    
    @abstractmethod
    async def act(self, decision: Decision, **kwargs) -> ActionResult:
        """执行阶段"""
        pass
    
    async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
        """主执行循环"""
        self._state = AgentState.THINKING
        self._current_step = 0
        self.add_message("user", message)
        
        while self._current_step < self.info.max_steps:
            try:
                # 1. 思考阶段
                thinking_output = []
                if stream:
                    async for chunk in self.think(message):
                        thinking_output.append(chunk)
                        yield f"[THINKING] {chunk}"
                
                # 2. 决策阶段
                self._state = AgentState.DECIDING
                context = {
                    "message": message,
                    "thinking": "".join(thinking_output),
                    "history": self._messages,
                }
                decision = await self.decide(context)
                
                # 3. 根据决策类型处理
                if decision.type == DecisionType.RESPONSE:
                    self._state = AgentState.RESPONDING
                    yield decision.content
                    self.add_message("assistant", decision.content)
                    break
                    
                elif decision.type == DecisionType.TOOL_CALL:
                    self._state = AgentState.ACTING
                    result = await self.act(decision)
                    yield f"\n[TOOL: {decision.tool_name}]\n{result.output}"
                    self.add_message("system", result.output, {"tool": decision.tool_name})
                    message = result.output
                    
                elif decision.type == DecisionType.SUBAGENT:
                    self._state = AgentState.ACTING
                    result = await self._delegate_to_subagent(decision)
                    yield f"\n[SUBAGENT: {decision.subagent_name}]\n{result.output}"
                    message = result.output
                    
                elif decision.type == DecisionType.TEAM_TASK:
                    self._state = AgentState.ACTING
                    result = await self._assign_team_task(decision)
                    yield f"\n[TEAM TASK]\n{result.output}"
                    message = result.output
                    
                elif decision.type == DecisionType.TERMINATE:
                    break
                    
                self._current_step += 1
                
            except Exception as e:
                self._state = AgentState.ERROR
                yield f"\n[ERROR] {str(e)}"
                break
        
        self._state = AgentState.IDLE
    
    def add_message(self, role: str, content: str, metadata: Dict = None):
        self._messages.append({
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        })
    
    async def _delegate_to_subagent(self, decision: Decision) -> ActionResult:
        """委托给子代理"""
        if not self._subagent_manager:
            return ActionResult(success=False, output="", error="No subagent manager")
        
        result = await self._subagent_manager.delegate(
            subagent_name=decision.subagent_name,
            task=decision.subagent_task,
            parent_messages=self._messages,
        )
        return ActionResult(
            success=result.success,
            output=result.output,
            metadata={"subagent": decision.subagent_name}
        )
    
    async def _assign_team_task(self, decision: Decision) -> ActionResult:
        """分配团队任务"""
        if not self._team_manager:
            return ActionResult(success=False, output="", error="No team manager")
        
        result = await self._team_manager.assign_task(decision.team_task)
        return ActionResult(
            success=result.success,
            output=result.output,
        )


# ============== 子代理管理器 ==============

class SubagentManager:
    """子代理管理器 - 借鉴Claude Code"""
    
    def __init__(
        self,
        agent_registry: "AgentRegistry",
        memory: Optional["UnifiedMemoryInterface"] = None,
    ):
        self.registry = agent_registry
        self.memory = memory
        
        # 运行中的子代理
        self._active_subagents: Dict[str, "SubagentSession"] = {}
        
    async def delegate(
        self,
        subagent_name: str,
        task: str,
        parent_messages: Optional[List[Dict]] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        background: bool = False,
    ) -> "SubagentResult":
        """委托任务给子代理"""
        
        # 1. 获取子代理
        subagent = self.registry.get_agent(subagent_name)
        if not subagent:
            raise ValueError(f"Subagent '{subagent_name}' not found")
        
        # 2. 创建会话
        session = SubagentSession(
            subagent_name=subagent_name,
            task=task,
            parent_context=parent_messages,
            context=context or {},
        )
        
        # 3. 运行子代理
        self._active_subagents[session.session_id] = session
        
        try:
            if background:
                # 后台执行
                asyncio.create_task(self._run_subagent(session, subagent))
                return SubagentResult(
                    success=True,
                    output="",
                    session_id=session.session_id,
                    status="running"
                )
            else:
                # 前台执行
                result = await asyncio.wait_for(
                    self._run_subagent(session, subagent),
                    timeout=timeout
                )
                return result
        except asyncio.TimeoutError:
            return SubagentResult(
                success=False,
                output="",
                error="Timeout",
                session_id=session.session_id
            )
    
    async def _run_subagent(
        self, 
        session: "SubagentSession",
        subagent: AgentBase
    ) -> "SubagentResult":
        """运行子代理"""
        output_parts = []
        
        try:
            async for chunk in subagent.run(session.task):
                output_parts.append(chunk)
                session.output_chunks.append(chunk)
            
            session.status = "completed"
            return SubagentResult(
                success=True,
                output="".join(output_parts),
                session_id=session.session_id,
            )
        except Exception as e:
            session.status = "failed"
            return SubagentResult(
                success=False,
                output="".join(output_parts),
                error=str(e),
                session_id=session.session_id,
            )
    
    async def resume(self, session_id: str) -> "SubagentResult":
        """恢复子代理会话"""
        session = self._active_subagents.get(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found")
        
        # 继续执行
        ...
    
    def get_available_subagents(self) -> List[str]:
        """获取可用的子代理列表"""
        return self.registry.list_agents()


@dataclass
class SubagentSession:
    """子代理会话"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subagent_name: str = ""
    task: str = ""
    parent_context: Optional[List[Dict]] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    status: str = "pending"  # pending | running | completed | failed
    output_chunks: List[str] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class SubagentResult:
    """子代理结果"""
    success: bool
    output: str
    error: Optional[str] = None
    session_id: Optional[str] = None
    status: str = "completed"


# ============== 团队管理器 ==============

class TeamManager:
    """团队管理器 - 借鉴Claude Code Agent Teams"""
    
    def __init__(
        self,
        coordinator: AgentBase,
        memory: Optional["UnifiedMemoryInterface"] = None,
    ):
        self.coordinator = coordinator
        self.memory = memory
        
        # 团队成员
        self._workers: Dict[str, AgentBase] = {}
        
        # 任务协调
        self._task_list = TaskList()
        self._task_file_lock = asyncio.Lock()
        
        # 通信
        self._mailbox: Dict[str, asyncio.Queue] = {}
    
    async def spawn_teammate(
        self,
        name: str,
        role: str,
        info: AgentInfo,
    ) -> AgentBase:
        """生成队友"""
        from derisk.agent.core_v2.agent_base import ProductionAgent
        
        agent = ProductionAgent(info=info)
        self._workers[name] = agent
        self._mailbox[name] = asyncio.Queue()
        
        return agent
    
    async def assign_task(self, task_config: Dict[str, Any]) -> ActionResult:
        """分配任务"""
        task = Task(
            id=str(uuid.uuid4()),
            description=task_config.get("description"),
            assigned_to=task_config.get("assigned_to"),
            dependencies=task_config.get("dependencies", []),
        )
        
        async with self._task_file_lock:
            self._task_list.add_task(task)
        
        return ActionResult(
            success=True,
            output=f"Task {task.id} assigned to {task.assigned_to}",
        )
    
    async def broadcast(self, message: str, exclude: Optional[Set[str]] = None):
        """广播消息给所有队友"""
        exclude = exclude or set()
        for name, queue in self._mailbox.items():
            if name not in exclude:
                await queue.put({
                    "type": "broadcast",
                    "from": "coordinator",
                    "content": message,
                })
    
    async def claim_task(
        self, 
        agent_name: str, 
        task_id: str
    ) -> bool:
        """认领任务"""
        async with self._task_file_lock:
            task = self._task_list.get_task(task_id)
            if not task or task.status != TaskStatus.PENDING:
                return False
            
            # 检查依赖
            for dep_id in task.dependencies:
                dep = self._task_list.get_task(dep_id)
                if dep.status != TaskStatus.COMPLETED:
                    return False
            
            task.status = TaskStatus.IN_PROGRESS
            task.assigned_to = agent_name
            return True
    
    async def complete_task(
        self,
        agent_name: str,
        task_id: str,
        result: Any,
    ):
        """完成任务"""
        async with self._task_file_lock:
            task = self._task_list.get_task(task_id)
            task.status = TaskStatus.COMPLETED
            task.result = result
            
            # 通知依赖此任务的其他任务
            for dependent in self._task_list.get_dependent_tasks(task_id):
                if dependent.assigned_to:
                    await self._mailbox[dependent.assigned_to].put({
                        "type": "dependency_completed",
                        "task_id": task_id,
                    })


# ============== 工具注册表 ==============

class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, "ToolBase"] = {}
    
    def register(self, tool: "ToolBase") -> "ToolRegistry":
        self._tools[tool.metadata.name] = tool
        return self
    
    def get(self, name: str) -> Optional["ToolBase"]:
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        return list(self._tools.keys())
    
    def get_openai_tools(self) -> List[Dict[str, Any]]:
        return [tool.get_openai_spec() for tool in self._tools.values()]


# ============== 生产实现 ==============

class ProductionAgent(AgentBase):
    """生产环境Agent实现"""
    
    def __init__(
        self,
        info: AgentInfo,
        llm_adapter: Optional["LLMAdapter"] = None,
        **kwargs
    ):
        super().__init__(info, **kwargs)
        self.llm = llm_adapter
        
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """思考 - 流式调用LLM"""
        messages = self._build_llm_messages()
        
        async for chunk in self.llm.astream(messages):
            yield chunk
    
    async def decide(self, context: Dict[str, Any], **kwargs) -> Decision:
        """决策 - 解析LLM输出"""
        thinking = context.get("thinking", "")
        
        # 使用LLM进行决策
        messages = self._build_llm_messages()
        messages.append({
            "role": "assistant",
            "content": thinking
        })
        messages.append({
            "role": "system",
            "content": """Based on your thinking, decide what to do next.
Options:
1. response - Provide a direct response to the user
2. tool_call - Execute a tool
3. subagent - Delegate to a subagent
4. terminate - End the conversation

Output in JSON format:
{"type": "response", "content": "..."} 
or
{"type": "tool_call", "tool_name": "...", "tool_args": {...}}
"""
        })
        
        response = await self.llm.acomplete(messages)
        return self._parse_decision(response)
    
    async def act(self, decision: Decision, **kwargs) -> ActionResult:
        """执行动作"""
        if decision.type == DecisionType.TOOL_CALL:
            # 检查权限
            permission = await self.permission_checker.check_async(
                tool_name=decision.tool_name,
                tool_args=decision.tool_args,
            )
            
            if not permission.granted:
                return ActionResult(
                    success=False,
                    output="",
                    error=permission.reason or "Permission denied"
                )
            
            # 执行工具
            tool = self.tools.get(decision.tool_name)
            if not tool:
                return ActionResult(
                    success=False,
                    output="",
                    error=f"Tool '{decision.tool_name}' not found"
                )
            
            result = await tool.execute(decision.tool_args)
            return ActionResult(
                success=result.success,
                output=result.output,
                error=result.error,
            )
        
        return ActionResult(success=False, output="", error="Invalid decision type")
    
    def _build_llm_messages(self) -> List[Dict[str, Any]]:
        """构建LLM消息列表"""
        messages = [
            {"role": "system", "content": f"You are {self.info.role}. {self.info.description}"}
        ]
        
        # 添加历史消息
        messages.extend(self._messages)
        
        # 添加工具定义
        if self.tools.list_tools():
            messages.append({
                "role": "system",
                "content": f"Available tools: {self.tools.get_openai_tools()}"
            })
        
        return messages
    
    def _parse_decision(self, response: str) -> Decision:
        """解析决策响应"""
        import json
        try:
            data = json.loads(response)
            return Decision(
                type=DecisionType(data.get("type")),
                content=data.get("content"),
                tool_name=data.get("tool_name"),
                tool_args=data.get("tool_args"),
                subagent_name=data.get("subagent_name"),
                subagent_task=data.get("subagent_task"),
            )
        except:
            return Decision(type=DecisionType.RESPONSE, content=response)
```

### 5.4 配置示例

```yaml
# agent_config.yaml - 声明式配置

name: code-reviewer
description: Expert code review specialist. Use proactively after code changes.
role: Senior Code Reviewer

tools:
  - read_file
  - grep
  - glob
  - bash

model: sonnet

max_steps: 10
timeout: 300

permission:
  default: ask
  rules:
    - pattern: "read_file"
      action: allow
    - pattern: "bash"
      action: ask

memory:
  enabled: true
  scope: project

subagents:
  - security-scanner
  - performance-analyzer

team:
  can_spawn: false
  role: specialist
```

```python
# 使用示例

from derisk.agent.core_v2 import (
    ProductionAgent, 
    AgentInfo, 
    SubagentManager,
    TeamManager,
    UnifiedMemoryManager,
    AutoCompactionManager,
)
from derisk.storage.vector_store import ChromaStore
from derisk.embedding import OpenAIEmbedding

# 1. 初始化记忆系统
memory = UnifiedMemoryManager(
    project_root="/path/to/project",
    vector_store=ChromaStore(...),
    embedding_model=OpenAIEmbedding(),
)

# 2. 加载Agent配置
agent_info = AgentInfo.from_yaml("agent_config.yaml")

# 3. 创建Agent
agent = ProductionAgent(
    info=agent_info,
    memory=memory,
)

# 4. 配置子代理管理器
subagent_manager = SubagentManager(
    agent_registry=AgentRegistry(),
    memory=memory,
)
agent._subagent_manager = subagent_manager

# 5. 运行
async for chunk in agent.run("Review the authentication module"):
    print(chunk, end="", flush=True)
```

---

## 6. 实施路线图

### 6.1 短期（1-2周）

```
优先级 P0:
1. 修正 SessionCompaction 
   - 添加内容保护机制
   - 添加共享记忆重新加载
   
2. 统一记忆接口
   - 定义 UnifiedMemoryInterface
   - 实现基础的 FileBackedStorage

3. Core_v2 基础增强
   - 实现 SubagentManager
   - 添加 PermissionChecker 集成
```

### 6.2 中期（3-4周）

```
优先级 P1:
1. 完善统一记忆框架
   - 实现 ClaudeCodeCompatibleMemory
   - 支持 @导入 语法
   - Git 友好的共享机制

2. Core_v2 多Agent完善
   - TeamManager 实现
   - TaskCoordination 实现
   - 消息传递机制

3. 自动压缩优化
   - AutoCompactionManager
   - 自适应触发策略
   - 关键信息提取
```

### 6.3 长期（5-8周）

```
优先级 P2:
1. 架构统一
   - Core 渐进迁移到 Core_v2
   - 接口兼容层
   
2. 生产就绪
   - 性能优化
   - 错误处理
   - 监控集成

3. 文档完善
   - 架构文档
   - 使用指南
   - 最佳实践
```

### 6.4 迁移策略

```
Core → Core_v2 迁移路径:

Phase 1: 并存
- Core_v2 作为新特性开发基础
- Core 保持稳定维护

Phase 2: 兼容层
- 为 Core 提供 Core_v2 适配器
- 统一记忆接口

Phase 3: 迁移
- 逐步迁移 Core 功能到 Core_v2
- 保持向后兼容

Phase 4: 统一
- Core_v2 成为默认实现
- Core 进入维护模式
```

---

*报告生成时间: 2026-03-01*
*基于实际代码深度分析*