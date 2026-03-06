# DERISK Core V1 架构文档

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
11. [与 Core V2 对比](#11-与-core-v2-对比)

---

## 1. 概述

DERISK Core V1 是一个基于学术论文《A Survey on Large Language Model Based Autonomous Agents》设计的 Agent 框架。框架将 Agent 架构分为四个核心模块：

- **Profiling Module** - 角色配置与身份定义
- **Memory Module** - 信息存储与记忆管理
- **Planning Module** - 任务规划与推理
- **Action Module** - 动作执行与环境交互

该架构借鉴了 OpenCode/OpenClaw 的最佳实践，提供了声明式配置、权限控制、上下文生命周期管理等高级特性。

### 核心设计理念

```
┌─────────────────────────────────────┐
│         Autonomous Agent            │
└─────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌────────┐  ┌─────────┐  ┌──────────┐
│Profiling│  │ Memory  │  │ Planning │
│ Module  │  │ Module  │  │  Module  │
└────────┘  └─────────┘  └──────────┘
                  │
                  ▼
           ┌──────────┐
           │  Action  │
           │  Module  │
           └──────────┘
```

---

## 2. 目录结构

```
packages/derisk-core/src/derisk/agent/core/
├── __init__.py                 # 模块入口，导出所有公共API
├── base_agent.py               # 核心代理基类 ConversableAgent
├── agent.py                    # Agent 接口定义
├── agent_info.py               # Agent 声明式配置与权限系统
├── execution_engine.py         # 简化版执行引擎
├── prompt_v2.py                # 简化版提示系统
├── simple_memory.py            # 简化版内存系统
├── skill.py                    # 技能系统
├── schema.py                   # 核心数据模型定义
├── types.py                    # 类型定义
├── role.py                     # 角色定义
├── llm_config.py               # LLM 配置
├── base_parser.py              # 解析器基类
├── base_team.py                # 团队基类
├── action_parser.py            # 动作解析器
├── user_proxy_agent.py         # 用户代理
├── scheduled_agent.py          # 调度代理
├── sandbox_manager.py          # 沙箱管理器
├── variable.py                 # 变量管理
├── agent_manage.py             # Agent 管理
├── system_tool_registry.py     # 系统工具注册
│
├── execution/                  # 执行模块
│   ├── __init__.py
│   ├── execution_loop.py       # 执行循环
│   └── llm_executor.py         # LLM 执行器
│
├── context_lifecycle/          # 上下文生命周期管理
│   ├── __init__.py
│   ├── simple_manager.py       # V2 简化版管理器（推荐）
│   ├── base_lifecycle.py       # 生命周期基类
│   ├── slot_manager.py         # 槽位管理器
│   ├── skill_lifecycle.py      # Skill 生命周期
│   ├── tool_lifecycle.py       # 工具生命周期
│   ├── orchestrator.py         # 编排器
│   ├── context_assembler.py    # 上下文组装器
│   ├── agent_integration.py    # Agent 集成
│   ├── skill_monitor.py        # Skill 监控
│   └── extensions.py           # 扩展功能
│
├── action/                     # 动作模块
│   ├── __init__.py
│   ├── base.py                 # Action 基类
│   ├── blank_action.py         # 空动作
│   └── report_action.py        # 报告动作
│
├── memory/                     # 内存模块
│   ├── base.py                 # Memory 基类
│   ├── short_term.py           # 短期记忆
│   ├── long_term.py            # 长期记忆
│   ├── agent_memory.py         # Agent 记忆
│   └── extract_memory.py       # 记忆提取
│
├── reasoning/                  # 推理模块
│   ├── reasoning_action.py     # 推理动作
│   └── reasoning_parser_v2.py  # 推理解析器
│
├── sandbox/                    # 沙箱模块
│   ├── __init__.py
│   ├── sandbox.py              # 沙箱实现
│   ├── sandbox_tool_registry.py # 沙箱工具注册
│   ├── prompt.py               # 沙箱提示
│   └── tools/                  # 沙箱工具集
│       ├── shell_tool.py       # Shell 工具
│       ├── view_tool.py        # 查看工具
│       ├── edit_file_tool.py   # 编辑文件工具
│       ├── create_file_tool.py # 创建文件工具
│       ├── download_file_tool.py # 下载文件工具
│       └── browser_tool.py     # 浏览器工具
│
├── profile/                    # 角色配置模块
│   ├── __init__.py
│   └── base.py                 # Profile 基类
│
├── tools/                      # 工具模块
│   └── read_file_tool.py       # 读文件工具
│
├── parsers/                    # 解析器模块
│
├── plan/                       # 规划模块
│
└── file_system/                # 文件系统模块
    └── file_tree.py            # 文件树结构
```

---

## 3. 核心模块功能

### 3.1 Agent 接口层 (`agent.py`)

**核心接口**:

```python
class Agent(ABC):
    """Agent 抽象基类，定义 Agent 通信协议"""
    
    @abstractmethod
    async def send(message, recipient, ...) -> Optional[AgentMessage]
        """向其他 Agent 发送消息"""
    
    @abstractmethod
    async def receive(message, sender, ...) -> None
        """接收来自其他 Agent 的消息"""
    
    @abstractmethod
    async def generate_reply(received_message, sender, ...) -> AgentMessage
        """基于接收消息生成回复"""
    
    @abstractmethod
    async def thinking(messages, reply_message_id, ...) -> Optional[AgentLLMOut]
        """思考和推理当前任务目标"""
    
    @abstractmethod
    async def act(message, sender, ...) -> List[ActionOutput]
        """基于 LLM 推理结果执行动作"""
    
    @abstractmethod
    async def verify(message, sender, ...) -> Tuple[bool, Optional[str]]
        """验证执行结果是否满足目标"""
```

**AgentContext 数据结构**:

```python
@dataclass
class AgentContext:
    conv_id: str                    # 会话ID
    conv_session_id: str            # 会话会话ID
    gpts_app_code: Optional[str]    # 应用代码
    agent_app_code: Optional[str]   # Agent ID
    language: Optional[str]         # 语言设置
    max_chat_round: int             # 最大对话轮数
    max_retry_round: int            # 最大重试轮数
    enable_vis_message: bool        # VIS 协议消息模式
    stream: bool                    # 流式输出
    incremental: bool               # 增量流式输出
```

### 3.2 ConversableAgent 核心实现 (`base_agent.py`)

**类继承关系**:
```
ConversableAgent(Role, Agent)
    ├── Role: 角色定义
    └── Agent: Agent 接口
```

**核心属性**:

```python
class ConversableAgent(Role, Agent):
    agent_context: Optional[AgentContext]    # Agent 上下文
    actions: List[Type[Action]]              # 可用动作列表
    resource: Optional[Resource]             # 资源绑定
    llm_config: Optional[LLMConfig]          # LLM 配置
    llm_client: Optional[AIWrapper]          # LLM 客户端
    
    # 权限与配置系统
    permission_ruleset: Optional[PermissionRuleset]  # 权限规则集
    agent_info: Optional[AgentInfo]                  # Agent 配置信息
    agent_mode: AgentMode                            # 运行模式
    
    # 运行时状态
    max_retry_count: int = 3
    max_steps: Optional[int]                         # 最大执行步数
    sandbox_manager: Optional[SandboxManager]        # 沙箱管理器
```

**核心流程 - generate_reply**:

```
generate_reply()
    │
    ├── 1. 推送事件: EventType.ChatStart
    │
    ├── 2. 初始化任务到 GptsMemory
    │
    └── 3. 主执行循环 (while not done and retry < max)
        │
        ├── 3.1 _generate_think_message()
        │       ├── 恢复模式检查
        │       ├── 加载模型消息上下文
        │       └── 调用 LLM 进行推理
        │
        ├── 3.2 act()
        │       ├── 解析推理结果
        │       ├── 执行 Action
        │       └── 返回 ActionOutput
        │
        ├── 3.3 verify()
        │       ├── 验证执行结果
        │       └── 返回 (passed, reason)
        │
        └── 3.4 后续处理
                ├── 写入记忆
                ├── 更新任务状态
                └── 循环控制
```

**权限检查方法**:

```python
def check_tool_permission(self, tool_name: str, command: Optional[str] = None) -> PermissionAction:
    """检查工具权限 - 返回 ASK/ALLOW/DENY"""
    if self.agent_info and self.agent_info.permission_ruleset:
        return self.agent_info.check_permission(tool_name, command)
    if self.permission_ruleset:
        return self.permission_ruleset.check(tool_name, command)
    return PermissionAction.ALLOW  # 默认允许
```

### 3.3 执行引擎 (`execution_engine.py`)

**核心组件**:

```python
class ExecutionEngine(Generic[T]):
    """简化版执行引擎，参考 OpenCode 的简单循环模式"""
    
    def __init__(
        self,
        max_steps: int = 10,
        timeout_seconds: Optional[float] = None,
        hooks: Optional[ExecutionHooks] = None,
        context_lifecycle: Optional[ContextLifecycleOrchestrator] = None,
    )
    
    async def execute(
        self,
        initial_input: Any,
        think_func: Callable,
        act_func: Callable,
        verify_func: Optional[Callable] = None,
        should_terminate: Optional[Callable] = None,
    ) -> ExecutionResult:
        """执行 Agent 循环"""
```

**执行步骤抽象**:

```python
@dataclass
class ExecutionStep:
    step_id: str
    step_type: str         # "thinking" / "action"
    content: Any
    status: ExecutionStatus
    start_time: float
    end_time: Optional[float]
    error: Optional[str]
    metadata: Dict[str, Any]
```

**Hooks 钩子系统**:

```python
class ExecutionHooks:
    _hooks: Dict[str, List[Callable]] = {
        "before_thinking": [],
        "after_thinking": [],
        "before_action": [],
        "after_action": [],
        "before_step": [],
        "after_step": [],
        "on_error": [],
        "on_complete": [],
        "before_skill_load": [],
        "after_skill_complete": [],
        "on_context_pressure": [],
    }
```

### 3.4 执行循环 (`execution/execution_loop.py`)

**执行状态管理**:

```python
class ExecutionState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"

@dataclass
class LoopContext:
    iteration: int = 0
    max_iterations: int = 10
    state: ExecutionState = ExecutionState.PENDING
    last_output: Optional[Any] = None
    should_terminate: bool = False
    
    def can_continue(self) -> bool:
        return (self.iteration < self.max_iterations 
                and self.state == ExecutionState.RUNNING 
                and not self.should_terminate)
```

**简化版执行循环**:

```python
class SimpleExecutionLoop:
    async def run(
        self,
        think_func: Callable,
        act_func: Callable,
        verify_func: Callable,
        should_continue_func: Optional[Callable] = None,
    ) -> Tuple[bool, ExecutionMetrics]:
        """执行 think -> act -> verify 循环"""
```

### 3.5 LLM 执行器 (`execution/llm_executor.py`)

**LLM 配置**:

```python
@dataclass
class LLMConfig:
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    stream: bool = True
    stop: Optional[List[str]] = None
```

**LLM 输出容器**:

```python
@dataclass
class LLMOutput:
    content: str
    thinking_content: Optional[str]    # 思维链内容
    model_name: Optional[str]
    tool_calls: Optional[List[Dict]]
    usage: Optional[Dict[str, int]]
    finish_reason: Optional[str]
```

### 3.6 提示系统 (`prompt_v2.py`)

**提示格式枚举**:

```python
class PromptFormat(str, Enum):
    JINJA2 = "jinja2"
    F_STRING = "f-string"
    MUSTACHE = "mustache"
    PLAIN = "plain"
```

**System Prompt 构建器**:

```python
class SystemPromptBuilder:
    def role(self, role: str) -> "SystemPromptBuilder"
    def goal(self, goal: str) -> "SystemPromptBuilder"
    def constraints(self, constraints: List[str]) -> "SystemPromptBuilder"
    def tools(self, tools: List[str]) -> "SystemPromptBuilder"
    def examples(self, examples: List[str]) -> "SystemPromptBuilder"
    def build(self) -> str
```

**Agent Profile 配置**:

```python
class AgentProfile(BaseModel):
    name: str
    role: str
    goal: Optional[str]
    constraints: List[str]
    examples: Optional[str]
    system_prompt: Optional[str]
    temperature: float = 0.5
    language: str = "zh"
    
    @classmethod
    def from_markdown(cls, content: str) -> "AgentProfile":
        """从 Markdown 解析（支持 YAML frontmatter）"""
    
    def build_system_prompt(self, tools, resources, **kwargs) -> str:
        """构建系统提示"""
```

### 3.7 简化版内存系统 (`simple_memory.py`)

**内存作用域**:

```python
class MemoryScope(str, Enum):
    GLOBAL = "global"     # 全局作用域
    SESSION = "session"   # 会话作用域
    TASK = "task"         # 任务作用域
```

**内存条目**:

```python
@dataclass
class MemoryEntry:
    content: str
    role: str
    timestamp: float
    metadata: Dict[str, Any]
    priority: MemoryPriority
    scope: MemoryScope
    entry_id: Optional[str]
    tokens: int
```

**简化版内存实现**:

```python
class SimpleMemory(BaseMemory):
    def __init__(self, max_entries: int = 10000)
    
    async def add(entry: MemoryEntry) -> str
    async def get(entry_id: str) -> Optional[MemoryEntry]
    async def search(query: str, limit: int, scope: MemoryScope) -> List[MemoryEntry]
    async def clear(scope: MemoryScope) -> int
```

### 3.8 技能系统 (`skill.py`)

**技能类型**:

```python
class SkillType(str, Enum):
    BUILTIN = "builtin"     # 内置技能
    CUSTOM = "custom"       # 自定义技能
    EXTERNAL = "external"   # 外部技能
    PLUGIN = "plugin"       # 插件技能
```

**技能基类**:

```python
class Skill(ABC):
    def __init__(self, metadata: Optional[SkillMetadata])
    
    @property
    def name(self) -> str
    @property
    def is_enabled(self) -> bool
    
    async def initialize(self) -> bool
    async def shutdown(self) -> None
    
    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any
```

**装饰器方式注册技能**:

```python
@skill("search")
async def search_web(query: str) -> List[str]:
    return ["result1", "result2"]
```

### 3.9 上下文生命周期管理 (`context_lifecycle/`)

**核心版本对比**:

| 版本 | 推荐度 | 特点 |
|------|--------|------|
| V2 SimpleContextManager | ★★★ | 加载新 Skill 自动压缩旧 Skill，无不可靠检测 |
| V1 ContextLifecycleOrchestrator | ★★ | 完整功能，支持槽位管理、淘汰策略 |

**V2 简化版管理器核心规则（参考 opencode）**:

```
1. 每次只允许一个活跃 Skill
2. 加载新 Skill 时，自动压缩前一个 Skill
3. Token 预算接近限制时，自动压缩最旧内容
```

**内容槽位**:

```python
class ContentType(str, Enum):
    SYSTEM = "system"
    SKILL = "skill"
    TOOL = "tool"
    RESOURCE = "resource"
    MEMORY = "memory"

@dataclass
class ContentSlot:
    id: str
    content_type: ContentType
    name: str
    content: str
    state: ContentState     # EMPTY / ACTIVE / COMPACTED / EVICTED
    token_count: int
    summary: Optional[str]
    key_results: List[str]
```

### 3.10 Agent 配置与权限系统 (`agent_info.py`)

**Agent 运行模式**:

```python
class AgentMode(str, Enum):
    PRIMARY = "primary"     # 主 Agent
    SUBAGENT = "subagent"   # 子 Agent
    ALL = "all"
```

**权限动作类型**:

```python
class PermissionAction(str, Enum):
    ASK = "ask"       # 需要用户确认
    ALLOW = "allow"   # 直接允许
    DENY = "deny"     # 拒绝执行
```

**权限规则**:

```python
@dataclass
class PermissionRule:
    action: PermissionAction    # ASK / ALLOW / DENY
    pattern: str                # 匹配模式（支持 fnmatch）
    permission: str             # 权限名称
    
    def matches(self, tool_name: str, command: Optional[str] = None) -> bool
```

**Agent 声明式配置**:

```python
class AgentInfo(BaseModel):
    name: str
    description: Optional[str]
    mode: AgentMode
    
    llm_model_config: Dict[str, Any]  # {provider_id, model_id}
    prompt: Optional[str]
    prompt_file: Optional[str]
    temperature: Optional[float]
    max_steps: Optional[int]
    
    tools: Dict[str, bool]            # {tool_name: true/false}
    permission: Dict[str, Any]        # 权限配置
    
    @classmethod
    def from_markdown(content: str) -> "AgentInfo"
    def check_permission(tool_name: str, command: Optional[str]) -> PermissionAction
```

### 3.11 Action 动作系统 (`action/base.py`)

**Action 输出模型**:

```python
class ActionOutput(BaseModel):
    content: str
    action_id: str
    name: Optional[str]
    is_exe_success: bool
    
    view: Optional[str]               # 给人看的信息
    model_view: Optional[str]         # 给模型看的信息
    
    action: Optional[str]
    action_input: Optional[Any]
    thoughts: Optional[str]
    observations: Optional[str]
    
    have_retry: bool = True
    ask_user: bool = False
    terminate: Optional[bool]         # 是否终止对话
```

**Action 基类**:

```python
class Action(ABC, Generic[T]):
    name: str  # 自动从类名推断
    
    def __init__(self, language: str = "en", name: Optional[str] = None)
    
    @property
    def resource_need(self) -> Optional[ResourceType]
    
    @classmethod
    def get_action_description(cls) -> str
    
    @abstractmethod
    async def run(
        self,
        ai_message: str = None,
        resource: Optional[Resource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        **kwargs,
    ) -> ActionOutput:
        """执行动作"""
```

### 3.12 Memory 记忆系统 (`memory/base.py`)

**记忆片段接口**:

```python
class MemoryFragment(ABC):
    @property
    @abstractmethod
    def id(self) -> int
    
    @property
    @abstractmethod
    def raw_observation(self) -> str
    
    @property
    def importance(self) -> Optional[float]
    
    @property
    @abstractmethod
    def is_insight(self) -> bool
```

**Memory 接口**:

```python
class Memory(ABC, Generic[T]):
    @abstractmethod
    async def write(memory_fragment: T, op: WriteOperation) -> Optional[DiscardedMemoryFragments]
    
    @abstractmethod
    async def read(
        observation: str,
        alpha: Optional[float],  # 新近性系数
        beta: Optional[float],   # 相关性系数
        gamma: Optional[float],  # 重要性系数
    ) -> List[T]
    
    async def reflect(memory_fragments: List[T]) -> List[T]
    async def get_insights(memory_fragments: List[T]) -> List[InsightMemoryFragment]
```

### 3.13 沙箱工具系统 (`sandbox/`)

**沙箱工具注册器**:

```python
sandbox_tool_dict: Dict[str, FunctionTool] = {}

@sandbox_tool(name=None, description=None, ask_user=False, stream=False)
def my_tool(...) -> Any:
    """装饰器方式注册沙箱工具"""
```

**沙箱工具列表**:

| 工具名 | 功能 |
|--------|------|
| `shell_tool` | Shell 命令执行 |
| `view_tool` | 查看文件内容 |
| `edit_file_tool` | 编辑文件 |
| `create_file_tool` | 创建文件 |
| `download_file_tool` | 下载文件 |
| `browser_tool` | 浏览器导航 |

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
│                         Agent Layer (Agent 层)                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    ConversableAgent                              │   │
│  │  - send() / receive()                                            │   │
│  │  - generate_reply()                                              │   │
│  │  - thinking() / act() / verify()                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ AgentInfo   │  │ Permission  │  │ AgentProfile│  │ Role        │    │
│  │ (声明式配置) │  │ (权限控制)  │  │ (角色配置)  │  │ (角色定义)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Execution Layer (执行层)                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    ExecutionEngine                               │   │
│  │  - execute(think_func, act_func, verify_func)                   │   │
│  │  - Hooks: before/after thinking/action                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │ ExecutionLoop   │  │ LLMExecutor     │  │ ContextLifecycle │         │
│  │ (执行循环)      │  │ (LLM调用)       │  │ (上下文管理)     │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Module Layer (模块层)                              │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Memory      │  │ Skill       │  │ Prompt      │  │ Profile     │    │
│  │ (记忆系统)  │  │ (技能系统)  │  │ (提示系统)  │  │ (角色配置)  │    │
│  │             │  │             │  │             │  │             │    │
│  │ - Sensory   │  │ - Registry  │  │ - Template  │  │ - Profile   │    │
│  │ - ShortTerm │  │ - Manager   │  │ - Builder   │  │ - Config    │    │
│  │ - LongTerm  │  │ - Function  │  │ - Variables │  │             │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ Action      │  │ Reasoning   │  │ Context     │  │ Sandbox     │    │
│  │ (动作系统)  │  │ (推理系统)  │  │ (上下文)    │  │ (沙箱)      │    │
│  │             │  │             │  │             │  │             │    │
│  │ - Base      │  │ - Parser    │  │ - Lifecycle │  │ - Tools     │    │
│  │ - Output    │  │ - Engine    │  │ - Manager   │  │ - Registry  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Infrastructure Layer (基础设施层)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ LLM Client  │  │ Storage     │  │ Tracer      │  │ Event       │    │
│  │ (模型调用)  │  │ (持久化)    │  │ (链路追踪)  │  │ (事件系统)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 四大模块架构（基于论文）

```
                        ┌─────────────────────────────────────┐
                        │         Autonomous Agent            │
                        └─────────────────────────────────────┘
                                          │
        ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
        │                 │               │               │                 │
        ▼                 ▼               ▼               ▼                 │
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐   │
│   Profiling   │ │    Memory     │ │   Planning    │ │    Action     │   │
│    Module     │ │    Module     │ │    Module     │ │    Module     │   │
├───────────────┤ ├───────────────┤ ├───────────────┤ ├───────────────┤   │
│ - Role        │ │ - Sensory     │ │ - Reasoning   │ │ - Base Action │   │
│ - Profile     │ │ - ShortTerm   │ │ - Execution   │ │ - ActionOutput│   │
│ - AgentInfo   │ │ - LongTerm    │ │   Loop        │ │ - Tools       │   │
│ - Permission  │ │ - GptsMemory  │ │ - Skill       │ │ - Sandbox     │   │
│               │ │ - SimpleMemory│ │   Manager     │ │               │   │
└───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘   │
        │                 │               │               │                 │
        └─────────────────┴───────────────┼───────────────┴─────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────────┐
                        │         Environment / LLM           │
                        └─────────────────────────────────────┘
```

---

## 5. 数据流

### 5.1 Agent 消息处理流程

```
User Input
    │
    ▼
┌─────────────────────┐
│    UserProxyAgent   │
│    (用户代理)       │
└─────────────────────┘
    │ send(message)
    ▼
┌─────────────────────┐
│  ConversableAgent   │
│    receive()        │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  generate_reply()   │
│                     │
│  ┌───────────────┐  │
│  │ Loop Start    │  │
│  └───────────────┘  │
│         │           │
│         ▼           │
│  ┌───────────────┐  │
│  │ thinking()    │  │◄─── LLM 调用
│  │ (推理)        │  │
│  └───────────────┘  │
│         │           │
│         ▼           │
│  ┌───────────────┐  │
│  │ act()         │  │◄─── Action 执行
│  │ (执行)        │  │
│  └───────────────┘  │
│         │           │
│         ▼           │
│  ┌───────────────┐  │
│  │ verify()      │  │◄─── 结果验证
│  │ (验证)        │  │
│  └───────────────┘  │
│         │           │
│    ┌────┴────┐      │
│    │         │      │
│    ▼         ▼      │
│ [成功]    [失败]    │
│    │         │      │
│    │    ┌────┘      │
│    │    ▼           │
│    │ [retry/recover]│
│    │    │           │
│    └────┴────┐      │
│              ▼      │
│  ┌───────────────┐  │
│  │ Loop End      │  │
│  └───────────────┘  │
└─────────────────────┘
    │
    ▼
AgentMessage (reply)
```

### 5.2 执行引擎数据流

```
Initial Input
    │
    ▼
┌───────────────────────────────────────────────────────┐
│                   ExecutionEngine                      │
│                                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │              Execution Loop                      │  │
│  │                                                  │  │
│  │   while step < max_steps:                        │  │
│  │       │                                          │  │
│  │       ├─► emit("before_step")                   │  │
│  │       │                                          │  │
│  │       ├─► ExecutionStep(thinking)               │  │
│  │       │       │                                  │  │
│  │       │       ├─► emit("before_thinking")       │  │
│  │       │       ├─► think_func(input)             │  │
│  │       │       └─► emit("after_thinking")        │  │
│  │       │                                          │  │
│  │       ├─► ExecutionStep(action)                 │  │
│  │       │       │                                  │  │
│  │       │       ├─► emit("before_action")         │  │
│  │       │       ├─► act_func(thinking_result)     │  │
│  │       │       └─► emit("after_action")          │  │
│  │       │                                          │  │
│  │       ├─► verify_func(result)                   │  │
│  │       │                                          │  │
│  │       └─► should_terminate? ──► break           │  │
│  │                                                  │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │           Context Lifecycle Manager              │  │
│  │                                                  │  │
│  │   - prepare_skill()  ──► load skill content     │  │
│  │   - check_pressure() ──► auto compact           │  │
│  │   - complete_skill() ──► compress & exit        │  │
│  │                                                  │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
└───────────────────────────────────────────────────────┘
    │
    ▼
ExecutionResult
```

### 5.3 上下文生命周期数据流

```
  Skill A Requested
        │
        ▼
  ┌─────────────────┐
  │ check token     │
  │ budget          │
  └─────────────────┘
        │
        ├─── pressure > 0.9? ──► auto_compact()
        │
        ▼
  ┌─────────────────┐
  │ load skill A    │
  │ content         │
  └─────────────────┘
        │
        ▼
  Skill B Requested
        │
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │               AUTO COMPACT Skill A                      │
  │                                                          │
  │   Skill A (full content)                                │
  │       │                                                  │
  │       ▼                                                  │
  │   ┌─────────────────────────────────────────┐           │
  │   │ <skill-result name="skill_a">           │           │
  │   │   <summary>Task completed...</summary>  │           │
  │   │   <key-results>...</key-results>        │           │
  │   │ </skill-result>                         │           │
  │   └─────────────────────────────────────────┘           │
  │                                                          │
  │   Tokens freed: skill_a.full - skill_a.summary          │
  └─────────────────────────────────────────────────────────┘
        │
        ▼
  build_context_for_llm(user_message)
        │
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    LLM Messages                          │
  │                                                          │
  │   [                                                       │
  │     { "role": "system", "content": "<system_prompt>" },  │
  │     { "role": "system", "content": "<previous_skills>" },│
  │     { "role": "system", "content": "<current_skill>" },  │
  │     { "role": "system", "content": "<tools>" },          │
  │     { "role": "user", "content": "<user_message>" }      │
  │   ]                                                       │
  └─────────────────────────────────────────────────────────┘
```

### 5.4 Memory 数据流

```
                    ┌─────────────────────────────────────┐
                    │           Environment               │
                    └─────────────────────────────────────┘
                                      │
                                      │ Observation
                                      ▼
                    ┌─────────────────────────────────────┐
                    │        Sensory Memory               │
                    │   (Temporary buffer, threshold)     │
                    └─────────────────────────────────────┘
                                      │
                                      │ importance > threshold
                                      ▼
                    ┌─────────────────────────────────────┐
                    │        Short-Term Memory            │
                    │   (Limited buffer, recent items)    │
                    └─────────────────────────────────────┘
                                      │
                                      │ overflow / time decay
                                      ▼
                    ┌─────────────────────────────────────┐
                    │        Long-Term Memory             │
                    │   (Persistent storage, indexed)     │
                    │                                      │
                    │   Write:                             │
                    │   - store fragment                   │
                    │   - calculate importance             │
                    │   - extract insights                 │
                    │                                      │
                    │   Read:                              │
                    │   - α × recency(q, m)               │
                    │   - β × relevance(q, m)             │
                    │   - γ × importance(m)               │
                    └─────────────────────────────────────┘
```

---

## 6. 关键设计模式

### 6.1 策略模式 - Permission 权限检查

```python
class PermissionRuleset:
    def check(self, tool_name: str, command: Optional[str] = None) -> PermissionAction:
        result = PermissionAction.ASK  # default strategy
        for rule in self._rules:
            if rule.matches(tool_name, command):
                result = rule.action  # rule-specific strategy
        return result
```

### 6.2 模板方法模式 - Agent 执行流程

```python
class Agent(ABC):
    @abstractmethod
    async def thinking(...)  # 子类实现
    @abstractmethod
    async def act(...)       # 子类实现
    @abstractmethod
    async def verify(...)    # 子类实现

class ConversableAgent(Agent):
    async def generate_reply(...):
        # 模板方法定义执行骨架
        while not done:
            thinking_result = await self.thinking(...)
            action_result = await self.act(thinking_result, ...)
            passed = await self.verify(action_result, ...)
```

### 6.3 观察者模式 - ExecutionHooks 事件系统

```python
class ExecutionHooks:
    _hooks: Dict[str, List[Callable]] = {
        "before_thinking": [],
        "after_thinking": [],
        "on_error": [],
        ...
    }
    
    def on(self, event: str, handler: Callable):
        self._hooks[event].append(handler)
    
    async def emit(self, event: str, *args, **kwargs):
        for handler in self._hooks[event]:
            await handler(*args, **kwargs)
```

### 6.4 单例模式 - SkillRegistry, AgentRegistry, ToolRegistry

```python
class SkillRegistry:
    _instance: Optional["SkillRegistry"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

### 6.5 装饰器模式 - 工具和技能注册

```python
@skill("search")
async def search_web(query: str) -> List[str]:
    return ["result1", "result2"]

@tool("read")
async def read_file(path: str) -> str:
    return "file content"

@sandbox_tool(name="shell")
async def execute_shell(cmd: str) -> str:
    return "output"
```

### 6.6 建造者模式 - SystemPromptBuilder

```python
prompt = (SystemPromptBuilder()
    .role("expert coder")
    .goal("write clean code")
    .constraints(["follow PEP8", "add docstrings"])
    .tools(["read", "write", "bash"])
    .build())
```

### 6.7 工厂方法模式

```python
def create_execution_context(max_iterations: int = 10, **kwargs) -> ExecutionContext
def create_execution_loop(max_iterations: int = 10, **kwargs) -> SimpleExecutionLoop
def create_llm_config(model: str, ...) -> LLMConfig
def create_llm_executor(llm_client: Any, ...) -> LLMExecutor
def create_memory(max_entries: int = 10000, ...) -> MemoryManager
def create_skill_registry() -> SkillRegistry
def create_context_lifecycle(...) -> ContextLifecycleOrchestrator
```

### 6.8 责任链模式 - Permission 规则检查

```python
for rule in self._rules:  # 规则链
    if rule.matches(tool_name, command):
        result = rule.action  # 最后一个匹配的规则生效
```

---

## 7. 扩展开发指南

### 7.1 扩展新 Agent

```python
from derisk.agent.core import ConversableAgent, AgentInfo, AgentMode

class MyCustomAgent(ConversableAgent):
    """自定义 Agent 实现"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    async def thinking(self, messages, reply_message_id, **kwargs):
        """重写推理逻辑"""
        return await super().thinking(messages, reply_message_id, **kwargs)
    
    async def act(self, message, sender, **kwargs):
        """重写动作执行"""
        return await super().act(message, sender, **kwargs)
    
    async def verify(self, message, sender, **kwargs):
        """重写验证逻辑"""
        return await super().verify(message, sender, **kwargs)

# 使用 AgentInfo 声明式配置
agent_info = AgentInfo(
    name="my-agent",
    description="My custom agent",
    mode=AgentMode.PRIMARY,
    temperature=0.7,
    max_steps=20,
    tools={"write": True, "bash": True},
    permission={"*": "allow", "dangerous_tool": "ask"},
)
```

### 7.2 扩展新 Action

```python
from derisk.agent.core.action.base import Action, ActionOutput
from pydantic import BaseModel, Field

class MyActionInput(BaseModel):
    query: str = Field(..., description="查询内容")
    
class MyAction(Action[MyActionInput]):
    """自定义 Action"""
    name = "MyAction"
    
    @property
    def resource_need(self) -> Optional[ResourceType]:
        return ResourceType.KnowledgePack
    
    async def run(
        self,
        ai_message: str = None,
        resource: Optional[Resource] = None,
        rely_action_out: Optional[ActionOutput] = None,
        **kwargs,
    ) -> ActionOutput:
        action_input = MyActionInput.model_validate_json(ai_message)
        
        try:
            result = await self._do_something(action_input, resource)
            return ActionOutput(
                content=result,
                is_exe_success=True,
                name=self.name,
            )
        except Exception as e:
            return ActionOutput(
                content=str(e),
                is_exe_success=False,
                name=self.name,
            )
    
    async def _do_something(self, action_input, resource):
        return "result"
```

### 7.3 扩展新 Skill

```python
from derisk.agent.core.skill import Skill, SkillMetadata, SkillType, skill

# 方式1：类继承
class MySkill(Skill):
    def __init__(self):
        super().__init__(
            metadata=SkillMetadata(
                name="my_skill",
                description="My custom skill",
                skill_type=SkillType.CUSTOM,
            )
        )
    
    async def _do_initialize(self) -> bool:
        return True
    
    async def execute(self, *args, **kwargs) -> Any:
        return await self._run_skill(*args, **kwargs)

# 方式2：装饰器
@skill("my_function_skill", description="A function-based skill")
async def my_function_skill(param: str) -> str:
    return f"Processed: {param}"
```

### 7.4 扩展新 Memory

```python
from derisk.agent.core.memory.base import Memory, MemoryFragment

class MyMemoryFragment(MemoryFragment):
    def __init__(self, observation: str, memory_id: int):
        self._observation = observation
        self._id = memory_id
    
    @property
    def id(self) -> int:
        return self._id
    
    @property
    def raw_observation(self) -> str:
        return self._observation

class MyMemory(Memory[MyMemoryFragment]):
    async def write(self, fragment: MyMemoryFragment, **kwargs):
        pass
    
    async def read(self, observation: str, alpha, beta, gamma) -> List[MyMemoryFragment]:
        pass
    
    async def clear(self) -> List[MyMemoryFragment]:
        pass
```

### 7.5 扩展新工具

```python
# 系统工具
from derisk.agent.core.system_tool_registry import system_tool_dict
from derisk.agent.resource.tool.base import FunctionTool

async def my_tool_func(param: str) -> str:
    return "result"

my_tool = FunctionTool(
    name="my_tool",
    func=my_tool_func,
    description="My custom tool",
)
system_tool_dict["my_tool"] = my_tool

# 沙箱工具
from derisk.agent.core.sandbox.sandbox_tool_registry import sandbox_tool

@sandbox_tool(name="my_sandbox_tool", description="My sandbox tool")
async def my_sandbox_tool(path: str) -> str:
    return "sandbox result"
```

### 7.6 扩展新权限规则

```python
from derisk.agent.core.agent_info import PermissionRule, PermissionAction, PermissionRuleset

# 创建自定义规则集
ruleset = PermissionRuleset([
    PermissionRule(action=PermissionAction.ALLOW, pattern="read_*", permission="read"),
    PermissionRule(action=PermissionAction.ASK, pattern="write_*", permission="write"),
    PermissionRule(action=PermissionAction.DENY, pattern="delete_*", permission="delete"),
    PermissionRule(action=PermissionAction.ALLOW, pattern="*", permission="*"),
])

# 或从配置创建
ruleset = PermissionRuleset.from_config({
    "*": "ask",
    "read": "allow",
    "write": {"sensitive_file": "deny"},
    "bash": {"rm_*": "deny", "*": "ask"},
})

# 应用到 Agent
agent = ConversableAgent(permission_ruleset=ruleset)
```

### 7.7 扩展执行钩子

```python
from derisk.agent.core.execution_engine import ExecutionHooks

hooks = ExecutionHooks()

@hooks.on("before_thinking")
async def log_thinking(step, input_data):
    print(f"Starting thinking at step {step}")

@hooks.on("after_action")
async def log_action(step, result):
    print(f"Action completed at step {step}: {result}")

@hooks.on("on_error")
async def handle_error(error):
    print(f"Error occurred: {error}")

@hooks.on("on_context_pressure")
async def handle_pressure(pressure):
    print(f"Context pressure high: {pressure:.2%}")

# 使用钩子创建执行引擎
engine = ExecutionEngine(hooks=hooks)
```

---

## 8. 使用示例

### 8.1 创建简单 Agent

```python
from derisk.agent.core import (
    ConversableAgent,
    AgentContext,
    AgentInfo,
    AgentMode,
    create_memory,
)

# 创建 Agent 上下文
agent_context = AgentContext(
    conv_id="conv_001",
    conv_session_id="session_001",
    gpts_app_code="my_app",
    agent_app_code="my_agent",
    language="zh",
    stream=True,
)

# 创建 Agent 配置
agent_info = AgentInfo(
    name="assistant",
    description="A helpful assistant",
    mode=AgentMode.PRIMARY,
    temperature=0.7,
    max_steps=10,
)

# 创建 Agent
agent = ConversableAgent(
    agent_context=agent_context,
    agent_info=agent_info,
)
await agent.build()
```

### 8.2 使用 AgentInfo 声明式配置

```python
# Markdown 格式配置
agent_config = """
---
name: code-reviewer
description: Reviews code for quality issues
mode: subagent
temperature: 0.3
max_steps: 5
tools:
  write: false
  edit: false
permission:
  "*": "ask"
  read: "allow"
  grep: "allow"
---

You are an expert code reviewer. Your task is to analyze code and identify:
1. Potential bugs
2. Security vulnerabilities
3. Code style issues
4. Performance concerns

Always provide constructive feedback with specific suggestions.
"""

from derisk.agent.core import AgentInfo
agent_info = AgentInfo.from_markdown(agent_config)
```

### 8.3 使用简化版执行循环

```python
from derisk.agent.core.execution import (
    create_execution_loop,
    create_execution_context,
)

loop = create_execution_loop(max_iterations=10)

async def think(ctx):
    return "thinking result"

async def act(thought, ctx):
    return "action result"

async def verify(result, ctx):
    return True

success, metrics = await loop.run(
    think_func=think,
    act_func=act,
    verify_func=verify,
)

print(f"Success: {success}")
print(f"Duration: {metrics.duration_ms}ms")
print(f"Iterations: {metrics.total_iterations}")
```

### 8.4 使用上下文生命周期管理

```python
from derisk.agent.core.context_lifecycle import AgentContextIntegration

integration = AgentContextIntegration(
    token_budget=50000,
    auto_compact_threshold=0.9,
)

await integration.initialize(
    session_id="session_001",
    system_prompt="You are a helpful coding assistant.",
)

# 准备 Skill
result = await integration.prepare_skill(
    skill_name="code_analysis",
    skill_content="# Code Analysis Skill...",
    required_tools=["read", "grep"],
)

# 构建消息
messages = integration.build_messages(
    user_message="分析 src/main.py 文件",
)

# Skill 执行完毕
await integration.complete_skill(
    summary="分析了 src/main.py，发现 3 个问题",
    key_results=["缺少错误处理", "未使用的导入", "硬编码配置"],
)
```

### 8.5 完整 Agent 示例

```python
import asyncio
from derisk.agent.core import (
    ConversableAgent,
    AgentContext,
    AgentInfo,
    AgentMode,
    PermissionRuleset,
    PermissionRule,
    PermissionAction,
    create_memory,
)
from derisk.agent.core.execution import create_execution_loop
from derisk.agent.core.context_lifecycle import AgentContextIntegration

async def main():
    # 1. 创建权限规则
    permission = PermissionRuleset([
        PermissionRule(action=PermissionAction.ALLOW, pattern="read_*", permission="read"),
        PermissionRule(action=PermissionAction.ASK, pattern="write_*", permission="write"),
        PermissionRule(action=PermissionAction.DENY, pattern="delete_*", permission="delete"),
    ])
    
    # 2. 创建 Agent 配置
    agent_info = AgentInfo(
        name="code-assistant",
        description="A helpful coding assistant",
        mode=AgentMode.PRIMARY,
        temperature=0.5,
        max_steps=20,
        tools={
            "read": True,
            "write": True,
            "bash": True,
            "grep": True,
        },
        permission={
            "*": "ask",
            "read": "allow",
            "grep": "allow",
        },
    )
    
    # 3. 创建上下文
    agent_context = AgentContext(
        conv_id="conv_001",
        conv_session_id="session_001",
        gpts_app_code="my_app",
        agent_app_code="code_assistant",
        language="zh",
        stream=True,
    )
    
    # 4. 创建内存
    memory = create_memory(max_entries=10000)
    
    # 5. 创建上下文生命周期管理
    context_integration = AgentContextIntegration(
        token_budget=100000,
        auto_compact_threshold=0.9,
    )
    
    # 6. 创建 Agent
    agent = ConversableAgent(
        agent_context=agent_context,
        agent_info=agent_info,
        permission_ruleset=permission,
    )
    
    # 7. 构建 Agent
    await agent.build()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9. 用户交互系统

### 9.1 概述

Core V1 新增完整的用户交互能力，支持：
- **Agent 主动提问**：任务执行中主动向用户获取信息
- **工具授权请求**：敏感操作前请求用户确认
- **方案选择**：提供多个方案供用户选择
- **中断恢复**：任意点中断后完美恢复所有上下文

### 9.2 核心组件

```
packages/derisk-core/src/derisk/agent/
├── interaction/                    # 交互系统模块
│   ├── __init__.py
│   ├── interaction_protocol.py    # 交互协议定义
│   ├── interaction_gateway.py     # 交互网关
│   └── recovery_coordinator.py    # 恢复协调器
│
└── core/
    └── interaction_adapter.py     # Core V1 交互适配器
```

### 9.3 InteractionAdapter 使用

```python
from derisk.agent.core import ConversableAgent, InteractionAdapter

agent = ConversableAgent(...)
adapter = InteractionAdapter(agent)

# 主动提问
answer = await adapter.ask("请提供数据库连接信息")

# 确认操作
confirmed = await adapter.confirm("确定要删除这个文件吗？")

# 选择方案
plan = await adapter.choose_plan([
    {"id": "fast", "name": "快速实现", "pros": ["快"], "cons": ["不完整"]},
    {"id": "full", "name": "完整实现", "pros": ["完整"], "cons": ["耗时"]},
])

# 工具授权
authorized = await adapter.request_tool_permission(
    "bash", 
    {"command": "rm -rf /data"}
)

# 通知
await adapter.notify_success("任务完成")
await adapter.notify_progress("正在处理...", progress=0.5)
```

### 9.4 中断恢复机制

```python
# 创建检查点
checkpoint_id = await recovery_coordinator.create_checkpoint(
    session_id="session_001",
    execution_id="exec_001",
    step_index=15,
    phase="waiting_interaction",
    context={},
    agent=agent,
)

# 恢复执行
result = await recovery_coordinator.recover(
    session_id="session_001",
    resume_mode="continue",  # continue / skip / restart
)

if result.success:
    print(result.summary)
    # 恢复上下文
    conversation_history = result.recovery_context.conversation_history
    todo_list = result.recovery_context.todo_list
```

### 9.5 Todo 管理

```python
# 创建 Todo
todo_id = await adapter.create_todo("实现用户登录功能", priority=1)

# 更新状态
await adapter.update_todo(todo_id, status="in_progress")
await adapter.update_todo(todo_id, status="completed", result="登录功能已完成")

# 获取进度
completed, total = adapter.get_progress()
```

### 9.6 交互类型

| 类型 | 描述 | 使用场景 |
|------|------|----------|
| `ASK` | 开放式问题 | 请求用户提供信息 |
| `CONFIRM` | 是/否确认 | 确认操作 |
| `SELECT` | 单选 | 选择配置项 |
| `AUTHORIZE` | 工具授权 | 敏感操作前确认 |
| `CHOOSE_PLAN` | 方案选择 | 多种实现方案 |
| `NOTIFY` | 通知 | 进度更新 |

---

## 10. Shared Infrastructure (共享基础设施)

### 10.1 概述

Core V1 与 Core V2 共享一套基础设施层，遵循**统一资源平面**设计原则：

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

# Skill 退出时归档
await archiver.archive_skill_content(
    skill_name="code_analysis",
    content=skill_full_content,
    summary="完成了代码分析",
    key_results=["发现3个问题", "建议优化点2处"],
)

# 上下文压力时自动归档
archived = await archiver.auto_archive_for_pressure(
    current_tokens=90000,
    budget_tokens=100000,
)
```

#### TaskBoardManager - 任务看板管理器

```python
from derisk.agent.shared import TaskBoardManager, TaskStatus, TaskPriority

# Todo 模式（简单任务）
task = await manager.create_todo(
    title="分析数据文件",
    description="读取并分析 data.csv",
    priority=TaskPriority.HIGH,
)
await manager.update_todo_status(task.id, TaskStatus.WORKING)
await manager.update_todo_status(task.id, TaskStatus.COMPLETED)

# 获取下一个待处理任务
next_task = await manager.get_next_pending_todo()

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

# 获取状态报告
report = await manager.get_status_report()
```

### 10.3 V1ContextAdapter - Core V1 适配器

```python
from derisk.agent.shared import SharedSessionContext, V1ContextAdapter

# 创建共享上下文
shared_ctx = await SharedSessionContext.create(
    session_id="session_001",
    conv_id="conv_001",
)

# 创建适配器
adapter = V1ContextAdapter(shared_ctx)

# 集成到 ConversableAgent
agent = ConversableAgent(agent_info=agent_info)
await adapter.integrate_with_agent(
    agent,
    enable_truncation=True,
    max_output_chars=8000,
)

# Agent 执行过程中自动享受：
# - 工具输出自动归档
# - Todo/Kanban 任务管理
# - 统一文件管理
```

### 10.4 提供的工具

通过 `V1ContextAdapter.get_tool_definitions()` 可以获取以下工具：

| 工具 | 描述 |
|------|------|
| `create_todo` | 创建 Todo 任务项 |
| `update_todo` | 更新 Todo 状态 |
| `create_kanban` | 创建 Kanban 看板 |
| `submit_deliverable` | 提交阶段交付物 |

### 10.5 与现有组件的关系

| 原有组件 | 共享组件 | 说明 |
|---------|---------|------|
| `AgentFileSystem` | `SharedSessionContext.file_system` | 统一文件管理 |
| `KanbanManager` | `TaskBoardManager` | 合并 Todo 和 Kanban |
| `Truncator` | `ContextArchiver` | 扩展为通用归档器 |
| `WorkLogManager` | `TaskBoardManager` | 任务追踪统一管理 |

### 10.6 最佳实践

1. **会话开始时创建 SharedSessionContext**
2. **使用适配器集成到具体架构**
3. **长任务启用 Kanban 模式**
4. **工具输出超过阈值自动归档**
5. **会话结束时调用 close() 清理资源**

---

## 11. 与 Core V2 对比

| 特性 | Core V1 | Core V2 |
|------|---------|---------|
| **设计理念** | 四模块架构（学术论文） | 配置驱动 + 钩子系统 |
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

## 附录：核心类关系图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Class Relationships                             │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │     Agent        │ (Interface)
                              │    (ABC)         │
                              └────────┬─────────┘
                                       │
                                       │ implements
                                       │
                              ┌────────▼─────────┐
                              │ ConversableAgent │
                              │                  │
                              │ - agent_context  │
                              │ - agent_info     │
                              │ - llm_config     │
                              │ - memory         │
                              └────────┬─────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           │ uses                      │ uses                      │ uses
           │                           │                           │
           ▼                           ▼                           ▼
   ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
   │   AgentInfo   │          │  LLMConfig    │          │ AgentMemory   │
   │               │          │               │          │               │
   │ - name        │          │ - model       │          │ - gpts_memory │
   │ - mode        │          │ - temperature │          │ - sensory     │
   │ - permission  │          │ - max_tokens  │          │ - short_term  │
   │ - tools       │          │               │          │ - long_term   │
   └───────┬───────┘          └───────────────┘          └───────────────┘
           │
           │ contains
           │
           ▼
   ┌───────────────┐
   │ Permission    │
   │ Ruleset       │
   │               │
   │ - rules[]     │
   │ - check()     │
   └───────────────┘
```

---

**文档版本**: v1.1  
**最后更新**: 2026-02-27  
**参考资料**: 
- [A Survey on Large Language Model Based Autonomous Agents](https://link.springer.com/article/10.1007/s11704-024-40231-1)
- OpenCode/OpenClaw 设计模式
- Shared Infrastructure 设计文档