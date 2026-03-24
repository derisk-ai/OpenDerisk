# Agent架构全面重构方案

## 执行摘要

基于对opencode (111k stars) 和 openclaw (230k stars) 两大顶级开源项目的深度对比分析,本文档提出了OpenDeRisk Agent系统的全面重构方案。方案涵盖Agent构建、运行时、可视化、用户交互、工具系统、流程控制、循环控制等8大核心领域,旨在构建一个生产级、可扩展、高可用的AI Agent平台。

## 一、架构设计对比总结

### 1.1 核心差异矩阵

| 设计维度 | OpenCode | OpenClaw | 差异分析 | 推荐方案 |
|---------|----------|----------|---------|----------|
| **架构模式** | Client/Server + TUI | Gateway + Multi-Client | OpenCode简单直接,OpenClaw可扩展 | Gateway分层架构 |
| **Agent定义** | Zod Schema + 配置 | Scope + Routing | OpenCode类型安全,OpenClaw灵活 | Pydantic Schema + 配置 |
| **状态管理** | SQLite本地存储 | 文件系统 + 内存 | OpenCode有ACID优势 | SQLite + 文件系统混合 |
| **执行模型** | 单线程Stream | RPC + Queue | OpenClaw更可扩展 | WebSocket + Queue模式 |
| **权限控制** | Permission Ruleset | Session Sandbox | OpenCode粒度更细 | Permission Ruleset + Sandbox |
| **渠道支持** | CLI + TUI | 12+消息平台 | OpenClaw渠道丰富 | 抽象Channel层 |
| **沙箱执行** | 无 | Docker Sandbox | OpenClaw安全优势 | Docker Sandbox |
| **工具组合** | Batch + Task | 无内置 | OpenCode组合能力强 | 工具组合器模式 |
| **LSP集成** | 完整集成 | 无 | OpenCode代码智能强 | 可选LSP集成 |
| **可视化** | TUI | Web + Canvas | OpenClaw可视化强 | Web推送 + Canvas |

### 1.2 最佳实践提取

#### 从OpenCode学习
1. **Zod Schema工具定义** - 类型安全 + 自动校验
2. **Permission Ruleset模式** - 精细的allow/deny/ask控制
3. **工具组合模式** - Batch并行 + Task委派
4. **Compaction机制** - 长对话上下文管理
5. **配置驱动** - Markdown/JSON双模式定义

#### 从OpenClaw学习
1. **Gateway控制平面** - 中心化服务架构
2. **Channel抽象** - 统一消息接口
3. **Docker沙箱** - 安全隔离执行
4. **Auth Profile轮换** - API密钥故障转移
5. **Node设备概念** - 跨设备能力扩展
6. **实时可视化** - Block Streaming + WebSocket

## 二、全面重构方案

### 2.1 整体架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                          Client Layer                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │   CLI    │  │   Web    │  │  API     │  │  Mobile  │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
└───────┼─────────────┼─────────────┼─────────────┼─────────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                             │
                    WebSocket / HTTP API
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Gateway Control Plane                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Session    │  │   Channel    │  │   Presence   │        │
│  │   Manager    │  │   Router     │  │   Service    │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Queue      │  │   Auth       │  │   Config     │        │
│  │   Manager    │  │   Manager    │  │   Manager    │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    RPC / Queue Message
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                       Agent Runtime Layer                        │
│  ┌────────────────────────────────────────────────────────┐   │
│  │                  Agent Orchestrator                     │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │   │
│  │  │ Planning │  │ Thinking │  │  Acting  │           │   │
│  │  │   Phase  │  │   Phase  │  │   Phase  │           │   │
│  │  └──────────┘  └──────────┘  └──────────┘           │   │
│  └────────────────────────────────────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │  Permission  │  │    Tool      │  │   Memory     │        │
│  │   System     │  │   System     │  │   System     │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    Tool Execution
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                       Tool Execution Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Local      │  │   Docker     │  │   Remote     │        │
│  │   Sandbox    │  │   Sandbox    │  │   Sandbox    │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              Tool Registry & Executor                 │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │    │
│  │  │  Bash   │ │  Code   │ │ Browser │ │  MCP    │  │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │    │
│  └──────────────────────────────────────────────────────────┘┘
└────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件设计

## 三、Agent构建重构

