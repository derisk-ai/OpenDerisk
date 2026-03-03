# Derisk Core V1 Agent 架构文档

> 最后更新: 2026-03-03
> 状态: 已实现，正在向 V2 迁移

## 一、架构概览

### 1.1 设计理念

Core V1 Agent 基于 **消息传递** 模型设计，核心概念包括：
- **ConversableAgent**: 可对话的智能体
- **消息循环**: send → receive → generate_reply
- **混合执行**: 同步思考 + 异步动作执行

### 1.2 核心架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Core V1 Agent 架构                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │                      Agent Layer                                 │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │ Agent (合约) │───>│ Role (角色)  │───>│Conversable   │      │    │
│   │  │   (ABC)      │    │  (Pydantic)  │    │Agent (核心)  │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                          Memory Layer                            │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │ AgentMemory  │───>│ GptsMemory   │───>│Conversation  │      │    │
│   │  │ (代理层)      │    │ (核心存储)    │    │Cache (会话)  │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                         Action Layer                             │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │ Action (抽象)│───>│ActionOutput  │───>│ Tool System  │      │    │
│   │  │              │    │   (结果)      │    │  (工具调用)   │      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                      │
│   ┌────────────────────────────────┼────────────────────────────────┐    │
│   │                           LLM Layer                              │    │
│   │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │    │
│   │  │ AIWrapper    │───>│LLMClient     │───>│ LLMProvider  │      │    │
│   │  │ (调用封装)    │    │ (旧版客户端)  │    │ (新版Provider)│      │    │
│   │  └──────────────┘    └──────────────┘    └──────────────┘      │    │
│   └─────────────────────────────────────────────────────────────────┘    │
│                                                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 二、分层模块定义

### 2.1 目录结构

```
packages/derisk-core/src/derisk/agent/core/
├── agent.py                 # Agent 抽象接口定义
├── base_agent.py            # ConversableAgent 核心实现 (108KB, 2600+ 行)
├── role.py                  # Role 基类 (16KB)
├── schema.py                # 数据模型定义
├── types.py                 # 消息类型定义
│
├── profile/                 # Agent 配置模板
│   ├── base.py             # Profile 抽象及 ProfileConfig
│   └── ...
│
├── memory/                  # 记忆系统
│   ├── agent_memory.py     # AgentMemory 代理记忆
│   ├── base.py             # 记忆存储接口
│   └── gpts/               # GptsMemory 实现
│       ├── gpts_memory.py  # 核心记忆管理 (250+ 行)
│       ├── base.py         # 消息/计划存储接口
│       └── default_*.py    # 默认存储实现
│
├── action/                  # Action 系统
│   ├── base.py             # Action 抽象基类
│   └── ...
│
├── context_lifecycle/       # 上下文生命周期管理
├── execution/               # 执行引擎
└── execution_engine.py      # 执行引擎实现
```

### 2.2 Agent 层

#### 2.2.1 Agent 接口 (`agent.py:18-86`)

```python
class Agent(ABC):
    """Agent Interface - 定义了Agent的核心生命周期方法"""

    # 核心通信方法
    async def send(self, message, recipient, ...)      # 发送消息
    async def receive(self, message, sender, ...)      # 接收消息
    async def generate_reply(self, ...) -> AgentMessage  # 生成回复

    # 思考与执行
    async def thinking(self, messages, ...) -> Optional[AgentLLMOut]  # LLM推理
    async def act(self, message, ...) -> List[ActionOutput]  # 执行动作
    async def verify(self, ...) -> Tuple[bool, Optional[str]]  # 验证结果
    async def review(self, message, censored) -> Tuple[bool, Any]  # 内容审查
```

#### 2.2.2 Role 类 (`role.py:30-220`)

