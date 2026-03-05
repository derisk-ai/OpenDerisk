"""
Team Messenger - 团队消息系统

实现Agent间的消息传递：
1. 点对点消息 - Agent间直接通信
2. 广播消息 - 向所有Agent广播
3. 订阅机制 - 按类型订阅消息
4. 消息历史 - 记录消息历史

@see ARCHITECTURE.md#12.7-teammessenger-消息系统
"""

from typing import Any, Callable, Dict, List, Optional, Awaitable
from datetime import datetime
from enum import Enum
import asyncio
import logging
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """消息类型"""
    TASK_ASSIGNED = "task_assigned"          # 任务分配
    TASK_STARTED = "task_started"            # 任务开始
    TASK_COMPLETED = "task_completed"        # 任务完成
    TASK_FAILED = "task_failed"              # 任务失败
    PROGRESS_UPDATE = "progress_update"      # 进度更新
    ARTIFACT_CREATED = "artifact_created"    # 产出物创建
    HELP_REQUEST = "help_request"            # 帮助请求
    HELP_RESPONSE = "help_response"          # 帮助响应
    STATUS_UPDATE = "status_update"          # 状态更新
    ERROR_REPORT = "error_report"            # 错误报告
    COORDINATION = "coordination"            # 协调消息
    CUSTOM = "custom"                        # 自定义消息


class MessagePriority(str, Enum):
    """消息优先级"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AgentMessage(BaseModel):
    """Agent消息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:12])
    type: MessageType
    sender: str
    receiver: Optional[str] = None  # None表示广播
    
    content: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    priority: MessagePriority = MessagePriority.NORMAL
    timestamp: datetime = Field(default_factory=datetime.now)
    
    requires_ack: bool = False
    ack_received: bool = False
    correlation_id: Optional[str] = None  # 用于关联请求/响应
    
    ttl: int = 60  # 生存时间（秒）
    delivered: bool = False
    
    class Config:
        arbitrary_types_allowed = True