### 3.1 AgentInfo配置模型

参考OpenCode的Zod Schema设计,使用Pydantic实现类型安全的Agent定义。

```python
# packages/derisk-serve/src/derisk_serve/agent/core/agent_info.py

from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum

class AgentMode(str, Enum):
    PRIMARY = "primary"      # 主Agent
    SUBAGENT = "subagent"    # 子Agent
    UTILITY = "utility"      # 工具Agent

class PermissionAction(str, Enum):
    ALLOW = "allow"          # 允许
    DENY = "deny"            # 拒绝
    ASK = "ask"              # 询问用户

class PermissionRule(BaseModel):
    """权限规则 - 参考OpenCode的Permission Ruleset"""
    tool_pattern: str        # 工具名称模式,支持通配符
    action: PermissionAction
    
class PermissionRuleset(BaseModel):
    """权限规则集"""
    rules: Dict[str, PermissionRule] = Field(default_factory=dict)
    default_action: PermissionAction = PermissionAction.ASK
    
    def check(self, tool_name: str) -> PermissionAction:
        """检查工具权限"""
        for pattern, rule in self.rules.items():
            if self._match_pattern(pattern, tool_name):
                return rule.action
        return self.default_action
    
    @staticmethod
    def _match_pattern(pattern: str, tool_name: str) -> bool:
        """匹配工具名称模式"""
        import fnmatch
        return fnmatch.fnmatch(tool_name, pattern)

class AgentInfo(BaseModel):
    """Agent配置信息 - 参考OpenCode的Agent.Info"""
    name: str                          # Agent名称
    description: Optional[str] = None  # 描述
    mode: AgentMode = AgentMode.PRIMARY
    hidden: bool = False               # 是否隐藏
    model_id: Optional[str] = None     # 独立模型配置
    provider_id: Optional[str] = None  # 模型提供者
    
    # 模型参数
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    
    # 执行限制
    max_steps: Optional[int] = Field(default=20, description="最大执行步骤数")
    timeout: Optional[int] = Field(default=300, description="超时时间(秒)")
    
    # 权限控制
    permission: PermissionRuleset = Field(default_factory=PermissionRuleset)
    
    # 颜色标识(用于可视化)
    color: Optional[str] = Field(default="#4A90E2")
    
    # 自定义选项
    options: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True

# 内置Agent定义
PRIMARY_AGENT = AgentInfo(
    name="primary",
    description="主Agent - 执行核心任务",
    mode=AgentMode.PRIMARY,
    permission=PermissionRuleset(
        rules={
            "*": PermissionRule(tool_pattern="*", action=PermissionAction.ALLOW),
            "*.env": PermissionRule(tool_pattern="*.env", action=PermissionAction.ASK),
            "doom_loop": PermissionRule(tool_pattern="doom_loop", action=PermissionAction.ASK),
        },
        default_action=PermissionAction.ALLOW
    )
)

PLAN_AGENT = AgentInfo(
    name="plan",
    description="规划Agent - 只读分析和探索",
    mode=AgentMode.PRIMARY,
    permission=PermissionRuleset(
        rules={
            "read": PermissionRule(tool_pattern="read", action=PermissionAction.ALLOW),
            "glob": PermissionRule(tool_pattern="glob", action=PermissionAction.ALLOW),
            "grep": PermissionRule(tool_pattern="grep", action=PermissionAction.ALLOW),
            "write": PermissionRule(tool_pattern="write", action=PermissionAction.DENY),
            "edit": PermissionRule(tool_pattern="edit", action=PermissionAction.DENY),
            "bash": PermissionRule(tool_pattern="bash", action=PermissionAction.ASK),
        },
        default_action=PermissionAction.DENY
    )
)

EXPLORE_SUBAGENT = AgentInfo(
    name="explore",
    description="代码库探索子Agent",
    mode=AgentMode.SUBAGENT,
    hidden=False,
    max_steps=10,
    permission=PermissionRuleset(
        rules={
            "read": PermissionRule(tool_pattern="read", action=PermissionAction.ALLOW),
            "glob": PermissionRule(tool_pattern="glob", action=PermissionAction.ALLOW),
            "grep": PermissionRule(tool_pattern="grep", action=PermissionAction.ALLOW),
        },
        default_action=PermissionAction.DENY
    )
)
```

