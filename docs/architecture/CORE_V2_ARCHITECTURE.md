# Derisk Core V2 Agent 架构文档

> 最后更新: 2026-03-03
> 状态: 活跃开发中

## 一、架构概览

### 1.1 设计理念

Core V2 Agent 基于以下设计原则：

```python
"""
设计原则:
1. 配置驱动 - 通过AgentInfo配置,而非复杂的继承
2. 权限集成 - 内置Permission系统
3. 流式输出 - 支持流式响应
4. 状态管理 - 明确的状态机
5. 异步优先 - 全异步设计
"""
```

### 1.2 核心架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Core V2 Agent 架构                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │                    Runtime Layer (运行时层)                      │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │V2AgentDispa- │───>│V2AgentRuntime│───>│  V2Adapter   │      │    │
│   │  │tcher (调度)  │    │ (会话管理)    │    │ (消息桥梁)   │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                      Agent Layer (代理层)                        │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │ AgentBase    │───>│ProductionAge│───>│EnhancedAgent │      │    │
│   │  │ (抽象基类)    │    │nt (生产级)   │    │ (增强实现)   │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                     Memory Layer (记忆层) [新增]                  │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │UnifiedMemory │───>│ProjectMemory │───>│ GptsMemory   │      │    │
│   │  │ (统一接口)    │    │ (CLAUDE.md)   │    │Adapter (V1) │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                   Context Layer (上下文层) [新增]                 │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │ContextIso-   │───>│SubagentCtx   │───>│ ContextWindow│      │    │
│   │  │lation (隔离) │    │Config (配置)  │    │ (窗口定义)   │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                    Strategy Layer (策略层)                       │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │SceneStrategy │───>│ReasoningStra-│───>│  HookSystem  │      │    │
│   │  │ (场景策略)    │    │tegy (推理)    │    │  (钩子)      │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 二、分层模块定义

### 2.1 目录结构

```
packages/derisk-core/src/derisk/agent/core_v2/
├── agent_base.py                # 核心基类定义 (787行)
├── agent_info.py                # Agent 配置信息
├── agent_binding.py             # 资源绑定机制
├── agent_harness.py             # Agent 运行时框架
├── enhanced_agent.py            # 生产级 Agent 实现 (1057行)
├── production_agent.py          # 生产 Agent 构建器
├── goal.py                      # 目标管理系统 (677行)
├── scene_strategy.py            # 场景策略系统 (603行)
├── reasoning_strategy.py        # 推理策略系统 (611行)
├── subagent_manager.py          # 子代理管理器 (834行)
├── memory_compaction.py         # 记忆压缩
├── improved_compaction.py       # 改进的压缩算法
├── llm_adapter.py               # LLM 适配器
├── vis_adapter.py               # VIS 协议适配
│
├── integration/                 # 集成层
│   ├── adapter.py               # V1/V2 适配器
│   ├── runtime.py               # V2 运行时 (961行)
│   ├── dispatcher.py            # 任务分发器
│   └── agent_impl.py            # Agent 实现
│
├── project_memory/              # [新增] 项目记忆系统
│   ├── __init__.py              # 接口定义 (225行)
│   └── manager.py               # 实现 (749行)
│
├── context_isolation/           # [新增] 上下文隔离系统
│   ├── __init__.py              # 接口和数据模型 (356行)
│   └── manager.py               # 实现 (618行)
│
├── unified_memory/              # [新增] 统一记忆接口
│   ├── base.py                  # 抽象接口 (268行)
│   ├── gpts_adapter.py          # GptsMemory 适配器
│   └── message_converter.py     # 消息转换
│
├── filesystem/                  # [新增] 文件系统集成
│   ├── claude_compatible.py     # CLAUDE.md 兼容层
│   ├── auto_memory_hook.py      # 自动记忆钩子
│   └── integration.py           # AgentFileSystem 集成
│
├── tools_v2/                    # V2 工具系统
├── multi_agent/                 # 多 Agent 协作
└── visualization/               # 可视化组件
```

