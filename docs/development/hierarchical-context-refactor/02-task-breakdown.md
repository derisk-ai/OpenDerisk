# 历史上下文管理重构 - 任务拆分计划

## 一、任务概览

### 1.1 任务分解总览

| 阶段 | 任务数 | 说明 |
|------|--------|------|
| Phase 1: 核心开发 | 8个任务 | UnifiedContextMiddleware 实现 + WorkLog 转换 |
| Phase 2: 集成改造 | 6个任务 | agent_chat.py + runtime.py 改造 |
| Phase 3: 测试验证 | 5个任务 | 单元测试 + 集成测试 + E2E测试 |
| Phase 4: 配置与灰度 | 4个任务 | 配置加载器 + 灰度控制器 + 监控 |
| Phase 5: 文档与发布 | 3个任务 | 文档编写 + 代码审查 + 发布准备 |

### 1.2 任务依赖关系图

```
Phase 1: 核心开发
    ├─ T1.1 项目结构创建
    │   ↓
    ├─ T1.2 UnifiedContextMiddleware 框架
    │   ↓
    ├─ T1.3 WorkLog 阶段分组
    │   ↓
    ├─ T1.4 Section 转换逻辑
    │   ↓
    ├─ T1.5 优先级判断
    │   ↓
    ├─ T1.6 长内容归档
    │   ↓
    ├─ T1.7 检查点机制
    │   ↓
    └─ T1.8 缓存管理

Phase 2: 集成改造 (依赖 Phase 1 完成)
    ├─ T2.1 agent_chat.py 初始化改造
    │   ↓
    ├─ T2.2 agent_chat.py 历史加载改造
    │   ↓
    ├─ T2.3 agent_chat.py 工具注入
    │   ↓
    ├─ T2.4 runtime.py 初始化改造
    │   ↓
    ├─ T2.5 runtime.py 执行流程改造
    │   ↓
    └─ T2.6 runtime.py 步骤记录

Phase 3: 测试验证 (依赖 Phase 2 完成)
    ├─ T3.1 WorkLog 转换单元测试
    │   ↓
    ├─ T3.2 中间件单元测试
    │   ↓
    ├─ T3.3 agent_chat.py 集成测试
    │   ↓
    ├─ T3.4 runtime.py 集成测试
    │   ↓
    └─ T3.5 E2E 完整流程测试

Phase 4: 配置与灰度 (依赖 Phase 3 完成)
    ├─ T4.1 配置加载器实现
    │   ↓
    ├─ T4.2 灰度控制器实现
    │   ↓
    ├─ T4.3 监控模块实现
    │   ↓
    └─ T4.4 性能优化

Phase 5: 文档与发布 (依赖 Phase 4 完成)
    ├─ T5.1 技术文档编写
    │   ↓
    ├─ T5.2 代码审查
    │   ↓
    └─ T5.3 发布准备
```

---

## 二、Phase 1: 核心开发（8个任务）

### T1.1 项目结构创建

**优先级**: P0  
**依赖**: 无

**任务描述**:
创建必要的目录结构和初始化文件

**实现步骤**:

1. 创建目录结构：
```bash
mkdir -p derisk/context
mkdir -p tests/test_unified_context
mkdir -p config
```

2. 创建 `__init__.py` 文件：
```python
# derisk/context/__init__.py
from .unified_context_middleware import UnifiedContextMiddleware, ContextLoadResult

__all__ = ["UnifiedContextMiddleware", "ContextLoadResult"]
```

3. 创建配置文件：
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
  strategy: "llm_summary"
  trigger:
    token_threshold: 40000

worklog_conversion:
  enabled: true
```

**交付物**:
- [ ] `derisk/context/__init__.py`
- [ ] `configs/hierarchical_context_config.yaml`
- [ ] `tests/test_unified_context/__init__.py`

**验收标准**:
- 目录结构创建完成
- 配置文件可正常加载
- 模块可正常导入

---

### T1.2 UnifiedContextMiddleware 框架

**优先级**: P0  
**依赖**: T1.1

**任务描述**:
实现 UnifiedContextMiddleware 核心框架

**实现步骤**:

1. 创建文件 `derisk/context/unified_context_middleware.py`

2. 实现 ContextLoadResult 数据类：
```python
@dataclass
class ContextLoadResult:
    """上下文加载结果"""
    
    conv_id: str
    task_description: str
    chapter_index: ChapterIndexer
    hierarchical_context_text: str
    recent_messages: List[GptsMessage]
    recall_tools: List[Any]
    stats: Dict[str, Any] = field(default_factory=dict)
    hc_integration: Optional[HierarchicalContextV2Integration] = None
```

3. 实现 UnifiedContextMiddleware 类框架：
```python
class UnifiedContextMiddleware:
    def __init__(
        self,
        gpts_memory: GptsMemory,
        agent_file_system: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        hc_config: Optional[HierarchicalContextConfig] = None,
        compaction_config: Optional[HierarchicalCompactionConfig] = None,
    ):
        self.gpts_memory = gpts_memory
        self.file_system = agent_file_system
        self.llm_client = llm_client
        
        self.hc_config = hc_config or HierarchicalContextConfig()
        self.compaction_config = compaction_config or HierarchicalCompactionConfig(
            enabled=True,
            strategy=CompactionStrategy.LLM_SUMMARY,
        )
        
        self.hc_integration = HierarchicalContextV2Integration(
            file_system=agent_file_system,
            llm_client=llm_client,
            config=self.hc_config,
        )
        
        self._conv_contexts: Dict[str, ContextLoadResult] = {}
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """初始化中间件"""
        await self.hc_integration.initialize()
