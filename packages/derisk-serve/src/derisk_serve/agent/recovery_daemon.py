"""PR 4: 启动时恢复守护进程。

进程启动时扫所有 RUNNING 会话，按心跳判断是否真死：
- 心跳新鲜 → 跳过（多进程部署场景，会话在另一进程跑）
- 心跳陈旧 → 标记 RETRYING + 触发恢复：
  - 有 pending_subagents → SubagentCoordinator.recover_main
  - 无 pending_subagents → 调 aggregation_chat(is_retry_chat=True) 触发 retry

恢复方式：复用 PR 3 的 step-level resume（跳过已成功工具，复用 work_log）

Tier 3.2: lease 机制
- 恢复前用 acquire_lease 原子抢占会话，避免双进程同时 retry
- 心跳新鲜但 lease 已过期 → 也尝试抢占（边缘 case，老 worker 死后 lease 自然释放）
- 抢占失败 → 跳过（已被其他 worker 接管）
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from derisk_serve.agent.heartbeat import (
    acquire_lease,
    get_worker_id,
    is_lease_expired,
    is_stale,
    touch_heartbeat,
)
from derisk_serve.agent.db.gpts_conversations_db import (
    GptsConversationsDao,
    GptsConversationsEntity,
)
from derisk_serve.agent.subagent_coordinator import SubagentCoordinator

logger = logging.getLogger(__name__)


class RecoveryDaemon:
    """进程启动时扫所有 RUNNING 会话，按心跳判断是否真死，真死的恢复。

    Usage:
        daemon = RecoveryDaemon(agent_chat=<AgentChat instance>)
        await daemon.scan_and_recover()
    """

    def __init__(self, agent_chat: Optional[object] = None):
        """Args:
            agent_chat: AgentChat 实例，提供 aggregation_chat / gpts_conversations 等依赖。
                可为 None（dry-run 模式，只 log 不实际恢复）。
        """
        self._agent_chat = agent_chat
        self._coordinator: Optional[SubagentCoordinator] = (
            SubagentCoordinator(agent_chat=agent_chat) if agent_chat else None
        )

    async def scan_and_recover(self) -> dict:
        """扫描所有 RUNNING 会话，按心跳决策恢复。

        Returns:
            统计字典：{scanned, fresh_skipped, stale_recovered, lease_lost, errors}
        """
        stats = {
            "scanned": 0,
            "fresh_skipped": 0,
            "stale_recovered": 0,
            "lease_lost": 0,
            "errors": 0,
        }
        try:
            dao = GptsConversationsDao()
            running_convs: List[GptsConversationsEntity] = await asyncio.to_thread(
                dao.get_running_convs
            )
        except Exception as e:
            logger.exception(f"[recovery-daemon] failed to query RUNNING convs: {e}")
            stats["errors"] += 1
            return stats

        logger.info(
            f"[recovery-daemon] scan start: {len(running_convs)} RUNNING convs, "
            f"worker_id={get_worker_id()}"
        )

        for conv in running_convs:
            stats["scanned"] += 1
            try:
                await self._process_one(conv, stats)
            except Exception as e:
                logger.exception(
                    f"[recovery-daemon] error processing conv={conv.conv_id}: {e}"
                )
                stats["errors"] += 1

        logger.info(f"[recovery-daemon] scan done: {stats}")
        return stats

    async def _process_one(
        self, conv: GptsConversationsEntity, stats: dict
    ) -> None:
        """处理单个 RUNNING 会话：检查心跳 + lease，必要时抢占并恢复。"""
        conv_id = conv.conv_id

        # 1. 心跳新鲜 + lease 在本进程或未过期 → 跳过（在另一进程跑）
        if not is_stale(conv.last_heartbeat):
            # 心跳新鲜，但 lease 可能已过期（边缘 case）—— 检查
            if not is_lease_expired(getattr(conv, "lease_expires_at", None)):
                logger.info(
                    f"[recovery-daemon] conv={conv_id} heartbeat fresh + lease valid, "
                    f"skipping (likely running in another process)"
                )
                stats["fresh_skipped"] += 1
                return
            # 心跳新鲜但 lease 过期 → 极少见，可能是手动改 DB。继续抢占。
            logger.warning(
                f"[recovery-daemon] conv={conv_id} heartbeat fresh but lease expired, "
                f"attempting takeover"
            )

        # 2. 心跳陈旧（或 lease 过期）→ 尝试原子抢占
        acquired = await acquire_lease(conv_id)
        if not acquired:
            # 被其他 worker 抢先 → 跳过
            logger.info(
                f"[recovery-daemon] conv={conv_id} lease acquired by another worker, "
                f"skipping"
            )
            stats["lease_lost"] += 1
            return

        logger.warning(
            f"[recovery-daemon] conv={conv_id} lease acquired by worker={get_worker_id()}, "
            f"recovering"
        )

        # 3. 标记 RETRYING（状态机守卫 PR 1）
        try:
            from derisk.agent.core.step_state_guard import (
                validate_session_transition,
                WARN_ONLY,
            )
            from derisk.agent.core.schema import Status
            try:
                validate_session_transition(
                    Status.RUNNING, Status.RETRYING
                )
            except Exception as ve:
                if not WARN_ONLY:
                    raise
                logger.warning(
                    f"[recovery-daemon] transition guard warning for {conv_id}: {ve}"
                )
            dao = GptsConversationsDao()
            await asyncio.to_thread(dao.update, conv_id, Status.RETRYING.value)
        except Exception as e:
            logger.warning(
                f"[recovery-daemon] failed to mark RETRYING for {conv_id}: {e}"
            )

        # 4. 触发恢复：有 pending_subagents 走 coordinator，否则直接 retry main
        if self._coordinator and self._has_pending_subagents(conv):
            await self._coordinator.recover_main(conv_id)
        else:
            await self._trigger_main_retry(conv_id)

        stats["stale_recovered"] += 1

    @staticmethod
    def _has_pending_subagents(conv: GptsConversationsEntity) -> bool:
        """检查 conv.extra 是否有 pending_subagents。"""
        if not conv.extra:
            return False
        try:
            import json
            extra = json.loads(conv.extra) if isinstance(conv.extra, str) else conv.extra
            if not isinstance(extra, dict):
                return False
            pending = extra.get("pending_subagents", [])
            return bool(pending)
        except Exception:
            return False

    async def _trigger_main_retry(self, conv_id: str) -> None:
        """无 pending_subagents 时，直接调 aggregation_chat 触发 retry main。

        PR 4 实现：如果 agent_chat 提供，调用其 aggregation_chat(is_retry_chat=True)。
        否则只 log（dry-run）。
        """
        if not self._agent_chat:
            logger.info(
                f"[recovery-daemon] dry-run: would trigger main retry for {conv_id}"
            )
            return

        try:
            aggregation_chat = getattr(self._agent_chat, "aggregation_chat", None)
            if not aggregation_chat:
                logger.warning(
                    f"[recovery-daemon] agent_chat has no aggregation_chat method, "
                    f"cannot trigger retry for {conv_id}"
                )
                return
            # 触发 retry：is_retry_chat=True 让 V1 走 _recovery_message 路径
            # + PR 3 step-level resume 跳过已成功工具
            await aggregation_chat(
                conv_id=conv_id,
                user_query=None,
                is_retry_chat=True,
                user_message_content="[auto-recovery] resuming after crash",
            )
            # 恢复后刷新心跳，标记为本进程在跑
            touch_heartbeat(conv_id)
        except Exception as e:
            logger.exception(
                f"[recovery-daemon] failed to trigger main retry for {conv_id}: {e}"
            )
