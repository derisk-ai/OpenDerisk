# Core V2 上下文管理与记忆系统详解

> 最后更新: 2026-03-03
> 状态: 活跃文档

本文档详细说明 Core V2 的上下文管理、压缩机制、记忆系统以及它们与文件系统的集成。

---

## 一、上下文管理架构

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        上下文管理整体架构                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    V2AgentRuntime (入口)                            │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐      │ │
│  │  │SessionContext│  │上下文中间件  │  │ Agent 实例管理        │      │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘      │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                              │                                           │
│                              ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                   上下文加载与处理流程                              │ │
│  │                                                                     │ │
│  │  用户消息 ──▶ 加载历史消息 ──▶ 加载项目记忆 ──▶ 检测窗口溢出        │ │
│  │                                              │                       │ │
│  │                                              ▼                       │ │
│  │                                    是否需要压缩?                     │ │
│  │                                     /         \                     │ │
│  │                                   否           是                    │ │
│  │                                    │            │                    │ │
│  │                                    ▼            ▼                    │ │
│  │                              直接使用    触发压缩机制                 │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                              │                                           │
│         ┌────────────────────┼────────────────────┐                     │
│         ▼                    ▼                    ▼                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐           │
│  │ 记忆系统    │     │ 压缩系统    │     │上下文隔离系统    │           │
│  │             │     │             │     │                  │           │
│  │UnifiedMemory│     │Compaction   │     │ContextIsolation  │           │
│  │ProjectMemory│     │Manager      │     │Manager           │           │
│  └─────────────┘     └─────────────┘     └─────────────────┘           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 上下文窗口数据结构

```python
@dataclass
class ContextWindow:
    """上下文窗口定义"""
    messages: List[Dict[str, Any]]       # 消息历史
    total_tokens: int                    # 当前 token 总数
    max_tokens: int = 128000             # 最大 token 限制 (Claude Opus)
    available_tools: Set[str]            # 可用工具集合
    memory_types: Set[str]               # 可访问的记忆类型
    resource_bindings: Dict[str, str]    # 资源绑定映射
```

---

## 二、上下文压缩机制

### 2.1 压缩触发策略

文件位置: `core_v2/improved_compaction.py`

#### 触发方式枚举

```python
class CompactionTrigger(str, Enum):
    MANUAL = "manual"          # 手动触发 - 用户/API 主动请求
    THRESHOLD = "threshold"    # 阈值触发 - 超过窗口 80%
    ADAPTIVE = "adaptive"      # 自适应触发 - 基于使用模式
    SCHEDULED = "scheduled"    # 定时触发 - 定期清理
```

#### 压缩策略枚举

```python
class CompactionStrategy(str, Enum):
    SUMMARIZE = "summarize"               # LLM 摘要压缩
    TRUNCATE_OLD = "truncate_old"         # 截断旧消息
    HYBRID = "hybrid"                     # 混合策略
    IMPORTANCE_BASED = "importance_based" # 基于重要性保留
```

### 2.2 压缩配置

```python
@dataclass
class CompactionConfig:
    # 窗口配置
    context_window_tokens: int = 128000     # 上下文窗口大小
    trigger_threshold_ratio: float = 0.8    # 触发阈值 (80%)

    # 保留策略
    keep_recent_messages: int = 3           # 保留最近消息数
    preserve_system_messages: bool = True   # 保留系统消息

    # Token 估算
    chars_per_token: int = 4                # 字符/Token 比率

    # 内容保护
    protect_code_blocks: bool = True        # 保护代码块
    protect_thinking_chains: bool = True    # 保护思考链
    protect_file_paths: bool = True         # 保护文件路径

    # 共享记忆
    reload_shared_memory: bool = True       # 压缩后重载共享记忆
```

### 2.3 压缩流程详解

```
┌─────────────────────────────────────────────────────────────────┐
│                        压缩执行流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 检测是否需要压缩                                             │
│     └── is_overflow() 或 force=True                             │
│              │                                                   │
│              ▼                                                   │
│  2. 提取受保护内容                                               │
│     ├── 代码块: ```...```                                        │
│     ├── 思考链: <thinking>...</thinking>                        │
│     └── 文件路径: /path/to/file                                  │
│              │                                                   │
│              ▼                                                   │
│  3. 提取关键信息                                                 │
│     ├── 规则提取 (关键词匹配)                                    │
│     └── LLM 提取 (可选)                                          │
│              │                                                   │
│              ▼                                                   │
│  4. 选择压缩消息                                                 │
│     └── 排除最近 N 条消息                                        │
│              │                                                   │
│              ▼                                                   │
│  5. 生成摘要                                                     │
│     ├── LLM 摘要: 调用大模型生成                                 │
│     └── 简单摘要: 消息拼接截断                                   │
│              │                                                   │
│              ▼                                                   │
│  6. 构建新消息列表                                               │
│     ├── [摘要消息]                                               │
│     ├── [受保护内容格式化]                                       │
│     └── [最近消息]                                               │
│              │                                                   │
│              ▼                                                   │
│  7. 重载共享记忆 (如果配置)                                      │
│     └── 从 ProjectMemory 重新加载                                │
│              │                                                   │
│              ▼                                                   │
│  8. 返回压缩结果                                                 │
│     ├── 压缩后消息列表                                           │
│     ├── 新 token 数                                              │
│     └── 压缩统计                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 内容保护器实现

文件位置: `core_v2/improved_compaction.py:146-277`

```python
class ContentProtector:
    """保护重要内容不被压缩"""

    # 保护模式定义
    PATTERNS = {
        'code_block': r'```[\s\S]*?```',
        'thinking': r'<(?:thinking|scratch_pad|reasoning)>[\s\S]*?</(?:thinking|scratch_pad|reasoning)>',
        'file_path': r'(?:^|\s)(/[a-zA-Z0-9_\-./]+(?:\.[a-zA-Z0-9]+)?)(?:\s|$)',
    }

    def extract_protected_content(self, messages: List[Dict]) -> ProtectedContent:
        """从消息中提取所有受保护内容"""
        protected = ProtectedContent()

        for msg in messages:
            content = msg.get('content', '')

            # 提取代码块
            code_blocks = re.findall(self.PATTERNS['code_block'], content)
            for code in code_blocks:
                # 计算重要性分数
                importance = self._calculate_importance(code)
                protected.code_blocks.append(CodeBlock(
                    content=code,
                    importance=importance,
                    source_message_id=msg.get('message_id'),
                ))

            # 提取思考链
            thinking_blocks = re.findall(self.PATTERNS['thinking'], content)
            protected.thinking_blocks.extend(thinking_blocks)

            # 提取文件路径
            file_paths = re.findall(self.PATTERNS['file_path'], content)
            protected.file_paths.extend(file_paths)

        return protected

    def _calculate_importance(self, content: str) -> float:
        """计算内容重要性分数 (0.0-1.0)"""
        score = 0.5  # 基础分

        # 关键词检测
        keywords = ['important', 'critical', 'key', '决定', '重要', '关键']
        for kw in keywords:
            if kw in content.lower():
                score += 0.1

        # 代码复杂度检测
        lines = content.split('\n')
        if len(lines) > 20:
            score += 0.1
        if len(lines) > 50:
            score += 0.1

        # 函数/类定义检测
        if re.search(r'def |class |function |async def ', content):
            score += 0.15

        return min(score, 1.0)
