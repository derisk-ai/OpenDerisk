"""
Progress - 实时进度可视化推送

参考OpenClaw的Block Streaming设计
实时推送Agent执行进度、思考过程、工具执行状态
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime
import json
import asyncio
import logging

logger = logging.getLogger(__name__)


class ProgressType(str, Enum):
    """进度类型"""

    THINKING = "thinking"  # 思考中
    TOOL_EXECUTION = "tool_execution"  # 工具执行
    SUBAGENT = "subagent"  # 子Agent
    ERROR = "error"  # 错误
    SUCCESS = "success"  # 成功
    WARNING = "warning"  # 警告
    INFO = "info"  # 信息


class ProgressEvent(BaseModel):
    """进度事件"""

    type: ProgressType  # 事件类型
    session_id: str  # Session ID
    message: str  # 消息
    details: Dict[str, Any] = Field(default_factory=dict)  # 详细信息
    percent: Optional[int] = None  # 进度百分比(0-100)
    timestamp: datetime = Field(default_factory=datetime.now)  # 时间戳

    class Config:
        use_enum_values = True
        arbitrary_types_allowed = True


class ProgressBroadcaster:
    """
    进度广播器 - 实时推送进度事件

    示例:
        broadcaster = ProgressBroadcaster(session_id, gateway)

        # 思考进度
        await broadcaster.thinking("正在分析问题...")

        # 工具执行进度
        await broadcaster.tool_execution("bash", "ls -la", "executing")

        # 错误
        await broadcaster.error("执行失败")
    """

    def __init__(self, session_id: str, gateway=None):
        self.session_id = session_id
        self.gateway = gateway
        self._subscribers: List = []
        self._event_count = 0

        logger.debug(f"[ProgressBroadcaster] 初始化: session={session_id[:8]}")

    async def broadcast(self, event: ProgressEvent):
        """
        广播进度事件

        Args:
            event: 进度事件
        """
        self._event_count += 1

        # 发送到Gateway
        if self.gateway:
            await self._send_to_gateway(event)

        # 发送给订阅者
        for subscriber in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(subscriber):
                    await subscriber(event)
                else:
                    subscriber(event)
            except Exception as e:
                logger.error(f"[ProgressBroadcaster] 发送给订阅者失败: {e}")

        logger.debug(
            f"[ProgressBroadcaster] 广播事件: {event.type} - {event.message[:50]}"
        )

    async def _send_to_gateway(self, event: ProgressEvent):
        """发送到Gateway"""
        if not self.gateway:
            return

        try:
            message = {
                "type": "progress",
                "session_id": self.session_id,
                "event": event.dict(),
            }

            # 假设Gateway有send_to_session方法
            if hasattr(self.gateway, "send_to_session"):
                await self.gateway.send_to_session(self.session_id, message)
            elif hasattr(self.gateway, "message_queue"):
                await self.gateway.message_queue.put(message)

        except Exception as e:
            logger.error(f"[ProgressBroadcaster] 发送到Gateway失败: {e}")

    # ========== 便捷方法 ==========

    async def thinking(self, content: str, percent: Optional[int] = None):
        """
        思考进度

        Args:
            content: 思考内容
            percent: 进度百分比
        """
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.THINKING,
                session_id=self.session_id,
                message=content,
                percent=percent,
            )
        )

    async def tool_execution(
        self,
        tool_name: str,
        args: Dict[str, Any],
        status: str = "started",
        percent: Optional[int] = None,
    ):
        """
        工具执行进度

        Args:
            tool_name: 工具名称
            args: 工具参数
            status: 执行状态(started/executing/completed/failed)
            percent: 进度百分比
        """
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.TOOL_EXECUTION,
                session_id=self.session_id,
                message=f"工具 {tool_name}: {status}",
                details={"tool_name": tool_name, "args": args, "status": status},
                percent=percent,
            )
        )

    async def tool_started(self, tool_name: str, args: Dict[str, Any]):
        """工具开始执行"""
        await self.tool_execution(tool_name, args, "started", 0)

    async def tool_completed(self, tool_name: str, result_summary: str):
        """工具执行完成"""
        await self.tool_execution(tool_name, {}, "completed", 100)

    async def tool_failed(self, tool_name: str, error: str):
        """工具执行失败"""
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.ERROR,
                session_id=self.session_id,
                message=f"工具 {tool_name} 执行失败: {error}",
                details={"tool_name": tool_name, "error": error},
            )
        )

    async def error(self, message: str, details: Optional[Dict] = None):
        """
        错误进度

        Args:
            message: 错误消息
            details: 详细信息
        """
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.ERROR,
                session_id=self.session_id,
                message=message,
                details=details or {},
            )
        )

    async def success(self, message: str, details: Optional[Dict] = None):
        """
        成功进度

        Args:
            message: 成功消息
            details: 详细信息
        """
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.SUCCESS,
                session_id=self.session_id,
                message=message,
                details=details or {},
                percent=100,
            )
        )

    async def warning(self, message: str, details: Optional[Dict] = None):
        """
        警告进度

        Args:
            message: 警告消息
            details: 详细信息
        """
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.WARNING,
                session_id=self.session_id,
                message=message,
                details=details or {},
            )
        )

    async def info(self, message: str, details: Optional[Dict] = None):
        """
        信息进度

        Args:
            message: 信息消息
            details: 详细信息
        """
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.INFO,
                session_id=self.session_id,
                message=message,
                details=details or {},
            )
        )

    async def subagent(self, subagent_name: str, task: str, status: str = "started"):
        """
        子Agent进度

        Args:
            subagent_name: 子Agent名称
            task: 任务描述
            status: 状态
        """
        await self.broadcast(
            ProgressEvent(
                type=ProgressType.SUBAGENT,
                session_id=self.session_id,
                message=f"子Agent {subagent_name}: {status}",
                details={
                    "subagent_name": subagent_name,
                    "task": task,
                    "status": status,
                },
            )
        )

    # ========== 订阅管理 ==========

    def subscribe(self, callback):
        """
        订阅进度事件

        Args:
            callback: 回调函数
        """
        self._subscribers.append(callback)
        logger.debug(
            f"[ProgressBroadcaster] 添加订阅者，总数: {len(self._subscribers)}"
        )

    def unsubscribe(self, callback):
        """
        取消订阅

        Args:
            callback: 回调函数
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.debug(
                f"[ProgressBroadcaster] 移除订阅者，总数: {len(self._subscribers)}"
            )

    # ========== 统计 ==========

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "session_id": self.session_id,
            "total_events": self._event_count,
            "subscribers": len(self._subscribers),
        }


