"""
统一会话管理器实现
"""

import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import UnifiedMessage, UnifiedSession

logger = logging.getLogger(__name__)


class UnifiedSessionManager:
    """
    统一会话管理器
    
    核心职责：
    1. 统一会话创建和管理
    2. 统一历史消息查询
    3. 自动适配V1/V2存储
    """
    
    def __init__(self, system_app: Any = None):
        self._system_app = system_app
        self._sessions: Dict[str, UnifiedSession] = {}
        self._conv_to_session: Dict[str, str] = {}
    
    async def create_session(
        self,
        app_code: str,
        user_id: Optional[str] = None,
        agent_version: str = "v2",
        session_id: Optional[str] = None,
        conv_id: Optional[str] = None,
    ) -> UnifiedSession:
        """
        创建会话，自动适配V1/V2
        
        Args:
            app_code: 应用代码
            user_id: 用户ID
            agent_version: Agent版本
            session_id: 会话ID（可选）
            conv_id: 对话ID（可选）
            
        Returns:
            UnifiedSession: 统一会话实例
        """
        session_id = session_id or self._generate_session_id()
        conv_id = conv_id or session_id
        
        logger.info(
            f"[UnifiedSessionManager] 创建会话: session_id={session_id}, "
            f"conv_id={conv_id}, app_code={app_code}, version={agent_version}"
        )
        
        storage_conv = await self._create_storage_session(
            conv_id=conv_id,
            app_code=app_code,
            user_id=user_id
        )
        
        runtime_session = None
        if agent_version == "v2":
            runtime_session = await self._create_runtime_session(
                session_id=session_id,
                conv_id=conv_id,
                app_code=app_code,
                user_id=user_id
            )
        
        session = UnifiedSession(
            session_id=session_id,
            conv_id=conv_id,
            app_code=app_code,
            user_id=user_id,
            agent_version=agent_version,
            storage_conv=storage_conv,
            runtime_session=runtime_session,
        )
        
        self._sessions[session_id] = session
        self._conv_to_session[conv_id] = session_id
        
        return session
    
    async def get_session(
        self,
        session_id: Optional[str] = None,
        conv_id: Optional[str] = None
    ) -> Optional[UnifiedSession]:
        """
        获取会话
        
        优先使用session_id，其次使用conv_id
        """
        if session_id:
            return self._sessions.get(session_id)
        
        if conv_id:
            session_id = self._conv_to_session.get(conv_id)
            if session_id:
                return self._sessions.get(session_id)
        
        return None
    
    async def close_session(self, session_id: str):
        """关闭会话"""
        session = self._sessions.get(session_id)
        if not session:
            return
        
        logger.info(f"[UnifiedSessionManager] 关闭会话: {session_id}")
        
        if session.runtime_session:
            try:
                if hasattr(session.runtime_session, "close"):
                    await session.runtime_session.close()
            except Exception as e:
                logger.error(f"[UnifiedSessionManager] 关闭运行时会话失败: {e}")
        
        if session.storage_conv:
            try:
                if hasattr(session.storage_conv, "clear"):
                    session.storage_conv.clear()
            except Exception as e:
                logger.error(f"[UnifiedSessionManager] 清理存储会话失败: {e}")
        
        self._sessions.pop(session_id, None)
        self._conv_to_session.pop(session.conv_id, None)
    
    async def get_history(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[UnifiedMessage]:
        """
        统一的历史消息查询
        
        自动适配V1/V2存储
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[UnifiedSessionManager] 会话不存在: {session_id}")
            return []
        
        if session.history and not offset:
            return session.history[-limit:]
        
        messages = []
        
        if session.agent_version == "v2":
            messages = await self._get_v2_history(session, limit, offset)
        else:
            messages = await self._get_v1_history(session, limit, offset)
        
        return messages
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UnifiedMessage:
        """添加消息到会话"""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")
        
        message = UnifiedMessage(
            id=str(uuid.uuid4().hex),
            role=role,
            content=content,
            metadata=metadata or {}
        )
        
        session.history.append(message)
        session.message_count += 1
        session.updated_at = datetime.now()
        
        if session.agent_version == "v2" and session.runtime_session:
            await self._persist_v2_message(session, message)
        elif session.storage_conv:
            await self._persist_v1_message(session, message)
        
        return message
    
    async def _create_storage_session(
        self,
        conv_id: str,
        app_code: str,
        user_id: Optional[str]
    ) -> Optional[Any]:
        """创建存储会话（V1兼容）"""
        try:
            from derisk.core import StorageConversation
            from derisk_serve.conversation.serve import Serve
            
            serve = Serve.get_instance(self._system_app)
            storage = serve.conv_storage
            message_storage = serve.message_storage
            
            storage_conv = StorageConversation(
                conv_uid=conv_id,
                chat_mode="chat_agent",
                user_name=user_id or "",
                sys_code="",
                conv_storage=storage,
                message_storage=message_storage,
                load_message=False
            )
            
            return storage_conv
        except Exception as e:
            logger.warning(f"[UnifiedSessionManager] 创建存储会话失败: {e}")
            return None
    
    async def _create_runtime_session(
        self,
        session_id: str,
        conv_id: str,
        app_code: str,
        user_id: Optional[str]
    ) -> Optional[Any]:
        """创建运行时会话（V2专用）"""
        try:
            from derisk.agent.core_v2.integration.runtime import SessionContext
            
            context = SessionContext(
                session_id=session_id,
                conv_id=conv_id,
                user_id=user_id,
                agent_name=app_code,
            )
            
            return context
        except Exception as e:
            logger.warning(f"[UnifiedSessionManager] 创建运行时会话失败: {e}")
            return None
    
    async def _get_v1_history(
        self,
        session: UnifiedSession,
        limit: int,
        offset: int
    ) -> List[UnifiedMessage]:
        """获取V1历史消息"""
        if not session.storage_conv:
            return []
        
        try:
            messages = session.storage_conv.messages
            
            unified_messages = []
            for msg in messages[offset:offset + limit]:
                unified_messages.append(self._to_unified_message(msg, "v1"))
            
            return unified_messages
        except Exception as e:
            logger.error(f"[UnifiedSessionManager] 获取V1历史失败: {e}")
            return []
    
    async def _get_v2_history(
        self,
        session: UnifiedSession,
        limit: int,
        offset: int
    ) -> List[UnifiedMessage]:
        """获取V2历史消息"""
        try:
            from derisk.agent.core.memory.gpts import GptsMemory
            
            gpts_memory = GptsMemory.get_instance(self._system_app)
            if not gpts_memory:
                return []
            
            messages = await gpts_memory.get_messages(
                session.conv_id,
                limit=limit,
                offset=offset
            )
            
            unified_messages = []
            for msg in messages:
                unified_messages.append(self._to_unified_message(msg, "v2"))
            
            return unified_messages
        except Exception as e:
            logger.error(f"[UnifiedSessionManager] 获取V2历史失败: {e}")
            return []
    
    def _to_unified_message(self, msg: Any, version: str) -> UnifiedMessage:
        """转换为统一消息格式"""
        if hasattr(msg, "to_dict"):
            msg_dict = msg.to_dict()
        elif hasattr(msg, "dict"):
            msg_dict = msg.dict()
        else:
            msg_dict = dict(msg) if msg else {}
        
        return UnifiedMessage(
            id=msg_dict.get("message_id", str(uuid.uuid4().hex)),
            role=msg_dict.get("role", msg_dict.get("type", "user")),
            content=msg_dict.get("content", msg_dict.get("context", "")),
            timestamp=msg_dict.get("timestamp", msg_dict.get("created_at", datetime.now())),
            metadata={
                "version": version,
                "round_index": msg_dict.get("round_index", msg_dict.get("rounds")),
                **msg_dict.get("metadata", {})
            }
        )
    
    async def _persist_v1_message(self, session: UnifiedSession, message: UnifiedMessage):
        """持久化V1消息"""
        if not session.storage_conv:
            return
        
        try:
            from derisk.core.interface.message import MessageStorageItem
            
            storage_item = MessageStorageItem(
                conv_uid=session.conv_id,
                index=session.message_count,
                message_id=message.id,
                round_index=session.message_count,
                type=message.role,
                content=message.content,
            )
            
            session.storage_conv.append_message(storage_item)
        except Exception as e:
            logger.error(f"[UnifiedSessionManager] 持久化V1消息失败: {e}")
    
    async def _persist_v2_message(self, session: UnifiedSession, message: UnifiedMessage):
        """持久化V2消息"""
        try:
            from derisk.agent.core.memory.gpts import GptsMemory
            
            gpts_memory = GptsMemory.get_instance(self._system_app)
            if not gpts_memory:
                return
            
            gpts_msg = type("GptsMessage", (), {
                "message_id": message.id,
                "conv_id": session.conv_id,
                "sender": message.role,
                "receiver": "user" if message.role == "assistant" else "assistant",
                "content": message.content,
                "rounds": session.message_count,
            })()
            
            await gpts_memory.append_message(session.conv_id, gpts_msg, save_db=True)
        except Exception as e:
            logger.error(f"[UnifiedSessionManager] 持久化V2消息失败: {e}")
    
    def _generate_session_id(self) -> str:
        """生成会话ID"""
        return str(uuid.uuid4().hex)