```

### 2.5 关键信息提取器

文件位置: `core_v2/improved_compaction.py:280-448`

```python
class KeyInfoExtractor:
    """从消息中提取关键信息"""

    # 关键信息类型
    INFO_TYPES = {
        'fact': '事实陈述',
        'decision': '决策记录',
        'constraint': '约束条件',
        'preference': '偏好设置',
        'action': '执行动作',
    }

    # 规则模式
    RULE_PATTERNS = [
        (r'(?:用户|user)\s*(?:要求|需要|想要)\s*(.+)', 'constraint'),
        (r'(?:决定|decision)\s*[:：]\s*(.+)', 'decision'),
        (r'(?:注意|note|important)\s*[:：]\s*(.+)', 'fact'),
        (r'(?:偏好|prefer)\s*[:：]\s*(.+)', 'preference'),
    ]

    async def extract(
        self,
        messages: List[Dict],
        use_llm: bool = False,
    ) -> List[KeyInfo]:
        """提取关键信息"""
        key_infos = []

        # 规则提取
        for msg in messages:
            content = msg.get('content', '')
            for pattern, info_type in self.RULE_PATTERNS:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    key_infos.append(KeyInfo(
                        type=info_type,
                        content=match.strip(),
                        source_id=msg.get('message_id'),
                        confidence=0.8,
                    ))

        # LLM 增强提取 (可选)
        if use_llm and self.llm_client:
            llm_infos = await self._extract_with_llm(messages)
            key_infos.extend(llm_infos)

        return key_infos
```

### 2.6 Token 估算器

文件位置: `core_v2/improved_compaction.py:451-492`

```python
class TokenEstimator:
    """Token 数量估算器"""

    def __init__(self, chars_per_token: int = 4):
        self.chars_per_token = chars_per_token

    def estimate(self, text: str) -> int:
        """估算文本的 token 数量"""
        if not text:
            return 0
        # 简单估算: 字符数 / 比率
        # 实际实现可能使用 tiktoken 库
        return len(text) // self.chars_per_token

    def estimate_messages(self, messages: List[Dict]) -> int:
        """估算消息列表的总 token 数"""
        total = 0
        for msg in messages:
            # 内容 tokens
            content = msg.get('content', '')
            total += self.estimate(content)

            # 角色/名称开销
            total += 4

            # 元数据开销
            if msg.get('name'):
                total += self.estimate(msg['name'])
            if msg.get('tool_calls'):
                total += 20  # 工具调用的固定开销

        return total
```

### 2.7 主压缩器实现

文件位置: `core_v2/improved_compaction.py:524-926`

```python
class ImprovedSessionCompaction:
    """改进的会话压缩器"""

    def __init__(
        self,
        config: Optional[CompactionConfig] = None,
        llm_client: Optional[Any] = None,
        project_memory: Optional["ProjectMemoryManager"] = None,
    ):
        self.config = config or CompactionConfig()
        self.llm_client = llm_client
        self.project_memory = project_memory

        self.content_protector = ContentProtector()
        self.key_info_extractor = KeyInfoExtractor(llm_client)
        self.token_estimator = TokenEstimator(self.config.chars_per_token)

    async def compact(
        self,
        messages: List[Dict[str, Any]],
        force: bool = False,
        trigger: CompactionTrigger = CompactionTrigger.MANUAL,
    ) -> CompactionResult:
        """执行压缩"""

        # 1. 计算当前 token 数
        current_tokens = self.token_estimator.estimate_messages(messages)
        max_tokens = int(self.config.context_window_tokens * self.config.trigger_threshold_ratio)

        # 2. 检查是否需要压缩
        if not force and current_tokens < max_tokens:
            return CompactionResult(
                needs_compaction=False,
                original_messages=messages,
                compacted_messages=messages,
                original_tokens=current_tokens,
                compacted_tokens=current_tokens,
            )

        # 3. 提取受保护内容
        protected = self.content_protector.extract_protected_content(messages)

        # 4. 提取关键信息
        key_infos = await self.key_info_extractor.extract(
            messages,
            use_llm=(self.llm_client is not None),
        )

        # 5. 选择要压缩的消息 (保留最近 N 条)
        to_compress = messages[:-self.config.keep_recent_messages]
        to_keep = messages[-self.config.keep_recent_messages:]

        # 6. 生成摘要
        if self.llm_client:
            summary = await self._generate_llm_summary(to_compress, key_infos, protected)
        else:
            summary = self._generate_simple_summary(to_compress, key_infos)

        # 7. 构建新消息列表
        summary_message = {
            "role": "system",
            "content": self._format_summary_message(summary, protected, key_infos),
            "message_id": f"compaction_{datetime.now().isoformat()}",
        }

        compacted_messages = [summary_message] + to_keep

        # 8. 重载共享记忆 (如果配置)
        if self.config.reload_shared_memory and self.project_memory:
            context_addition = await self.project_memory.build_context()
            if context_addition:
                compacted_messages.insert(0, {
                    "role": "system",
                    "content": f"[Project Memory]\n{context_addition}",
                    "message_id": "project_memory_reload",
                })

        # 9. 计算新 token 数
        new_tokens = self.token_estimator.estimate_messages(compacted_messages)

        return CompactionResult(
            needs_compaction=True,
            original_messages=messages,
            compacted_messages=compacted_messages,
            original_tokens=current_tokens,
            compacted_tokens=new_tokens,
            compression_ratio=1 - (new_tokens / current_tokens),
            protected_content=protected,
            key_infos=key_infos,
        )
