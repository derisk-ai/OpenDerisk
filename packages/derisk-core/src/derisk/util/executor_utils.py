import asyncio
import contextvars
import inspect
import logging
from abc import ABC, abstractmethod
from concurrent.futures import Executor
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, Any, List, Optional, Tuple
from typing import Union, Awaitable, Coroutine

from derisk.component import BaseComponent, ComponentType, SystemApp

logger = logging.getLogger(__name__)


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


# 全局默认线程池
_default_executor = None


def default_executor() -> Executor:
    global _default_executor
    if not _default_executor:
        from derisk._private.config import Config
        _default_executor = DefaultExecutorFactory.get_instance(Config().SYSTEM_APP).create()
    return _default_executor


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


async def run_async_tasks(
    tasks: List[Coroutine],
    concurrency_limit: int = None,
) -> List[Any]:
    """Run a list of async tasks."""
    tasks_to_execute: List[Any] = tasks

    async def _gather() -> List[Any]:
        if concurrency_limit:
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def _execute_task(task):
                async with semaphore:
                    return await task

            # Execute tasks with semaphore limit
            return await asyncio.gather(
                *[_execute_task(task) for task in tasks_to_execute]
            )
        else:
            return await asyncio.gather(*tasks_to_execute)

    # outputs: List[Any] = asyncio.run(_gather())
    return await _gather()


def run_tasks(
    tasks: List[Callable],
    concurrency_limit: int = None,
) -> List[Any]:
    """
    Run a list of tasks concurrently using a thread pool.

    Args:
        tasks: List of callable functions to execute
        concurrency_limit: Maximum number of concurrent threads (optional)

    Returns:
        List of results from all tasks in the order they were submitted
    """
    max_workers = concurrency_limit if concurrency_limit else None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks and get futures
        futures = [executor.submit(task) for task in tasks]

        # Collect results in order, raising any exceptions
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as e:
                # Cancel any pending futures
                for f in futures:
                    f.cancel()
                raise e

    return results


# def execute_parallel_sync(funcs_and_params):
#     """
#     并行运行多个函数。
#     参数:
#         funcs_and_params: 列表，每项写成 (函数名, 参数1, 参数2, ...)
#     返回:
#         各函数的返回结果列表，顺序与输入一致
#
#     样例:
#         def add(a, b):
#             return a + b
#
#         def hello(name):
#             return f"Hello, {name}!"
#
#         results = run_parallel([
#             (add, 3, 5),           # add(3, 5)
#             (hello, "Alice"),      # hello("Alice")
#             (max, 1, 2, 7, 4, 0)   # max(1, 2, 7, 4, 0)
#         ])
#         print(results)
#         # 输出: [8, 'Hello, Alice!', 7]
#     """
#     with concurrent.futures.ThreadPoolExecutor() as executor:
#         futures = [executor.submit(item[0], *item[1:]) for item in funcs_and_params]
#         return [f.result() for f in futures]


def execute_no_wait(
    func: Union[Callable, Callable[..., Awaitable]],
    *args,
    executor: Executor = None,
    callback: Optional[Callable[[Any], None]] = None,
    error_callback: Optional[Callable[[Exception], None]] = None,
    **kwargs
):
    """
    在后台执行函数，fire and forget

    Args:
        func: 要执行的函数（同步或异步）
        executor: 线程池
        *args: 函数的位置参数
        callback: 成功时的回调函数（可选）
        error_callback: 失败时的回调函数（可选）
        **kwargs: 函数的关键字参数
    """

    async def _execute_function(func, args, kwargs, callback, error_callback):
        """内部执行函数的方法"""
        try:
            # 执行函数
            if asyncio.iscoroutinefunction(func):
                # 异步函数直接执行
                result = await func(*args, **kwargs)
            else:
                # 同步函数在executor中执行
                ctx = contextvars.copy_context()

                def run_with_context():
                    return ctx.run(partial(func, *args, **kwargs))

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(executor, run_with_context)

            # 执行成功回调
            if callback:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)

        except Exception as e:
            logger.exception(f"execute_no_wait exception: {func}: {repr(e)}")
            # 执行错误回调
            if error_callback:
                try:
                    if asyncio.iscoroutinefunction(error_callback):
                        await error_callback(e)
                    else:
                        error_callback(e)
                except:
                    pass  # 忽略回调函数的异常

    asyncio.create_task(
        _execute_function(func, args, kwargs, callback, error_callback)
    )


class Task:
    """任务包装类"""

    def __init__(self, func: Callable, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def execute(self):
        """执行任务"""
        result = self.func(*self.args, **self.kwargs)

        # 如果返回的是协程，在新事件循环中执行
        if inspect.iscoroutine(result):
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(result)
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)

        return result


def t(func: Callable, *args, **kwargs) -> Tuple:
    """
    创建任务的辅助函数

    Args:
        func: 要执行的函数
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        (func, args, kwargs) 元组

    Examples:
        execute_to_thread(
            t(sync_task, "arg1", prefix="Hi"),
            t(async_task, name="test", suffix="!!!")
        )
    """
    return (func, args, kwargs)