```

4. 实现主入口方法框架：
```python
async def load_context(
    self,
    conv_id: str,
    task_description: Optional[str] = None,
    include_worklog: bool = True,
    token_budget: int = 12000,
    force_reload: bool = False,
) -> ContextLoadResult:
    """加载完整的历史上下文（主入口）"""
    # TODO: 实现加载逻辑
    pass
```

**交付物**:
- [ ] `derisk/context/unified_context_middleware.py`
- [ ] ContextLoadResult 数据类
- [ ] UnifiedContextMiddleware 类框架

**验收标准**:
- 类可正常实例化
- initialize() 方法可正常调用
- 类型检查通过

---

### T1.3 WorkLog 阶段分组

**优先级**: P0  
**依赖**: T1.2

**任务描述**:
实现 WorkLog 按任务阶段分组的逻辑

**实现步骤**:

1. 在 UnifiedContextMiddleware 中添加方法：
```python
async def _group_worklog_by_phase(
    self,
    worklog: List[WorkEntry],
) -> Dict[TaskPhase, List[WorkEntry]]:
    """将 WorkLog 按任务阶段分组"""
    
    phase_entries = {
        TaskPhase.EXPLORATION: [],
        TaskPhase.DEVELOPMENT: [],
        TaskPhase.DEBUGGING: [],
        TaskPhase.REFINEMENT: [],
        TaskPhase.DELIVERY: [],
    }
    
    current_phase = TaskPhase.EXPLORATION
    exploration_tools = {"read", "glob", "grep", "search", "think"}
    development_tools = {"write", "edit", "bash", "execute", "run"}
    refinement_keywords = {"refactor", "optimize", "improve", "enhance"}
    delivery_keywords = {"summary", "document", "conclusion", "report"}
    
    for entry in worklog:
        # 优先级1：手动标记的阶段
        if "phase" in entry.metadata:
            phase_value = entry.metadata["phase"]
            if isinstance(phase_value, str):
                try:
                    current_phase = TaskPhase(phase_value)
                except ValueError:
                    pass
        
        # 优先级2：失败的操作 → DEBUGGING
        elif not entry.success:
            current_phase = TaskPhase.DEBUGGING
        
        # 优先级3：根据工具名判断
        elif entry.tool in exploration_tools:
            current_phase = TaskPhase.EXPLORATION
        elif entry.tool in development_tools:
            current_phase = TaskPhase.DEVELOPMENT
        
        # 优先级4：根据标签判断
        elif any(kw in entry.tags for kw in refinement_keywords):
            current_phase = TaskPhase.REFINEMENT
        elif any(kw in entry.tags for kw in delivery_keywords):
            current_phase = TaskPhase.DELIVERY
        
        phase_entries[current_phase].append(entry)
    
    # 过滤空阶段
    return {phase: entries for phase, entries in phase_entries.items() if entries}
```

2. 添加单元测试：
```python
# tests/test_unified_context/test_worklog_conversion.py

async def test_group_worklog_by_phase_exploration():
    """测试探索阶段分组"""
    middleware = create_test_middleware()
    
    entries = [
        WorkEntry(timestamp=1.0, tool="read", success=True),
        WorkEntry(timestamp=2.0, tool="glob", success=True),
        WorkEntry(timestamp=3.0, tool="grep", success=True),
    ]
    
    result = await middleware._group_worklog_by_phase(entries)
    
    assert len(result[TaskPhase.EXPLORATION]) == 3
    assert len(result[TaskPhase.DEVELOPMENT]) == 0
```

**交付物**:
- [ ] _group_worklog_by_phase 方法实现
- [ ] 单元测试（至少覆盖探索、开发、调试三个阶段）

**验收标准**:
- 阶段分组准确率 > 95%
- 单元测试通过
- 边界情况处理正确（空列表、单个条目等）

---

### T1.4 Section 转换逻辑

**优先级**: P0  
**依赖**: T1.2, T1.3

**任务描述**:
实现 WorkEntry → Section 的转换逻辑

**实现步骤**:

1. 实现章节创建方法：
```python
async def _create_chapter_from_phase(
    self,
    conv_id: str,
    phase: TaskPhase,
    entries: List[WorkEntry],
) -> Chapter:
    """从阶段和 WorkEntry 创建章节"""
    
    first_timestamp = int(entries[0].timestamp)
    chapter_id = f"chapter_{phase.value}_{first_timestamp}"
    title = self._generate_chapter_title(phase, entries)
    
    sections = []
    for idx, entry in enumerate(entries):
        section = await self._work_entry_to_section(entry, idx)
        sections.append(section)
    
    chapter = Chapter(
        chapter_id=chapter_id,
        phase=phase,
        title=title,
        summary="",  # 后续由压缩器生成
        sections=sections,
        created_at=entries[0].timestamp,
        tokens=sum(s.tokens for s in sections),
        is_compacted=False,
    )
    
    return chapter
```

2. 实现 Section 转换方法：
```python
async def _work_entry_to_section(
    self,
    entry: WorkEntry,
    index: int,
) -> Section:
    """将 WorkEntry 转换为 Section"""
    
    priority = self._determine_section_priority(entry)
    section_id = f"section_{int(entry.timestamp)}_{entry.tool}_{index}"
    
    content = entry.summary or ""
    detail_ref = None
    
    # 长内容归档
    if entry.result and len(entry.result) > 500:
        detail_ref = await self._archive_long_content(entry)
        content = entry.summary or entry.result[:200] + "..."
    
    # 构建完整内容
    full_content = f"**工具**: {entry.tool}\n"
    if entry.summary:
        full_content += f"**摘要**: {entry.summary}\n"
    if content:
        full_content += f"**内容**: {content}\n"
    if not entry.success:
        full_content += f"**状态**: ❌ 失败\n"
        if entry.result:
            full_content += f"**错误**: {entry.result[:200]}\n"
    
    return Section(
        section_id=section_id,
        step_name=f"{entry.tool} - {entry.summary[:30] if entry.summary else '执行'}",
        content=full_content,
        detail_ref=detail_ref,
        priority=priority,
        timestamp=entry.timestamp,
        tokens=len(full_content) // 4,
        metadata={
            "tool": entry.tool,
            "args": entry.args,
            "success": entry.success,
            "original_tokens": entry.tokens,
            "tags": entry.tags,
        },
    )
