"""
SSE Stream Manager - SSE流式输出管理器

支持两种部署模式：
1. 单机模式（默认）：无需Redis，用户输入通过HTTP请求直接到达执行节点
2. 分布式模式：需要Redis，用户输入通过Redis Pub/Sub路由到执行节点

SSE模式下的用户输入流程：
- 单机模式：前端SSE连接 + HTTP输入请求都在同一进程，直接处理
- 分布式模式：输入请求通过Redis路由到执行节点的Agent
"""

from typing import Dict, List, Optional, Any, AsyncIterator, Callable
from datetime import datetime
from enum import Enum
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
import os

logger = logging.getLogger(__name__)


class ExecutionPhase(str, Enum):
    """执行阶段"""
    THINKING = "thinking"
    DECIDING = "deciding"
    ACTING = "acting"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    ERROR = "error"


class StepBoundary(str, Enum):
    """步骤边界类型"""
    BEFORE_THINK = "before_think"
    AFTER_THINK = "after_think"
    BEFORE_DECIDE = "before_decide"
    AFTER_DECIDE = "after_decide"
    BEFORE_ACT = "before_act"
    AFTER_ACT = "after_act"
    STEP_COMPLETE = "step_complete"


@dataclass
class ExecutionState:
    """执行状态"""
    session_id: str
    execution_id: str
    node_id: str
    status: str = "running"
    current_step: int = 0
    phase: ExecutionPhase = ExecutionPhase.THINKING
    started_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "status": self.status,
            "current_step": self.current_step,
            "phase": self.phase.value,
            "started_at": self.started_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionState":
        return cls(
            session_id=data["session_id"],
            execution_id=data["execution_id"],
            node_id=data["node_id"],
            status=data.get("status", "running"),
            current_step=data.get("current_step", 0),
            phase=ExecutionPhase(data.get("phase", "thinking")),
            started_at=datetime.fromisoformat(data["started_at"]) if "started_at" in data else datetime.now(),
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]) if "last_heartbeat" in data else datetime.now(),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SSEEvent:
    """SSE事件"""
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_sse(self) -> str:
        return f"data: {json.dumps({'type': self.event_type, **self.data, 'timestamp': self.timestamp.isoformat()})}\n\n"


