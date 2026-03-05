# DERISK 用户交互模式与中断恢复完整设计方案

## 目录

1. [设计概述](#1-设计概述)
2. [交互类型定义](#2-交互类型定义)
3. [Core V1 交互方案设计](#3-core-v1-交互方案设计)
4. [Core V2 交互方案设计](#4-core-v2-交互方案设计)
5. [中断恢复机制设计](#5-中断恢复机制设计)
6. [前端到后端完整流程](#6-前端到后端完整流程)
7. [协议定义](#7-协议定义)
8. [实现代码](#8-实现代码)
9. [Todo/Kanban 恢复机制](#9-todokanban-恢复机制)

---

## 1. 设计概述

### 1.1 设计目标

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     用户交互模式设计目标                                  │
└─────────────────────────────────────────────────────────────────────────┘

1. 主动交互能力
   ├── Agent 主动提问：任务执行中主动向用户获取信息
   ├── 工具授权请求：敏感操作前请求用户确认
   ├── 方案选择：提供多个方案供用户选择
   └── 进度通知：实时推送任务进度和状态

2. 中断恢复能力
   ├── 任意点中断：用户可在任意时刻中断任务
   ├── 完美恢复：恢复所有上下文、工作记录、附件
   ├── Todo/Kanban：未完成任务可继续执行
   └── 历史回溯：支持查看和跳转到历史决策点

3. 用户体验
   ├── 实时响应：交互请求秒级响应
   ├── 持久化保证：数据不丢失
   ├── 多端同步：支持多设备同步状态
   └── 离线支持：离线操作可缓存后同步
```

### 1.2 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           前端产品层                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Web UI    │  │  Desktop App│  │  CLI/Terminal│  │  Mobile App │    │
│  │             │  │             │  │             │  │             │    │
│  │ - React组件 │  │ - Electron  │  │ - Rich CLI  │  │ - React Native│  │
│  │ - WebSocket │  │ - WebSocket │  │ - HTTP/SSE  │  │ - WebSocket │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         交互网关层 (API Gateway)                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    InteractionGateway                            │   │
│  │                                                                  │   │
│  │   - WebSocket Server: 实时双向通信                              │   │
│  │   - HTTP REST API: 同步请求/响应                                │   │
│  │   - SSE Server: 服务器推送事件                                  │   │
│  │   - Session Manager: 会话管理                                  │   │
│  │   - Auth Middleware: 认证授权                                  │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Agent 执行层                                    │
│                                                                         │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐      │
│  │         Core V1             │  │         Core V2             │      │
│  │                             │  │                             │      │
│  │  - InteractionAdapter       │  │  - InteractionManager       │      │
│  │  - PermissionInterceptor    │  │  - PermissionManager        │      │
│  │  - StateSnapshotManager     │  │  - AgentHarness             │      │
│  │  - RecoveryCoordinator      │  │  - CheckpointManager        │      │
│  │                             │  │  - RecoveryCoordinator      │      │
│  └─────────────────────────────┘  └─────────────────────────────┘      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         持久化存储层                                    │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ SessionStore│  │ StateStore  │  │ Checkpoint  │  │ FileStorage │    │
│  │ (Redis)     │  │ (PostgreSQL)│  │ Store       │  │ (S3/OSS)    │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 交互类型定义

### 2.1 交互类型枚举

```python
class InteractionType(str, Enum):
    """交互类型枚举"""
    
    # 询问类型
    ASK = "ask"                    # 开放式问题询问
    CONFIRM = "confirm"            # 是/否确认
    SELECT = "select"              # 单选
    MULTIPLE_SELECT = "multiple_select"  # 多选
    
    # 授权类型
    AUTHORIZE = "authorize"        # 工具执行授权
    AUTHORIZE_ONCE = "authorize_once"    # 单次授权
    AUTHORIZE_SESSION = "authorize_session"  # 会话级授权
    
    # 方案选择
    CHOOSE_PLAN = "choose_plan"    # 选择执行方案
    CHOOSE_PRIORITY = "choose_priority"  # 选择优先级
    
    # 输入类型
    INPUT_TEXT = "input_text"      # 文本输入
    INPUT_FILE = "input_file"      # 文件上传
    INPUT_CODE = "input_code"      # 代码输入
    
    # 通知类型
    NOTIFY = "notify"              # 普通通知
    NOTIFY_PROGRESS = "notify_progress"  # 进度通知
    NOTIFY_ERROR = "notify_error"  # 错误通知
    NOTIFY_SUCCESS = "notify_success"    # 成功通知
```

### 2.2 交互优先级

```python
class InteractionPriority(str, Enum):
    """交互优先级"""
    
    CRITICAL = "critical"    # 关键 - 阻塞执行，必须立即处理
    HIGH = "high"           # 高优先级 - 建议尽快处理
    NORMAL = "normal"       # 正常 - 可稍后处理
    LOW = "low"             # 低优先级 - 信息性通知
```

### 2.3 交互请求模型

```python
@dataclass
class InteractionRequest:
    """交互请求"""
    
    # 基本信息
    request_id: str                    # 请求唯一ID
    interaction_type: InteractionType  # 交互类型
    priority: InteractionPriority      # 优先级
    
    # 内容
    title: str                         # 标题
    message: str                       # 消息内容
    options: List[InteractionOption]   # 选项列表
    
    # 上下文
    session_id: str                    # 会话ID
    execution_id: str                  # 执行ID
    step_index: int                    # 当前步骤索引
    agent_name: str                    # Agent名称
    tool_name: Optional[str]           # 相关工具名（授权类）
    
    # 配置
    timeout: Optional[int] = 300       # 超时时间(秒)
    default_choice: Optional[str] = None  # 默认选择
    allow_cancel: bool = True          # 是否允许取消
    allow_skip: bool = False           # 是否允许跳过
    allow_defer: bool = True           # 是否允许延后处理
    
    # 快照（用于恢复）
    state_snapshot: Optional[Dict] = None  # 状态快照
    
    # 元数据
    created_at: datetime
    metadata: Dict[str, Any]
```

### 2.4 交互响应模型

```python
@dataclass
class InteractionResponse:
    """交互响应"""
    
    # 关联信息
    request_id: str                    # 对应的请求ID
    session_id: str                    # 会话ID
    
    # 响应内容
    choice: Optional[str] = None       # 用户选择（单选）
    choices: List[str] = None          # 用户选择（多选）
    input_value: Optional[str] = None  # 输入值
    files: List[str] = None            # 上传文件路径
    
    # 状态
    status: InteractionStatus          # 响应状态
    user_message: Optional[str] = None # 用户的额外说明
    
    # 授权扩展
    grant_scope: Optional[str] = None  # 授权范围：once/session/always
    grant_duration: Optional[int] = None  # 授权时长
    
    # 时间戳
    timestamp: datetime
```

---

## 3. Core V1 交互方案设计

### 3.1 架构增强

Core V1 需要在现有架构基础上新增以下组件：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Core V1 交互架构增强                                 │
└─────────────────────────────────────────────────────────────────────────┘

现有组件                          新增组件
───────────────                   ───────────────
ConversableAgent                  InteractionAdapter
    │                                 │
    ├── llm_client                   ├── 请求构建器
    ├── memory                       ├── 响应处理器
    ├── actions                      ├── 超时管理器
    └── permission_ruleset           └── 上下文快照
                  │
                  ▼
PermissionRuleset                 PermissionInterceptor
    │                                 │
    ├── check()                      ├── 异步授权请求
    └── rules                        ├── 用户确认流程
                                      └── 授权缓存

ExecutionEngine                    StateSnapshotManager
    │                                 │
    ├── execute()                    ├── 快照创建
    ├── hooks                        ├── 快照恢复
    └── context_lifecycle            └── 增量同步

追加组件                          RecoveryCoordinator
                                      │
                                      ├── 会话恢复
                                      ├── 任务续接
                                      └── 状态同步
```

### 3.2 InteractionAdapter 设计

```python
"""
Core V1 - InteractionAdapter

为 Core V1 的 ConversableAgent 提供统一的交互能力
"""

class InteractionAdapter:
    """
    交互适配器 - 将用户交互集成到 Core V1 Agent
    
    使用方式：
    ```python
    agent = ConversableAgent(...)
    adapter = InteractionAdapter(agent)
    
    # 主动提问
    answer = await adapter.ask("请提供数据库连接信息")
    
    # 工具授权
    authorized = await adapter.request_tool_permission("bash", {"command": "rm -rf"})
    
    # 方案选择
    plan = await adapter.choose_plan([
        {"id": "plan_a", "name": "方案A：快速实现", "pros": ["快"], "cons": ["不完整"]},
        {"id": "plan_b", "name": "方案B：完整实现", "pros": ["完整"], "cons": ["慢"]},
    ])
    ```
    """
    
    def __init__(
        self,
        agent: "ConversableAgent",
        gateway: Optional["InteractionGateway"] = None,
        config: Optional["InteractionConfig"] = None,
    ):
        self.agent = agent
        self.gateway = gateway or get_default_gateway()
        self.config = config or InteractionConfig()
        
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._response_cache: Dict[str, InteractionResponse] = {}
        
    async def ask(
        self,
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        options: Optional[List[str]] = None,
        timeout: int = 300,
        context: Optional[Dict] = None,
    ) -> str:
        """
        主动向用户提问
        
        适用场景：
        - 缺少必要信息时请求用户提供
        - 需要澄清模糊指令
        - 需要用户指定参数
        """
        # 创建快照
        snapshot = await self._create_snapshot()
        
        # 构建请求
        interaction_type = InteractionType.SELECT if options else InteractionType.ASK
        request = InteractionRequest(
            interaction_type=interaction_type,
            priority=InteractionPriority.HIGH,
            title=title,
            message=question,
            options=[InteractionOption(label=o, value=o) for o in (options or [])],
            session_id=self.agent.agent_context.conv_session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent.name,
            timeout=timeout,
            default_choice=default,
            state_snapshot=snapshot,
            context=context or {},
        )
        
        # 发送请求并等待响应
        response = await self._send_and_wait(request)
        
        if response.status == InteractionStatus.TIMEOUT:
            if default:
                return default
            raise InteractionTimeoutError(f"用户未在 {timeout} 秒内响应")
        
        return response.input_value or response.choice or ""
    
    async def request_tool_permission(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        reason: Optional[str] = None,
        timeout: int = 120,
    ) -> bool:
        """
        请求工具执行授权
        
        适用场景：
        - 危险命令执行（rm -rf, drop table 等）
        - 敏感数据访问
        - 外部网络请求
        """
        # 检查权限规则
        if self.agent.permission_ruleset:
            action = self.agent.permission_ruleset.check(tool_name)
            if action == PermissionAction.ALLOW:
                return True
            if action == PermissionAction.DENY:
                return False
        
        # 创建快照
        snapshot = await self._create_snapshot()
        
        # 构建授权请求
        request = InteractionRequest(
            interaction_type=InteractionType.AUTHORIZE,
            priority=InteractionPriority.CRITICAL,
            title=f"工具授权请求: {tool_name}",
            message=self._format_auth_message(tool_name, tool_args, reason),
            options=[
                InteractionOption(label="允许（本次）", value="allow_once", default=True),
                InteractionOption(label="允许（本次会话）", value="allow_session"),
                InteractionOption(label="拒绝", value="deny"),
            ],
            session_id=self.agent.agent_context.conv_session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent.name,
            tool_name=tool_name,
            timeout=timeout,
            state_snapshot=snapshot,
            context={"tool_args": tool_args, "reason": reason},
        )
        
        response = await self._send_and_wait(request)
        
        if response.choice == "deny":
            return False
        
        # 缓存授权
        if response.choice == "allow_session":
            self._cache_session_permission(tool_name)
        
        return True
    
    async def choose_plan(
        self,
        plans: List[Dict[str, Any]],
        title: str = "请选择执行方案",
        timeout: int = 300,
    ) -> str:
        """
        让用户选择执行方案
        
        适用场景：
        - 多种技术路线可选
        - 成本/时间权衡
        - 风险级别选择
        """
        snapshot = await self._create_snapshot()
        
        options = []
        for plan in plans:
            options.append(InteractionOption(
                label=plan.get("name", plan.get("id")),
                value=plan.get("id"),
                description=self._format_plan_description(plan),
            ))
        
        request = InteractionRequest(
            interaction_type=InteractionType.CHOOSE_PLAN,
            priority=InteractionPriority.HIGH,
            title=title,
            message="发现多种可行的执行方案，请选择您偏好的方案：",
            options=options,
            session_id=self.agent.agent_context.conv_session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent.name,
            timeout=timeout,
            state_snapshot=snapshot,
            context={"plans": plans},
        )
        
        response = await self._send_and_wait(request)
        return response.choice
    
    async def notify(
        self,
        message: str,
        level: NotifyLevel = NotifyLevel.INFO,
        title: Optional[str] = None,
        progress: Optional[float] = None,
    ):
        """
        发送通知（无需等待响应）
        """
        request = InteractionRequest(
            interaction_type=InteractionType.NOTIFY_PROGRESS if progress else InteractionType.NOTIFY,
            priority=InteractionPriority.NORMAL,
            title=title or "通知",
            message=message,
            session_id=self.agent.agent_context.conv_session_id,
            execution_id=self._get_execution_id(),
            step_index=self._get_current_step(),
            agent_name=self.agent.name,
            metadata={"level": level.value, "progress": progress},
        )
        
        await self.gateway.send(request)
    
    async def _create_snapshot(self) -> Dict[str, Any]:
        """创建当前状态快照"""
        return {
            "timestamp": datetime.now().isoformat(),
            "agent_name": self.agent.name,
            "step_index": self._get_current_step(),
            "memory_context": await self._extract_memory_context(),
            "pending_actions": self._get_pending_actions(),
            "variables": self._get_variables(),
            "files_created": self._get_created_files(),
            "todo_list": self._get_todo_list(),
        }
    
    async def _send_and_wait(self, request: InteractionRequest) -> InteractionResponse:
        """发送请求并等待响应"""
        future = asyncio.Future()
        self._pending_requests[request.request_id] = future
        
        try:
            await self.gateway.send(request)
            return await asyncio.wait_for(future, timeout=request.timeout)
        except asyncio.TimeoutError:
            return InteractionResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=InteractionStatus.TIMEOUT,
            )
        finally:
            self._pending_requests.pop(request.request_id, None)
    
    def handle_response(self, response: InteractionResponse):
        """处理来自前端的响应"""
        if response.request_id in self._pending_requests:
            future = self._pending_requests[response.request_id]
            if not future.done():
                future.set_result(response)
```

### 3.3 集成到 ConversableAgent

```python
"""
扩展 ConversableAgent 以支持交互能力
"""

class ConversableAgent(Role, Agent):
    # ... 现有代码 ...
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 新增：交互适配器
        self._interaction_adapter: Optional[InteractionAdapter] = None
    
    @property
    def interaction(self) -> InteractionAdapter:
        """获取交互适配器"""
        if self._interaction_adapter is None:
            self._interaction_adapter = InteractionAdapter(self)
        return self._interaction_adapter
    
    async def act(self, message, sender, **kwargs) -> List[ActionOutput]:
        """执行动作 - 增强权限检查"""
        # 解析工具调用
        tool_calls = self._parse_tool_calls(message)
        
        results = []
        for tool_call in tool_calls:
            # 交互式权限检查
            if self.interaction:
                authorized = await self.interaction.request_tool_permission(
                    tool_name=tool_call.name,
                    tool_args=tool_call.args,
                )
                if not authorized:
                    results.append(ActionOutput(
                        content=f"工具 {tool_call.name} 执行被用户拒绝",
                        is_exe_success=False,
                    ))
                    continue
            
            # 执行工具
            result = await self._execute_tool(tool_call)
            results.append(result)
        
        return results
```

---

## 4. Core V2 交互方案设计

### 4.1 架构增强

Core V2 已有完善的 InteractionManager，需要增强以下几点：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Core V2 交互架构增强                                 │
└─────────────────────────────────────────────────────────────────────────┘

现有组件                          增强内容
───────────────                   ───────────────
InteractionManager                WebSocketInteractionHandler
    │                                 │
    ├── ask_user()                   ├── 实时推送
    ├── confirm()                    ├── 多端同步
    ├── select()                     ├── 断线重连
    ├── request_authorization()      └── 离线缓存
    └── notify()

PermissionManager                  InteractivePermissionChecker
    │                                 │
    ├── check()                      ├── 用户交互授权
    └── ruleset                      ├── 授权范围管理
                                      └── 会话级缓存

AgentHarness                       EnhancedCheckpointManager
    │                                 │
    ├── execute()                    ├── 交互点快照
    ├── pause()                      ├── 响应集成
    └── resume()                     ├── 自动暂停
                                      └── 恢复触发
```

### 4.2 增强的 InteractionManager

```python
"""
Core V2 - EnhancedInteractionManager

扩展现有 InteractionManager 以支持完整交互能力
"""

class EnhancedInteractionManager(InteractionManager):
    """
    增强的交互管理器
    
    新增功能：
    1. WebSocket 实时通信
    2. 断线重连与恢复
    3. 离线请求缓存
    4. 多端同步
    """
    
    def __init__(
        self,
        gateway: Optional["InteractionGateway"] = None,
        state_store: Optional["StateStore"] = None,
        offline_cache_size: int = 100,
    ):
        super().__init__()
        self.gateway = gateway
        self.state_store = state_store
        
        # 离线缓存
        self._offline_cache: List[InteractionRequest] = []
        self._offline_cache_size = offline_cache_size
        
        # 连接状态
        self._is_connected = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        
        # 授权缓存
        self._authorization_cache: Dict[str, AuthorizationCache] = {}
    
    async def ask_with_context(
        self,
        question: str,
        title: str = "需要您的输入",
        default: Optional[str] = None,
        options: Optional[List[Dict]] = None,
        context: Optional[Dict] = None,
        snapshot: Optional[Dict] = None,
        timeout: int = 300,
    ) -> str:
        """
        带上下文的询问 - 支持中断恢复
        
        Args:
            question: 问题内容
            title: 标题
            default: 默认值
            options: 选项列表
            context: 上下文信息
            snapshot: 状态快照（用于恢复）
            timeout: 超时时间
        """
        interaction_type = InteractionType.SELECT if options else InteractionType.ASK
        
        request = InteractionRequest(
            request_id=self._generate_request_id(),
            interaction_type=interaction_type,
            priority=InteractionPriority.HIGH,
            title=title,
            message=question,
            options=[InteractionOption(**o) for o in (options or [])],
            context=context or {},
            timeout=timeout,
            default_choice=default,
            state_snapshot=snapshot,
        )
        
        response = await self._execute_with_retry(request)
        
        if response.status == InteractionStatus.TIMEOUT:
            if default:
                return default
            raise InteractionTimeoutError(f"等待用户响应超时")
        
        return response.input_value or response.choice or ""
    
    async def request_authorization_smart(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        ruleset: Optional[PermissionRuleset] = None,
        context: Optional[Dict] = None,
        snapshot: Optional[Dict] = None,
    ) -> PermissionResponse:
        """
        智能授权请求
        
        根据规则和缓存决定是否需要用户确认
        """
        # 1. 检查规则
        if ruleset:
            action = ruleset.check(tool_name)
            if action == PermissionAction.ALLOW:
                return PermissionResponse(granted=True, action=action)
            if action == PermissionAction.DENY:
                return PermissionResponse(granted=False, action=action)
        
        # 2. 检查会话级授权缓存
        cache_key = self._get_auth_cache_key(tool_name, tool_args)
        if cache_key in self._authorization_cache:
            cache = self._authorization_cache[cache_key]
            if cache.is_valid():
                return PermissionResponse(granted=True, action=PermissionAction.ALLOW)
        
        # 3. 请求用户授权
        risk_level = self._assess_risk_level(tool_name, tool_args)
        
        request = InteractionRequest(
            request_id=self._generate_request_id(),
            interaction_type=InteractionType.AUTHORIZE,
            priority=InteractionPriority.CRITICAL if risk_level == "high" else InteractionPriority.HIGH,
            title=f"需要授权: {tool_name}",
            message=self._format_auth_request_message(tool_name, tool_args, risk_level),
            options=[
                InteractionOption(label="允许本次", value="allow_once", default=True),
                InteractionOption(label="允许本次会话所有同类操作", value="allow_session"),
                InteractionOption(label="总是允许", value="allow_always"),
                InteractionOption(label="拒绝", value="deny"),
            ],
            tool_name=tool_name,
            context=context or {},
            state_snapshot=snapshot,
            metadata={"risk_level": risk_level, "tool_args": tool_args},
        )
        
        response = await self._execute_with_retry(request)
        
        granted = response.choice in ["allow_once", "allow_session", "allow_always"]
        
        # 缓存授权
        if response.choice == "allow_session":
            self._cache_session_authorization(tool_name, tool_args)
        elif response.choice == "allow_always":
            await self._save_permanent_authorization(tool_name)
        
        return PermissionResponse(
            granted=granted,
            action=PermissionAction.ALLOW if granted else PermissionAction.DENY,
            user_message=response.user_message,
        )
    
    async def choose_plan_with_analysis(
        self,
        plans: List[Dict[str, Any]],
        title: str = "请选择方案",
        analysis: Optional[str] = None,
        snapshot: Optional[Dict] = None,
    ) -> str:
        """
        方案选择 - 提供详细分析
        """
        options = []
        for i, plan in enumerate(plans):
            pros = plan.get("pros", [])
            cons = plan.get("cons", [])
            estimated_time = plan.get("estimated_time", "未知")
            risk = plan.get("risk_level", "中")
            
            description = f"预计耗时: {estimated_time}\n"
            description += f"风险级别: {risk}\n"
            if pros:
                description += f"优点: {', '.join(pros)}\n"
            if cons:
                description += f"缺点: {', '.join(cons)}"
            
            options.append(InteractionOption(
                label=plan.get("name", f"方案 {i+1}"),
                value=plan.get("id", str(i+1)),
                description=description,
            ))
        
        message = "我分析了多种可行方案：\n\n"
        if analysis:
            message += f"{analysis}\n\n"
        message += "请选择您偏好的执行方案："
        
        request = InteractionRequest(
            request_id=self._generate_request_id(),
            interaction_type=InteractionType.CHOOSE_PLAN,
            priority=InteractionPriority.HIGH,
            title=title,
            message=message,
            options=options,
            state_snapshot=snapshot,
            context={"plans": plans, "analysis": analysis},
        )
        
        response = await self._execute_with_retry(request)
        return response.choice
    
    async def _execute_with_retry(self, request: InteractionRequest) -> InteractionResponse:
        """执行请求，支持重试"""
        if self._is_connected and self.gateway:
            try:
                return await self._send_via_gateway(request)
            except ConnectionError:
                self._is_connected = False
        
        # 离线模式：缓存请求
        if not self._is_connected:
            self._cache_offline_request(request)
            return await self._wait_for_connection(request)
        
        raise InteractionError("无法发送交互请求")
    
    async def _send_via_gateway(self, request: InteractionRequest) -> InteractionResponse:
        """通过 Gateway 发送请求"""
        future = asyncio.Future()
        self._pending_requests[request.request_id] = future
        
        await self.gateway.send(request)
        
        try:
            return await asyncio.wait_for(
                future,
                timeout=request.timeout or 300
            )
        except asyncio.TimeoutError:
            return InteractionResponse(
                request_id=request.request_id,
                status=InteractionStatus.TIMEOUT,
            )
    
    def _cache_offline_request(self, request: InteractionRequest):
        """缓存离线请求"""
        self._offline_cache.append(request)
        if len(self._offline_cache) > self._offline_cache_size:
            self._offline_cache.pop(0)
    
    async def _wait_for_connection(self, request: InteractionRequest) -> InteractionResponse:
        """等待连接恢复"""
        while not self._is_connected and self._reconnect_attempts < self._max_reconnect_attempts:
            await asyncio.sleep(5)
            self._reconnect_attempts += 1
            # 尝试重连
            self._is_connected = await self._try_reconnect()
        
        if self._is_connected:
            return await self._send_via_gateway(request)
        
        return InteractionResponse(
            request_id=request.request_id,
            status=InteractionStatus.FAILED,
        )
```

### 4.3 WebSocket 交互处理器

```python
"""
Core V2 - WebSocketInteractionHandler

通过 WebSocket 实现实时交互
"""

class WebSocketInteractionHandler(InteractionHandler):
    """WebSocket 交互处理器"""
    
    def __init__(self, websocket_manager: "WebSocketManager"):
        self.ws_manager = websocket_manager
        self._pending_responses: Dict[str, asyncio.Future] = {}
    
    async def can_handle(self, request: InteractionRequest) -> bool:
        """检查是否有活跃的 WebSocket 连接"""
        return await self.ws_manager.has_connection(request.session_id)
    
    async def handle(self, request: InteractionRequest) -> InteractionResponse:
        """通过 WebSocket 处理交互"""
        future = asyncio.Future()
        self._pending_responses[request.request_id] = future
        
        # 发送交互请求
        await self.ws_manager.send_to_session(
            session_id=request.session_id,
            message={
                "type": "interaction_request",
                "data": request.to_dict(),
            }
        )
        
        try:
            return await asyncio.wait_for(future, timeout=request.timeout or 300)
        except asyncio.TimeoutError:
            return InteractionResponse(
                request_id=request.request_id,
                status=InteractionStatus.TIMEOUT,
            )
    
    async def on_response(self, response_data: Dict):
        """处理来自前端的响应"""
        request_id = response_data.get("request_id")
        if request_id in self._pending_responses:
            response = InteractionResponse.from_dict(response_data)
            future = self._pending_responses.pop(request_id)
            if not future.done():
                future.set_result(response)
```

---

## 5. 中断恢复机制设计

### 5.1 恢复机制架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        中断恢复机制架构                                   │
└─────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────┐
                         │   用户中断请求      │
                         │   (手动/超时/异常)  │
                         └──────────┬──────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       RecoveryCoordinator                                │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │ SnapshotManager │  │ ContextRestorer │  │ TaskResumer     │         │
│  │                 │  │                 │  │                 │         │
│  │ - 创建快照      │  │ - 恢复对话上下文│  │ - 恢复待执行任务│         │
│  │ - 增量同步      │  │ - 恢复工作记录  │  │ - 恢复Todo/Kanban│        │
│  │ - 压缩存储      │  │ - 恢复附件文件  │  │ - 恢复决策历史  │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
│                                                                          │
│                           │                                              │
│                           ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                       RecoveryState                                │  │
│  │                                                                    │  │
│  │   - session_id: str                                                │  │
│  │   - checkpoint_id: str                                             │  │
│  │   - interrupt_point: InterruptPoint                                │  │
│  │   - pending_interactions: List[InteractionRequest]                │  │
│  │   - resumable_tasks: List[Task]                                    │  │
│  │   - todo_list: List[TodoItem]                                      │  │
│  │   - files_created: List[str]                                       │  │
│  │   - decision_history: List[Decision]                               │  │
│  │                                                                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   用户恢复请求      │
                         │   (继续/跳过/取消)  │
                         └─────────────────────┘
```

### 5.2 恢复状态模型

```python
@dataclass
class InterruptPoint:
    """中断点信息"""
    
    # 基本信息
    interrupt_id: str
    session_id: str
    execution_id: str
    
    # 中断位置
    step_index: int
    phase: str              # "thinking" / "acting" / "waiting_interaction"
    
    # 中断原因
    reason: str             # "user_request" / "timeout" / "error" / "interaction_pending"
    error_message: Optional[str]
    
    # 时间戳
    created_at: datetime


@dataclass
class RecoveryState:
    """恢复状态"""
    
    # 标识
    recovery_id: str
    session_id: str
    checkpoint_id: str
    
    # 中断点
    interrupt_point: InterruptPoint
    
    # 快照数据
    conversation_history: List[Dict]       # 对话历史
    tool_execution_history: List[Dict]     # 工具执行记录
    decision_history: List[Dict]           # 决策历史
    
    # 待处理
    pending_interactions: List[InteractionRequest]  # 待响应的交互请求
    pending_actions: List[Dict]            # 待执行的动作
    
    # 工作成果
    files_created: List[FileInfo]          # 创建的文件
    files_modified: List[FileInfo]         # 修改的文件
    variables: Dict[str, Any]              # 变量状态
    
    # 任务状态
    todo_list: List[TodoItem]              # Todo 列表
    kanban_state: Optional[Dict]           # Kanban 状态
    completed_subtasks: List[str]          # 已完成的子任务
    pending_subtasks: List[str]            # 待执行的子任务
    
    # 目标
    original_goal: str                     # 原始目标
    current_subgoal: Optional[str]         # 当前子目标
    
    # 元数据
    created_at: datetime
    snapshot_size: int


@dataclass
class TodoItem:
    """Todo 项目"""
    id: str
    content: str
    status: str            # "pending" / "in_progress" / "completed" / "blocked"
    priority: int
    dependencies: List[str]
    result: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


@dataclass
class FileInfo:
    """文件信息"""
    path: str
    content_hash: str
    size: int
    created_at: datetime
    modified_at: datetime
```

### 5.3 RecoveryCoordinator 实现

```python
"""
RecoveryCoordinator - 恢复协调器

统一管理 Core V1 和 Core V2 的中断恢复
"""

class RecoveryCoordinator:
    """
    恢复协调器
    
    职责：
    1. 在交互点创建快照
    2. 持久化恢复状态
    3. 协调恢复流程
    """
    
    def __init__(
        self,
        state_store: StateStore,
        file_store: FileStorage,
        checkpoint_interval: int = 5,  # 每 5 步自动检查点
    ):
        self.state_store = state_store
        self.file_store = file_store
        self.checkpoint_interval = checkpoint_interval
        
        self._recovery_states: Dict[str, RecoveryState] = {}
        self._interrupt_points: Dict[str, InterruptPoint] = {}
    
    async def create_checkpoint(
        self,
        session_id: str,
        execution_id: str,
        step_index: int,
        phase: str,
        context: Dict[str, Any],
        agent: Union["ConversableAgent", "SimpleAgent"],
    ) -> str:
        """
        创建检查点
        
        在以下场景自动调用：
        1. 交互请求发起前
        2. 每 N 步执行后
        3. 重要决策完成后
        """
        checkpoint_id = f"cp_{session_id}_{step_index}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # 收集快照数据
        snapshot_data = await self._collect_snapshot_data(agent)
        
        # 创建中断点
        interrupt_point = InterruptPoint(
            interrupt_id=f"int_{checkpoint_id}",
            session_id=session_id,
            execution_id=execution_id,
            step_index=step_index,
            phase=phase,
            reason="checkpoint",
            created_at=datetime.now(),
        )
        
        # 创建恢复状态
        recovery_state = RecoveryState(
            recovery_id=f"rec_{checkpoint_id}",
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            interrupt_point=interrupt_point,
            conversation_history=snapshot_data["conversation_history"],
            tool_execution_history=snapshot_data["tool_execution_history"],
            decision_history=snapshot_data["decision_history"],
            pending_interactions=[],
            pending_actions=snapshot_data["pending_actions"],
            files_created=snapshot_data["files_created"],
            files_modified=snapshot_data["files_modified"],
            variables=snapshot_data["variables"],
            todo_list=snapshot_data["todo_list"],
            kanban_state=snapshot_data.get("kanban_state"),
            completed_subtasks=snapshot_data["completed_subtasks"],
            pending_subtasks=snapshot_data["pending_subtasks"],
            original_goal=snapshot_data["original_goal"],
            current_subgoal=snapshot_data.get("current_subgoal"),
            created_at=datetime.now(),
            snapshot_size=0,
        )
        
        # 计算快照大小
        recovery_state.snapshot_size = len(json.dumps(recovery_state.to_dict()))
        
        # 持久化
        await self.state_store.save(checkpoint_id, recovery_state.to_dict())
        
        # 缓存
        self._recovery_states[session_id] = recovery_state
        self._interrupt_points[interrupt_point.interrupt_id] = interrupt_point
        
        return checkpoint_id
    
    async def create_interaction_checkpoint(
        self,
        session_id: str,
        execution_id: str,
        interaction_request: InteractionRequest,
        agent: Union["ConversableAgent", "SimpleAgent"],
    ) -> str:
        """
        在交互请求发起时创建检查点
        
        这是恢复的精确点
        """
        checkpoint_id = await self.create_checkpoint(
            session_id=session_id,
            execution_id=execution_id,
            step_index=interaction_request.step_index,
            phase="waiting_interaction",
            context=interaction_request.context,
            agent=agent,
        )
        
        # 将交互请求添加到等待列表
        if session_id in self._recovery_states:
            self._recovery_states[session_id].pending_interactions.append(interaction_request)
            await self._persist_recovery_state(session_id)
        
        return checkpoint_id
    
    async def recover(
        self,
        session_id: str,
        checkpoint_id: Optional[str] = None,
        resume_mode: str = "continue",  # "continue" / "skip" / "restart"
    ) -> RecoveryResult:
        """
        恢复执行
        
        Args:
            session_id: 会话ID
            checkpoint_id: 检查点ID（可选，默认使用最新）
            resume_mode: 恢复模式
                - continue: 从中断点继续
                - skip: 跳过当前等待的交互
                - restart: 从任务开始重新执行
        """
        # 加载恢复状态
        if checkpoint_id:
            recovery_state = await self._load_recovery_state(checkpoint_id)
        else:
            recovery_state = await self._get_latest_recovery_state(session_id)
        
        if not recovery_state:
            return RecoveryResult(
                success=False,
                error="No recovery state found",
            )
        
        # 验证恢复状态
        validation = await self._validate_recovery_state(recovery_state)
        if not validation.valid:
            return RecoveryResult(
                success=False,
                error=validation.error,
            )
        
        # 恢复文件状态
        await self._restore_files(recovery_state)
        
        # 构建恢复上下文
        recovery_context = RecoveryContext(
            recovery_state=recovery_state,
            resume_mode=resume_mode,
        )
        
        return RecoveryResult(
            success=True,
            recovery_context=recovery_context,
            pending_interaction=recovery_state.pending_interactions[0] if recovery_state.pending_interactions else None,
            pending_todos=recovery_state.todo_list,
            summary=self._create_recovery_summary(recovery_state),
        )
    
    async def resume_from_interaction(
        self,
        session_id: str,
        interaction_response: InteractionResponse,
    ) -> ResumeResult:
        """
        从交互响应恢复执行
        """
        recovery_state = self._recovery_states.get(session_id)
        if not recovery_state:
            recovery_state = await self._get_latest_recovery_state(session_id)
        
        if not recovery_state:
            return ResumeResult(success=False, error="No recovery state")
        
        # 移除已响应的交互请求
        recovery_state.pending_interactions = [
            r for r in recovery_state.pending_interactions
            if r.request_id != interaction_response.request_id
        ]
        
        # 返回恢复所需的所有信息
        return ResumeResult(
            success=True,
            checkpoint_id=recovery_state.checkpoint_id,
            step_index=recovery_state.interrupt_point.step_index,
            conversation_history=recovery_state.conversation_history,
            variables=recovery_state.variables,
            todo_list=recovery_state.todo_list,
            response=interaction_response,
        )
    
    async def _collect_snapshot_data(
        self,
        agent: Union["ConversableAgent", "SimpleAgent"],
    ) -> Dict[str, Any]:
        """收集快照数据"""
        data = {
            "conversation_history": [],
            "tool_execution_history": [],
            "decision_history": [],
            "pending_actions": [],
            "files_created": [],
            "files_modified": [],
            "variables": {},
            "todo_list": [],
            "kanban_state": None,
            "completed_subtasks": [],
            "pending_subtasks": [],
            "original_goal": "",
            "current_subgoal": None,
        }
        
        # Core V1 数据收集
        if hasattr(agent, "agent_context"):
            # 对话历史
            if agent.memory and hasattr(agent.memory, "get_context_window"):
                data["conversation_history"] = await agent.memory.get_context_window(max_tokens=100000)
            
            # 变量状态
            if hasattr(agent, "variables"):
                data["variables"] = dict(agent.variables)
            
            # Todo 列表
            if hasattr(agent, "todo_list"):
                data["todo_list"] = [
                    TodoItem(
                        id=t.get("id"),
                        content=t.get("content"),
                        status=t.get("status"),
                        priority=t.get("priority", 0),
                        dependencies=t.get("dependencies", []),
                        result=t.get("result"),
                        created_at=t.get("created_at"),
                        completed_at=t.get("completed_at"),
                    )
                    for t in agent.todo_list
                ]
        
        # Core V2 数据收集
        elif hasattr(agent, "harness"):
            harness = agent.harness
            if harness.snapshot:
                data["conversation_history"] = harness.snapshot.messages
                data["variables"] = harness.snapshot.variables
                data["tool_execution_history"] = harness.snapshot.tool_history
                data["decision_history"] = harness.snapshot.decision_history
        
        return data
    
    async def _restore_files(self, recovery_state: RecoveryState):
        """恢复文件状态"""
        for file_info in recovery_state.files_created + recovery_state.files_modified:
            # 检查文件是否仍存在
            if not os.path.exists(file_info.path):
                # 尝试从存储恢复
                content = await self.file_store.get(file_info.content_hash)
                if content:
                    os.makedirs(os.path.dirname(file_info.path), exist_ok=True)
                    with open(file_info.path, "w") as f:
                        f.write(content)
    
    def _create_recovery_summary(self, recovery_state: RecoveryState) -> str:
        """创建恢复摘要"""
        summary_parts = [
            f"## 任务恢复摘要",
            f"",
            f"**原始目标**: {recovery_state.original_goal}",
            f"",
            f"**中断点**: 第 {recovery_state.interrupt_point.step_index} 步",
            f"**中断原因**: {recovery_state.interrupt_point.reason}",
            f"**中断时间**: {recovery_state.interrupt_point.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
        ]
        
        if recovery_state.todo_list:
            completed = [t for t in recovery_state.todo_list if t.status == "completed"]
            pending = [t for t in recovery_state.todo_list if t.status != "completed"]
            
            summary_parts.append(f"### 任务进度")
            summary_parts.append(f"- 已完成: {len(completed)} 项")
            summary_parts.append(f"- 待处理: {len(pending)} 项")
            summary_parts.append(f"")
            
            if pending:
                summary_parts.append(f"### 待处理任务")
                for t in pending[:5]:
                    summary_parts.append(f"- [{t.status}] {t.content}")
                if len(pending) > 5:
                    summary_parts.append(f"- ... 还有 {len(pending) - 5} 项")
                summary_parts.append(f"")
        
        if recovery_state.files_created or recovery_state.files_modified:
            summary_parts.append(f"### 工作成果")
            summary_parts.append(f"- 创建文件: {len(recovery_state.files_created)} 个")
            summary_parts.append(f"- 修改文件: {len(recovery_state.files_modified)} 个")
        
        return "\n".join(summary_parts)
```

---

## 6. 前端到后端完整流程

### 6.1 前端交互组件设计

```typescript
/**
 * 前端交互组件 - React 实现
 */

// 交互请求组件
interface InteractionRequestProps {
  request: InteractionRequest;
  onRespond: (response: InteractionResponse) => void;
  onDefer: () => void;
}

const InteractionRequestModal: React.FC<InteractionRequestProps> = ({
  request,
  onRespond,
  onDefer
}) => {
  const [inputValue, setInputValue] = useState('');
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  
  // 渲染不同类型的交互
  const renderContent = () => {
    switch (request.interaction_type) {
      case 'ask':
        return (
          <AskInput
            question={request.message}
            defaultValue={request.default_choice}
            onInput={setInputValue}
          />
        );
      
      case 'confirm':
        return (
          <ConfirmDialog
            message={request.message}
            onConfirm={() => onRespond({
              request_id: request.request_id,
              choice: 'yes',
              status: 'responsed'
            })}
            onCancel={() => onRespond({
              request_id: request.request_id,
              choice: 'no',
              status: 'responsed'
            })}
          />
        );
      
      case 'select':
        return (
          <SelectOptions
            options={request.options}
            selected={selectedChoice}
            onSelect={setSelectedChoice}
          />
        );
      
      case 'authorize':
        return (
          <AuthorizationRequest
            toolName={request.tool_name}
            context={request.context}
            options={request.options}
            selected={selectedChoice}
            onSelect={setSelectedChoice}
          />
        );
      
      case 'choose_plan':
        return (
          <PlanSelector
            plans={request.context?.plans || []}
            selected={selectedChoice}
            onSelect={setSelectedChoice}
          />
        );
      
      default:
        return <div>{request.message}</div>;
    }
  };
  
  return (
    <Modal
      title={request.title}
      priority={request.priority}
      timeout={request.timeout}
      allowDefer={request.allow_defer}
    >
      {renderContent()}
      
      <ModalActions>
        {request.allow_skip && (
          <Button onClick={() => onRespond({
            request_id: request.request_id,
            status: 'cancelled',
            cancel_reason: 'skipped'
          })}>
            跳过
          </Button>
        )}
        
        {request.allow_defer && (
          <Button onClick={onDefer}>
            稍后处理
          </Button>
        )}
        
        <Button
          primary
          onClick={() => onRespond({
            request_id: request.request_id,
            choice: selectedChoice || undefined,
            input_value: inputValue || undefined,
            status: 'responsed'
          })}
        >
          确认
        </Button>
      </ModalActions>
    </Modal>
  );
};

// 恢复会话组件
const SessionRecovery: React.FC<{
  recoveryState: RecoveryState;
  onResume: (mode: 'continue' | 'skip' | 'restart') => void;
}> = ({ recoveryState, onResume }) => {
  return (
    <Card>
      <CardHeader>
        <Typography variant="h5">发现未完成的任务</Typography>
        <Typography variant="body2" color="textSecondary">
          中断于 {recoveryState.interrupt_point.created_at}
        </Typography>
      </CardHeader>
      
      <CardContent>
        <Typography variant="body1">
          原始目标: {recoveryState.original_goal}
        </Typography>
        
        {/* 进度展示 */}
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2">任务进度</Typography>
          <LinearProgress
            variant="determinate"
            value={
              (recoveryState.completed_subtasks.length /
                (recoveryState.completed_subtasks.length + recoveryState.pending_subtasks.length)) * 100
            }
          />
        </Box>
        
        {/* Todo 列表 */}
        {recoveryState.todo_list.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2">待处理任务</Typography>
            <List>
              {recoveryState.todo_list
                .filter(t => t.status !== 'completed')
                .map(todo => (
                  <ListItem key={todo.id}>
                    <ListItemIcon>
                      {todo.status === 'in_progress' ? (
                        <CircularProgress size={20} />
                      ) : (
                        <RadioButtonUnchecked />
                      )}
                    </ListItemIcon>
                    <ListItemText primary={todo.content} />
                  </ListItem>
                ))}
            </List>
          </Box>
        )}
        
        {/* 文件列表 */}
        {(recoveryState.files_created.length > 0 || recoveryState.files_modified.length > 0) && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2">工作成果</Typography>
            <FileList
              files={[
                ...recoveryState.files_created.map(f => ({ ...f, type: 'created' })),
                ...recoveryState.files_modified.map(f => ({ ...f, type: 'modified' }))
              ]}
            />
          </Box>
        )}
      </CardContent>
      
      <CardActions>
        <Button onClick={() => onResume('restart')}>
          重新开始
        </Button>
        <Button onClick={() => onResume('skip')}>
          跳过当前步骤
        </Button>
        <Button
          variant="contained"
          onClick={() => onResume('continue')}
        >
          继续执行
        </Button>
      </CardActions>
    </Card>
  );
};

// WebSocket 连接管理
class InteractionWebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private messageQueue: any[] = [];
  
  constructor(
    private url: string,
    private onMessage: (data: any) => void,
    private onConnectionChange: (connected: boolean) => void
  ) {}
  
  connect() {
    this.ws = new WebSocket(this.url);
    
    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.onConnectionChange(true);
      this.flushQueue();
    };
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.onMessage(data);
    };
    
    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.onConnectionChange(false);
      this.scheduleReconnect();
    };
    
    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }
  
  send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      this.messageQueue.push(data);
    }
  }
  
  private flushQueue() {
    while (this.messageQueue.length > 0) {
      const data = this.messageQueue.shift();
      this.send(data);
    }
  }
  
  private scheduleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
    }
  }
}

// Hook: 使用交互管理
function useInteraction(sessionId: string) {
  const [pendingRequests, setPendingRequests] = useState<InteractionRequest[]>([]);
  const [recoveryState, setRecoveryState] = useState<RecoveryState | null>(null);
  
  const wsRef = useRef<InteractionWebSocket | null>(null);
  
  useEffect(() => {
    const ws = new InteractionWebSocket(
      `wss://api.example.com/ws/${sessionId}`,
      (data) => {
        switch (data.type) {
          case 'interaction_request':
            setPendingRequests(prev => [...prev, data.data]);
            break;
          
          case 'recovery_available':
            setRecoveryState(data.data);
            break;
          
          case 'session_restored':
            setRecoveryState(null);
            break;
        }
      },
      (connected) => {
        console.log('Connection status:', connected);
      }
    );
    
    ws.connect();
    wsRef.current = ws;
    
    // 检查恢复状态
    fetch(`/api/session/${sessionId}/recovery`)
      .then(res => res.json())
      .then(data => {
        if (data.has_recovery) {
          setRecoveryState(data.recovery_state);
        }
      });
    
    return () => {
      ws.disconnect?.();
    };
  }, [sessionId]);
  
  const respond = useCallback((response: InteractionResponse) => {
    wsRef.current?.send({
      type: 'interaction_response',
      data: response
    });
    setPendingRequests(prev => prev.filter(r => r.request_id !== response.request_id));
  }, []);
  
  const resumeSession = useCallback((mode: 'continue' | 'skip' | 'restart') => {
    wsRef.current?.send({
      type: 'resume_session',
      data: { mode }
    });
    setRecoveryState(null);
  }, []);
  
  return {
    pendingRequests,
    recoveryState,
    respond,
    resumeSession
  };
}
```

### 6.2 后端 API 设计

```python
"""
后端 API 路由设计
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter()


# REST API 端点

class SessionCreateRequest(BaseModel):
    agent_config: Dict[str, Any]
    initial_goal: str

class SessionCreateResponse(BaseModel):
    session_id: str
    websocket_url: str

@router.post("/session", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest):
    """创建新会话"""
    session_id = generate_session_id()
    
    # 检查是否有恢复状态
    has_recovery = await recovery_coordinator.has_recovery_state(session_id)
    
    # 创建会话
    await session_manager.create_session(
        session_id=session_id,
        agent_config=request.agent_config,
        initial_goal=request.initial_goal,
    )
    
    return SessionCreateResponse(
        session_id=session_id,
        websocket_url=f"wss://api.example.com/ws/{session_id}"
    )


class RecoveryStatusResponse(BaseModel):
    has_recovery: bool
    recovery_state: Optional[Dict[str, Any]]

@router.get("/session/{session_id}/recovery", response_model=RecoveryStatusResponse)
async def get_recovery_status(session_id: str):
    """获取恢复状态"""
    recovery_state = await recovery_coordinator.get_latest_recovery_state(session_id)
    
    return RecoveryStatusResponse(
        has_recovery=recovery_state is not None,
        recovery_state=recovery_state.to_dict() if recovery_state else None
    )


class ResumeRequest(BaseModel):
    mode: str  # "continue" / "skip" / "restart"

class ResumeResponse(BaseModel):
    success: bool
    message: str
    pending_interaction: Optional[Dict[str, Any]]

@router.post("/session/{session_id}/resume", response_model=ResumeResponse)
async def resume_session(session_id: str, request: ResumeRequest):
    """恢复会话"""
    result = await recovery_coordinator.recover(
        session_id=session_id,
        resume_mode=request.mode
    )
    
    return ResumeResponse(
        success=result.success,
        message=result.summary if result.success else result.error,
        pending_interaction=result.pending_interaction.to_dict() if result.pending_interaction else None
    )


class InteractionResponseRequest(BaseModel):
    request_id: str
    choice: Optional[str]
    choices: Optional[List[str]]
    input_value: Optional[str]
    files: Optional[List[str]]
    user_message: Optional[str]
    grant_scope: Optional[str]

@router.post("/session/{session_id}/interaction/respond")
async def respond_interaction(session_id: str, request: InteractionResponseRequest):
    """响应交互请求"""
    response = InteractionResponse(
        request_id=request.request_id,
        session_id=session_id,
        choice=request.choice,
        choices=request.choices or [],
        input_value=request.input_value,
        status=InteractionStatus.RESPONSED,
        user_message=request.user_message,
        grant_scope=request.grant_scope,
    )
    
    await interaction_gateway.deliver_response(response)
    
    return {"success": True}


# WebSocket 端点

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 连接端点"""
    await websocket.accept()
    
    # 注册连接
    connection_id = await ws_manager.register(session_id, websocket)
    
    try:
        # 发送恢复状态检查
        recovery_state = await recovery_coordinator.get_latest_recovery_state(session_id)
        if recovery_state:
            await websocket.send_json({
                "type": "recovery_available",
                "data": recovery_state.to_dict()
            })
        
        # 主消息循环
        while True:
            data = await websocket.receive_json()
            
            message_type = data.get("type")
            
            if message_type == "interaction_response":
                # 处理交互响应
                response = InteractionResponse.from_dict(data["data"])
                await interaction_gateway.deliver_response(response)
            
            elif message_type == "resume_session":
                # 恢复会话
                mode = data["data"].get("mode", "continue")
                result = await recovery_coordinator.recover(session_id, resume_mode=mode)
                
                await websocket.send_json({
                    "type": "session_resumed",
                    "data": {
                        "success": result.success,
                        "summary": result.summary
                    }
                })
                
                if result.success:
                    # 继续执行
                    asyncio.create_task(
                        continue_execution(session_id, result.recovery_context)
                    )
            
            elif message_type == "cancel_session":
                # 取消会话
                await session_manager.cancel_session(session_id)
                await websocket.send_json({
                    "type": "session_cancelled",
                    "data": {"session_id": session_id}
                })
    
    except WebSocketDisconnect:
        # 保存中断状态
        await create_interrupt_checkpoint(session_id, "user_disconnect")
    
    finally:
        await ws_manager.unregister(connection_id)


# 中断检查点创建
async def create_interrupt_checkpoint(session_id: str, reason: str):
    """创建中断检查点"""
    session = await session_manager.get_session(session_id)
    if session and session.is_running:
        await recovery_coordinator.create_checkpoint(
            session_id=session_id,
            execution_id=session.execution_id,
            step_index=session.current_step,
            phase="interrupted",
            context={"reason": reason},
            agent=session.agent,
        )
```

---

## 7. 协议定义

### 7.1 WebSocket 消息协议

```yaml
# WebSocket 消息格式

# 1. 交互请求（服务端 -> 客户端）
interaction_request:
  type: "interaction_request"
  data:
    request_id: "req_abc123"
    interaction_type: "ask" | "confirm" | "select" | "authorize" | "choose_plan"
    priority: "critical" | "high" | "normal" | "low"
    title: "需要您的输入"
    message: "请提供数据库连接信息"
    options:
      - label: "选项1"
        value: "option1"
        description: "选项描述"
        default: false
    timeout: 300
    default_choice: "option1"
    allow_cancel: true
    allow_skip: false
    allow_defer: true
    state_snapshot:
      # 完整状态快照
      step_index: 15
      conversation_history: [...]
      todo_list: [...]
      files_created: [...]
    context:
      # 额外上下文
      tool_name: "database"
      tool_args: {...}

# 2. 交互响应（客户端 -> 服务端）
interaction_response:
  type: "interaction_response"
  data:
    request_id: "req_abc123"
    choice: "option1"          # 单选
    choices: ["a", "b"]        # 多选
    input_value: "user input"  # 输入
    files: ["/path/to/file"]   # 文件
    user_message: "额外说明"
    grant_scope: "session"     # 授权范围
    status: "responsed"

# 3. 恢复可用通知（服务端 -> 客户端）
recovery_available:
  type: "recovery_available"
  data:
    recovery_id: "rec_xxx"
    session_id: "sess_xxx"
    checkpoint_id: "cp_xxx"
    interrupt_point:
      step_index: 15
      phase: "waiting_interaction"
      reason: "user_disconnect"
      created_at: "2026-02-27T10:00:00"
    original_goal: "实现用户登录功能"
    todo_list:
      - id: "todo1"
        content: "创建登录页面"
        status: "completed"
      - id: "todo2"
        content: "实现认证逻辑"
        status: "in_progress"
    files_created:
      - path: "/src/pages/login.tsx"
        content_hash: "abc123"
        created_at: "2026-02-27T09:30:00"
    conversation_history: [...]

# 4. 恢复会话请求（客户端 -> 服务端）
resume_session:
  type: "resume_session"
  data:
    mode: "continue" | "skip" | "restart"

# 5. 会话恢复成功（服务端 -> 客户端）
session_resumed:
  type: "session_resumed"
  data:
    success: true
    summary: "从第15步继续执行..."
    pending_interaction:
      # 等待响应的交互

# 6. 任务进度更新（服务端 -> 客户端）
progress_update:
  type: "progress_update"
  data:
    step_index: 16
    total_steps: 30
    phase: "executing"
    message: "正在处理..."
    todo_completed: 5
    todo_total: 10

# 7. 执行完成（服务端 -> 客户端）
execution_complete:
  type: "execution_complete"
  data:
    success: true
    result: "任务完成"
    files_created: [...]
    files_modified: [...]
    total_tokens: 50000
    duration_seconds: 300
```

### 7.2 HTTP API 协议

```yaml
# REST API 端点

# 创建会话
POST /api/session
Request:
  agent_config:
    name: "code-assistant"
    scene: "coding"
    llm:
      provider: "openai"
      model: "gpt-4"
  initial_goal: "实现用户登录功能"
Response:
  session_id: "sess_xxx"
  websocket_url: "wss://api.example.com/ws/sess_xxx"

# 获取恢复状态
GET /api/session/{session_id}/recovery
Response:
  has_recovery: true
  recovery_state:
    # 完整恢复状态

# 恢复会话
POST /api/session/{session_id}/resume
Request:
  mode: "continue"
Response:
  success: true
  message: "恢复成功"
  pending_interaction:
    # 待处理的交互请求

# 响应交互
POST /api/session/{session_id}/interaction/respond
Request:
  request_id: "req_xxx"
  choice: "option1"
  input_value: "..."
Response:
  success: true

# 获取会话历史
GET /api/session/{session_id}/history
Response:
  messages: [...]
  tool_calls: [...]
  decisions: [...]

# 获取 Todo 列表
GET /api/session/{session_id}/todos
Response:
  todos:
    - id: "todo1"
      content: "创建登录页面"
      status: "completed"
      created_at: "..."
```

---

## 8. 实现代码

### 8.1 完整的 InteractionGateway

```python
"""
InteractionGateway - 统一交互网关

管理所有交互请求的分发和响应收集
"""

class InteractionGateway:
    """
    交互网关
    
    职责：
    1. 接收来自 Agent 的交互请求
    2. 分发到对应的客户端
    3. 收集客户端响应
    4. 协调恢复流程
    """
    
    def __init__(
        self,
        ws_manager: WebSocketManager,
        state_store: StateStore,
        recovery_coordinator: RecoveryCoordinator,
    ):
        self.ws_manager = ws_manager
        self.state_store = state_store
        self.recovery_coordinator = recovery_coordinator
        
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._request_by_session: Dict[str, List[str]] = {}
    
    async def send(self, request: InteractionRequest) -> str:
        """发送交互请求"""
        # 存储请求
        await self.state_store.set(f"request:{request.request_id}", request.to_dict())
        
        # 记录到会话
        if request.session_id not in self._request_by_session:
            self._request_by_session[request.session_id] = []
        self._request_by_session[request.session_id].append(request.request_id)
        
        # 检查连接
        if await self.ws_manager.has_connection(request.session_id):
            await self.ws_manager.send_to_session(
                session_id=request.session_id,
                message={
                    "type": "interaction_request",
                    "data": request.to_dict()
                }
            )
        else:
            # 离线模式：保存待处理
            await self._save_pending_request(request)
        
        return request.request_id
    
    async def send_and_wait(
        self,
        request: InteractionRequest,
    ) -> InteractionResponse:
        """发送请求并等待响应"""
        future = asyncio.Future()
        self._pending_requests[request.request_id] = future
        
        await self.send(request)
        
        try:
            return await asyncio.wait_for(future, timeout=request.timeout)
        except asyncio.TimeoutError:
            return InteractionResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=InteractionStatus.TIMEOUT
            )
    
    async def deliver_response(self, response: InteractionResponse):
        """投递响应"""
        # 更新请求状态
        request_data = await self.state_store.get(f"request:{response.request_id}")
        if request_data:
            request_data["status"] = "responded"
            await self.state_store.set(f"request:{response.request_id}", request_data)
        
        # 触发等待的 Future
        if response.request_id in self._pending_requests:
            future = self._pending_requests.pop(response.request_id)
            if not future.done():
                future.set_result(response)
        
        # 如果有待恢复的任务
        if response.session_id:
            await self._check_and_resume(response)
    
    async def _check_and_resume(self, response: InteractionResponse):
        """检查并恢复执行"""
        session_id = response.session_id
        
        # 获取恢复状态
        recovery_state = await self.recovery_coordinator.get_latest_recovery_state(session_id)
        if recovery_state:
            # 从交互点恢复
            resume_result = await self.recovery_coordinator.resume_from_interaction(
                session_id=session_id,
                interaction_response=response
            )
            
            if resume_result.success:
                # 通知客户端恢复状态
                await self.ws_manager.send_to_session(
                    session_id=session_id,
                    message={
                        "type": "session_resumed",
                        "data": {
                            "success": True,
                            "checkpoint_id": resume_result.checkpoint_id
                        }
                    }
                )
                
                # 继续执行
                asyncio.create_task(
                    self._continue_execution(session_id, resume_result)
                )
    
    async def _continue_execution(self, session_id: str, resume_result: ResumeResult):
        """继续执行 Agent"""
        session = await session_manager.get_session(session_id)
        if session:
            # 注入恢复的响应
            session.agent.continue_with_response(resume_result.response)
            
            # 继续执行
            await session.agent.run_from_step(resume_result.step_index)
    
    async def _save_pending_request(self, request: InteractionRequest):
        """保存待处理请求（离线模式）"""
        pending_key = f"pending:{request.session_id}"
        pending = await self.state_store.get(pending_key) or []
        pending.append(request.to_dict())
        await self.state_store.set(pending_key, pending)
```

### 8.2 Agent 执行框架集成

```python
"""
Agent 执行框架集成示例

展示如何在 Core V1 和 Core V2 中集成交互和恢复能力
"""

# Core V1 集成
class ConversableAgentWithInteraction(ConversableAgent):
    """带交互能力的 ConversableAgent"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._interaction_adapter = None
        self._recovery_coordinator = None
    
    @property
    def interaction(self) -> InteractionAdapter:
        if self._interaction_adapter is None:
            self._interaction_adapter = InteractionAdapter(
                agent=self,
                gateway=get_interaction_gateway()
            )
        return self._interaction_adapter
    
    async def generate_reply(self, *args, **kwargs):
        """生成回复 - 增强版本"""
        # 恢复检查
        if self._check_recovery():
            recovery_result = await self._handle_recovery()
            if recovery_result.resume_mode == "continue":
                # 从恢复点继续
                return await self._resume_from_checkpoint(recovery_result)
        
        # 正常执行
        try:
            return await super().generate_reply(*args, **kwargs)
        
        except InteractionPendingError as e:
            # 交互请求_pending
            await self._create_interaction_checkpoint(e.request)
            raise
        
        except asyncio.CancelledError:
            # 用户取消
            await self._create_interrupt_checkpoint("user_cancel")
            raise
    
    async def act(self, message, sender, **kwargs):
        """执行动作 - 交互式版本"""
        tool_calls = self._parse_tool_calls(message)
        results = []
        
        for tool_call in tool_calls:
            # 交互式权限检查
            authorized = await self.interaction.request_tool_permission(
                tool_name=tool_call.name,
                tool_args=tool_call.args,
            )
            
            if not authorized:
                results.append(ActionOutput(
                    content=f"工具 {tool_call.name} 执行被用户拒绝",
                    is_exe_success=False,
                    name=tool_call.name,
                ))
                continue
            
            # 执行工具
            result = await self._execute_tool(tool_call)
            results.append(result)
            
            # 更新 Todo
            await self._update_todo_progress(tool_call)
        
        return results


# Core V2 集成
class SimpleAgentWithRecovery(SimpleAgent):
    """带恢复能力的 SimpleAgent"""
    
    def __init__(
        self,
        name: str,
        llm_adapter: LLMAdapter,
        tools: List[ToolBase],
        interaction_manager: Optional[EnhancedInteractionManager] = None,
        recovery_coordinator: Optional[RecoveryCoordinator] = None,
        **kwargs
    ):
        super().__init__(name, llm_adapter, tools, **kwargs)
        
        self.interaction = interaction_manager or EnhancedInteractionManager()
        self.recovery = recovery_coordinator or get_recovery_coordinator()
        
        # 恢复状态
        self._recovery_context: Optional[RecoveryContext] = None
    
    async def run(self, goal: str) -> AgentExecutionResult:
        """执行任务"""
        session_id = self._get_session_id()
        
        # 检查恢复
        recovery_state = await self.recovery.get_latest_recovery_state(session_id)
        if recovery_state:
            return await self._handle_recovery(goal, recovery_state)
        
        # 正常执行
        return await self._execute_with_checkpoints(goal)
    
    async def _execute_with_checkpoints(self, goal: str) -> AgentExecutionResult:
        """带检查点的执行"""
        step = 0
        
        while step < self.max_steps:
            # 创建检查点
            if step % self.checkpoint_interval == 0:
                await self.recovery.create_checkpoint(
                    session_id=self._session_id,
                    execution_id=self._execution_id,
                    step_index=step,
                    phase="executing",
                    context={},
                    agent=self,
                )
            
            try:
                # 思考阶段
                thinking = await self.think(self._build_messages())
                thinking_content = "".join([chunk async for chunk in thinking])
                
                # 解析工具调用
                tool_calls = self._parse_tool_calls(thinking_content)
                
                if not tool_calls:
                    # 无工具调用，任务完成
                    break
                
                # 动作阶段
                for tool_call in tool_calls:
                    # 交互式权限检查
                    permission = await self.interaction.request_authorization_smart(
                        tool_name=tool_call.name,
                        tool_args=tool_call.args,
                        snapshot=await self._get_snapshot(),
                    )
                    
                    if not permission.granted:
                        # 用户拒绝
                        self._messages.append({
                            "role": "system",
                            "content": f"用户拒绝了工具 {tool_call.name} 的执行"
                        })
                        continue
                    
                    # 执行工具
                    result = await self._execute_tool(tool_call)
                    
                    # 更新 Todo
                    self._update_todos(tool_call, result)
                
                step += 1
            
            except InteractionPendingError as e:
                # 在交互点创建检查点
                await self.recovery.create_interaction_checkpoint(
                    session_id=self._session_id,
                    execution_id=self._execution_id,
                    interaction_request=e.request,
                    agent=self,
                )
                raise
            
            except asyncio.CancelledError:
                # 用户取消
                await self.recovery.create_checkpoint(
                    session_id=self._session_id,
                    execution_id=self._execution_id,
                    step_index=step,
                    phase="cancelled",
                    context={"reason": "user_cancel"},
                    agent=self,
                )
                raise
        
        return AgentExecutionResult(
            success=True,
            answer=self._get_final_answer(),
            steps=step,
            files_created=self._get_created_files(),
            todos=self._get_todos(),
        )
    
    async def _handle_recovery(
        self,
        goal: str,
        recovery_state: RecoveryState,
    ) -> AgentExecutionResult:
        """处理恢复"""
        # 通过交互让用户选择恢复模式
        resume_mode = await self.interaction.select(
            message="发现未完成的任务，请选择处理方式：",
            options=[
                {"label": "继续执行", "value": "continue", "description": "从中断点继续"},
                {"label": "跳过当前步骤", "value": "skip", "description": "跳过等待中的交互"},
                {"label": "重新开始", "value": "restart", "description": "从任务开始重新执行"},
            ],
            title="任务恢复",
        )
        
        if resume_mode == "restart":
            return await self._execute_with_checkpoints(goal)
        
        # 恢复状态
        self._messages = recovery_state.conversation_history
        self._variables = recovery_state.variables
        self._todos = recovery_state.todo_list
        
        if resume_mode == "continue" and recovery_state.pending_interactions:
            # 有待响应的交互
            pending = recovery_state.pending_interactions[0]
            # 等待用户响应
            await self.interaction.send(pending)
        
        # 从断点继续
        return await self._execute_with_checkpoints_from(
            step_index=recovery_state.interrupt_point.step_index
        )
```

---

## 9. Todo/Kanban 恢复机制

### 9.1 Todo 管理器设计

```python
"""
TodoManager - 任务列表管理器

管理执行过程中的任务列表，支持中断恢复
"""

@dataclass
class TodoItem:
    """Todo 项目"""
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed", "blocked", "failed"]
    priority: int
    dependencies: List[str]  # 依赖的其他 Todo ID
    result: Optional[str]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    metadata: Dict[str, Any]

class TodoManager:
    """
    Todo 管理器
    
    功能：
    1. 任务分解与依赖管理
    2. 状态跟踪与持久化
    3. 中断恢复支持
    4. Kanban 视图生成
    """
    
    def __init__(
        self,
        session_id: str,
        state_store: Optional[StateStore] = None,
    ):
        self.session_id = session_id
        self.state_store = state_store or get_default_state_store()
        
        self._todos: Dict[str, TodoItem] = {}
        self._todo_order: List[str] = []
    
    async def create_todo(
        self,
        content: str,
        priority: int = 0,
        dependencies: Optional[List[str]] = None,
    ) -> str:
        """创建 Todo"""
        todo_id = f"todo_{uuid.uuid4().hex[:8]}"
        
        todo = TodoItem(
            id=todo_id,
            content=content,
            status="pending",
            priority=priority,
            dependencies=dependencies or [],
            result=None,
            error=None,
            created_at=datetime.now(),
            started_at=None,
            completed_at=None,
            metadata={},
        )
        
        self._todos[todo_id] = todo
        self._todo_order.append(todo_id)
        
        await self._persist()
        
        return todo_id
    
    async def start_todo(self, todo_id: str):
        """开始执行 Todo"""
        if todo_id in self._todos:
            self._todos[todo_id].status = "in_progress"
            self._todos[todo_id].started_at = datetime.now()
            await self._persist()
    
    async def complete_todo(self, todo_id: str, result: Optional[str] = None):
        """完成 Todo"""
        if todo_id in self._todos:
            self._todos[todo_id].status = "completed"
            self._todos[todo_id].result = result
            self._todos[todo_id].completed_at = datetime.now()
            await self._persist()
            
            # 尝试解锁阻塞的 Todo
            await self._check_blocked_todos()
    
    async def block_todo(self, todo_id: str, reason: str):
        """阻塞 Todo"""
        if todo_id in self._todos:
            self._todos[todo_id].status = "blocked"
            self._todos[todo_id].error = reason
            await self._persist()
    
    async def fail_todo(self, todo_id: str, error: str):
        """Todo 失败"""
        if todo_id in self._todos:
            self._todos[todo_id].status = "failed"
            self._todos[todo_id].error = error
            self._todos[todo_id].completed_at = datetime.now()
            await self._persist()
    
    def get_next_todo(self) -> Optional[TodoItem]:
        """获取下一个可执行的 Todo"""
        for todo_id in self._todo_order:
            todo = self._todos[todo_id]
            if todo.status == "pending":
                # 检查依赖是否完成
                if self._dependencies_met(todo):
                    return todo
        return None
    
    def get_todos_by_status(self, status: str) -> List[TodoItem]:
        """按状态获取 Todo"""
        return [t for t in self._todos.values() if t.status == status]
    
    def get_kanban_view(self) -> Dict[str, List[TodoItem]]:
        """获取 Kanban 视图"""
        return {
            "pending": self.get_todos_by_status("pending"),
            "in_progress": self.get_todos_by_status("in_progress"),
            "completed": self.get_todos_by_status("completed"),
            "blocked": self.get_todos_by_status("blocked"),
            "failed": self.get_todos_by_status("failed"),
        }
    
    def get_progress(self) -> Tuple[int, int]:
        """获取进度"""
        total = len(self._todos)
        completed = len(self.get_todos_by_status("completed"))
        return completed, total
    
    def get_recovery_summary(self) -> str:
        """获取恢复摘要"""
        completed, total = self.get_progress()
        pending = len(self.get_todos_by_status("pending"))
        blocked = len(self.get_todos_by_status("blocked"))
        failed = len(self.get_todos_by_status("failed"))
        
        lines = [
            "## 任务进度概览",
            "",
            f"- 总任务数: {total}",
            f"- 已完成: {completed}",
            f"- 进行中: {len(self.get_todos_by_status('in_progress'))}",
            f"- 待处理: {pending}",
            f"- 已阻塞: {blocked}",
            f"- 已失败: {failed}",
            "",
        ]
        
        # 未完成的任务详情
        unfinished = [
            t for t in self._todos.values()
            if t.status not in ["completed"]
        ]
        
        if unfinished:
            lines.append("### 待处理任务")
            for t in unfinished[:10]:
                status_icon = {
                    "pending": "⏳",
                    "in_progress": "🔄",
                    "blocked": "🚫",
                    "failed": "❌",
                }.get(t.status, "•")
                lines.append(f"{status_icon} {t.content}")
        
        return "\n".join(lines)
    
    def _dependencies_met(self, todo: TodoItem) -> bool:
        """检查依赖是否满足"""
        for dep_id in todo.dependencies:
            if dep_id in self._todos:
                if self._todos[dep_id].status != "completed":
                    return False
        return True
    
    async def _check_blocked_todos(self):
        """检查并解锁阻塞的 Todo"""
        for todo in self._todos.values():
            if todo.status == "blocked":
                if self._dependencies_met(todo):
                    todo.status = "pending"
                    todo.error = None
        await self._persist()
    
    async def _persist(self):
        """持久化 Todo 列表"""
        data = {
            "session_id": self.session_id,
            "todos": [t.to_dict() for t in self._todos.values()],
            "order": self._todo_order,
        }
        await self.state_store.set(f"todos:{self.session_id}", data)
    
    @classmethod
    async def restore(cls, session_id: str, state_store: StateStore) -> "TodoManager":
        """从持久化恢复"""
        manager = cls(session_id, state_store)
        
        data = await state_store.get(f"todos:{session_id}")
        if data:
            manager._todo_order = data.get("order", [])
            for t in data.get("todos", []):
                manager._todos[t["id"]] = TodoItem(**t)
        
        return manager
```

### 9.2 Kanban 集成

```python
"""
KanbanIntegration - Kanban 系统集成

将 Todo 系统与前端 Kanban 视图集成
"""

class KanbanIntegration:
    """
    Kanban 集成
    
    功能：
    1. 实时同步 Todo 状态到前端
    2. 支持拖拽排序
    3. 支持前端手动操作
    """
    
    def __init__(
        self,
        todo_manager: TodoManager,
        ws_manager: WebSocketManager,
    ):
        self.todo_manager = todo_manager
        self.ws_manager = ws_manager
    
    async def sync_to_frontend(self):
        """同步到前端"""
        kanban_view = self.todo_manager.get_kanban_view()
        
        await self.ws_manager.send_to_session(
            session_id=self.todo_manager.session_id,
            message={
                "type": "kanban_update",
                "data": {
                    "columns": {
                        "pending": [self._format_todo(t) for t in kanban_view["pending"]],
                        "in_progress": [self._format_todo(t) for t in kanban_view["in_progress"]],
                        "completed": [self._format_todo(t) for t in kanban_view["completed"]],
                        "blocked": [self._format_todo(t) for t in kanban_view["blocked"]],
                    },
                    "progress": self.todo_manager.get_progress(),
                }
            }
        )
    
    async def handle_frontend_action(self, action: Dict):
        """处理前端操作"""
        action_type = action.get("type")
        
        if action_type == "move_todo":
            # 移动 Todo（拖拽）
            todo_id = action["todo_id"]
            new_status = action["new_status"]
            
            if new_status == "in_progress":
                await self.todo_manager.start_todo(todo_id)
            elif new_status == "completed":
                await self.todo_manager.complete_todo(todo_id)
            
            await self.sync_to_frontend()
        
        elif action_type == "add_todo":
            # 添加 Todo
            content = action["content"]
            priority = action.get("priority", 0)
            await self.todo_manager.create_todo(content, priority)
            await self.sync_to_frontend()
        
        elif action_type == "edit_todo":
            # 编辑 Todo
            todo_id = action["todo_id"]
            if todo_id in self.todo_manager._todos:
                self.todo_manager._todos[todo_id].content = action["content"]
                await self.todo_manager._persist()
            await self.sync_to_frontend()
    
    def _format_todo(self, todo: TodoItem) -> Dict:
        """格式化 Todo 用于前端展示"""
        return {
            "id": todo.id,
            "content": todo.content,
            "status": todo.status,
            "priority": todo.priority,
            "dependencies": todo.dependencies,
            "result": todo.result,
            "created_at": todo.created_at.isoformat(),
            "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
        }
```

---

## 10. 总结

### 10.1 实现路径

```
阶段 1: 基础交互能力
├── 实现 InteractionGateway
├── 实现 WebSocket 消息协议
├── 前端交互组件开发
└── 基础权限交互

阶段 2: 状态持久化
├── 实现 StateStore
├── 实现检查点机制
├── 实现文件存储
└── 会话管理

阶段 3: 恢复机制
├── 实现 RecoveryCoordinator
├── 集成到 Core V1 Agent
├── 集成到 Core V2 Agent
└── 测试中断恢复

阶段 4: Todo/Kanban
├── 实现 TodoManager
├── 前端 Kanban 组件
├── 双向同步
└── 恢复集成

阶段 5: 生产就绪
├── 性能优化
├── 错误处理
├── 监控告警
└── 文档完善
```

### 10.2 关键特性总结

| 特性 | 描述 | 状态 |
|------|------|------|
| Agent 主动提问 | 缺少信息时主动询问用户 | 设计完成 |
| 工具授权请求 | 敏感操作前请求用户确认 | 设计完成 |
| 方案选择 | 提供多方案供用户选择 | 设计完成 |
| 进度通知 | 实时推送任务进度 | 设计完成 |
| 任意点中断 | 用户可在任意时刻中断 | 设计完成 |
| 完美恢复 | 恢复所有上下文和状态 | 设计完成 |
| Todo 恢复 | 未完成任务可继续 | 设计完成 |
| Kanban 视图 | 可视化任务进度 | 设计完成 |
| 文件恢复 | 恢复创建/修改的文件 | 设计完成 |
| 多端同步 | 支持多设备同时使用 | 设计完成 |

---

**文档版本**: v1.0  
**创建日期**: 2026-02-27  
**作者**: DERISK Team