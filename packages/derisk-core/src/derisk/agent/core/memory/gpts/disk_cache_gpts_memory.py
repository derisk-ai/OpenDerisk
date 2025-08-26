import logging
import os
import shutil
from concurrent.futures import Executor
from typing import Optional, List
from diskcache import FanoutCache, Cache
from pathlib import Path

from derisk.agent import GptsMemory
from derisk.agent.core.memory.gpts import GptsPlansMemory, GptsMessageMemory, GptsMessage
from derisk.agent.core.memory.gpts.gpts_memory import ConversationCache
from derisk.vis import VisProtocolConverter

logger = logging.getLogger(__name__)


class DiskConversationCache(ConversationCache):
    """使用 diskcache 存储 messages 的会话缓存"""

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
        self.cache_dir = f'./pilot/message/cache/{conv_id}'  # 默认缓存路径
        self.messages = Cache(
            directory=self.cache_dir,
            timeout=ttl,
            size_limit=200 * 1024 * 1024,  # 200MB/会话
            disk_min_file_size=4096,  # >4KB存文件
            disk_pickle_protocol=5,
            sqlite_journal_mode='WAL',
            cull_limit=20  # 更激进清理
        )

    def touch(self):
        """续期：更新消息缓存的过期时间"""
        # diskcache 自动处理过期，无需手动操作
        super().touch()  # 父类的 views/plans 仍需续期



    def clear(self):
        """覆盖基类方法，清理磁盘数据"""
        super().clear()  # 调用父类清理内存数据

        # 清理磁盘缓存
        if self.cache_dir and Path(self.cache_dir).exists():
            shutil.rmtree(self.cache_dir, ignore_errors=True)

        # 关闭缓存连接
        self.messages.close()

    def __del__(self):
        try:
            if hasattr(self, 'messages') and self.messages is not None:
                self.messages.close()
        except (AttributeError, TypeError, ImportError):
            # 解释器退出时忽略所有错误
            pass
class DiskGptsMemory(GptsMemory):
    """支持磁盘缓存 messages 的内存管理器"""

    def _get_or_create_cache(
            self,
            conv_id: str,
            start_round: int = 0,
            vis_converter: Optional[VisProtocolConverter] = None,
    ) -> DiskConversationCache:
        """创建带磁盘缓存的会话对象"""
        if conv_id not in self._conversations:
            self._conversations[conv_id] = DiskConversationCache(
                conv_id=conv_id,
                vis_converter=vis_converter,
                start_round=start_round,
                ttl=self._cache_ttl,
                maxsize=self._cache_maxsize,
            )
        return self._conversations[conv_id]

