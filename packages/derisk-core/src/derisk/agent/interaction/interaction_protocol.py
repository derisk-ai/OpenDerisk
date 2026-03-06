"""
Interaction Protocol - 统一交互协议定义

提供 Agent 与用户之间的标准化交互协议
支持多种交互类型、状态管理和恢复机制
"""

from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import uuid
import json


class InteractionType(str, Enum):
    """交互类型枚举"""
    
    ASK = "ask"
    CONFIRM = "confirm"
    SELECT = "select"
    MULTIPLE_SELECT = "multiple_select"
    AUTHORIZE = "authorize"
    AUTHORIZE_ONCE = "authorize_once"
    AUTHORIZE_SESSION = "authorize_session"
    CHOOSE_PLAN = "choose_plan"
    INPUT_TEXT = "input_text"
    INPUT_FILE = "input_file"
    NOTIFY = "notify"
    NOTIFY_PROGRESS = "notify_progress"
    NOTIFY_ERROR = "notify_error"
    NOTIFY_SUCCESS = "notify_success"


class InteractionPriority(str, Enum):
    """交互优先级"""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class InteractionStatus(str, Enum):
    """交互状态"""
    PENDING = "pending"
    RESPONSED = "responsed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    FAILED = "failed"
    DEFERRED = "deferred"