### 3.2 Agent接口简化

```python
# packages/derisk-serve/src/derisk_serve/agent/core/agent_base.py

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Dict, Any
from .agent_info import AgentInfo

class AgentBase(ABC):
    """Agent基类 - 简化接口,配置驱动"""
    
    def __init__(self, info: AgentInfo):
        self.info = info
        self._state: Dict[str, Any] = {}
        
    @abstractmethod
    async def send(self, message: str, **kwargs) -> None:
        """发送消息到Agent"""
        pass
    
    @abstractmethod
    async def receive(self) -> AsyncIterator[str]:
        """接收Agent响应(流式)"""
        pass
    
    @abstractmethod
    async def thinking(self, prompt: str) -> AsyncIterator[str]:
        """思考过程(流式输出)"""
        pass
    
    @abstractmethod
    async def act(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """执行工具动作"""
        pass
    
    def check_permission(self, tool_name: str) -> bool:
        """检查工具权限"""
        action = self.info.permission.check(tool_name)
        return action in [PermissionAction.ALLOW, PermissionAction.ASK]
    
    @property
    def state(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return self._state.copy()
```

## 四、Agent运行时重构

### 4.1 Gateway控制平面

```python
# packages/derisk-serve/src/derisk_serve/agent/gateway/gateway.py

import asyncio
from typing import Dict, Optional
import websockets
from ..core.agent_info import AgentInfo

class Gateway:
    """Gateway控制平面 - 参考OpenClaw Gateway设计"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 18789):
        self.host = host
        self.port = port
        self.sessions: Dict[str, Session] = {}
        self.channels: Dict[str, Channel] = {}
        self.queue = asyncio.Queue()
        self.presence_service = PresenceService()
        
    async def start(self):
        """启动Gateway"""
        await websockets.serve(self._handle_connection, self.host, self.port)
        
    async def _handle_connection(self, websocket, path):
        """处理WebSocket连接"""
        # 1. 认证
        client = await self._authenticate(websocket)
        
        # 2. 创建Session
        session = await self._create_session(client)
        
        # 3. 消息循环
        async for message in websocket:
            await self.queue.put((session.id, message))
            
    async def _create_session(self, client) -> Session:
        """创建Session"""
        session = Session(
            id=self._generate_session_id(),
            client=client,
            agent_info=self._get_agent_for_client(client)
        )
        self.sessions[session.id] = session
        return session
        
    def _get_agent_for_client(self, client) -> AgentInfo:
        """根据客户端路由到对应的Agent"""
        # 实现channel/account到agent的映射
        pass

class Session:
    """Session - 隔离的对话上下文"""
    
    def __init__(self, id: str, client, agent_info: AgentInfo):
        self.id = id
        self.client = client
        self.agent_info = agent_info
        self.messages: list = []
        self.state: Dict[str, Any] = {}
        self.queue = asyncio.Queue()
        
class Channel:
    """Channel抽象 - 统一消息接口"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        
    async def send(self, message: str):
        """发送消息到渠道"""
        pass
        
    async def receive(self) -> AsyncIterator[str]:
        """从渠道接收消息"""
        pass

class PresenceService:
    """Presence服务 - 在线状态管理"""
    
    def __init__(self):
        self.online_clients: Dict[str, Dict] = {}
        
    def set_online(self, client_id: str, metadata: Dict):
        """设置客户端在线"""
        self.online_clients[client_id] = metadata
        
    def set_offline(self, client_id: str):
        """设置客户端离线"""
        self.online_clients.pop(client_id, None)
```

### 4.2 执行循环优化

