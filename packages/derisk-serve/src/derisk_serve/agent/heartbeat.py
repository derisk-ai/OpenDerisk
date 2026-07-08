"""PR 4: 心跳工具模块（inline 到 agent loop，非独立组件）。

设计原则（用户明确要求）：
- 心跳与 AgentLoop 深度绑定，不是独立 HeartbeatManager
- 在 agent loop 自然进度点（think/act 前后）inline 更新
- fire-and-forget：asyncio.create_task 不 await，失败只 log warning，不阻塞 loop

判定：
- loop 正常跑 → 心跳自然新鲜
- 进程崩溃 / kill -9 → 心跳停止更新 → 重启时 RecoveryDaemon 检测到陈旧 → 自动恢复

STALE_THRESHOLD = 90s：足够长（覆盖 LLM 长响应 + 工具执行），足够短（崩溃后 90s 内重启能检测到）

Tier 3.2: lease 机制
- 全局 worker_id（每个进程一个 UUID，启动时生成）
- touch_heartbeat 同时 renew_lease，把心跳更新和租约续绑定在一起
- RecoveryDaemon 用 acquire_lease 抢占会话，避免双进程同时 retry
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

# 注册 derisk-core 的心跳 hook（避免 derisk-core 反向依赖 derisk-serve）
try:
    from derisk.agent.core.heartbeat_hook import register_heartbeat_callback
    register_heartbeat_callback(lambda conv_id: touch_heartbeat(conv_id))
except Exception:
    # derisk-core 不可用（极少数测试场景）— 静默跳过
    pass

logger = logging.getLogger(__name__)

# 心跳陈旧阈值（秒）。超过则视为会话已死，可被恢复。
STALE_THRESHOLD_SECONDS = 90
# 租约 TTL（秒）。续租周期需小于此值，否则会被其他 worker 抢占。
LEASE_TTL_SECONDS = 90

# Tier 3.2: 进程级 worker_id，启动时生成一次
_WORKER_ID: str = str(uuid.uuid4())


def get_worker_id() -> str:
    """获取当前进程的 worker_id（每个进程唯一，启动时生成）。"""
    return _WORKER_ID


async def _update_heartbeat_safe(conv_id: str) -> None:
    """fire-and-forget 心跳更新，失败只 log warning。

    Tier 3.2: 如果当前 worker 持有 lease，同时续租；否则只更新 last_heartbeat
    （acquire_lease 在会话入口单独调用）。
    """
    try:
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

        dao = GptsConversationsDao()
        # 尝试续租（如果当前 worker 持有 lease）
        renewed = await asyncio.to_thread(
            dao.renew_lease, conv_id, get_worker_id(), LEASE_TTL_SECONDS
        )
        if not renewed:
            # 未持有 lease 或被抢占 → 退化为只更新心跳（向后兼容）
            await asyncio.to_thread(dao.update_heartbeat, conv_id)
    except Exception as e:
        logger.warning(f"[heartbeat] update failed for conv={conv_id}: {e}")


def touch_heartbeat(conv_id: str) -> None:
    """非阻塞心跳：spawn 一个 task 不 await，立即返回。

    在 agent loop 自然进度点调用（think 前 / act 前后），
    loop 不等待 DB 写完成。

    Args:
        conv_id: 会话 ID
    """
    if not conv_id:
        return
    try:
        asyncio.create_task(_update_heartbeat_safe(conv_id))
    except RuntimeError:
        # No running event loop — 静默跳过（同步上下文调用）
        logger.debug(f"[heartbeat] no event loop, skipping touch for {conv_id}")


def is_stale(
    last_heartbeat: Optional[datetime], threshold_seconds: int = STALE_THRESHOLD_SECONDS
) -> bool:
    """判断心跳是否陈旧（会话是否真死）。

    None 视为陈旧（无心跳 = 可能从未启动 / 老数据无字段）。
    """
    if last_heartbeat is None:
        return True
    delta = (datetime.utcnow() - last_heartbeat).total_seconds()
    return delta > threshold_seconds


# ---- Tier 3.2: lease 公开接口 ----

async def acquire_lease(conv_id: str, ttl_seconds: int = LEASE_TTL_SECONDS) -> bool:
    """获取会话租约。

    在会话入口（_inner_chat 开始）调用，确保当前 worker 拥有会话所有权。
    多进程部署下，避免两个 worker 同时跑同一会话。

    Returns:
        True 如果获取成功；False 如果已被其他 worker 持有且未过期。
    """
    if not conv_id:
        return False
    try:
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

        dao = GptsConversationsDao()
        return await asyncio.to_thread(
            dao.acquire_lease, conv_id, get_worker_id(), ttl_seconds
        )
    except Exception as e:
        logger.warning(f"[lease] acquire failed for conv={conv_id}: {e}")
        return False


async def release_lease(conv_id: str) -> None:
    """释放会话租约。

    在会话正常结束 / 异常退出时调用。fire-and-forget，失败只 log warning。
    """
    if not conv_id:
        return
    try:
        from derisk_serve.agent.db.gpts_conversations_db import GptsConversationsDao

        dao = GptsConversationsDao()
        await asyncio.to_thread(dao.release_lease, conv_id, get_worker_id())
    except Exception as e:
        logger.warning(f"[lease] release failed for conv={conv_id}: {e}")


def is_lease_expired(lease_expires_at: Optional[datetime]) -> bool:
    """判断租约是否过期。None 视为过期（无租约 = 可被抢占）。"""
    if lease_expires_at is None:
        return True
    return datetime.utcnow() > lease_expires_at
