import json
import logging
import os
import shutil
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Executor
from datetime import datetime
from typing import Optional, List, Dict, Any
from diskcache import Cache
from pathlib import Path

from derisk.agent import GptsMemory, ActionOutput
from derisk.agent.core.memory.gpts import GptsPlansMemory, GptsMessageMemory, GptsMessage
from derisk.agent.core.memory.gpts.gpts_memory import ConversationCache
from derisk.util.executor_utils import blocking_func_to_async
from derisk.vis import VisProtocolConverter
from ...user_proxy_agent import HUMAN_ROLE


logger = logging.getLogger(__name__)


class DiskConversationCache(ConversationCache):
    """使用 diskcache 存储 messages 的会话缓存（优化异步阻塞）"""

    def __init__(
        self,
        conv_id: str,
        vis_converter: VisProtocolConverter,
        start_round: int = 0,
        *,
        ttl: int = 3600,
        maxsize: int = 1000,
    ):
        # 初始化父类（views/plans 仍用 TTLCache）
        super().__init__(
            conv_id=conv_id,
            vis_converter=vis_converter,
            start_round=start_round,
            ttl=ttl,
            maxsize=maxsize
        )

        # 替换 messages 为 diskcache
        self.cache_dir = f'./pilot/message/cache/{conv_id}'
        self.messages = Cache(
            directory=self.cache_dir,
            timeout=ttl,
            size_limit=200 * 1024 * 1024,  # 200MB/会话
            disk_min_file_size=4096,
            disk_pickle_protocol=5,
            sqlite_journal_mode='WAL',
            cull_limit=20
        )

    def clear(self):
        """清理磁盘数据（异步执行）"""
        super().clear()

        def cleanup():
            try:
                if hasattr(self, 'messages') and self.messages is not None:
                    self.messages.close()
                    self.messages = None
            except Exception as e:
                logger.error(f"Error closing diskcache: {e}")
            try:
                if self.cache_dir and Path(self.cache_dir).exists():
                    shutil.rmtree(self.cache_dir, ignore_errors=True)
            except Exception as e:
                logger.error(f"Error removing cache directory: {e}")

        thread = threading.Thread(target=cleanup, daemon=True)
        thread.start()

    def __del__(self):
        try:
            if hasattr(self, 'messages') and self.messages is not None:
                self.messages.close()
                self.messages = None
        except (AttributeError, TypeError, ImportError):
            pass


class DiskGptsMemory(GptsMemory):
    """支持磁盘缓存 messages 的内存管理器（完全非阻塞）"""

    def _get_or_create_cache(
        self,
        conv_id: str,
        start_round: int = 0,
        vis_converter: Optional[VisProtocolConverter] = None,
    ) -> DiskConversationCache:
        with self._conversations_lock:
            if conv_id not in self._conversations:
                logger.info(
                    f"对话{conv_id}不在缓存中，构建新磁盘缓存！可视化组件:{vis_converter.render_name if vis_converter else ''}"
                )
                self._conversations[conv_id] = DiskConversationCache(
                    conv_id=conv_id,
                    vis_converter=vis_converter or self._default_vis_converter,
                    start_round=start_round,
                    ttl=self._cache_ttl,
                    maxsize=self._cache_maxsize,
                )
            return self._conversations[conv_id]

    async def _cache_messages(self, conv_id: str, messages: List[GptsMessage]):
        cache = self._get_cache(conv_id)
        if cache is None:
            return

        def write_to_cache():
            for msg in messages:
                cache.messages[msg.message_id] = msg
                if msg.message_id not in cache.message_ids:
                    cache.message_ids.append(msg.message_id)

        await blocking_func_to_async(self._executor, write_to_cache)

    async def append_message(
        self,
        conv_id: str,
        message: GptsMessage,
        incremental: bool = False,
        save_db: bool = True,
        sender: Optional["ConversableAgent"] = None
    ):
        cache = self._get_cache(conv_id)
        message.updated_at = datetime.now()

        if cache:
            def write_to_cache():
                cache.messages[message.message_id] = message
                if message.message_id not in cache.message_ids:
                    cache.message_ids.append(message.message_id)

            await blocking_func_to_async(self._executor, write_to_cache)

        if save_db:
            await blocking_func_to_async(
                self._executor, self._message_memory.update, message
            )

        await self.push_message(
            conv_id, gpt_msg=message, incremental=incremental, sender=sender
        )

    # ========================
    # 🔒 关键修复：所有读取操作放在线程池中
    # ========================

    async def get_messages(self, conv_id: str) -> List[GptsMessage]:
        cache = self._get_or_create_cache(conv_id)

        def _load_ordered_messages():
            msgs = []
            for msg_id in cache.message_ids:
                msg = cache.messages.get(msg_id)
                if msg is not None:
                    msgs.append(msg)
            msgs.sort(key=lambda x: x.rounds)
            return msgs

        return await blocking_func_to_async(self._executor, _load_ordered_messages)

    async def get_agent_messages(self, conv_id: str, agent: str) -> List[GptsMessage]:
        messages = await self.get_messages(conv_id)
        return [
            msg for msg in messages
            if msg.sender == agent or msg.receiver == agent
        ]

    async def user_answer(self, conv_id: str) -> str:
        cache = self._get_cache(conv_id)

        def _find_last_human_response():
            # Load all messages synchronously
            all_msgs = []
            for mid in cache.message_ids:
                m = cache.messages.get(mid)
                if m:
                    all_msgs.append(m)
            all_msgs.sort(key=lambda x: x.rounds)
            messages = all_msgs[cache.start_round:]

            reversed_messages = list(reversed(messages))
            final_content = None
            for message in reversed_messages:
                content_view = message.content
                if message.action_report:
                    try:
                        action_out = message.action_report[0]
                        if action_out is not None:
                            content_view = action_out.content
                    except json.JSONDecodeError:
                        logger.error(f"Invalid action_report format: {message.action_report}")
                if final_content is None:
                    final_content = content_view
                if message.receiver == HUMAN_ROLE:
                    return content_view
            return final_content

        return await blocking_func_to_async(self._executor, _find_last_human_response)