```python
# packages/derisk-serve/src/derisk_serve/agent/core/agent_executor.py

import asyncio
from typing import AsyncIterator, Dict, Any, Optional
from .agent_info import AgentInfo, PermissionAction
from .agent_base import AgentBase

class AgentExecutor:
    """Agent执行器 - 优化执行循环"""
    
    def __init__(self, agent: AgentBase):
        self.agent = agent
        self.step_count = 0
        self.retry_count = 0
        self.max_retry = 3
        
    async def generate_reply(
        self, 
        message: str,
        stream: bool = True
    ) -> AsyncIterator[str]:
        """生成回复 - 简化逻辑"""
        self.step_count = 0
        
        while self.step_count < self.agent.info.max_steps:
            try:
                # 1. 思考阶段
                thinking = self.agent.thinking(message)
                async for chunk in thinking:
                    yield f"[THINKING] {chunk}"
                    
                # 2. 决策阶段
                decision = await self._make_decision(message)
                
                if decision["type"] == "response":
                    # 直接回复
                    yield decision["content"]
                    break
                    
                elif decision["type"] == "tool_call":
                    # 工具调用
                    result = await self._execute_tool(
                        decision["tool_name"],
                        decision["tool_args"]
                    )
                    message = self._format_tool_result(result)
                    self.step_count += 1
                    
                elif decision["type"] == "subagent":
                    # 子Agent委派
                    result = await self._delegate_to_subagent(
                        decision["subagent"],
                        decision["task"]
                    )
                    message = self._format_subagent_result(result)
                    self.step_count += 1
                    
            except Exception as e:
                self.retry_count += 1
                if self.retry_count >= self.max_retry:
                    yield f"[ERROR] 执行失败: {str(e)}"
                    break
                await asyncio.sleep(2 ** self.retry_count)  # 指数退避
                
    async def _execute_tool(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any]
    ) -> Any:
        """执行工具 - 集成权限检查"""
        # 1. 权限检查
        action = self.agent.info.permission.check(tool_name)
        
        if action == PermissionAction.DENY:
            raise PermissionError(f"工具 {tool_name} 被拒绝执行")
            
        if action == PermissionAction.ASK:
            # 请求用户确认
            approved = await self._ask_user_permission(tool_name, tool_args)
            if not approved:
                raise PermissionError(f"用户拒绝了工具 {tool_name} 的执行")
                
        # 2. 执行工具
        result = await self.agent.act(tool_name, tool_args)
        
        # 3. 沙箱隔离(可选)
        if self._should_sandbox(tool_name):
            result = await self._execute_in_sandbox(tool_name, tool_args)
            
        return result
```

## 五、工具系统重构

### 5.1 Tool定义模式

```python
# packages/derisk-serve/src/derisk_serve/agent/tools/tool_base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel

class ToolMetadata(BaseModel):
    """工具元数据"""
    name: str
    description: str
    category: str
    risk_level: str = "medium"  # low/medium/high
    requires_permission: bool = True

class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    output: Any
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None

class ToolBase(ABC):
    """工具基类 - 参考OpenCode的Tool定义"""
    
    def __init__(self):
        self.metadata = self._define_metadata()
        self.parameters = self._define_parameters()
        
    @abstractmethod
    def _define_metadata(self) -> ToolMetadata:
        """定义工具元数据"""
        pass
        
    @abstractmethod
    def _define_parameters(self) -> Dict[str, Any]:
        """定义工具参数(Schema)"""
        pass
        
    @abstractmethod
    async def execute(self, args: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        pass
        
    def validate_args(self, args: Dict[str, Any]) -> bool:
        """验证参数"""
        from pydantic import ValidationError
        try:
            # 使用Pydantic验证
            return True
        except ValidationError:
            return False

# 工具注册表
class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}
        
    def register(self, tool: ToolBase):
        """注册工具"""
        self._tools[tool.metadata.name] = tool
        
    def get(self, name: str) -> Optional[ToolBase]:
        """获取工具"""
        return self._tools.get(name)
        
    def list_by_category(self, category: str) -> list:
        """按类别列出工具"""
        return [
            tool for tool in self._tools.values()
            if tool.metadata.category == category
        ]

# 全局注册表
tool_registry = ToolRegistry()
```

### 5.2 核心工具实现

