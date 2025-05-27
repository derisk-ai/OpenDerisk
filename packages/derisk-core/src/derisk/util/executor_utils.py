import asyncio
import contextvars
import logging
from abc import ABC, abstractmethod
from concurrent.futures import Executor, ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, Union

from derisk.component import BaseComponent, ComponentType, SystemApp


class ExecutorFactory(BaseComponent, ABC):
    name = ComponentType.EXECUTOR_DEFAULT.value

    @abstractmethod
    def create(self) -> "Executor":
        """Create executor"""


class DefaultExecutorFactory(ExecutorFactory):
    def __init__(self, system_app: SystemApp | None = None, max_workers=None):
        super().__init__(system_app)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix=self.name
        )
    def init_app(self, system_app: SystemApp):
        pass

    def create(self) -> Executor:
        return self._executor


BlockingFunction = Callable[..., Any]


async def blocking_func_to_async(
    executor: Executor, func: BlockingFunction, *args, **kwargs
):
    """Run a potentially blocking function within an executor.

    Args:
        executor (Executor): The concurrent.futures.Executor to run the function within.
        func (ApplyFunction): The callable function, which should be a synchronous
            function. It should accept any number and type of arguments and return an
            asynchronous coroutine.
        *args (Any): Any additional arguments to pass to the function.
        **kwargs (Any): Other arguments to pass to the function

    Returns:
        Any: The result of the function's execution.

    Raises:
        ValueError: If the provided function 'func' is an asynchronous coroutine
            function.

    This function allows you to execute a potentially blocking function within an
    executor. It expects 'func' to be a synchronous function and will raise an error
    if 'func' is an asynchronous coroutine.
    """
    if asyncio.iscoroutinefunction(func):
        raise ValueError(f"The function {func} is not blocking function")

    # This function will be called within the new thread, capturing the current context
    ctx = contextvars.copy_context()

    def run_with_context():
        return ctx.run(partial(func, *args, **kwargs))

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, run_with_context)


async def blocking_func_to_async_no_executor(func: BlockingFunction, *args, **kwargs):
    """Run a potentially blocking function within an executor."""
    return await blocking_func_to_async(None, func, *args, **kwargs)  # type: ignore


class AsyncToSyncIterator:
    def __init__(self, async_iterable, loop: asyncio.BaseEventLoop):
        self.async_iterable = async_iterable
        self.async_iterator = None
        self._loop = loop

    def __iter__(self):
        self.async_iterator = self.async_iterable.__aiter__()
        return self

    def __next__(self):
        if self.async_iterator is None:
            raise StopIteration

        try:
            return self._loop.run_until_complete(self.async_iterator.__anext__())
        except StopAsyncIteration:
            raise StopIteration

async def heartbeat_wrapper(data_producer,
                            heartbeat_data: Union[Any, Callable],
                            interval=10):
    """
    向data_producer的输出中添加定时心跳数据

    :param data_producer: 原始的迭代器
    :param heartbeat_data: 心跳数据 注意需要跟原始数据结构保持一致
    :param heartbeat_supplier: 心跳数据 注意需要跟原始数据结构保持一致
    :param interval: 心跳间隔 秒
    :return: 插入了心跳数据的数据序列
    """

    # 创建一个异步队列，用于合并数据流和心跳信号
    queue = asyncio.Queue()
    # 停止标志
    stop_event = asyncio.Event()
    _END_SENTINEL = object()

    async def _data_producer():
        try:
            # 从原始迭代器中获取数据
            async for data in data_producer:
                await queue.put(data)
        except BaseException as e:
            print(f"heartbeat_wrapper _data_producer exception: {repr(e)}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            try:
                await queue.put(_END_SENTINEL)
                stop_event.set()
            except:
                print(f"heartbeat_wrapper _data_producer.final exception: {repr(e)}")
                pass

    async def _heartbeat_producer():
        # 从心跳迭代器中获取数据
        while stop_event is not None and not stop_event.is_set():
            try:
                # 合并心跳间隔和停止检测
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                # 正常心跳周期
                try:
                    _heartbeat_data = heartbeat_data() if isinstance(heartbeat_data, Callable) else heartbeat_data
                    print("heartbeat_wrapper _heartbeat_producer: ", _heartbeat_data)
                    await queue.put(_heartbeat_data) # 发送心跳
                except BaseException:
                    break
                continue
            except BaseException as e:
                print(f"heartbeat_wrapper _heartbeat_producer exception: {repr(e)}")
                break

    data_task = asyncio.create_task(_data_producer())
    heartbeat_task = asyncio.create_task(_heartbeat_producer())

    try:
        while True:
            item = await queue.get()
            if item is _END_SENTINEL:
                break
            yield item
    except BaseException as e:
        print(f"heartbeat_wrapper queue.get exception: {repr(e)}")
        import traceback
        traceback.print_exc()
    finally:
        stop_event.set() # 双重保险
        # data_task.cancel()
        # heartbeat_task.cancel()
        await asyncio.gather(data_task, heartbeat_task, return_exceptions=True)

# if __name__ == "__main__":
#     async def data_producer():
#         for i in range(3):
#             await asyncio.sleep(10)
#             yield i
#
#     async def main():
#         async for data in heartbeat_wrapper(data_producer=data_producer(), heartbeat_data="heartbeat", interval=3):
#             print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), data)
#
#         print("done")
#
#     asyncio.run(main())