```python
class Role(ABC, BaseModel):
    """Role class for role-based conversation"""

    profile: ProfileConfig          # 角色配置（名称、目标、约束等）
    memory: AgentMemory             # 记忆管理
    scheduler: Optional[Scheduler]  # 调度器
    language: str = "zh"            # 语言
    is_human: bool = False          # 是否人类
    is_team: bool = False           # 是否团队

    # Prompt构建方法
    async def build_prompt(self, is_system=True, resource_vars=None, ...)
    def prompt_template(self, prompt_type="system", ...) -> Tuple[str, str]
```

#### 2.2.3 ConversableAgent 核心属性 (`base_agent.py:100-200`)

```python
class ConversableAgent(Role, Agent):
    # 运行时上下文
    agent_context: Optional[AgentContext]    # Agent上下文
    actions: List[Type[Action]]              # 可用Action列表
    llm_config: Optional[LLMConfig]          # LLM配置
    llm_client: Optional[AIWrapper]          # LLM客户端包装

    # 资源管理
    resource: Optional[Resource]             # 资源
    resource_map: Dict[str, List[Resource]]  # 资源分类映射

    # 权限系统
    permission_ruleset: Optional[PermissionRuleset]
    agent_info: Optional[AgentInfo]

    # 系统工具
    available_system_tools: Dict[str, Any]   # 可用系统工具

    # 运行时控制
    max_retry_count: int = 3                 # 最大重试次数
    stream_out: bool = True                  # 是否流式输出
    enable_function_call: bool = False       # 是否启用Function Call
    sandbox_manager: Optional[SandboxManager]  # 沙箱管理
```

### 2.3 Memory 层

#### 2.3.1 记忆层次结构

```
┌─────────────────────────────────────────────────────────────┐
│                     AgentMemory                             │
│              (Agent级别的记忆管理)                          │
└──────────────────┬──────────────────────────────────────────┘
                   │
        +----------+----------+
        |                     │
┌───────v────────┐   ┌────────v──────────┐
│ ShortTermMemory │   │   GptsMemory      │
│ (会话短期记忆)  │   │  (持久化存储)     │
└─────────────────┘   └────────┬──────────┘
                               │
         +---------------------+---------------------+
         |                     |                     │
┌────────v────────┐  ┌────────v────────┐  ┌────────v────────┐
│ GptsMessageMemory│  │ GptsPlansMemory  │  │  ConversationCache │
│ (消息存储)       │  │ (计划存储)       │  │  (会话缓存)        │
└──────────────────┘  └─────────────────┘  └──────────────────┘
```

#### 2.3.2 GptsMemory 核心接口 (`memory/gpts/gpts_memory.py`)

```python
class GptsMemory(FileMetadataStorage, WorkLogStorage, KanbanStorage, TodoStorage):
    """会话全局消息记忆管理"""

    async def init(self, conv_id, app_code, history_messages=None,
                   vis_converter=None, start_round=0)
    async def clear(self, conv_id)                          # 清理会话
    async def cache(self, conv_id) -> ConversationCache     # 获取缓存

    # 消息操作
    async def push_message(self, conv_id, stream_msg, incremental=True)
    async def append_message(self, conv_id, message, save_db=True)
    async def queue_iterator(self, conv_id):                # 队列迭代器

    # 任务管理
    async def upsert_task(self, conv_id, task: TreeNodeData)
    async def complete(self, conv_id)                       # 标记完成
```

#### 2.3.3 ConversationCache 会话缓存 (`gpts_memory.py:177-270`)

```python
class ConversationCache:
    """单个会话的所有缓存数据"""

    def __init__(self, conv_id, vis_converter, start_round=0):
        self.conv_id = conv_id
        self.messages: Dict[str, GptsMessage] = {}          # 消息字典
        self.actions: Dict[str, ActionOutput] = {}          # Action结果
        self.plans: Dict[str, GptsPlan] = {}                # 计划
        self.system_messages: Dict[str, AgentSystemMessage] = {}  # 系统消息

        # 会话树管理
        self.task_manager: TreeManager[AgentTaskContent] = TreeManager()
        self.message_ids: List[str] = []                    # 消息顺序

        # 异步队列（SSE流式输出）
        self.channel = Queue(maxsize=100)

        # 文件系统
        self.files: Dict[str, AgentFileMetadata] = {}       # 文件元数据

        # 工作日志和看板
        self.work_logs: List[WorkEntry] = []
        self.kanban: Optional[Kanban] = None
        self.todos: List[TodoItem] = []
```