```python
# packages/derisk-serve/src/derisk_serve/agent/tools/bash_tool.py

from .tool_base import ToolBase, ToolMetadata, ToolResult
from typing import Dict, Any
import asyncio

class BashTool(ToolBase):
    """Bash工具 - 多环境执行"""
    
    def _define_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="bash",
            description="执行Shell命令",
            category="system",
            risk_level="high",
            requires_permission=True
        )
        
    def _define_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令"
                },
                "timeout": {
                    "type": "integer",
                    "default": 120,
                    "description": "超时时间(秒)"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录"
                },
                "sandbox": {
                    "type": "string",
                    "enum": ["local", "docker", "remote"],
                    "default": "local",
                    "description": "执行环境"
                }
            },
            "required": ["command"]
        }
        
    async def execute(
        self, 
        args: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> ToolResult:
        sandbox = args.get("sandbox", "local")
        command = args["command"]
        timeout = args.get("timeout", 120)
        cwd = args.get("cwd")
        
        if sandbox == "docker":
            return await self._execute_in_docker(command, cwd, timeout)
        elif sandbox == "remote":
            return await self._execute_remote(command, cwd, timeout)
        else:
            return await self._execute_local(command, cwd, timeout)
            
    async def _execute_local(
        self, 
        command: str, 
        cwd: str, 
        timeout: int
    ) -> ToolResult:
        """本地执行"""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            
            return ToolResult(
                success=proc.returncode == 0,
                output=stdout.decode(),
                metadata={
                    "return_code": proc.returncode,
                    "stderr": stderr.decode()
                }
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"命令执行超时({timeout}秒)"
            )
            
    async def _execute_in_docker(
        self, 
        command: str, 
        cwd: str, 
        timeout: int
    ) -> ToolResult:
        """Docker沙箱执行 - 参考OpenClaw"""
        import docker
        
        client = docker.from_env()
        container = client.containers.run(
            "python:3.11",
            command=f"sh -c '{command}'",
            volumes={cwd: {"bind": "/workspace", "mode": "rw"}},
            working_dir="/workspace",
            detach=True
        )
        
        try:
            result = container.wait(timeout=timeout)
            logs = container.logs().decode()
            
            return ToolResult(
                success=result["StatusCode"] == 0,
                output=logs
            )
        finally:
            container.remove()

# 注册工具
tool_registry.register(BashTool())
```

### 5.3 Skill系统

```python
# packages/derisk-serve/src/derisk_serve/agent/skills/skill_base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from pydantic import BaseModel

class SkillMetadata(BaseModel):
    """技能元数据"""
    name: str
    version: str
    description: str
    author: str
    tools: List[str]  # 需要的工具
    tags: List[str]

class SkillBase(ABC):
    """技能基类 - 参考OpenClaw Skills"""
    
    def __init__(self):
        self.metadata = self._define_metadata()
        
    @abstractmethod
    def _define_metadata(self) -> SkillMetadata:
        """定义技能元数据"""
        pass
        
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能"""
        pass
        
    def get_required_tools(self) -> List[str]:
        """获取需要的工具"""
        return self.metadata.tools

# 技能注册表
class SkillRegistry:
    """技能注册表"""
    
    def __init__(self):
        self._skills: Dict[str, SkillBase] = {}
        
    def register(self, skill: SkillBase):
        """注册技能"""
        self._skills[skill.metadata.name] = skill
        
    async def install_skill(self, skill_name: str, source: str):
        """安装技能"""
        # 从ClawHub或其他源安装
        pass

skill_registry = SkillRegistry()
```

## 六、可视化增强

### 6.1 实时进度推送

```python
# packages/derisk-serve/src/derisk_serve/agent/visualization/progress.py

from typing import Dict, Any, Optional
from enum import Enum
import asyncio

class ProgressType(str, Enum):
    THINKING = "thinking"
    TOOL_EXECUTION = "tool_execution"
    SUBAGENT = "subagent"
    ERROR = "error"
    SUCCESS = "success"

class ProgressEvent:
    """进度事件"""
    
    def __init__(
        self,
        type: ProgressType,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        percent: Optional[int] = None
    ):
        self.type = type
        self.message = message
        self.details = details or {}
        self.percent = percent
        self.timestamp = asyncio.get_event_loop().time()

class ProgressBroadcaster:
    """进度广播器"""
    
    def __init__(self, session_id: str, gateway):
        self.session_id = session_id
        self.gateway = gateway
        self._subscribers = []
        
    async def broadcast(self, event: ProgressEvent):
        """广播进度事件"""
        message = {
            "type": "progress",
            "session_id": self.session_id,
            "event": {
                "type": event.type,
                "message": event.message,
                "details": event.details,
                "percent": event.percent,
                "timestamp": event.timestamp
            }
        }
        
        # 通过WebSocket推送
        await self.gateway.send_to_session(self.session_id, message)
        
    async def thinking(self, content: str):
        """思考过程可视化"""
        await self.broadcast(ProgressEvent(
            type=ProgressType.THINKING,
            message=content
        ))
        
    async def tool_execution(
        self, 
        tool_name: str, 
        args: Dict[str, Any],
        status: str
    ):
        """工具执行可视化"""
        await self.broadcast(ProgressEvent(
            type=ProgressType.TOOL_EXECUTION,
            message=f"执行工具: {tool_name}",
            details={
                "tool_name": tool_name,
                "args": args,
                "status": status
            }
        ))
```

