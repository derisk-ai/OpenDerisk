"""
Authorization Cache - Unified Tool Authorization System

This module implements the authorization cache:
- AuthorizationCache: Session-based authorization caching with TTL

Version: 2.0
"""

import time
import hashlib
import json
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with expiration."""
    granted: bool
    timestamp: float
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuthorizationCache:
    """
    Authorization Cache - Session-based caching with TTL.
    
    Caches authorization decisions to avoid repeated user prompts
    for the same tool/argument combinations within a session.
    """
    
    def __init__(self, ttl: int = 3600, max_entries: int = 10000):
        """
        Initialize the cache.
        
        Args:
            ttl: Time-to-live for cache entries in seconds (default: 1 hour)
            max_entries: Maximum number of entries to keep
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "evictions": 0,
        }
    
    @property
    def ttl(self) -> int:
        """Get the TTL in seconds."""
        return self._ttl
    
    @ttl.setter
    def ttl(self, value: int):
        """Set the TTL in seconds."""
        self._ttl = max(0, value)
    
    def get(self, key: str) -> Optional[Tuple[bool, str]]:
        """
        Get a cached authorization decision.
        
        Args:
            key: Cache key
            
        Returns:
            Tuple of (granted, reason) if found and not expired, None otherwise
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            # Check TTL
            age = time.time() - entry.timestamp
            if age > self._ttl:
                # Expired
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            
            self._stats["hits"] += 1
            return (entry.granted, entry.reason)
    
    def set(
        self,
        key: str,
        granted: bool,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Set a cached authorization decision.
        
        Args:
            key: Cache key
            granted: Whether authorization was granted
            reason: Reason for the decision
            metadata: Additional metadata
        """
        with self._lock:
            # Check if we need to evict entries
            if len(self._cache) >= self._max_entries:
                self._evict_oldest()
            
            self._cache[key] = CacheEntry(
                granted=granted,
                timestamp=time.time(),
                reason=reason,
                metadata=metadata or {},
            )
            self._stats["sets"] += 1
    
    def _evict_oldest(self) -> None:
        """Evict the oldest entries to make room."""
        # Remove oldest 10% of entries
        if not self._cache:
            return
        
        entries = list(self._cache.items())
        entries.sort(key=lambda x: x[1].timestamp)
        
        num_to_remove = max(1, len(entries) // 10)
        for key, _ in entries[:num_to_remove]:
            del self._cache[key]
            self._stats["evictions"] += 1
    
    def clear(self, session_id: Optional[str] = None) -> int:
        """
        Clear cache entries.
        
        Args:
            session_id: If provided, only clear entries for this session.
                       If None, clear all entries.
                       
        Returns:
            Number of entries cleared
        """
        with self._lock:
            if session_id is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            
            # Clear only entries matching the session
            keys_to_remove = [
                k for k in self._cache.keys()
                if k.startswith(f"{session_id}:")
            ]
            
            for key in keys_to_remove:
                del self._cache[key]
            
            return len(keys_to_remove)
    
    def has(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        return self.get(key) is not None
    
    def size(self) -> int:
        """Get the number of entries in the cache."""
        with self._lock:
            return len(self._cache)
    
    def stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        with self._lock:
            return dict(self._stats)
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if (current_time - entry.timestamp) > self._ttl
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            return len(expired_keys)
    
    @staticmethod
    def build_cache_key(
        session_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        include_args: bool = True,
    ) -> str:
        """
        Build a cache key for an authorization check.
        
        Args:
            session_id: Session identifier
            tool_name: Name of the tool
            arguments: Tool arguments
            include_args: Whether to include arguments in the key
            
        Returns:
            Cache key string
        """
        if include_args:
            # Hash the arguments for consistent key generation
            args_str = json.dumps(arguments, sort_keys=True, default=str)
            args_hash = hashlib.md5(args_str.encode()).hexdigest()[:16]
            return f"{session_id}:{tool_name}:{args_hash}"
        else:
            # Tool-level caching (ignores arguments)
            return f"{session_id}:{tool_name}:*"


# Global cache instance
_authorization_cache: Optional[AuthorizationCache] = None


def get_authorization_cache() -> AuthorizationCache:
    """Get the global authorization cache instance."""
    global _authorization_cache
    if _authorization_cache is None:
        _authorization_cache = AuthorizationCache()
    return _authorization_cache


def set_authorization_cache(cache: AuthorizationCache) -> None:
    """Set the global authorization cache instance."""
    global _authorization_cache
    _authorization_cache = cache


__all__ = [
    "AuthorizationCache",
    "CacheEntry",
    "get_authorization_cache",
    "set_authorization_cache",
]
