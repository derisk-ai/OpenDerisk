"""
统一消息DAO

底层使用gpts_messages表，提供统一的消息存储和查询接口
"""

import json
import logging
from typing import List, Optional
from datetime import datetime
import threading

from derisk.core.interface.unified_message import UnifiedMessage

logger = logging.getLogger(__name__)


class UnifiedMessageDAO:
    """统一消息DAO，底层使用gpts_messages表（单例模式）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        try:
            from derisk_serve.agent.db.gpts_messages_db import GptsMessagesDao
            from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

            self.msg_dao = GptsMessagesDao()
            self.conv_dao = GptsConversationsDao()
            self._initialized = True
        except ImportError as e:
            logger.error(f"Failed to import DAO dependencies: {e}")
            raise

    @classmethod
    def get_instance(cls) -> "UnifiedMessageDAO":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        with cls._lock:
            cls._instance = None

    async def save_message(self, message: UnifiedMessage) -> None:
        """保存消息（统一入口）

        Args:
            message: UnifiedMessage实例
        """
        from derisk_serve.agent.db.gpts_messages_db import GptsMessagesEntity

        try:
            tool_calls_json = (
                json.dumps(message.tool_calls, ensure_ascii=False)
                if message.tool_calls
                else None
            )
            context_json = (
                json.dumps(message.context, ensure_ascii=False)
                if message.context
                else None
            )
            action_report_json = (
                json.dumps(message.action_report, ensure_ascii=False)
                if message.action_report
                else None
            )
            resource_info_json = (
                json.dumps(message.resource_info, ensure_ascii=False)
                if message.resource_info
                else None
            )

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
                gmt_create=message.created_at or datetime.now(),
            )

            await self.msg_dao.update_message(entity)
            logger.debug(
                f"Saved message {message.message_id} to conversation {message.conv_id}"
            )

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
        order: str = "asc",
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

            logger.debug(
                f"Loaded {len(unified_messages)} messages for conversation {conv_id}"
            )
            return unified_messages

        except Exception as e:
            logger.error(f"Failed to get messages for conversation {conv_id}: {e}")
            raise

    async def get_messages_by_session(
        self, session_id: str, limit: int = 100
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

            logger.debug(
                f"Loaded {len(unified_messages)} messages for session {session_id}"
            )
            return unified_messages

        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            raise

    async def get_latest_messages(
        self, conv_id: str, limit: int = 10
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
        session_id: Optional[str] = None,
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
                gmt_create=datetime.now(),
            )

            await self.conv_dao.a_add(entity)
            logger.debug(f"Created conversation {conv_id} for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to create conversation {conv_id}: {e}")
            raise

    async def update_conversation_state(self, conv_id: str, state: str) -> None:
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
        action_report = (
            json.loads(entity.action_report) if entity.action_report else None
        )
        resource_info = (
            json.loads(entity.resource_info) if entity.resource_info else None
        )

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
            created_at=entity.gmt_create,
        )

    def _determine_message_type(
        self, sender: Optional[str], receiver: Optional[str]
    ) -> str:
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

    async def list_conversations(
        self,
        user_id: Optional[str] = None,
        sys_code: Optional[str] = None,
        filter_text: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """统一查询对话列表（Core V1 + Core V2）

        同时查询 chat_history 和 gpts_conversations 表，合并结果返回

        Args:
            user_id: 用户ID
            sys_code: 系统代码
            filter_text: 过滤关键字（搜索摘要/目标）
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            {
                "items": [UnifiedConversationSummary, ...],
                "total_count": int,
                "total_pages": int,
                "page": int,
                "page_size": int
            }
        """
        from derisk.core.interface.unified_message import UnifiedConversationSummary

        # 1. 查询 Core V1 (chat_history)
        v1_items = await self._list_conversations_v1(user_id, sys_code, filter_text)

        # 2. 查询 Core V2 (gpts_conversations)
        v2_items = await self._list_conversations_v2(user_id, sys_code, filter_text)

        # 3. 合并结果（去重：同一 conv_id 优先保留 v2 记录）
        seen_conv_ids = set()
        all_items = []
        # v2 优先
        for item in v2_items:
            if item.conv_id not in seen_conv_ids:
                seen_conv_ids.add(item.conv_id)
                all_items.append(item)
        for item in v1_items:
            if item.conv_id not in seen_conv_ids:
                seen_conv_ids.add(item.conv_id)
                all_items.append(item)

        # 4. 按时间倒序排序
        all_items.sort(
            key=lambda x: x.updated_at or x.created_at or datetime.min, reverse=True
        )

        # 5. 分页
        total_count = len(all_items)
        total_pages = (
            (total_count + page_size - 1) // page_size if total_count > 0 else 1
        )
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = all_items[start_idx:end_idx]

        return {
            "items": paginated_items,
            "total_count": total_count,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
        }

    async def _list_conversations_v1(
        self,
        user_id: Optional[str] = None,
        sys_code: Optional[str] = None,
        filter_text: Optional[str] = None,
    ) -> List:
        """查询 Core V1 (chat_history) 的对话列表

        Args:
            user_id: 用户ID
            sys_code: 系统代码
            filter_text: 过滤关键字

        Returns:
            UnifiedConversationSummary 列表
        """
        from derisk.core.interface.unified_message import UnifiedConversationSummary
        from derisk.storage.chat_history.chat_history_db import (
            ChatHistoryEntity,
            ChatHistoryDao,
        )

        try:
            dao = ChatHistoryDao()
            session = dao.get_raw_session()
            try:
                query = session.query(ChatHistoryEntity)

                if user_id:
                    query = query.filter(ChatHistoryEntity.user_name == user_id)
                if sys_code:
                    query = query.filter(ChatHistoryEntity.sys_code == sys_code)
                if filter_text:
                    query = query.filter(
                        ChatHistoryEntity.summary.like(f"%{filter_text}%")
                    )

                # 按时间倒序
                query = query.order_by(ChatHistoryEntity.id.desc())

                entities = query.all()

                result = []
                for entity in entities:
                    result.append(
                        UnifiedConversationSummary(
                            conv_id=entity.conv_uid,
                            user_id=entity.user_name or "",
                            goal=entity.summary,
                            chat_mode=entity.chat_mode or "chat_normal",
                            state="complete",
                            app_code=entity.app_code,
                            created_at=entity.gmt_created,
                            updated_at=entity.gmt_modified,
                            source="v1",
                        )
                    )

                logger.debug(f"Loaded {len(result)} conversations from chat_history")
                return result

            finally:
                session.close()

        except Exception as e:
            logger.warning(f"Failed to query chat_history: {e}")
            return []

    async def _list_conversations_v2(
        self,
        user_id: Optional[str] = None,
        sys_code: Optional[str] = None,
        filter_text: Optional[str] = None,
    ) -> List:
        """查询 Core V2 (gpts_conversations) 的对话列表

        Args:
            user_id: 用户ID
            sys_code: 系统代码
            filter_text: 过滤关键字

        Returns:
            UnifiedConversationSummary 列表
        """
        from derisk.core.interface.unified_message import UnifiedConversationSummary

        try:
            session = self.conv_dao.get_raw_session()
            try:
                from derisk_serve.agent.db.gpts_conversations_db import (
                    GptsConversationsEntity,
                )

                query = session.query(GptsConversationsEntity)

                if user_id:
                    query = query.filter(GptsConversationsEntity.user_code == user_id)
                if sys_code:
                    query = query.filter(GptsConversationsEntity.sys_code == sys_code)
                if filter_text:
                    query = query.filter(
                        GptsConversationsEntity.user_goal.like(f"%{filter_text}%")
                    )

                # 按时间倒序
                query = query.order_by(GptsConversationsEntity.id.desc())

                entities = query.all()

                result = []
                for entity in entities:
                    result.append(
                        UnifiedConversationSummary(
                            conv_id=entity.conv_id,
                            user_id=entity.user_code or "",
                            conv_session_id=entity.conv_session_id,
                            goal=entity.user_goal,
                            chat_mode=entity.team_mode or "gpts_v2",
                            state=entity.state or "active",
                            app_code=entity.gpts_name,
                            created_at=entity.created_at,
                            updated_at=entity.updated_at,
                            source="v2",
                        )
                    )

                logger.debug(
                    f"Loaded {len(result)} conversations from gpts_conversations"
                )
                return result

            finally:
                session.close()

        except Exception as e:
            logger.warning(f"Failed to query gpts_conversations: {e}")
            return []
