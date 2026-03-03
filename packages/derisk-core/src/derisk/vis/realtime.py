"""
实时推送系统

支持WebSocket和SSE的实时数据推送
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class RealtimePusher(ABC):
    """实时推送器基类"""
    
    @abstractmethod
    async def push_part(self, conv_id: str, part: Any):
        """推送Part"""
        pass
    
    @abstractmethod
    async def push_event(self, conv_id: str, event_type: str, data: Dict[str, Any]):
        """推送事件"""
        pass
    
    @abstractmethod
    def add_client(self, conv_id: str, client: Any):
        """添加客户端"""
        pass
    
    @abstractmethod
    def remove_client(self, conv_id: str, client: Any):
        """移除客户端"""
        pass


class WebSocketPusher(RealtimePusher):
    """
    WebSocket实时推送器
    
    支持多会话、多客户端的实时推送
    """
    
    def __init__(self):
        # conv_id -> set of websocket clients
        self._clients: Dict[str, Set[Any]] = {}
        # 消息队列(用于异步处理)
        self._message_queue: asyncio.Queue = asyncio.Queue()
        # 历史消息缓存
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._max_history_per_conv = 100
    
    async def push_part(self, conv_id: str, part: Any):
        """
        推送Part到指定会话
        
        Args:
            conv_id: 会话ID
            part: Part实例
        """
        # 转换为字典
        if hasattr(part, 'to_vis_dict'):
            part_dict = part.to_vis_dict()
        elif hasattr(part, 'model_dump'):
            part_dict = part.model_dump()
        else:
            part_dict = dict(part)
        
        # 构建消息
        message = {
            "type": "part_update",
            "conv_id": conv_id,
            "timestamp": datetime.now().isoformat(),
            "data": part_dict
        }
        
        await self._broadcast(conv_id, message)
    
    async def push_event(self, conv_id: str, event_type: str, data: Dict[str, Any]):
        """
        推送事件
        
        Args:
            conv_id: 会话ID
            event_type: 事件类型
            data: 事件数据
        """
        message = {
            "type": "event",
            "event_type": event_type,
            "conv_id": conv_id,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        await self._broadcast(conv_id, message)
    
    async def _broadcast(self, conv_id: str, message: Dict[str, Any]):
        """
        广播消息到所有客户端
        
        Args:
            conv_id: 会话ID
            message: 消息内容
        """
        # 记录历史
        if conv_id not in self._history:
            self._history[conv_id] = []
        
        self._history[conv_id].append(message)
        if len(self._history[conv_id]) > self._max_history_per_conv:
            self._history[conv_id] = self._history[conv_id][-self._max_history_per_conv:]
        
        # 获取客户端列表
        clients = self._clients.get(conv_id, set())
        
        if not clients:
            logger.debug(f"[WS] 会话 {conv_id} 没有连接的客户端")
            return
        
        # 序列化消息
        message_str = json.dumps(message, ensure_ascii=False, default=str)
        
        # 广播
        dead_clients = set()
        for client in clients:
            try:
                await client.send(message_str)
            except Exception as e:
                logger.debug(f"[WS] 发送消息失败: {e}")
                dead_clients.add(client)
        
        # 清理断开的客户端
        for client in dead_clients:
            self.remove_client(conv_id, client)
    
    def add_client(self, conv_id: str, client: Any):
        """
        添加WebSocket客户端
        
        Args:
            conv_id: 会话ID
            client: WebSocket客户端对象
        """
        if conv_id not in self._clients:
            self._clients[conv_id] = set()
        
        self._clients[conv_id].add(client)
        logger.info(f"[WS] 客户端已连接到会话 {conv_id},当前{len(self._clients[conv_id])}个客户端")
    
    def remove_client(self, conv_id: str, client: Any):
        """
        移除WebSocket客户端
        
        Args:
            conv_id: 会话ID
            client: WebSocket客户端对象
        """
        if conv_id in self._clients:
            self._clients[conv_id].discard(client)
            logger.info(f"[WS] 客户端已断开会话 {conv_id},剩余{len(self._clients[conv_id])}个客户端")
            
            # 清理空会话
            if not self._clients[conv_id]:
                del self._clients[conv_id]
    
    def get_history(self, conv_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取历史消息
        
        Args:
            conv_id: 会话ID
            limit: 限制数量
            
        Returns:
            消息列表
        """
        history = self._history.get(conv_id, [])
        return history[-limit:]
    
    def get_client_count(self, conv_id: str) -> int:
        """
        获取客户端数量
        
        Args:
            conv_id: 会话ID
            
        Returns:
            客户端数量
        """
        return len(self._clients.get(conv_id, set()))