### 2.2 Runtime 层 (运行时层)

#### 2.2.1 V2AgentRuntime (`integration/runtime.py`)

**核心职责**:
- Session 生命周期管理
- Agent 执行调度
- 消息流处理和推送
- 与 GptsMemory 集成
- 分层上下文管理

```python
class V2AgentRuntime:
    def __init__(
        self,
        config: RuntimeConfig = None,
        gpts_memory: Any = None,           # V1 记忆系统
        adapter: V2Adapter = None,
        progress_broadcaster: ProgressBroadcaster = None,
        enable_hierarchical_context: bool = True,
        llm_client: Any = None,
        conv_storage: Any = None,          # StorageConversation
        message_storage: Any = None,       # ChatHistoryMessageEntity
        project_memory: Optional[ProjectMemoryManager] = None,  # [新增]
    ):
        # ...
```

**Session 管理**:

```python
@dataclass
class SessionContext:
    session_id: str
    conv_id: str
    user_id: Optional[str] = None
    agent_name: str = "primary"
    created_at: datetime = field(default_factory=datetime.now)
    state: RuntimeState = RuntimeState.IDLE
    message_count: int = 0

    # StorageConversation 用于消息持久化
    storage_conv: Optional[Any] = None
```

**执行入口**:

```python
async def execute(
    self,
    session_id: str,
    message: str,
    stream: bool = True,
    enable_context_loading: bool = True,
    **kwargs,
) -> AsyncIterator[V2StreamChunk]:
    """执行 Agent"""
    context = await self.get_session(session_id)
    agent = await self._get_or_create_agent(context, kwargs)

    # 加载分层上下文
    if enable_context_loading and self._context_middleware:
        context_result = await self._context_middleware.load_context(
            conv_id=conv_id,
            task_description=message[:200],
        )

    # 流式执行
    if stream:
        async for chunk in self._execute_stream(agent, message, context):
            yield chunk
            await self._push_stream_chunk(conv_id, chunk)
```

### 2.3 Agent 层 (代理层)

#### 2.3.1 AgentBase 核心设计 (`agent_base.py`)

**三阶段执行模型**:

```python
@abstractmethod
async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
    """思考阶段 - 生成思考过程"""
    pass

@abstractmethod
async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
    """决策阶段 - 决定下一步动作

    Returns:
        Dict: 决策结果,包含:
            - type: "response" | "tool_call" | "subagent" | "terminate"
            - content: 响应内容(如果type=response)
            - tool_name: 工具名称(如果type=tool_call)
            - tool_args: 工具参数(如果type=tool_call)
            - subagent: 子Agent名称(如果type=subagent)
            - task: 任务内容(如果type=subagent)
    """
    pass

@abstractmethod
async def act(self, tool_name: str, tool_args: Dict[str, Any], **kwargs) -> Any:
    """执行动作阶段"""
    pass
```

**状态机**:

```python
class AgentState(str, Enum):
    IDLE = "idle"                  # 空闲状态
    THINKING = "thinking"          # 思考中
    ACTING = "acting"              # 执行动作中
    WAITING_INPUT = "waiting_input"  # 等待用户输入
    ERROR = "error"                # 错误状态
    TERMINATED = "terminated"      # 已终止
```

**初始化参数** (`agent_base.py:112-170`):

```python
def __init__(
    self,
    info: AgentInfo,                              # Agent 配置信息
    memory: Optional[UnifiedMemoryInterface] = None,  # 统一记忆接口
    use_persistent_memory: bool = False,          # 是否持久化
    gpts_memory: Optional["GptsMemory"] = None,   # V1 Memory 适配
    conv_id: Optional[str] = None,
    project_memory: Optional["ProjectMemoryManager"] = None,  # [新增]
    context_isolation_config: Optional["SubagentContextConfig"] = None,  # [新增]
):
```

