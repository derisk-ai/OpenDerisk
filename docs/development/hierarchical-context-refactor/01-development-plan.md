# 历史上下文管理重构 - 开发方案

## 一、项目背景

### 1.1 当前问题

| 问题类别 | 具体问题 | 影响范围 | 严重程度 |
|---------|---------|---------|---------|
| 历史丢失 | Core 架构只取首尾消息，中间工作丢失 | 所有多轮对话 | 严重 |
| WorkLog 丢失 | 历史加载不包含 WorkLog | 所有使用工具的对话 | 严重 |
| 上下文断层 | 第100轮对话质量远低于第1轮 | 长对话场景 | 严重 |
| 记忆系统混乱 | 三套记忆系统未协同 (GptsMemory, UnifiedMemoryManager, AgentBase._messages) | 系统可维护性 | 中等 |
| 资源浪费 | HierarchicalContext 系统完全未使用 | 技术债务 | 中等 |

### 1.2 现有资产盘点

**已实现但未使用的系统**：

位置：`derisk/agent/shared/hierarchical_context/`

| 组件 | 功能 | 状态 | 文件 |
|------|------|------|------|
| 章节索引器 | Chapter/Section 二级索引 | ✓ 已实现 | chapter_indexer.py |
| 分层压缩器 | LLM/Rules/Hybrid 三种压缩策略 | ✓ 已实现 | hierarchical_compactor.py |
| 阶段检测器 | 5个任务阶段自动检测 | ✓ 已实现 | phase_transition_detector.py |
| 回溯工具 | recall_section/recall_chapter/search_history | ✓ 已实现 | recall_tool.py |
| V2集成器 | HierarchicalContextV2Integration | ✓ 已实现 | integration_v2.py |
| 配置系统 | MemoryPromptConfig + CompactionConfig | ✓ 已实现 | compaction_config.py |

**结论**：80% 功能已实现，只需集成和适配。

### 1.3 项目目标

**核心目标**：

1. **解决会话连续追问上下文丢失问题**
   - 第1轮到第100轮对话保持相同的上下文质量
   - 完整保留工作过程（WorkLog），支持历史回溯
   - 智能压缩管理，优化上下文窗口利用率

2. **统一 Core 和 Core V2 记忆和文件系统架构**
   - 整合三套记忆系统（GptsMemory, UnifiedMemoryManager, AgentBase._messages）
   - 统一文件系统持久化机制（AgentFileSystem）
   - 建立 Core 和 Core V2 共享的记忆管理层

3. **激活沉睡的 HierarchicalContext 系统**
   - 利用已实现的 80% 功能，快速上线
   - 建立统一的上下文管理标准
   - 提升系统可维护性和可扩展性

**量化指标**：
- 历史加载成功率 > 99.9%
- 历史加载延迟 < 500ms (P95)
- 测试覆盖率 > 80%
- 压缩效率 > 50%（节省 Token 比例）
- 会话连续追问上下文完整率 = 100%

---

## 二、技术方案设计

### 2.1 整体架构（五层架构）