```

---

## 三、记忆系统架构

### 3.1 统一记忆接口

文件位置: `core_v2/unified_memory/base.py`

#### 记忆类型定义

```python
class MemoryType(str, Enum):
    """记忆类型枚举"""
    WORKING = "working"        # 工作记忆 - 当前任务相关
    EPISODIC = "episodic"      # 情景记忆 - 具体事件/对话
    SEMANTIC = "semantic"      # 语义记忆 - 知识/事实
    SHARED = "shared"          # 共享记忆 - 跨会话共享
    PREFERENCE = "preference"  # 偏好记忆 - 用户偏好设置
```

#### 记忆项数据结构

```python
@dataclass
class MemoryItem:
    """记忆项"""
    id: str                              # 唯一标识
    content: str                         # 记忆内容
    memory_type: MemoryType              # 记忆类型
    importance: float = 0.5              # 重要性 (0.0-1.0)

    # 向量相关
    embedding: Optional[List[float]] = None  # 嵌入向量

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0                # 访问次数

    # 来源追踪
    file_path: Optional[str] = None      # 文件路径 (如果有)
    source: str = "unknown"              # 来源标识
```

#### 统一接口定义

```python
class UnifiedMemoryInterface(ABC):
    """统一记忆接口"""

    @abstractmethod
    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        importance: float = 0.5,
        metadata: Optional[Dict] = None,
    ) -> str:
        """写入记忆，返回记忆 ID"""
        pass

    @abstractmethod
    async def read(
        self,
        query: str,
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryItem]:
        """读取记忆"""
        pass

    @abstractmethod
    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        threshold: float = 0.7,
    ) -> List[MemoryItem]:
        """向量相似度搜索"""
        pass

    @abstractmethod
    async def consolidate(
        self,
        source: MemoryType,
        target: MemoryType,
        criteria: Optional[Dict] = None,
    ) -> int:
        """记忆整合/迁移"""
        pass

    @abstractmethod
    async def export(self, memory_type: Optional[MemoryType] = None) -> str:
        """导出记忆为字符串"""
        pass

    @abstractmethod
    async def import_from_file(
        self,
        file_path: str,
        memory_type: MemoryType = MemoryType.SHARED,
    ) -> int:
        """从文件导入记忆"""
        pass
```

### 3.2 统一记忆管理器

文件位置: `core_v2/unified_memory/unified_manager.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                    UnifiedMemoryManager                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  写入流程:                                                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │接收内容   │───▶│生成嵌入   │───▶│创建Item  │───▶│存储到后端 │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                                        │                         │
│                                        ▼                         │
│                         ┌─────────────────────────────┐         │
│                         │ 存储后端选择                 │         │
│                         │ ├── 内存缓存 (快速访问)      │         │
│                         │ ├── 向量存储 (相似搜索)      │         │
│                         │ └── 文件存储 (持久化)        │         │
│                         └─────────────────────────────┘         │
│                                                                  │
│  读取流程:                                                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │接收查询   │───▶│生成查询   │───▶│搜索匹配   │───▶│返回结果   │  │
│  └──────────┘    │嵌入向量   │    └──────────┘    └──────────┘  │
│                  └──────────┘                                    │
│                                                                  │
│  整合流程:                                                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │源类型记忆 │───▶│过滤筛选   │───▶│升级/迁移  │───▶│目标类型   │  │
│  │(working) │    │(重要性)   │    │          │    │(semantic)│  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 核心实现

```python
class UnifiedMemoryManager(UnifiedMemoryInterface):
    """统一记忆管理器"""

    def __init__(
        self,
        embedding_model: Optional[Any] = None,
        vector_store: Optional[Any] = None,
        file_storage: Optional["FileBackedStorage"] = None,
    ):
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.file_storage = file_storage

        # 内存缓存
        self._cache: Dict[str, MemoryItem] = {}

    async def initialize(self) -> None:
        """初始化 - 加载已有记忆"""
        if self.file_storage:
            # 从文件加载共享记忆
            memories = await self.file_storage.load_all()
            for item in memories:
                # 生成嵌入向量
                if self.embedding_model and not item.embedding:
                    item.embedding = await self._generate_embedding(item.content)

                # 添加到缓存
                self._cache[item.id] = item

                # 添加到向量存储
                if self.vector_store and item.embedding:
                    await self.vector_store.add(item)

    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        importance: float = 0.5,
        metadata: Optional[Dict] = None,
    ) -> str:
        """写入记忆"""
        # 生成 ID
        memory_id = str(uuid.uuid4())

        # 生成嵌入向量
        embedding = None
        if self.embedding_model:
            embedding = await self._generate_embedding(content)

        # 创建记忆项
        item = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            embedding=embedding,
            metadata=metadata or {},
        )

        # 添加到缓存
        self._cache[memory_id] = item

        # 添加到向量存储
        if self.vector_store and embedding:
            await self.vector_store.add(item)

        # 持久化到文件
        if self.file_storage and memory_type in [MemoryType.SHARED, MemoryType.PREFERENCE]:
            await self.file_storage.save(item)

        return memory_id

    async def search_similar(
        self,
        query: str,
        top_k: int = 10,
        threshold: float = 0.7,
    ) -> List[MemoryItem]:
        """向量相似度搜索"""
        if not self.vector_store:
            return []

        # 生成查询向量
        query_embedding = await self._generate_embedding(query)

        # 搜索
        results = await self.vector_store.similarity_search(
            query_embedding,
            top_k=top_k,
            threshold=threshold,
        )

        # 从缓存获取完整信息
        items = []
        for result in results:
            item = self._cache.get(result.id)
            if item:
                # 更新访问统计
                item.last_accessed = datetime.now()
                item.access_count += 1
                items.append(item)

        return items

    async def consolidate(
        self,
        source: MemoryType,
        target: MemoryType,
        criteria: Optional[Dict] = None,
    ) -> int:
        """记忆整合"""
        criteria = criteria or {}
        min_importance = criteria.get("min_importance", 0.5)
        min_access_count = criteria.get("min_access_count", 1)
        max_age_hours = criteria.get("max_age_hours", 24)

        migrated_count = 0
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        for item in list(self._cache.values()):
            if item.memory_type != source:
                continue

            # 检查是否符合迁移条件
            if (item.importance >= min_importance and
                item.access_count >= min_access_count and
                item.created_at >= cutoff_time):

                # 迁移到目标类型
                item.memory_type = target
                migrated_count += 1

                # 持久化
                if self.file_storage:
                    await self.file_storage.save(item)

        return migrated_count
```