#### 2.3.2 AgentInfo 配置模型 (`agent_info.py`)

```python
class AgentInfo(BaseModel):
    name: str                       # Agent 名称
    description: str                # 描述
    mode: AgentMode                 # 运行模式 (AUTO/INTERACTIVE/SUBAGENT)
    system_prompt: Optional[str]    # 系统提示词
    permission: PermissionRuleset   # 权限规则
    max_steps: int = 20             # 最大步数
    tools: List[str] = []           # 可用工具
    subagents: List[str] = []       # 子 Agent 列表
```

#### 2.3.3 主执行循环 (`agent_base.py:639-729`)

```python
async def run(self, message: str, stream: bool = True) -> AsyncIterator[str]:
    """主执行循环"""
    self.add_message("user", message)
    await self.save_memory(content=f"User: {message}", ...)  # 持久化

    while self._current_step < self.info.max_steps:
        try:
            # 1. THINKING 阶段
            self.set_state(AgentState.THINKING)
            if stream:
                async for chunk in self.think(message):
                    yield f"[THINKING] {chunk}"

            # 2. DECIDING 阶段
            decision = await self.decide(message)
            decision_type = decision.get("type")

            # 3. 处理决策
            if decision_type == "response":
                yield content
                break
            elif decision_type == "tool_call":
                result = await self.execute_tool(tool_name, tool_args)
                message = self._format_tool_result(tool_name, result)
            elif decision_type == "subagent":
                result = await self.delegate_to_subagent(subagent, task)
                message = result.to_llm_message()
            elif decision_type == "terminate":
                break

        except Exception as e:
            self.set_state(AgentState.ERROR)
            yield f"[ERROR] {str(e)}"
            break
```

### 2.4 Memory 层 (记忆层) [新增]

#### 2.4.1 统一记忆接口 (`unified_memory/base.py`)

```python
class MemoryType(str, Enum):
    WORKING = "working"      # 工作记忆
    EPISODIC = "episodic"    # 情景记忆
    SEMANTIC = "semantic"    # 语义记忆
    SHARED = "shared"        # 共享记忆
    PREFERENCE = "preference"  # 偏好记忆

class UnifiedMemoryInterface(ABC):
    @abstractmethod
    async def write(self, content: str, memory_type: MemoryType, ...) -> str:
        """写入记忆"""

    @abstractmethod
    async def read(self, query: str, options: SearchOptions) -> List[MemoryItem]:
        """读取记忆"""

    @abstractmethod
    async def search_similar(self, query: str, top_k: int) -> List[MemoryItem]:
        """向量相似度搜索"""

    @abstractmethod
    async def consolidate(self, source: MemoryType, target: MemoryType):
        """记忆整合"""
```

#### 2.4.2 项目记忆系统 (`project_memory/`)

**设计目标**: 实现类似 Claude Code 的 CLAUDE.md 风格的多层级记忆管理。

**优先级定义**:

```python
class MemoryPriority(IntEnum):
    AUTO = 0       # 自动生成的记忆 (最低优先级)
    USER = 25      # 用户级记忆 (~/.derisk/)
    PROJECT = 50   # 项目级记忆 (./.derisk/)
    MANAGED = 75   # 托管记忆
    SYSTEM = 100   # 系统记忆 (最高优先级)
```

**目录结构**:

```
.derisk/
├── MEMORY.md              # 项目级主记忆
├── RULES.md               # 规则定义
├── AGENTS/
│   ├── DEFAULT.md         # 默认 Agent 配置
│   └── custom_agent.md    # 特定 Agent 配置
├── KNOWLEDGE/
│   └── domain_kb.md       # 领域知识库
└── MEMORY.LOCAL/          # 本地记忆 (不提交 Git)
    ├── auto-memory.md     # 自动生成的记忆
    └── sessions/          # 会话记忆
```

**@import 指令支持**:

```markdown
# MEMORY.md
@import @user/preferences.md    # 导入用户级记忆
@import @knowledge/python.md    # 导入知识库
@import AGENTS/DEFAULT.md       # 导入 Agent 配置
```

**ProjectMemoryManager 核心方法**:

```python
class ProjectMemoryManager:
    async def build_context(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """构建完整上下文，按优先级合并所有层"""

    async def write_auto_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """写入自动记忆"""
```

#### 2.4.3 GptsMemory 适配器 (`unified_memory/gpts_adapter.py`)

```python
class GptsMemoryAdapter(UnifiedMemoryInterface):
    """适配 V1 的 GptsMemory 到统一接口"""

    def __init__(self, gpts_memory: GptsMemory, conv_id: str):
        self._gpts_memory = gpts_memory
        self._conv_id = conv_id

    async def write(self, content: str, memory_type: MemoryType, ...):
        # 转换为 GptsMessage 并存储
        msg = GptsMessage(
            conv_id=self._conv_id,
            content=content,
            ...
        )
        await self._gpts_memory.append_message(self._conv_id, msg)
```

### 2.5 Context 层 (上下文层) [新增]

#### 2.5.1 隔离模式定义 (`context_isolation/__init__.py`)

```python
class ContextIsolationMode(str, Enum):
    """上下文隔离模式

    - ISOLATED: 完全新上下文，不继承父级
    - SHARED: 继承父级上下文，实时同步更新
    - FORK: 复制父级上下文快照，之后独立
    """
    ISOLATED = "isolated"
    SHARED = "shared"
    FORK = "fork"
```

#### 2.5.2 核心数据模型

```python
class ContextWindow:
    """上下文窗口定义"""
    messages: List[Dict[str, Any]]       # 消息历史
    total_tokens: int                    # 当前 token 数
    max_tokens: int = 128000             # 最大 token 限制
    available_tools: Set[str]            # 可用工具
    memory_types: Set[str]               # 可访问的记忆类型
    resource_bindings: Dict[str, str]    # 资源绑定

class SubagentContextConfig:
    """子 Agent 上下文配置"""
    isolation_mode: ContextIsolationMode
    memory_scope: MemoryScope            # 记忆范围配置
    resource_bindings: List[ResourceBinding]
    allowed_tools: Optional[List[str]]   # 允许的工具列表
    denied_tools: List[str]              # 拒绝的工具列表
    max_context_tokens: int = 32000
    timeout_seconds: int = 300
```

#### 2.5.3 ContextIsolationManager

```python
class ContextIsolationManager:
    async def create_isolated_context(
        self,
        parent_context: Optional[ContextWindow],
        config: SubagentContextConfig,
    ) -> IsolatedContext:
        """根据隔离模式创建上下文"""

    async def merge_context_back(
        self,
        isolated_context: IsolatedContext,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将子 Agent 结果合并回父上下文"""
```

**三种模式实现**:

```python
def _create_isolated_window(self, config):
    """ISOLATED: 空上下文"""
    return ContextWindow(messages=[], total_tokens=0, ...)

def _create_shared_window(self, parent, config):
    """SHARED: 直接返回父上下文引用"""
    return parent  # 共享引用，实时同步

def _create_forked_window(self, parent, config):
    """FORK: 深拷贝父上下文"""
    forked = parent.clone()
    # 应用记忆范围过滤和工具过滤
    if not config.memory_scope.inherit_parent:
        forked.messages = []
    return forked
```

### 2.6 Strategy 层 (策略层)

#### 2.6.1 Scene Strategy 钩子系统 (`scene_strategy.py`)

**阶段定义**:

```python
class AgentPhase(str, Enum):
    INIT = "init"
    SYSTEM_PROMPT_BUILD = "system_prompt_build"
    BEFORE_THINK = "before_think"
    THINK = "think"
    AFTER_THINK = "after_think"
    BEFORE_ACT = "before_act"
    ACT = "act"
    AFTER_ACT = "after_act"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ERROR = "error"
    COMPLETE = "complete"
```

