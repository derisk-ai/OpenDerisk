import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Union, AsyncIterator, Optional

from derisk.agent.core.memory.gpts.gpts_memory import ConversationCache
from derisk.context.window import ContextWindow
from derisk.core.interface.scheduler import Scheduler, SchedulePayload, Signal
from derisk.util.date_utils import current_ms
from derisk.util.logger import digest

logger = logging.getLogger("schedule")


class LocalScheduler(Scheduler):
    def __init__(self, queue_size: int = -1, cache: ConversationCache = None):
        super().__init__()
        self._running = False
        self._queue = asyncio.Queue(maxsize=queue_size)
        self._cache = cache

    async def put(self, payload: Union[SchedulePayload, Signal]):
        """添加一个任务"""
        self._running = True
        await self._queue.put(payload)

    async def running(self) -> bool:
        """调度队列是否运行中"""
        return self._running

    async def stop(self):
        """停止调度(放入停止信号)"""
        await self.put(Signal.STOP)

    async def schedule(self):
        """开始调度"""
        while self._running:
            try:
                async with self._queue_item(timeout=1.0) as payload:
                    if payload == Signal.STOP:
                        break
                    elif payload == Signal.EMPTY_STOP:
                        if self._queue.empty():
                            break
                    else:
                        try:
                            agent = self._cache.senders.get(payload.agent_name)
                            await agent.handler(payload.stage)(payload)
                        except Exception as e:
                            logger.exception(f"调度异常, payload={payload}, 异常={repr(e)}")
                            await self.put(Signal.EMPTY_STOP)
                        finally:
                            pass
            except Exception as e:
                logger.exception(f"调度异常: {repr(e)}")
                await self.put(Signal.EMPTY_STOP)
        self._running = False

    @asynccontextmanager
    async def _queue_item(self, timeout=1.0) -> AsyncIterator[Union[SchedulePayload, Signal]]:
        from derisk.util.tracer import root_tracer

        with root_tracer.start_span("agent.schedule", metadata={"succeed": True}) as span:
            succeed = True
            start_ms = current_ms()
            item: Optional[Union[SchedulePayload, Signal]] = None
            has_item = False
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                has_item = True
                yield item
            except (TimeoutError, asyncio.TimeoutError):
                yield Signal.EMPTY_STOP
            except Exception as e:
                succeed = False
                span.metadata["succeed"] = False
                raise
            finally:
                info = {
                    "conv_id": item.conv_id if item and isinstance(item, SchedulePayload) else None,
                    "agent": item.agent_name if item and isinstance(item, SchedulePayload) else None,
                    "stage": item.stage if item and isinstance(item, SchedulePayload) else None,
                    "context_index": item.context_index if item and isinstance(item, SchedulePayload) else None,
                }
                digest(None, "schedule", succeed=succeed, cost_ms=current_ms() - start_ms, **info)
                span.metadata.update(info)
                if has_item:
                    self._queue.task_done()


if __name__ == "__main__":
    async def produce(scheduler: Scheduler):
        for i in range(3):
            await scheduler.put(SchedulePayload(value=f"{i}"))
            await asyncio.sleep(0.5)
        await scheduler.stop()


    async def main():
        scheduler: Scheduler = LocalScheduler()
        asyncio.create_task(produce(scheduler))
        await scheduler.schedule()
        print("done")


    asyncio.run(main())
