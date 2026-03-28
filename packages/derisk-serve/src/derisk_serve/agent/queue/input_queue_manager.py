"""Input Queue Manager for distributed message handling.

This module provides a queue manager that coordinates between in-memory cache
and database persistence for user inputs during agent execution.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable, Awaitable, Union

from derisk_serve.agent.db.agent_input_queue_db import (
    AgentInputQueueDao,
    AgentInputQueueEntity,
)

logger = logging.getLogger(__name__)


@dataclass
class QueuedInput:
    """队列中的输入项"""

    item_id: int
    message_id: str
    message_content: str  # JSON string of AgentMessage
    sender_name: str
    sender_type: str
    priority: int
    extra: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def get_message_dict(self) -> Dict[str, Any]:
        """获取消息字典"""
        try:
            return json.loads(self.message_content)
        except json.JSONDecodeError:
            return {"content": self.message_content}


class InputQueueManager:
    """分布式输入队列管理器

    管理用户在 Agent 执行过程中追加的输入消息。

    特性：
    1. 数据库持久化 - 支持分布式场景，任意服务实例可写入
    2. 内存缓存 - 提高性能，减少数据库查询
    3. 优先级排序 - 支持高优先级消息插队
    4. 消费者追踪 - 记录哪个实例消费了消息
    """

    def __init__(
        self,
        dao: Optional[AgentInputQueueDao] = None,
        poll_interval: float = 0.5,
    ):
        """初始化输入队列管理器

        Args:
            dao: 数据库访问对象，如果为 None 则延迟初始化
            poll_interval: 后台轮询间隔（秒）
        """
        self._dao = dao
        self._poll_interval = poll_interval

        # 内存缓存: conv_id -> List[QueuedInput]
        self._memory_cache: Dict[str, List[QueuedInput]] = {}

        # 服务器实例ID（用于追踪消费者）
        self._instance_id = (
            f"{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%H%M%S')}"
        )

        # 后台轮询任务
        self._poll_tasks: Dict[str, asyncio.Task] = {}

        # 是否启用后台轮询
        self._polling_enabled = False

    @property
    def instance_id(self) -> str:
        """获取当前实例ID"""
        return self._instance_id

    def _get_dao(self) -> AgentInputQueueDao:
        """获取 DAO 实例"""
        if self._dao is None:
            self._dao = AgentInputQueueDao()
        return self._dao

    async def submit_input(
        self,
        conv_id: str,
        conv_session_id: str,
        message_content: str,
        message_id: Optional[str] = None,
        sender_name: str = "user",
        sender_type: str = "user",
        priority: int = 0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """提交新输入到队列

        Args:
            conv_id: 对话ID (agent_conv_id)
            conv_session_id: 会话ID
            message_content: 消息内容 (JSON string 或纯文本)
            message_id: 消息ID（可选，自动生成）
            sender_name: 发送者名称
            sender_type: 发送者类型 (user/system)
            priority: 优先级（数字越大越优先）
            extra: 额外信息

        Returns:
            消息ID
        """
        message_id = message_id or uuid.uuid4().hex

        # 持久化到数据库
        entity = AgentInputQueueEntity(
            conv_id=conv_id,
            conv_session_id=conv_session_id,
            message_id=message_id,
            message_content=message_content,
            sender_name=sender_name,
            sender_type=sender_type,
            status="pending",
            priority=priority,
            extra=json.dumps(extra) if extra else None,
        )

        dao = self._get_dao()
        item_id = await dao.insert(entity)

        # 同时加入内存缓存
        queued_input = QueuedInput(
            item_id=item_id,
            message_id=message_id,
            message_content=message_content,
            sender_name=sender_name,
            sender_type=sender_type,
            priority=priority,
            extra=extra or {},
            created_at=datetime.now(),
        )

        if conv_id not in self._memory_cache:
            self._memory_cache[conv_id] = []
        self._memory_cache[conv_id].append(queued_input)

        logger.info(
            f"[InputQueue] Submitted input: conv_id={conv_id}, "
            f"message_id={message_id}, priority={priority}, instance={self._instance_id}"
        )

        return message_id

    async def drain_pending_inputs(
        self,
        conv_id: str,
        conv_session_id: Optional[str] = None,
        mark_consumed: bool = True,
        limit: int = 10,
    ) -> List[QueuedInput]:
        """获取并消费所有待处理输入

        这是 Agent 在 thinking 前调用的核心方法。

        Args:
            conv_id: 对话ID (agent_conv_id, 如 "session_1")
            conv_session_id: 会话ID (如 "session")，用于匹配前端提交的输入
            mark_consumed: 是否标记为已消费
            limit: 最大返回数量

        Returns:
            待处理的输入列表（按优先级降序排序）
        """
        dao = self._get_dao()

        # 1. 获取内存缓存
        cached = list(self._memory_cache.get(conv_id, []))
        if conv_session_id and conv_session_id != conv_id:
            session_cached = self._memory_cache.get(conv_session_id, [])
            seen_ids = {i.message_id for i in cached}
            for item in session_cached:
                if item.message_id not in seen_ids:
                    cached.append(item)

        # 2. 获取数据库待处理项
        db_items = []
        try:
            items_by_conv = await dao.get_pending_by_conv(conv_id, limit=limit * 2)
            db_items.extend(items_by_conv)

            if conv_session_id and conv_session_id != conv_id:
                items_by_session = await dao.get_pending_by_session(
                    conv_session_id, limit=limit * 2
                )
                seen_db_ids = {i.id for i in db_items}
                for item in items_by_session:
                    if item.id not in seen_db_ids:
                        db_items.append(item)
        except Exception as e:
            logger.error(f"[InputQueue] Failed to get pending inputs from DB: {e}")

        # 3. 合并去重
        cached_ids = {i.message_id for i in cached}
        all_inputs = list(cached)

        for item in db_items:
            if item.message_id not in cached_ids:
                queued_input = QueuedInput(
                    item_id=item.id,
                    message_id=item.message_id,
                    message_content=item.message_content,
                    sender_name=item.sender_name or "user",
                    sender_type=item.sender_type or "user",
                    priority=item.priority or 0,
                    extra=json.loads(item.extra) if item.extra else {},
                    created_at=item.gmt_create,
                )
                all_inputs.append(queued_input)
                cached_ids.add(item.message_id)

        # 4. 按优先级排序，取前 limit 个
        all_inputs.sort(key=lambda x: x.priority, reverse=True)
        result_inputs = all_inputs[:limit]

        # 5. 标记为已消费
        if mark_consumed and result_inputs:
            item_ids = [i.item_id for i in result_inputs]
            try:
                await dao.mark_consumed(item_ids, self._instance_id)
                logger.info(
                    f"[InputQueue] Marked {len(item_ids)} inputs as consumed in DB"
                )
            except Exception as e:
                logger.error(f"[InputQueue] Failed to mark inputs as consumed: {e}")

            # 更新内存缓存，移除已消费的项
            consumed_ids = {i.message_id for i in result_inputs}
            for cache_key in [conv_id, conv_session_id]:
                if cache_key and cache_key in self._memory_cache:
                    self._memory_cache[cache_key] = [
                        i
                        for i in self._memory_cache[cache_key]
                        if i.message_id not in consumed_ids
                    ]
                    if not self._memory_cache[cache_key]:
                        del self._memory_cache[cache_key]

        if result_inputs:
            logger.info(
                f"[InputQueue] Drained {len(result_inputs)} inputs for conv_id={conv_id}, "
                f"conv_session_id={conv_session_id}, instance={self._instance_id}"
            )

        return result_inputs

    async def has_pending_inputs(
        self, conv_id: str, conv_session_id: Optional[str] = None
    ) -> bool:
        """检查是否有待处理输入

        快速检查方法，用于 while 条件判断。

        Args:
            conv_id: 对话ID
            conv_session_id: 会话ID，用于匹配前端提交的输入

        Returns:
            是否有待处理输入
        """
        if self._memory_cache.get(conv_id):
            return True
        if conv_session_id and self._memory_cache.get(conv_session_id):
            return True

        try:
            dao = self._get_dao()
            if await dao.count_pending(conv_id) > 0:
                return True
            if (
                conv_session_id
                and await dao.count_pending_by_session(conv_session_id) > 0
            ):
                return True
            return False
        except Exception as e:
            logger.error(f"[InputQueue] Failed to check pending inputs: {e}")
            return False

    async def get_pending_count(
        self, conv_id: str, conv_session_id: Optional[str] = None
    ) -> int:
        """获取待处理输入数量

        Args:
            conv_id: 对话ID
            conv_session_id: 会话ID，用于匹配前端提交的输入

        Returns:
            待处理输入数量
        """
        memory_items = list(self._memory_cache.get(conv_id, []))
        if conv_session_id:
            session_items = self._memory_cache.get(conv_session_id, [])
            seen_ids = {i.message_id for i in memory_items}
            for item in session_items:
                if item.message_id not in seen_ids:
                    memory_items.append(item)
        memory_count = len(memory_items)

        try:
            dao = self._get_dao()
            db_count = await dao.count_pending(conv_id)
            if conv_session_id:
                session_count = await dao.count_pending_by_session(conv_session_id)
                db_count = max(db_count, session_count)
            if memory_count > 0:
                return max(memory_count, db_count)
            return db_count
        except Exception as e:
            logger.error(f"[InputQueue] Failed to count pending inputs: {e}")
            return memory_count

    async def clear_inputs(
        self, conv_id: str, conv_session_id: Optional[str] = None
    ) -> None:
        """清空指定对话的所有输入

        Args:
            conv_id: 对话ID
            conv_session_id: 会话ID
        """
        self._memory_cache.pop(conv_id, None)
        if conv_session_id:
            self._memory_cache.pop(conv_session_id, None)

        try:
            dao = self._get_dao()
            await dao.clear_by_conv(conv_id)
            if conv_session_id and conv_session_id != conv_id:
                await dao.clear_by_session(conv_session_id)
            logger.info(
                f"[InputQueue] Cleared all inputs for conv_id={conv_id}, "
                f"conv_session_id={conv_session_id}"
            )
        except Exception as e:
            logger.error(f"[InputQueue] Failed to clear inputs: {e}")

    def start_polling(self, conv_id: str) -> None:
        """启动后台轮询任务

        定期从数据库同步新输入到内存缓存。
        用于主动同步分布式场景下其他实例写入的数据。

        Args:
            conv_id: 对话ID
        """
        if conv_id in self._poll_tasks:
            return

        self._polling_enabled = True

        async def _poll_loop():
            while self._polling_enabled:
                try:
                    await asyncio.sleep(self._poll_interval)

                    dao = self._get_dao()
                    db_items = await dao.get_pending_by_conv(conv_id)

                    cached_ids = {
                        i.message_id for i in self._memory_cache.get(conv_id, [])
                    }

                    for item in db_items:
                        if item.message_id not in cached_ids:
                            queued_input = QueuedInput(
                                item_id=item.id,
                                message_id=item.message_id,
                                message_content=item.message_content,
                                sender_name=item.sender_name or "user",
                                sender_type=item.sender_type or "user",
                                priority=item.priority or 0,
                                extra=json.loads(item.extra) if item.extra else {},
                                created_at=item.gmt_create,
                            )
                            if conv_id not in self._memory_cache:
                                self._memory_cache[conv_id] = []
                            self._memory_cache[conv_id].append(queued_input)
                            logger.info(
                                f"[InputQueue] Polled new input: {item.message_id}"
                            )

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[InputQueue] Poll loop error: {e}")
                    await asyncio.sleep(1)

        self._poll_tasks[conv_id] = asyncio.create_task(_poll_loop())
        logger.info(f"[InputQueue] Started polling for conv_id={conv_id}")

    def stop_polling(self, conv_id: str) -> None:
        """停止轮询

        Args:
            conv_id: 对话ID
        """
        task = self._poll_tasks.pop(conv_id, None)
        if task:
            task.cancel()
            logger.info(f"[InputQueue] Stopped polling for conv_id={conv_id}")

    def stop_all_polling(self) -> None:
        """停止所有轮询"""
        self._polling_enabled = False
        for conv_id, task in list(self._poll_tasks.items()):
            task.cancel()
        self._poll_tasks.clear()
        logger.info("[InputQueue] Stopped all polling tasks")


# 单例模式
_input_queue_manager: Optional[InputQueueManager] = None


def get_input_queue_manager() -> InputQueueManager:
    """获取全局输入队列管理器实例"""
    global _input_queue_manager
    if _input_queue_manager is None:
        _input_queue_manager = InputQueueManager()
    return _input_queue_manager


def init_input_queue_manager(
    dao: Optional[AgentInputQueueDao] = None,
) -> InputQueueManager:
    """初始化全局输入队列管理器"""
    global _input_queue_manager
    _input_queue_manager = InputQueueManager(dao=dao)
    return _input_queue_manager