### 3.3 文件支持的存储

文件位置: `core_v2/unified_memory/file_backed_storage.py`

#### 目录结构

```
.agent_memory/              # 共享记忆目录 (提交到 Git)
├── PROJECT_MEMORY.md       # 项目级共享记忆
├── TEAM_RULES.md          # 团队规则
└── sessions/              # 会话目录
    └── {session_id}.md    # 会话记忆

.agent_memory.local/        # 本地记忆目录 (Git 忽略)
├── working.md             # 工作记忆
├── episodic.md            # 情景记忆
└── preference.md          # 偏好记忆
```

#### 记忆块格式

```markdown
---
memory_id: a1b2c3d4-e5f6-7890-abcd-ef1234567890
type: shared
importance: 0.8
created: 2026-03-03T10:30:00
source: user_input
metadata: {"tags": ["architecture", "decision"]}
---

这是记忆的内容...

可以包含多行文本，支持 Markdown 格式。
```

#### 核心实现

```python
class FileBackedStorage:
    """文件支持的存储"""

    MEMORY_DIR = ".agent_memory"
    LOCAL_DIR = ".agent_memory.local"

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.memory_dir = self.base_path / self.MEMORY_DIR
        self.local_dir = self.base_path / self.LOCAL_DIR

    async def save(self, item: MemoryItem) -> None:
        """保存记忆到文件"""
        # 确定目标目录
        if item.memory_type in [MemoryType.SHARED]:
            target_dir = self.memory_dir
        else:
            target_dir = self.local_dir

        target_dir.mkdir(parents=True, exist_ok=True)

        # 确定文件名
        if item.memory_type == MemoryType.SHARED and item.file_path:
            file_path = Path(item.file_path)
        else:
            file_path = target_dir / f"{item.memory_type.value}.md"

        # 格式化记忆块
        block = self._format_memory_block(item)

        # 追加写入
        async with aiofiles.open(file_path, mode='a') as f:
            await f.write("\n\n" + block)

    def _format_memory_block(self, item: MemoryItem) -> str:
        """格式化为记忆块"""
        front_matter = {
            "memory_id": item.id,
            "type": item.memory_type.value,
            "importance": item.importance,
            "created": item.created_at.isoformat(),
            "source": item.source,
            "metadata": item.metadata,
        }

        yaml_str = yaml.dump(front_matter, allow_unicode=True, default_flow_style=False)
        return f"---\n{yaml_str}---\n\n{item.content}"

    async def load_all(self) -> List[MemoryItem]:
        """加载所有记忆"""
        items = []

        # 加载共享记忆
        if self.memory_dir.exists():
            for md_file in self.memory_dir.glob("**/*.md"):
                file_items = await self._parse_memory_file(md_file)
                items.extend(file_items)

        # 加载本地记忆
        if self.local_dir.exists():
            for md_file in self.local_dir.glob("**/*.md"):
                file_items = await self._parse_memory_file(md_file)
                items.extend(file_items)

        return items

    async def _parse_memory_file(self, file_path: Path) -> List[MemoryItem]:
        """解析记忆文件"""
        async with aiofiles.open(file_path) as f:
            content = await f.read()

        items = []
        blocks = content.split("---\n")

        for i in range(1, len(blocks), 2):
            if i + 1 >= len(blocks):
                break

            front_matter = yaml.safe_load(blocks[i])
            item_content = blocks[i + 1].strip()

            # 处理 @import
            resolved_content = await self._resolve_imports(item_content)

            items.append(MemoryItem(
                id=front_matter.get("memory_id", str(uuid.uuid4())),
                content=resolved_content,
                memory_type=MemoryType(front_matter.get("type", "working")),
                importance=front_matter.get("importance", 0.5),
                created_at=datetime.fromisoformat(front_matter["created"]),
                source=front_matter.get("source", "unknown"),
                metadata=front_matter.get("metadata", {}),
                file_path=str(file_path),
            ))

        return items

    async def _resolve_imports(
        self,
        content: str,
        depth: int = 0,
        max_depth: int = 5,
    ) -> str:
        """解析 @import 指令"""
        if depth >= max_depth:
            return content

        # 匹配 @import 指令
        import_pattern = r'@import\s+(@?[\w./-]+)'

        def replace_import(match):
            import_path = match.group(1)
            # 解析路径...
            # 递归调用 _resolve_imports
            return resolved_content

        return re.sub(import_pattern, replace_import, content)
```

### 3.4 GptsMemory 适配器

文件位置: `core_v2/unified_memory/gpts_adapter.py`

#### 架构角色