```

3. 实现章节标题生成：
```python
def _generate_chapter_title(
    self,
    phase: TaskPhase,
    entries: List[WorkEntry],
) -> str:
    """生成章节标题"""
    
    phase_titles = {
        TaskPhase.EXPLORATION: "需求探索与分析",
        TaskPhase.DEVELOPMENT: "功能开发与实现",
        TaskPhase.DEBUGGING: "问题调试与修复",
        TaskPhase.REFINEMENT: "优化与改进",
        TaskPhase.DELIVERY: "总结与交付",
    }
    
    base_title = phase_titles.get(phase, phase.value)
    key_tools = list(set(e.tool for e in entries[:5]))
    
    if key_tools:
        tools_str = ", ".join(key_tools[:3])
        return f"{base_title} ({tools_str})"
    
    return base_title
```

**交付物**:
- [ ] _create_chapter_from_phase 方法
- [ ] _work_entry_to_section 方法
- [ ] _generate_chapter_title 方法
- [ ] 单元测试

**验收标准**:
- 转换正确性：WorkEntry 所有字段正确映射到 Section
- 内容格式：生成的 content 包含工具名称和摘要
- 章节标题包含阶段名称和关键工具

---

### T1.5 优先级判断逻辑

**优先级**: P0  
**依赖**: T1.2

**任务描述**:
实现 Section 优先级判断逻辑

**实现步骤**:

1. 实现优先级判断方法：
```python
def _determine_section_priority(self, entry: WorkEntry) -> ContentPriority:
    """确定 Section 优先级"""
    
    # CRITICAL: 任务关键（标签标记）
    if "critical" in entry.tags or "decision" in entry.tags:
        return ContentPriority.CRITICAL
    
    # HIGH: 关键工具且成功
    critical_tools = {"write", "bash", "edit", "execute"}
    if entry.tool in critical_tools and entry.success:
        return ContentPriority.HIGH
    
    # MEDIUM: 普通成功调用
    if entry.success:
        return ContentPriority.MEDIUM
    
    # LOW: 失败或低价值操作
    return ContentPriority.LOW
```

2. 添加单元测试：
```python
async def test_determine_section_priority_critical():
    """测试 CRITICAL 优先级"""
    middleware = create_test_middleware()
    
    entry = WorkEntry(
        timestamp=1.0,
        tool="write",
        success=True,
        tags=["critical", "decision"],
    )
    
    priority = middleware._determine_section_priority(entry)
    assert priority == ContentPriority.CRITICAL

async def test_determine_section_priority_high():
    """测试 HIGH 优先级"""
    middleware = create_test_middleware()
    
    entry = WorkEntry(
        timestamp=1.0,
        tool="bash",
        success=True,
        tags=[],
    )
    
    priority = middleware._determine_section_priority(entry)
    assert priority == ContentPriority.HIGH

async def test_determine_section_priority_low():
    """测试 LOW 优先级（失败操作）"""
    middleware = create_test_middleware()
    
    entry = WorkEntry(
        timestamp=1.0,
        tool="read",
        success=False,
    )
    
    priority = middleware._determine_section_priority(entry)
    assert priority == ContentPriority.LOW
```

**交付物**:
- [ ] _determine_section_priority 方法
- [ ] 所有优先级的单元测试

**验收标准**:
- CRITICAL: 带 critical 或 decision 标签
- HIGH: 关键工具 + 成功
- MEDIUM: 普通成功调用
- LOW: 失败或低价值
- 单元测试覆盖率 100%

---

### T1.6 长内容归档

**优先级**: P1  
**依赖**: T1.2

**任务描述**:
实现长内容归档到文件系统的逻辑

**实现步骤**:

1. 实现归档方法：
```python
async def _archive_long_content(self, entry: WorkEntry) -> str:
    """归档长内容到文件系统"""
    
    if not self.file_system:
        return None
    
    try:
        archive_dir = f"worklog_archive/{entry.timestamp}"
        archive_file = f"{archive_dir}/{entry.tool}.json"
        
        archive_data = {
            "timestamp": entry.timestamp,
            "tool": entry.tool,
            "args": entry.args,
            "result": entry.result,
            "summary": entry.summary,
            "success": entry.success,
            "tokens": entry.tokens,
        }
        
        await self.file_system.write_file(
            file_path=archive_file,
            content=json.dumps(archive_data, ensure_ascii=False, indent=2),
        )
        
        return archive_file
        
    except Exception as e:
        logger.warning(f"[UnifiedContextMiddleware] 归档失败: {e}")
        return None
```

2. 在 Section 转换中集成归档：
```python
async def _work_entry_to_section(self, entry: WorkEntry, index: int) -> Section:
    content = entry.summary or ""
    detail_ref = None
    
    # 如果结果很长，归档到文件系统
    if entry.result and len(entry.result) > 500:
        detail_ref = await self._archive_long_content(entry)
        content = entry.summary or entry.result[:200] + "..."
    
    # ...
