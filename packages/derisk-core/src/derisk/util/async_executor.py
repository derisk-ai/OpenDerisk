import asyncio
import concurrent.futures
import functools
import threading
from typing import Any, Callable, Dict, Optional, TypeVar

F = TypeVar('F', bound=Callable[..., Any])


class AsyncExecutorPool:
    """全局线程池管理器"""

    _pools: Dict[str, concurrent.futures.ThreadPoolExecutor] = {}
    _lock = threading.Lock()

    @classmethod
    def get_executor(
        cls,
        max_workers: Optional[int] = None,
        thread_name_prefix: str = "AsyncWorker"
    ) -> concurrent.futures.ThreadPoolExecutor:
        """获取或创建线程池"""
        pool_key = f"{max_workers}_{thread_name_prefix}"

        with cls._lock:
            if pool_key not in cls._pools:
                cls._pools[pool_key] = concurrent.futures.ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix=thread_name_prefix
                )

        return cls._pools[pool_key]

    @classmethod
    def shutdown_all(cls, wait: bool = True):
        """关闭所有线程池"""
        with cls._lock:
            for executor in cls._pools.values():
                executor.shutdown(wait=wait)
            cls._pools.clear()


# 注册清理函数
import atexit

atexit.register(AsyncExecutorPool.shutdown_all)


def to_async(
    max_workers: Optional[int] = None,
    thread_name_prefix: str = "AsyncWorker",
) -> Callable[[F], F]:
    """
    通用装饰器：确保同步函数不阻塞事件循环

    Args:
        max_workers: 线程池最大工作线程数
        thread_name_prefix: 线程名称前缀



    Returns:
        装饰后的函数

    Example:
        @to_async(max_workers=4)
        def slow_database_query(query):
            time.sleep(2)
            return f"Result for {query}"
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # 检测是否在事件循环中运行
                loop = asyncio.get_running_loop()

                # 获取线程池
                executor = AsyncExecutorPool.get_executor(max_workers, thread_name_prefix)

                # 在线程池中执行
                future = executor.submit(func, *args, **kwargs)
                result = future.result()
                return result

            except RuntimeError:
                # 不在事件循环中，直接执行
                result = func(*args, **kwargs)
                return result

        # 添加一些有用的属性
        wrapper._original_func = func
        wrapper._to_async_config = {
            'max_workers': max_workers,
            'thread_name_prefix': thread_name_prefix,
        }

        return wrapper

    return decorator