```
┌─────────────────────────────────────────────────────────────────┐
│                  应用层 (Application Layer)                      │
│  agent_chat.py - 入口统一，使用 UnifiedContextMiddleware        │
│  RuntimeManager - Core V2 运行时管理                             │
└─────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────┐
│           统一上下文中间件                  │
│  职责：历史加载 + 会话管理 + 检查点恢复                           │
│  核心类：UnifiedContextMiddleware                                │
└─────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────┐
│       HierarchicalContext 核心系统 (已实现 ✓)                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  HierarchicalContextV2Integration                        │  │
│  │  ├─ ChapterIndexer         (章节索引器)                   │  │
│  │  ├─ HierarchicalCompactor  (分层压缩器)                   │  │
│  │  ├─ RecallToolManager      (回溯工具管理)                 │  │
│  │  └─ PhaseTransitionDetector (阶段检测器)                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│  + WorkLog → Section 转换层 (新增)                              │
└─────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                   持久化层                       │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐        │
│  │  GptsMemory  │  │ AgentFileSys  │  │ UnifiedMemory│        │
│  │  (数据库)     │  │ (文件存储)     │  │ Manager      │        │
│  └──────────────┘  └───────────────┘  └──────────────┘        │
│  协作：WorkLog + GptsMessage → HierarchicalContext Index       │
└─────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────┐
│                   文件系统层                   │
│  .agent_memory/                                                 │
│  ├── sessions/{conv_id}/                                        │
│  │   ├── memory_index.json        # 章节索引                    │
│  │   ├── chapters/                # 章节持久化                  │
│  │   │   ├── chapter_001.json                                   │
│  │   │   └── chapter_002.json                                   │
│  │   └── worklog_archive/         # WorkLog 归档                │
│  ├── PROJECT_MEMORY.md            # 项目共享记忆                │
│  └── checkpoints/                 # 检查点存储                  │
│      └── {conv_id}_checkpoint.json                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 各层职责说明

**第一层：应用层 (Application Layer)**
- agent_chat.py：Core 架构的统一入口
- RuntimeManager：Core V2 架构的运行时管理
- 职责：接收用户请求，调用中间件层服务

**第二层：统一上下文中间件**
- UnifiedContextMiddleware：核心中间件
- 职责：
  - 统一历史加载接口
  - WorkLog → Section 转换
  - 会话上下文管理
  - 检查点保存和恢复
  - 缓存管理

**第三层：HierarchicalContext 核心系统**
- 已实现的核心组件：
  - ChapterIndexer：章节/节索引管理
  - HierarchicalCompactor：智能压缩
  - RecallToolManager：回溯工具管理
  - PhaseTransitionDetector：阶段检测
- 新增功能：
  - WorkLog → Section 转换层
  - 与中间件层对接

**第四层：持久化层**
- GptsMemory：数据库存储（对话消息、WorkLog）
- AgentFileSystem：文件系统存储（章节索引、归档）
- UnifiedMemoryManager：统一记忆管理
- 职责：协调三套记忆系统，统一存储接口

**第五层：文件系统层**
- .agent_memory/：Root 目录
  - sessions/{conv_id}/：会话级持久化
  - PROJECT_MEMORY.md：项目共享记忆
  - checkpoints/：检查点存储
- 职责：提供文件级持久化支持，支持版本管理和共享

### 2.3 核心组件职责

| 层级 | 组件 | 职责 | 类型 | 工作量 |
|------|------|------|------|--------|
| **应用层** | agent_chat.py | Core 架构入口，调用中间件 | 改造 | 20% |
| **应用层** | runtime.py | Core V2 运行时，调用中间件 | 改造 | 15% |
| **中间件层** | UnifiedContextMiddleware | 统一历史加载、WorkLog转换、会话管理 | 新增 | 100% |
| **核心系统层** | HierarchicalContextV2Integration | 分层上下文集成 | 已有 | 0% |
| **核心系统层** | ChapterIndexer | 章节/节索引管理 | 已有 | 0% |
| **核心系统层** | HierarchicalCompactor | 智能压缩 | 已有 | 0% |
| **核心系统层** | RecallToolManager | 回溯工具管理 | 已有 | 0% |
| **核心系统层** | WorkLog转换层 | WorkEntry → Section | 新增 | 100% |
| **持久化层** | GptsMemory | 数据库存储 | 已有 | 0% |
| **持久化层** | AgentFileSystem | 文件系统存储 | 已有 | 0% |
| **持久化层** | UnifiedMemoryManager | 统一记忆管理 | 统合 | 20% |
| **文件系统层** | .agent_memory/ | 文件持久化目录 | 已有 | 0% |

### 2.3 数据流设计

```
用户发起对话
    ↓
agent_chat.py (_inner_chat)
    ↓