### 2.4 Action 层

#### 2.4.1 Action 抽象基类

```python
class Action(ABC):
    """Action 抽象基类 - 定义动作执行接口"""

    @abstractmethod
    async def run(self, *args, **kwargs) -> ActionOutput:
        """执行动作，返回结果"""
        pass

    @abstractmethod
    def describe(self) -> str:
        """描述动作功能"""
        pass
```

#### 2.4.2 ActionOutput 数据结构

```python
@dataclass
class ActionOutput:
    """动作执行结果"""
    content: str                    # 输出内容
    action_name: str                # 动作名称
    is_success: bool = True         # 是否成功
    observation: str = ""           # 观察结果
    resource_info: Dict = None      # 资源信息
    metadata: Dict = None           # 元数据
```

### 2.5 LLM 层

#### 2.5.1 双轨制 LLM 架构

```python
# 旧架构: LLMClient
class LLMClient(ABC):
    async def create(self, **config) -> AsyncIterator[AgentLLMOut]:
        """调用LLM"""
        pass

# 新架构: AIWrapper + Provider
class AIWrapper:
    async def create(self, **config):
        # 获取Provider
        llm_model = extra_kwargs.get("llm_model")
        if ModelConfigCache.has_model(llm_model):
            self._provider = self._provider_cache.get(llm_model)

        # 构建请求
        request = ModelRequest(model=final_llm_model, messages=messages, ...)

        # 调用Provider
        async for output in self._provider.create(request):
            yield AgentLLMOut(...)
```

---

## 三、执行流程详解

### 3.1 Agent 生命周期

```
┌──────────────┐
│   receive()  │◄──────── 外部消息入口
└──────┬───────┘
       │
       v
┌───────────────────┐
│  generate_reply() │
│  (生成回复主流程) │
└───────┬───────────┘
        │
        ├──► [1] 构建思考消息 (load_thinking_messages)
        │         - 加载历史对话
        │         - 构建系统Prompt
        │         - 构建用户Prompt
        │
        ├──► [2] 模型推理 (thinking)
        │         ┌─────────────────────────────────────┐
        │         │  Retry Loop (max 3 retries)         │
        │         │  - LLM调用 (llm_client.create)      │
        │         │  - 流式输出监听 (listen_thinking_   │
        │         │    stream)                           │
        │         │  - 思考内容解析 (thinking_content)  │
        │         └─────────────────────────────────────┘
        │
        ├──► [3] 内容审查 (review)
        │
        ├──► [4] 执行动作 (act)
        │         ┌─────────────────────────────────────┐
        │         │  Action Loop (until success/fail)   │
        │         │  - 解析消息 -> Action               │
        │         │  - 执行Action (action.run)           │
        │         │  - 验证结果 (verify)                 │
        │         │  - 写记忆 (write_memories)           │
        │         └─────────────────────────────────────┘
        │
        └──► [5] 最终处理 (adjust_final_message)
                  - 更新状态
                  - 推送最终结果
```

### 3.2 消息流转架构

```
┌───────────────┐                    ┌───────────────┐
│  UserProxy    │ ──AgentMessage───► │ Conversable   │
│  Agent        │◄────reply──────── │ Agent         │
└───────┬───────┘                    └───────┬───────┘
        │                                    │
        │       ┌────────────────────────────┘
        │       │
        │       v
        │   ┌───────────┐
        │   │ GptsMemory│
        │   │ channel   │
        │   └─────┬─────┘
        │         │
        │         v
        │   ┌───────────┐
        │   │  Queue    │
        │   └─────┬─────┘
        │         │
        │         v
        │   ┌───────────┐     ┌───────────┐
        └──►│ _chat_    │────►│  Frontend │
            │ messages  │     │  (SSE)    │
            └───────────┘     └───────────┘
```

