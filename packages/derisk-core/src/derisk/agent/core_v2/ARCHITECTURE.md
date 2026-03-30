# DERISK Core V2 架构文档

## 目录

1. [概述](#1-概述)
2. [目录结构](#2-目录结构)
3. [核心模块功能](#3-核心模块功能)
4. [架构层次](#4-架构层次)
5. [数据流](#5-数据流)
6. [关键设计模式](#6-关键设计模式)
7. [扩展开发指南](#7-扩展开发指南)
8. [使用示例](#8-使用示例)
9. [用户交互系统](#9-用户交互系统)
10. [Shared Infrastructure](#10-shared-infrastructure-共享基础设施)
11. [与 Core V1 对比](#11-与-core-v1-对比)
12. [MultiAgent 架构设计](#12-multiagent-架构设计)

---

## 1. 概述

DERISK Core V2 是在 Core V1 基础上重构的新型 Agent 框架，采用**配置驱动 + 钩子系统**的设计理念，提供更强的生产级能力：

### V2.2 新增特性 - MultiAgent协作

- **Multi-Agent协作** - 支持多Agent并行工作、任务拆分、层次执行
- **产品层关联** - 产品应用到Agent团队的配置映射
- **共享资源平面** - 统一的资源管理和共享机制
- **智能路由** - 基于能力和负载的任务分配策略

### 核心设计理念

```
┌──────────────────────────────────────────────────────────────────┐
│                    Configuration Driven Design                   │
│                                                                  │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│   │ AgentInfo   │───►│ SceneProfile │───►│ Execution   │        │
│   │ (配置)      │    │ (场景)       │    │ (执行)      │        │
│   └─────────────┘    └─────────────┘    └─────────────┘        │
│          │                  │                  │                │
│          ▼                  ▼                  ▼                │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                    Hook System (钩子系统)                │  │
│   │  before_thinking → after_thinking → before_action...    │  │
│   └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 主要改进

| 特性 | Core V1 | Core V2 |
|------|---------|---------|
| **执行引擎** | ExecutionEngine + Hooks | AgentHarness + Checkpoint |
| **记忆系统** | SimpleMemory + Memory层次 | MemoryCompaction + VectorMemory |
| **权限系统** | PermissionRuleset | PermissionManager + InteractiveChecker |
| **配置方式** | AgentInfo + Markdown | AgentConfig + YAML/JSON |
| **场景扩展** | 手动创建 | 场景预设 + SceneProfile |
| **模型监控** | 无 | ModelMonitor + TokenUsageTracker |
| **可观测性** | 基础日志 | ObservabilityManager |
| **沙箱** | SandboxManager | DockerSandbox + LocalSandbox |
| **推理策略** | ReasoningAction | ReasoningStrategyFactory |
| **长任务支持** | 有限 | 长任务执行器 + 检查点 |

---

## 2. 目录结构

```
packages/derisk-core/src/derisk/agent/core_v2/
├── __init__.py                 # 模块入口，导出所有公共API
├── agent_info.py               # Agent 配置模型
├── agent_base.py               # Agent 基类
├── agent_harness.py            # Agent 执行框架（核心）
├── production_agent.py         # 生产级 Agent 实现
│
├── permission.py               # 权限系统
├── goal.py                     # 目标管理系统
├── interaction.py              # 交互协议系统
│
├── model_provider.py           # 模型供应商抽象层
├── model_monitor.py            # 模型调用监控追踪
├── llm_adapter.py              # LLM 适配器
│
├── memory_compaction.py        # 记忆压缩机制
├── memory_vector.py            # 向量检索系统
│
├── sandbox_docker.py           # Docker沙箱执行
│
├── reasoning_strategy.py       # 推理策略系统
│
├── observability.py            # 可观测性系统
├── config_manager.py           # 配置管理系统
│
├── task_scene.py               # 任务场景定义
├── scene_registry.py           # 场景注册中心
├── scene_config_loader.py      # 场景配置加载
├── scene_strategy.py           # 场景策略框架
├── scene_strategies_builtin.py # 内置策略实现
│
├── mode_manager.py             # 模式切换管理器
├── context_processor.py        # 上下文处理器
├── context_validation.py       # 上下文验证器
│
├── execution_replay.py         # 执行回放系统
├── long_task_executor.py       # 长任务执行器
│
├── vis_push_manager.py         # VIS 推送管理器
├── vis_push_hooks.py           # VIS 推送钩子
│
├── resource_adapter.py         # 资源适配器
├── api_routes.py               # API 路由
├── main.py                     # 入口文件
│
├── context_lifecycle/          # 上下文生命周期
│   ├── __init__.py
│   └── orchestrator.py
│
├── tools_v2/                   # 工具系统 V2
│   ├── __init__.py
│   ├── tool_base.py            # 工具基类
│   ├── tool_registry.py        # 工具注册器
│   ├── builtin_tools.py        # 内置工具
│   ├── interaction_tools.py    # 交互工具
│   ├── network_tools.py        # 网络工具
│   ├── analysis_tools.py       # 分析工具
│   ├── mcp_tools.py            # MCP 工具适配
│   └── action_adapter.py       # Action 适配器
│
├── visualization/              # 可视化模块
│   ├── __init__.py
│   └── progress.py             # 进度广播
│
└── integration/                # 集成模块
    ├── __init__.py
    ├── adapter.py              # V1-V2 适配器
    └── runtime.py              # 运行时集成
```

---

## 3. 核心模块功能

### 3.1 AgentHarness 执行框架 (`agent_harness.py`)

**核心能力**:

```python
class AgentHarness:
    """
    Agent 执行框架
    
    特性：
    - Durable Execution: 持久化执行，重启后恢复
    - Checkpointing: 检查点机制，状态快照
    - Pause/Resume: 暂停和恢复
    - State Compression: 智能状态压缩
    - Circuit Breaker: 熔断机制
    - Task Queue: 异步任务队列
    """
    
    def __init__(
        self,
        max_steps: int = 100,
        checkpoint_interval: int = 10,
        state_store: Optional[StateStore] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    )
    
    async def execute(
        self,
        goal: str,
        context: ExecutionContext,
        on_step: Optional[Callable] = None,
    ) -> ExecutionResult:
        """执行任务"""
    
    async def pause(self) -> Checkpoint:
        """暂停并创建检查点"""
    
    async def resume(self, checkpoint_id: str) -> None:
        """从检查点恢复"""
```

**执行状态**:

```python
class ExecutionState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

**检查点机制**:

```python
class Checkpoint(BaseModel):
    checkpoint_id: str
    execution_id: str
    checkpoint_type: CheckpointType  # MANUAL / AUTOMATIC / MILESTONE
    timestamp: datetime
    state: Dict[str, Any]
    context: Dict[str, Any]
    step_index: int
    checksum: Optional[str]
```

**分层上下文**:

```python
class ExecutionContext:
    system_layer: Dict[str, Any]     # 系统级配置
    task_layer: Dict[str, Any]       # 任务相关数据
    tool_layer: Dict[str, Any]       # 工具执行结果
    memory_layer: Dict[str, Any]     # 记忆数据
    temporary_layer: Dict[str, Any]  # 临时数据
```

### 3.2 AgentBase 基类 (`agent_base.py`)

**核心接口**:

```python
class AgentBase(ABC):
    """Agent 基类"""
    
    @property
    @abstractmethod
    def name(self) -> str
    
    @property
    @abstractmethod
    def state(self) -> AgentState
    
    @abstractmethod
    async def initialize(self, config: AgentConfig) -> None
    
    @abstractmethod
    async def think(self, messages: List[LLMMessage]) -> AsyncIterator[str]
    
    @abstractmethod
    async def act(self, tool_calls: List[ToolCall]) -> List[ToolResult]
    
    @abstractmethod
    async def run(self, goal: str) -> AgentExecutionResult
```

**SimpleAgent 实现**:

```python
class SimpleAgent(AgentBase):
    """简化版 Agent 实现"""
    
    def __init__(
        self,
        name: str,
        llm_adapter: LLMAdapter,
        tools: List[ToolBase],
        hooks: Optional[List[SceneHook]] = None,
    )
    
    async def run(self, goal: str) -> AgentExecutionResult:
        """执行任务"""
```

### 3.3 权限系统 (`permission.py`)

**权限检查器**:

```python
class PermissionChecker(ABC):
    @abstractmethod
    async def check(self, request: PermissionRequest) -> PermissionResponse:
        """检查权限"""

class InteractivePermissionChecker(PermissionChecker):
    """交互式权限检查器 - 需要用户确认"""
    
    async def check(self, request: PermissionRequest) -> PermissionResponse:
        # 返回 ASK / ALLOW / DENY
```

**权限请求/响应**:

```python
@dataclass
class PermissionRequest:
    tool_name: str
    action: str
    parameters: Dict[str, Any]
    context: Dict[str, Any]

@dataclass
class PermissionResponse:
    action: PermissionAction  # ALLOW / DENY / ASK
    reason: Optional[str]
    conditions: Optional[Dict[str, Any]]
```

### 3.4 目标管理系统 (`goal.py`)

**目标定义**:

```python
class Goal(BaseModel):
    id: str
    name: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    priority: GoalPriority = GoalPriority.MEDIUM
    
    success_criteria: List[SuccessCriterion] = []
    sub_goals: List["Goal"] = []
    
    created_at: datetime
    deadline: Optional[datetime]
    completed_at: Optional[datetime]
```

**成功标准**:

```python
class SuccessCriterion(BaseModel):
    name: str
    criterion_type: CriterionType  # OUTPUT_CONTAINS / FILE_EXISTS / TEST_PASSES
    expected_value: Any
    weight: float = 1.0
```

**目标管理器**:

```python
class GoalManager:
    def create_goal(self, name: str, description: str, **kwargs) -> Goal
    def decompose_goal(self, goal_id: str, strategy: GoalDecompositionStrategy) -> List[Goal]
    def update_progress(self, goal_id: str, progress: float) -> None
    def check_completion(self, goal_id: str) -> Tuple[bool, str]
```

### 3.5 交互系统 (`interaction.py`)

**交互类型**:

```python
class InteractionType(str, Enum):
    CONFIRMATION = "confirmation"    # 确认请求
    QUESTION = "question"            # 问题询问
    CHOICE = "choice"                # 多选
    INPUT = "input"                  # 输入请求
    NOTIFICATION = "notification"    # 通知
```

**交互管理器**:

```python
class InteractionManager:
    async def request(
        self,
        interaction_type: InteractionType,
        message: str,
        options: Optional[List[InteractionOption]] = None,
        timeout: Optional[float] = None,
    ) -> InteractionResponse:
        """发送交互请求"""
```

**CLI/WebSocket 处理器**:

```python
class CLIInteractionHandler(InteractionHandler):
    """命令行交互处理器"""
    
    async def handle(self, request: InteractionRequest) -> InteractionResponse:
        # 在命令行显示请求，等待用户输入

class WebSocketInteractionHandler(InteractionHandler):
    """WebSocket 交互处理器"""
    
    async def handle(self, request: InteractionRequest) -> InteractionResponse:
        # 通过 WebSocket 发送请求，等待响应
```

### 3.6 模型供应商 (`model_provider.py`)

**抽象层**:

```python
class ModelProvider(ABC):
    @abstractmethod
    async def call(
        self,
        messages: List[ModelMessage],
        config: ModelConfig,
        options: Optional[CallOptions] = None,
    ) -> ModelResponse:
        """调用模型"""

class OpenAIProvider(ModelProvider):
    """OpenAI 实现"""
    
class AnthropicProvider(ModelProvider):
    """Anthropic 实现"""
```

**模型配置**:

```python
class ModelConfig(BaseModel):
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stream: bool = True
    stop: Optional[List[str]] = None
```

**模型注册中心**:

```python
class ModelRegistry:
    def register(self, provider_id: str, provider: ModelProvider) -> None
    def get(self, provider_id: str) -> ModelProvider
    def list_providers(self) -> List[str]
```

### 3.7 模型监控 (`model_monitor.py`)

**调用追踪**:

```python
class ModelCallSpan(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    
    provider: str
    model: str
    kind: SpanKind  # LLM_CALL / TOOL_CALL / REASONING
    
    status: CallStatus  # PENDING / SUCCESS / FAILED
    start_time: datetime
    end_time: Optional[datetime]
    
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost: float
```

**Token 用量追踪**:

```python
class TokenUsageTracker:
    def record_usage(self, span: ModelCallSpan) -> None
    def get_total_usage(self) -> TokenUsage
    def get_usage_by_model(self, model: str) -> TokenUsage
```

**成本预算**:

```python
class CostBudget:
    def __init__(self, max_cost: float, alert_threshold: float = 0.8)
    def check_budget(self, estimated_cost: float) -> bool
    def record_cost(self, actual_cost: float) -> None
```

### 3.8 记忆压缩 (`memory_compaction.py`)

**压缩策略**:

```python
class CompactionStrategy(str, Enum):
    SUMMARY = "summary"           # 摘要压缩
    KEY_INFO = "key_info"         # 关键信息提取
    SEMANTIC = "semantic"         # 语义压缩
    HYBRID = "hybrid"             # 混合策略
```

**记忆压缩器**:

```python
class MemoryCompactor:
    async def compact(
        self,
        messages: List[MemoryMessage],
        strategy: CompactionStrategy,
        max_output_tokens: int,
    ) -> CompactionResult:
        """压缩历史消息"""
```

**关键信息提取**:

```python
class KeyInfoExtractor:
    async def extract(self, messages: List[MemoryMessage]) -> List[KeyInfo]:
        """从消息中提取关键信息"""

class ImportanceScorer:
    def score(self, message: MemoryMessage) -> float:
        """计算消息重要性分数"""
```

### 3.9 向量检索 (`memory_vector.py`)

**向量存储**:

```python
class VectorStore(ABC):
    @abstractmethod
    async def add(self, documents: List[VectorDocument]) -> List[str]:
        """添加文档"""
    
    @abstractmethod
    async def search(self, query: str, k: int = 10) -> List[SearchResult]:
        """搜索相似文档"""

class InMemoryVectorStore(VectorStore):
    """内存向量存储"""
```

**向量记忆存储**:

```python
class VectorMemoryStore:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        vector_store: VectorStore,
    )
    
    async def store_memory(self, content: str, metadata: Dict) -> str:
        """存储记忆"""
    
    async def retrieve_memories(self, query: str, k: int = 5) -> List[SearchResult]:
        """检索相关记忆"""
```

### 3.10 Docker 沙箱 (`sandbox_docker.py`)

**沙箱类型**:

```python
class SandboxType(str, Enum):
    LOCAL = "local"       # 本地执行
    DOCKER = "docker"     # Docker 容器
```

**沙箱配置**:

```python
class SandboxConfig(BaseModel):
    sandbox_type: SandboxType
    image: Optional[str] = "python:3.11-slim"
    workdir: str = "/workspace"
    timeout: int = 300
    memory_limit: str = "1g"
    cpu_limit: float = 1.0
    network_enabled: bool = False
    volume_mounts: Dict[str, str] = {}
```

**沙箱管理器**:

```python
class SandboxManager:
    async def create_sandbox(self, config: SandboxConfig) -> str:
        """创建沙箱"""
    
    async def execute(
        self,
        sandbox_id: str,
        command: str,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """在沙箱中执行命令"""
    
    async def destroy_sandbox(self, sandbox_id: str) -> None:
        """销毁沙箱"""
```

### 3.11 推理策略 (`reasoning_strategy.py`)

**策略类型**:

```python
class StrategyType(str, Enum):
    REACT = "react"                   # ReAct 策略
    PLAN_AND_EXECUTE = "plan_execute" # 规划执行
    CHAIN_OF_THOUGHT = "cot"          # 思维链
    REFLECTION = "reflection"         # 反思
```

**策略接口**:

```python
class ReasoningStrategy(ABC):
    @abstractmethod
    async def execute(
        self,
        goal: str,
        context: Dict[str, Any],
    ) -> ReasoningResult:
        """执行推理"""
```

**ReAct 策略**:

```python
class ReActStrategy(ReasoningStrategy):
    """
    ReAct: 推理 + 行动
    
    循环：
    1. Thought: 思考当前状态
    2. Action: 选择并执行行动
    3. Observation: 观察结果
    4. 重复直到完成
    """
```

**策略工厂**:

```python
class ReasoningStrategyFactory:
    def create(self, strategy_type: StrategyType, **kwargs) -> ReasoningStrategy
```

### 3.12 可观测性 (`observability.py`)

**指标收集**:

```python
class MetricsCollector:
    def record_counter(self, name: str, value: int = 1, tags: Dict = None) -> None
    def record_gauge(self, name: str, value: float, tags: Dict = None) -> None
    def record_histogram(self, name: str, value: float, tags: Dict = None) -> None
```

**链路追踪**:

```python
class Tracer:
    def start_span(self, name: str, parent: Optional[Span] = None) -> Span
    def end_span(self, span: Span) -> None
```

**日志收集**:

```python
class StructuredLogger:
    def log(self, level: LogLevel, message: str, **kwargs) -> None
    def info(self, message: str, **kwargs) -> None
    def error(self, message: str, **kwargs) -> None
```

### 3.13 配置管理 (`config_manager.py`)

**配置源**:

```python
class ConfigSource(str, Enum):
    FILE = "file"           # 文件配置
    ENV = "environment"     # 环境变量
    DEFAULT = "default"     # 默认值
    RUNTIME = "runtime"     # 运行时
```

**Agent 配置**:

```python
class AgentConfig(BaseModel):
    name: str
    version: str = "1.0.0"
    description: Optional[str]
    
    llm: Dict[str, Any]         # LLM 配置
    tools: List[str]            # 工具列表
    permissions: Dict[str, Any] # 权限配置
    
    max_steps: int = 100
    timeout: int = 3600
    
    scene: Optional[str]        # 场景名称
    hooks: List[str] = []       # 钩子列表
```

**配置管理器**:

```python
class ConfigManager:
    def load(self, source: ConfigSource, path: Optional[str] = None) -> None
    def get(self, key: str, default: Any = None) -> Any
    def set(self, key: str, value: Any, source: ConfigSource) -> None
    def watch(self, callback: Callable) -> None
```

### 3.14 任务场景 (`task_scene.py`)

**场景类型**:

```python
class TaskScene(str, Enum):
    GENERAL = "general"           # 通用场景
    CODING = "coding"             # 编码场景
    ANALYSIS = "analysis"         # 分析场景
    CREATIVE = "creative"         # 创意场景
    RESEARCH = "research"         # 研究场景
    DOCUMENTATION = "documentation" # 文档场景
    TESTING = "testing"           # 测试场景
    REFACTORING = "refactoring"   # 重构场景
    DEBUG = "debug"               # 调试场景
    CUSTOM = "custom"             # 自定义场景
```

**场景配置**:

```python
class SceneProfile(BaseModel):
    name: str
    scene_type: TaskScene
    description: str
    
    # Prompt 策略
    system_prompt: str
    prompt_template: Optional[str]
    
    # 上下文策略
    truncation_policy: TruncationPolicy
    compaction_policy: CompactionPolicy
    token_budget: TokenBudget
    
    # 工具策略
    tool_policy: ToolPolicy
    allowed_tools: List[str]
    forbidden_tools: List[str]
    
    # 输出策略
    output_format: OutputFormat
    response_style: ResponseStyle
```

**场景构建器**:

```python
class SceneProfileBuilder:
    def name(self, name: str) -> "SceneProfileBuilder"
    def system_prompt(self, prompt: str) -> "SceneProfileBuilder"
    def truncation(self, strategy: TruncationStrategy) -> "SceneProfileBuilder"
    def tools(self, allowed: List[str]) -> "SceneProfileBuilder"
    def build(self) -> SceneProfile
```

### 3.15 场景策略 (`scene_strategy.py`)

**钩子类型**:

```python
class SceneHook(ABC):
    """场景钩子基类"""
    
    @property
    @abstractmethod
    def phase(self) -> AgentPhase:
        """钩子触发阶段"""
    
    @property
    def priority(self) -> HookPriority:
        """钩子优先级"""
    
    @abstractmethod
    async def execute(self, context: HookContext) -> HookResult:
        """执行钩子"""

class AgentPhase(str, Enum):
    PRE_THINK = "pre_think"
    POST_THINK = "post_think"
    PRE_ACT = "pre_act"
    POST_ACT = "post_act"
    PRE_STEP = "pre_step"
    POST_STEP = "post_step"
    ON_ERROR = "on_error"
    ON_COMPLETE = "on_complete"
```

**内置钩子**:

| 钩子 | 功能 |
|------|------|
| `CodeBlockProtectionHook` | 保护代码块完整性 |
| `FilePathPreservationHook` | 文件路径保持 |
| `CodeStyleInjectionHook` | 代码风格注入 |
| `ProjectContextInjectionHook` | 项目上下文注入 |
| `ToolOutputFormatterHook` | 工具输出格式化 |
| `ErrorRecoveryHook` | 错误恢复处理 |

### 3.16 工具系统 V2 (`tools_v2/`)

**工具基类**:

```python
class ToolBase(ABC):
    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """工具元数据"""
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""

@dataclass
class ToolMetadata:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    returns: str
    examples: List[str]
```

**工具注册器**:

```python
class ToolRegistry:
    def register(self, tool: ToolBase) -> None
    def get(self, name: str) -> Optional[ToolBase]
    def list_tools(self) -> List[ToolMetadata]
    async def execute(self, name: str, **kwargs) -> ToolResult
```

**内置工具**:

| 工具 | 功能 |
|------|------|
| `BashTool` | Shell 命令执行 |
| `ReadTool` | 文件读取 |
| `WriteTool` | 文件写入 |
| `SearchTool` | 内容搜索 |
| `ListFilesTool` | 文件列表 |
| `ThinkTool` | 深度思考 |
| `QuestionTool` | 问题询问 |
| `ConfirmTool` | 确认请求 |
| `NotifyTool` | 通知发送 |
| `ProgressTool` | 进度报告 |
| `WebFetchTool` | 网页获取 |
| `WebSearchTool` | 网页搜索 |
| `APICallTool` | API 调用 |
| `AnalyzeDataTool` | 数据分析 |
| `AnalyzeCodeTool` | 代码分析 |
| `GenerateReportTool` | 报告生成 |

**MCP 工具适配**:

```python
class MCPToolAdapter:
    """将 MCP 协议工具适配为 ToolBase"""
    
    @classmethod
    def adapt(cls, mcp_tool: Any) -> ToolBase:
        """适配 MCP 工具"""
```

### 3.17 长任务执行器 (`long_task_executor.py`)

**长任务配置**:

```python
class LongTaskConfig(BaseModel):
    task_id: str
    goal: str
    
    checkpoint_interval: int = 10
    max_retries: int = 3
    timeout: int = 86400  # 24 hours
    
    on_progress: Optional[Callable[[ProgressReport], None]]
    on_checkpoint: Optional[Callable[[Checkpoint], None]]
```

**进度报告**:

```python
@dataclass
class ProgressReport:
    task_id: str
    phase: ProgressPhase  # INITIALIZING / EXECUTING / COMPLETING
    progress: float       # 0.0 - 1.0
    current_step: int
    total_steps: int
    message: str
    timestamp: datetime
```

---

## 4. 架构层次

### 4.1 总体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Product Layer (产品层)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Chat App   │  │  Code App   │  │  Data App   │  │ Custom Apps │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Execution Framework Layer (执行框架层)              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                         AgentHarness                             │   │
│  │  - Checkpointing: 检查点机制                                     │   │
│  │  - Pause/Resume: 暂停恢复                                        │   │
│  │  - Circuit Breaker: 熔断保护                                     │   │
│  │  - Task Queue: 任务队列                                          │   │
│  │  - State Compression: 状态压缩                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │ ModeManager     │  │ SceneStrategy   │  │ LongTaskExecutor│         │
│  │ (模式切换)      │  │ (场景策略)      │  │ (长任务)        │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Core Component Layer (核心组件层)                  │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ GoalManager │  │ Interaction │  │ Permission  │  │ Reasoning   │    │
│  │ (目标管理)  │  │ (交互系统)  │  │ (权限控制)  │  │ (推理策略)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ ModelProv.  │  │ ModelMonitor│  │ MemoryComp. │  │ MemoryVector│    │
│  │ (模型供应)  │  │ (模型监控)  │  │ (记忆压缩)  │  │ (向量记忆)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ SandboxDocker│  │ Tools V2   │  │ SceneProfile│  │ ConfigManager│    │
│  │ (沙箱执行)  │  │ (工具系统)  │  │ (场景配置)  │  │ (配置管理)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Infrastructure Layer (基础设施层)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ LLMAdapter  │  │ StateStore  │  │ Observability│  │ ContextValid.│   │
│  │ (LLM适配)  │  │ (状态存储)  │  │ (可观测性)  │  │ (上下文验证)│   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 配置驱动架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Configuration Layer (配置层)                          │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                          SceneProfile                              │ │
│  │                                                                    │ │
│  │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │ │
│  │   │ PromptPolicy    │  │ ContextPolicy   │  │ ToolPolicy      │  │ │
│  │   │ - system_prompt │  │ - truncation    │  │ - allowed_tools │  │ │
│  │   │ - template      │  │ - compaction    │  │ - forbidden     │  │ │
│  │   │ - variables     │  │ - token_budget  │  │ - permissions   │  │ │
│  │   └─────────────────┘  └─────────────────┘  └─────────────────┘  │ │
│  │                                                                    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                    │                                    │
│                                    ▼                                    │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                           AgentConfig                              │ │
│  │                                                                    │ │
│  │   name: string                                                     │ │
│  │   scene: SceneProfile                                              │ │
│  │   llm: { provider, model, ... }                                   │ │
│  │   permissions: {}                                                  │ │
│  │   hooks: [HookClass, ...]                                         │ │
│  │                                                                    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ instantiate
┌─────────────────────────────────────────────────────────────────────────┐
│                      Runtime Layer (运行时层)                            │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                           SimpleAgent                              │ │
│  │                                                                    │ │
│  │   Run(config: AgentConfig):                                       │ │
│  │     1. Load SceneProfile                                          │ │
│  │     2. Initialize LLMAdapter                                      │ │
│  │     3. Register Tools                                             │ │
│  │     4. Setup Hooks                                                │ │
│  │     5. Execute with AgentHarness                                  │ │
│  │                                                                    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 数据流

### 5.1 Agent 执行流程

```
Goal Input
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          AgentHarness                                │
│                                                                      │
│  ┌───────────────┐                                                  │
│  │ Initialize    │                                                  │
│  │ - Load config │                                                  │
│  │ - Setup tools │                                                  │
│  │ - Init hooks  │                                                  │
│  └───────────────┘                                                  │
│         │                                                            │
│         ▼                                                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Execution Loop                              │  │
│  │                                                                │  │
│  │   while step < max_steps and not done:                        │  │
│  │       │                                                        │  │
│  │       ├─► [Hook: PRE_STEP]                                    │  │
│  │       │                                                        │  │
│  │       ├─► GoalManager.get_current_subgoal()                   │  │
│  │       │                                                        │  │
│  │       ├─► [Hook: PRE_THINK]                                   │  │
│  │       ├─► LLMAdapter.call(messages) ──► stream response       │  │
│  │       ├─► [Hook: POST_THINK]                                  │  │
│  │       │                                                        │  │
│  │       ├─► Parse tool_calls from response                      │  │
│  │       │                                                        │  │
│  │       ├─► [Hook: PRE_ACT]                                     │  │
│  │       ├─► PermissionManager.check(tool_call)                  │  │
│  │       │       │                                                │  │
│  │       │       ├── ALLOW ──► ToolRegistry.execute()            │  │
│  │       │       ├── DENY ──► return error message               │  │
│  │       │       └── ASK ──► InteractionManager.request()        │  │
│  │       ├─► [Hook: POST_ACT]                                    │  │
│  │       │                                                        │  │
│  │       ├─► GoalManager.check_completion()                      │  │
│  │       │                                                        │  │
│  │       ├─► [Hook: POST_STEP]                                   │  │
│  │       │                                                        │  │
│  │       └─► CheckpointManager.checkpoint() (every N steps)      │  │
│  │                                                                │  │
│  └───────────────────────────────────────────────────────────────┘  │
│         │                                                            │
│         ▼                                                            │
│  ┌───────────────┐                                                  │
│  │ Finalize      │                                                  │
│  │ - Save result │                                                  │
│  │ - Cleanup     │                                                  │
│  └───────────────┘                                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
ExecutionResult
```

### 5.2 场景策略数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Scene Strategy Execution Flow                         │
└─────────────────────────────────────────────────────────────────────────┘

TaskScene (e.g., CODING)
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SceneStrategyExecutor                               │
│                                                                          │
│   1. Load SceneProfile                                                  │
│      ├── System Prompt: "You are an expert coder..."                   │
│      ├── TruncationPolicy: CODE_AWARE                                  │
│      ├── CompactionPolicy: HYBRID                                      │
│      └── ToolPolicy: allowed=[read, write, bash, ...]                  │
│                                                                          │
│   2. Register Hooks                                                     │
│      ├── CodeBlockProtectionHook (PRE_ACT)                             │
│      ├── FilePathPreservationHook (PRE_THINK)                          │
│      ├── CodeStyleInjectionHook (PRE_THINK)                            │
│      └── ErrorRecoveryHook (ON_ERROR)                                  │
│                                                                          │
│   3. Initialize Context                                                 │
│      ├── ContextProcessor.apply_policies()                             │
│      └── ContextValidator.validate()                                   │
│                                                                          │
│   4. Execute with Hooks                                                 │
│      │                                                                   │
│      │   ┌────────────────────────────────────────────────────────┐    │
│      │   │ Hook Chain Execution                                    │    │
│      │   │                                                         │    │
│      │   │   Phase: PRE_THINK                                      │    │
│      │   │   ├── FilePathPreservationHook.execute()               │    │
│      │   │   │   └── Extract and preserve file paths              │    │
│      │   │   └── CodeStyleInjectionHook.execute()                 │    │
│      │   │       └── Inject code style guidelines                 │    │
│      │   │                                                         │    │
│      │   │   Phase: POST_ACT                                       │    │
│      │   │   └── CodeBlockProtectionHook.execute()                │    │
│      │   │       └── Verify code block integrity                  │    │
│      │   │                                                         │    │
│      │   └────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Output Processing                                   │
│                                                                          │
│   ├── OutputFormatter.format(result, OutputFormat.MARKDOWN)            │
│   └── ResponseStyle.apply(style=ResponseStyle.BALANCED)               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.3 记忆压缩数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Memory Compaction Flow                                │
└─────────────────────────────────────────────────────────────────────────┘

New Messages Arrive
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    MemoryCompactionManager                               │
│                                                                          │
│   ├── Check: message_count > trigger_threshold?                        │
│   │                                                                      │
│   └── Yes ──► Compact                                                   │
│              │                                                           │
│              ▼                                                           │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                    Compaction Pipeline                          │   │
│   │                                                                 │   │
│   │   1. ImportanceScorer.score(messages)                          │   │
│   │      └── Calculate importance for each message                 │   │
│   │                                                                 │   │
│   │   2. KeyInfoExtractor.extract(messages)                        │   │
│   │      └── Extract key information                               │   │
│   │                                                                 │   │
│   │   3. SummaryGenerator.generate(key_infos)                      │   │
│   │      └── Generate compact summary                              │   │
│   │                                                                 │   │
│   │   4. Preserve messages by policy:                              │   │
│   │      ├── preserve_tool_results                                 │   │
│   │      ├── preserve_error_messages                               │   │
│   │      └── preserve_user_questions                               │   │
│   │                                                                 │   │
│   └────────────────────────────────────────────────────────────────┘   │
│              │                                                           │
│              ▼                                                           │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                    CompactionResult                             │   │
│   │                                                                 │   │
│   │   summary: "Completed 3 tasks: auth, database, api..."         │   │
│   │   key_infos: [                                                 │   │
│   │     {type: "decision", content: "Chose PostgreSQL..."},        │   │
│   │     {type: "error", content: "Fixed connection timeout..."},   │   │
│   │   ]                                                            │   │
│   │   tokens_saved: 15000                                          │   │
│   │                                                                 │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    VectorMemoryStore Integration                         │
│                                                                          │
│   ├── Embed compacted summary                                          │
│   ├── Store in VectorStore for semantic search                         │
│   └── Enable future retrieval: "What did we decide about auth?"        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 关键设计模式

### 6.1 策略模式 - ReasoningStrategy

```python
class ReasoningStrategy(ABC):
    @abstractmethod
    async def execute(self, goal: str, context: Dict) -> ReasoningResult:
        pass

class ReActStrategy(ReasoningStrategy):
    async def execute(self, goal: str, context: Dict) -> ReasoningResult:
        # ReAct 实现

class PlanAndExecuteStrategy(ReasoningStrategy):
    async def execute(self, goal: str, context: Dict) -> ReasoningResult:
        # 规划执行实现

# 工厂选择策略
strategy = ReasoningStrategyFactory().create(StrategyType.REACT)
```

### 6.2 工厂模式 - 模块工厂

```python
class LLMFactory:
    @staticmethod
    def create(provider: LLMProvider, **kwargs) -> LLMAdapter:
        if provider == LLMProvider.OPENAI:
            return OpenAIAdapter(**kwargs)
        elif provider == LLMProvider.ANTHROPIC:
            return AnthropicAdapter(**kwargs)

class ReasoningStrategyFactory:
    def create(self, strategy_type: StrategyType) -> ReasoningStrategy:
        # 创建对应策略实例
```

### 6.3 注册表模式 - ToolRegistry, ModelRegistry

```python
class ToolRegistry:
    _tools: Dict[str, ToolBase] = {}
    
    def register(self, tool: ToolBase) -> None:
        self._tools[tool.metadata.name] = tool
    
    def get(self, name: str) -> Optional[ToolBase]:
        return self._tools.get(name)

# 全局访问
tool_registry = ToolRegistry()
tool_registry.register(BashTool())
tool_registry.register(ReadTool())
```

### 6.4 构建器模式 - SceneProfileBuilder

```python
profile = (SceneProfileBuilder()
    .name("code-assistant")
    .scene_type(TaskScene.CODING)
    .system_prompt("You are an expert coder...")
    .truncation(TruncationStrategy.CODE_AWARE)
    .tools(["read", "write", "bash", "grep"])
    .build())
```

### 6.5 适配器模式 - MCPToolAdapter

```python
class MCPToolAdapter(ToolBase):
    """将 MCP 协议工具适配为 V2 接口"""
    
    def __init__(self, mcp_tool: MCPTool):
        self._mcp_tool = mcp_tool
    
    async def execute(self, **kwargs) -> ToolResult:
        # 转换参数格式
        mcp_params = self._convert_params(kwargs)
        # 调用 MCP 工具
        result = await self._mcp_tool.execute(mcp_params)
        # 转换结果格式
        return self._convert_result(result)
```

### 6.6 钩子模式 - SceneHook

```python
class SceneHook(ABC):
    @property
    @abstractmethod
    def phase(self) -> AgentPhase:
        pass
    
    @abstractmethod
    async def execute(self, context: HookContext) -> HookResult:
        pass

# 装饰器方式注册
@scene_hook(phase=AgentPhase.PRE_THINK, priority=HookPriority.HIGH)
async def my_hook(context: HookContext) -> HookResult:
    return HookResult(success=True)
```

### 6.7 熔断器模式 - CircuitBreaker

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60):
        self.failures = 0
        self.state = "closed"
    
    async def execute(self, func: Callable) -> Any:
        if self.state == "open":
            raise CircuitBreakerOpen()
        
        try:
            result = await func()
            self.failures = 0
            return result
        except Exception:
            self.failures += 1
            if self.failures >= self.threshold:
                self.state = "open"
            raise
```

### 6.8 观察者模式 - ObservabilityManager

```python
class ObservabilityManager:
    def __init__(self):
        self._metrics = MetricsCollector()
        self._tracer = Tracer()
        self._logger = StructuredLogger()
    
    def observe(self, name: str):
        def decorator(func):
            async def wrapper(*args, **kwargs):
                span = self._tracer.start_span(name)
                try:
                    result = await func(*args, **kwargs)
                    self._metrics.record_counter(f"{name}.success")
                    return result
                except Exception as e:
                    self._metrics.record_counter(f"{name}.error")
                    raise
                finally:
                    self._tracer.end_span(span)
            return wrapper
        return decorator
```

---

## 7. 扩展开发指南

### 7.1 扩展新场景

```python
from derisk.agent.core_v2 import (
    TaskScene,
    SceneProfile,
    SceneProfileBuilder,
    SceneRegistry,
    TruncationStrategy,
)

# 方式1：使用构建器
custom_scene = (SceneProfileBuilder()
    .name("data-pipeline")
    .scene_type(TaskScene.CUSTOM)
    .description("Data pipeline construction specialist")
    .system_prompt("""
You are a data pipeline expert. Your tasks:
1. Analyze data sources
2. Design transformation steps
3. Build robust pipelines
4. Handle errors gracefully
""")
    .truncation(TruncationStrategy.ADAPTIVE)
    .compaction(CompactionStrategy.KEY_INFO)
    .tools(["read", "write", "bash", "python"])
    .output_format(OutputFormat.MARKDOWN)
    .response_style(ResponseStyle.DETAILED)
    .build())

# 方式2：直接创建类
class DataPipelineScene(SceneProfile):
    name: str = "data-pipeline"
    scene_type: TaskScene = TaskScene.CUSTOM
    description: str = "Data pipeline construction"
    system_prompt: str = "You are a data pipeline expert..."
    truncation_policy: TruncationPolicy = TruncationPolicy(
        strategy=TruncationStrategy.ADAPTIVE,
        code_block_protection=True,
    )

# 注册场景
SceneRegistry.register(custom_scene)
```

### 7.2 扩展新钩子

```python
from derisk.agent.core_v2 import (
    SceneHook,
    AgentPhase,
    HookPriority,
    HookContext,
    HookResult,
    scene_hook,
)

# 方式1：类继承
class MyCustomHook(SceneHook):
    @property
    def phase(self) -> AgentPhase:
        return AgentPhase.POST_ACT
    
    @property
    def priority(self) -> HookPriority:
        return HookPriority.HIGH
    
    async def execute(self, context: HookContext) -> HookResult:
        # 在动作执行后进行处理
        tool_result = context.get("last_tool_result")
        if tool_result:
            # 处理结果
            processed = self._process_result(tool_result)
            context.set("processed_result", processed)
        
        return HookResult(
            success=True,
            modified_context=context,
        )
    
    def _process_result(self, result):
        return result

# 方式2：装饰器
@scene_hook(phase=AgentPhase.PRE_THINK)
async def log_thinking(context: HookContext) -> HookResult:
    print(f"Thinking about: {context.get('current_goal')}")
    return HookResult(success=True)

# 注册钩子
hooks = [MyCustomHook(), log_thinking]
```

### 7.3 扩展新工具

```python
from derisk.agent.core_v2 import (
    ToolBase,
    ToolMetadata,
    ToolResult,
    tool,
)

# 方式1：类继承
class DatabaseQueryTool(ToolBase):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="db_query",
            description="Execute SQL queries on database",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL query to execute",
                    },
                    "database": {
                        "type": "string",
                        "description": "Database name",
                    },
                },
                "required": ["query"],
            },
        )
    
    async def execute(self, query: str, database: str = "default") -> ToolResult:
        try:
            # 执行查询
            results = await self._run_query(query, database)
            return ToolResult(
                success=True,
                output=results,
                metadata={"rows_affected": len(results)},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e),
            )
    
    async def _run_query(self, query: str, database: str):
        # 实现查询逻辑
        return []

# 方式2：装饰器
@tool(
    name="translate",
    description="Translate text between languages",
    parameters={
        "text": {"type": "string", "description": "Text to translate"},
        "target_lang": {"type": "string", "description": "Target language"},
    },
)
async def translate_tool(text: str, target_lang: str = "en") -> str:
    # 实现翻译
    return f"Translated: {text}"
```

### 7.4 扩展新推理策略

```python
from derisk.agent.core_v2 import (
    ReasoningStrategy,
    ReasoningStep,
    ReasoningResult,
    StrategyType,
)

class TreeOfThoughtStrategy(ReasoningStrategy):
    """
    Tree of Thought 推理策略
    
    生成多个候选思路，评估后选择最优
    """
    
    def __init__(self, num_thoughts: int = 3):
        self.num_thoughts = num_thoughts
    
    async def execute(
        self,
        goal: str,
        context: Dict[str, Any],
    ) -> ReasoningResult:
        # 1. 生成多个候选思路
        thoughts = await self._generate_thoughts(goal, context)
        
        # 2. 评估每个思路
        evaluations = await self._evaluate_thoughts(thoughts, goal)
        
        # 3. 选择最优思路
        best_thought = self._select_best(thoughts, evaluations)
        
        # 4. 执行最优思路
        result = await self._execute_thought(best_thought, context)
        
        return ReasoningResult(
            success=True,
            steps=[ReasoningStep(thought=t) for t in thoughts],
            final_answer=result,
        )
    
    async def _generate_thoughts(self, goal, context):
        # 实现
        pass
    
    async def _evaluate_thoughts(self, thoughts, goal):
        # 实现
        pass

# 注册策略
from derisk.agent.core_v2 import reasoning_strategy_factory
reasoning_strategy_factory.register(StrategyType.TREE_OF_THOUGHT, TreeOfThoughtStrategy)
```

### 7.5 扩展新模型提供者

```python
from derisk.agent.core_v2 import (
    ModelProvider,
    ModelConfig,
    ModelMessage,
    ModelResponse,
    ModelRegistry,
)

class CustomModelProvider(ModelProvider):
    """自定义模型提供者"""
    
    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint
    
    async def call(
        self,
        messages: List[ModelMessage],
        config: ModelConfig,
        options: Optional[CallOptions] = None,
    ) -> ModelResponse:
        # 转换消息格式
        api_messages = [m.to_dict() for m in messages]
        
        # 调用 API
        response = await self._api_call(api_messages, config)
        
        # 转换响应
        return ModelResponse(
            content=response["content"],
            tool_calls=response.get("tool_calls"),
            usage=response.get("usage"),
        )
    
    async def _api_call(self, messages, config):
        # 实现具体的 API 调用
        pass

# 注册提供者
model_registry.register("custom_provider", CustomModelProvider())
```

### 7.6 扩展权限检查

```python
from derisk.agent.core_v2 import (
    PermissionChecker,
    PermissionRequest,
    PermissionResponse,
    PermissionAction,
)

class RoleBasedPermissionChecker(PermissionChecker):
    """基于角色的权限检查器"""
    
    def __init__(self, roles: Dict[str, List[str]]):
        """
        Args:
            roles: {role_name: [allowed_tool_names]}
        """
        self.roles = roles
        self.user_role = "default"
    
    def set_role(self, role: str):
        self.user_role = role
    
    async def check(self, request: PermissionRequest) -> PermissionResponse:
        allowed_tools = self.roles.get(self.user_role, [])
        
        if request.tool_name in allowed_tools:
            return PermissionResponse(
                action=PermissionAction.ALLOW,
                reason=f"Tool allowed for role: {self.user_role}",
            )
        
        # 检查是否有通配符匹配
        for pattern in allowed_tools:
            if fnmatch.fnmatch(request.tool_name, pattern):
                return PermissionResponse(
                    action=PermissionAction.ALLOW,
                    reason=f"Tool matched pattern: {pattern}",
                )
        
        return PermissionResponse(
            action=PermissionAction.DENY,
            reason=f"Tool not allowed for role: {self.user_role}",
        )
```

---

## 8. 使用示例

### 8.1 创建简单 Agent

```python
from derisk.agent.core_v2 import (
    SimpleAgent,
    LLMAdapter,
    LLMFactory,
    LLMProvider,
    ToolRegistry,
    register_builtin_tools,
)

# 创建 LLM 适配器
llm = LLMFactory.create(
    provider=LLMProvider.OPENAI,
    model="gpt-4",
    api_key="your-api-key",
)

# 注册工具
tool_registry = ToolRegistry()
register_builtin_tools(tool_registry)

# 创建 Agent
agent = SimpleAgent(
    name="assistant",
    llm_adapter=llm,
    tools=tool_registry.list_tools(),
)

# 运行
result = await agent.run("Write a Python script to fetch weather data")
print(result.answer)
```

### 8.2 使用场景配置

```python
from derisk.agent.core_v2 import (
    SimpleAgent,
    get_scene_profile,
    SceneProfileBuilder,
    TaskScene,
)

# 使用预置场景
coding_scene = get_scene_profile(TaskScene.CODING)

# 或创建自定义场景
custom_scene = (SceneProfileBuilder()
    .name("my-coding-assistant")
    .scene_type(TaskScene.CODING)
    .system_prompt("You are a Python expert...")
    .tools(["read", "write", "bash", "python", "pytest"])
    .build())

# 创建 Agent 并应用场景
agent = SimpleAgent(
    name="coder",
    llm_adapter=llm,
    tools=custom_scene.allowed_tools,
    scene=custom_scene,
)

result = await agent.run("Implement a REST API with FastAPI")
```

### 8.3 使用执行框架

```python
from derisk.agent.core_v2 import (
    AgentHarness,
    ExecutionContext,
    FileStateStore,
    CheckpointType,
)

# 创建状态存储
state_store = FileStateStore("/path/to/checkpoints")

# 创建执行框架
harness = AgentHarness(
    max_steps=100,
    checkpoint_interval=10,
    state_store=state_store,
)

# 创建上下文
context = ExecutionContext(
    system_layer={"scene": "coding"},
    task_layer={"goal": "Build a web scraper"},
)

# 定义进度回调
async def on_progress(report):
    print(f"Progress: {report.progress:.0%} - {report.message}")

# 执行
result = await harness.execute(
    goal="Build a web scraper for news articles",
    context=context,
    on_step=on_progress,
)

print(f"Completed: {result.success}")
print(f"Steps: {result.total_steps}")
```

### 8.4 使用目标管理

```python
from derisk.agent.core_v2 import (
    GoalManager,
    Goal,
    GoalPriority,
    SuccessCriterion,
    CriterionType,
)

# 创建目标管理器
manager = GoalManager()

# 创建主目标
main_goal = manager.create_goal(
    name="Build API",
    description="Build a complete REST API",
    priority=GoalPriority.HIGH,
    success_criteria=[
        SuccessCriterion(
            name="Endpoints work",
            criterion_type=CriterionType.TEST_PASSES,
            expected_value="test_api.py",
        ),
    ],
)

# 分解为子目标
sub_goals = manager.decompose_goal(
    main_goal.id,
    strategy=GoalDecompositionStrategy.SEQUENTIAL,
)

for sub in sub_goals:
    print(f"Sub-goal: {sub.name}")

# 跟踪进度
manager.update_progress(sub_goals[0].id, 0.5)
completed, reason = manager.check_completion(main_goal.id)
```

### 8.5 使用交互系统

```python
from derisk.agent.core_v2 import (
    InteractionManager,
    BatchInteractionManager,
    CLIInteractionHandler,
    InteractionType,
    NotifyLevel,
)

# 创建交互管理器
interaction = InteractionManager()
interaction.register_handler("cli", CLIInteractionHandler())

# 确认请求
response = await interaction.request(
    interaction_type=InteractionType.CONFIRMATION,
    message="About to delete 10 files. Continue?",
    timeout=60.0,
)

if response.confirmed:
    print("User confirmed")
else:
    print("User declined")

# 发送通知
await interaction.notify(
    level=NotifyLevel.INFO,
    message="Task completed successfully",
)
```

### 8.6 使用记忆压缩

```python
from derisk.agent.core_v2 import (
    MemoryCompactionManager,
    CompactionStrategy,
)

# 创建压缩管理器
compactor = MemoryCompactionManager(
    strategy=CompactionStrategy.HYBRID,
    trigger_threshold=40,
)

# 添加消息
for msg in conversation_history:
    compactor.add_message(msg)

# 触发压缩
result = await compactor.compact()

print(f"Summary: {result.summary}")
print(f"Key info: {result.key_infos}")
print(f"Tokens saved: {result.tokens_saved}")
```

---

## 9. 用户交互系统

### 9.1 概述

Core V2 提供增强的用户交互能力，基于现有的 InteractionManager 进行扩展：
- **EnhancedInteractionManager**：增强的交互管理器
- **WebSocket 实时通信**：支持实时双向通信
- **智能授权缓存**：避免重复确认
- **完整恢复机制**：任意点中断后完美恢复

### 9.2 核心组件

```
packages/derisk-core/src/derisk/agent/
├── interaction/                    # 共享交互模块
│   ├── interaction_protocol.py    # 交互协议定义
│   ├── interaction_gateway.py     # 交互网关
│   └── recovery_coordinator.py    # 恢复协调器
│
└── core_v2/
    └── enhanced_interaction.py    # 增强交互管理器
```

### 9.3 EnhancedInteractionManager 使用

```python
from derisk.agent.core_v2 import EnhancedInteractionManager

interaction = EnhancedInteractionManager(
    session_id="session_001",
    agent_name="code-assistant",
)

# 设置执行上下文
interaction.set_step(10)
interaction.set_execution_id("exec_001")

# 主动提问
answer = await interaction.ask("请提供数据库连接信息")

# 确认操作
confirmed = await interaction.confirm("确定要部署到生产环境吗？")

# 智能授权（支持缓存）
authorized = await interaction.request_authorization_smart(
    tool_name="bash",
    tool_args={"command": "npm run deploy"},
    reason="部署到生产环境",
)

# 方案选择
plan = await interaction.choose_plan([
    {"id": "plan_a", "name": "蓝绿部署", "pros": ["零停机"], "cons": ["资源双倍"]},
    {"id": "plan_b", "name": "滚动更新", "pros": ["资源节省"], "cons": ["短暂停机"]},
])

# 通知
await interaction.notify_progress("正在部署...", progress=0.5)
await interaction.notify_success("部署完成")
```

### 9.4 Todo 管理

```python
# 创建 Todo
todo_id = await interaction.create_todo(
    content="实现 API 接口",
    priority=1,
    dependencies=["design_db"],  # 依赖其他 Todo
)

# 开始执行
await interaction.start_todo(todo_id)

# 完成
await interaction.complete_todo(todo_id, result="API 已实现")

# 获取进度
completed, total = interaction.get_progress()
next_todo = interaction.get_next_todo()
```

### 9.5 中断与恢复

```python
from derisk.agent.interaction import get_recovery_coordinator

recovery = get_recovery_coordinator()

# 检查恢复状态
if await recovery.has_recovery_state("session_001"):
    result = await recovery.recover(
        session_id="session_001",
        resume_mode="continue",
    )
    
    if result.success:
        # 恢复对话历史
        history = result.recovery_context.conversation_history
        # 恢复 Todo 列表
        todos = result.recovery_context.todo_list
        # 恢复变量
        variables = result.recovery_context.variables
```

### 9.6 授权缓存机制

```python
class AuthorizationCache:
    """授权缓存支持三种范围"""
    
    # once: 单次使用后失效
    # session: 会话期间有效
    # always: 永久有效
    
    def is_valid(self) -> bool:
        # 检查缓存是否仍然有效
        pass
```

### 9.7 与 Core V1 交互对比

| 特性 | Core V1 | Core V2 |
|------|---------|---------|
| **交互管理器** | InteractionAdapter | EnhancedInteractionManager |
| **授权缓存** | 会话级 | 单次/会话/永久级 |
| **Todo 管理** | 基础 | 完整（含依赖管理） |
| **恢复机制** | RecoveryCoordinator | RecoveryCoordinator |
| **WebSocket 支持** | 通过 Gateway | 通过 Gateway |

---

## 9.8 VIS 推送系统

Core V2 提供 VIS 推送能力，用于支持 vis_window3 渲染。采用**配置驱动 + 管理器分离**的设计。

### 设计原则

1. **配置驱动** - 通过 AgentInfo.enable_vis_push 控制
2. **职责分离** - VISPushManager 专注于推送，Agent 专注于业务
3. **钩子扩展** - 支持 VISPushHook 通过钩子系统扩展
4. **可选注入** - 没有 GptsMemory 时静默跳过

### VISPushManager - VIS 推送管理器

```python
from derisk.agent.core_v2 import VISPushManager, VISPushConfig

# 创建推送管理器
config = VISPushConfig(
    enabled=True,
    push_thinking=True,
    push_tool_calls=True,
)

manager = VISPushManager(
    gpts_memory=gpts_memory,
    conv_id="conv-123",
    agent_name="my-agent",
    config=config,
)

# 初始化消息
manager.init_message(goal="用户的问题")

# 推送 thinking
await manager.push_thinking("正在思考...")

# 推送工具调用
await manager.push_tool_start("bash", {"command": "ls"})
await manager.push_tool_result("bash", "file1.txt\nfile2.txt", success=True)

# 推送最终响应
await manager.push_response("任务完成")
```

### VISPushHook - 钩子系统支持

```python
from derisk.agent.core_v2 import VISPushHook, create_vis_push_hooks

# 创建钩子
hook = VISPushHook(
    gpts_memory=gpts_memory,
    conv_id="conv-123",
    config=VISPushConfig(enabled=True),
)

# 添加到场景配置
profile = SceneProfileBuilder()
    .name("vis-enabled-agent")
    .hooks([hook])
    .build()

# 或使用工厂函数创建多个钩子
hooks = create_vis_push_hooks(
    gpts_memory=gpts_memory,
    conv_id="conv-123",
    combined=True,  # 使用组合钩子
)
```

### AgentInfo 配置

```python
from derisk.agent.core_v2 import AgentInfo

# 启用 VIS 推送（默认启用）
info = AgentInfo(
    name="my-agent",
    enable_vis_push=True,      # 总开关
    vis_push_thinking=True,    # 推送 thinking
    vis_push_tool_calls=True,  # 推送工具调用
)
```

### 与 Core V1 对比

| 特性 | Core V1 | Core V2 |
|------|---------|---------|
| **推送方式** | Agent 内置 listen_thinking_stream() | VISPushManager 分离 |
| **配置控制** | 无 | enable_vis_push 配置 |
| **钩子支持** | 无 | VISPushHook |
| **职责分离** | 耦合在 Agent 中 | 独立管理器 |

---

## 10. Shared Infrastructure (共享基础设施)

### 10.1 概述

Core V2 与 Core V1 共享一套基础设施层，遵循**统一资源平面**设计原则：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Shared Infrastructure Layer                          │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ AgentFileSystem │  │ TaskBoardManager│  │ ContextArchiver │             │
│  │ (统一文件管理)   │  │ (Todo/Kanban)   │  │ (自动归档)      │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           └────────────────────┴────────────────────┘                       │
│                               │                                              │
│                    ┌──────────▼──────────┐                                   │
│                    │ SharedSessionContext│                                   │
│                    │  (会话上下文容器)    │                                   │
│                    └──────────┬──────────┘                                   │
└───────────────────────────────┼─────────────────────────────────────────────┘
                    ┌───────────┴───────────┐
                    │                       │
        ┌───────────▼───────────┐ ┌─────────▼─────────────┐
        │       Core V1         │ │       Core V2         │
        │  (V1ContextAdapter)   │ │  (V2ContextAdapter)   │
        └───────────────────────┘ └───────────────────────┘
```

**设计原则：**
- **统一资源平面**：所有基础数据存储管理使用同一套组件
- **架构无关**：不依赖特定 Agent 架构实现
- **会话隔离**：每个会话独立管理资源
- **易于维护**：组件集中管理，减少重复代码

### 10.2 核心组件

#### SharedSessionContext - 统一会话上下文容器

```python
from derisk.agent.shared import SharedSessionContext, SharedContextConfig

# 创建共享上下文
config = SharedContextConfig(
    archive_threshold_tokens=2000,
    auto_archive=True,
    enable_task_board=True,
)

ctx = await SharedSessionContext.create(
    session_id="session_001",
    conv_id="conv_001",
    gpts_memory=gpts_memory,
    config=config,
)

# 访问组件
await ctx.file_system.save_file(...)
await ctx.task_board.create_todo(...)
result = await ctx.archiver.process_tool_output(...)

# 清理
await ctx.close()
```

#### ContextArchiver - 上下文自动归档器

Core V2 通过 ContextArchiver 实现工具输出自动归档，与 MemoryCompaction 协同工作：

```python
from derisk.agent.shared import ContextArchiver, ContentType

# 处理工具输出（自动判断是否需要归档）
result = await archiver.process_tool_output(
    tool_name="bash",
    output=large_output,
)

if result["archived"]:
    print(f"已归档到: {result['archive_ref']['file_id']}")
    # 上下文中只保留预览
    context_content = result["content"]

# 上下文压力时自动归档
archived = await archiver.auto_archive_for_pressure(
    current_tokens=90000,
    budget_tokens=100000,
)
```

#### TaskBoardManager - 任务看板管理器

支持推理过程按需创建 Todo/Kanban：

```python
from derisk.agent.shared import TaskBoardManager, TaskStatus, TaskPriority

# Todo 模式（简单任务）
task = await manager.create_todo(
    title="分析数据文件",
    description="读取并分析 data.csv",
    priority=TaskPriority.HIGH,
)

# Kanban 模式（复杂阶段化任务）
result = await manager.create_kanban(
    mission="完成数据分析报告",
    stages=[
        {"stage_id": "collect", "description": "收集数据"},
        {"stage_id": "analyze", "description": "分析数据"},
        {"stage_id": "report", "description": "生成报告"},
    ]
)

# 提交阶段交付物
await manager.submit_deliverable(
    stage_id="collect",
    deliverable={"data_source": "data.csv", "row_count": 10000},
)
```

### 10.3 V2ContextAdapter - Core V2 适配器

```python
from derisk.agent.shared import SharedSessionContext, V2ContextAdapter

# 创建共享上下文
shared_ctx = await SharedSessionContext.create(
    session_id="session_001",
    conv_id="conv_001",
)

# 创建适配器
adapter = V2ContextAdapter(shared_ctx)

# 获取增强的工具集（包含 Todo/Kanban 工具）
enhanced_tools = await adapter.get_enhanced_tools()

# 创建 Agent 并集成
agent = SimpleAgent(
    name="assistant",
    llm_adapter=llm_adapter,
    tools=base_tools + enhanced_tools,
)

# 集成到 Harness（注册钩子）
harness = AgentHarness(...)
await adapter.integrate_with_harness(harness)
```

### 10.4 钩子集成

V2ContextAdapter 自动注册以下钩子：

| 钩子 | 功能 |
|------|------|
| `on_context_pressure` | 上下文压力时自动归档 |
| `after_action` | 工具执行后检查并归档大输出 |
| `on_skill_complete` | Skill 完成时归档内容 |

```python
# 钩子配置
await adapter.integrate_with_harness(
    harness,
    hooks_config={
        "context_pressure": True,
        "tool_output_archive": True,
        "skill_exit": True,
    },
)
```

### 10.5 与 MemoryCompaction 协同

ContextArchiver 与 MemoryCompaction 协同工作：

```
工具输出
    │
    ├── 大于阈值? ──是──► ContextArchiver.process_tool_output()
    │                           │
    │                           └──► 保存到文件，返回预览+引用
    │
    └── 小于阈值 ──否──► 直接返回

MemoryCompaction.compact()
    │
    ├── 检查归档引用
    │
    └── 压缩时保留引用，可按需恢复完整内容
```

### 10.6 最佳实践

1. **会话开始时创建 SharedSessionContext**
2. **使用 V2ContextAdapter 集成到 AgentHarness**
3. **启用所有钩子获得完整功能**
4. **长任务推荐 Kanban 模式**
5. **会话结束时调用 close() 清理资源**

---

## 11. 与 Core V1 对比

### 11.1 架构差异

```
Core V1 (学术论文驱动)                    Core V2 (配置驱动)
─────────────────────────                ─────────────────────────
Profiling Module                         AgentConfig + SceneProfile
    │                                        │
    ├── Role                                ├── AgentInfo
    ├── Profile                             ├── SceneProfile
    └── AgentInfo                           └── Hooks

Memory Module                             Memory System V2
    │                                        │
    ├── SensoryMemory                       ├── VectorMemoryStore
    ├── ShortTermMemory                     ├── MemoryCompaction
    └── LongTermMemory                      └── KeyInfo Extraction

Planning Module                           Reasoning System
    │                                        │
    ├── ExecutionEngine                     ├── AgentHarness
    ├── ExecutionLoop                       ├── CheckpointManager
    └── ContextLifecycle                    └── ReasoningStrategy

Action Module                             Action System V2
    │                                        │
    ├── Action                              ├── ToolBase
    ├── ActionOutput                        ├── ToolRegistry
    └── SandboxManager                      └── SandboxDocker
```

### 11.2 功能对比

| 功能 | Core V1 | Core V2 |
|------|---------|---------|
| **执行持久化** | 无 | 检查点 + 状态存储 |
| **长任务支持** | 有限 | 完整支持 + 进度报告 |
| **场景预设** | 无 | 9种预设场景 |
| **钩子系统** | 11个钩子点 | 13个钩子点 + 优先级 |
| **模型监控** | 无 | Token追踪 + 成本预算 |
| **向量检索** | 无 | 内置向量存储 |
| **权限交互** | 简单检查 | 交互式确认 |
| **并行工具** | 无 | 批量执行 |
| **错误恢复** | 基础重试 | 熔断器 + 恢复钩子 |

### 11.3 迁移指南

```python
# Core V1 方式
from derisk.agent.core import ConversableAgent, AgentInfo

agent_info = AgentInfo(
    name="assistant",
    mode=AgentMode.PRIMARY,
    temperature=0.7,
)

agent = ConversableAgent(agent_info=agent_info)
await agent.build()

# Core V2 方式
from derisk.agent.core_v2 import SimpleAgent, AgentConfig, get_scene_profile

config = AgentConfig(
    name="assistant",
    scene=get_scene_profile(TaskScene.GENERAL),
    llm={"provider": "openai", "model": "gpt-4"},
)

agent = SimpleAgent.from_config(config)
result = await agent.run("Your task here")
```

---

**文档版本**: v2.2  
**最后更新**: 2026-02-28  
**参考资料**: 
- DERISK Core V1 架构文档
- OpenCode/OpenClaw 设计模式
- Agent Capability Framework 设计

---

## 12. MultiAgent 架构设计

> @see multi_agent/模块
> @see product_agent_registry.py - 产品Agent注册中心
> @see agent_binding.py - Agent资源绑定

### 12.1 概述

CoreV2 MultiAgent架构实现了**产品层统一、资源平面共享**的多Agent协作能力：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Product Layer (产品层)                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Chat App   │  │  Code App   │  │  Data App   │  │ Custom Apps │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         └────────────────┼────────────────┼────────────────┘               │
│                          ▼                ▼                                │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                    ProductAgentRegistry (产品Agent注册中心)          │   │
│  │  - app_code → AgentTeamConfig 映射                                  │   │
│  │  - 产品级Agent配置管理                                               │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Orchestration Layer (编排层)                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    MultiAgentOrchestrator                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │ TaskPlanner  │  │ AgentRouter  │  │ ResultMerger │               │   │
│  │  │ (任务规划)   │  │ (Agent路由)  │  │ (结果合并)   │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Agent Execution Layer (Agent执行层)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ AnalystAgent│  │ CoderAgent  │  │ TesterAgent │  │ CustomAgent │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                    AgentHarness (执行框架 - CoreV2已有)              │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Shared Resource Plane (共享资源平面)                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    SharedContext (共享上下文)                         │   │
│  │  - 协作黑板    - 产出物仓库    - 共享记忆    - 资源缓存               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 12.2 核心模块

| 模块 | 文件 | 功能描述 |
|------|------|----------|
| **SharedContext** | `multi_agent/shared_context.py` | 多Agent协作的数据平面 |
| **TaskPlanner** | `multi_agent/planner.py` | 任务分解与执行计划生成 |
| **MultiAgentOrchestrator** | `multi_agent/orchestrator.py` | 多Agent编排与调度 |
| **AgentTeam** | `multi_agent/team.py` | Agent团队管理 |
| **AgentRouter** | `multi_agent/router.py` | 任务到Agent的智能路由 |
| **TeamMessenger** | `multi_agent/messenger.py` | Agent间消息传递 |
| **TeamMonitor** | `multi_agent/monitor.py` | 团队执行监控 |
| **ProductAgentRegistry** | `product_agent_registry.py` | 产品Agent配置注册中心 |
| **ProductAgentBinding** | `agent_binding.py` | 产品-Agent绑定服务 |

### 12.3 使用示例

#### 12.3.1 基本多Agent执行

```python
from derisk.agent.core_v2 import (
    MultiAgentOrchestrator,
    ExecutionStrategy,
    SharedContext,
)

# 创建编排器
orchestrator = MultiAgentOrchestrator(
    max_parallel_agents=3,
)

# 执行多Agent任务
result = await orchestrator.execute(
    goal="开发用户登录模块",
    team_capabilities={"analysis", "coding", "testing"},
    available_agents={
        "analyst": ["analysis"],
        "coder": ["coding"],
        "tester": ["testing"],
    },
    execution_strategy=ExecutionStrategy.HIERARCHICAL,
)

print(result.get_summary())
```

#### 12.3.2 产品-Agent绑定

```python
from derisk.agent.core_v2 import (
    ProductAgentRegistry,
    ProductAgentBinding,
    AgentTeamConfig,
    AgentConfig,
    ResourceBinding,
    ResourceScope,
)

# 创建注册中心和绑定服务
registry = ProductAgentRegistry()
binding = ProductAgentBinding(registry)

# 配置Agent团队
team_config = AgentTeamConfig(
    team_id="dev-team-1",
    team_name="Development Team",
    app_code="code_app",
    worker_configs=[
        AgentConfig(agent_type="analyst", capabilities=["analysis"]),
        AgentConfig(agent_type="coder", capabilities=["coding"]),
        AgentConfig(agent_type="tester", capabilities=["testing"]),
    ],
    execution_strategy="hierarchical",
    max_parallel_workers=2,
)

# 绑定到产品
result = await binding.bind_agents_to_app(
    app_code="code_app",
    team_config=team_config,
)

# 绑定资源
registry.bind_resources("code_app", [
    ResourceBinding(
        resource_type="knowledge",
        resource_name="code_wiki",
        shared_scope=ResourceScope.TEAM,
    ),
])

# 解析执行上下文
team_config, context = await binding.resolve_agents_for_app("code_app")
```

#### 12.3.3 共享上下文使用

```python
from derisk.agent.core_v2 import SharedContext, MemoryEntry

# 创建共享上下文
context = SharedContext(session_id="session-123")

# 更新任务结果
await context.update(
    task_id="task-1",
    result={"status": "completed", "files": ["main.py", "test.py"]},
    artifacts={"source_code": "...code content...", "test_report": "...report..."},
)

# 获取产出物
artifact = context.get_artifact("source_code")

# 添加共享记忆
await context.add_memory(
    content="用户要求使用Python实现",
    source="user_input",
    importance=0.9,
)

# 搜索记忆
memories = await context.search_memory("Python")
```

#### 12.3.4 Agent团队管理

```python
from derisk.agent.core_v2 import (
    AgentTeam,
    TeamConfig,
    AgentRole,
    WorkerAgent,
)

# 配置团队
config = TeamConfig(
    team_name="DevTeam",
    worker_types=["analyst", "coder", "tester"],
    max_parallel_workers=3,
)

# 创建团队
team = AgentTeam(config=config, shared_context=context)
await team.initialize()

# 并行执行任务
results = await team.execute_parallel(tasks)

# 获取统计信息
stats = team.get_statistics()
print(f"活跃Worker: {stats['active_workers']}")
```

### 12.4 执行策略

| 策略 | 描述 | 适用场景 |
|------|------|----------|
| **SEQUENTIAL** | 顺序执行任务 | 有严格依赖的任务 |
| **PARALLEL** | 并行执行所有任务 | 独立无依赖任务 |
| **HIERARCHICAL** | 按层次并行执行 | 部分依赖的任务 |
| **ADAPTIVE** | 根据任务自动选择策略 | 自动化场景 |

### 12.5 数据流

```
用户请求
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Product Layer Entry                           │
│  app_chat(app_code="code_app", user_query="开发登录模块")        │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│         ProductAgentBinding.resolve_agents_for_app()             │
│  ↓ 解析: AgentTeamConfig + SharedContext + Resources            │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│              MultiAgentOrchestrator.execute()                    │
│                                                                  │
│  1. TaskPlanner.plan() → 分解任务                               │
│  2. AgentRouter.route() → 分配Agent                             │
│  3. execute_hierarchical() → 层次执行                           │
│     ┌────────────────────────────────────────────────────────┐  │
│     │ Level 1: [AnalystAgent] 分析需求                       │  │
│     │           ↓ 写入SharedContext                          │  │
│     │ Level 2: [ArchitectAgent] 设计方案                     │  │
│     │           ↓ 写入SharedContext                          │  │
│     │ Level 3: [CoderAgent] + [TesterAgent] 并行执行         │  │
│     └────────────────────────────────────────────────────────┘  │
│  4. ResultMerger.merge() → 合并结果                             │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
ExecutionResult (最终结果 + 所有Artifacts)
```

### 12.6 与现有架构集成

MultiAgent模块与CoreV2现有组件无缝集成：

```
MultiAgent 模块
      │
      ├──► GoalManager (goal.py) - 任务目标管理
      │
      ├──► AgentHarness (agent_harness.py) - 单Agent执行框架
      │
      ├──► ToolRegistry (tools_v2/) - 工具共享
      │
      ├──► MemoryCompaction - 记忆压缩
      │
      ├──► ResourceManager (resource/) - 资源管理
      │
      └──► ObservabilityManager - 可观测性
```

### 12.7 扩展开发

#### 12.7.1 自定义Agent类型

```python
from derisk.agent.core_v2 import AgentConfig

# 定义新Agent类型
custom_agent = AgentConfig(
    agent_type="security_analyst",
    agent_name="安全分析师",
    capabilities=["security_scan", "vulnerability_analyze"],
    tools=["code_scan", "dependency_check"],
    is_coordinator=False,
)

# 注册到团队配置
team_config.worker_configs.append(custom_agent)
```

#### 12.7.2 自定义路由策略

```python
from derisk.agent.core_v2 import AgentRouter, RoutingStrategy

router = AgentRouter(default_strategy=RoutingStrategy.BEST_FIT)

# 注册Agent能力
router.register_agent("analyst", ["analysis", "research"], proficiency=0.9)
router.register_agent("coder", ["coding", "debugging"], proficiency=0.85)

# 路由任务
result = router.route(task, strategy=RoutingStrategy.LEAST_LOADED)
```

#### 12.7.3 自定义共享资源

```python
from derisk.agent.core_v2 import SharedContext

context = SharedContext(session_id="session-123")

# 设置自定义资源
context.set_resource("api_client", my_api_client)

# 在Agent中访问
api = context.get_resource("api_client")
```

### 12.8 最佳实践

1. **产品优先设计** - 先定义产品应用，再配置Agent团队
2. **资源共享** - 通过SharedContext实现Agent间数据共享
3. **层次执行** - 复杂任务使用HIERARCHICAL策略
4. **监控集成** - 使用TeamMonitor跟踪执行状态
5. **资源绑定** - 在产品级别绑定共享资源
- Shared Infrastructure 设计文档