UnifiedContextMiddleware.load_context(conv_id)
    ├─→ 推断任务描述
    ├─→ 启动 HierarchicalContext 执行
    ├─→ 加载历史消息 (GptsMemory.get_messages)
    └─→ 加载并转换 WorkLog
        ├─→ GptsMemory.get_work_log(conv_id)
        ├─→ 按任务阶段分组 (_group_worklog_by_phase)
        │   └─→ Dict[TaskPhase, List[WorkEntry]]
        ├─→ 创建章节 (_create_chapter_from_phase)
        │   └─→ WorkEntry → Section (_work_entry_to_section)
        │       ├─→ 确定优先级 (_determine_section_priority)
        │       └─→ 归档长内容 (_archive_long_content)
        └─→ 添加到索引器 (ChapterIndexer.add_chapter)
    ↓
返回 ContextLoadResult
    ├─→ hierarchical_context_text (分层上下文文本)
    ├─→ recent_messages (最近消息)
    ├─→ recall_tools (回溯工具列表)
    └─→ stats (统计信息)
    ↓
注入到 Agent
    ├─→ 注入回溯工具 (_inject_recall_tools)
    └─→ 注入分层上下文到提示 (_inject_hierarchical_context_to_prompt)
    ↓
Agent 执行对话
    ↓
记录执行步骤 (record_step)
    ↓
自动触发压缩 (auto_compact_if_needed)
```

### 2.4 文件结构规划

```
derisk/
├── context/                                    # 新增目录
│   ├── __init__.py
│   ├── unified_context_middleware.py           # 核心中间件
│   ├── gray_release_controller.py              # 灰度控制器
│   └── monitor.py                              # 监控模块
│
├── agent/
│   ├── shared/
│   │   └── hierarchical_context/               # 已有，无需改动
│   │       ├── integration_v2.py
│   │       ├── hierarchical_compactor.py
│   │       └── ...
│   │
│   └── core_v2/
│       └── integration/
│           └── runtime.py                      # 改造
│
└── derisk_serve/
    └── agent/
        └── agents/
            └── chat/
                └── agent_chat.py               # 改造

configs/
└── hierarchical_context_config.yaml            # 新增配置文件

tests/
└── test_unified_context/
    ├── test_middleware.py
    ├── test_worklog_conversion.py
    ├── test_integration.py
    └── test_e2e.py
```

---

## 三、核心设计原则

### 3.1 解决 Core 和 Core V2 统一记忆系统

**问题分析**：

当前存在三套记忆系统并行：
1. GptsMemory（Core 架构，已在使用）
2. UnifiedMemoryManager（Core V2 新设计，未使用）
3. AgentBase._messages（Core V2 运行时缓存）

**统一策略**：

```
┌─────────────────────────────────────────────────────┐
│          UnifiedContextMiddleware（统一入口）        │
│  ↓ Core 和 Core V2 都调用此中间件                    │
├─────────────────────────────────────────────────────┤
│                                                  ↙  │
│  ┌──────────────┐          ┌──────────────────┐    │
│  │  GptsMemory  │ ←主存储→ │ UnifiedMemoryMgr │    │
│  │  (数据库)     │   同步    │ (文件持久化)      │    │
│  └──────────────┘          └──────────────────┘    │
│        ↓                           ↓                │
│  ┌──────────────────────────────────────────────┐  │
│  │        AgentFileSystem (共享文件系统)         │  │
│  │  .agent_memory/sessions/{conv_id}/           │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**实现方式**：

1. **GptsMemory 作为主存储**：
   - 保持现有的数据库存储逻辑
   - Core 和 Core V2 都通过 UnifiedContextMiddleware 访问

2. **UnifiedMemoryManager 作为文件持久化层**：
   - 将 HierarchicalContext Index 持久化到文件系统
   - 支持跨会话共享记忆（PROJECT_MEMORY.md）
   - Core 和 Core V2 共享同一套文件存储

3. **AgentBase._messages 作为运行时缓存**：
   - 初始化时从 GptsMemory 加载历史消息
   - 执行过程中实时更新
   - 会话结束时同步到 GptsMemory

