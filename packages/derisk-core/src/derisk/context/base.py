import asyncio
import contextvars
import logging
import threading
from collections import deque
from typing import Optional, Any

logger = logging.getLogger("context")


class ContextWindow:
    _thread_local = threading.local()
    _async_local: contextvars.ContextVar = contextvars.ContextVar("current_context_stack", default=None)

    _ctx: Any = {}  # 仅初始化新上下文窗口时使用

    def __init__(self, ctx: dict = None):
        self._ctx = ctx if ctx is not None else {}

    def __enter__(self):
        ContextWindow.enter(self._ctx)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ContextWindow.exit()

    @classmethod
    def enter(cls, context: dict[str, Any]) -> None:
        """Enter a context window.

        Args:
            context : The context window to enter
        """
        is_async = _is_async_context()
        if is_async:
            stack = cls._get_async_stack()
            stack.append(context)
            logger.info(f"context window, enter --> [{len(stack)}]")
            cls._async_local.set(stack)
        else:
            if not hasattr(cls._thread_local, "current_context_stack"):
                cls._thread_local.current_context_stack = deque()
            cls._thread_local.current_context_stack.append(context)
            logger.info(f"context window, enter --> [{len(cls._thread_local.current_context_stack)}]")

    @classmethod
    def exit(cls) -> None:
        """Exit a context window."""
        is_async = _is_async_context()
        if is_async:
            stack = cls._get_async_stack()
            if stack:
                stack.pop()
                logger.info(f"context window, out --> [{len(stack)}]")
                cls._async_local.set(stack)
        else:
            if (
                hasattr(cls._thread_local, "current_context_stack")
                and cls._thread_local.current_context_stack
            ):
                cls._thread_local.current_context_stack.pop()
                logger.info(f"context window, out --> [{len(cls._thread_local.current_context_stack)}]")

    @classmethod
    def get_current(cls) -> Optional[dict]:
        """Get the current context window.

        Returns:
            Optional[dict]: The current context window
        """
        is_async = _is_async_context()
        if is_async:
            stack = cls._get_async_stack()
            return stack[-1] if stack else None
        else:
            if (
                hasattr(cls._thread_local, "current_context_stack")
                and cls._thread_local.current_context_stack
            ):
                return cls._thread_local.current_context_stack[-1]
            return None

    @classmethod
    def _get_async_stack(cls):
        """获取异步上下文栈，如果不存在则创建新的"""
        stack = cls._async_local.get()
        if stack is None:
            stack = deque()
            cls._async_local.set(stack)
        return stack


def _is_async_context():
    try:
        loop = asyncio.get_running_loop()
        return asyncio.current_task(loop=loop) is not None
    except RuntimeError:
        return False
