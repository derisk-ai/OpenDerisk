# Derisk 统一工具架构与授权系统 - 架构设计文档（第二部分）

---

## 五、统一交互系统设计

### 5.1 交互协议

```python
# derisk/core/interaction/protocol.py

from typing import Dict, Any, List, Optional, Union, Literal
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import uuid


class InteractionType(str, Enum):
    """交互类型"""
    # 用户输入类
    TEXT_INPUT = "text_input"               # 文本输入
    FILE_UPLOAD = "file_upload"             # 文件上传
    
    # 选择类
    SINGLE_SELECT = "single_select"         # 单选
    MULTI_SELECT = "multi_select"           # 多选
    
    # 确认类
    CONFIRMATION = "confirmation"           # 确认/取消
    AUTHORIZATION = "authorization"         # 授权确认
    PLAN_SELECTION = "plan_selection"       # 方案选择
    
    # 通知类
    INFO = "info"                           # 信息通知
    WARNING = "warning"                     # 警告通知
    ERROR = "error"                         # 错误通知
    SUCCESS = "success"                     # 成功通知
    PROGRESS = "progress"                   # 进度通知
    
    # 任务管理类
    TODO_CREATE = "todo_create"             # 创建任务
    TODO_UPDATE = "todo_update"             # 更新任务


class InteractionPriority(str, Enum):
    """交互优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class InteractionStatus(str, Enum):
    """交互状态"""
    PENDING = "pending"         # 等待处理
    PROCESSING = "processing"   # 处理中
    COMPLETED = "completed"     # 已完成
    TIMEOUT = "timeout"         # 超时
    CANCELLED = "cancelled"     # 已取消
    ERROR = "error"             # 错误


class InteractionOption(BaseModel):
    """交互选项"""
    label: str                                      # 显示文本
    value: str                                      # 选项值
    description: Optional[str] = None               # 描述
    icon: Optional[str] = None                      # 图标
    disabled: bool = False                          # 是否禁用
    default: bool = False                           # 是否默认
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InteractionRequest(BaseModel):
    """交互请求 - 统一协议"""
    
    # 基本信息
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    type: InteractionType
    priority: InteractionPriority = InteractionPriority.NORMAL
    
    # 内容
    title: str
    message: str
    options: List[InteractionOption] = Field(default_factory=list)
    
    # 默认值
    default_value: Optional[str] = None
    default_values: List[str] = Field(default_factory=list)
    
    # 控制选项
    timeout: Optional[int] = 300                    # 超时（秒）
    allow_cancel: bool = True                       # 允许取消
    allow_skip: bool = False                        # 允许跳过
    allow_defer: bool = True                        # 允许延迟处理
    
    # 会话信息
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    step_index: int = 0
    execution_id: Optional[str] = None
    
    # 授权相关（仅AUTHORIZATION类型）
    authorization_context: Optional[Dict[str, Any]] = None
    allow_session_grant: bool = False
    
    # 文件上传相关（仅FILE_UPLOAD类型）
    accepted_file_types: Optional[List[str]] = None
    max_file_size: Optional[int] = None             # 字节
    allow_multiple_files: bool = False
    
    # 进度相关（仅PROGRESS类型）
    progress_value: Optional[float] = None          # 0.0 - 1.0
    progress_message: Optional[str] = None
    
    # TODO相关
    todo_item: Optional[Dict[str, Any]] = None
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "type": self.type,
            "priority": self.priority,
            "title": self.title,
            "message": self.message,
            "options": [opt.model_dump() for opt in self.options],
            "default_value": self.default_value,
            "default_values": self.default_values,
            "timeout": self.timeout,
            "allow_cancel": self.allow_cancel,
            "allow_skip": self.allow_skip,
            "allow_defer": self.allow_defer,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "step_index": self.step_index,
            "execution_id": self.execution_id,
            "authorization_context": self.authorization_context,
            "allow_session_grant": self.allow_session_grant,
            "accepted_file_types": self.accepted_file_types,
            "max_file_size": self.max_file_size,
            "allow_multiple_files": self.allow_multiple_files,
            "progress_value": self.progress_value,
            "progress_message": self.progress_message,
            "todo_item": self.todo_item,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionRequest":
        """从字典创建"""
        data = data.copy()
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "options" in data:
            data["options"] = [InteractionOption(**opt) for opt in data["options"]]
        return cls(**data)


class InteractionResponse(BaseModel):
    """交互响应 - 统一协议"""
    
    # 基本信息
    request_id: str
    session_id: Optional[str] = None
    
    # 响应内容
    choice: Optional[str] = None                    # 单选结果
    choices: List[str] = Field(default_factory=list) # 多选结果
    input_value: Optional[str] = None               # 文本输入
    file_ids: List[str] = Field(default_factory=list) # 文件ID列表
    
    # 状态
    status: InteractionStatus = InteractionStatus.COMPLETED
    
    # 用户消息
    user_message: Optional[str] = None
    cancel_reason: Optional[str] = None
    
    # 授权相关
    grant_scope: Optional[str] = None               # once/session/permanent
    grant_duration: Optional[int] = None            # 有效期（秒）
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
    
    @property
    def is_confirmed(self) -> bool:
        """是否确认"""
        return self.choice in ["yes", "allow", "confirm"]
    
    @property
    def is_denied(self) -> bool:
        """是否拒绝"""
        return self.choice in ["no", "deny", "cancel"] or self.status == InteractionStatus.CANCELLED
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "choice": self.choice,
            "choices": self.choices,
            "input_value": self.input_value,
            "file_ids": self.file_ids,
            "status": self.status,
            "user_message": self.user_message,
            "cancel_reason": self.cancel_reason,
            "grant_scope": self.grant_scope,
            "grant_duration": self.grant_duration,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionResponse":
        """从字典创建"""
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


# ========== 便捷构造函数 ==========

def create_authorization_request(
    tool_name: str,
    tool_description: str,
    arguments: Dict[str, Any],
    risk_assessment: Dict[str, Any],
    session_id: str,
    agent_name: str,
    allow_session_grant: bool = True,
    timeout: int = 300,
) -> InteractionRequest:
    """创建授权请求"""
    
    # 构建消息
    risk_level = risk_assessment.get("level", "medium")
    risk_factors = risk_assessment.get("factors", [])
    
    message = f"""需要您的授权确认

工具: {tool_name}
描述: {tool_description}
风险等级: {risk_level.upper()}
参数: {arguments}
"""
    
    if risk_factors:
        message += "\n风险因素:\n"
        for factor in risk_factors:
            message += f"  - {factor}\n"
    
    return InteractionRequest(
        type=InteractionType.AUTHORIZATION,
        priority=InteractionPriority.HIGH if risk_level in ["high", "critical"] else InteractionPriority.NORMAL,
        title="工具执行授权",
        message=message,
        options=[
            InteractionOption(label="允许", value="allow", icon="check"),
            InteractionOption(label="拒绝", value="deny", icon="close", default=True),
        ],
        timeout=timeout,
        session_id=session_id,
        agent_name=agent_name,
        authorization_context={
            "tool_name": tool_name,
            "arguments": arguments,
            "risk_assessment": risk_assessment,
        },
        allow_session_grant=allow_session_grant,
    )


def create_text_input_request(
    question: str,
    title: str = "请输入",
    default: Optional[str] = None,
    session_id: Optional[str] = None,
    timeout: int = 300,
) -> InteractionRequest:
    """创建文本输入请求"""
    return InteractionRequest(
        type=InteractionType.TEXT_INPUT,
        title=title,
        message=question,
        default_value=default,
        timeout=timeout,
        session_id=session_id,
    )


def create_confirmation_request(
    message: str,
    title: str = "确认",
    default: bool = False,
    session_id: Optional[str] = None,
    timeout: int = 60,
) -> InteractionRequest:
    """创建确认请求"""
    return InteractionRequest(
        type=InteractionType.CONFIRMATION,
        title=title,
        message=message,
        options=[
            InteractionOption(label="确认", value="yes", default=default),
            InteractionOption(label="取消", value="no", default=not default),
        ],
        timeout=timeout,
        session_id=session_id,
    )


def create_selection_request(
    message: str,
    options: List[Union[str, Dict[str, Any]]],
    title: str = "请选择",
    default: Optional[str] = None,
    session_id: Optional[str] = None,
    timeout: int = 120,
) -> InteractionRequest:
    """创建选择请求"""
    formatted_options = []
    for opt in options:
        if isinstance(opt, str):
            formatted_options.append(InteractionOption(
                label=opt,
                value=opt,
                default=(opt == default),
            ))
        else:
            formatted_options.append(InteractionOption(
                label=opt.get("label", opt.get("value", "")),
                value=opt.get("value", ""),
                description=opt.get("description"),
                default=(opt.get("value") == default),
            ))
    
    return InteractionRequest(
        type=InteractionType.SINGLE_SELECT,
        title=title,
        message=message,
        options=formatted_options,
        default_value=default,
        timeout=timeout,
        session_id=session_id,
    )


def create_notification(
    message: str,
    level: Literal["info", "warning", "error", "success"] = "info",
    title: Optional[str] = None,
    session_id: Optional[str] = None,
) -> InteractionRequest:
    """创建通知"""
    type_map = {
        "info": InteractionType.INFO,
        "warning": InteractionType.WARNING,
        "error": InteractionType.ERROR,
        "success": InteractionType.SUCCESS,
    }
    
    return InteractionRequest(
        type=type_map[level],
        title=title or level.upper(),
        message=message,
        session_id=session_id,
        timeout=None,  # 通知不需要超时
    )
```

