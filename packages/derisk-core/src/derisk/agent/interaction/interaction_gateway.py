"""
Interaction Gateway - 交互网关

管理所有交互请求的分发和响应收集
支持 WebSocket 实时通信和 HTTP 同步请求
"""

from typing import Dict, List, Optional, Any, Callable, Awaitable
from datetime import datetime
import asyncio
import json
import logging
from abc import ABC, abstractmethod

from .interaction_protocol import (
    InteractionRequest,
    InteractionResponse,
    InteractionStatus,
    InteractionTimeoutError,
    InteractionCancelledError,
)

logger = logging.getLogger(__name__)


class StateStore(ABC):
    """状态存储抽象接口"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass


class MemoryStateStore(StateStore):
    """内存状态存储"""
    
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)
    
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        self._store[key] = value
        return True
    
    async def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        return key in self._store


class WebSocketManager(ABC):
    """WebSocket 管理器抽象接口"""
    
    @abstractmethod
    async def has_connection(self, session_id: str) -> bool:
        pass
    
    @abstractmethod
    async def send_to_session(self, session_id: str, message: Dict[str, Any]) -> bool:
        pass
    
    @abstractmethod
    async def broadcast(self, message: Dict[str, Any]) -> int:
        pass


class MockWebSocketManager(WebSocketManager):
    """Mock WebSocket 管理器（用于测试）"""
    
    def __init__(self):
        self._connections: Dict[str, bool] = {}
        self._messages: List[Dict[str, Any]] = []
    
    def add_connection(self, session_id: str):
        self._connections[session_id] = True
    
    def remove_connection(self, session_id: str):
        self._connections.pop(session_id, None)
    
    async def has_connection(self, session_id: str) -> bool:
        return self._connections.get(session_id, False)
    
    async def send_to_session(self, session_id: str, message: Dict[str, Any]) -> bool:
        if await self.has_connection(session_id):
            self._messages.append({"session_id": session_id, "message": message})
            logger.info(f"[MockWebSocket] Sent to {session_id}: {message.get('type')}")
            return True
        return False
    
    async def broadcast(self, message: Dict[str, Any]) -> int:
        count = 0
        for session_id in self._connections:
            if await self.send_to_session(session_id, message):
                count += 1
        return count
    
    def get_messages(self) -> List[Dict[str, Any]]:
        return self._messages
    
    def clear_messages(self):
        self._messages.clear()


class UserInputItem:
    """用户主动输入项"""
    
    def __init__(
        self,
        content: str,
        input_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.content = content
        self.input_type = input_type
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
        self.processed = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "input_type": self.input_type,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "processed": self.processed,
        }


class InteractionGateway:
    """
    交互网关
    
    职责：
    1. 接收来自 Agent 的交互请求
    2. 分发到对应的客户端
    3. 收集客户端响应
    4. 协调恢复流程
    5. 管理用户主动输入队列
    """
    
    def __init__(
        self,
        ws_manager: Optional[WebSocketManager] = None,
        state_store: Optional[StateStore] = None,
    ):
        self.ws_manager = ws_manager or MockWebSocketManager()
        self.state_store = state_store or MemoryStateStore()
        
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._request_by_session: Dict[str, List[str]] = {}
        self._response_handlers: Dict[str, Callable] = {}
        
        self._user_input_queue: Dict[str, List[UserInputItem]] = {}
        self._input_event: Dict[str, asyncio.Event] = {}
        
        self._is_connected = False
        self._stats = {
            "requests_sent": 0,
            "responses_received": 0,
            "timeouts": 0,
            "cancelled": 0,
            "user_inputs_received": 0,
            "user_inputs_processed": 0,
        }
    
    def set_connected(self, connected: bool):
        """设置连接状态"""
        self._is_connected = connected
    
    async def send(self, request: InteractionRequest) -> str:
        """发送交互请求"""
        await self.state_store.set(
            f"request:{request.request_id}",
            request.to_dict(),
            ttl=request.timeout + 60 if request.timeout else None
        )
        
        session_id = request.session_id or "default"
        if session_id not in self._request_by_session:
            self._request_by_session[session_id] = []
        self._request_by_session[session_id].append(request.request_id)
        
        has_connection = await self.ws_manager.has_connection(session_id)
        
        if has_connection:
            success = await self.ws_manager.send_to_session(
                session_id=session_id,
                message={
                    "type": "interaction_request",
                    "data": request.to_dict()
                }
            )
            if success:
                self._stats["requests_sent"] += 1
                logger.info(f"[Gateway] Sent request {request.request_id} to session {session_id}")
                return request.request_id
        
        await self._save_pending_request(request)
        logger.info(f"[Gateway] Saved pending request {request.request_id} (offline mode)")
        return request.request_id
    
    async def send_and_wait(
        self,
        request: InteractionRequest,
    ) -> InteractionResponse:
        """发送请求并等待响应"""
        future = asyncio.Future()
        self._pending_requests[request.request_id] = future
        
        await self.send(request)
        
        try:
            response = await asyncio.wait_for(future, timeout=request.timeout or 300)
            self._stats["responses_received"] += 1
            return response
        except asyncio.TimeoutError:
            self._stats["timeouts"] += 1
            return InteractionResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=InteractionStatus.TIMEOUT
            )
        except asyncio.CancelledError:
            self._stats["cancelled"] += 1
            return InteractionResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=InteractionStatus.CANCELLED
            )
        finally:
            self._pending_requests.pop(request.request_id, None)
    
    async def deliver_response(self, response: InteractionResponse):
        """投递响应"""
        request_data = await self.state_store.get(f"request:{response.request_id}")
        if request_data:
            request_data["status"] = response.status
            await self.state_store.set(
                f"request:{response.request_id}",
                request_data
            )
        
        if response.request_id in self._pending_requests:
            future = self._pending_requests.pop(response.request_id)
            if not future.done():
                future.set_result(response)
                logger.info(f"[Gateway] Delivered response for {response.request_id}")
        
        if response.request_id in self._response_handlers:
            handler = self._response_handlers.pop(response.request_id)
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(response)
                else:
                    handler(response)
            except Exception as e:
                logger.error(f"[Gateway] Handler error: {e}")
    
    def register_response_handler(
        self,
        request_id: str,
        handler: Callable[[InteractionResponse], Awaitable[None] | None]
    ):
        """注册响应处理器"""
        self._response_handlers[request_id] = handler
    
    async def get_pending_requests(self, session_id: str) -> List[InteractionRequest]:
        """获取会话的待处理请求"""
        request_ids = self._request_by_session.get(session_id, [])
        requests = []
        for rid in request_ids:
            data = await self.state_store.get(f"request:{rid}")
            if data:
                requests.append(InteractionRequest.from_dict(data))
        return requests
    
    async def cancel_request(self, request_id: str, reason: str = "user_cancel"):
        """取消请求"""
        response = InteractionResponse(
            request_id=request_id,
            status=InteractionStatus.CANCELLED,
            cancel_reason=reason
        )
        await self.deliver_response(response)
    
    async def _save_pending_request(self, request: InteractionRequest):
        """保存待处理请求（离线模式）"""
        pending_key = f"pending:{request.session_id}"
        pending = await self.state_store.get(pending_key) or []
        if isinstance(pending, list):
            pending.append(request.to_dict())
            await self.state_store.set(pending_key, {"items": pending})
    
    async def submit_user_input(
        self,
        session_id: str,
        content: str,
        input_type: str = "text",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        提交用户主动输入
        
        Args:
            session_id: 会话ID
            content: 输入内容
            input_type: 输入类型 (text, file, command等)
            metadata: 额外元数据
            
        Returns:
            str: 输入项ID
        """
        input_item = UserInputItem(
            content=content,
            input_type=input_type,
            metadata=metadata or {},
        )
        
        if session_id not in self._user_input_queue:
            self._user_input_queue[session_id] = []
        
        self._user_input_queue[session_id].append(input_item)
        self._stats["user_inputs_received"] += 1
        
        if session_id in self._input_event:
            self._input_event[session_id].set()
        
        await self.ws_manager.send_to_session(
            session_id,
            {
                "type": "user_input_ack",
                "data": {
                    "received": True,
                    "queue_length": len(self._user_input_queue[session_id]),
                }
            }
        )
        
        logger.info(f"[Gateway] User input submitted for session {session_id}: {content[:50]}...")
        return f"input_{len(self._user_input_queue[session_id])}"
    
    async def get_pending_user_inputs(
        self,
        session_id: str,
        clear: bool = True,
    ) -> List[UserInputItem]:
        """
        获取待处理的用户输入
        
        Args:
            session_id: 会话ID
            clear: 是否清空队列
            
        Returns:
            List[UserInputItem]: 用户输入列表
        """
        inputs = self._user_input_queue.get(session_id, [])
        
        if clear and inputs:
            self._user_input_queue[session_id] = []
            self._stats["user_inputs_processed"] += len(inputs)
        
        return inputs
    
    async def has_pending_user_input(self, session_id: str) -> bool:
        """检查是否有待处理的用户输入"""
        return len(self._user_input_queue.get(session_id, [])) > 0
    
    async def wait_for_user_input(
        self,
        session_id: str,
        timeout: float = 0.1,
    ) -> Optional[UserInputItem]:
        """
        等待用户输入（带超时）
        
        Args:
            session_id: 会话ID
            timeout: 超时时间（秒）
            
        Returns:
            Optional[UserInputItem]: 用户输入项，超时返回None
        """
        if session_id not in self._input_event:
            self._input_event[session_id] = asyncio.Event()
        
        if self._user_input_queue.get(session_id):
            inputs = self._user_input_queue[session_id]
            if inputs:
                return inputs.pop(0)
        
        try:
            await asyncio.wait_for(
                self._input_event[session_id].wait(),
                timeout=timeout
            )
            self._input_event[session_id].clear()
            
            if self._user_input_queue.get(session_id):
                inputs = self._user_input_queue[session_id]
                if inputs:
                    return inputs.pop(0)
        except asyncio.TimeoutError:
            pass
        
        return None
    
    def clear_user_input_queue(self, session_id: str):
        """清空用户输入队列"""
        self._user_input_queue[session_id] = []
        if session_id in self._input_event:
            self._input_event[session_id].clear()

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()


_gateway_instance: Optional[InteractionGateway] = None


def get_interaction_gateway() -> InteractionGateway:
    """获取全局交互网关实例"""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = InteractionGateway()
    return _gateway_instance


def set_interaction_gateway(gateway: InteractionGateway):
    """设置全局交互网关实例"""
    global _gateway_instance
    _gateway_instance = gateway


__all__ = [
    "StateStore",
    "MemoryStateStore",
    "WebSocketManager",
    "MockWebSocketManager",
    "UserInputItem",
    "InteractionGateway",
    "get_interaction_gateway",
    "set_interaction_gateway",
]