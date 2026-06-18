"""ColdPersistenceAdapter 的生产实现 —— 包装 gpts_cold_segments DAO。

放在 react_master_agent 层（而非 context_engine 内），因为它依赖 derisk_serve 的
DAO；context_engine 保持对存储无依赖、可纯测。DAO 不可用时静默降级（load 返回
None / save no-op），由 ContextEngine 的内存缓存兜底，绝不阻塞主流程。
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from .context_engine.summarizer import HandoffMessage

logger = logging.getLogger(__name__)


class DbColdPersistenceAdapter:
    """基于 gpts_cold_segments 表的 cold handoff 持久化。"""

    def __init__(self, executor: Optional[ThreadPoolExecutor] = None):
        self._executor = executor
        self._dao = None
        self._dao_init_failed = False

    def _get_dao(self):
        if self._dao is not None or self._dao_init_failed:
            return self._dao
        try:
            from derisk_serve.agent.db.gpts_cold_segment_db import GptsColdSegmentDao

            self._dao = GptsColdSegmentDao()
        except Exception as e:  # derisk_serve 不可用 → 降级
            logger.warning(
                "[DbColdPersistence] DAO 不可用，cold handoff 降级为内存：%s", e
            )
            self._dao_init_failed = True
        return self._dao

    async def load_handoff(
        self, session_id: str, content_hash: str
    ) -> Optional[HandoffMessage]:
        dao = self._get_dao()
        if dao is None:
            return None
        try:
            # 优先异步方法
            if hasattr(dao, "get_by_hash_async"):
                row = await dao.get_by_hash_async(session_id, content_hash)
            else:
                row = await asyncio.get_event_loop().run_in_executor(
                    self._executor, dao.get_by_hash, session_id, content_hash
                )
        except Exception as e:
            logger.warning("[DbColdPersistence] load 失败：%s", e)
            return None
        if not row:
            return None
        return HandoffMessage(
            content=row.get("summary") or "",
            content_hash=content_hash,
            source_unit_ids=row.get("source_message_ids") or [],
            original_tokens=row.get("original_tokens", 0),
            compressed_tokens=row.get("compressed_tokens", 0),
            degraded=False,
        )

    async def save_handoff(
        self, session_id: str, conv_id: str, handoff: HandoffMessage
    ) -> None:
        dao = self._get_dao()
        if dao is None:
            return
        try:
            if hasattr(dao, "upsert_async"):
                await dao.upsert_async(
                    session_id=session_id,
                    conv_id=conv_id,
                    content_hash=handoff.content_hash,
                    summary=handoff.content,
                    source_message_ids=handoff.source_unit_ids,
                    original_tokens=handoff.original_tokens,
                    compressed_tokens=handoff.compressed_tokens,
                )
            else:
                await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    lambda: dao.upsert(
                        session_id,
                        conv_id,
                        handoff.content_hash,
                        handoff.content,
                        handoff.source_unit_ids,
                        handoff.original_tokens,
                        handoff.compressed_tokens,
                    ),
                )
        except Exception as e:
            logger.warning("[DbColdPersistence] save 失败：%s", e)
