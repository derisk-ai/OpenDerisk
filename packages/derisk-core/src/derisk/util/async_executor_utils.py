import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable
import time
from circuitbreaker import circuit

# 配置全局隔离策略
SYSTEM_POOL = ThreadPoolExecutor(max_workers=10)  # 独立线程池


# ============================
# 1. 自定义异常体系
# ============================
logger = logging.getLogger(__name__)


class ServiceException(Exception):
    """服务异常基类"""

    def __init__(self, message, service_name=None):
        super().__init__(message)
        self.service_name = service_name


class ServiceTimeoutError(ServiceException):
    """服务调用超时异常"""

    def __init__(self, service_name, timeout):
        super().__init__(
            f"Service {service_name} timed out after {timeout}s", service_name
        )
        self.timeout = timeout


class SystemGuard:
    """系统防护核心类"""

    def __init__(self):
        self.executor = SYSTEM_POOL

    async def protected_call(
        self, func: Callable, *args, service_name: str = "default", **kwargs
    ) -> Any:
        """执行受保护的操作调用"""
        time_out = kwargs.pop("time_out", 120)

        try:
            return await asyncio.wait_for(
                self._execute_safely(func, *args, **kwargs), timeout=time_out
            )
        except asyncio.TimeoutError:
            logger.warning(f"Service {service_name} timed out ({time_out}s)")
            raise ServiceTimeoutError(service_name, time_out)
        except Exception as e:
            logger.error(f"Service {service_name} error: {str(e)}")
            raise

    async def _execute_safely(self, func: Callable, *args, **kwargs):
        """安全执行函数"""
        loop = asyncio.get_event_loop()

        # 将函数包装为partial对象
        func_call = partial(func, *args, **kwargs)

        # 判断是否协程函数
        if asyncio.iscoroutinefunction(func):
            return await func_call()
        else:
            # 同步函数放入线程池执行
            return await loop.run_in_executor(self.executor, func_call)


# 初始化防护系统
system_guard = SystemGuard()


async def safe_call_tool(func: Callable, *args, **kwargs):
    """受熔断保护的服务调用"""
    return await system_guard.protected_call(
        func, *args, service_name=func.__name__, **kwargs
    )

def async_to_sync(func):
    """
    将异步函数转换为同步函数
    """

    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
            # 如果已经有事件循环（当前在异步环境中）
            if loop.is_running():
                # 在异步环境中，我们需要通过线程安全的方式运行
                return asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop).result()
        except RuntimeError:
            # 检测并处理主线程中没有事件循环的情况（同步方式）
            pass

        # 当前没有事件循环，则创建一个新的事件循环运行
        return run_new_event_loop(func, *args, **kwargs)

    return wrapper

def run_new_event_loop(func, *args, **kwargs):
    """
    在一个新的事件循环中运行异步函数。
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(func(*args, **kwargs))
    finally:
        loop.close()
        asyncio.set_event_loop(None)