### 6.2 Canvas可视化

```python
# packages/derisk-serve/src/derisk_serve/agent/visualization/canvas.py

from typing import Dict, Any, List
from pydantic import BaseModel

class CanvasElement(BaseModel):
    """Canvas元素"""
    id: str
    type: str  # text/code/chart/table/image
    content: Any
    position: Dict[str, int]
    style: Dict[str, Any] = {}

class Canvas:
    """Canvas可视化工作区 - 参考OpenClaw Canvas"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.elements: Dict[str, CanvasElement] = {}
        
    async def render(self, element: CanvasElement):
        """渲染元素"""
        self.elements[element.id] = element
        await self._push_update(element)
        
    async def clear(self):
        """清空Canvas"""
        self.elements.clear()
        await self._push_clear()
        
    async def snapshot(self) -> Dict[str, Any]:
        """获取Canvas快照"""
        return {
            "session_id": self.session_id,
            "elements": [e.dict() for e in self.elements.values()]
        }
```

## 七、Memory系统简化

```python
# packages/derisk-serve/src/derisk_serve/agent/memory/memory_simple.py

from typing import Dict, Any, List, Optional
from datetime import datetime
import sqlite3
import json

class SimpleMemory:
    """简化Memory系统 - SQLite存储"""
    
    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_session_id (session_id)
            )
        """)
        conn.commit()
        conn.close()
        
    def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """添加消息"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (session_id, role, content, json.dumps(metadata) if metadata else None)
        )
        conn.commit()
        conn.close()
        
    def get_messages(
        self, 
        session_id: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """获取消息历史"""
        conn = sqlite3.connect(self.db_path)
        query = "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC"
        if limit:
            query += f" LIMIT {limit}"
            
        cursor = conn.execute(query, (session_id,))
        messages = []
        for row in cursor.fetchall():
            messages.append({
                "id": row[0],
                "session_id": row[1],
                "role": row[2],
                "content": row[3],
                "metadata": json.loads(row[4]) if row[4] else None,
                "created_at": row[5]
            })
        conn.close()
        return messages
        
    def compact(self, session_id: str, summary: str):
        """压缩消息 - Compaction机制"""
        # 1. 获取所有消息
        messages = self.get_messages(session_id)
        
        # 2. 生成摘要
        # 3. 删除旧消息
        # 4. 插入摘要
        
        conn = sqlite3.connect(self.db_path)
        
        # 删除旧消息
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        
        # 插入摘要
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (session_id, "system", summary, json.dumps({"compaction": True}))
        )
        
        conn.commit()
        conn.close()
```

## 八、Channel抽象

```python
# packages/derisk-serve/src/derisk_serve/agent/channels/channel_base.py

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any
from pydantic import BaseModel

class ChannelConfig(BaseModel):
    """Channel配置"""
    name: str
    type: str  # cli/web/api/discord/slack/telegram
    enabled: bool = True
    metadata: Dict[str, Any] = {}

class ChannelBase(ABC):
    """Channel抽象基类 - 参考OpenClaw Channel"""
    
    def __init__(self, config: ChannelConfig):
        self.config = config
        
    @abstractmethod
    async def connect(self):
        """连接到Channel"""
        pass
        
    @abstractmethod
    async def disconnect(self):
        """断开Channel"""
        pass
        
    @abstractmethod
    async def send(self, message: str, context: Dict[str, Any]):
        """发送消息到Channel"""
        pass
        
    @abstractmethod
    async def receive(self) -> AsyncIterator[Dict[str, Any]]:
        """从Channel接收消息"""
        pass
        
    @abstractmethod
    async def typing_indicator(self, is_typing: bool):
        """显示打字指示器"""
        pass

# 实现示例: CLI Channel
class CLIChannel(ChannelBase):
    """CLI Channel"""
    
    async def connect(self):
        print(f"[{self.config.name}] 已连接")
        
    async def disconnect(self):
        print(f"[{self.config.name}] 已断开")
        
    async def send(self, message: str, context: Dict[str, Any]):
        print(f"\n[Agent]: {message}\n")
        
    async def receive(self) -> AsyncIterator[Dict[str, Any]]:
        while True:
            user_input = input("[You]: ")
            yield {
                "content": user_input,
                "metadata": {}
            }
            
    async def typing_indicator(self, is_typing: bool):
        if is_typing:
            print("...", end="", flush=True)
```