### 5.2 交互网关

```python
# derisk/core/interaction/gateway.py

from typing import Dict, Any, Optional, Callable, Awaitable, List
from abc import ABC, abstractmethod
import asyncio
import logging
from datetime import datetime

from .protocol import (
    InteractionRequest,
    InteractionResponse,
    InteractionStatus,
)

logger = logging.getLogger(__name__)


class ConnectionManager(ABC):
    """连接管理器抽象"""
    
    @abstractmethod
    async def has_connection(self, session_id: str) -> bool:
        """检查是否有连接"""
        pass
    
    @abstractmethod
    async def send(self, session_id: str, message: Dict[str, Any]) -> bool:
        """发送消息"""
        pass
    
    @abstractmethod
    async def broadcast(self, message: Dict[str, Any]) -> int:
        """广播消息"""
        pass


class StateStore(ABC):
    """状态存储抽象"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass


class MemoryConnectionManager(ConnectionManager):
    """内存连接管理器"""
    
    def __init__(self):
        self._connections: Dict[str, bool] = {}
    
    def add_connection(self, session_id: str):
        self._connections[session_id] = True
    
    def remove_connection(self, session_id: str):
        self._connections.pop(session_id, None)
    
    async def has_connection(self, session_id: str) -> bool:
        return self._connections.get(session_id, False)
    
    async def send(self, session_id: str, message: Dict[str, Any]) -> bool:
        if await self.has_connection(session_id):
            logger.info(f"[MemoryConnMgr] Send to {session_id}: {message.get('type')}")
            return True
        return False
    
    async def broadcast(self, message: Dict[str, Any]) -> int:
        return len(self._connections)


class MemoryStateStore(StateStore):
    """内存状态存储"""
    
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)
    
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        self._store[key] = value
        return True
    
    async def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        return key in self._store


class InteractionGateway:
    """
    交互网关 - 统一交互管理
    
    职责:
    1. 交互请求分发
    2. 响应收集
    3. 超时管理
    4. 会话状态管理
    """
    
    def __init__(
        self,
        connection_manager: Optional[ConnectionManager] = None,
        state_store: Optional[StateStore] = None,
    ):
        self.connection_manager = connection_manager or MemoryConnectionManager()
        self.state_store = state_store or MemoryStateStore()
        
        # 待处理的请求
        self._pending_requests: Dict[str, asyncio.Future] = {}
        
        # 会话请求索引
        self._session_requests: Dict[str, List[str]] = {}
        
        # 统计
        self._stats = {
            "requests_sent": 0,
            "responses_received": 0,
            "timeouts": 0,
            "cancelled": 0,
        }
    
    async def send(
        self,
        request: InteractionRequest,
    ) -> str:
        """
        发送交互请求（不等待响应）
        
        Returns:
            str: 请求ID
        """
        # 保存请求
        await self.state_store.set(
            f"request:{request.request_id}",
            request.to_dict(),
            ttl=request.timeout + 60 if request.timeout else None,
        )
        
        # 索引到会话
        session_id = request.session_id or "default"
        if session_id not in self._session_requests:
            self._session_requests[session_id] = []
        self._session_requests[session_id].append(request.request_id)
        
        # 发送到客户端
        has_connection = await self.connection_manager.has_connection(session_id)
        
        if has_connection:
            success = await self.connection_manager.send(
                session_id,
                {
                    "type": "interaction_request",
                    "data": request.to_dict(),
                }
            )
            if success:
                self._stats["requests_sent"] += 1
                logger.info(f"[Gateway] Sent request {request.request_id} to session {session_id}")
                return request.request_id
        
        # 保存为待处理
        await self._save_pending_request(request)
        logger.info(f"[Gateway] Saved pending request {request.request_id}")
        return request.request_id
    
    async def send_and_wait(
        self,
        request: InteractionRequest,
    ) -> InteractionResponse:
        """
        发送请求并等待响应
        
        Returns:
            InteractionResponse: 响应结果
        """
        # 创建Future
        future = asyncio.Future()
        self._pending_requests[request.request_id] = future
        
        # 发送请求
        await self.send(request)
        
        # 等待响应
        try:
            response = await asyncio.wait_for(
                future,
                timeout=request.timeout or 300,
            )
            self._stats["responses_received"] += 1
            return response
            
        except asyncio.TimeoutError:
            self._stats["timeouts"] += 1
            return InteractionResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=InteractionStatus.TIMEOUT,
                cancel_reason="等待用户响应超时",
            )
            
        except asyncio.CancelledError:
            self._stats["cancelled"] += 1
            return InteractionResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=InteractionStatus.CANCELLED,
            )
            
        finally:
            self._pending_requests.pop(request.request_id, None)
    
    async def deliver_response(
        self,
        response: InteractionResponse,
    ):
        """
        投递响应
        
        当用户通过WebSocket或API提交响应时调用
        """
        # 更新请求状态
        request_data = await self.state_store.get(f"request:{response.request_id}")
        if request_data:
            request_data["status"] = response.status
            await self.state_store.set(
                f"request:{response.request_id}",
                request_data,
            )
        
        # 投递到Future
        if response.request_id in self._pending_requests:
            future = self._pending_requests.pop(response.request_id)
            if not future.done():
                future.set_result(response)
                logger.info(f"[Gateway] Delivered response for {response.request_id}")
    
    async def get_pending_requests(
        self,
        session_id: str,
    ) -> List[InteractionRequest]:
        """获取会话的待处理请求"""
        request_ids = self._session_requests.get(session_id, [])
        requests = []
        
        for rid in request_ids:
            data = await self.state_store.get(f"request:{rid}")
            if data:
                requests.append(InteractionRequest.from_dict(data))
        
        return requests
    
    async def cancel_request(
        self,
        request_id: str,
        reason: str = "user_cancel",
    ):
        """取消请求"""
        response = InteractionResponse(
            request_id=request_id,
            status=InteractionStatus.CANCELLED,
            cancel_reason=reason,
        )
        await self.deliver_response(response)
    
    async def _save_pending_request(self, request: InteractionRequest):
        """保存待处理请求"""
        pending_key = f"pending:{request.session_id}"
        pending = await self.state_store.get(pending_key) or {"items": []}
        
        if isinstance(pending, dict) and "items" in pending:
            pending["items"].append(request.to_dict())
            await self.state_store.set(pending_key, pending)
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()


# 全局交互网关
_gateway_instance: Optional[InteractionGateway] = None


def get_interaction_gateway() -> InteractionGateway:
    """获取全局交互网关"""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = InteractionGateway()
    return _gateway_instance


def set_interaction_gateway(gateway: InteractionGateway):
    """设置全局交互网关"""
    global _gateway_instance
    _gateway_instance = gateway
```