class BroadcastMessage(BaseModel):
    """广播消息"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4().hex)[:12])
    type: MessageType
    sender: str
    
    content: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    timestamp: datetime = Field(default_factory=datetime.now)
    
    recipients: List[str] = Field(default_factory=list)
    delivered_to: List[str] = Field(default_factory=list)


class MessageHistory:
    """消息历史记录"""
    
    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._messages: List[AgentMessage] = []
        self._by_sender: Dict[str, List[str]] = {}
        self._by_type: Dict[MessageType, List[str]] = {}
        self._lock = asyncio.Lock()
    
    async def add(self, message: AgentMessage) -> None:
        """添加消息到历史"""
        async with self._lock:
            if len(self._messages) >= self._max_size:
                removed = self._messages.pop(0)
                self._remove_index(removed)
            
            self._messages.append(message)
            
            if message.sender not in self._by_sender:
                self._by_sender[message.sender] = []
            self._by_sender[message.sender].append(message.id)
            
            if message.type not in self._by_type:
                self._by_type[message.type] = []
            self._by_type[message.type].append(message.id)
    
    def _remove_index(self, message: AgentMessage) -> None:
        """移除索引"""
        if message.sender in self._by_sender:
            try:
                self._by_sender[message.sender].remove(message.id)
            except ValueError:
                pass
        
        if message.type in self._by_type:
            try:
                self._by_type[message.type].remove(message.id)
            except ValueError:
                pass
    
    async def get_by_sender(self, sender: str, limit: int = 10) -> List[AgentMessage]:
        """按发送者获取消息"""
        async with self._lock:
            ids = self._by_sender.get(sender, [])[-limit:]
            return [m for m in self._messages if m.id in ids]
    
    async def get_by_type(self, msg_type: MessageType, limit: int = 10) -> List[AgentMessage]:
        """按类型获取消息"""
        async with self._lock:
            ids = self._by_type.get(msg_type, [])[-limit:]
            return [m for m in self._messages if m.id in ids]
    
    async def get_recent(self, limit: int = 20) -> List[AgentMessage]:
        """获取最近消息"""
        async with self._lock:
            return self._messages[-limit:]


class TeamMessenger:
    """
    团队消息系统
    
    提供Agent间的消息传递能力。
    
    @example
    ```python
    messenger = TeamMessenger()
    
    # 订阅消息
    async def handle_task(msg: AgentMessage):
        print(f"Received: {msg.content}")
    
    messenger.subscribe("agent-1", MessageType.TASK_ASSIGNED, handle_task)
    
    # 发送点对点消息
    await messenger.send(AgentMessage(
        type=MessageType.TASK_ASSIGNED,
        sender="coordinator",
        receiver="agent-1",
        content={"task_id": "task-123"},
    ))
    
    # 广播消息
    await messenger.broadcast(MessageType.STATUS_UPDATE, {"status": "running"})
    ```
    """
    
    def __init__(
        self,
        enable_history: bool = True,
        history_size: int = 1000,
    ):
        self._enable_history = enable_history
        self._history = MessageHistory(max_size=history_size) if enable_history else None
        
        self._subscribers: Dict[str, Dict[MessageType, List[Callable]]] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._pending_acks: Dict[str, asyncio.Event] = {}
        
        self._lock = asyncio.Lock()
    
    async def send(self, message: AgentMessage) -> bool:
        """
        发送点对点消息
        
        Args:
            message: 要发送的消息
        
        Returns:
            是否发送成功
        """
        if not message.receiver:
            logger.warning("[Messenger] No receiver specified, use broadcast instead")
            return False
        
        async with self._lock:
            receiver = message.receiver
            
            if receiver not in self._subscribers:
                logger.warning(f"[Messenger] No subscriber for: {receiver}")
                return False
            
            handlers = self._subscribers[receiver].get(message.type, [])
            
            if not handlers:
                if receiver in self._queues:
                    await self._queues[receiver].put(message)
            else:
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        logger.error(f"[Messenger] Handler error: {e}")
            
            message.delivered = True
            
            if self._enable_history and self._history:
                await self._history.add(message)
            
            if message.requires_ack:
                self._pending_acks[message.id] = asyncio.Event()
            
            logger.debug(f"[Messenger] Sent {message.type.value} from {message.sender} to {receiver}")
            return True
    
    async def broadcast(
        self,
        msg_type: MessageType,
        content: Any,
        sender: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BroadcastMessage:
        """
        广播消息
        
        Args:
            msg_type: 消息类型
            content: 消息内容
            sender: 发送者
            metadata: 元数据
        
        Returns:
            广播消息记录
        """
        broadcast_msg = BroadcastMessage(
            type=msg_type,
            sender=sender,
            content=content,
            metadata=metadata or {},
            recipients=list(self._subscribers.keys()),
        )
        
        message = AgentMessage(
            type=msg_type,
            sender=sender,
            content=content,
            metadata=metadata or {},
        )
        
        async with self._lock:
            for receiver, handlers_by_type in self._subscribers.items():
                handlers = handlers_by_type.get(msg_type, [])
                
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message)
                        else:
                            handler(message)
                    except Exception as e:
                        logger.error(f"[Messenger] Broadcast handler error for {receiver}: {e}")
                
                if receiver in self._queues:
                    msg_copy = message.model_copy()
                    msg_copy.receiver = receiver
                    await self._queues[receiver].put(msg_copy)
                
                broadcast_msg.delivered_to.append(receiver)
            
            if self._enable_history and self._history:
                await self._history.add(message)
        
        logger.debug(f"[Messenger] Broadcast {msg_type.value} to {len(broadcast_msg.delivered_to)} agents")
        return broadcast_msg
    
    def subscribe(
        self,
        agent_id: str,
        msg_type: MessageType,
        handler: Callable[[AgentMessage], Awaitable[None]],
    ) -> None:
        """
        订阅特定类型的消息
        
        Args:
            agent_id: Agent ID
            msg_type: 消息类型
            handler: 处理函数
        """
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = {}
        
        if msg_type not in self._subscribers[agent_id]:
            self._subscribers[agent_id][msg_type] = []
        
        self._subscribers[agent_id][msg_type].append(handler)
        
        logger.debug(f"[Messenger] {agent_id} subscribed to {msg_type.value}")
    
    def unsubscribe(
        self,
        agent_id: str,
        msg_type: Optional[MessageType] = None,
    ) -> None:
        """
        取消订阅
        
        Args:
            agent_id: Agent ID
            msg_type: 消息类型（None表示取消所有订阅）
        """
        if agent_id not in self._subscribers:
            return
        
        if msg_type:
            self._subscribers[agent_id].pop(msg_type, None)
        else:
            del self._subscribers[agent_id]
        
        logger.debug(f"[Messenger] {agent_id} unsubscribed from {msg_type.value if msg_type else 'all'}")
    
    async def get_message_queue(self, agent_id: str) -> asyncio.Queue:
        """
        获取消息队列
        
        Args:
            agent_id: Agent ID
        
        Returns:
            消息队列
        """
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
        return self._queues[agent_id]
    
    async def ack(self, message_id: str) -> None:
        """
        确认消息
        
        Args:
            message_id: 消息ID
        """
        if message_id in self._pending_acks:
            self._pending_acks[message_id].set()
    
    async def wait_for_ack(
        self,
        message_id: str,
        timeout: float = 10.0,
    ) -> bool:
        """
        等待确认
        
        Args:
            message_id: 消息ID
            timeout: 超时时间
        
        Returns:
            是否收到确认
        """
        if message_id not in self._pending_acks:
            return False
        
        try:
            await asyncio.wait_for(
                self._pending_acks[message_id].wait(),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_acks.pop(message_id, None)
    
    async def get_history(
        self,
        sender: Optional[str] = None,
        msg_type: Optional[MessageType] = None,
        limit: int = 20,
    ) -> List[AgentMessage]:
        """
        获取消息历史
        
        Args:
            sender: 发送者过滤
            msg_type: 类型过滤
            limit: 数量限制
        
        Returns:
            消息列表
        """
        if not self._enable_history or not self._history:
            return []
        
        if sender:
            return await self._history.get_by_sender(sender, limit)
        elif msg_type:
            return await self._history.get_by_type(msg_type, limit)
        else:
            return await self._history.get_recent(limit)
    
    def get_subscribers(self) -> Dict[str, List[MessageType]]:
        """获取所有订阅者及其订阅的消息类型"""
        return {
            agent_id: list(handlers.keys())
            for agent_id, handlers in self._subscribers.items()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        history_count = len(self._history._messages) if self._history else 0
        
        return {
            "total_subscribers": len(self._subscribers),
            "total_queues": len(self._queues),
            "history_size": history_count,
            "pending_acks": len(self._pending_acks),
        }