## 九、Sandbox沙箱系统

```python
# packages/derisk-serve/src/derisk_serve/agent/sandbox/sandbox.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import docker
import tempfile
import os

class SandboxBase(ABC):
    """沙箱基类"""
    
    @abstractmethod
    async def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        """在沙箱中执行命令"""
        pass

class DockerSandbox(SandboxBase):
    """Docker沙箱 - 参考OpenClaw"""
    
    def __init__(
        self,
        image: str = "python:3.11",
        timeout: int = 300,
        memory_limit: str = "512m"
    ):
        self.image = image
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.client = docker.from_env()
        
    async def execute(
        self, 
        command: str, 
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """在Docker容器中执行"""
        volumes = {}
        if cwd:
            volumes[cwd] = {"bind": "/workspace", "mode": "rw"}
            
        container = self.client.containers.run(
            self.image,
            command=f"sh -c '{command}'",
            volumes=volumes,
            working_dir="/workspace" if cwd else None,
            environment=env,
            mem_limit=self.memory_limit,
            detach=True
        )
        
        try:
            result = container.wait(timeout=self.timeout)
            logs = container.logs().decode()
            
            return {
                "success": result["StatusCode"] == 0,
                "output": logs,
                "return_code": result["StatusCode"]
            }
        except Exception as e:
            return {
                "success": False,
                "output": str(e),
                "error": str(e)
            }
        finally:
            container.remove()

class LocalSandbox(SandboxBase):
    """本地沙箱(受限执行)"""
    
    async def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        """在本地受限环境中执行"""
        # 实现受限的本地执行
        # 例如: 限制网络、限制文件系统访问等
        pass
```

## 十、配置系统

### 10.1 Agent配置文件

支持Markdown + YAML前置配置的双模式定义(参考OpenCode):

```markdown
---
name: primary
description: 主Agent - 执行核心任务
mode: primary
model_id: claude-3-opus
max_steps: 20
permission:
  "*": allow
  "*.env": ask
  doom_loop: ask
---

# Primary Agent

这是一个功能完整的主Agent,具备以下能力:

- 代码编辑和重构
- Shell命令执行
- 文件操作
- 网络搜索

## 使用示例

```
用户: 帮我重构这个函数
Agent: [执行代码分析和重构]
```
```

### 10.2 配置加载器

```python
# packages/derisk-serve/src/derisk_serve/agent/config/config_loader.py

import yaml
import json
from pathlib import Path
from typing import Dict, Any
from ..core.agent_info import AgentInfo

class AgentConfigLoader:
    """Agent配置加载器 - 支持Markdown/JSON双模式"""
    
    @staticmethod
    def load(path: str) -> AgentInfo:
        """加载配置"""
        p = Path(path)
        
        if p.suffix == ".md":
            return AgentConfigLoader._load_markdown(path)
        elif p.suffix == ".json":
            return AgentConfigLoader._load_json(path)
        else:
            raise ValueError(f"不支持的配置格式: {p.suffix}")
            
    @staticmethod
    def _load_markdown(path: str) -> AgentInfo:
        """从Markdown加载"""
        content = Path(path).read_text()
        
        # 提取YAML前置配置
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                yaml_content = parts[1].strip()
                md_content = parts[2].strip()
                
                config = yaml.safe_load(yaml_content)
                config["prompt"] = md_content
                
                return AgentInfo(**config)
                
        raise ValueError("Markdown格式不正确")
        
    @staticmethod
    def _load_json(path: str) -> AgentInfo:
        """从JSON加载"""
        with open(path) as f:
            config = json.load(f)
        return AgentInfo(**config)
```