---

## 六、Agent集成设计

### 6.1 AgentInfo增强

```python
# derisk/core/agent/info.py

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from enum import Enum

from ..tools.metadata import ToolCategory
from ..authorization.model import (
    AuthorizationConfig,
    AuthorizationMode,
    PermissionRuleset,
)


class AgentMode(str, Enum):
    """Agent模式"""
    PRIMARY = "primary"         # 主Agent
    SUBAGENT = "subagent"       # 子Agent
    UTILITY = "utility"         # 工具Agent
    SUPERVISOR = "supervisor"   # 监督者Agent


class AgentCapability(str, Enum):
    """Agent能力标签"""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DATA_ANALYSIS = "data_analysis"
    FILE_MANIPULATION = "file_manipulation"
    WEB_SCRAPING = "web_scraping"
    SHELL_EXECUTION = "shell_execution"
    MULTI_AGENT = "multi_agent"
    USER_INTERACTION = "user_interaction"


class ToolSelectionPolicy(BaseModel):
    """工具选择策略"""
    
    # 工具过滤
    included_categories: List[ToolCategory] = Field(default_factory=list)
    excluded_categories: List[ToolCategory] = Field(default_factory=list)
    
    included_tools: List[str] = Field(default_factory=list)
    excluded_tools: List[str] = Field(default_factory=list)
    
    # 工具优先级
    preferred_tools: List[str] = Field(default_factory=list)
    
    # 工具数量限制
    max_tools: Optional[int] = None
    
    def filter_tools(self, tools: List[Any]) -> List[Any]:
        """过滤工具列表"""
        result = []
        
        for tool in tools:
            name = tool.metadata.name
            category = tool.metadata.category
            
            # 检查排除列表
            if name in self.excluded_tools:
                continue
            if category in self.excluded_categories:
                continue
            
            # 检查包含列表
            if self.included_tools and name not in self.included_tools:
                if self.included_categories and category not in self.included_categories:
                    continue
            
            result.append(tool)
        
        # 限制数量
        if self.max_tools and len(result) > self.max_tools:
            # 优先保留preferred_tools
            preferred = [t for t in result if t.metadata.name in self.preferred_tools]
            others = [t for t in result if t.metadata.name not in self.preferred_tools]
            
            remaining = self.max_tools - len(preferred)
            if remaining > 0:
                result = preferred + others[:remaining]
            else:
                result = preferred[:self.max_tools]
        
        return result


class AgentInfo(BaseModel):
    """
    Agent配置信息 - 统一标准
    
    声明式配置，支持多种运行模式
    """
    
    # ========== 基本信息 ==========
    name: str
    description: Optional[str] = None
    mode: AgentMode = AgentMode.PRIMARY
    version: str = "1.0.0"
    
    # ========== 隐藏标记 ==========
    hidden: bool = False                # 是否在UI中隐藏
    
    # ========== LLM配置 ==========
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)
    
    # ========== 执行配置 ==========
    max_steps: int = Field(20, gt=0, description="最大执行步骤数")
    timeout: int = Field(300, gt=0, description="超时时间(秒)")
    
    # ========== 工具配置 ==========
    tool_policy: ToolSelectionPolicy = Field(default_factory=ToolSelectionPolicy)
    tools: List[str] = Field(default_factory=list, description="工具列表（兼容）")
    
    # ========== 授权配置 ==========
    authorization: AuthorizationConfig = Field(
        default_factory=AuthorizationConfig,
        description="授权配置",
    )
    
    # 兼容旧字段
    permission: Optional[PermissionRuleset] = None
    
    # ========== 能力标签 ==========
    capabilities: List[AgentCapability] = Field(default_factory=list)
    
    # ========== 显示配置 ==========
    color: str = Field("#4A90E2", description="颜色标识")
    icon: Optional[str] = None
    
    # ========== Prompt配置 ==========
    system_prompt: Optional[str] = None
    system_prompt_file: Optional[str] = None
    user_prompt_template: Optional[str] = None
    
    # ========== 上下文配置 ==========
    context_window_size: Optional[int] = None
    memory_enabled: bool = True
    memory_type: str = "short_term"     # short_term/long_term
    
    # ========== 多Agent配置 ==========
    subagents: List[str] = Field(default_factory=list)
    collaboration_mode: str = "sequential"  # sequential/parallel/hierarchical
    
    # ========== 元数据 ==========
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    
    class Config:
        use_enum_values = True
    
    def get_effective_authorization(self) -> AuthorizationConfig:
        """获取生效的授权配置"""
        # 如果有旧版permission，转换为AuthorizationConfig
        if self.permission:
            auth = self.authorization
            auth.ruleset = self.permission
        return self.authorization
    
    def get_openai_tools(self, registry: Any) -> List[Dict[str, Any]]:
        """获取OpenAI格式工具列表"""
        all_tools = registry.list_all()
        filtered = self.tool_policy.filter_tools(all_tools)
        return [t.metadata.get_openai_spec() for t in filtered]


# ========== 预定义Agent模板 ==========

PRIMARY_AGENT_TEMPLATE = AgentInfo(
    name="primary",
    description="主Agent - 执行核心任务，具备完整工具权限",
    mode=AgentMode.PRIMARY,
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
    ),
    max_steps=30,
    color="#4A90E2",
    capabilities=[
        AgentCapability.CODE_GENERATION,
        AgentCapability.FILE_MANIPULATION,
        AgentCapability.SHELL_EXECUTION,
        AgentCapability.USER_INTERACTION,
    ],
)

PLAN_AGENT_TEMPLATE = AgentInfo(
    name="plan",
    description="规划Agent - 只读分析和代码探索",
    mode=AgentMode.PRIMARY,
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.STRICT,
        blacklist_tools=["bash", "write", "edit", "delete"],
    ),
    tool_policy=ToolSelectionPolicy(
        included_categories=[ToolCategory.FILE_SYSTEM, ToolCategory.CODE],
        excluded_tools=["write", "edit", "delete"],
    ),
    max_steps=15,
    color="#7B68EE",
    capabilities=[
        AgentCapability.CODE_REVIEW,
        AgentCapability.DATA_ANALYSIS,
    ],
)

SUBAGENT_TEMPLATE = AgentInfo(
    name="subagent",
    description="子Agent - 被委派执行特定任务",
    mode=AgentMode.SUBAGENT,
    authorization=AuthorizationConfig(
        mode=AuthorizationMode.PERMISSIVE,
    ),
    max_steps=10,
    color="#32CD32",
)


def create_agent_from_template(
    template_name: str,
    name: Optional[str] = None,
    **overrides,
) -> AgentInfo:
    """从模板创建Agent"""
    templates = {
        "primary": PRIMARY_AGENT_TEMPLATE,
        "plan": PLAN_AGENT_TEMPLATE,
        "subagent": SUBAGENT_TEMPLATE,
    }
    
    template = templates.get(template_name)
    if not template:
        raise ValueError(f"Unknown template: {template_name}")
    
    # 复制模板
    data = template.model_dump()
    data.update(overrides)
    
    if name:
        data["name"] = name
    
    return AgentInfo(**data)
```