```

3. 添加单元测试：
```python
async def test_archive_long_content():
    """测试长内容归档"""
    middleware = create_test_middleware_with_filesystem()
    
    entry = WorkEntry(
        timestamp=1.0,
        tool="bash",
        result="x" * 1000,  # 长内容
        summary="运行测试",
        success=True,
    )
    
    section = await middleware._work_entry_to_section(entry, 0)
    
    assert section.detail_ref is not None
    assert len(section.content) < len(entry.result)
```

**交付物**:
- [ ] _archive_long_content 方法
- [ ] 单元测试
- [ ] 异常处理逻辑

**验收标准**:
- 长内容（>500字符）被归档
- 归档文件路径正确返回
- 异常情况不影响主流程

---

### T1.7 检查点机制

**优先级**: P1  
**依赖**: T1.2

**任务描述**:
实现检查点保存和恢复机制

**实现步骤**:

1. 实现检查点保存：
```python
async def save_checkpoint(
    self,
    conv_id: str,
    checkpoint_path: Optional[str] = None,
) -> str:
    """保存检查点"""
    
    checkpoint_data = self.hc_integration.get_checkpoint_data(conv_id)
    
    if not checkpoint_data:
        raise ValueError(f"No context found for conv_id: {conv_id}")
    
    if not checkpoint_path:
        checkpoint_path = f"checkpoints/{conv_id}_checkpoint.json"
    
    # 使用 AgentFileSystem 或本地文件系统
    if self.file_system:
        await self.file_system.write_file(
            file_path=checkpoint_path,
            content=checkpoint_data.to_json(),
        )
    else:
        # 本地文件系统
        import os
        os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            f.write(checkpoint_data.to_json())
    
    logger.info(f"[UnifiedContextMiddleware] 保存检查点: {checkpoint_path}")
    return checkpoint_path
```

2. 实现检查点恢复：
```python
async def restore_checkpoint(
    self,
    conv_id: str,
    checkpoint_path: str,
) -> ContextLoadResult:
    """从检查点恢复"""
    
    # 读取检查点数据
    if self.file_system:
        checkpoint_json = await self.file_system.read_file(checkpoint_path)
    else:
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            checkpoint_json = f.read()
    
    from derisk.agent.shared.hierarchical_context import HierarchicalContextCheckpoint
    checkpoint_data = HierarchicalContextCheckpoint.from_json(checkpoint_json)
    
    # 恢复到集成器
    await self.hc_integration.restore_from_checkpoint(conv_id, checkpoint_data)
    
    # 重新加载上下文
    return await self.load_context(conv_id, force_reload=True)
```

**交付物**:
- [ ] save_checkpoint 方法
- [ ] restore_checkpoint 方法
- [ ] 单元测试

**验收标准**:
- 检查点可保存和恢复
- 恢复后的状态与保存前一致
- 支持文件系统和本地存储

---

### T1.8 缓存管理

**优先级**: P1  
**依赖**: T1.2

**任务描述**:
实现上下文缓存机制

**实现步骤**:

1. 在 load_context 中添加缓存逻辑：
```python
async def load_context(
    self,
    conv_id: str,
    task_description: Optional[str] = None,
    include_worklog: bool = True,
    token_budget: int = 12000,
    force_reload: bool = False,
) -> ContextLoadResult:
    """加载完整的历史上下文（主入口）"""
    
    # 1. 检查缓存
    if not force_reload and conv_id in self._conv_contexts:
        logger.debug(f"[UnifiedContextMiddleware] 使用缓存上下文: {conv_id[:8]}")
        return self._conv_contexts[conv_id]
    
    async with self._lock:
        # 双重检查
        if not force_reload and conv_id in self._conv_contexts:
            return self._conv_contexts[conv_id]
        
        # ... 执行加载逻辑 ...
        
        # 缓存结果
        self._conv_contexts[conv_id] = result
        
        return result
```

2. 实现缓存清理：
```python
async def cleanup_context(self, conv_id: str) -> None:
    """清理上下文缓存"""
    
    await self.hc_integration.cleanup_execution(conv_id)
    
    if conv_id in self._conv_contexts:
        del self._conv_contexts[conv_id]
    
    logger.info(f"[UnifiedContextMiddleware] 清理上下文: {conv_id[:8]}")

def clear_all_cache(self) -> None:
    """清理所有缓存"""
    self._conv_contexts.clear()
    logger.info("[UnifiedContextMiddleware] 清理所有缓存")
```

**交付物**:
- [ ] 缓存逻辑实现
- [ ] 清理方法实现
- [ ] 单元测试

**验收标准**:
- 缓存命中时不重复加载
- force_reload 可强制刷新
- 清理方法正确移除缓存

---

## 三、Phase 2: 集成改造（6个任务）

### T2.1 agent_chat.py 初始化改造

**优先级**: P0  
**依赖**: Phase 1 完成

**任务描述**:
在 AgentChat.__init__ 中初始化 UnifiedContextMiddleware

**实现步骤**:

1. 在 `agent_chat.py` 中导入：
```python
# 在文件顶部导入
from derisk.context.unified_context_middleware import UnifiedContextMiddleware
from derisk.agent.shared.hierarchical_context import (
    HierarchicalContextConfig,
    HierarchicalCompactionConfig,
    CompactionStrategy,
)
```

2. 在 `AgentChat.__init__` 中添加初始化：
```python
def __init__(
    self,
    system_app: SystemApp,
    gpts_memory: Optional[GptsMemory] = None,
    llm_provider: Optional[DefaultLLMClient] = None,
):
    # ... 原有代码 ...
    
    # 新增：初始化统一上下文中间件
    self.context_middleware = UnifiedContextMiddleware(
        gpts_memory=self.memory,
        agent_file_system=None,  # 后续在 _inner_chat 中设置
        llm_client=llm_provider,
        hc_config=HierarchicalContextConfig(
            max_chapter_tokens=10000,
            max_section_tokens=2000,
            recent_chapters_full=2,
            middle_chapters_index=3,
            early_chapters_summary=5,
        ),
        compaction_config=HierarchicalCompactionConfig(
            enabled=True,
            strategy=CompactionStrategy.LLM_SUMMARY,
            token_threshold=40000,
            protect_recent_chapters=2,
        ),
    )
