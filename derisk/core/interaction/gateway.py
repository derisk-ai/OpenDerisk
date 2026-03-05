"""
Interaction Gateway - Unified Tool Authorization System

This module implements the interaction gateway:
- ConnectionManager: Abstract connection management
- StateStore: Abstract state storage
- InteractionGateway: Main gateway for sending/receiving interactions

Version: 2.0
"""

import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, Awaitable
from dataclasses import dataclass, field
import threading
from datetime import datetime

from .protocol import (
    InteractionRequest,
    InteractionResponse,
    InteractionStatus,
    InteractionType,
)

logger = logging.getLogger(__name__)


class ConnectionManager(ABC):
    """
    Abstract base class for connection management.
    
    Implementations handle the actual transport (WebSocket, HTTP, etc.)
    """
    
    @abstractmethod
    async def has_connection(self, session_id: str) -> bool:
        """Check if a session has an active connection."""
        pass
    
    @abstractmethod
    async def send(self, session_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific session.
        
        Args:
            session_id: Target session ID
            message: Message to send
            
        Returns:
            True if sent successfully
        """
        pass
    
    @abstractmethod
    async def broadcast(self, message: Dict[str, Any]) -> int:
        """
        Broadcast a message to all connected sessions.
        
        Args:
            message: Message to broadcast
            
        Returns:
            Number of sessions that received the message
        """
        pass


class MemoryConnectionManager(ConnectionManager):
    """
    In-memory connection manager for testing and simple deployments.
    
    Uses callbacks to simulate sending messages.
    """
    
    def __init__(self):
        self._connections: Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]] = {}
        self._lock = threading.Lock()
    
    def add_connection(
        self,
        session_id: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Add a connection for a session."""
        with self._lock:
            self._connections[session_id] = callback
    
    def remove_connection(self, session_id: str) -> bool:
        """Remove a connection for a session."""
        with self._lock:
            if session_id in self._connections:
                del self._connections[session_id]
                return True
            return False
    
    async def has_connection(self, session_id: str) -> bool:
        """Check if a session has an active connection."""
        with self._lock:
            return session_id in self._connections
    
    async def send(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Send a message to a specific session."""
        with self._lock:
            callback = self._connections.get(session_id)
        
        if callback:
            try:
                await callback(message)
                return True
            except Exception as e:
                logger.error(f"Failed to send to {session_id}: {e}")
                return False
        return False
    
    async def broadcast(self, message: Dict[str, Any]) -> int:
        """Broadcast a message to all connected sessions."""
        with self._lock:
            connections = list(self._connections.items())
        
        sent = 0
        for session_id, callback in connections:
            try:
                await callback(message)
                sent += 1
            except Exception as e:
                logger.error(f"Failed to broadcast to {session_id}: {e}")
        
        return sent
    
    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        with self._lock:
            return len(self._connections)


class StateStore(ABC):
    """
    Abstract base class for state storage.
    
    Implementations can use memory, Redis, database, etc.
    """
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a value from the store."""
        pass
    
    @abstractmethod
    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set a value in the store.
        
        Args:
            key: Storage key
            value: Value to store
            ttl: Time-to-live in seconds
            
        Returns:
            True if stored successfully
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value from the store."""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the store."""
        pass


class MemoryStateStore(StateStore):
    """
    In-memory state store for testing and simple deployments.
    """
    
    def __init__(self):
        self._store: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self._lock = threading.Lock()
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a value from the store."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            
            value, expiry = entry
            if expiry and time.time() > expiry:
                del self._store[key]
                return None
            
            return value
    
    async def set(
        self,
        key: str,
        value: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in the store."""
        with self._lock:
            expiry = time.time() + ttl if ttl else None
            self._store[key] = (value, expiry)
            return True
    
    async def delete(self, key: str) -> bool:
        """Delete a value from the store."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the store."""
        return await self.get(key) is not None
    
    def size(self) -> int:
        """Get the number of entries in the store."""
        with self._lock:
            return len(self._store)
    
    def cleanup_expired(self) -> int:
        """Remove expired entries."""
        with self._lock:
            current_time = time.time()
            expired = [
                k for k, (v, exp) in self._store.items()
                if exp and current_time > exp
            ]
            for key in expired:
                del self._store[key]
            return len(expired)


@dataclass
class PendingRequest:
    """A pending interaction request."""
    request: InteractionRequest
    future: asyncio.Future
    created_at: float = field(default_factory=time.time)
    timeout: Optional[float] = None
    
    @property
    def is_expired(self) -> bool:
        """Check if the request has expired."""
        if self.timeout is None:
            return False
        return time.time() - self.created_at > self.timeout


class InteractionGateway:
    """
    Interaction Gateway - Central hub for user interactions.
    
    Manages:
    - Sending interaction requests to users
    - Receiving responses from users
    - Request/response correlation
    - Timeouts and cancellation
    """
    
    def __init__(
        self,
        connection_manager: Optional[ConnectionManager] = None,
        state_store: Optional[StateStore] = None,
        default_timeout: int = 300,
    ):
        """
        Initialize the interaction gateway.
        
        Args:
            connection_manager: Connection manager for sending messages
            state_store: State store for persisting requests
            default_timeout: Default request timeout in seconds
        """
        self._connection_manager = connection_manager or MemoryConnectionManager()
        self._state_store = state_store or MemoryStateStore()
        self._default_timeout = default_timeout
        
        # Pending request tracking
        self._pending_requests: Dict[str, PendingRequest] = {}
        self._session_requests: Dict[str, List[str]] = {}  # session -> request_ids
        self._lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "requests_sent": 0,
            "responses_received": 0,
            "timeouts": 0,
            "cancellations": 0,
        }
    
    @property
    def connection_manager(self) -> ConnectionManager:
        """Get the connection manager."""
        return self._connection_manager
    
    @property
    def state_store(self) -> StateStore:
        """Get the state store."""
        return self._state_store
    
    @property
    def stats(self) -> Dict[str, int]:
        """Get gateway statistics."""
        with self._lock:
            return dict(self._stats)
    
    async def send(
        self,
        request: InteractionRequest,
        wait_response: bool = False,
        timeout: Optional[int] = None,
    ) -> Optional[InteractionResponse]:
        """
        Send an interaction request to the user.
        
        Args:
            request: The interaction request
            wait_response: Whether to wait for a response
            timeout: Request timeout in seconds
            
        Returns:
            InteractionResponse if wait_response=True and response received,
            None otherwise
        """
        if wait_response:
            return await self.send_and_wait(request, timeout)
        
        # Fire and forget
        await self._send_request(request)
        return None
    
    async def send_and_wait(
        self,
        request: InteractionRequest,
        timeout: Optional[int] = None,
    ) -> InteractionResponse:
        """
        Send a request and wait for the response.
        
        Args:
            request: The interaction request
            timeout: Request timeout in seconds (uses default if not provided)
            
        Returns:
            The user's response
            
        Raises:
            asyncio.TimeoutError: If the request times out
            asyncio.CancelledError: If the request is cancelled
        """
        effective_timeout = timeout or request.timeout or self._default_timeout
        
        # Create future for response
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        # Track the pending request
        pending = PendingRequest(
            request=request,
            future=future,
            timeout=effective_timeout,
        )
        
        with self._lock:
            self._pending_requests[request.request_id] = pending
            
            # Track by session
            session_id = request.session_id or "default"
            if session_id not in self._session_requests:
                self._session_requests[session_id] = []
            self._session_requests[session_id].append(request.request_id)
        
        try:
            # Send the request
            await self._send_request(request)
            
            # Wait for response with timeout
            if effective_timeout > 0:
                response = await asyncio.wait_for(future, timeout=effective_timeout)
            else:
                response = await future
            
            return response
            
        except asyncio.TimeoutError:
            with self._lock:
                self._stats["timeouts"] += 1
            
            # Create timeout response
            return InteractionResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=InteractionStatus.EXPIRED,
                cancel_reason="Request timed out",
            )
            
        finally:
            # Cleanup
            with self._lock:
                self._pending_requests.pop(request.request_id, None)
                
                session_id = request.session_id or "default"
                if session_id in self._session_requests:
                    try:
                        self._session_requests[session_id].remove(request.request_id)
                    except ValueError:
                        pass
    
    async def _send_request(self, request: InteractionRequest) -> bool:
        """Internal method to send a request via the connection manager."""
        session_id = request.session_id or "default"
        
        # Store request state
        await self._state_store.set(
            f"request:{request.request_id}",
            request.to_dict(),
            ttl=request.timeout or self._default_timeout,
        )
        
        # Build message
        message = {
            "type": "interaction_request",
            "request": request.to_dict(),
            "timestamp": datetime.now().isoformat(),
        }
        
        # Send via connection manager
        sent = await self._connection_manager.send(session_id, message)
        
        if sent:
            with self._lock:
                self._stats["requests_sent"] += 1
        else:
            logger.warning(f"No connection for session {session_id}")
        
        return sent
    
    async def deliver_response(self, response: InteractionResponse) -> bool:
        """
        Deliver a response to a pending request.
        
        Called when a user responds to an interaction request.
        
        Args:
            response: The user's response
            
        Returns:
            True if response was delivered to a pending request
        """
        request_id = response.request_id
        
        with self._lock:
            pending = self._pending_requests.get(request_id)
            self._stats["responses_received"] += 1
        
        if pending and not pending.future.done():
            pending.future.set_result(response)
            
            # Store response state
            await self._state_store.set(
                f"response:{request_id}",
                response.to_dict(),
                ttl=3600,  # Keep responses for 1 hour
            )
            
            return True
        
        # No pending request found - might be for a fire-and-forget request
        # Store the response anyway
        await self._state_store.set(
            f"response:{request_id}",
            response.to_dict(),
            ttl=3600,
        )
        
        return False
    
    def get_pending_requests(
        self,
        session_id: Optional[str] = None,
    ) -> List[InteractionRequest]:
        """
        Get pending requests, optionally filtered by session.
        
        Args:
            session_id: Filter by session ID
            
        Returns:
            List of pending interaction requests
        """
        with self._lock:
            if session_id:
                request_ids = self._session_requests.get(session_id, [])
                return [
                    self._pending_requests[rid].request
                    for rid in request_ids
                    if rid in self._pending_requests
                ]
            else:
                return [p.request for p in self._pending_requests.values()]
    
    def get_pending_request(self, request_id: str) -> Optional[InteractionRequest]:
        """Get a specific pending request."""
        with self._lock:
            pending = self._pending_requests.get(request_id)
            return pending.request if pending else None
    
    async def cancel_request(
        self,
        request_id: str,
        reason: str = "Cancelled by user",
    ) -> bool:
        """
        Cancel a pending request.
        
        Args:
            request_id: Request ID to cancel
            reason: Cancellation reason
            
        Returns:
            True if request was cancelled
        """
        with self._lock:
            pending = self._pending_requests.get(request_id)
            self._stats["cancellations"] += 1
        
        if pending and not pending.future.done():
            # Create cancellation response
            response = InteractionResponse(
                request_id=request_id,
                session_id=pending.request.session_id,
                status=InteractionStatus.CANCELLED,
                cancel_reason=reason,
            )
            
            pending.future.set_result(response)
            
            # Cleanup
            with self._lock:
                self._pending_requests.pop(request_id, None)
            
            await self._state_store.delete(f"request:{request_id}")
            
            return True
        
        return False
    
    async def cancel_session_requests(
        self,
        session_id: str,
        reason: str = "Session ended",
    ) -> int:
        """
        Cancel all pending requests for a session.
        
        Args:
            session_id: Session ID
            reason: Cancellation reason
            
        Returns:
            Number of requests cancelled
        """
        with self._lock:
            request_ids = list(self._session_requests.get(session_id, []))
        
        cancelled = 0
        for request_id in request_ids:
            if await self.cancel_request(request_id, reason):
                cancelled += 1
        
        return cancelled
    
    def pending_count(self, session_id: Optional[str] = None) -> int:
        """Get the number of pending requests."""
        with self._lock:
            if session_id:
                return len(self._session_requests.get(session_id, []))
            return len(self._pending_requests)
    
    async def cleanup_expired(self) -> int:
        """
        Cleanup expired pending requests.
        
        Returns:
            Number of requests cleaned up
        """
        with self._lock:
            expired_ids = [
                rid for rid, pending in self._pending_requests.items()
                if pending.is_expired
            ]
        
        cleaned = 0
        for request_id in expired_ids:
            await self.cancel_request(request_id, "Request expired")
            cleaned += 1
        
        return cleaned


# Global gateway instance
_gateway_instance: Optional[InteractionGateway] = None


def get_interaction_gateway() -> InteractionGateway:
    """Get the global interaction gateway instance."""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = InteractionGateway()
    return _gateway_instance


def set_interaction_gateway(gateway: InteractionGateway) -> None:
    """Set the global interaction gateway instance."""
    global _gateway_instance
    _gateway_instance = gateway


async def send_interaction(
    request: InteractionRequest,
    wait_response: bool = True,
    timeout: Optional[int] = None,
) -> Optional[InteractionResponse]:
    """
    Convenience function to send an interaction request.
    
    Args:
        request: The interaction request
        wait_response: Whether to wait for a response
        timeout: Request timeout in seconds
        
    Returns:
        InteractionResponse if wait_response=True, None otherwise
    """
    gateway = get_interaction_gateway()
    return await gateway.send(request, wait_response, timeout)


async def deliver_response(response: InteractionResponse) -> bool:
    """
    Convenience function to deliver a response.
    
    Args:
        response: The user's response
        
    Returns:
        True if delivered successfully
    """
    gateway = get_interaction_gateway()
    return await gateway.deliver_response(response)


__all__ = [
    "ConnectionManager",
    "MemoryConnectionManager",
    "StateStore",
    "MemoryStateStore",
    "PendingRequest",
    "InteractionGateway",
    "get_interaction_gateway",
    "set_interaction_gateway",
    "send_interaction",
    "deliver_response",
]