**钩子基类**:

```python
class SceneHook(ABC):
    name: str = "base_hook"
    priority: HookPriority = HookPriority.NORMAL
    phases: List[AgentPhase] = []

    async def on_before_think(self, ctx: HookContext) -> HookResult:
        return HookResult(proceed=True)

    async def on_after_tool(self, ctx: HookContext) -> HookResult:
        return HookResult(proceed=True)
```

#### 2.6.2 Reasoning Strategy (`reasoning_strategy.py`)

**支持的策略**:

```python
class StrategyType(str, Enum):
    REACT = "react"                        # ReAct (推理+行动)
    PLAN_AND_EXECUTE = "plan_and_execute"  # 计划-执行
    TREE_OF_THOUGHT = "tree_of_thought"    # 思维树
    CHAIN_OF_THOUGHT = "chain_of_thought"  # 思维链
    REFLECTION = "reflection"              # 反思
```

---

## 三、Subagent 系统

### 3.1 SubagentManager (`subagent_manager.py`)

```python
class SubagentManager:
    async def delegate(
        self,
        subagent_name: str,
        task: str,
        parent_session_id: str,
        context: Optional[Dict] = None,
        timeout: Optional[int] = None,
        sync: bool = True,
    ) -> SubagentResult:
        """委派任务给子 Agent"""

    async def delegate_with_isolation(
        self,
        subagent_name: str,
        task: str,
        parent_session_id: str,
        isolation_mode: ContextIsolationMode = None,
        context_config: SubagentContextConfig = None,
    ) -> SubagentResult:
        """使用上下文隔离委派任务"""
```

### 3.2 带上下文隔离的委派流程

```python
async def delegate_with_isolation(self, ...):
    # 1. 创建隔离上下文
    isolated_context = await self._context_isolation_manager.create_isolated_context(
        parent_context=parent_context_window,
        config=context_config or SubagentContextConfig(
            isolation_mode=isolation_mode or ContextIsolationMode.FORK,
        ),
    )

    # 2. 委派任务
    result = await self.delegate(...)

    # 3. 合并结果回父上下文
    if context_config.memory_scope.propagate_up:
        merge_data = await self._context_isolation_manager.merge_context_back(
            isolated_context,
            {"output": result.output, "success": result.success},
        )

    # 4. 清理隔离上下文
    await self._context_isolation_manager.cleanup_context(isolated_context.context_id)

    return result
```

---

## 四、执行流程详解

### 4.1 数据流图

```
用户输入
    ↓
[V2AgentRuntime.execute]
    ↓
[创建/获取 Session] ───→ StorageConversation (ChatHistoryMessageEntity)
    ↓
[加载分层上下文] ──────→ UnifiedContextMiddleware
    ↓
[创建/获取 Agent] ─────→ Agent Factory
    ↓
[Agent.run] ───────────→ Think/Decide/Act 循环
    ↓
    ├─→ [think] → LLM 调用 → 思考过程流式输出
    ├─→ [decide] → 决策 (response/tool/subagent/terminate)
    └─→ [act] → 工具执行/子 Agent 委派
              ↓
    ├─→ [Tool Execution] ─→ ToolRegistry.execute()
    ├─→ [Subagent Delegation] ─→ SubagentManager.delegate()
    │              ↓
    │         [ContextIsolation.create_isolated_context]
    │              ↓
    │         [子 Agent 执行]
    │              ↓
    │         [merge_context_back] (如果 propagate_up)
    │              ↓
    └─→ [Memory] ─→ UnifiedMemory.write() ─→ GptsMemory Adapter
    ↓
[消息持久化] ──────────→ GptsMemory (gpts_messages)
    ↓                    → StorageConversation (chat_history_message)
[VIS 输出转换] ────────→ CoreV2VisWindow3Converter
    ↓
[流式输出到前端]
```