### 3.2 解决会话连续追问上下文不丢失

**问题分析**：

当前在 agent_chat.py 中：
```python
# 只取首尾消息，中间工作丢失
for gpts_conversation in rely_conversations:
    temps = await self.memory.get_messages(gpts_conversation.conv_id)
    if temps and len(temps) > 1:
        historical_dialogues.append(temps[0])    # 只取第一条
        historical_dialogues.append(temps[-1])   # 只取最后一条
```

**解决方案**：

通过 UnifiedContextMiddleware + HierarchicalContext 实现完整历史保留：

```
会话第1轮：
  用户提问 → Agent执行 → WorkLog记录
  ↓
  保存到 GptsMemory + 文件系统持久化

会话第2轮：
  ↓
  UnifiedContextMiddleware.load_context(conv_id)
    ├─→ GptsMemory.get_messages(conv_id)         # 加载历史消息
    ├─→ GptsMemory.get_work_log(conv_id)         # 加载 WorkLog
    ├─→ 加载文件系统中的章节索引
    └─→ 构建完整上下文：HistoryMessage + WorkLog
  ↓
  注入到 Agent → Agent 可查看完整历史 → 执行 → 记录

会话第N轮：
  ↓
  同样的流程，所有历史都可追溯
  ↓
  自动压缩管理（超过阈值自动压缩，保留关键信息）
```

**关键机制**：

1. **完整历史加载**：
   ```python
   context_result = await middleware.load_context(
       conv_id=conv_id,
       include_worklog=True,  # 包含 WorkLog
   )
   ```

2. **自动压缩**：
   - 当历史超过 token 阈值（如40000），自动触发压缩
   - 使用 LLM 生成摘要，保留关键信息
   - 压缩后内容持久化，不丢失

3. **历史回溯**：
   - Agent 可通过工具查看任意历史步骤
   - recall_section(section_id)
   - recall_chapter(chapter_id)

4. **检查点恢复**：
   - 每轮对话结束保存检查点
   - 异常恢复时从检查点恢复
   - 确保不丢失任何上下文

### 3.3 数据同步机制

**GptsMemory ↔ UnifiedMemoryManager 同步**：

```python
async def load_context(conv_id):
    # 1. 从 GptsMemory 加载（主存储）
    messages = await gpts_memory.get_messages(conv_id)
    worklog = await gpts_memory.get_work_log(conv_id)
    
    # 2. 从 UnifiedMemoryManager 加载（文件持久化）
    chapters = await unified_memory.load_chapters(conv_id)
    
    # 3. 合并并构建上下文
    context = build_context(messages, worklog, chapters)
    
    # 4. 同步到文件系统
    await unified_memory.save_index(conv_id, context.chapter_index)
    
    return context
```

**同步策略**：
- 读取时：优先从 GptsMemory 读取，UnifiedMemoryManager 补充
- 写入时：同时写入 GptsMemory（数据库）和 UnifiedMemoryManager（文件）
- 一致性：通过中间件保证两边数据一致

---

## 四、核心实现设计

### 4.1 UnifiedContextMiddleware 核心设计

**类定义**：

