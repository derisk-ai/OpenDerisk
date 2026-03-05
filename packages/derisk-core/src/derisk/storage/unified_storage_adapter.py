"""
StorageConversation统一存储适配器

将Core V1的StorageConversation适配到统一存储（gpts_messages）
不修改原有StorageConversation代码，保持向后兼容
"""
import logging
import uuid
from typing import Optional, List
from datetime import datetime

from derisk.core.interface.unified_message import UnifiedMessage
from derisk.storage.unified_message_dao import UnifiedMessageDAO

logger = logging.getLogger(__name__)


class StorageConversationUnifiedAdapter:
    """StorageConversation统一存储适配器
    
    为Core V1的StorageConversation提供统一存储能力
    底层使用gpts_messages表
    """
    
    def __init__(self, storage_conv: 'StorageConversation'):
        """初始化适配器
        
        Args:
            storage_conv: StorageConversation实例
        """
        self.storage_conv = storage_conv
        self._unified_dao = UnifiedMessageDAO()
    
    async def save_to_unified_storage(self) -> None:
        """保存到统一存储
        
        将StorageConversation的消息保存到gpts_messages表
        """
        try:
            conv_id = self.storage_conv.conv_uid
            user_name = self.storage_conv.user_name or "unknown"
            
            await self._unified_dao.create_conversation(
                conv_id=conv_id,
                user_id=user_name,
                goal=getattr(self.storage_conv, 'summary', None),
                chat_mode=self.storage_conv.chat_mode,
                agent_name=getattr(self.storage_conv, 'agent_name', None),
                session_id=getattr(self.storage_conv, 'session_id', None)
            )
            
            messages = self.storage_conv.messages or []
            unified_messages = []
            
            for idx, msg in enumerate(messages):
                sender = self._get_sender_from_message(msg)
                
                unified_msg = UnifiedMessage.from_base_message(
                    msg=msg,
                    conv_id=conv_id,
                    conv_session_id=getattr(self.storage_conv, 'session_id', conv_id),
                    message_id=f"{conv_id}_msg_{idx}",
                    sender=sender,
                    sender_name=user_name,
                    round_index=getattr(msg, 'round_index', 0),
                    index=idx
                )
                
                unified_messages.append(unified_msg)
            
            if unified_messages:
                await self._unified_dao.save_messages_batch(unified_messages)
                logger.info(
                    f"Saved {len(unified_messages)} messages to unified storage "
                    f"for conversation {conv_id}"
                )
        except Exception as e:
            logger.error(
                f"Failed to save conversation {self.storage_conv.conv_uid} "
                f"to unified storage: {e}"
            )
            raise
    
    async def load_from_unified_storage(self) -> 'StorageConversation':
        """从统一存储加载
        
        从gpts_messages表加载消息到StorageConversation
        
        Returns:
            StorageConversation实例
        """
        try:
            conv_id = self.storage_conv.conv_uid
            
            unified_messages = await self._unified_dao.get_messages_by_conv_id(
                conv_id=conv_id
            )
            
            if not unified_messages:
                logger.debug(f"No messages found for conversation {conv_id}")
                return self.storage_conv
            
            from derisk.core.interface.message import BaseMessage
            
            self.storage_conv.messages = []
            
            for unified_msg in unified_messages:
                base_msg = unified_msg.to_base_message()
                
                if hasattr(unified_msg, 'rounds'):
                    base_msg.round_index = unified_msg.rounds
                
                self.storage_conv.messages.append(base_msg)
            
            if self.storage_conv.messages:
                self.storage_conv._message_index = len(self.storage_conv.messages)
                max_round = max(
                    getattr(m, 'round_index', 0) 
                    for m in self.storage_conv.messages
                )
                self.storage_conv.chat_order = max_round
            
            logger.info(
                f"Loaded {len(unified_messages)} messages from unified storage "
                f"for conversation {conv_id}"
            )
            
            return self.storage_conv
            
        except Exception as e:
            logger.error(
                f"Failed to load conversation {self.storage_conv.conv_uid} "
                f"from unified storage: {e}"
            )
            raise
    
    async def append_message_to_unified(
        self, 
        message: 'BaseMessage'
    ) -> None:
        """追加单条消息到统一存储
        
        Args:
            message: BaseMessage实例
        """
        try:
            conv_id = self.storage_conv.conv_uid
            
            unified_msg = UnifiedMessage.from_base_message(
                msg=message,
                conv_id=conv_id,
                conv_session_id=getattr(
                    self.storage_conv, 'session_id', conv_id
                ),
                sender=self._get_sender_from_message(message),
                sender_name=self.storage_conv.user_name,
                round_index=getattr(message, 'round_index', 0)
            )
            
            await self._unified_dao.save_message(unified_msg)
            logger.debug(f"Appended message to conversation {conv_id}")
            
        except Exception as e:
            logger.error(f"Failed to append message: {e}")
            raise
    
    async def delete_from_unified_storage(self) -> None:
        """从统一存储删除对话及其消息"""
        try:
            conv_id = self.storage_conv.conv_uid
            await self._unified_dao.delete_conversation(conv_id)
            logger.info(f"Deleted conversation {conv_id} from unified storage")
        except Exception as e:
            logger.error(
                f"Failed to delete conversation {self.storage_conv.conv_uid}: {e}"
            )
            raise
    
    def _get_sender_from_message(self, msg: 'BaseMessage') -> str:
        """从消息类型推断发送者
        
        Args:
            msg: BaseMessage实例
            
        Returns:
            发送者标识
        """
        msg_type = getattr(msg, 'type', 'human')
        
        type_to_sender = {
            "human": "user",
            "ai": getattr(self.storage_conv, 'agent_name', "assistant"),
            "system": "system",
            "view": "view"
        }
        
        return type_to_sender.get(msg_type, "assistant")


async def convert_storage_conv_to_unified(
    storage_conv: 'StorageConversation'
) -> None:
    """将StorageConversation转换为统一存储的便捷函数
    
    Args:
        storage_conv: StorageConversation实例
    """
    adapter = StorageConversationUnifiedAdapter(storage_conv)
    await adapter.save_to_unified_storage()


async def load_storage_conv_from_unified(
    storage_conv: 'StorageConversation'
) -> 'StorageConversation':
    """从统一存储加载StorageConversation的便捷函数
    
    Args:
        storage_conv: StorageConversation实例
        
    Returns:
        加载后的StorageConversation实例
    """
    adapter = StorageConversationUnifiedAdapter(storage_conv)
    return await adapter.load_from_unified_storage()