```

**交付物**:
- [ ] agent_chat.py 改造
- [ ] 导入语句添加
- [ ] 初始化代码添加

**验收标准**:
- AgentChat 可正常实例化
- context_middleware 属性存在
- 配置参数正确传递

---

### T2.2 agent_chat.py 历史加载改造

**优先级**: P0  
**依赖**: T2.1

**任务描述**:
在 _inner_chat 中替换历史加载逻辑

**实现步骤**:

1. 在 `_inner_chat` 开始处添加：
```python
async def _inner_chat(
    self,
    user_query,
    conv_session_id,
    conv_uid,
    gpts_app,
    agent_memory,
    is_retry_chat,
    last_speaker_name,
    init_message_rounds,
    historical_dialogues,  # 旧参数，将废弃
    user_code,
    sys_code,
    stream,
    chat_in_params,
    **ext_info,
):
    """核心聊天逻辑 - 已集成 HierarchicalContext"""
    
    # ========== 步骤1：设置文件系统 ==========
    if hasattr(agent_memory, 'file_system'):
        self.context_middleware.file_system = agent_memory.file_system
    
    await self.context_middleware.initialize()
    
    # ========== 步骤2：使用中间件加载上下文 ==========
    # 旧代码（替换）：
    # for gpts_conversation in rely_conversations:
    #     temps = await self.memory.get_messages(gpts_conversation.conv_id)
    #     if temps and len(temps) > 1:
    #         historical_dialogues.append(temps[0])
    #         historical_dialogues.append(temps[-1])
    
    # 新代码：使用 UnifiedContextMiddleware
    context_result = await self.context_middleware.load_context(
        conv_id=conv_uid,
        task_description=user_query.content if hasattr(user_query, 'content') else str(user_query),
        include_worklog=True,
        token_budget=12000,
    )
    
    logger.info(
        f"[AgentChat] 已加载上下文: "
        f"chapters={context_result.stats.get('chapter_count', 0)}, "
        f"sections={context_result.stats.get('section_count', 0)}"
    )
    
    # ... 后续使用 context_result ...
```

2. 更新 AgentContext 创建：
```python
agent_context = AgentContext(
    conv_id=conv_uid,
    gpts_app=gpts_app,
    agent_memory=agent_memory,
    visitor_target_var={},
    init_message_rounds=init_message_rounds,
    chat_in_params=chat_in_params,
    # 新增：分层上下文
    hierarchical_context=context_result.hierarchical_context_text,
)
```

**交付物**:
- [ ] _inner_chat 方法改造
- [ ] 历史加载逻辑替换
- [ ] 日志记录添加

**验收标准**:
- 上下文可正常加载
- 日志输出正确
- 向下兼容（历史消息仍可访问）

---

### T2.3 agent_chat.py 工具注入

**优先级**: P0  
**依赖**: T2.2

**任务描述**:
实现回溯工具和分层上下文的注入

**实现步骤**:

1. 实现工具注入方法：
```python
async def _inject_recall_tools(
    self,
    agent: Any,
    recall_tools: List[Any],
) -> None:
    """注入回溯工具到 Agent"""
    
    if not recall_tools:
        return
    
    logger.info(f"[AgentChat] 注入 {len(recall_tools)} 个回溯工具")
    
    # Core V1: ConversableAgent
    if hasattr(agent, 'available_system_tools'):
        for tool in recall_tools:
            agent.available_system_tools[tool.name] = tool
            logger.debug(f"[AgentChat] 注入工具到 available_system_tools: {tool.name}")
    
    # Core V2: AgentBase
    elif hasattr(agent, 'tools') and hasattr(agent.tools, 'register'):
        for tool in recall_tools:
            agent.tools.register(tool)
            logger.debug(f"[AgentChat] 注册工具到 tools: {tool.name}")
    
    else:
        logger.warning("[AgentChat] Agent 不支持工具注入")
```

2. 实现 Prompt 注入方法：
```python
async def _inject_hierarchical_context_to_prompt(
    self,
    agent: Any,
    hierarchical_context: str,
) -> None:
    """注入分层上下文到系统提示"""
    
    if not hierarchical_context:
        return
    
    from derisk.agent.shared.hierarchical_context import (
        integrate_hierarchical_context_to_prompt,
    )
    
    # 方式1：直接修改系统提示
    if hasattr(agent, 'system_prompt'):
        original_prompt = agent.system_prompt or ""
        
        integrated_prompt = integrate_hierarchical_context_to_prompt(
            original_system_prompt=original_prompt,
            hierarchical_context=hierarchical_context,
        )
        
        agent.system_prompt = integrated_prompt
        logger.info("[AgentChat] 已注入分层上下文到系统提示")
    
    # 方式2：通过 register_variables（ReActMasterAgent）
    elif hasattr(agent, 'register_variables'):
        agent.register_variables(
            hierarchical_context=hierarchical_context,
        )
        logger.info("[AgentChat] 已通过 register_variables 注入上下文")
```

3. 在 _inner_chat 中调用注入：
```python
# 注入回溯工具
if context_result.recall_tools:
    await self._inject_recall_tools(agent, context_result.recall_tools)

# 注入分层上下文到系统提示
if context_result.hierarchical_context_text:
    await self._inject_hierarchical_context_to_prompt(
        agent,
        context_result.hierarchical_context_text,
    )