```python
class UnifiedContextMiddleware:
    """
    统一上下文中间件
    
    核心职责：
    1. 整合 HierarchicalContextV2Integration
    2. 实现 WorkLog → Section 转换
    3. 协调 GptsMemory 和 AgentFileSystem
    4. 提供统一的历史加载接口
    """
    
    def __init__(
        self,
        gpts_memory: GptsMemory,
        agent_file_system: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        hc_config: Optional[HierarchicalContextConfig] = None,
        compaction_config: Optional[HierarchicalCompactionConfig] = None,
    ):
        ...
    
    # ========== 核心方法 ==========
    
    async def load_context(
        self,
        conv_id: str,
        task_description: Optional[str] = None,
        include_worklog: bool = True,
        token_budget: int = 12000,
        force_reload: bool = False,
    ) -> ContextLoadResult:
        """加载完整的历史上下文（主入口）"""
        ...
    
    async def record_step(
        self,
        conv_id: str,
        action_out: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """记录执行步骤到 HierarchicalContext"""
        ...
    
    # ========== WorkLog 转换方法 ==========
    
    async def _load_and_convert_worklog(
        self,
        conv_id: str,
        hc_manager: HierarchicalContextManager,
    ) -> None:
        """加载 WorkLog 并转换为 Section 结构"""
        ...
    
    async def _group_worklog_by_phase(
        self,
        worklog: List[WorkEntry],
    ) -> Dict[TaskPhase, List[WorkEntry]]:
        """将 WorkLog 按任务阶段分组"""
        ...
    
    async def _work_entry_to_section(
        self,
        entry: WorkEntry,
        index: int,
    ) -> Section:
        """将 WorkEntry 转换为 Section"""
        ...
    
    def _determine_section_priority(self, entry: WorkEntry) -> ContentPriority:
        """确定 Section 优先级"""
        ...
```

**关键实现细节**：

1. **阶段检测算法**：

```python
phase_entries = {
    TaskPhase.EXPLORATION: [],
    TaskPhase.DEVELOPMENT: [],
    TaskPhase.DEBUGGING: [],
    TaskPhase.REFINEMENT: [],
    TaskPhase.DELIVERY: [],
}

current_phase = TaskPhase.EXPLORATION

for entry in worklog:
    # 优先级1：手动标记的阶段
    if "phase" in entry.metadata:
        current_phase = TaskPhase(entry.metadata["phase"])
    
    # 优先级2：失败的操作 → DEBUGGING
    elif not entry.success:
        current_phase = TaskPhase.DEBUGGING
    
    # 优先级3：根据工具名判断
    elif entry.tool in ["read", "glob", "grep", "search"]:
        current_phase = TaskPhase.EXPLORATION
    elif entry.tool in ["write", "edit", "bash", "execute"]:
        current_phase = TaskPhase.DEVELOPMENT
    
    # 优先级4：根据标签判断
    elif any(kw in entry.tags for kw in ["refactor", "optimize"]):
        current_phase = TaskPhase.REFINEMENT
    elif any(kw in entry.tags for kw in ["summary", "document"]):
        current_phase = TaskPhase.DELIVERY
    
    phase_entries[current_phase].append(entry)
```

2. **优先级判断逻辑**：

```python
def _determine_section_priority(self, entry: WorkEntry) -> ContentPriority:
    # CRITICAL: 关键决策、重要发现
    if "critical" in entry.tags or "decision" in entry.tags:
        return ContentPriority.CRITICAL
    
    # HIGH: 关键工具且成功
    if entry.tool in ["write", "bash", "edit"] and entry.success:
        return ContentPriority.HIGH
    
    # MEDIUM: 普通成功调用
    if entry.success:
        return ContentPriority.MEDIUM
    
    # LOW: 失败或低价值操作
    return ContentPriority.LOW
```

### 3.2 agent_chat.py 改造设计

**改造点**：

1. 在 `AgentChat.__init__` 中初始化中间件
2. 在 `_inner_chat` 中替换历史加载逻辑
3. 注入回溯工具到 Agent
4. 注入分层上下文到系统提示

**关键代码**：

```python
# 在 _inner_chat 中

# 旧代码（替换）：
# for gpts_conversation in rely_conversations:
#     temps = await self.memory.get_messages(gpts_conversation.conv_id)
#     if temps and len(temps) > 1:
#         historical_dialogues.append(temps[0])
#         historical_dialogues.append(temps[-1])

# 新代码：
context_result = await self.context_middleware.load_context(
    conv_id=conv_uid,
    task_description=user_query.content if hasattr(user_query, 'content') else str(user_query),
    include_worklog=True,
    token_budget=12000,
)

# 注入回溯工具
await self._inject_recall_tools(agent, context_result.recall_tools)

# 注入分层上下文
await self._inject_hierarchical_context_to_prompt(
    agent,
    context_result.hierarchical_context_text,
)
```

