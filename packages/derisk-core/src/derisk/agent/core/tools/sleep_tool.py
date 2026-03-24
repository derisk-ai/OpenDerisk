"""
SleepTool - Agent Loop 休眠工具

允许 LLM 在需要等待的场景下暂停 agent loop 执行
时长限定 1 秒到 5 分钟 (300 秒)
"""

import asyncio
import logging
from typing import Optional

from derisk.agent.core.system_tool_registry import system_tool

logger = logging.getLogger(__name__)

# Sleep 请求存储，用于跨工具调用传递 sleep 状态
_sleep_requests: dict = {}


@system_tool(
    name="sleep",
    description="""暂停 Agent Loop 执行指定时间。

在需要等待的场景下使用，例如：
- 等待异步任务完成
- 等待外部服务响应
- 避免频繁轮询

时长限制：1 秒到 5 分钟 (300 秒)
注意：休眠期间 Agent 不会执行任何操作。""",
    ask_user=False,
)
async def sleep(duration: int, reason: Optional[str] = None) -> str:
    """
    暂停 Agent Loop 执行

    Args:
        duration: 休眠时长（秒），范围 1-300 秒
        reason: 休眠原因（可选）

    Returns:
        str: 休眠结果信息
    """
    # 参数校验
    if duration < 1:
        return "错误：休眠时长不能小于 1 秒"

    if duration > 300:
        return "错误：休眠时长不能超过 5 分钟 (300 秒)"

    # 记录休眠请求
    reason_text = f"，原因：{reason}" if reason else ""
    logger.info(f"[SleepTool] 开始休眠 {duration} 秒{reason_text}")

    try:
        # 执行休眠
        await asyncio.sleep(duration)

        logger.info(f"[SleepTool] 休眠完成，已休眠 {duration} 秒")
        return f"已完成休眠 {duration} 秒{reason_text}"

    except asyncio.CancelledError:
        logger.warning(f"[SleepTool] 休眠被中断")
        return f"休眠被中断（已休眠部分时间）"
    except Exception as e:
        logger.error(f"[SleepTool] 休眠失败: {e}")
        return f"休眠失败: {str(e)}"


def get_sleep_request(session_id: str) -> Optional[int]:
    """
    获取指定会话的 sleep 请求时长

    Args:
        session_id: 会话 ID

    Returns:
        Optional[int]: sleep 时长（秒），如果没有请求则返回 None
    """
    return _sleep_requests.get(session_id)


def clear_sleep_request(session_id: str) -> None:
    """
    清除指定会话的 sleep 请求

    Args:
        session_id: 会话 ID
    """
    _sleep_requests.pop(session_id, None)


def set_sleep_request(session_id: str, duration: int) -> None:
    """
    设置指定会话的 sleep 请求

    Args:
        session_id: 会话 ID
        duration: sleep 时长（秒）
    """
    _sleep_requests[session_id] = duration