# 设置对话历史（使用上下文结果中的历史消息）
if context_result.recent_messages:
    agent.history_messages = context_result.recent_messages
```

**交付物**:
- [ ] _inject_recall_tools 方法
- [ ] _inject_hierarchical_context_to_prompt 方法
- [ ] 在 _inner_chat 中集成调用

**验收标准**:
- 工具可正常注入到 Agent
- 分层上下文可正常注入到系统提示
- Agent 可调用回溯工具

---

### T2.4 runtime.py 初始化改造

**优先级**: P0  
**依赖**: Phase 1 完成

**任务描述**:
在 V2AgentRuntime 中初始化 UnifiedContextMiddleware

**实现步骤**:

1. 在 `runtime.py` 中导入：
```python
from derisk.context.unified_context_middleware import UnifiedContextMiddleware
from derisk.agent.shared.hierarchical_context import HierarchicalContextConfig
```

2. 在 `V2AgentRuntime.__init__` 中添加初始化：
```python
def __init__(
    self,
    config: RuntimeConfig = None,
    gpts_memory: Any = None,
    adapter: V2Adapter = None,
    progress_broadcaster: ProgressBroadcaster = None,
    agent_file_system: Optional[Any] = None,  # 新增参数
):
    self.config = config or RuntimeConfig()
    self.gpts_memory = gpts_memory
    self.adapter = adapter or V2Adapter()
    self.progress_broadcaster = progress_broadcaster
    self.file_system = agent_file_system
    
    # 新增：统一上下文中间件
    self.context_middleware = None
    if gpts_memory:
        self.context_middleware = UnifiedContextMiddleware(
            gpts_memory=gpts_memory,
            agent_file_system=agent_file_system,
            hc_config=HierarchicalContextConfig(),
        )
    
    # ... 原有代码 ...
```

3. 在 `start()` 方法中初始化：
```python
async def start(self):
    """启动运行时"""
    self._state = RuntimeState.RUNNING
    
    if self.gpts_memory and hasattr(self.gpts_memory, "start"):
        await self.gpts_memory.start()
    
    # 新增：初始化上下文中间件
    if self.context_middleware:
        await self.context_middleware.initialize()
    
    self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    logger.info("[V2Runtime] 运行时已启动（已集成分层上下文）")
```

**交付物**:
- [ ] runtime.py 改造
- [ ] 导入语句添加
- [ ] 初始化代码添加

**验收标准**:
- V2AgentRuntime 可正常实例化
- context_middleware 属性存在
- start() 方法正确初始化中间件

---

### T2.5 runtime.py 执行流程改造

**优先级**: P0  
**依赖**: T2.4

**任务描述**:
在 _execute_stream 中集成上下文加载

**实现步骤**:

1. 改造 `_execute_stream` 方法：
```python
async def _execute_stream(
    self,
    agent: Any,
    message: str,
    context: SessionContext,
    **kwargs,
) -> AsyncIterator[V2StreamChunk]:
    """执行流式输出 - 已集成 HierarchicalContext"""
    
    from ..agent_base import AgentBase, AgentState
    
    # ========== 步骤1：加载分层上下文 ==========
    hc_context = None
    if self.context_middleware:
        try:
            hc_context = await self.context_middleware.load_context(
                conv_id=context.conv_id,
                task_description=message,
                include_worklog=True,
                token_budget=12000,
            )
            
            logger.info(
                f"[V2Runtime] 已加载分层上下文: "
                f"chapters={hc_context.stats.get('chapter_count', 0)}, "
                f"context_length={len(hc_context.hierarchical_context_text)}"
            )
        except Exception as e:
            logger.error(f"[V2Runtime] 加载上下文失败: {e}", exc_info=True)
    
    # ========== 步骤2：创建 Agent Context ==========
    agent_context = self.adapter.context_bridge.create_v2_context(
        conv_id=context.conv_id,
        session_id=context.session_id,
        user_id=context.user_id,
    )
    
    # 注入分层上下文
    if hc_context:
        agent_context.metadata["hierarchical_context"] = hc_context.hierarchical_context_text
        agent_context.metadata["chapter_index"] = hc_context.chapter_index
        agent_context.metadata["hc_integration"] = hc_context.hc_integration
    
    # ========== 步骤3：初始化 Agent ==========
    await agent.initialize(agent_context)
    
    # 注入回溯工具
    if hc_context and hc_context.recall_tools:
        await self._inject_tools_to_agent(agent, hc_context.recall_tools)
    
    # ========== 步骤4：构建带历史的消息 ==========
    message_with_history = message
    if hc_context and hc_context.hierarchical_context_text:
        message_with_history = self._build_message_with_context(
            message,
            hc_context.hierarchical_context_text,
        )
    
    # ========== 步骤5：执行 Agent ==========
    # ... 原有执行逻辑 ...
```

2. 实现辅助方法：
```python
def _build_message_with_context(
    self,
    message: str,
    hierarchical_context: str,
) -> str:
    """构建带分层上下文的消息"""
    if not hierarchical_context:
        return message
    
    return f"""[历史任务记录]

{hierarchical_context}

---

[当前任务]
{message}"""

async def _inject_tools_to_agent(
    self,
    agent: Any,
    tools: List[Any],
) -> None:
    """注入工具到 Agent"""
    if not tools:
        return
    
    if hasattr(agent, 'tools') and hasattr(agent.tools, 'register'):
        for tool in tools:
            try:
                agent.tools.register(tool)
                logger.debug(f"[V2Runtime] 注入工具: {tool.name}")
            except Exception as e:
                logger.warning(f"[V2Runtime] 注入工具失败 {tool.name}: {e}")
