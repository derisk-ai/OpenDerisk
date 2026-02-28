"""
可视化进度广播模块

提供实时进度推送能力，支持：
- WebSocket实时推送
- SSE事件流
- 进度状态管理
"""

from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class ProgressEventType(str, Enum):
    """进度事件类型"""
    THINKING = "thinking"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    PROGRESS = "progress"
    COMPLETE = "complete"


@dataclass
class ProgressEvent:
    """进度事件"""
    type: ProgressEventType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class ProgressBroadcaster:
    """
    进度广播器
    
    示例:
        broadcaster = ProgressBroadcaster()
        
        async def handler(event):
            print(f"[{event.type}] {event.content}")
        
        broadcaster.subscribe(handler)
        
        await broadcaster.thinking("正在分析问题...")
        await broadcaster.tool_started("bash", {"command": "ls"})
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        self._subscribers: List[Callable] = []
        self._websocket_clients: Set[Any] = set()
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._history: List[ProgressEvent] = []
        self._max_history = 1000
    
    def subscribe(self, handler: Callable[[ProgressEvent], None]):
        """订阅进度事件"""
        self._subscribers.append(handler)
    
    def unsubscribe(self, handler: Callable):
        """取消订阅"""
        if handler in self._subscribers:
            self._subscribers.remove(handler)
    
    def add_websocket(self, websocket: Any):
        """添加WebSocket客户端"""
        self._websocket_clients.add(websocket)
        logger.debug(f"[Progress] WebSocket客户端已添加，当前{len(self._websocket_clients)}个")
    
    def remove_websocket(self, websocket: Any):
        """移除WebSocket客户端"""
        self._websocket_clients.discard(websocket)
        logger.debug(f"[Progress] WebSocket客户端已移除，当前{len(self._websocket_clients)}个")
    
    async def _broadcast(self, event: ProgressEvent):
        """广播事件"""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        for handler in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"[Progress] 订阅者处理失败: {e}")
        
        if self._websocket_clients:
            message = json.dumps(event.to_dict(), ensure_ascii=False)
            dead_clients = set()
            
            for ws in self._websocket_clients:
                try:
                    await ws.send(message)
                except Exception:
                    dead_clients.add(ws)
            
            for ws in dead_clients:
                self._websocket_clients.discard(ws)
    
    async def thinking(self, content: str, **metadata):
        """发送思考事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.THINKING,
            content=content,
            metadata=metadata
        ))
    
    async def tool_started(self, tool_name: str, args: Dict[str, Any]):
        """发送工具开始事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.TOOL_STARTED,
            content=f"开始执行工具: {tool_name}",
            metadata={"tool_name": tool_name, "args": args}
        ))
    
    async def tool_completed(self, tool_name: str, result: str):
        """发送工具完成事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.TOOL_COMPLETED,
            content=f"工具 {tool_name} 执行完成",
            metadata={"tool_name": tool_name, "result": result}
        ))
    
    async def tool_failed(self, tool_name: str, error: str):
        """发送工具失败事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.TOOL_FAILED,
            content=f"工具 {tool_name} 执行失败: {error}",
            metadata={"tool_name": tool_name, "error": error}
        ))
    
    async def info(self, content: str, **metadata):
        """发送信息事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.INFO,
            content=content,
            metadata=metadata
        ))
    
    async def warning(self, content: str, **metadata):
        """发送警告事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.WARNING,
            content=content,
            metadata=metadata
        ))
    
    async def error(self, content: str, **metadata):
        """发送错误事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.ERROR,
            content=content,
            metadata=metadata
        ))
    
    async def progress(self, current: int, total: int, message: str = ""):
        """发送进度事件"""
        percent = (current / total * 100) if total > 0 else 0
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.PROGRESS,
            content=message or f"进度: {current}/{total}",
            metadata={
                "current": current,
                "total": total,
                "percent": round(percent, 1)
            }
        ))
    
    async def complete(self, result: str = ""):
        """发送完成事件"""
        await self._broadcast(ProgressEvent(
            type=ProgressEventType.COMPLETE,
            content=result or "任务完成",
            metadata={"final": True}
        ))
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取历史事件"""
        events = self._history[-limit:]
        return [e.to_dict() for e in events]


progress_broadcaster = ProgressBroadcaster()