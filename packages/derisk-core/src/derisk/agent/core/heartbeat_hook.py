"""PR 4: 心跳 hook（derisk-core 层，避免反向依赖 derisk-serve）。

derisk-core 不直接依赖 derisk-serve，但 agent loop（base_agent / react_master_agent）
需要 inline 触发心跳。用注册模式：derisk-serve 在启动时注册实际实现，
derisk-core 调用注册的 callback。未注册时 no-op。

设计：
- agent loop 自然进度点调 touch_heartbeat(conv_id)
- derisk-serve.heartbeat 在 import 时 register_heartbeat_callback(real_impl)
- 测试可注入 mock callback
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 实际心跳实现（由 derisk-serve.heartbeat 注册）
_heartbeat_callback: Optional[Callable[[str], None]] = None


def register_heartbeat_callback(cb: Callable[[str], None]) -> None:
    """注册心跳实现。derisk-serve 启动时调用。"""
    global _heartbeat_callback
    _heartbeat_callback = cb
    logger.debug("[heartbeat-hook] callback registered")


def touch_heartbeat(conv_id: str) -> None:
    """触发心跳。在 agent loop 自然进度点调用。

    未注册 callback 时 no-op（derisk-core 单元测试场景）。
    """
    if not conv_id:
        return
    cb = _heartbeat_callback
    if cb is None:
        return
    try:
        cb(conv_id)
    except Exception as e:
        # fire-and-forget：心跳失败不阻塞 loop
        logger.warning(f"[heartbeat-hook] callback failed for {conv_id}: {e}")


def reset_heartbeat_callback() -> None:
    """测试用：清除注册的 callback。"""
    global _heartbeat_callback
    _heartbeat_callback = None