def execute_to_thread(
    *task_definitions: Tuple[Callable, tuple, dict],
    executor: Optional[ThreadPoolExecutor] = None,
    wait: bool = True
) -> List[Any]:
    """
    将任务提交到线程池中执行（同步调用方使用，!!等待结果时会阻塞当前线程!!）

    适用场景：
    - 避免同步阻塞操作（如 time.sleep、requests 等）阻塞主线程
    - 并行执行多个耗时任务
    - 在异步环境中调用也可以，但推荐使用 execute_to_loop

    Args:
        *task_definitions: 任务定义，使用 t() 函数创建
        executor: 自定义线程池执行器，默认使用全局执行器
        wait: 是否等待执行结果
             - True: 等待所有任务完成并返回结果列表
             - False: 立即返回 None 列表，任务在后台执行

    Returns:
        如果 wait=True，返回所有任务的执行结果列表
        如果 wait=False，返回 None 列表

    Examples:
        # 等待结果（并行执行）
        results = execute_to_thread(
            t(sync_task, "arg1", prefix="Hi"),
            t(async_task, name="test", suffix="!!!")
        )
        # 输出: ["Hi with sync: arg1", "Hello with async: test!!!"]

        # 不等待结果（火忘模式）
        execute_to_thread(
            t(log_task, "fire and forget"),
            wait=False
        )
        # 立即返回，任务在后台执行
    """
    if executor is None:
        executor = default_executor()

    # 解析并创建任务
    tasks = []
    for task_def in task_definitions:
        if not isinstance(task_def, tuple) or len(task_def) < 1:
            raise ValueError(f"Invalid task format: {task_def}. Use t() function to create tasks.")

        func = task_def[0]
        args = task_def[1] if len(task_def) > 1 else ()
        kwargs = task_def[2] if len(task_def) > 2 else {}

        if not isinstance(args, tuple):
            raise ValueError(f"Args must be a tuple, got {type(args)}: {args}")
        if not isinstance(kwargs, dict):
            raise ValueError(f"Kwargs must be a dict, got {type(kwargs)}: {kwargs}")

        tasks.append(Task(func, *args, **kwargs))

    # 提交所有任务到线程池
    futures = []
    for task in tasks:
        future = executor.submit(task.execute)
        futures.append(future)

    # 根据 wait 参数决定是否等待
    if not wait:
        return []

    return [f.result() for f in futures]


async def execute_to_coro(
    *task_definitions: Tuple[Callable, tuple, dict],
    executor: Optional[ThreadPoolExecutor] = None,
    wait: bool = True
) -> List[Any]:
    """
    将任务提交到线程池中以协程方式执行（异步调用方使用）

    与 execute_to_thread 的区别：
    - 使用 asyncio 的事件循环调度，不阻塞当前协程
    - 适合在 async 函数中使用
    - 可以与其他协程并发执行

    适用场景：
    - 在 async 函数中执行阻塞操作（如 time.sleep、requests 等）
    - 需要并行执行多个耗时任务，同时不阻塞事件循环

    Args:
        *task_definitions: 任务定义，使用 t() 函数创建
        executor: 自定义线程池执行器，默认使用全局执行器
        wait: 是否等待执行结果
             - True: 异步等待所有任务完成并返回结果列表
             - False: 立即返回 None 列表，任务在后台执行

    Returns:
        如果 wait=True，返回所有任务的执行结果列表
        如果 wait=False，返回 None 列表

    Examples:
        # 在 async 函数中使用（推荐）
        async def async_caller():
            results = await execute_to_loop(
                t(sync_task, "arg1", prefix="Hi"),
                t(async_task, name="test", suffix="!!!")
            )
            return results

        # 不等待结果
        async def fire_and_forget():
            await execute_to_loop(
                t(log_task, "background task"),
                wait=False
            )
            # 立即返回，任务在后台执行
    """
    if executor is None:
        executor = default_executor()

    loop = asyncio.get_running_loop()

    # 解析并创建任务
    tasks = []
    for task_def in task_definitions:
        if not isinstance(task_def, tuple) or len(task_def) < 1:
            raise ValueError(f"Invalid task format: {task_def}. Use t() function to create tasks.")

        func = task_def[0]
        args = task_def[1] if len(task_def) > 1 else ()
        kwargs = task_def[2] if len(task_def) > 2 else {}

        if not isinstance(args, tuple):
            raise ValueError(f"Args must be a tuple, got {type(args)}: {args}")
        if not isinstance(kwargs, dict):
            raise ValueError(f"Kwargs must be a dict, got {type(kwargs)}: {kwargs}")

        tasks.append(Task(func, *args, **kwargs))

    # 提交所有任务到线程池
    futures = []
    for task in tasks:
        future = loop.run_in_executor(executor, task.execute)
        futures.append(future)

    # 根据 wait 参数决定是否等待
    if not wait:
        return []

    return await asyncio.gather(*futures)


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


async def heartbeat_wrapper(
    data_producer, heartbeat_data: Union[Any, Callable], interval=10
):
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
                    _heartbeat_data = (
                        heartbeat_data()
                        if isinstance(heartbeat_data, Callable)
                        else heartbeat_data
                    )
                    print("heartbeat_wrapper _heartbeat_producer: ", _heartbeat_data)
                    await queue.put(_heartbeat_data)  # 发送心跳
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
        stop_event.set()  # 双重保险
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