## 十一、实施路线图

### Phase 1: 核心重构 (2周)

**Week 1: Agent构建重构**
- [ ] 实现AgentInfo配置模型
- [ ] 实现Permission权限系统
- [ ] 简化AgentBase接口
- [ ] 迁移现有Agent到新模型

**Week 2: 运行时重构**
- [ ] 实现Gateway控制平面
- [ ] 实现Session管理
- [ ] 优化执行循环
- [ ] 集成进度推送

### Phase 2: Tool系统 (1周)

**Week 3: 工具系统增强**
- [ ] 重构ToolBase基类
- [ ] 实现BashTool多环境执行
- [ ] 实现ToolRegistry注册表
- [ ] 集成Permission系统

### Phase 3: 可视化 (1周)

**Week 4: 可视化增强**
- [ ] 实现ProgressBroadcaster
- [ ] 实现Canvas可视化
- [ ] WebSocket实时推送
- [ ] Web界面集成

### Phase 4: 扩展能力 (2周)

**Week 5: Channel和Memory**
- [ ] 实现Channel抽象层
- [ ] 简化Memory系统
- [ ] 迁移到SQLite存储
- [ ] 实现Compaction机制

**Week 6: Skill和Sandbox**
- [ ] 实现Skill系统
- [ ] 实现DockerSandbox
- [ ] 安全审计
- [ ] 性能优化

### Phase 5: 测试和文档 (1周)

**Week 7: 测试和文档**
- [ ] 单元测试覆盖
- [ ] 集成测试
- [ ] 性能测试
- [ ] 文档编写
- [ ] 迁移指南

## 十二、兼容性保证

### 12.1 接口兼容

```python
# 兼容层 - 保持旧接口可用
from ..core.agent_base import AgentBase as NewAgentBase

class Agent(NewAgentBase):
    """兼容旧接口的Agent"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._deprecated_warning()
        
    def _deprecated_warning(self):
        import warnings
        warnings.warn(
            "Agent类已废弃,请使用AgentBase",
            DeprecationWarning,
            stacklevel=2
        )
```

### 12.2 数据迁移脚本

```python
# scripts/migrate_memory.py

"""Memory数据迁移脚本"""

def migrate_memory(old_db_path: str, new_db_path: str):
    """从旧Memory格式迁移到新格式"""
    # 实现数据迁移逻辑
    pass
```

## 十三、性能指标

### 13.1 目标性能

| 指标 | 当前值 | 目标值 |
|------|-------|--------|
| Agent响应延迟 | 2-3秒 | < 1秒 |
| 工具执行延迟 | 1-2秒 | < 500ms |
| Memory查询延迟 | 500ms | < 100ms |
| 并发Session数 | 10 | 100 |
| 内存占用 | 500MB | < 200MB |

### 13.2 性能优化策略

1. **异步化** - 全异步执行,避免阻塞
2. **连接池** - 复用数据库连接
3. **缓存** - 热点数据缓存
4. **流式处理** - 流式输出减少内存
5. **索引优化** - 数据库索引优化

## 十四、安全考虑

1. **权限控制** - Permission Ruleset确保工具安全
2. **沙箱隔离** - Docker Sandbox隔离危险操作
3. **输入验证** - Pydantic Schema自动验证
4. **审计日志** - 完整操作日志记录
5. **密钥保护** - 环境变量存储敏感信息

## 十五、总结

本重构方案全面借鉴了OpenCode和OpenClaw两大顶级项目的最佳实践,从以下方面进行了系统性重构:

### 核心改进
1. **配置驱动** - Agent通过AgentInfo配置化定义
2. **类型安全** - Pydantic Schema贯穿始终
3. **权限精细** - Permission Ruleset细粒度控制
4. **架构分层** - Gateway + Agent Runtime清晰分层
5. **可视化强** - 实时进度推送 + Canvas可视化
6. **可扩展** - Channel抽象 + Skill系统
7. **安全隔离** - Docker沙箱 + 权限控制

### 预期收益
- 代码复杂度降低 50%
- 执行效率提升 3-5倍
- 可维护性显著提升
- 安全性大幅增强
- 扩展性完全解耦

重构完成后,OpenDeRisk将具备生产级AI Agent平台的核心能力,为后续功能扩展奠定坚实基础。