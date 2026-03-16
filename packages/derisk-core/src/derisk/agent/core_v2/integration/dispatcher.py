"""
V2AgentDispatcher - Agent 调度器

统一的消息分发和 Agent 调度
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Type, Union

from .adapter import V2Adapter, V2StreamChunk
from .runtime import SessionContext, V2AgentRuntime, RuntimeConfig

logger = logging.getLogger(__name__)


# 用于同步会话到 chat_history 表
async def sync_session_to_chat_history(
    conv_id: str,
    user_id: Optional[str],
    agent_name: str,
    summary: str = "New Conversation",
):
    """将会话信息同步到 chat_history 表"""
    try:
        from derisk.storage.chat_history.chat_history_db import (
            ChatHistoryDao,
            ChatHistoryEntity,
        )

        chat_history_dao = ChatHistoryDao()
        entity = ChatHistoryEntity(
            conv_uid=conv_id,
            chat_mode="chat_agent",
            summary=summary,
            user_name=user_id,
            app_code=agent_name,
        )
        chat_history_dao.raw_update(entity)
        logger.info(f"[Dispatcher] Created chat_history record for conv_id: {conv_id}")
    except Exception as e:
        logger.warning(f"[Dispatcher] Failed to create chat_history record: {e}")


class DispatchPriority(int, Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass
class DispatchTask:
    task_id: str
    session_id: str
    message: str
    priority: DispatchPriority = DispatchPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    multimodal_contents: Optional[List[Dict[str, Any]]] = None
    sandbox_file_refs: Optional[List[Any]] = None


class V2AgentDispatcher:
    """
    V2 Agent 调度器

    核心功能:
    1. 消息队列管理
    2. Agent 调度执行
    3. 流式响应处理
    4. 与前端通信集成
    """

    def __init__(
        self,
        runtime: V2AgentRuntime = None,
        adapter: V2Adapter = None,
        max_workers: int = 10,
    ):
        self.runtime = runtime or V2AgentRuntime()
        self.adapter = adapter or V2Adapter()
        self.max_workers = max_workers

        self._task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._task_results: Dict[str, Any] = {}
        self._workers: List[asyncio.Task] = []
        self._running = False

        self._on_task_start: Optional[Callable] = None
        self._on_task_complete: Optional[Callable] = None
        self._on_stream_chunk: Optional[Callable] = None

    def on_task_start(self, handler: Callable):
        self._on_task_start = handler

    def on_task_complete(self, handler: Callable):
        self._on_task_complete = handler

    def on_stream_chunk(self, handler: Callable):
        self._on_stream_chunk = handler

    async def start(self):
        if self._running:
            return

        self._running = True
        await self.runtime.start()

        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)

        logger.info(f"[Dispatcher] 启动 {self.max_workers} 个工作线程")

    async def stop(self):
        self._running = False

        for worker in self._workers:
            worker.cancel()

        self._workers.clear()

        for task_id, task in self._active_tasks.items():
            task.cancel()

        self._active_tasks.clear()

        await self.runtime.stop()
        logger.info("[Dispatcher] 调度器已停止")

    async def dispatch(
        self,
        message: str,
        session_id: Optional[str] = None,
        conv_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: str = "primary",
        priority: DispatchPriority = DispatchPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
        result_queue: Optional[asyncio.Queue] = None,
        multimodal_contents: Optional[List[Dict[str, Any]]] = None,
        sandbox_file_refs: Optional[List[Any]] = None,
    ) -> str:
        new_session_created = False
        if session_id:
            existing = await self.runtime.get_session(session_id)
            if not existing:
                session_context = await self.runtime.create_session(
                    session_id=session_id,
                    conv_id=conv_id or session_id,
                    user_id=user_id,
                    agent_name=agent_name,
                    metadata=metadata,
                )
                session_id = session_context.session_id
                new_session_created = True
        else:
            session_context = await self.runtime.create_session(
                conv_id=conv_id,
                user_id=user_id,
                agent_name=agent_name,
                metadata=metadata,
            )
            session_id = session_context.session_id
            new_session_created = True

        if new_session_created:
            await sync_session_to_chat_history(
                conv_id=conv_id or session_id,
                user_id=user_id,
                agent_name=agent_name,
                summary=message[:100] if message else "New Conversation",
            )

        task = DispatchTask(
            task_id=str(uuid.uuid4().hex),
            session_id=session_id,
            message=message,
            priority=priority,
            metadata=metadata or {},
            multimodal_contents=multimodal_contents,
            sandbox_file_refs=sandbox_file_refs,
        )

        if result_queue:
            self._task_results[task.task_id] = result_queue

        await self._task_queue.put((priority.value, datetime.now().timestamp(), task))

        logger.info(f"[Dispatcher] 任务已入队: {task.task_id[:8]}")
        return task.task_id

    async def dispatch_and_wait(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[V2StreamChunk]:
        import sys

        result_queue = asyncio.Queue()

        task_id = await self.dispatch(
            message=message, session_id=session_id, result_queue=result_queue, **kwargs
        )
        print(
            f"[dispatch_and_wait] task_id={task_id[:8]}, queue registered",
            file=sys.stderr,
            flush=True,
        )

        print(f"[dispatch_and_wait] waiting for chunks...", file=sys.stderr, flush=True)
        chunk_count = 0
        while True:
            chunk = await result_queue.get()
            if chunk is None:
                print(
                    f"[dispatch_and_wait] got None, breaking. Total chunks: {chunk_count}",
                    file=sys.stderr,
                    flush=True,
                )
                break
            chunk_count += 1
            print(
                f"[dispatch_and_wait] yielding chunk #{chunk_count}: type={chunk.type}",
                file=sys.stderr,
                flush=True,
            )
            yield chunk
            if chunk.is_final:
                print(
                    f"[dispatch_and_wait] chunk is final, breaking",
                    file=sys.stderr,
                    flush=True,
                )
                break

    async def _worker_loop(self, worker_id: int):
        logger.info(f"[Worker-{worker_id}] 启动")

        while self._running:
            try:
                logger.debug(f"[Worker-{worker_id}] 等待任务...")
                priority, timestamp, task = await asyncio.wait_for(
                    self._task_queue.get(), timeout=1.0
                )

                logger.info(f"[Worker-{worker_id}] 收到任务: {task.task_id[:8]}")
                task.started_at = datetime.now()

                import sys

                print(
                    f"[Worker-{worker_id}] task_id={task.task_id[:8]}, in _task_results: {task.task_id in self._task_results}",
                    file=sys.stderr,
                    flush=True,
                )
                print(
                    f"[Worker-{worker_id}] _task_results keys: {[k[:8] for k in self._task_results.keys()]}",
                    file=sys.stderr,
                    flush=True,
                )

                if self._on_task_start:
                    await self._safe_call(self._on_task_start, task)

                chunk_count = 0
                async for chunk in self.runtime.execute(
                    task.session_id,
                    task.message,
                    multimodal_contents=task.multimodal_contents,
                    sandbox_file_refs=task.sandbox_file_refs,
                ):
                    chunk_count += 1
                    print(
                        f"[Worker-{worker_id}] chunk #{chunk_count}: type={chunk.type}, content={chunk.content[:50] if chunk.content else 'N/A'}",
                        file=sys.stderr,
                        flush=True,
                    )
                    if task.task_id in self._task_results:
                        await self._task_results[task.task_id].put(chunk)
                        print(
                            f"[Worker-{worker_id}] put chunk to queue",
                            file=sys.stderr,
                            flush=True,
                        )
                    else:
                        print(
                            f"[Worker-{worker_id}] WARNING: task_id not in _task_results!",
                            file=sys.stderr,
                            flush=True,
                        )

                    if self._on_stream_chunk:
                        await self._safe_call(self._on_stream_chunk, task, chunk)

                print(
                    f"[Worker-{worker_id}] Total chunks: {chunk_count}",
                    file=sys.stderr,
                    flush=True,
                )

                task.completed_at = datetime.now()
                logger.info(f"[Worker-{worker_id}] 任务完成: {task.task_id[:8]}")

                if task.task_id in self._task_results:
                    await self._task_results[task.task_id].put(None)
                    del self._task_results[task.task_id]

                if self._on_task_complete:
                    await self._safe_call(self._on_task_complete, task, None)

                self._task_queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"[Worker-{worker_id}] 错误: {e}")
                if self._on_task_complete:
                    await self._safe_call(self._on_task_complete, task, e)

        logger.info(f"[Worker-{worker_id}] 停止")

    async def _safe_call(self, func: Callable, *args):
        try:
            if asyncio.iscoroutinefunction(func):
                await func(*args)
            else:
                func(*args)
        except Exception as e:
            logger.error(f"[Dispatcher] 回调错误: {e}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "queue_size": self._task_queue.qsize(),
            "active_tasks": len(self._active_tasks),
            "workers": len(self._workers),
            "runtime_status": self.runtime.get_status(),
        }