### 3.3 Runtime 改造设计

**改造点**：

1. 在 `V2AgentRuntime.__init__` 中初始化中间件
2. 在 `_execute_stream` 中加载上下文
3. 在执行过程中记录步骤

**关键代码**：

```python
async def _execute_stream(self, agent, message, context, **kwargs):
    # 加载上下文
    hc_context = await self.context_middleware.load_context(
        conv_id=context.conv_id,
        task_description=message,
        include_worklog=True,
    )
    
    # 注入到 Agent context
    agent_context.metadata["hierarchical_context"] = hc_context.hierarchical_context_text
    
    # 注入回溯工具
    await self._inject_tools_to_agent(agent, hc_context.recall_tools)
    
    # 构建带历史的消息
    message_with_context = self._build_message_with_context(
        message,
        hc_context.hierarchical_context_text,
    )
    
    # 执行并记录步骤
    async for chunk in agent.run(message_with_context, stream=True, **kwargs):
        if hasattr(chunk, 'action_out'):
            await self.context_middleware.record_step(
                conv_id=context.conv_id,
                action_out=chunk.action_out,
            )
        yield chunk
```

---

## 四、配置设计

### 4.1 配置文件结构

```yaml
# configs/hierarchical_context_config.yaml

hierarchical_context:
  enabled: true
  
chapter:
  max_chapter_tokens: 10000
  max_section_tokens: 2000
  recent_chapters_full: 2
  middle_chapters_index: 3
  early_chapters_summary: 5

compaction:
  enabled: true
  strategy: "llm_summary"  # llm_summary / rule_based / hybrid
  trigger:
    token_threshold: 40000
  protection:
    protect_recent_chapters: 2
    protect_recent_tokens: 15000

worklog_conversion:
  enabled: true
  phase_detection:
    exploration_tools: ["read", "glob", "grep", "search", "think"]
    development_tools: ["write", "edit", "bash", "execute", "run"]
    refinement_keywords: ["refactor", "optimize", "improve", "enhance"]
    delivery_keywords: ["summary", "document", "conclusion", "report"]

gray_release:
  enabled: false
  gray_percentage: 0
  user_whitelist: []
  app_whitelist: []
  conv_whitelist: []
```

### 4.2 配置加载器

```python
class HierarchicalContextConfigLoader:
    """分层上下文配置加载器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "configs/hierarchical_context_config.yaml"
        self._config_cache: Optional[Dict[str, Any]] = None
    
    def load(self) -> Dict[str, Any]:
        """加载配置"""
        if self._config_cache:
            return self._config_cache
        
        config_file = Path(self.config_path)
        if not config_file.exists():
            return self._get_default_config()
        
        with open(config_file, 'r', encoding='utf-8') as f:
            self._config_cache = yaml.safe_load(f)
        
        return self._config_cache
    
    def get_hc_config(self) -> HierarchicalContextConfig:
        """获取 HierarchicalContext 配置"""
        ...
    
    def get_compaction_config(self) -> HierarchicalCompactionConfig:
        """获取压缩配置"""
        ...
```

---

## 五、灰度发布设计

### 5.1 灰度控制器

```python
class GrayReleaseController:
    """灰度发布控制器"""
    
    def __init__(self, config: GrayReleaseConfig):
        self.config = config
    
    def should_enable_hierarchical_context(
        self,
        user_id: Optional[str] = None,
        app_id: Optional[str] = None,
        conv_id: Optional[str] = None,
    ) -> bool:
        """判断是否启用分层上下文"""
        
        # 1. 检查黑名单
        if user_id and user_id in self.config.user_blacklist:
            return False
        if app_id and app_id in self.config.app_blacklist:
            return False
        
        # 2. 检查白名单
        if user_id and user_id in self.config.user_whitelist:
            return True
        if app_id and app_id in self.config.app_whitelist:
            return True
        if conv_id and conv_id in self.config.conv_whitelist:
            return True
        
        # 3. 流量百分比灰度
        if self.config.gray_percentage > 0:
            hash_key = conv_id or user_id or app_id or "default"
            hash_value = int(hashlib.md5(hash_key.encode()).hexdigest(), 16)
            if (hash_value % 100) < self.config.gray_percentage:
                return True
        
        return False
```

