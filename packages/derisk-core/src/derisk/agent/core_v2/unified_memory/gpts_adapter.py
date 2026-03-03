"""
GptsMemoryAdapter - 适配 GptsMemory 到 UnifiedMemoryInterface

这个适配器让 GptsMemory 实现 UnifiedMemoryInterface 接口，
作为 Core V2 统一记忆系统的后端存储。

架构设计:
┌─────────────────────────────────────────────────────────────┐
│  AgentBase (V2)          ConversableAgent (V1)              │
│       │                        │                            │
│       v                        v                            │
│  UnifiedMemoryInterface  AgentMemory                        │
│       │                        │                            │
│       └────────────┬───────────┘                            │
│                    v                                        │
│           GptsMemoryAdapter                                 │
│           (实现 UnifiedMemoryInterface)                      │
│                    │                                        │
│                    v                                        │
│              GptsMemory                                     │
│         (底层存储 + 数据库持久化)                             │
│                    │                                        │
│     ┌──────────────┼──────────────┐                        │
│     v              v              v                         │
│ gpts_messages  chat_history  work_log                      │
└─────────────────────────────────────────────────────────────┘
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import (
    MemoryItem,
    MemoryType,
    SearchOptions,
    UnifiedMemoryInterface,
    MemoryConsolidationResult,
)

logger = logging.getLogger(__name__)


class GptsMemoryAdapter(UnifiedMemoryInterface):
    """
    GptsMemory 适配器 - 实现 UnifiedMemoryInterface

    将 GptsMemory 适配为统一记忆接口，使 Core V2 的 Agent
    能够使用 GptsMemory 的持久化存储能力。

    功能映射:
    - write() -> append_message() / append_work_entry()
    - read() -> get_messages() / get_work_log()
    - search_similar() -> 内存中过滤
    - consolidate() -> memory_compaction

    示例:
        from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
        from derisk.agent.core_v2.unified_memory.gpts_adapter import GptsMemoryAdapter

        gpts_memory = GptsMemory()
        adapter = GptsMemoryAdapter(gpts_memory, conv_id="conv_123")

        # 写入记忆
        memory_id = await adapter.write("用户查询天气", MemoryType.WORKING)

        # 读取记忆
        items = await adapter.read("天气")
    """

    def __init__(
        self,
        gpts_memory: Any,
        conv_id: str,
        session_id: Optional[str] = None,
    ):
        """
        初始化 GptsMemory 适配器

        Args:
            gpts_memory: GptsMemory 实例
            conv_id: 会话 ID
            session_id: 可选的会话 ID (用于区分同一 conv_id 下的不同 session)
        """
        self._gpts_memory = gpts_memory
        self._conv_id = conv_id
        self._session_id = session_id or conv_id
        self._memory_items: Dict[str, MemoryItem] = {}
        self._initialized = False

    @property
    def session_id(self) -> str:
        """获取会话 ID"""
        return self._session_id

    @property
    def conv_id(self) -> str:
        """获取对话 ID"""
        return self._conv_id

    @property
    def gpts_memory(self) -> Any:
        """获取底层 GptsMemory 实例"""
        return self._gpts_memory

    async def initialize(self) -> None:
        """初始化适配器，从 GptsMemory 加载已有消息"""
        if self._initialized:
            return

        try:
            # 加载已有消息到内存缓存
            messages = await self._gpts_memory.get_messages(self._conv_id)
            for msg in messages:
                memory_id = msg.message_id or str(uuid.uuid4())
                content = self._extract_message_content(msg)

                self._memory_items[memory_id] = MemoryItem(
                    id=memory_id,
                    content=content,
                    memory_type=MemoryType.EPISODIC,  # 历史消息作为情景记忆
                    metadata={
                        "sender": getattr(msg, 'sender', None),
                        "receiver": getattr(msg, 'receiver', None),
                        "role": getattr(msg, 'role', None),
                        "rounds": getattr(msg, 'rounds', 0),
                        "created_at": str(getattr(msg, 'created_at', datetime.now())),
                    },
                    created_at=getattr(msg, 'created_at', datetime.now()),
                )

            self._initialized = True
            logger.info(
                f"[GptsMemoryAdapter] 初始化完成: conv_id={self._conv_id[:8]}, "
                f"messages={len(messages)}"
            )
        except Exception as e:
            logger.error(f"[GptsMemoryAdapter] 初始化失败: {e}")
            self._initialized = True  # 即使失败也标记为已初始化

    def _extract_message_content(self, message: Any) -> str:
        """从消息对象提取内容字符串"""
        if hasattr(message, 'content'):
            content = message.content
            if isinstance(content, str):
                return content
            elif isinstance(content, dict):
                return content.get('text', str(content))
            return str(content)
        return str(message)

    async def write(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_file: bool = True,
    ) -> str:
        """
        写入记忆项

        Args:
            content: 记忆内容
            memory_type: 记忆类型
            metadata: 元数据
            sync_to_file: 是否同步到文件 (对于 GptsMemory 即是否持久化到数据库)

        Returns:
            记忆项 ID
        """
        await self.initialize()

        memory_id = str(uuid.uuid4())
        now = datetime.now()

        # 创建 MemoryItem
        item = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            created_at=now,
            last_accessed=now,
        )

        # 存储到内存缓存
        self._memory_items[memory_id] = item

        # 根据记忆类型决定是否写入 GptsMemory
        if memory_type in (MemoryType.WORKING, MemoryType.EPISODIC):
            await self._write_to_gpts_memory(content, memory_type, metadata, memory_id, sync_to_file)

        logger.debug(
            f"[GptsMemoryAdapter] 写入记忆: id={memory_id[:8]}, type={memory_type.value}"
        )

        return memory_id

    async def _write_to_gpts_memory(
        self,
        content: str,
        memory_type: MemoryType,
        metadata: Optional[Dict[str, Any]],
        memory_id: str,
        save_db: bool,
    ) -> None:
        """将内容写入 GptsMemory"""
        from derisk.agent.core.memory.gpts.base import GptsMessage

        # 创建一个类似 GptsMessage 的对象
        message_dict = {
            "message_id": memory_id,
            "conv_id": self._conv_id,
            "conv_session_id": self._session_id,
            "sender": metadata.get("sender", "agent") if metadata else "agent",
            "sender_name": metadata.get("sender_name", "Agent") if metadata else "Agent",
            "receiver": metadata.get("receiver", "user") if metadata else "user",
            "receiver_name": metadata.get("receiver_name", "User") if metadata else "User",
            "role": metadata.get("role", "assistant") if metadata else "assistant",
            "content": content,
            "rounds": metadata.get("rounds", 0) if metadata else 0,
            "is_success": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        # 使用动态创建的对象
        class MessageProxy:
            pass

        msg = MessageProxy()
        for key, value in message_dict.items():
            setattr(msg, key, value)

        try:
            await self._gpts_memory.append_message(
                self._conv_id, msg, save_db=save_db
            )
        except Exception as e:
            logger.warning(f"[GptsMemoryAdapter] 写入 GptsMemory 失败: {e}")

    async def read(
        self,
        query: str,
        options: Optional[SearchOptions] = None,
    ) -> List[MemoryItem]:
        """
        读取匹配的记忆项

        Args:
            query: 查询字符串
            options: 搜索选项

        Returns:
            匹配的记忆项列表
        """
        await self.initialize()

        options = options or SearchOptions()
        results = []

        for item in self._memory_items.values():
            # 过滤记忆类型
            if options.memory_types and item.memory_type not in options.memory_types:
                continue

            # 过滤重要性
            if item.importance < options.min_importance:
                continue

            # 过滤时间范围
            if options.time_range:
                start, end = options.time_range
                if item.created_at < start or item.created_at > end:
                    continue

            # 过滤来源
            if options.sources and item.source not in options.sources:
                continue

            # 文本匹配
            if query and query.lower() not in item.content.lower():
                continue

            # 更新访问信息
            item.update_access()
            results.append(item)

        # 按重要性排序
        results.sort(key=lambda x: x.importance, reverse=True)

        return results[:options.top_k]

    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        """
        相似性搜索 (简化实现 - 基于关键词匹配)

        注意: 完整的向量相似性搜索需要集成向量存储

        Args:
            query: 查询字符串
            top_k: 返回数量
            filters: 过滤条件

        Returns:
            相似的记忆项列表
        """
        await self.initialize()

        # TODO: 集成向量存储进行真正的相似性搜索
        # 目前使用简单的关键词匹配
        options = SearchOptions(top_k=top_k)

        if filters:
            if "memory_types" in filters:
                options.memory_types = filters["memory_types"]
            if "min_importance" in filters:
                options.min_importance = filters["min_importance"]

        return await self.read(query, options)

    async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """
        根据 ID 获取记忆项

        Args:
            memory_id: 记忆项 ID

        Returns:
            记忆项或 None
        """
        await self.initialize()

        item = self._memory_items.get(memory_id)
        if item:
            item.update_access()
        return item

    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        更新记忆项

        Args:
            memory_id: 记忆项 ID
            content: 新内容
            metadata: 新元数据

        Returns:
            是否成功更新
        """
        await self.initialize()

        if memory_id not in self._memory_items:
            return False

        item = self._memory_items[memory_id]

        if content:
            item.content = content
        if metadata:
            item.metadata.update(metadata)

        item.last_accessed = datetime.now()

        return True

    async def delete(self, memory_id: str) -> bool:
        """
        删除记忆项

        Args:
            memory_id: 记忆项 ID

        Returns:
            是否成功删除
        """
        await self.initialize()

        if memory_id not in self._memory_items:
            return False

        del self._memory_items[memory_id]
        return True

    async def consolidate(
        self,
        source_type: MemoryType,
        target_type: MemoryType,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> MemoryConsolidationResult:
        """
        压缩/合并记忆

        将工作记忆转换为长期记忆，或从情景记忆中提取语义知识

        Args:
            source_type: 源记忆类型
            target_type: 目标记忆类型
            criteria: 合并条件

        Returns:
            合并结果
        """
        await self.initialize()

        criteria = criteria or {}
        min_importance = criteria.get("min_importance", 0.5)
        min_access_count = criteria.get("min_access_count", 1)

        items_to_consolidate = []
        items_to_discard = []

        for item in self._memory_items.values():
            if item.memory_type != source_type:
                continue

            if item.importance >= min_importance and item.access_count >= min_access_count:
                items_to_consolidate.append(item)
            else:
                items_to_discard.append(item)

        # 更新记忆类型
        for item in items_to_consolidate:
            item.memory_type = target_type

        # 删除不重要的记忆
        for item in items_to_discard:
            del self._memory_items[item.id]

        tokens_saved = sum(len(i.content) // 4 for i in items_to_discard)

        logger.info(
            f"[GptsMemoryAdapter] 记忆合并: {source_type.value} -> {target_type.value}, "
            f"consolidated={len(items_to_consolidate)}, discarded={len(items_to_discard)}"
        )

        return MemoryConsolidationResult(
            success=True,
            source_type=source_type,
            target_type=target_type,
            items_consolidated=len(items_to_consolidate),
            items_discarded=len(items_to_discard),
            tokens_saved=tokens_saved,
        )

    async def export(
        self,
        format: str = "markdown",
        memory_types: Optional[List[MemoryType]] = None,
    ) -> str:
        """
        导出记忆

        Args:
            format: 导出格式 (markdown, json)
            memory_types: 要导出的记忆类型

        Returns:
            导出的内容字符串
        """
        await self.initialize()

        items = list(self._memory_items.values())

        if memory_types:
            items = [i for i in items if i.memory_type in memory_types]

        if format == "json":
            import json
            return json.dumps(
                [i.to_dict() for i in items],
                indent=2,
                ensure_ascii=False
            )

        # Markdown 格式
        content = f"# Memory Export - {self._conv_id}\n\n"
        for item in items:
            content += f"## [{item.memory_type.value}] {item.id[:8]}\n"
            content += f"{item.content}\n\n"
            if item.metadata:
                content += f"**Metadata**: {item.metadata}\n\n"
            content += "---\n\n"

        return content

    async def import_from_file(
        self,
        file_path: str,
        memory_type: MemoryType = MemoryType.SHARED,
    ) -> int:
        """
        从文件导入记忆

        Args:
            file_path: 文件路径
            memory_type: 记忆类型

        Returns:
            导入的数量
        """
        await self.initialize()

        try:
            import json

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 尝试解析为 JSON
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    count = 0
                    for item_dict in data:
                        item = MemoryItem.from_dict(item_dict)
                        item.memory_type = memory_type
                        self._memory_items[item.id] = item
                        count += 1
                    return count
            except json.JSONDecodeError:
                pass

            # 作为普通文本导入
            await self.write(content, memory_type)
            return 1

        except Exception as e:
            logger.error(f"[GptsMemoryAdapter] 导入失败: {e}")
            return 0

    async def clear(
        self,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> int:
        """
        清除记忆

        Args:
            memory_types: 要清除的记忆类型 (None 表示全部)

        Returns:
            清除的数量
        """
        await self.initialize()

        if not memory_types:
            count = len(self._memory_items)
            self._memory_items.clear()
            return count

        ids_to_remove = [
            id for id, item in self._memory_items.items()
            if item.memory_type in memory_types
        ]

        for id in ids_to_remove:
            del self._memory_items[id]

        return len(ids_to_remove)

    # ============== 扩展方法 ==============

    async def get_messages(self) -> List[Any]:
        """
        获取会话的所有消息 (直接从 GptsMemory 获取)

        Returns:
            消息列表
        """
        try:
            return await self._gpts_memory.get_messages(self._conv_id)
        except Exception as e:
            logger.error(f"[GptsMemoryAdapter] 获取消息失败: {e}")
            return []

    async def append_message(self, message: Any, save_db: bool = True) -> None:
        """
        追加消息到会话 (直接操作 GptsMemory)

        Args:
            message: 消息对象
            save_db: 是否保存到数据库
        """
        try:
            await self._gpts_memory.append_message(
                self._conv_id, message, save_db=save_db
            )
        except Exception as e:
            logger.error(f"[GptsMemoryAdapter] 追加消息失败: {e}")

    async def get_work_log(self) -> List[Any]:
        """
        获取工作日志

        Returns:
            工作日志列表
        """
        try:
            return await self._gpts_memory.get_work_log(self._conv_id)
        except Exception as e:
            logger.error(f"[GptsMemoryAdapter] 获取工作日志失败: {e}")
            return []

    async def append_work_entry(self, entry: Any, save_db: bool = True) -> None:
        """
        追加工作日志条目

        Args:
            entry: 工作日志条目
            save_db: 是否保存到数据库
        """
        try:
            await self._gpts_memory.append_work_entry(
                self._conv_id, entry, save_db=save_db
            )
        except Exception as e:
            logger.error(f"[GptsMemoryAdapter] 追加工作日志失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "conv_id": self._conv_id,
            "session_id": self._session_id,
            "total_items": len(self._memory_items),
            "initialized": self._initialized,
            "by_type": {
                mt.value: len([i for i in self._memory_items.values() if i.memory_type == mt])
                for mt in MemoryType
            },
        }