### 3.3 关键代码片段

#### generate_reply 核心逻辑 (`base_agent.py:1200-1400`)

```python
async def generate_reply(self, received_message, sender, ...):
    while not done and self.current_retry_counter < self.max_retry_count:
        # 1. 模型推理
        reply_message, agent_llm_out = await self._generate_think_message(...)

        # 2. Action执行
        act_outs = await self.act(
            message=reply_message,
            sender=sender,
            agent_llm_out=agent_llm_out,  # 包含tool_calls
            ...
        )

        # 3. 验证结果
        check_pass, fail_reason = await self.verify(
            message=reply_message,
            sender=sender,
            reviewer=reviewer,
            **verify_param
        )

        # 4. 写记忆
        await self.write_memories(
            question=question,
            ai_message=ai_message,
            action_output=act_outs,
            check_pass=check_pass,
            ...
        )
```

---

## 四、关键数据模型

### 4.1 AgentContext (`agent.py:222-261`)

```python
@dataclasses.dataclass
class AgentContext:
    conv_id: str                      # 对话ID
    conv_session_id: str              # 会话ID
    staff_no: Optional[str] = None    # 员工号
    user_id: Optional[str] = None     # 用户ID
    trace_id: Optional[str] = None    # 追踪ID

    gpts_app_code: Optional[str] = None   # 应用Code
    gpts_app_name: Optional[str] = None   # 应用名称
    agent_app_code: Optional[str] = None  # Agent Code (记忆模块强依赖)

    language: str = "zh"              # 语言
    max_chat_round: int = 100         # 最大轮数
    max_retry_round: int = 10         # 最大重试
    temperature: float = 0.5          # 温度

    enable_vis_message: bool = True   # 启用VIS消息
    incremental: bool = True          # 增量输出
    stream: bool = True               # 流式输出
```

### 4.2 AgentMessage (`types.py:85-193`)

```python
@dataclasses.dataclass
class AgentMessage:
    message_id: Optional[str] = None
    content: Optional[Union[str, ChatCompletionUserMessageParam]] = None
    content_types: Optional[List[str]] = None  # ["text", "image_url", ...]
    message_type: Optional[str] = "agent_message"
    thinking: Optional[str] = None      # 思考内容
    name: Optional[str] = None
    rounds: int = 0                     # 轮数
    round_id: Optional[str] = None
    context: Optional[Dict] = None      # 上下文
    action_report: Optional[List[ActionOutput]] = None
    review_info: Optional[AgentReviewInfo] = None
    current_goal: Optional[str] = None  # 当前目标
    model_name: Optional[str] = None
    role: Optional[str] = None          # 角色
    success: bool = True
    tool_calls: Optional[List[Dict]] = None  # Function Call
```

### 4.3 数据库模型