### 5.2 灰度阶段规划

| 阶段 | 对象 | 灰度比例 | 目标 |
|------|------|---------|------|
| 内部测试 | 开发团队内部 | 100% (白名单) | 功能验证 |
| 小规模灰度 | 部分早期用户 | 10% 流量 | 稳定性验证 |
| 中规模灰度 | 扩大用户范围 | 30% 流量 | 兼容性验证 |
| 大规模灰度 | 大部分用户 | 50% 流量 | 全面验证 |
| 全量发布 | 所有用户 | 100% 流量 | 正式上线 |

---

## 六、质量保证

### 6.1 测试策略

**测试金字塔**：
- 单元测试（60%）：WorkLog 转换、阶段检测、优先级判断
- 集成测试（30%）：中间件集成、Runtime 集成
- E2E 测试（10%）：完整对话流程

### 6.2 测试用例清单

| 测试类别 | 测试用例 | 优先级 |
|---------|---------|--------|
| 单元测试 | WorkLog 按阶段分组 - 探索阶段 | P0 |
| 单元测试 | WorkLog 按阶段分组 - 开发阶段 | P0 |
| 单元测试 | WorkLog 按阶段分组 - 调试阶段 | P0 |
| 单元测试 | Section 优先级判断 - CRITICAL | P0 |
| 单元测试 | Section 优先级判断 - HIGH | P0 |
| 单元测试 | WorkEntry → Section 基本转换 | P0 |
| 单元测试 | WorkEntry → Section 长内容归档 | P1 |
| 集成测试 | 上下文基本加载 | P0 |
| 集成测试 | 多阶段上下文加载 | P0 |
| 集成测试 | 回溯工具注入 | P1 |
| E2E 测试 | 完整对话流程 | P0 |
| 性能测试 | 大量 WorkLog 加载性能 | P1 |

### 6.3 验收标准

**功能验收**：
- 历史加载：第100轮对话包含前99轮的关键信息
- WorkLog 保留：历史加载包含 WorkLog 内容
- 章节索引：自动创建章节和节结构
- 回溯工具：Agent 可调用回溯工具查看历史
- 自动压缩：超过阈值自动触发压缩

**性能验收**：
- 历史加载延迟 (P95) < 500ms
- 步骤记录延迟 (P95) < 50ms
- 内存增量 < 100MB/1000会话
- 压缩效率 > 50%

**质量验收**：
- 单元测试覆盖率 > 80%
- 集成测试通过率 = 100%
- 代码审查问题数 = 0 critical

---

## 七、配置管理设计

### 7.1 监控指标

```
hierarchical_context_load_total{status="success"}    # 加载成功次数
hierarchical_context_load_total{status="failure"}    # 加载失败次数
hierarchical_context_load_latency_seconds           # 加载延迟
hierarchical_recall_tool_usage_total{tool_name}     # 回溯工具使用次数
hierarchical_compaction_total{strategy, status}     # 压缩次数
hierarchical_active_sessions                        # 活跃会话数
hierarchical_context_tokens{conv_id}                # 上下文 Token 数
hierarchical_chapter_count{conv_id}                 # 章节数量
```

### 7.2 告警规则

| 指标 | 阈值 | 级别 |
|------|------|------|
| 历史加载错误率 | > 0.1% | 警告 |
| 历史加载错误率 | > 0.5% | 严重 |
| 历史加载延迟 (P95) | > 800ms | 警告 |
| 历史加载延迟 (P95) | > 1.5s | 严重 |