```
┌──────────────────────────────────────────────────────────────────┐
│                      V1/V2 集成架构                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ┌─────────────┐                        ┌─────────────────────┐ │
│   │  Core V2    │                        │      Core V1        │ │
│   │  Agent      │                        │      Agent          │ │
│   └──────┬──────┘                        └──────────┬──────────┘ │
│          │                                          │             │
│          ▼                                          ▼             │
│   ┌─────────────────────┐              ┌───────────────────────┐ │
│   │UnifiedMemoryInterface│              │     GptsMemory        │ │
│   └──────────┬──────────┘              │  (V1 记忆系统)         │ │
│              │                          └───────────┬───────────┘ │
│              │                                       │             │
│              ▼                                       │             │
│   ┌────────────────────┐                             │             │
│   │GptsMemoryAdapter   │◀────────────────────────────┘             │
│   │                    │                                          │
│   │ 写入: write()      │──────▶ append_message()                  │
│   │ 读取: read()       │──────▶ get_messages()                    │
│   │ 搜索: search()     │──────▶ 内存关键词匹配                     │
│   │ 整合: consolidate()│──────▶ memory_compaction                 │
│   └────────────────────┘                                          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### 核心实现

```python
class GptsMemoryAdapter(UnifiedMemoryInterface):
    """适配 V1 的 GptsMemory 到统一接口"""

    def __init__(self, gpts_memory: "GptsMemory", conv_id: str):
        self._gpts_memory = gpts_memory
        self._conv_id = conv_id

    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        importance: float = 0.5,
        metadata: Optional[Dict] = None,
    ) -> str:
        """写入记忆 - 转换为 GptsMessage"""
        message_id = str(uuid.uuid4())

        msg = GptsMessage(
            conv_id=self._conv_id,
            message_id=message_id,
            content=content,
            role="assistant",
            sender_name="memory",
            context={
                "memory_type": memory_type.value,
                "importance": importance,
                **(metadata or {}),
            },
        )

        await self._gpts_memory.append_message(self._conv_id, msg)
        return message_id

    async def read(
        self,
        query: str,
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryItem]:
        """读取记忆"""
        messages = await self._gpts_memory.get_messages(self._conv_id)

        items = []
        for msg in messages:
            context = msg.context or {}
            if context.get("memory_type"):
                items.append(MemoryItem(
                    id=msg.message_id,
                    content=msg.content,
                    memory_type=MemoryType(context.get("memory_type", "working")),
                    importance=context.get("importance", 0.5),
                    source="gpts_memory",
                ))

        return items
```

---

## 四、项目记忆系统

文件位置: `core_v2/project_memory/`

### 4.1 记忆优先级层次

```python
class MemoryPriority(IntEnum):
    """记忆优先级"""
    AUTO = 0         # 自动生成的记忆 (最低)
    USER = 25        # 用户级别 (~/.derisk/)
    PROJECT = 50     # 项目级别 (./.derisk/)
    MANAGED = 75     # 托管/企业策略
    SYSTEM = 100     # 系统级别 (最高，不可覆盖)
```

### 4.2 目录结构与作用

```
.derisk/                          # 项目根目录
├── MEMORY.md                     # 项目主记忆 (优先级: 50)
│   └── 包含项目概述、关键决策、架构说明
│
├── RULES.md                      # 项目规则 (优先级: 50)
│   └── 编码规范、提交规则、审查标准
│
├── AGENTS/                       # Agent 特定配置
│   ├── DEFAULT.md               # 默认 Agent 配置 (优先级: 50)
│   └── reviewer.md              # 审查 Agent 配置 (优先级: 50)
│
├── KNOWLEDGE/                    # 知识库目录
│   ├── domain.md                # 领域知识 (优先级: 50)
│   └── glossary.md              # 词汇表 (优先级: 50)
│
├── MEMORY.LOCAL/                 # 本地记忆 (Git 忽略)
│   ├── auto-memory.md           # 自动记忆 (优先级: 0)
│   └── sessions/                # 会话记忆
│       └── {session_id}.md
│
└── .gitignore                   # Git 配置
```

### 4.3 上下文构建流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    build_context() 执行流程                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 收集所有记忆层                                               │
│     ├── SYSTEM 层 (如果存在)                                     │
│     ├── MANAGED 层 (如果存在)                                    │
│     ├── PROJECT 层 (.derisk/MEMORY.md etc.)                     │
│     ├── USER 层 (~/.derisk/MEMORY.md)                           │
│     └── AUTO 层 (MEMORY.LOCAL/auto-memory.md)                   │
│              │                                                   │
│              ▼                                                   │
│  2. 按优先级排序 (高到低)                                        │
│     └── SYSTEM > MANAGED > PROJECT > USER > AUTO                │
│              │                                                   │
│              ▼                                                   │
│  3. 对每层构建内容                                               │
│     ├── 读取文件内容                                             │
│     ├── 解析 @import 指令                                        │
│     └── 合并同层多源                                             │
│              │                                                   │
│              ▼                                                   │
│  4. 拼接生成最终上下文                                           │
│     ├── 添加优先级标记                                           │
│     └── 避免重复内容                                             │
│              │                                                   │
│              ▼                                                   │
│  5. 返回上下文字符串                                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 @import 指令机制

```markdown
# MEMORY.md 示例

@import @user/preferences.md      # 导入用户级偏好
@import @knowledge/python.md      # 导入知识库
@import AGENTS/DEFAULT.md         # 导入默认 Agent 配置
@import ./RULES.md                # 导入项目规则 (相对路径)

