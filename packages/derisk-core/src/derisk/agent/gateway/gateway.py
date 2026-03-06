"""
Gateway - 控制平面核心框架

参考OpenClaw的Gateway设计
简化版本,用于快速实施
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
import json
from pydantic import BaseModel, Field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    """Session状态"""

    ACTIVE = "active"  # 活跃
    IDLE = "idle"  # 空闲
    CLOSED = "closed"  # 已关闭


class Session(BaseModel):
    """Session - 隔离的对话上下文"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = "primary"
    state: SessionState = SessionState.ACTIVE
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """添加消息到Session"""
        message = {
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }
        self.messages.append(message)
        self.last_active = datetime.now()
        logger.debug(f"[Session {self.id[:8]}] 添加消息: {role} - {content[:50]}...")

    def get_context(self) -> Dict[str, Any]:
        """获取Session上下文"""
        return {
            "session_id": self.id,
            "agent_name": self.agent_name,
            "state": self.state.value,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
        }

    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True


class Message(BaseModel):
    """消息模型"""

    type: str  # 消息类型
    session_id: Optional[str] = None  # Session ID
    content: Any  # 消息内容
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        arbitrary_types_allowed = True


class Gateway:
    """
    Gateway控制平面 - 参考OpenClaw设计

    核心职责:
    1. Session管理 - 创建、获取、删除Session
    2. 消息路由 - 分发消息到对应的Session
    3. 状态管理 - 维护Gateway全局状态
    4. 事件广播 - 向客户端推送事件

    示例:
        gateway = Gateway()

        # 创建Session
        session = await gateway.create_session("primary")

        # 发送消息
        await gateway.send_message(session.id, "user", "你好")

        # 获取Session
        session = gateway.get_session(session.id)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Gateway

        Args:
            config: Gateway配置
        """
        self.config = config or {}
        self.sessions: Dict[str, Session] = {}
        self.message_queue = asyncio.Queue()
        self._event_handlers: Dict[str, List] = {}

        logger.info(f"[Gateway] 初始化完成,配置: {self.config}")

    # ========== Session管理 ==========

    async def create_session(
        self, agent_name: str = "primary", metadata: Optional[Dict[str, Any]] = None
    ) -> Session:
        """
        创建新Session

        Args:
            agent_name: Agent名称
            metadata: Session元数据

        Returns:
            Session: 新创建的Session
        """
        session = Session(agent_name=agent_name, metadata=metadata or {})

        self.sessions[session.id] = session

        logger.info(f"[Gateway] 创建Session: {session.id[:8]}, Agent: {agent_name}")

        # 触发事件
        await self._emit_event("session_created", session.get_context())

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取Session

        Args:
            session_id: Session ID

        Returns:
            Optional[Session]: Session对象,不存在则返回None
        """
        return self.sessions.get(session_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有Session"""
        return [session.get_context() for session in self.sessions.values()]

    async def close_session(self, session_id: str):
        """
        关闭Session

        Args:
            session_id: Session ID
        """
        session = self.sessions.get(session_id)
        if session:
            session.state = SessionState.CLOSED
            logger.info(f"[Gateway] 关闭Session: {session_id[:8]}")
            await self._emit_event("session_closed", {"session_id": session_id})

    def delete_session(self, session_id: str):
        """
        删除Session

        Args:
            session_id: Session ID
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"[Gateway] 删除Session: {session_id[:8]}")

    # ========== 消息管理 ==========

    async def send_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        发送消息

        Args:
            session_id: Session ID
            role: 角色
            content: 消息内容
            metadata: 元数据
        """
        session = self.get_session(session_id)
        if not session:
            logger.error(f"[Gateway] Session不存在: {session_id[:8]}")
            return

        session.add_message(role, content, metadata)

        # 将消息放入队列
        message = Message(
            type="agent_message",
            session_id=session_id,
            content={"role": role, "content": content, "metadata": metadata},
        )

        await self.message_queue.put(message)

        # 触发事件
        await self._emit_event("message_received", message.dict())

    async def receive_message(self) -> Optional[Message]:
        """
        接收消息(从队列)

        Returns:
            Optional[Message]: 消息对象
        """
        try:
            message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
            return message
        except asyncio.TimeoutError:
            return None

    # ========== 事件系统 ==========

    def on(self, event_type: str, handler):
        """
        注册事件处理器

        Args:
            event_type: 事件类型
            handler: 处理函数
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def _emit_event(self, event_type: str, data: Any):
        """
        触发事件

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"[Gateway] 事件处理器错误: {event_type} - {e}")

    # ========== 状态查询 ==========

    def get_status(self) -> Dict[str, Any]:
        """获取Gateway状态"""
        active_sessions = sum(
            1 for s in self.sessions.values() if s.state == SessionState.ACTIVE
        )

        return {
            "total_sessions": len(self.sessions),
            "active_sessions": active_sessions,
            "queue_size": self.message_queue.qsize(),
            "config": self.config,
        }

    async def cleanup_idle_sessions(self, idle_timeout: int = 3600):
        """
        清理空闲Session

        Args:
            idle_timeout: 空闲超时时间(秒)
        """
        now = datetime.now()
        to_close = []

        for session_id, session in self.sessions.items():
            idle_seconds = (now - session.last_active).total_seconds()
            if idle_seconds > idle_timeout and session.state == SessionState.IDLE:
                to_close.append(session_id)

        for session_id in to_close:
            await self.close_session(session_id)
            self.delete_session(session_id)

        if to_close:
            logger.info(f"[Gateway] 清理了 {len(to_close)} 个空闲Session")


# 全局Gateway实例
_gateway: Optional[Gateway] = None


def get_gateway() -> Gateway:
    """获取全局Gateway实例"""
    global _gateway
    if _gateway is None:
        _gateway = Gateway()
    return _gateway


def init_gateway(config: Optional[Dict[str, Any]] = None) -> Gateway:
    """初始化全局Gateway"""
    global _gateway
    _gateway = Gateway(config)
    return _gateway