### 4.2 与 V1 的关键差异

| 方面 | Core V1 | Core V2 |
|------|---------|---------|
| **执行模型** | generate_reply 单循环 | Think/Decide/Act 三阶段 |
| **消息模型** | send/receive 显式消息传递 | run() 主循环隐式处理 |
| **状态管理** | 隐式状态 | 明确状态机 (AgentState) |
| **子Agent** | 通过消息路由 | SubagentManager 显式委派 |
| **记忆系统** | GptsMemory (单一) | UnifiedMemory + ProjectMemory (分层) |
| **上下文隔离** | 无 | ISOLATED/SHARED/FORK 三种模式 |
| **扩展机制** | 继承重写 | SceneStrategy 钩子系统 |
| **推理策略** | 硬编码 | 可插拔 ReasoningStrategy |

---

## 五、新增模块详解

### 5.1 Filesystem 集成 (`filesystem/`)

#### CLAUDE.md 兼容层

```python
class ClaudeMdParser:
    """CLAUDE.md 文件解析器"""

    @staticmethod
    def parse(content: str) -> ClaudeMdDocument:
        """解析 CLAUDE.md 内容"""
        # 1. 提取 YAML Front Matter
        # 2. 提取 @import 导入
        # 3. 提取章节结构

class ClaudeCompatibleAdapter:
    """Claude Code 兼容适配器"""

    CLAUDE_MD_FILES = ["CLAUDE.md", "claude.md", ".claude.md"]

    async def convert_to_derisk(self) -> bool:
        """将 CLAUDE.md 转换为 Derisk 格式"""
```

#### 自动记忆钩子

```python
class AutoMemoryHook(SceneHook):
    """自动记忆写入钩子"""
    name = "auto_memory"
    phases = [AgentPhase.AFTER_ACT, AgentPhase.COMPLETE]

class ImportantDecisionHook(SceneHook):
    """重要决策记录钩子"""
    name = "important_decision"
    DECISION_KEYWORDS = ["决定", "选择", "采用", "decided", "chose"]
```

---

## 六、关键文件索引

| 文件 | 路径 | 核心职责 |
|------|------|---------|
| AgentBase | `core_v2/agent_base.py` | 抽象基类，定义三阶段模型 |
| EnhancedAgent | `core_v2/enhanced_agent.py` | 生产级实现 |
| V2AgentRuntime | `core_v2/integration/runtime.py` | 运行时会话管理 |
| SubagentManager | `core_v2/subagent_manager.py` | 子代理委派管理 |
| ProjectMemoryManager | `core_v2/project_memory/manager.py` | 项目记忆管理 |
| ContextIsolationManager | `core_v2/context_isolation/manager.py` | 上下文隔离管理 |
| UnifiedMemoryInterface | `core_v2/unified_memory/base.py` | 统一记忆接口 |
| SceneStrategy | `core_v2/scene_strategy.py` | 场景策略钩子 |
| ReasoningStrategy | `core_v2/reasoning_strategy.py` | 推理策略 |
| V2Adapter | `core_v2/integration/adapter.py` | V1/V2 消息桥梁 |

---

## 七、演进路线

### 7.1 已完成

- [x] Think/Decide/Act 三阶段执行模型
- [x] 统一记忆接口 (UnifiedMemory)
- [x] 项目记忆系统 (ProjectMemory)
- [x] 上下文隔离系统 (ContextIsolation)
- [x] 子代理管理器 (SubagentManager)
- [x] 场景策略钩子系统 (SceneStrategy)
- [x] 推理策略系统 (ReasoningStrategy)
- [x] CLAUDE.md 兼容层
- [x] 自动记忆钩子

### 7.2 待优化

- [ ] 完善记忆压缩算法
- [ ] 增强多 Agent 协作能力
- [ ] 优化上下文加载性能
- [ ] 完善错误恢复机制