# 项目特定内容
本项目是一个 AI Agent 框架...
```

#### 路径前缀说明

| 前缀 | 解析规则 | 示例 |
|------|---------|------|
| `@user/` | 解析为用户级目录 `~/.derisk/` | `@user/preferences.md` |
| `@project/` | 解析为项目根目录 `.derisk/` | `@project/RULES.md` |
| `@knowledge/` | 解析为知识库目录 `.derisk/KNOWLEDGE/` | `@knowledge/domain.md` |
| 无前缀 | 相对于当前文件的路径 | `./AGENTS/DEFAULT.md` |

### 4.5 ProjectMemoryManager 核心实现

```python
class ProjectMemoryManager:
    """项目记忆管理器"""

    def __init__(
        self,
        project_root: str = ".",
        user_root: Optional[str] = None,
    ):
        self.project_root = Path(project_root)
        self.user_root = Path(user_root) if user_root else Path.home() / ".derisk"

        self._memory_layers: Dict[MemoryPriority, MemoryLayer] = {}
        self._import_cache: Dict[str, str] = {}

    async def initialize(self, config: Optional[Dict] = None) -> None:
        """初始化记忆系统"""
        # 创建目录结构
        self._ensure_directories()

        # 扫描并加载所有记忆层
        await self._load_all_layers()

    async def build_context(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """构建完整上下文"""
        context_parts = []

        # 按优先级从高到低处理
        for priority in sorted(MemoryPriority, reverse=True):
            layer = self._memory_layers.get(priority)
            if not layer:
                continue

            # 获取合并后的内容
            content = layer.get_merged_content()

            # 解析 @import 指令
            resolved = await self._resolve_imports(content)

            if resolved.strip():
                context_parts.append(f"[Priority {priority.name}]\n{resolved}")

        return "\n\n".join(context_parts)

    async def write_auto_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """写入自动记忆"""
        auto_memory_path = self.project_root / ".derisk" / "MEMORY.LOCAL" / "auto-memory.md"
        auto_memory_path.parent.mkdir(parents=True, exist_ok=True)

        # 格式化记忆条目
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        importance = metadata.get("importance", 0.5) if metadata else 0.5
        tags = metadata.get("tags", []) if metadata else []

        entry = f"""
## Auto Memory Entry - {timestamp}

{content}

- Importance: {importance}
- Tags: {', '.join(tags) if tags else 'none'}

---
"""
        # 追加写入
        async with aiofiles.open(auto_memory_path, mode='a') as f:
            await f.write(entry)

        # 更新缓存
        await self._reload_auto_layer()

        return f"auto_{datetime.now().timestamp()}"

    async def _resolve_imports(
        self,
        content: str,
        depth: int = 0,
        max_depth: int = 5,
    ) -> str:
        """递归解析 @import 指令"""
        if depth >= max_depth:
            return content

        import_pattern = r'@import\s+(@?[\w./-]+)'

        def replace_import(match):
            import_path = match.group(1)

            # 解析路径前缀
            if import_path.startswith('@user/'):
                full_path = self.user_root / import_path[6:]
            elif import_path.startswith('@project/'):
                full_path = self.project_root / ".derisk" / import_path[9:]
            elif import_path.startswith('@knowledge/'):
                full_path = self.project_root / ".derisk" / "KNOWLEDGE" / import_path[11:]
            else:
                # 相对路径
                full_path = self.project_root / ".derisk" / import_path.lstrip('./')

            # 检查缓存
            cache_key = str(full_path)
            if cache_key in self._import_cache:
                return self._import_cache[cache_key]

            # 读取文件
            if full_path.exists():
                imported_content = full_path.read_text()
                # 递归解析
                resolved = await self._resolve_imports(
                    imported_content,
                    depth + 1,
                    max_depth,
                )
                self._import_cache[cache_key] = resolved
                return resolved

            return f"[Import not found: {import_path}]"

        return re.sub(import_pattern, replace_import, content)

    async def consolidate_memories(
        self,
        config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """记忆整合 - 清理和归档"""
        config = config or {}
        min_importance = config.get("min_importance", 0.3)
        max_age_days = config.get("max_age_days", 30)
        deduplicate = config.get("deduplicate", True)

        auto_memory_path = self.project_root / ".derisk" / "MEMORY.LOCAL" / "auto-memory.md"
        if not auto_memory_path.exists():
            return {"status": "no_auto_memory"}

        # 读取自动记忆
        content = auto_memory_path.read_text()
        entries = self._parse_auto_memory_entries(content)

        # 过滤
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        filtered_entries = []
        seen_content = set()

        for entry in entries:
            # 重要性过滤
            if entry['importance'] < min_importance:
                continue

            # 年龄过滤
            if entry['created_at'] < cutoff_date:
                continue

            # 去重
            if deduplicate:
                normalized = self._normalize_content(entry['content'])
                if normalized in seen_content:
                    continue
                seen_content.add(normalized)

            filtered_entries.append(entry)

        # 重建文件
        new_content = self._rebuild_auto_memory(filtered_entries)
        auto_memory_path.write_text(new_content)

        return {
            "original_count": len(entries),
            "filtered_count": len(filtered_entries),
            "removed_count": len(entries) - len(filtered_entries),
        }
```

---

## 五、上下文隔离机制

文件位置: `core_v2/context_isolation/`

### 5.1 隔离模式详解

```python
class ContextIsolationMode(str, Enum):
    """上下文隔离模式"""
    ISOLATED = "isolated"   # 完全隔离，全新上下文
    SHARED = "shared"       # 共享父上下文，实时同步
    FORK = "fork"           # 复制父上下文快照，后续独立
```

#### 模式对比

| 模式 | 继承父上下文 | 实时同步 | 独立演化 | 适用场景 |
|------|-------------|---------|---------|---------|
| ISOLATED | ❌ | ❌ | ✅ | 完全独立的子任务 |
| SHARED | ✅ | ✅ | ❌ | 需要实时感知父级变化 |
| FORK | ✅ (快照) | ❌ | ✅ | 基于当前状态独立探索 |

### 5.2 SubagentContextConfig 配置

```python
@dataclass
class SubagentContextConfig:
    """子 Agent 上下文配置"""

    # 隔离模式
    isolation_mode: ContextIsolationMode = ContextIsolationMode.FORK

    # 记忆范围
    memory_scope: MemoryScope = field(default_factory=lambda: MemoryScope(
        inherit_parent=True,           # 继承父级记忆
        accessible_layers=["working", "shared"],  # 可访问的记忆层
        propagate_up=False,            # 是否向上传播
        propagate_down=True,           # 是否向下传播
    ))

    # 资源绑定
    resource_bindings: List[ResourceBinding] = field(default_factory=list)

    # 工具限制
    allowed_tools: Optional[List[str]] = None  # None 表示无限制
    denied_tools: List[str] = field(default_factory=list)

    # Token 限制
    max_context_tokens: int = 32000

    # 超时设置
    timeout_seconds: int = 300
```

### 5.3 隔离流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                   上下文隔离执行流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  父 Agent 执行                                                   │
│       │                                                          │
│       ▼                                                          │
│  决定委派子任务                                                   │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │           ContextIsolationManager.create_isolated_context   ││
│  │                                                              ││
│  │   ISOLATED 模式:         SHARED 模式:        FORK 模式:     ││
│  │   ┌──────────┐          ┌──────────┐       ┌──────────┐    ││
│  │   │ 空消息列表│          │ 返回父上下│       │ 深拷贝父  │    ││
│  │   │ 空 token  │          │ 文引用    │       │ 上下文    │    ││
│  │   │ 新工具集合│          │ 共享状态  │       │ 过滤记忆  │    ││
│  │   └──────────┘          └──────────┘       └──────────┘    ││
│  │         │                     │                   │         ││
│  │         └─────────────────────┴───────────────────┘         ││
│  │                               │                              ││
│  └───────────────────────────────┼──────────────────────────────┘│
│                                  ▼                               │
│                        创建 IsolatedContext                      │
│                                  │                               │
│                                  ▼                               │
│                        子 Agent 执行任务                         │
│                                  │                               │
│                                  ▼                               │
│                   ┌─────────────────────────────┐               │
│                   │ 是否需要合并回父上下文?      │               │
│                   │ (memory_scope.propagate_up) │               │
│                   └─────────────────────────────┘               │
│                           /            \                        │
│                         否              是                       │
│                          │              │                       │
│                          ▼              ▼                       │
│                     直接返回     merge_context_back()           │
│                                       │                         │
│                                       ▼                         │
│                              ┌──────────────────┐               │
│                              │ 合并策略选择     │               │
│                              │ - append: 追加   │               │
│                              │ - replace: 替换  │               │
│                              │ - merge: 合并    │               │
│                              └──────────────────┘               │
│                                       │                         │
│                                       ▼                         │
│                                 更新父上下文                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 ContextIsolationManager 实现

```python
class ContextIsolationManager:
    """上下文隔离管理器"""

    def __init__(self):
        self._isolated_contexts: Dict[str, IsolatedContext] = {}

    async def create_isolated_context(
        self,
        parent_context: Optional[ContextWindow],
        config: SubagentContextConfig,
    ) -> IsolatedContext:
        """创建隔离上下文"""
        context_id = str(uuid.uuid4())

        # 根据模式创建窗口
        if config.isolation_mode == ContextIsolationMode.ISOLATED:
            window = self._create_isolated_window(config)
        elif config.isolation_mode == ContextIsolationMode.SHARED:
            window = self._create_shared_window(parent_context, config)
        else:  # FORK
            window = self._create_forked_window(parent_context, config)

        # 创建隔离上下文
        isolated = IsolatedContext(
            context_id=context_id,
            window=window,
            config=config,
            parent_id=None if config.isolation_mode == ContextIsolationMode.ISOLATED
                         else id(parent_context),
        )

        self._isolated_contexts[context_id] = isolated
        return isolated

    def _create_isolated_window(self, config: SubagentContextConfig) -> ContextWindow:
        """ISOLATED: 创建全新的空上下文"""
        return ContextWindow(
            messages=[],
            total_tokens=0,
            max_tokens=config.max_context_tokens,
            available_tools=set(config.allowed_tools) if config.allowed_tools else set(),
            memory_types=set(config.memory_scope.accessible_layers),
            resource_bindings={b.name: b.target for b in config.resource_bindings},
        )

    def _create_shared_window(
        self,
        parent_context: ContextWindow,
        config: SubagentContextConfig,
    ) -> ContextWindow:
        """SHARED: 直接返回父上下文引用"""
        # 实时同步，无需复制
        return parent_context

    def _create_forked_window(
        self,
        parent_context: ContextWindow,
        config: SubagentContextConfig,
    ) -> ContextWindow:
        """FORK: 深拷贝父上下文"""
        # 深拷贝
        forked = ContextWindow(
            messages=[msg.copy() for msg in parent_context.messages],
            total_tokens=parent_context.total_tokens,
            max_tokens=config.max_context_tokens,
            available_tools=set(config.allowed_tools) if config.allowed_tools
                          else parent_context.available_tools.copy(),
            memory_types=set(config.memory_scope.accessible_layers),
            resource_bindings=parent_context.resource_bindings.copy(),
        )

        # 应用记忆范围过滤
        if not config.memory_scope.inherit_parent:
            forked.messages = []
            forked.total_tokens = 0

        # 应用工具过滤
        for denied in config.denied_tools:
            forked.available_tools.discard(denied)

        return forked

    async def merge_context_back(
        self,
        isolated_context: IsolatedContext,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将子 Agent 结果合并回父上下文"""
        if isolated_context.config.isolation_mode == ContextIsolationMode.SHARED:
            # 共享模式已经实时同步，无需合并
            return {"merged": False, "reason": "shared_mode"}

        # 获取父上下文
        parent = self._get_parent_context(isolated_context.parent_id)
        if not parent:
            return {"merged": False, "reason": "parent_not_found"}

        # 根据策略合并
        merge_strategy = result.get("merge_strategy", "append")

        if merge_strategy == "append":
            # 追加消息
            for msg in isolated_context.window.messages:
                parent.messages.append(msg)
                parent.total_tokens += self._estimate_tokens(msg)

        elif merge_strategy == "replace":
            # 替换最后 N 条消息
            replace_count = result.get("replace_count", 0)
            parent.messages = parent.messages[:-replace_count] if replace_count > 0 else parent.messages
            for msg in isolated_context.window.messages:
                parent.messages.append(msg)

        elif merge_strategy == "merge":
            # 合并并去重
            existing_ids = {msg.get("message_id") for msg in parent.messages}
            for msg in isolated_context.window.messages:
                if msg.get("message_id") not in existing_ids:
                    parent.messages.append(msg)

        return {"merged": True, "strategy": merge_strategy}

    async def cleanup_context(self, context_id: str) -> None:
        """清理隔离上下文"""
        if context_id in self._isolated_contexts:
            del self._isolated_contexts[context_id]
```

---

## 六、运行时上下文处理

文件位置: `core_v2/integration/runtime.py`

### 6.1 会话上下文数据结构

```python
@dataclass
class SessionContext:
    """会话上下文"""
    session_id: str                       # 会话 ID
    conv_id: str                          # 对话 ID
    user_id: Optional[str] = None         # 用户 ID
    agent_name: str = "primary"           # Agent 名称
    created_at: datetime = field(default_factory=datetime.now)
    state: RuntimeState = RuntimeState.IDLE
    message_count: int = 0

    # 持久化存储
    storage_conv: Optional[Any] = None    # StorageConversation 实例

    # 上下文窗口
    context_window: Optional[ContextWindow] = None
```

### 6.2 执行流程中的上下文处理

```python
class V2AgentRuntime:
    """V2 Agent 运行时"""

    async def execute(
        self,
        session_id: str,
        message: str,
        stream: bool = True,
        enable_context_loading: bool = True,
        **kwargs,
    ) -> AsyncIterator[V2StreamChunk]:
        """执行 Agent"""

        # 1. 获取会话上下文
        context = await self.get_session(session_id)

        # 2. 设置状态
        context.state = RuntimeState.RUNNING

        # 3. 加载分层上下文
        if enable_context_loading and self._context_middleware:
            context_result = await self._context_middleware.load_context(
                conv_id=context.conv_id,
                task_description=message[:200] if message else None,
            )

            # 更新上下文窗口
            if context_result.get("context"):
                context.context_window = ContextWindow(
                    messages=context_result["messages"],
                    total_tokens=context_result["tokens"],
                )

        # 4. 推送用户消息到记忆
        if self._gpts_memory:
            user_msg = GptsMessage(
                conv_id=context.conv_id,
                role="user",
                content=message,
            )
            await self._gpts_memory.append_message(context.conv_id, user_msg)

        # 5. 执行 Agent
        agent = await self._get_or_create_agent(context, kwargs)

        if stream:
            async for chunk in self._execute_stream(agent, message, context):
                # 推送流式输出
                await self._push_stream_chunk(context.conv_id, chunk)
                yield chunk
        else:
            result = await self._execute_sync(agent, message)
            yield result

        # 6. 恢复状态
        context.state = RuntimeState.IDLE
        context.message_count += 1
```

### 6.3 上下文中间件

```python
class UnifiedContextMiddleware:
    """统一上下文中间件"""

    def __init__(
        self,
        gpts_memory: Optional[GptsMemory] = None,
        project_memory: Optional[ProjectMemoryManager] = None,
        compaction_manager: Optional[ImprovedSessionCompaction] = None,
    ):
        self.gpts_memory = gpts_memory
        self.project_memory = project_memory
        self.compaction_manager = compaction_manager

    async def load_context(
        self,
        conv_id: str,
        task_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """加载完整上下文"""
        result = {
            "messages": [],
            "tokens": 0,
            "context": "",
        }

        # 1. 加载历史消息
        if self.gpts_memory:
            messages = await self.gpts_memory.get_messages(conv_id)
            result["messages"] = messages

        # 2. 加载项目记忆
        if self.project_memory:
            project_context = await self.project_memory.build_context()
            result["context"] = project_context

        # 3. 检测是否需要压缩
        if self.compaction_manager:
            estimated_tokens = self.compaction_manager.token_estimator.estimate_messages(
                result["messages"]
            )

            if estimated_tokens > self.compaction_manager.config.context_window_tokens * 0.8:
                # 触发压缩
                compacted = await self.compaction_manager.compact(
                    result["messages"],
                    trigger=CompactionTrigger.THRESHOLD,
                )
                result["messages"] = compacted.compacted_messages
                result["tokens"] = compacted.compacted_tokens
            else:
                result["tokens"] = estimated_tokens

        return result
```

---

## 七、数据流总览

### 7.1 完整数据流图

```
┌────────────────────────────────────────────────────────────────────────┐
│                        用户输入                                         │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    V2AgentRuntime.execute()                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  1. 获取/创建 SessionContext                                      │  │
│  │  2. 设置状态为 RUNNING                                            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  UnifiedContextMiddleware.load_context()               │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐   │
│  │ 加载历史消息   │  │ 加载项目记忆   │  │ 检测窗口溢出           │   │
│  │ from GptsMemory│  │from ProjectMem │  │ 触发压缩机制           │   │
│  └───────┬────────┘  └───────┬────────┘  └───────────┬────────────┘   │
│          │                   │                       │                  │
│          └───────────────────┴───────────────────────┘                  │
│                              │                                          │
│                              ▼                                          │
│                  构建完整上下文 ContextWindow                           │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Agent 执行循环                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                        think() → decide() → act()                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
│              ┌─────────────────────┼─────────────────────┐             │
│              ▼                     ▼                     ▼             │
│      ┌──────────────┐     ┌──────────────┐     ┌──────────────┐        │
│      │  工具执行    │     │ 子Agent委派  │     │  记忆写入    │        │
│      │              │     │              │     │              │        │
│      │ ToolRegistry │     │SubagentMgr  │     │UnifiedMemory │        │
│      └──────────────┘     │ + ContextIso │     └──────────────┘        │
│                           └──────────────┘                              │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        消息持久化                                       │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐   │
│  │GptsMemory      │  │VectorStore     │  │FileSystem              │   │
│  │(gpts_messages) │  │(embeddings)    │  │(.derisk/MEMORY.md)     │   │
│  └────────────────┘  └────────────────┘  └────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        输出转换                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              CoreV2VisWindow3Converter → VIS 协议                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 八、关键文件索引

| 文件 | 功能 | 关键类/函数 |
|------|------|------------|
| `improved_compaction.py` | 改进的会话压缩 | `ImprovedSessionCompaction`, `ContentProtector`, `KeyInfoExtractor` |
| `memory_compaction.py` | 记忆压缩管理 | `MemoryCompactor`, `ImportanceScorer` |
| `unified_memory/base.py` | 统一记忆接口 | `UnifiedMemoryInterface`, `MemoryItem`, `MemoryType` |
| `unified_memory/unified_manager.py` | 统一记忆管理器 | `UnifiedMemoryManager` |
| `unified_memory/file_backed_storage.py` | 文件存储 | `FileBackedStorage` |
| `unified_memory/gpts_adapter.py` | V1 适配器 | `GptsMemoryAdapter` |
| `unified_memory/message_converter.py` | 消息转换 | `MessageConverter` |
| `project_memory/manager.py` | 项目记忆管理 | `ProjectMemoryManager` |
| `context_isolation/manager.py` | 上下文隔离 | `ContextIsolationManager`, `IsolatedContext` |
| `integration/runtime.py` | 运行时核心 | `V2AgentRuntime`, `SessionContext` |