### 6.2 统一Agent基类

```python
# derisk/core/agent/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator, List
from enum import Enum
import asyncio
import logging

from .info import AgentInfo
from ..tools.base import ToolRegistry, ToolResult
from ..tools.metadata import ToolMetadata
from ..authorization.engine import (
    AuthorizationEngine,
    AuthorizationContext,
    get_authorization_engine,
)
from ..authorization.model import AuthorizationConfig
from ..interaction.gateway import InteractionGateway, get_interaction_gateway
from ..interaction.protocol import (
    InteractionRequest,
    InteractionResponse,
    create_authorization_request,
)

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    """Agent状态"""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentBase(ABC):
    """
    Agent基类 - 统一接口
    
    所有Agent必须继承此类
    """
    
    def __init__(
        self,
        info: AgentInfo,
        tool_registry: Optional[ToolRegistry] = None,
        auth_engine: Optional[AuthorizationEngine] = None,
        interaction_gateway: Optional[InteractionGateway] = None,
    ):
        self.info = info
        self.tools = tool_registry or ToolRegistry()
        self.auth_engine = auth_engine or get_authorization_engine()
        self.interaction = interaction_gateway or get_interaction_gateway()
        
        self._state = AgentState.IDLE
        self._session_id: Optional[str] = None
        self._current_step = 0
    
    @property
    def state(self) -> AgentState:
        return self._state
    
    @property
    def session_id(self) -> Optional[str]:
        return self._session_id
    
    # ========== 抽象方法 ==========
    
    @abstractmethod
    async def think(self, message: str, **kwargs) -> AsyncIterator[str]:
        """
        思考阶段
        
        分析问题，生成思考过程（流式）
        """
        pass
    
    @abstractmethod
    async def decide(self, message: str, **kwargs) -> Dict[str, Any]:
        """
        决策阶段
        
        决定下一步行动：回复用户或调用工具
        """
        pass
    
    @abstractmethod
    async def act(self, action: Dict[str, Any], **kwargs) -> Any:
        """
        行动阶段
        
        执行决策结果
        """
        pass
    
    # ========== 工具执行 ==========
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        执行工具 - 带完整授权检查
        
        流程:
        1. 获取工具
        2. 授权检查
        3. 执行工具
        4. 返回结果
        """
        # 1. 获取工具
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"工具不存在: {tool_name}",
            )
        
        # 2. 授权检查
        auth_result = await self._check_authorization(
            tool_name=tool_name,
            tool_metadata=tool.metadata,
            arguments=arguments,
        )
        
        if not auth_result:
            return ToolResult(
                success=False,
                output="",
                error="授权被拒绝",
            )
        
        # 3. 执行工具
        try:
            result = await tool.execute_safe(arguments, context)
            return result
        except Exception as e:
            logger.exception(f"[{self.info.name}] Tool execution failed: {tool_name}")
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
    
    async def _check_authorization(
        self,
        tool_name: str,
        tool_metadata: ToolMetadata,
        arguments: Dict[str, Any],
    ) -> bool:
        """检查授权"""
        # 构建授权上下文
        auth_ctx = AuthorizationContext(
            session_id=self._session_id or "default",
            agent_name=self.info.name,
            tool_name=tool_name,
            tool_metadata=tool_metadata,
            arguments=arguments,
        )
        
        # 执行授权检查
        auth_result = await self.auth_engine.check_authorization(
            ctx=auth_ctx,
            config=self.info.get_effective_authorization(),
            user_confirmation_handler=self._handle_user_confirmation,
        )
        
        return auth_result.decision in ["granted", "cached"]
    
    async def _handle_user_confirmation(
        self,
        request: Dict[str, Any],
    ) -> bool:
        """
        处理用户确认
        
        通过InteractionGateway请求用户授权
        """
        # 创建交互请求
        interaction_request = create_authorization_request(
            tool_name=request["tool_name"],
            tool_description=request["tool_description"],
            arguments=request["arguments"],
            risk_assessment=request["risk_assessment"],
            session_id=request["session_id"],
            agent_name=self.info.name,
            allow_session_grant=request.get("allow_session_grant", True),
            timeout=request.get("timeout", 300),
        )
        
        # 发送并等待响应
        response = await self.interaction.send_and_wait(interaction_request)
        
        return response.is_confirmed
    
    # ========== 用户交互 ==========
    
    async def ask_user(
        self,
        question: str,
        title: str = "请输入",
        default: Optional[str] = None,
        timeout: int = 300,
    ) -> str:
        """询问用户"""
        from ..interaction.protocol import create_text_input_request
        
        request = create_text_input_request(
            question=question,
            title=title,
            default=default,
            session_id=self._session_id,
            timeout=timeout,
        )
        
        response = await self.interaction.send_and_wait(request)
        return response.input_value or default or ""
    
    async def confirm(
        self,
        message: str,
        title: str = "确认",
        default: bool = False,
        timeout: int = 60,
    ) -> bool:
        """确认操作"""
        from ..interaction.protocol import create_confirmation_request
        
        request = create_confirmation_request(
            message=message,
            title=title,
            default=default,
            session_id=self._session_id,
            timeout=timeout,
        )
        
        response = await self.interaction.send_and_wait(request)
        return response.is_confirmed
    
    async def select(
        self,
        message: str,
        options: List[Dict[str, Any]],
        title: str = "请选择",
        default: Optional[str] = None,
        timeout: int = 120,
    ) -> str:
        """选择操作"""
        from ..interaction.protocol import create_selection_request
        
        request = create_selection_request(
            message=message,
            options=options,
            title=title,
            default=default,
            session_id=self._session_id,
            timeout=timeout,
        )
        
        response = await self.interaction.send_and_wait(request)
        return response.choice or default or ""
    
    async def notify(
        self,
        message: str,
        level: str = "info",
        title: Optional[str] = None,
    ):
        """发送通知"""
        from ..interaction.protocol import create_notification
        
        request = create_notification(
            message=message,
            level=level,
            title=title,
            session_id=self._session_id,
        )
        
        await self.interaction.send(request)
    
    # ========== 运行循环 ==========
    
    async def run(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        主运行循环
        
        思考 -> 决策 -> 行动 循环
        """
        self._state = AgentState.RUNNING
        self._session_id = session_id or f"session_{id(self)}"
        self._current_step = 0
        
        try:
            while self._current_step < self.info.max_steps:
                self._current_step += 1
                
                # 思考阶段
                async for chunk in self.think(message, **kwargs):
                    yield chunk
                
                # 决策阶段
                decision = await self.decide(message, **kwargs)
                
                # 行动阶段
                if decision.get("type") == "response":
                    # 直接回复用户
                    yield decision["content"]
                    break
                
                elif decision.get("type") == "tool_call":
                    # 执行工具
                    result = await self.act(decision, **kwargs)
                    
                    if isinstance(result, ToolResult):
                        if result.success:
                            message = f"工具执行成功: {result.output[:200]}"
                        else:
                            message = f"工具执行失败: {result.error}"
                    
                    yield f"\n{message}\n"
                
                elif decision.get("type") == "complete":
                    # 任务完成
                    break
                
                elif decision.get("type") == "error":
                    # 发生错误
                    yield f"\n[错误] {decision.get('error')}\n"
                    self._state = AgentState.FAILED
                    break
            
            else:
                # 达到最大步数
                yield f"\n[警告] 达到最大步骤限制({self.info.max_steps})\n"
            
            self._state = AgentState.COMPLETED
            yield "\n[完成]"
            
        except Exception as e:
            self._state = AgentState.FAILED
            logger.exception(f"[{self.info.name}] Agent run failed")
            yield f"\n[异常] {str(e)}\n"
```

---

*文档继续，请查看第三部分...*