"""
统一消息DAO

底层使用gpts_messages表，提供统一的消息存储和查询接口
"""
import json
import logging
from typing import List, Optional
from datetime import datetime

from derisk.core.interface.unified_message import UnifiedMessage

logger = logging.getLogger(__name__)


class UnifiedMessageDAO:
    """统一消息DAO，底层使用gpts_messages表"""
    
    def __init__(self):
        try:
            from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
            from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao
            
            self.msg_dao = GptsMessagesDao()
            self.conv_dao = GptsConversationsDao()
        except ImportError as e:
            logger.error(f"Failed to import DAO dependencies: {e}")
            raise
    
    async def save_message(self, message: UnifiedMessage) -> None:
        """保存消息（统一入口）
        
        Args:
            message: UnifiedMessage实例
        """
        from derisk_serve.agent.db.gpts_messages_db import GptsMessagesEntity
        
        try:
            tool_calls_json = json.dumps(message.tool_calls, ensure_ascii=False) if message.tool_calls else None
            context_json = json.dumps(message.context, ensure_ascii=False) if message.context else None
            action_report_json = json.dumps(message.action_report, ensure_ascii=False) if message.action_report else None
            resource_info_json = json.dumps(message.resource_info, ensure_ascii=False) if message.resource_info else None
            
            entity = GptsMessagesEntity(
                conv_id=message.conv_id,
                conv_session_id=message.conv_session_id,
                message_id=message.message_id,
                sender=message.sender,
                sender_name=message.sender_name,
                receiver=message.receiver,
                receiver_name=message.receiver_name,
                rounds=message.rounds,
                content=message.content,
                thinking=message.thinking,
                tool_calls=tool_calls_json,
                observation=message.observation,
                context=context_json,
                action_report=action_report_json,
                resource_info=resource_info_json,
                gmt_create=message.created_at or datetime.now()
            )
            
            await self.msg_dao.update_message(entity)
            logger.debug(f"Saved message {message.message_id} to conversation {message.conv_id}")
            
        except Exception as e:
            logger.error(f"Failed to save message {message.message_id}: {e}")
            raise
    
    async def save_messages_batch(self, messages: List[UnifiedMessage]) -> None:
        """批量保存消息
        
        Args:
            messages: UnifiedMessage列表
        """
        for msg in messages:
            await self.save_message(msg)
    
    async def get_messages_by_conv_id(
        self, 
        conv_id: str,
        limit: Optional[int] = None,
        include_thinking: bool = False,
        order: str = "asc"
    ) -> List[UnifiedMessage]:
        """获取对话的所有消息
        
        Args:
            conv_id: 对话ID
            limit: 返回消息数量限制
            include_thinking: 是否包含思考过程
            order: 排序方式（asc/desc）
            
        Returns:
            UnifiedMessage列表
        """
        try:
            gpts_messages = await self.msg_dao.get_by_conv_id(conv_id)
            
            unified_messages = []
            for gpt_msg in gpts_messages:
                unified_msg = self._entity_to_unified(gpt_msg)
                
                if not include_thinking and unified_msg.thinking:
                    unified_msg.thinking = None
                
                unified_messages.append(unified_msg)
            
            if order == "desc":
                unified_messages = unified_messages[::-1]
            
            if limit and limit > 0:
                unified_messages = unified_messages[:limit]
            
            logger.debug(f"Loaded {len(unified_messages)} messages for conversation {conv_id}")
            return unified_messages
            
        except Exception as e:
            logger.error(f"Failed to get messages for conversation {conv_id}: {e}")
            raise
    
    async def get_messages_by_session(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[UnifiedMessage]:
        """获取会话下的所有消息
        
        Args:
            session_id: 会话ID
            limit: 返回消息数量限制
            
        Returns:
            UnifiedMessage列表
        """
        try:
            gpts_messages = await self.msg_dao.get_by_session_id(session_id)
            
            unified_messages = []
            for gpt_msg in gpts_messages[:limit]:
                unified_msg = self._entity_to_unified(gpt_msg)
                unified_messages.append(unified_msg)
            
            logger.debug(f"Loaded {len(unified_messages)} messages for session {session_id}")
            return unified_messages
            
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            raise
    
    async def get_latest_messages(
        self,
        conv_id: str,
        limit: int = 10
    ) -> List[UnifiedMessage]:
        """获取最新的N条消息
        
        Args:
            conv_id: 对话ID
            limit: 返回消息数量
            
        Returns:
            UnifiedMessage列表
        """
        all_messages = await self.get_messages_by_conv_id(conv_id)
        return all_messages[-limit:] if len(all_messages) > limit else all_messages
    
    async def create_conversation(
        self,
        conv_id: str,
        user_id: str,
        goal: Optional[str] = None,
        chat_mode: str = "chat_normal",
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """创建对话记录
        
        Args:
            conv_id: 对话ID
            user_id: 用户ID
            goal: 对话目标
            chat_mode: 对话模式
            agent_name: Agent名称
            session_id: 会话ID
        """
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsEntity
        
        try:
            entity = GptsConversationsEntity(
                conv_id=conv_id,
                conv_session_id=session_id or conv_id,
                user_goal=goal,
                user_code=user_id,
                gpts_name=agent_name or "assistant",
                state="active",
                gmt_create=datetime.now()
            )
            
            await self.conv_dao.a_add(entity)
            logger.debug(f"Created conversation {conv_id} for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to create conversation {conv_id}: {e}")
            raise
    
    async def update_conversation_state(
        self,
        conv_id: str,
        state: str
    ) -> None:
        """更新对话状态
        
        Args:
            conv_id: 对话ID
            state: 状态
        """
        try:
            await self.conv_dao.update(conv_id, state=state)
            logger.debug(f"Updated conversation {conv_id} state to {state}")
        except Exception as e:
            logger.error(f"Failed to update conversation {conv_id} state: {e}")
            raise
    
    async def delete_conversation(self, conv_id: str) -> None:
        """删除对话及其消息
        
        Args:
            conv_id: 对话ID
        """
        try:
            await self.conv_dao.delete_chat_message(conv_id)
            logger.debug(f"Deleted conversation {conv_id}")
        except Exception as e:
            logger.error(f"Failed to delete conversation {conv_id}: {e}")
            raise
    
    def _entity_to_unified(self, entity) -> UnifiedMessage:
        """将数据库实体转换为UnifiedMessage
        
        Args:
            entity: GptsMessagesEntity实例
            
        Returns:
            UnifiedMessage实例
        """
        tool_calls = json.loads(entity.tool_calls) if entity.tool_calls else None
        context = json.loads(entity.context) if entity.context else None
        action_report = json.loads(entity.action_report) if entity.action_report else None
        resource_info = json.loads(entity.resource_info) if entity.resource_info else None
        
        message_type = self._determine_message_type(entity.sender, entity.receiver)
        
        return UnifiedMessage(
            message_id=entity.message_id or "",
            conv_id=entity.conv_id,
            conv_session_id=entity.conv_session_id,
            sender=entity.sender or "user",
            sender_name=entity.sender_name,
            receiver=entity.receiver,
            receiver_name=entity.receiver_name,
            message_type=message_type,
            content=entity.content or "",
            thinking=entity.thinking,
            tool_calls=tool_calls,
            observation=entity.observation,
            context=context,
            action_report=action_report,
            resource_info=resource_info,
            rounds=entity.rounds or 0,
            message_index=entity.rounds or 0,
            created_at=entity.gmt_create
        )
    
    def _determine_message_type(self, sender: Optional[str], receiver: Optional[str]) -> str:
        """根据sender和receiver判断消息类型
        
        Args:
            sender: 发送者
            receiver: 接收者
            
        Returns:
            消息类型
        """
        if not sender:
            return "system"
        
        if sender == "user" or sender.lower() in ["human", "user"]:
            return "human"
        
        if sender == "system":
            return "system"
        
        if "::" in sender:
            return "agent"
        
        return "ai"