class NotifyLevel(str, Enum):
    """通知级别"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


class InteractionOption(BaseModel):
    """交互选项"""
    label: str
    value: str
    description: Optional[str] = None
    icon: Optional[str] = None
    disabled: bool = False
    default: bool = False


class InteractionRequest(BaseModel):
    """交互请求"""
    
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    interaction_type: InteractionType
    priority: InteractionPriority = InteractionPriority.NORMAL
    
    title: str
    message: str
    options: List[InteractionOption] = Field(default_factory=list)
    
    session_id: Optional[str] = None
    execution_id: Optional[str] = None
    step_index: int = 0
    agent_name: Optional[str] = None
    tool_name: Optional[str] = None
    
    timeout: Optional[int] = 300
    default_choice: Optional[str] = None
    allow_cancel: bool = True
    allow_skip: bool = False
    allow_defer: bool = True
    
    state_snapshot: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "interaction_type": self.interaction_type,
            "priority": self.priority,
            "title": self.title,
            "message": self.message,
            "options": [o.model_dump() for o in self.options],
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "step_index": self.step_index,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "timeout": self.timeout,
            "default_choice": self.default_choice,
            "allow_cancel": self.allow_cancel,
            "allow_skip": self.allow_skip,
            "allow_defer": self.allow_defer,
            "state_snapshot": self.state_snapshot,
            "context": self.context,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionRequest":
        data = data.copy()
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "options" in data:
            data["options"] = [InteractionOption(**o) for o in data["options"]]
        return cls(**data)


class InteractionResponse(BaseModel):
    """交互响应"""
    
    request_id: str
    session_id: Optional[str] = None
    
    choice: Optional[str] = None
    choices: List[str] = Field(default_factory=list)
    input_value: Optional[str] = None
    files: List[str] = Field(default_factory=list)
    
    status: InteractionStatus = InteractionStatus.RESPONSED
    user_message: Optional[str] = None
    cancel_reason: Optional[str] = None
    
    grant_scope: Optional[str] = None
    grant_duration: Optional[int] = None
    
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "choice": self.choice,
            "choices": self.choices,
            "input_value": self.input_value,
            "files": self.files,
            "status": self.status,
            "user_message": self.user_message,
            "cancel_reason": self.cancel_reason,
            "grant_scope": self.grant_scope,
            "grant_duration": self.grant_duration,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionResponse":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


class TodoItem(BaseModel):
    """Todo 项目"""
    
    id: str = Field(default_factory=lambda: f"todo_{uuid.uuid4().hex[:8]}")
    content: str
    status: Literal["pending", "in_progress", "completed", "blocked", "failed"] = "pending"
    priority: int = 0
    dependencies: List[str] = Field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "priority": self.priority,
            "dependencies": self.dependencies,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TodoItem":
        data = data.copy()
        for field in ["created_at", "started_at", "completed_at"]:
            if field in data and data[field] and isinstance(data[field], str):
                data[field] = datetime.fromisoformat(data[field])
        return cls(**data)


class InterruptPoint(BaseModel):
    """中断点信息"""
    
    interrupt_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    session_id: str
    execution_id: str
    
    step_index: int
    phase: str
    
    reason: str
    error_message: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interrupt_id": self.interrupt_id,
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "step_index": self.step_index,
            "phase": self.phase,
            "reason": self.reason,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InterruptPoint":
        data = data.copy()
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


class RecoveryState(BaseModel):
    """恢复状态"""
    
    recovery_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex))
    session_id: str
    checkpoint_id: str
    
    interrupt_point: InterruptPoint
    
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    tool_execution_history: List[Dict[str, Any]] = Field(default_factory=list)
    decision_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    pending_interactions: List[InteractionRequest] = Field(default_factory=list)
    pending_actions: List[Dict[str, Any]] = Field(default_factory=list)
    
    files_created: List[Dict[str, Any]] = Field(default_factory=list)
    files_modified: List[Dict[str, Any]] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    
    todo_list: List[TodoItem] = Field(default_factory=list)
    completed_subtasks: List[str] = Field(default_factory=list)
    pending_subtasks: List[str] = Field(default_factory=list)
    
    original_goal: str = ""
    current_subgoal: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.now)
    snapshot_size: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "session_id": self.session_id,
            "checkpoint_id": self.checkpoint_id,
            "interrupt_point": self.interrupt_point.to_dict(),
            "conversation_history": self.conversation_history,
            "tool_execution_history": self.tool_execution_history,
            "decision_history": self.decision_history,
            "pending_interactions": [r.to_dict() for r in self.pending_interactions],
            "pending_actions": self.pending_actions,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "variables": self.variables,
            "todo_list": [t.to_dict() for t in self.todo_list],
            "completed_subtasks": self.completed_subtasks,
            "pending_subtasks": self.pending_subtasks,
            "original_goal": self.original_goal,
            "current_subgoal": self.current_subgoal,
            "created_at": self.created_at.isoformat(),
            "snapshot_size": self.snapshot_size,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryState":
        data = data.copy()
        if "interrupt_point" in data and isinstance(data["interrupt_point"], dict):
            data["interrupt_point"] = InterruptPoint.from_dict(data["interrupt_point"])
        if "pending_interactions" in data:
            data["pending_interactions"] = [
                InteractionRequest.from_dict(r) for r in data["pending_interactions"]
            ]
        if "todo_list" in data:
            data["todo_list"] = [TodoItem.from_dict(t) for t in data["todo_list"]]
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)
    
    def get_progress_summary(self) -> str:
        """获取进度摘要"""
        lines = [
            "## 任务恢复摘要",
            "",
            f"**原始目标**: {self.original_goal}",
            f"**中断点**: 第 {self.interrupt_point.step_index} 步",
            f"**中断原因**: {self.interrupt_point.reason}",
            "",
        ]
        
        if self.todo_list:
            completed = [t for t in self.todo_list if t.status == "completed"]
            pending = [t for t in self.todo_list if t.status != "completed"]
            
            lines.append(f"### 任务进度")
            lines.append(f"- 已完成: {len(completed)} 项")
            lines.append(f"- 待处理: {len(pending)} 项")
            lines.append("")
            
            if pending:
                lines.append("### 待处理任务")
                for t in pending[:5]:
                    status_icon = {"pending": "⏳", "in_progress": "🔄", "blocked": "🚫", "failed": "❌"}.get(t.status, "•")
                    lines.append(f"{status_icon} {t.content}")
                if len(pending) > 5:
                    lines.append(f"- ... 还有 {len(pending) - 5} 项")
        
        return "\n".join(lines)


class RecoveryResult(BaseModel):
    """恢复结果"""
    success: bool
    recovery_context: Optional[RecoveryState] = None
    pending_interaction: Optional[InteractionRequest] = None
    pending_todos: List[TodoItem] = Field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None


class ResumeResult(BaseModel):
    """继续执行结果"""
    success: bool
    checkpoint_id: Optional[str] = None
    step_index: int = 0
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    variables: Dict[str, Any] = Field(default_factory=dict)
    todo_list: List[TodoItem] = Field(default_factory=list)
    response: Optional[InteractionResponse] = None
    error: Optional[str] = None


class InteractionError(Exception):
    """交互异常基类"""
    pass


class InteractionTimeoutError(InteractionError):
    """交互超时异常"""
    pass


class InteractionCancelledError(InteractionError):
    """交互取消异常"""
    pass


class InteractionPendingError(InteractionError):
    """交互等待异常"""
    def __init__(self, request: InteractionRequest):
        self.request = request
        super().__init__(f"Interaction pending: {request.request_id}")


class RecoveryError(Exception):
    """恢复异常"""
    pass


__all__ = [
    "InteractionType",
    "InteractionPriority",
    "InteractionStatus",
    "NotifyLevel",
    "InteractionOption",
    "InteractionRequest",
    "InteractionResponse",
    "TodoItem",
    "InterruptPoint",
    "RecoveryState",
    "RecoveryResult",
    "ResumeResult",
    "InteractionError",
    "InteractionTimeoutError",
    "InteractionCancelledError",
    "InteractionPendingError",
    "RecoveryError",
]