```

**交付物**:
- [ ] _execute_stream 方法改造
- [ ] _build_message_with_context 方法
- [ ] _inject_tools_to_agent 方法

**验收标准**:
- 上下文可正常加载
- 消息可正确构建
- 工具可正常注入

---

### T2.6 runtime.py 步骤记录

**优先级**: P0  
**依赖**: T2.5

**任务描述**:
在执行过程中记录步骤到 HierarchicalContext

**实现步骤**:

1. 在 _execute_stream 中添加步骤记录：
```python
async def _execute_stream(
    self,
    agent: Any,
    message: str,
    context: SessionContext,
    **kwargs,
) -> AsyncIterator[V2StreamChunk]:
    # ... 前面的代码 ...
    
    # 执行
    if isinstance(agent, AgentBase):
        if self.progress_broadcaster and hasattr(agent, '_progress_broadcaster'):
            agent._progress_broadcaster = self.progress_broadcaster
        
        try:
            async for chunk in agent.run(message_with_history, stream=True, **kwargs):
                # 新增：记录步骤到 HierarchicalContext
                if hasattr(chunk, 'action_out') and self.context_middleware:
                    await self.context_middleware.record_step(
                        conv_id=context.conv_id,
                        action_out=chunk.action_out,
                    )
                
                # 转换为 V2StreamChunk
                v2_chunk = self._convert_to_v2_chunk(chunk, context)
                yield v2_chunk
                
        except Exception as e:
            logger.error(f"[V2Runtime] Agent 执行错误: {e}", exc_info=True)
            yield V2StreamChunk(type="error", content=str(e))
    
    else:
        # 兼容旧版 Agent
        async for chunk in self._execute_legacy_agent(agent, message_with_history, context):
            yield chunk
```

2. 在对话结束时清理：
```python
async def close_session(self, session_id: str):
    """关闭会话"""
    if session_id in self._sessions:
        context = self._sessions.pop(session_id)
        context.state = RuntimeState.TERMINATED
        
        # ... 原有清理逻辑 ...
        
        # 新增：清理上下文中间件
        if self.context_middleware:
            await self.context_middleware.cleanup_context(session_id)
        
        logger.info(f"[V2Runtime] 关闭会话: {session_id[:8]}")