@dataclass
class UserInputMessage:
    """用户输入消息"""
    session_id: str
    content: str
    input_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class SSEStreamManager:
    """
    SSE流管理器
    
    支持两种模式：
    1. 单机模式（默认，无需Redis）：
       - 所有执行状态存在内存
       - 用户输入直接放入本地队列
       - 适合单节点部署
    
    2. 分布式模式（需要Redis）：
       - 执行状态存储在Redis
       - 用户输入通过Redis Pub/Sub路由
       - 适合多节点负载均衡部署
    """
    
    KEY_PREFIX = "derisk:sse:"
    
    def __init__(
        self,
        store=None,
        node_id: Optional[str] = None,
        heartbeat_interval: int = 10,
        execution_ttl: int = 3600,
        enable_distributed: Optional[bool] = None,
    ):
        self._store = store
        self._enable_distributed = enable_distributed
        self._store_initialized = False
        
        self.node_id = node_id or self._generate_node_id()
        self.heartbeat_interval = heartbeat_interval
        self.execution_ttl = execution_ttl
        
        self._local_executions: Dict[str, ExecutionState] = {}
        self._input_queues: Dict[str, asyncio.Queue] = {}
        self._sse_connections: Dict[str, asyncio.Queue] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._subscriber_task: Optional[asyncio.Task] = None
        
        self._is_distributed = False
    
    @property
    def store(self):
        """延迟初始化存储"""
        if not self._store_initialized:
            self._store_initialized = True
            if self._store is not None:
                pass
            elif self._enable_distributed is False:
                self._store = None
            else:
                redis_url = os.getenv("REDIS_URL", "")
                if redis_url:
                    try:
                        from .distributed_store import RedisStateStore
                        self._store = RedisStateStore(redis_url)
                        self._is_distributed = True
                        logger.info(f"[SSEStreamManager] Distributed mode enabled with Redis")
                    except Exception as e:
                        logger.warning(f"[SSEStreamManager] Redis not available, using local mode: {e}")
                        self._store = None
                else:
                    self._store = None
            
            if self._store is None:
                self._is_distributed = False
                logger.info(f"[SSEStreamManager] Local mode enabled (no external dependencies)")
        
        return self._store
    
    @property
    def is_distributed(self) -> bool:
        return self._is_distributed
    
    def _generate_node_id(self) -> str:
        import socket
        return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    
    def _key(self, key: str) -> str:
        return f"{self.KEY_PREFIX}{key}"
    
    async def start(self):
        """启动管理器"""
        _ = self.store
        
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        if self._is_distributed and self.store:
            self._subscriber_task = asyncio.create_task(self._subscribe_inputs())
        
        mode = "distributed" if self._is_distributed else "local"
        logger.info(f"[SSEStreamManager] Started on node {self.node_id} ({mode} mode)")
    
    async def stop(self):
        """停止管理器"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._subscriber_task:
            self._subscriber_task.cancel()
        logger.info(f"[SSEStreamManager] Stopped on node {self.node_id}")
    
    async def register_execution(
        self,
        session_id: str,
        execution_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionState:
        """注册执行"""
        state = ExecutionState(
            session_id=session_id,
            execution_id=execution_id,
            node_id=self.node_id,
            metadata=metadata or {},
        )
        
        self._local_executions[session_id] = state
        self._input_queues[session_id] = asyncio.Queue()
        
        if self._is_distributed and self.store:
            await self.store.set(
                self._key(f"exec:{session_id}"),
                state.to_dict(),
                ttl=self.execution_ttl,
            )
        
        logger.info(f"[SSEStreamManager] Registered execution {execution_id} for session {session_id}")
        return state
    
    async def unregister_execution(self, session_id: str):
        """注销执行"""
        if session_id in self._local_executions:
            del self._local_executions[session_id]
        if session_id in self._input_queues:
            del self._input_queues[session_id]
        if session_id in self._sse_connections:
            del self._sse_connections[session_id]
        
        if self._is_distributed and self.store:
            await self.store.delete(self._key(f"exec:{session_id}"))
        
        logger.info(f"[SSEStreamManager] Unregistered execution for session {session_id}")
    
    async def update_execution_state(
        self,
        session_id: str,
        status: Optional[str] = None,
        phase: Optional[ExecutionPhase] = None,
        current_step: Optional[int] = None,
    ):
        """更新执行状态"""
        if session_id not in self._local_executions:
            return
        
        state = self._local_executions[session_id]
        
        if status:
            state.status = status
        if phase:
            state.phase = phase
        if current_step is not None:
            state.current_step = current_step
        
        state.last_heartbeat = datetime.now()
        
        if self._is_distributed and self.store:
            await self.store.set(
                self._key(f"exec:{session_id}"),
                state.to_dict(),
                ttl=self.execution_ttl,
            )
    
    async def get_execution_node(self, session_id: str) -> Optional[str]:
        """获取执行节点ID"""
        if session_id in self._local_executions:
            return self.node_id
        
        if self._is_distributed and self.store:
            state_data = await self.store.get(self._key(f"exec:{session_id}"))
            if state_data:
                return state_data.get("node_id")
        
        return None
    
    async def is_local_execution(self, session_id: str) -> bool:
        """检查是否是本地执行"""
        return session_id in self._local_executions
    
    async def submit_user_input(
        self,
        session_id: str,
        content: str,
        input_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        提交用户输入
        
        单机模式：直接放入本地队列
        分布式模式：通过Redis路由到执行节点
        """
        message = UserInputMessage(
            session_id=session_id,
            content=content,
            input_type=input_type,
            metadata=metadata or {},
        )
        
        if session_id in self._input_queues:
            await self._input_queues[session_id].put(message)
            logger.info(f"[SSEStreamManager] Input queued locally for session {session_id}")
            return True
        
        if self._is_distributed and self.store:
            node_id = await self.get_execution_node(session_id)
            if node_id:
                if node_id == self.node_id:
                    if session_id in self._input_queues:
                        await self._input_queues[session_id].put(message)
                        logger.info(f"[SSEStreamManager] Input queued locally for session {session_id}")
                        return True
                else:
                    await self.store.publish(
                        self._key(f"input:{node_id}"),
                        {
                            "session_id": session_id,
                            "content": content,
                            "input_type": input_type,
                            "metadata": metadata or {},
                        },
                    )
                    logger.info(f"[SSEStreamManager] Input routed to node {node_id} for session {session_id}")
                    return True
        
        logger.warning(f"[SSEStreamManager] No active execution for session {session_id}")
        return False
    
    async def get_pending_user_input(
        self,
        session_id: str,
        timeout: float = 0.1,
    ) -> Optional[UserInputMessage]:
        """获取待处理的用户输入"""
        if session_id not in self._input_queues:
            return None
        
        try:
            return await asyncio.wait_for(
                self._input_queues[session_id].get(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return None
    
    async def has_pending_user_input(self, session_id: str) -> bool:
        """检查是否有待处理的用户输入"""
        if session_id not in self._input_queues:
            return False
        return not self._input_queues[session_id].empty()
    
    def register_sse_connection(self, session_id: str) -> asyncio.Queue:
        """注册SSE连接（用于向客户端发送事件）"""
        queue = asyncio.Queue()
        self._sse_connections[session_id] = queue
        return queue
    
    def unregister_sse_connection(self, session_id: str):
        """注销SSE连接"""
        if session_id in self._sse_connections:
            del self._sse_connections[session_id]
    
    async def send_sse_event(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any],
    ):
        """发送SSE事件到客户端"""
        event = SSEEvent(event_type=event_type, data=data)
        
        if session_id in self._sse_connections:
            await self._sse_connections[session_id].put(event.to_sse())
        
        if self._is_distributed and self.store:
            await self.store.publish(
                self._key(f"stream:{session_id}"),
                {"event": event.to_sse()},
            )
    
    async def create_sse_stream(
        self,
        session_id: str,
        execution_id: str,
    ) -> AsyncIterator[str]:
        """创建SSE流"""
        await self.register_execution(session_id, execution_id)
        
        queue = self.register_sse_connection(session_id)
        
        try:
            while True:
                state = self._local_executions.get(session_id)
                if state and state.status in ["completed", "error"]:
                    break
                
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now().isoformat()})}\n\n"
                
        except asyncio.CancelledError:
            pass
        finally:
            self.unregister_sse_connection(session_id)
            await self.unregister_execution(session_id)
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while True:
            try:
                for session_id, state in list(self._local_executions.items()):
                    state.last_heartbeat = datetime.now()
                    if self._is_distributed and self.store:
                        await self.store.set(
                            self._key(f"exec:{session_id}"),
                            state.to_dict(),
                            ttl=self.execution_ttl,
                        )
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SSEStreamManager] Heartbeat error: {e}")
                await asyncio.sleep(1)
    
    async def _subscribe_inputs(self):
        """订阅用户输入（仅分布式模式）"""
        if not self.store:
            return
            
        subscription = await self.store.subscribe(self._key(f"input:{self.node_id}"))
        
        try:
            while True:
                message = await subscription.get_message(timeout=1.0)
                if message:
                    session_id = message.get("session_id")
                    if session_id and session_id in self._input_queues:
                        input_msg = UserInputMessage(
                            session_id=session_id,
                            content=message.get("content", ""),
                            input_type=message.get("input_type", "text"),
                            metadata=message.get("metadata", {}),
                        )
                        await self._input_queues[session_id].put(input_msg)
                        logger.info(f"[SSEStreamManager] Received remote input for session {session_id}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[SSEStreamManager] Input subscriber error: {e}")


_sse_manager: Optional[SSEStreamManager] = None


def get_sse_manager() -> SSEStreamManager:
    """获取SSE管理器实例"""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEStreamManager()
    return _sse_manager


def set_sse_manager(manager: SSEStreamManager):
    """设置SSE管理器实例"""
    global _sse_manager
    _sse_manager = manager


__all__ = [
    "ExecutionPhase",
    "StepBoundary",
    "ExecutionState",
    "SSEEvent",
    "UserInputMessage",
    "SSEStreamManager",
    "get_sse_manager",
    "set_sse_manager",
]