class ProgressManager:
    """
    进度管理器 - 管理多个Session的进度

    示例:
        manager = ProgressManager(gateway)

        # 创建广播器
        broadcaster = manager.create_broadcaster("session-1")

        # 使用广播器
        await broadcaster.thinking("思考中...")

        # 获取统计
        stats = manager.get_all_stats()
    """

    def __init__(self, gateway=None):
        self.gateway = gateway
        self._broadcasters: Dict[str, ProgressBroadcaster] = {}

    def create_broadcaster(self, session_id: str) -> ProgressBroadcaster:
        """
        创建进度广播器

        Args:
            session_id: Session ID

        Returns:
            ProgressBroadcaster: 广播器实例
        """
        if session_id not in self._broadcasters:
            broadcaster = ProgressBroadcaster(session_id, self.gateway)
            self._broadcasters[session_id] = broadcaster
            logger.info(f"[ProgressManager] 创建广播器: {session_id[:8]}")

        return self._broadcasters[session_id]

    def get_broadcaster(self, session_id: str) -> Optional[ProgressBroadcaster]:
        """获取广播器"""
        return self._broadcasters.get(session_id)

    def remove_broadcaster(self, session_id: str):
        """删除广播器"""
        if session_id in self._broadcasters:
            del self._broadcasters[session_id]
            logger.info(f"[ProgressManager] 删除广播器: {session_id[:8]}")

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有广播器的统计信息"""
        return {
            session_id: broadcaster.get_stats()
            for session_id, broadcaster in self._broadcasters.items()
        }


# 全局进度管理器
_progress_manager: Optional[ProgressManager] = None


def get_progress_manager() -> ProgressManager:
    """获取全局进度管理器"""
    global _progress_manager
    if _progress_manager is None:
        _progress_manager = ProgressManager()
    return _progress_manager


def init_progress_manager(gateway=None) -> ProgressManager:
    """初始化全局进度管理器"""
    global _progress_manager
    _progress_manager = ProgressManager(gateway)
    return _progress_manager


def create_broadcaster(session_id: str) -> ProgressBroadcaster:
    """创建进度广播器(便捷函数)"""
    return get_progress_manager().create_broadcaster(session_id)
