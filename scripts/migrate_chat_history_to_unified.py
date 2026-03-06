"""
数据迁移脚本：chat_history到统一存储

将chat_history表的数据迁移到gpts_messages表
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict

from tqdm import tqdm

from derisk.storage.chat_history.chat_history_db import ChatHistoryDao, ChatHistoryEntity
from derisk.storage.unified_message_dao import UnifiedMessageDAO
from derisk.core.interface.unified_message import UnifiedMessage

logger = logging.getLogger(__name__)


class DataMigration:
    """数据迁移类"""
    
    def __init__(self):
        self.chat_history_dao = ChatHistoryDao()
        self.unified_dao = UnifiedMessageDAO()
    
    async def migrate_chat_history(self, batch_size: int = 100) -> dict:
        """迁移chat_history数据到统一存储
        
        Args:
            batch_size: 批量处理大小
            
        Returns:
            迁移统计信息
        """
        print(f"[{datetime.now()}] 开始迁移 chat_history...")
        
        stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }
        
        try:
            total = await self._count_chat_history()
            stats["total"] = total
            
            print(f"总共需要迁移 {total} 个对话")
            
            offset = 0
            
            with tqdm(total=total, desc="迁移chat_history") as pbar:
                while offset < total:
                    batch = await self._list_chat_history_batch(
                        limit=batch_size,
                        offset=offset
                    )
                    
                    if not batch:
                        break
                    
                    for entity in batch:
                        try:
                            result = await self._migrate_single(entity)
                            
                            if result == "success":
                                stats["success"] += 1
                            elif result == "skipped":
                                stats["skipped"] += 1
                            else:
                                stats["failed"] += 1
                                stats["errors"].append({
                                    "conv_uid": entity.conv_uid,
                                    "error": result
                                })
                        except Exception as e:
                            stats["failed"] += 1
                            stats["errors"].append({
                                "conv_uid": entity.conv_uid,
                                "error": str(e)
                            })
                            logger.error(
                                f"迁移失败 conv_uid={entity.conv_uid}: {e}"
                            )
                        
                        pbar.update(1)
                    
                    offset += batch_size
            
            print(f"\n[{datetime.now()}] 迁移完成!")
            print(f"统计信息:")
            print(f"  总数: {stats['total']}")
            print(f"  成功: {stats['success']}")
            print(f"  跳过: {stats['skipped']}")
            print(f"  失败: {stats['failed']}")
            
            return stats
            
        except Exception as e:
            logger.error(f"迁移过程出错: {e}")
            raise
    
    async def _migrate_single(self, entity: ChatHistoryEntity) -> str:
        """迁移单个chat_history记录
        
        Args:
            entity: ChatHistoryEntity实例
            
        Returns:
            结果: "success", "skipped", 或错误消息
        """
        try:
            conv_id = entity.conv_uid
            
            existing = await self._check_conversation_exists(conv_id)
            
            if existing:
                logger.debug(f"对话 {conv_id} 已存在，跳过")
                return "skipped"
            
            await self._create_conversation_from_chat_history(entity)
            
            messages = self._parse_messages_from_chat_history(entity)
            
            if not messages:
                logger.debug(f"对话 {conv_id} 没有消息")
                return "success"
            
            unified_messages = []
            
            for msg_data in messages:
                for idx, msg_item in enumerate(msg_data.get("messages", [])):
                    unified_msg = self._convert_to_unified_message(
                        msg_item=msg_item,
                        conv_id=conv_id,
                        session_id=conv_id,
                        idx=idx
                    )
                    
                    if unified_msg:
                        unified_messages.append(unified_msg)
            
            if unified_messages:
                await self.unified_dao.save_messages_batch(unified_messages)
            
            logger.info(f"成功迁移对话 {conv_id}，包含 {len(unified_messages)} 条消息")
            return "success"
            
        except Exception as e:
            logger.error(f"迁移对话 {entity.conv_uid} 失败: {e}")
            return str(e)
    
    async def _check_conversation_exists(self, conv_id: str) -> bool:
        """检查对话是否已存在
        
        Args:
            conv_id: 对话ID
            
        Returns:
            是否存在
        """
        try:
            messages = await self.unified_dao.get_messages_by_conv_id(
                conv_id=conv_id,
                limit=1
            )
            
            return len(messages) > 0
        except:
            return False
    
    async def _create_conversation_from_chat_history(self, entity: ChatHistoryEntity):
        """从chat_history创建对话记录
        
        Args:
            entity: ChatHistoryEntity实例
        """
        await self.unified_dao.create_conversation(
            conv_id=entity.conv_uid,
            user_id=entity.user_name or "unknown",
            goal=entity.summary,
            chat_mode=entity.chat_mode or "chat_normal",
            session_id=entity.conv_uid
        )
    
    def _parse_messages_from_chat_history(self, entity: ChatHistoryEntity) -> List[Dict]:
        """从chat_history解析消息列表
        
        Args:
            entity: ChatHistoryEntity实例
            
        Returns:
            消息列表
        """
        if not entity.messages:
            return []
        
        try:
            messages = json.loads(entity.messages)
            return messages if isinstance(messages, list) else [messages]
        except Exception as e:
            logger.warning(f"解析消息失败 conv_uid={entity.conv_uid}: {e}")
            return []
    
    def _convert_to_unified_message(
        self,
        msg_item: Dict,
        conv_id: str,
        session_id: str,
        idx: int
    ) -> UnifiedMessage:
        """将chat_history消息转换为UnifiedMessage
        
        Args:
            msg_item: 消息项
            conv_id: 对话ID
            session_id: 会话ID
            idx: 消息索引
            
        Returns:
            UnifiedMessage实例
        """
        try:
            msg_type = msg_item.get("type", "human")
            msg_data = msg_item.get("data", {})
            content = msg_data.get("content", "")
            
            role_mapping = {
                "human": "human",
                "ai": "ai",
                "system": "system",
                "view": "view"
            }
            
            message_type = role_mapping.get(msg_type, "human")
            
            sender = "user"
            if msg_type == "ai":
                sender = "assistant"
            elif msg_type == "system":
                sender = "system"
            elif msg_type == "view":
                sender = "view"
            
            return UnifiedMessage(
                message_id=f"{conv_id}_msg_{idx}",
                conv_id=conv_id,
                conv_session_id=session_id,
                sender=sender,
                message_type=message_type,
                content=str(content),
                rounds=msg_item.get("round_index", 0),
                message_index=idx,
                metadata={
                    "source": "chat_history_migration",
                    "original_type": msg_type,
                    "migrated_at": datetime.now().isoformat()
                },
                created_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"转换消息失败: {e}")
            return None
    
    async def _count_chat_history(self) -> int:
        """统计chat_history记录数
        
        Returns:
            记录总数
        """
        try:
            with self.chat_history_dao.session(commit=False) as session:
                count = session.query(ChatHistoryEntity).count()
                return count
        except Exception as e:
            logger.error(f"统计失败: {e}")
            return 0
    
    async def _list_chat_history_batch(
        self,
        limit: int,
        offset: int
    ) -> List[ChatHistoryEntity]:
        """批量查询chat_history
        
        Args:
            limit: 数量限制
            offset: 偏移量
            
        Returns:
            ChatHistoryEntity列表
        """
        try:
            with self.chat_history_dao.session(commit=False) as session:
                entities = session.query(ChatHistoryEntity) \
                    .order_by(ChatHistoryEntity.gmt_create) \
                    .limit(limit) \
                    .offset(offset) \
                    .all()
                
                return entities
        except Exception as e:
            logger.error(f"查询失败: {e}")
            return []


async def main():
    """主函数"""
    migration = DataMigration()
    
    print("=" * 60)
    print("开始数据迁移: chat_history -> gpts_messages")
    print("=" * 60)
    
    stats = await migration.migrate_chat_history(batch_size=100)
    
    print("\n" + "=" * 60)
    print("数据迁移完成!")
    print("=" * 60)
    
    return stats


if __name__ == "__main__":
    result = asyncio.run(main())
    
    if result["failed"] > 0:
        print("\n失败的记录:")
        for error in result["errors"][:10]:  # 只显示前10个错误
            print(f"  conv_uid: {error['conv_uid']}, error: {error['error']}")
        
        if len(result["errors"]) > 10:
            print(f"  ... 还有 {len(result['errors']) - 10} 个错误未显示")