"""
GptsMessageMemory统一存储适配器

将Core V2的GptsMessageMemory适配到统一存储
底层继续使用gpts_messages表，但通过UnifiedMessage接口
"""
import logging
from typing import List, Optional

from derisk.core.interface.unified_message import UnifiedMessage
from derisk.storage.unified_message_dao import UnifiedMessageDAO

logger = logging.getLogger(__name__)


class GptsMessageMemoryUnifiedAdapter:
    """GptsMessageMemory统一存储适配器
    
    为Core V2的GptsMessageMemory提供统一接口
    底层继续使用gpts_messages表
    """
    
    def __init__(self):
        """初始化适配器"""
        self._unified_dao = UnifiedMessageDAO()
        
        try:
            from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
            self._gpts_messages_dao = GptsMessagesDao()
        except ImportError:
            logger.warning("GptsMessagesDao not available")
            self._gpts_messages_dao = None
    
    async def append(self, message: 'GptsMessage') -> None:
        """追加消息
        
        Args:
            message: GptsMessage实例
        """
        try:
            unified_msg = UnifiedMessage.from_gpts_message(message)
            await self._unified_dao.save_message(unified_msg)
            logger.debug(f"Appended message {message.message_id} via unified DAO")
        except Exception as e:
            logger.error(f"Failed to append message: {e}")
            raise
    
    async def get_by_conv_id(self, conv_id: str) -> List['GptsMessage']:
        """获取对话的所有消息
        
        Args:
            conv_id: 对话ID
            
        Returns:
            GptsMessage列表
        """
        try:
            unified_messages = await self._unified_dao.get_messages_by_conv_id(
                conv_id=conv_id,
                include_thinking=True
            )
            
            gpts_messages = []
            for unified_msg in unified_messages:
                gpts_msg = unified_msg.to_gpts_message()
                gpts_messages.append(gpts_msg)
            
            logger.debug(
                f"Loaded {len(gpts_messages)} messages for conversation {conv_id}"
            )
            return gpts_messages
            
        except Exception as e:
            logger.error(f"Failed to get messages for conversation {conv_id}: {e}")
            raise
    
    async def get_by_session_id(self, session_id: str) -> List['GptsMessage']:
        """获取会话的所有消息
        
        Args:
            session_id: 会话ID
            
        Returns:
            GptsMessage列表
        """
        try:
            unified_messages = await self._unified_dao.get_messages_by_session(
                session_id=session_id
            )
            
            gpts_messages = []
            for unified_msg in unified_messages:
                gpts_msg = unified_msg.to_gpts_message()
                gpts_messages.append(gpts_msg)
            
            logger.debug(
                f"Loaded {len(gpts_messages)} messages for session {session_id}"
            )
            return gpts_messages
            
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            raise
    
    async def get_latest_messages(
        self,
        conv_id: str,
        limit: int = 10
    ) -> List['GptsMessage']:
        """获取最新的N条消息
        
        Args:
            conv_id: 对话ID
            limit: 返回消息数量
            
        Returns:
            GptsMessage列表
        """
        try:
            unified_messages = await self._unified_dao.get_latest_messages(
                conv_id=conv_id,
                limit=limit
            )
            
            gpts_messages = []
            for unified_msg in unified_messages:
                gpts_msg = unified_msg.to_gpts_message()
                gpts_messages.append(gpts_msg)
            
            return gpts_messages
            
        except Exception as e:
            logger.error(f"Failed to get latest messages for conversation {conv_id}: {e}")
            raise
    
    async def delete_by_conv_id(self, conv_id: str) -> None:
        """删除对话的所有消息
        
        Args:
            conv_id: 对话ID
        """
        try:
            await self._unified_dao.delete_conversation(conv_id)
            logger.info(f"Deleted all messages for conversation {conv_id}")
        except Exception as e:
            logger.error(f"Failed to delete messages for conversation {conv_id}: {e}")
            raise


class UnifiedGptsMessageMemory:
    """统一的GptsMessageMemory实现
    
    完全使用UnifiedMessageDAO，保持向后兼容
    """
    
    def __init__(self):
        """初始化"""
        self._adapter = GptsMessageMemoryUnifiedAdapter()
    
    async def append(self, message: 'GptsMessage') -> None:
        """追加消息
        
        Args:
            message: GptsMessage实例
        """
        await self._adapter.append(message)
    
    async def get_by_conv_id(self, conv_id: str) -> List['GptsMessage']:
        """获取对话消息
        
        Args:
            conv_id: 对话ID
            
        Returns:
            GptsMessage列表
        """
        return await self._adapter.get_by_conv_id(conv_id)
    
    async def get_by_session_id(self, session_id: str) -> List['GptsMessage']:
        """获取会话消息
        
        Args:
            session_id: 会话ID
            
        Returns:
            GptsMessage列表
        """
        return await self._adapter.get_by_session_id(session_id)
    
    async def get_latest_messages(
        self,
        conv_id: str,
        limit: int = 10
    ) -> List['GptsMessage']:
        """获取最新消息
        
        Args:
            conv_id: 对话ID
            limit: 返回数量
            
        Returns:
            GptsMessage列表
        """
        return await self._adapter.get_latest_messages(conv_id, limit)
    
    async def delete_by_conv_id(self, conv_id: str) -> None:
        """删除对话消息
        
        Args:
            conv_id: 对话ID
        """
        await self._adapter.delete_by_conv_id(conv_id)


def create_unified_gpts_memory() -> UnifiedGptsMessageMemory:
    """创建统一的GptsMessageMemory实例
    
    Returns:
        UnifiedGptsMessageMemory实例
    """
    return UnifiedGptsMessageMemory()