```

**交付物**:
- [ ] 步骤记录逻辑添加
- [ ] 上下文清理逻辑添加
- [ ] 日志记录添加

**验收标准**:
- 步骤可正常记录
- 上下文可正常清理
- 无内存泄漏

---

## 四、Phase 3: 测试验证（5个任务）

### T3.1 WorkLog 转换单元测试

**优先级**: P0  
**依赖**: Phase 1 完成

**实现步骤**:

创建测试文件 `tests/test_unified_context/test_worklog_conversion.py`

测试用例清单：
- test_group_worklog_by_phase_exploration
- test_group_worklog_by_phase_development
- test_group_worklog_by_phase_debugging
- test_group_worklog_by_phase_refinement
- test_group_worklog_by_phase_delivery
- test_group_worklog_with_manual_phase
- test_determine_section_priority_critical
- test_determine_section_priority_high
- test_determine_section_priority_medium
- test_determine_section_priority_low
- test_work_entry_to_section_basic
- test_work_entry_to_section_with_long_content
- test_work_entry_to_section_with_failure
- test_archive_long_content
- test_generate_chapter_title

**验收标准**:
- 测试覆盖率 > 90%
- 所有测试用例通过
- 边界情况覆盖完整

---

### T3.2 中间件单元测试

**优先级**: P0  
**依赖**: Phase 1 完成

**实现步骤**:

创建测试文件 `tests/test_unified_context/test_middleware.py`

测试用例清单：
- test_middleware_initialization
- test_load_context_basic
- test_load_context_with_cache
- test_load_context_force_reload
- test_infer_task_description
- test_load_recent_messages
- test_record_step
- test_save_checkpoint
- test_restore_checkpoint
- test_cleanup_context
- test_clear_all_cache

**验收标准**:
- 测试覆盖率 > 85%
- 所有测试用例通过
- 异常情况处理正确

---

### T3.3 agent_chat.py 集成测试

**优先级**: P0  
**依赖**: Phase 2 完成

**实现步骤**:

创建测试文件 `tests/test_unified_context/test_agent_chat_integration.py`

测试用例清单：
- test_agent_chat_initialization
- test_inner_chat_context_loading
- test_inject_recall_tools_to_conv_agent
- test_inject_recall_tools_to_v2_agent
- test_inject_hierarchical_context_to_prompt
- test_full_conversation_flow_with_context

**验收标准**:
- 集成测试通过
- Agent 可正常使用上下文
- 回溯工具可正常调用

---

### T3.4 runtime.py 集成测试

**优先级**: P0  
**依赖**: Phase 2 完成

**实现步骤**:

创建测试文件 `tests/test_unified_context/test_runtime_integration.py`

测试用例清单：
- test_runtime_initialization
- test_execute_stream_with_context
- test_execute_stream_without_gpts_memory
- test_build_message_with_context
- test_inject_tools_to_agent
- test_record_step_during_execution
- test_cleanup_on_session_close

**验收标准**:
- 集成测试通过
- 多轮对话上下文保持
- 错误处理正确

---

### T3.5 E2E 完整流程测试

**优先级**: P0  
**依赖**: Phase 3 所有任务完成

**实现步骤**:

创建测试文件 `tests/test_unified_context/test_e2e.py`

测试场景：
- 完整对话流程（10轮以上）
- 多阶段任务执行
- 历史上下文验证
- 回溯工具调用验证
- 性能测试（1000条 WorkLog）

**验收标准**:
- E2E 测试通过
- 第100轮对话包含前99轮关键信息
- 性能指标达标（延迟 < 500ms）

---

## 五、Phase 4: 配置与灰度（4个任务）

### T4.1 配置加载器实现

**优先级**: P1  
**依赖**: Phase 3 完成

**任务描述**:
实现配置加载器，支持从 YAML 文件加载配置

**实现步骤**:

1. 创建文件 `derisk/context/config_loader.py`
2. 实现 HierarchicalContextConfigLoader 类
3. 支持配置热重载
4. 添加配置验证

**交付物**:
- [ ] config_loader.py
- [ ] 配置验证逻辑
- [ ] 单元测试

---

### T4.2 灰度控制器实现

**优先级**: P1  
**依赖**: Phase 3 完成

**任务描述**:
实现灰度发布控制器

**实现步骤**:

1. 创建文件 `derisk/context/gray_release_controller.py`
2. 实现 GrayReleaseController 类
3. 支持多维度灰度（用户/应用/会话）
4. 支持流量百分比灰度

**交付物**:
- [ ] gray_release_controller.py
- [ ] 单元测试
- [ ] 灰度配置示例

---

### T4.3 监控模块实现

**优先级**: P1  
**依赖**: Phase 3 完成

**任务描述**:
实现监控指标收集和上报

**实现步骤**:

1. 创建文件 `derisk/context/monitor.py`
2. 定义监控指标（Counter, Histogram, Gauge）
3. 在中间件中集成监控
4. 实现告警规则

**交付物**:
- [ ] monitor.py
- [ ] 监控指标定义
- [ ] 告警规则配置

---

### T4.4 性能优化

**优先级**: P1  
**依赖**: T4.1, T4.2, T4.3

**任务描述**:
性能优化和瓶颈分析

**优化方向**:
- 异步加载优化
- 缓存策略优化
- 文件 I/O 优化
- 内存使用优化

**验收标准**:
- 历史加载延迟 < 500ms (P95)
- 内存使用增量 < 100MB/1000会话

---

## 六、Phase 5: 文档与发布（3个任务）

### T5.1 技术文档编写

**优先级**: P1  
**依赖**: Phase 4 完成

**文档清单**:
- 架构设计文档
- API 参考文档
- 集成指南
- 配置说明
- 故障排查指南

**交付物**:
- [ ] docs/development/hierarchical-context-refactor/02-api-reference.md
- [ ] docs/development/hierarchical-context-refactor/03-integration-guide.md
- [ ] docs/development/hierarchical-context-refactor/04-troubleshooting.md

---

### T5.2 代码审查

**优先级**: P0  
**依赖**: Phase 5 所有任务完成

**审查内容**:
- 代码质量检查
- 安全审查
- 性能审查
- 测试覆盖率检查

**验收标准**:
- 代码审查问题数 = 0 critical
- 测试覆盖率 > 80%
- 无安全漏洞

---

### T5.3 发布准备

**优先级**: P0  
**依赖**: T5.2

**准备工作**:
- 发布说明编写
- 部署脚本准备
- 回滚方案确认
- 监控大盘搭建

**交付物**:
- [ ] 发布说明
- [ ] 部署文档
- [ ] 回滚方案
- [ ] 监控大盘

---

## 七、任务执行指南

### 7.1 任务状态跟踪

使用 TodoWrite 工具跟踪每个任务的进度：
- pending: 待开始
- in_progress: 进行中
- completed: 已完成
- cancelled: 已取消

### 7.2 任务优先级说明

- P0: 必须完成，阻塞后续任务
- P1: 重要任务，建议完成
- P2: 可选任务，时间允许时完成

### 7.3 开发流程

1. 阅读 Task 描述和实现步骤
2. 创建对应文件
3. 按步骤实现代码
4. 编写单元测试
5. 运行测试确保通过
6. 更新任务状态
7. 进行下一个任务

### 7.4 验收清单

每个任务完成后，需确认：
- [ ] 代码实现完成
- [ ] 单元测试编写并通过
- [ ] 代码风格符合规范
- [ ] 日志记录添加
- [ ] 文档更新（如需要）

---

## 八、风险管理

### 8.1 技术风险

| 风险 | 应对措施 |
|------|---------|
| 性能下降 | 缓存机制、异步加载、性能测试 |
| 兼容性问题 | 向下兼容设计、灰度发布 |
| 内存泄漏 | 缓存清理、监控告警 |

### 8.2 依赖风险

| 依赖项 | 风险 | 应对 |
|--------|------|------|
| HierarchicalContext 系统 | 已有代码可能不稳定 | 充分测试 |
| GptsMemory 接口变更 | 接口不兼容 | 适配层设计 |
| 文件系统依赖 | 存储失败 | 降级处理 |

---

## 九、附录

### 9.1 相关文档

- [HierarchicalContext 系统文档](/derisk/agent/shared/hierarchical_context/README.md)
- [GptsMemory 文档](/derisk/agent/core/memory/gpts/README.md)
- [AgentChat 文档](/derisk_serve/agent/agents/chat/README.md)

### 9.2 关键接口

**UnifiedContextMiddleware**:
```python
async def load_context(conv_id, ...) -> ContextLoadResult
async def record_step(conv_id, action_out, ...)
async def save_checkpoint(conv_id, ...)
async def restore_checkpoint(conv_id, checkpoint_path)
async def cleanup_context(conv_id)
```

**ContextLoadResult**:
```python
conv_id: str
task_description: str
chapter_index: ChapterIndexer
hierarchical_context_text: str
recent_messages: List[GptsMessage]
recall_tools: List[Any]
stats: Dict[str, Any]
```

### 9.3 配置示例

```yaml
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
  strategy: "llm_summary"
  trigger:
    token_threshold: 40000

worklog_conversion:
  enabled: true
  
gray_release:
  enabled: false
  gray_percentage: 0
```