class SSEPusher(RealtimePusher):
    """
    SSE (Server-Sent Events) 实时推送器
    
    作为WebSocket的备选方案
    """
    
    def __init__(self):
        # conv_id -> list of response queues
        self._queues: Dict[str, List[asyncio.Queue]] = {}
    
    async def push_part(self, conv_id: str, part: Any):
        """推送Part"""
        if hasattr(part, 'to_vis_dict'):
            part_dict = part.to_vis_dict()
        elif hasattr(part, 'model_dump'):
            part_dict = part.model_dump()
        else:
            part_dict = dict(part)
        
        message = {
            "event": "part_update",
            "data": json.dumps(part_dict, ensure_ascii=False, default=str)
        }
        
        await self._broadcast(conv_id, message)
    
    async def push_event(self, conv_id: str, event_type: str, data: Dict[str, Any]):
        """推送事件"""
        message = {
            "event": event_type,
            "data": json.dumps(data, ensure_ascii=False, default=str)
        }
        
        await self._broadcast(conv_id, message)
    
    async def _broadcast(self, conv_id: str, message: Dict[str, Any]):
        """广播消息"""
        queues = self._queues.get(conv_id, [])
        
        for queue in queues:
            try:
                await queue.put(message)
            except Exception as e:
                logger.debug(f"[SSE] 队列写入失败: {e}")
    
    def add_client(self, conv_id: str, client: Any):
        """添加客户端(创建队列)"""
        if conv_id not in self._queues:
            self._queues[conv_id] = []
        
        # 为每个客户端创建消息队列
        queue = asyncio.Queue()
        client._sse_queue = queue  # 绑定到客户端对象
        self._queues[conv_id].append(queue)
        
        logger.info(f"[SSE] 客户端已连接到会话 {conv_id}")
    
    def remove_client(self, conv_id: str, client: Any):
        """移除客户端"""
        if hasattr(client, '_sse_queue'):
            queue = client._sse_queue
            if conv_id in self._queues and queue in self._queues[conv_id]:
                self._queues[conv_id].remove(queue)
                
                if not self._queues[conv_id]:
                    del self._queues[conv_id]


# 全局推送器实例
_realtime_pusher: Optional[RealtimePusher] = None


def initialize_realtime_pusher(use_sse: bool = False):
    """
    初始化实时推送器
    
    Args:
        use_sse: 是否使用SSE(默认使用WebSocket)
    """
    global _realtime_pusher
    
    if _realtime_pusher is not None:
        logger.info("[Realtime] 推送器已初始化")
        return
    
    if use_sse:
        _realtime_pusher = SSEPusher()
        logger.info("[Realtime] 使用SSE推送器")
    else:
        _realtime_pusher = WebSocketPusher()
        logger.info("[Realtime] 使用WebSocket推送器")


def get_realtime_pusher() -> Optional[RealtimePusher]:
    """获取实时推送器实例"""
    return _realtime_pusher


def create_websocket_endpoint():
    """
    创建WebSocket端点处理器
    
    用于FastAPI集成
    
    Returns:
        WebSocket处理函数
    """
    from fastapi import WebSocket, WebSocketDisconnect
    
    async def websocket_handler(websocket: WebSocket, conv_id: str):
        """
        WebSocket处理函数
        
        Args:
            websocket: WebSocket连接
            conv_id: 会话ID
        """
        await websocket.accept()
        
        pusher = get_realtime_pusher()
        if not pusher:
            await websocket.close(code=1011, reason="Pusher not initialized")
            return
        
        pusher.add_client(conv_id, websocket)
        
        try:
            # 发送历史消息
            history = pusher.get_history(conv_id, limit=50)
            for msg in history:
                await websocket.send_json(msg)
            
            # 保持连接,监听客户端消息
            while True:
                try:
                    data = await websocket.receive_text()
                    # 处理客户端消息(如心跳)
                    if data == "ping":
                        await websocket.send_text("pong")
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"[WS] 接收消息错误: {e}")
                    break
        
        finally:
            pusher.remove_client(conv_id, websocket)
    
    return websocket_handler