**GptsConversationsEntity** (`gpts_conversations_db.py`):
```python
class GptsConversationsEntity(Model):
    __tablename__ = "gpts_conversations"

    id = Column(Integer, primary_key=True)
    conv_id = Column(String(255), nullable=False)      # 对话唯一ID
    conv_session_id = Column(String(255))              # 会话ID
    user_goal = Column(Text)                           # 用户目标
    gpts_name = Column(String(255))                    # Agent名称
    team_mode = Column(String(255))                    # 团队模式
    state = Column(String(255))                        # 状态
    max_auto_reply_round = Column(Integer)             # 最大自动回复轮数
    auto_reply_count = Column(Integer)                 # 自动回复计数
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

---

## 五、前后端交互链路

### 5.1 API 层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Routes                           │
├─────────────────────────────────────────────────────────────┤
│  /api/v1/serve/chat/...                                     │
│     ├── chat()              # 主聊天接口 (SSE流式)          │
│     ├── stop_chat()         # 停止对话                      │
│     └── query_chat()        # 查询对话                      │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 AgentChat 核心服务 (`agents/chat/agent_chat.py`)

```python
class AgentChat(BaseComponent, ABC):
    async def chat(self, conv_uid, gpts_name, user_query, ...):
        """主聊天入口"""
        # 1. 初始化会话
        agent_conv_id, gpts_conversations = await self._initialize_agent_conversation(...)

        # 2. 构建Agent并执行对话
        async for task, resp, agent_conv_id in self.aggregation_chat(...):
            # 流式返回SSE格式数据
            yield task, resp, agent_conv_id

    async def aggregation_chat(self, ...):
        """具体对话实现"""
        # 1. 加载应用配置
        gpt_app: GptsApp = await app_service.app_detail(gpts_name)

        # 2. 初始化记忆
        await self.memory.init(agent_conv_id, app_code=gpts_name, vis_converter=vis_protocol)

        # 3. 构建Agent
        recipient = await self._build_agent_by_gpts(...)

        # 4. 执行对话
        await user_proxy.initiate_chat(recipient=recipient, message=user_query)

        # 5. 流式输出消息
        async for chunk in self._chat_messages(agent_conv_id):
            yield task, _format_vis_msg(chunk), agent_conv_id
```

### 5.3 SSE 流式输出

```python
async def _chat_messages(self, conv_id: str):
    """消息流式输出"""
    iterator = await self.memory.queue_iterator(conv_id)
    async for item in iterator:
        yield item  # SSE格式: data:{\"vis\": {...}} \\n\\n

# 前端接收格式 (VIS协议)
data: {"vis": {
    "uid": "...",
    "type": "incr",
    "sender": "agent_name",
    "thinking": "...",
    "content": "...",
    "status": "running",
}}
```

---

## 六、与 V2 架构对比

| 方面 | Core V1 | Core V2 |
|------|---------|---------|
| **执行模型** | generate_reply 单循环 | Think/Decide/Act 三阶段 |
| **消息模型** | send/receive 显式消息传递 | run() 主循环隐式处理 |
| **状态管理** | 隐式状态 | 明确状态机 (AgentState) |
| **子Agent** | 通过消息路由 | SubagentManager 显式委派 |
| **记忆系统** | GptsMemory (单一) | UnifiedMemory + ProjectMemory (分层) |
| **上下文隔离** | 无 | ISOLATED/SHARED/FORK 三种模式 |
| **扩展机制** | 继承重写 | SceneStrategy 钩子系统 |

---

## 七、已知问题与演进方向

### 7.1 已知问题

1. **代码膨胀**: base_agent.py 已超过 2600 行，职责过重
2. **双轨LLM**: 新旧架构并存，迁移不完整
3. **记忆限制**: 无分层记忆，上下文管理能力有限
4. **子Agent弱**: 依赖消息路由，无独立上下文管理

### 7.2 演进方向

1. **向 V2 迁移**: 逐步替换核心组件
2. **记忆统一**: 通过 GptsMemoryAdapter 桥接
3. **运行时统一**: V2AgentRuntime 渐进式替换

---

## 八、关键文件索引

| 文件 | 路径 | 核心职责 |
|------|------|---------|
| Agent 接口 | `agent/core/agent.py` | 抽象接口定义 |
| ConversableAgent | `agent/core/base_agent.py` | 核心Agent实现 |
| GptsMemory | `agent/core/memory/gpts/gpts_memory.py` | 记忆管理 |
| AgentChat | `derisk_serve/agent/agents/chat/agent_chat.py` | 前端交互服务 |
| GptsMessagesDao | `derisk_serve/agent/db/gpts_messages_db.py` | 消息持久化 |