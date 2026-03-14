"""GPTs Memory Module (Optimized with Logging)"""

from __future__ import annotations

import asyncio
import logging
import time
from asyncio import Queue
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union, Any

import psutil
from cachetools import TTLCache

from derisk.util.executor_utils import blocking_func_to_async, execute_no_wait
from .agent_system_message import AgentSystemMessage
from .base import (
    GptsMessage,
    GptsMessageMemory,
    GptsPlansMemory,
    GptsPlan,
    AgentSystemMessageMemory,
)
from .default_gpts_memory import DefaultGptsMessageMemory, DefaultGptsPlansMemory
from .file_base import (
    AgentFileMetadata,
    AgentFileMemory,
    FileMetadataStorage,
    FileType,
    WorkLogStorage,
    WorkEntry,
    WorkLogSummary,
    WorkLogStatus,
    KanbanStorage,
    Kanban,
    KanbanStage,
    StageStatus,
    TodoStorage,
    TodoItem,
    TodoStatus,
)
from .default_file_memory import DefaultAgentFileMemory
from ...action.base import ActionOutput
from ...file_system.file_tree import TreeManager, TreeNodeData
from .....util.id_generator import IdGenerator
from .....util.tracer import trace
from .....vis.vis_converter import VisProtocolConverter, DefaultVisConverter

logger = logging.getLogger(__name__)


# --------------------------
# 消息通道迭代器
# --------------------------
class QueueIterator:
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        start = time.perf_counter()
        item = await self.queue.get()
        if item == "[DONE]":
            self.queue.task_done()
            raise StopAsyncIteration
        logger.debug(f"Queue wait: {(time.perf_counter() - start) * 1000:.2f}ms")
        try:
            return item
        finally:
            self.queue.task_done()


class AgentTaskType(Enum):
    PLAN = "plan"
    AGENT = "agent"
    STAGE = "stage"
    TASK = "task"
    HIDDEN = "hidden"


@dataclass
class AgentTaskContent:
    agent_id: Optional[str] = None  # type:ignore
    agent_name: Optional[str] = None  # type:ignore
    """处理当前任务的Agent"""
    task_type: Optional[str] = field(default=None)
    """当前节点的记录类型"""
    message_id: Optional[str] = None
    cost: float = 0

    def update(
        self,
        task_type: Optional[str] = None,
        agent: Optional[str] = None,
        message_id: Optional[str] = None,
    ):
        if task_type:
            self.task_type = task_type
        if agent:
            self.agent = agent
        if message_id:
            self.message_id = message_id


# @dataclass
# class AgentTaskContent:
#     agent: "ConversableAgent"  # type:ignore
#     """处理当前任务的Agent"""
#     task_type: Optional[str] = field(default=None)
#     """当前节点的记录类型"""
#     messages: List[str] = field(default_factory=list)
#     """当前Agent在当前任务下所生成的消息,和消息对应的Action"""
#     actions: List[str] = field(default_factory=list)
#     intent: Optional[str] = field(default=None)
#     """当前任务的意图"""
#     description: Optional[str] = field(default=None)
#     """当前任务的意图说明"""
#     summary: Optional[str] = None
#     """当前任务的整体总结"""
#     step_summary: List[Dict] = field(default_factory=list)
#     """当前任务的分布总结"""
#     message_action: Dict[str, List[str]] = field(default_factory=lambda: {})
#     """消息和action的关系"""
#     action_task: Dict[str, str] = field(default_factory=dict)
#     """action和任务的关系"""
#     cost: Optional[float] = field(default=0)
#     """当前Agent任务耗时"""


# def update(self, state: Optional[str] = None, intent: Optional[str] = None, description: Optional[str] = None,
#            summary: Optional[str] = None, step_summary: Optional[List[dict]] = None):
#     if state:
#         self.state = state
#     if intent:
#         self.intent = intent
#     if description:
#         self.description = description
#     if summary:
#         self.summary = summary
#     if step_summary:
#         self.step_summary = step_summary
#
# def update_actions(self, message_id: str, action_outs: List[ActionOutput]):
#     if not action_outs:
#         return
#     message_action_ids = []
#     for item in action_outs:
#         if item.action_id not in self.actions:
#             self.actions.append(item.action_id)
#             message_action_ids.append(item.action_id)
#     if message_id not in self.message_action:
#         self.message_action[message_id] = message_action_ids
#     else:
#         self.message_action[message_id].extend(message_action_ids)
#
# def upsert_message(self, message: GptsMessage):
#     if message.metrics:
#         start_ms = message.metrics.start_time_ms
#         end_ms = message.metrics.end_time_ms
#         if not message.metrics.end_time_ms:
#             end_ms = time.time_ns() // 1_000_000
#         cost = round((end_ms - start_ms) / 1_000, 2)
#         self.cost = cost
#     if message.message_id not in self.messages:
#         self.messages.append(message.message_id)
#     self.update_actions(message_id=message.message_id, action_outs=message.action_report)


# --------------------------
# 会话级缓存容器
# --------------------------
class ConversationCache:
    """单个会话的所有缓存数据"""

    def __init__(
        self,
        conv_id: str,
        vis_converter: VisProtocolConverter,
        start_round: int = 0,
    ):
        self.conv_id = conv_id
        self.messages: Dict[str, GptsMessage] = {}
        self.actions: Dict[str, ActionOutput] = {}
        self.plans: Dict[str, GptsPlan] = {}
        self.system_messages: Dict[str, AgentSystemMessage] = {}
        self.context_windows: Dict[str, Dict[str, Any]] = {}  # 各子任务的上下文窗口

        # 缓存接收到的输入消息id
        self.input_message_id: Optional[str] = None
        # 缓存返回给用户的消息id
        self.output_message_id: Optional[str] = None

        self.task_manager: TreeManager[AgentTaskContent] = TreeManager()
        self.message_ids: List[str] = []  # 保证消息顺序
        self.channel = Queue(maxsize=100)  # 限制队列大小，防 OOM
        self.round_generator = IdGenerator(start_round + 1)
        self.vis_converter = vis_converter
        self.start_round = start_round
        self.stop_flag = False
        self.start_push = False

        ## 当前Agent相关信息
        self.main_agent_name: Optional[str] = None
        self.senders: Dict[str, "ConversableAgent"] = {}  # type: ignore

        ## TODOLIST缓存 (用于PDCA Agent推送todollist)
        self.todollist_vis: Optional[str] = None

        ## 文件系统缓存
        self.files: Dict[str, AgentFileMetadata] = {}  # file_id -> AgentFileMetadata
        self.file_key_index: Dict[str, str] = {}  # file_key -> file_id (catalog)

        ## 工作日志缓存
        self.work_logs: List[WorkEntry] = []  # 工作日志条目列表
        self.work_log_summaries: List[WorkLogSummary] = []  # 压缩摘要列表

        ## 看板缓存
        self.kanban: Optional[Kanban] = None  # 当前看板
        self.pre_kanban_logs: List[WorkEntry] = []  # 看板创建前的预研日志
        self.deliverables: Dict[str, Dict[str, Any]] = {}  # stage_id -> deliverable

        ## Todo 缓存
        self.todos: List[TodoItem] = []  # 任务列表

        self.last_access = time.time()
        self.lock = asyncio.Lock()  # 会话级锁

    def clear(self):
        """清理所有资源并通知消费者退出"""
        # 释放可视化资源
        if hasattr(self.vis_converter, "close"):
            try:
                self.vis_converter.close()
            except Exception as e:
                logger.error(f"Error closing vis_converter: {e}")

        # 清理数据结构
        self.messages.clear()
        self.plans.clear()
        self.system_messages.clear()
        self.message_ids.clear()
        self.senders.clear()
        self.context_windows.clear()

        # 清理文件缓存
        self.files.clear()
        self.file_key_index.clear()

        # 清理工作日志
        self.work_logs.clear()
        self.work_log_summaries.clear()

        # 清理看板相关
        self.kanban = None
        self.pre_kanban_logs.clear()
        self.deliverables.clear()

        # 清理 Todo
        self.todos.clear()

        # 通知队列消费者退出
        try:
            self.channel.put_nowait("[DONE]")
        except asyncio.QueueFull:
            pass  # 队列满，忽略

    def get_messages_ordered(self) -> List[GptsMessage]:
        return [
            self.messages[msg_id]
            for msg_id in self.message_ids
            if msg_id in self.messages
        ]

    def get_plans_list(self) -> List[GptsPlan]:
        return list(self.plans.values())

    def get_system_messages(
        self, type: Optional[str] = None, phase: Optional[str] = None
    ):
        result = []
        for v in self.system_messages.values():
            if (
                (type and v.type == type)
                or (phase and v.phase == phase)
                or (not type and not phase)
            ):
                result.append(v)
        return result


# --------------------------
# 动态线程池
# --------------------------
class DynamicThreadPoolExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers=None, *args, **kwargs):
        if max_workers is None:
            max_workers = psutil.cpu_count() * 4
        super().__init__(max_workers, *args, **kwargs)
        self._adjust_task = None
        self._monitor_task = None

    def start_dynamic_adjust(self, loop: asyncio.AbstractEventLoop):
        """启动动态调整任务（通过事件循环）"""
        if self._adjust_task is None:
            self._adjust_task = loop.create_task(self._dynamic_adjust_loop())
        if self._monitor_task is None:
            self._monitor_task = loop.create_task(self._monitor_loop())

    async def _dynamic_adjust_loop(self):
        while True:
            await asyncio.sleep(30)
            self.adjust_thread_pool()

    async def _monitor_loop(self):
        while True:
            await asyncio.sleep(60)
            logger.info(
                f"ThreadPool Status: workers={self._max_workers} "
                f"pending={self._work_queue.qsize()} "
                f"active={len(self._threads)}"
            )

    def adjust_thread_pool(self):
        current_load = psutil.getloadavg()[0] / psutil.cpu_count()
        current_workers = self._max_workers
        pending_tasks = self._work_queue.qsize()

        if current_load > 1.0 and pending_tasks > current_workers * 2:
            new_workers = min(current_workers * 2, psutil.cpu_count() * 8)
        elif current_load < 0.5 and pending_tasks < current_workers // 2:
            new_workers = max(current_workers // 2, psutil.cpu_count())
        else:
            return

        if new_workers != current_workers:
            logger.info(f"Adjusting thread pool: {current_workers}->{new_workers}")
            self._max_workers = new_workers
            for _ in range(new_workers - current_workers):
                self._adjust_thread_count()


# --------------------------
# 全局内存管理（单例）
# --------------------------
class GptsMemory(FileMetadataStorage, WorkLogStorage, KanbanStorage, TodoStorage):
    """会话全局消息记忆管理（包含文件元数据管理、工作日志、看板和任务列表管理）.

    同时实现了 FileMetadataStorage、WorkLogStorage、KanbanStorage 和 TodoStorage 接口，
    可作为 AgentFileSystem、WorkLogManager、KanbanManager 和 Todo 工具的统一存储后端。
    """

    def __init__(
        self,
        plans_memory: GptsPlansMemory = DefaultGptsPlansMemory(),
        message_memory: GptsMessageMemory = DefaultGptsMessageMemory(),
        executor: Executor = None,
        default_vis_converter: VisProtocolConverter = DefaultVisConverter(),
        *,
        cache_ttl: int = 10800,  # 会话缓存 TTL（秒）
        cache_maxsize: int = 200,  # 最大会话数
        message_system_memory: Optional[AgentSystemMessageMemory] = None,
        file_memory: AgentFileMemory = None,
        file_metadata_db_storage: Optional[Any] = None,  # 数据库文件元数据存储后端
        work_log_db_storage: Optional[Any] = None,  # 数据库 WorkLog 存储后端
        kanban_db_storage: Optional[Any] = None,  # 数据库 Kanban 存储后端
        todo_db_storage: Optional[Any] = None,  # 数据库 Todo 存储后端
    ):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        self._plans_memory = plans_memory
        self._message_memory = message_memory
        self._message_system_memory = message_system_memory
        self._file_memory = file_memory or DefaultAgentFileMemory()
        self._executor = executor or DynamicThreadPoolExecutor()
        self._default_vis_converter = default_vis_converter
        self._conversations = TTLCache(
            maxsize=cache_maxsize, ttl=cache_ttl, timer=time.time
        )
        self._conv_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None

        # 数据库存储后端（用于持久化）
        self._file_metadata_db_storage = file_metadata_db_storage
        self._work_log_db_storage = work_log_db_storage
        self._kanban_db_storage = kanban_db_storage
        self._todo_db_storage = todo_db_storage

    @property
    def file_memory(self) -> AgentFileMemory:
        """获取文件元数据存储.

        文件目录(catalog)功能也集成在file_memory中，通过以下方法访问：
        - save_catalog(conv_id, file_key, file_id): 保存映射
        - get_catalog(conv_id): 获取所有映射
        - get_file_id_by_key(conv_id, file_key): 通过key获取ID
        """
        return self._file_memory

    async def start(self):
        """启动内存管理服务（必须在事件循环中调用）"""
        # 启动动态线程池调整
        if isinstance(self._executor, DynamicThreadPoolExecutor):
            self._executor.start_dynamic_adjust(loop=asyncio.get_running_loop())

        # 启动监控和清理任务
        self._monitor_task = asyncio.create_task(self._monitor_resources())
        self._cleanup_task = asyncio.create_task(self._auto_cleanup_async())

        logger.info("GptsMemory service started")

    async def shutdown(self):
        """关闭内存管理服务"""
        if self._monitor_task:
            self._monitor_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()

        # 清理所有会话
        async with self._global_lock:
            for conv_id in list(self._conversations.keys()):
                await self.clear(conv_id)

        logger.info("GptsMemory service stopped")

    async def _monitor_resources(self):
        """资源监控任务"""
        while True:
            # 监控内存使用
            process = psutil.Process()
            mem_info = process.memory_info()
            logger.info(
                f"Memory Usage: RSS={mem_info.rss / 1024 / 1024:.2f} MB | VMS={mem_info.vms / 1024 / 1024:.2f} MB"
            )

            # 监控缓存状态
            logger.info(
                f"Conversation Cache: {len(self._conversations)} active sessions"
            )

            # 监控线程池
            if isinstance(self._executor, ThreadPoolExecutor):
                logger.info(
                    f"ThreadPool: workers={self._executor._max_workers} "
                    f"| queue={self._executor._work_queue.qsize()} "
                    f"| active={len(self._executor._threads)}"
                )

            # 监控会话队列
            async with self._global_lock:
                for conv_id, cache in self._conversations.items():
                    logger.debug(
                        f"Conversation {conv_id} queue: {cache.channel.qsize()} messages"
                    )

            await asyncio.sleep(60)  # 每60秒采集一次

    async def start_cleanup(self):
        """启动后台自动清理任务（应用初始化时调用）"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._auto_cleanup_async())

    async def stop_cleanup(self):
        """停止后台清理任务（应用关闭时调用）"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _auto_cleanup_async(self):
        """异步自动触发 TTL 过期"""
        while True:
            await asyncio.sleep(300)  # 每5分钟
            async with self._global_lock:
                self._conversations.expire()
                logger.info(
                    f"Auto cleanup triggered, current sessions: {len(self._conversations)}"
                )

    @property
    def plans_memory(self) -> GptsPlansMemory:
        return self._plans_memory

    @property
    def message_memory(self) -> GptsMessageMemory:
        return self._message_memory

    @property
    def message_system_memory(self) -> Optional[AgentSystemMessageMemory]:
        return self._message_system_memory

    async def cache(self, conv_id: str) -> Optional[ConversationCache]:
        return await self._get_cache(conv_id)

    async def _get_cache(self, conv_id: str) -> Optional[ConversationCache]:
        async with self._global_lock:
            cache = self._conversations.get(conv_id)
            if cache:
                cache.last_access = time.time()
            return cache

    def _get_cache_sync(self, conv_id: str) -> Optional[ConversationCache]:
        cache = self._conversations.get(conv_id)
        if cache:
            cache.last_access = time.time()
        return cache

    async def _get_or_create_cache(
        self,
        conv_id: str,
        start_round: int = 0,
        vis_converter: Optional[VisProtocolConverter] = None,
    ) -> ConversationCache:
        async with self._global_lock:
            if conv_id not in self._conversations:
                logger.info(
                    f"对话 {conv_id} 不在缓存中，构建新缓存！可视化组件: "
                    f"{vis_converter.render_name if vis_converter else 'default'}"
                )
                self._conversations[conv_id] = ConversationCache(
                    conv_id=conv_id,
                    vis_converter=vis_converter or self._default_vis_converter,
                    start_round=start_round,
                )
                # 创建会话级锁
                self._conv_locks[conv_id] = asyncio.Lock()
            return self._conversations[conv_id]

    async def _get_conv_lock(self, conv_id: str) -> asyncio.Lock:
        async with self._global_lock:
            return self._conv_locks.setdefault(conv_id, asyncio.Lock())

    async def _cache_messages(self, conv_id: str, messages: List[GptsMessage]):
        cache = await self._get_cache(conv_id)
        if not cache:
            return
        async with await self._get_conv_lock(conv_id):
            for msg in messages:
                cache.messages[msg.message_id] = msg
                if msg.message_id not in cache.message_ids:
                    cache.message_ids.append(msg.message_id)

    async def load_persistent_memory(self, conv_id: str):
        """懒加载持久化数据（仅当缓存为空时）"""
        logger.warning(f"load_persistent_memory conv_id:{conv_id}! 从数据库加载消息！")
        cache = await self._get_cache(conv_id)
        if not cache:
            return

        # 加载消息
        if not cache.message_ids:
            messages = await self._message_memory.get_by_conv_id(conv_id)
            await self._cache_messages(conv_id, messages)

        # 加载计划
        if not cache.plans:
            plans = await self._plans_memory.get_by_conv_id(conv_id)
            async with await self._get_conv_lock(conv_id):
                for p in plans:
                    cache.plans[p.task_uid] = p

    # --------------------------
    # 内部功能方法区
    # --------------------------
    def _merge_messages(self, messages: List[GptsMessage]):
        i = 0
        new_messages: List[GptsMessage] = []
        from ...user_proxy_agent import HUMAN_ROLE

        while i < len(messages):
            cu_item = messages[i]

            # 屏蔽用户发送消息
            if cu_item.sender == HUMAN_ROLE:
                i += 1
                continue
            if not cu_item.show_message:
                ## 接到消息的Agent不展示消息，消息直接往后传递展示
                if i + 1 < len(messages):
                    ne_item = messages[i + 1]
                    new_message = ne_item
                    new_message.sender = cu_item.sender
                    new_message.current_goal = (
                        ne_item.current_goal or cu_item.current_goal
                    )
                    new_message.resource_info = (
                        ne_item.resource_info or cu_item.resource_info
                    )
                    new_messages.append(new_message)
                    i += 2  # 两个消息合并为一个
                    continue
            new_messages.append(cu_item)
            i += 1

        return new_messages

    async def _merge_messages_async(
        self, messages: List[GptsMessage]
    ) -> List[GptsMessage]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._merge_messages, messages
        )

    # --------------------------
    # 外部核心方法区
    # --------------------------
    async def queue_iterator(self, conv_id: str) -> Optional[QueueIterator]:
        cache = await self._get_cache(conv_id)
        return QueueIterator(cache.channel) if cache else None

    async def init(
        self,
        conv_id: str,
        history_messages: List[GptsMessage] = None,
        vis_converter: VisProtocolConverter = None,
        start_round: int = 0,
        app_code=None,
    ):
        cache = await self._get_or_create_cache(conv_id, start_round, vis_converter)
        if history_messages:
            await self._cache_messages(conv_id, history_messages)

    async def set_agents(self, conv_id: str, main_agent: "ConversableAgent"):  # type:ignore
        logger.info(f"set_main:{conv_id},{main_agent.name}")
        cache = await self._get_cache(conv_id)
        if cache:
            cache.main_agent_name = main_agent.name

            ## 解压缩主Agent下的所有关联子Agent
            async def _scan_agents(agent):
                cache.senders[agent.name] = agent
                if hasattr(agent, "agents") and agent.agents:
                    for item in agent.agents:
                        await _scan_agents(item)

            await _scan_agents(main_agent)

    async def set_agent(self, conv_id: str, sender: "ConversableAgent"):  # type:ignore
        cache = await self._get_cache(conv_id)
        if cache:
            cache.senders[sender.name] = sender

    async def async_vis_converter(self, conv_id: str) -> Optional[VisProtocolConverter]:
        cache = await self._get_cache(conv_id)
        return cache.vis_converter if cache else None

    # 保留同步版，但加注释
    def vis_converter(self, agent_conv_id: str) -> Optional[VisProtocolConverter]:
        """⚠️ 同步方法！仅用于非 asyncio 上下文。生产环境优先使用 get_vis_converter()"""
        cache = self._get_cache_sync(agent_conv_id)
        return cache.vis_converter if cache else None

    async def next_message_rounds(
        self, conv_id: str, new_init_round: Optional[int] = None
    ) -> int:
        cache = await self._get_cache(conv_id)
        if cache:
            return await cache.round_generator.next(new_init_round)
        return 0

    async def vis_final(self, conv_id: str) -> Any:
        """生成最终可视化视图"""
        cache = None
        try:
            cache = await self._get_cache(conv_id)
            if not cache:
                return None
            messages = await self.get_messages(conv_id)

            messages = messages[cache.start_round :]
            messages = await self._merge_messages_async(messages)
            plans = cache.plans  # 直接使用 dict
            vis_convert = cache.vis_converter or DefaultVisConverter()
            final_view = await vis_convert.final_view(
                messages=messages,
                plans_map=plans,
                senders_map=dict(cache.senders),
                main_agent_name=cache.main_agent_name,
                messages_map=cache.messages,
                actions_map=cache.actions,
                task_manager=cache.task_manager,
                input_message_id=cache.input_message_id,
                output_message_id=cache.output_message_id,
            )
            return final_view
        except Exception as e:
            logger.exception(f"vis_final exception!conv_id={conv_id}")
        finally:
            if cache:
                cache.senders.clear()

    async def user_answer(self, conv_id: str) -> str:
        messages = await self.get_messages(conv_id)
        cache = await self._get_cache(conv_id)
        if not cache:
            return ""
        messages = messages[cache.start_round :]
        from ...user_proxy_agent import HUMAN_ROLE

        for msg in reversed(messages):
            if msg.receiver == HUMAN_ROLE:
                content = msg.content
                if msg.action_report:
                    try:
                        content = ""
                        for item in msg.action_report:
                            view = item.content
                            content = content + "\n" + view
                    except Exception:
                        logger.exception("Failed to parse action_report")
                return content
        return messages[-1].content if messages else ""

    async def vis_messages(
        self,
        conv_id: str,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[GptsPlan]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        incr_type: Optional[str] = None,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None,  # type:ignore
        **kwargs,
    ) -> Any:
        """生成消息可视化视图"""
        cache = await self._get_cache(conv_id)
        if not cache:
            return None
        messages = await self.get_messages(conv_id)
        messages = messages[cache.start_round :]
        messages = await self._merge_messages_async(messages)
        all_plans = cache.plans
        return await cache.vis_converter.visualization(
            messages=messages,
            plans_map=all_plans,
            gpt_msg=gpt_msg,
            stream_msg=stream_msg,
            new_plans=new_plans,
            actions_map=cache.actions,
            is_first_chunk=is_first_chunk,
            is_first_push=not cache.start_push,
            incremental=incremental,
            incr_type=incr_type,
            main_agent_name=cache.main_agent_name,
            senders_map=senders_map or dict(cache.senders),
            task_manager=cache.task_manager,
            conv_id=conv_id,
            cache=cache,
            **kwargs,
        )

    async def complete(self, conv_id: str):
        logger.info(f"完成会话[{conv_id}]")
        cache = await self._get_cache(conv_id)
        if cache:
            await cache.channel.put("[DONE]")

    async def have_memory_cache(self, conv_id: str) -> bool:
        return (await self._get_cache(conv_id)) is not None

    async def get_task_manager(self, conv_id: str) -> Optional[TreeManager]:
        cache = await self._get_cache(conv_id)
        if not cache:
            return None
        return cache.task_manager

    @trace("gptsmemory.append_task")
    async def upsert_task(self, conv_id: str, task: TreeNodeData[AgentTaskContent]):
        cache = await self._get_cache(conv_id)
        if not cache:
            return
        is_success, is_new = cache.task_manager.upsert_node(
            parent_id=task.parent_id, node=task
        )
        ## 新增节点的时候 推送前端展示
        logger.info(f"推送新的任务节点[{task.node_id},{task.name}]")
        await self.push_message(conv_id, new_task_nodes=[task])

    async def get_task(
        self, conv_id: str, node_id: str
    ) -> Optional[TreeNodeData[AgentTaskContent]]:
        cache = await self._get_cache(conv_id)
        if not cache:
            return None
        return cache.task_manager.get_node(node_id)

    @trace("agent.append_message")
    async def append_message(
        self,
        conv_id: str,
        message: GptsMessage,
        incremental: bool = False,
        save_db: bool = True,
        sender: Optional["ConversableAgent"] = None,  # type:ignore
    ):
        cache = await self._get_cache(conv_id)
        if not cache:
            return

        conv_lock = await self._get_conv_lock(conv_id)
        from ...user_proxy_agent import HUMAN_ROLE

        async with conv_lock:
            # 更新消息缓存
            message.updated_at = datetime.now()
            if message.sender == HUMAN_ROLE:
                cache.input_message_id = message.message_id

            if message.receiver == HUMAN_ROLE:
                cache.output_message_id = message.message_id

            ## 直接更新是覆盖
            cache.messages[message.message_id] = message
            if message.message_id not in cache.message_ids:
                cache.message_ids.append(message.message_id)
            ## 更新action数据
            if message.action_report:
                for act_out in message.action_report:
                    cache.actions[act_out.action_id] = act_out

            # # 更新任务空间
            # ## 开始当前的任务空间
            # task_node: TreeNodeData[AgentTaskContent] = cache.task_manager.get_node(message.goal_id)
            #
            # if task_node:
            #     logger.info(f"[DEBUG]当前task_space:{task_node.node_id}, 添加目标id:{message.message_id}的消息")
            #     task_node.content.upsert_message(message)
            # else:
            #     logger.warning(f"[{message.goal_id}]没有对应的任务空间！")

        if save_db:
            try:
                execute_no_wait(self._message_memory.update, message)
            except Exception as e:
                logger.error(f"Failed to save message to DB: {e}")

        logger.debug(f"Appended message to {conv_id}: {message.message_id}")
        await self.push_message(
            conv_id, gpt_msg=message, incremental=incremental, sender=sender
        )

    async def append_system_message(self, agent_system_message: AgentSystemMessage):
        cache = await self._get_cache(agent_system_message.conv_id)
        agent_system_message.gmt_modified = datetime.now()
        conv_lock = await self._get_conv_lock(agent_system_message.conv_id)
        async with conv_lock:
            if cache:
                cache.system_messages[agent_system_message.message_id] = (
                    agent_system_message
                )
        if self.message_system_memory:
            try:
                await blocking_func_to_async(
                    self._executor,
                    self.message_system_memory.update,
                    agent_system_message,
                )
            except Exception as e:
                logger.error(f"Failed to save system message: {e}")

    async def get_system_messages(
        self, conv_id: str, type: Optional[str] = None, phase: Optional[str] = None
    ) -> List[AgentSystemMessage]:
        cache = await self._get_or_create_cache(conv_id)
        return cache.get_system_messages(type=type, phase=phase)

    async def append_plans(
        self,
        conv_id: str,
        plans: List[GptsPlan],
        incremental: bool = False,
        sender: Optional["ConversableAgent"] = None,  # type:ignore
        need_storage: bool = True,
    ):
        cache = await self._get_cache(conv_id)
        conv_lock = await self._get_conv_lock(conv_id)
        async with conv_lock:
            if cache:
                for plan in plans:
                    plan.created_at = datetime.now()
                    cache.plans[plan.task_uid] = plan

        await self.push_message(
            conv_id, new_plans=plans, incremental=incremental, sender=sender
        )

        if need_storage:
            try:
                await blocking_func_to_async(
                    self._executor, self._plans_memory.batch_save, plans
                )
            except Exception as e:
                logger.error(f"Failed to save plans: {e}")

        logger.info(f"Appended {len(plans)} plans to {conv_id}")

    async def update_plan(
        self, conv_id: str, plan: GptsPlan, incremental: bool = False
    ):
        plan.updated_at = datetime.now()
        try:
            await blocking_func_to_async(
                self._executor,
                self._plans_memory.update_by_uid,
                conv_id,
                plan.task_uid,
                plan.state,
                plan.retry_times,
                model=plan.agent_model,
                result=plan.result,
            )
        except Exception as e:
            logger.error(f"Failed to update plan: {e}")
            return

        cache = await self._get_cache(conv_id)
        conv_lock = await self._get_conv_lock(conv_id)
        async with conv_lock:
            if cache and plan.task_uid in cache.plans:
                existing = cache.plans[plan.task_uid]
                existing.state = plan.state
                existing.retry_times = plan.retry_times
                existing.agent_model = plan.agent_model
                existing.result = plan.result

        await self.push_message(conv_id, new_plans=[plan], incremental=incremental)
        logger.info(f"Updated plan {conv_id}:{plan.task_uid}")

    async def get_plans(self, conv_id: str) -> List[GptsPlan]:
        cache = await self._get_cache(conv_id)
        return list(cache.plans.values()) if cache else []

    async def get_plan(self, conv_id: str, task_uid: str) -> Optional[GptsPlan]:
        cache = await self._get_cache(conv_id)
        return cache.plans.get(task_uid) if cache else None

    async def get_planner_plans(self, conv_id: str, planner: str) -> List[GptsPlan]:
        cache = await self._get_cache(conv_id)
        if not cache:
            return []
        return [p for p in cache.plans.values() if p.planning_agent == planner]

    async def get_by_planner_and_round(
        self, conv_id: str, planner: str, round_id: str
    ) -> List[GptsPlan]:
        cache = await self._get_cache(conv_id)
        if not cache:
            return []
        return [
            p
            for p in cache.plans.values()
            if p.planning_agent == planner and p.conv_round_id == round_id
        ]

    async def push_message(
        self,
        conv_id: str,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[GptsPlan]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        incr_type: Optional[str] = None,
        sender: Optional["ConversableAgent"] = None,  # type:ignore
        **kwargs,
    ):
        cache = await self._get_cache(conv_id)
        if not cache or cache.stop_flag:
            return

        if cache.stop_flag:
            raise ValueError("当前会话已经停止！")

        # 更新发送者缓存
        if sender:
            conv_lock = await self._get_conv_lock(conv_id)
            async with conv_lock:
                cache.senders[sender.name] = sender

        from ...user_proxy_agent import HUMAN_ROLE

        if gpt_msg and gpt_msg.sender == HUMAN_ROLE:
            return

        try:
            final_view = await self.vis_messages(
                conv_id,
                gpt_msg=gpt_msg,
                stream_msg=stream_msg,
                new_plans=new_plans,
                is_first_chunk=is_first_chunk,
                incremental=incremental,
                senders_map=dict(cache.senders),
                incr_type=incr_type,
                **kwargs,
            )
            if final_view:
                ## 如果消息通道满了 直接抛弃，不阻塞后续执行
                cache.channel.put_nowait(final_view)
                if stream_msg or gpt_msg:
                    cache.start_push = True
                await asyncio.sleep(0)
        except asyncio.QueueFull:
            logger.warning(f"Queue full for {conv_id}, dropping message")
        except Exception as e:
            logger.exception(f"Error pushing message: {e}")

    async def get_messages(self, conv_id: str) -> List[GptsMessage]:
        cache = await self._get_or_create_cache(conv_id)
        if not cache.message_ids:
            await self.load_persistent_memory(conv_id)
        messages = cache.get_messages_ordered()
        messages.sort(key=lambda x: x.rounds)  # 若 append 时保序，可移除此行
        return messages

    async def get_session_messages(self, conv_session_id: str) -> List[GptsMessage]:
        return await blocking_func_to_async(
            self._executor, self.message_memory.get_by_session_id, conv_session_id
        )

    async def stop(self, conv_id: str):
        """停止会话的消息推送和消费者.

        设置停止标志并通知队列消费者退出，但不清理会话数据。

        Args:
            conv_id: 会话ID
        """
        logger.info(f"Stopping memory for {conv_id}")
        cache = await self._get_cache(conv_id)
        if cache:
            # 设置停止标志，阻止新的消息推送
            cache.stop_flag = True
            # 通知队列消费者退出
            try:
                cache.channel.put_nowait("[DONE]")
            except asyncio.QueueFull:
                pass  # 队列满，忽略
            logger.info(f"Stopped conversation: {conv_id}")

    async def clear(self, conv_id: str):
        """主动清理会话资源"""
        logger.info(f"Clearing memory for {conv_id}")
        async with self._global_lock:
            cache = self._conversations.pop(conv_id, None)
            if conv_id in self._conv_locks:
                del self._conv_locks[conv_id]
        if cache:
            # 手动清理senders引用
            cache.senders.clear()
            cache.clear()
            logger.info(f"Cleared conversation cache: {conv_id}")

    # --------------------------
    # 文件管理方法区
    # --------------------------
    async def append_file(
        self, conv_id: str, file_metadata: AgentFileMetadata, save_db: bool = True
    ):
        """添加文件元数据到缓存和存储.

        Args:
            conv_id: 会话ID
            file_metadata: 文件元数据
            save_db: 是否持久化到数据库
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.files[file_metadata.file_id] = file_metadata
            cache.file_key_index[file_metadata.file_key] = file_metadata.file_id

        if save_db:
            if self._file_metadata_db_storage:
                try:
                    await self._file_metadata_db_storage.save_file_metadata(
                        file_metadata
                    )
                    logger.debug(
                        f"Saved file metadata to DB storage: {file_metadata.file_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to save file metadata to DB storage: {e}")
            else:
                try:
                    await blocking_func_to_async(
                        self._executor, self._file_memory.append, file_metadata
                    )
                    logger.debug(
                        f"Saved file metadata to file memory: {file_metadata.file_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to save file metadata to file memory: {e}")

    async def update_file(self, conv_id: str, file_metadata: AgentFileMetadata):
        """更新文件元数据.

        Args:
            conv_id: 会话ID
            file_metadata: 文件元数据
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.files[file_metadata.file_id] = file_metadata

        if self._file_metadata_db_storage:
            try:
                await self._file_metadata_db_storage.update_file_metadata(file_metadata)
                logger.debug(
                    f"Updated file metadata in DB storage: {file_metadata.file_id}"
                )
            except Exception as e:
                logger.error(f"Failed to update file metadata in DB storage: {e}")
        else:
            try:
                await blocking_func_to_async(
                    self._executor, self._file_memory.update, file_metadata
                )
            except Exception as e:
                logger.error(f"Failed to update file metadata: {e}")

    async def get_files(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取会话的所有文件.

        Args:
            conv_id: 会话ID

        Returns:
            文件元数据列表
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache.files:
            if self._file_metadata_db_storage:
                try:
                    files = await self._file_metadata_db_storage.list_files(conv_id)
                    async with await self._get_conv_lock(conv_id):
                        for f in files:
                            cache.files[f.file_id] = f
                            cache.file_key_index[f.file_key] = f.file_id
                    return files
                except Exception as e:
                    logger.error(f"Failed to load files from DB storage: {e}")
            else:
                files = await blocking_func_to_async(
                    self._executor, self._file_memory.get_by_conv_id, conv_id
                )
                async with await self._get_conv_lock(conv_id):
                    for f in files:
                        cache.files[f.file_id] = f
                        cache.file_key_index[f.file_key] = f.file_id
                return files
        return list(cache.files.values())

    async def get_file_by_id(
        self, conv_id: str, file_id: str
    ) -> Optional[AgentFileMetadata]:
        """通过ID获取文件元数据.

        Args:
            conv_id: 会话ID
            file_id: 文件ID

        Returns:
            文件元数据
        """
        cache = await self._get_cache(conv_id)
        if cache and file_id in cache.files:
            return cache.files[file_id]
        return None

    async def get_file_by_key(
        self, conv_id: str, file_key: str
    ) -> Optional[AgentFileMetadata]:
        """通过key获取文件元数据.

        Args:
            conv_id: 会话ID
            file_key: 文件key

        Returns:
            文件元数据
        """
        cache = await self._get_cache(conv_id)
        if cache and file_key in cache.file_key_index:
            file_id = cache.file_key_index[file_key]
            return cache.files.get(file_id)
        if self._file_metadata_db_storage:
            try:
                file_metadata = await self._file_metadata_db_storage.get_file_by_key(
                    conv_id, file_key
                )
                if file_metadata and cache:
                    async with await self._get_conv_lock(conv_id):
                        cache.files[file_metadata.file_id] = file_metadata
                        cache.file_key_index[file_metadata.file_key] = (
                            file_metadata.file_id
                        )
                return file_metadata
            except Exception as e:
                logger.error(f"Failed to get file by key from DB storage: {e}")
        return None

    async def get_files_by_type(
        self, conv_id: str, file_type: Union[str, FileType]
    ) -> List[AgentFileMetadata]:
        """获取指定类型的文件.

        Args:
            conv_id: 会话ID
            file_type: 文件类型

        Returns:
            文件元数据列表
        """
        cache = await self._get_or_create_cache(conv_id)
        target_type = file_type.value if isinstance(file_type, FileType) else file_type

        async with await self._get_conv_lock(conv_id):
            return [f for f in cache.files.values() if f.file_type == target_type]

    async def get_conclusion_files(self, conv_id: str) -> List[AgentFileMetadata]:
        """获取所有结论文件（用于推送给用户）.

        Args:
            conv_id: 会话ID

        Returns:
            结论文件列表
        """
        return await self.get_files_by_type(conv_id, FileType.CONCLUSION)

    async def save_file_catalog(self, conv_id: str):
        """保存文件目录.

        Args:
            conv_id: 会话ID
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return

        if self._file_metadata_db_storage:
            try:
                for file_key, file_id in cache.file_key_index.items():
                    await self._file_metadata_db_storage.save_catalog(
                        conv_id, file_key, file_id
                    )
                logger.debug(f"Saved file catalog to DB storage for {conv_id}")
            except Exception as e:
                logger.error(f"Failed to save file catalog to DB storage: {e}")
        else:
            try:
                for file_key, file_id in cache.file_key_index.items():
                    await blocking_func_to_async(
                        self._executor,
                        self._file_memory.save_catalog,
                        conv_id,
                        file_key,
                        file_id,
                    )
                logger.debug(f"Saved file catalog for {conv_id}")
            except Exception as e:
                logger.error(f"Failed to save file catalog: {e}")

    async def load_file_catalog(self, conv_id: str) -> Optional[Dict[str, str]]:
        """加载文件目录.

        Args:
            conv_id: 会话ID

        Returns:
            文件目录字典 {file_key -> file_id}
        """
        try:
            if self._file_metadata_db_storage:
                catalog = await self._file_metadata_db_storage.get_catalog(conv_id)
            else:
                catalog = await blocking_func_to_async(
                    self._executor, self._file_memory.get_catalog, conv_id
                )
            if catalog:
                cache = await self._get_or_create_cache(conv_id)
                async with await self._get_conv_lock(conv_id):
                    cache.file_key_index = dict(catalog)
            return catalog
        except Exception as e:
            logger.error(f"Failed to load file catalog: {e}")
            return None

    # =========================================================================
    # FileMetadataStorage Interface Implementation
    # =========================================================================
    # GptsMemory 实现了 FileMetadataStorage 接口，可作为 AgentFileSystem 的存储后端

    async def save_file_metadata(self, file_metadata: "AgentFileMetadata") -> None:
        """FileMetadataStorage接口: 保存文件元数据."""
        await self.append_file(file_metadata.conv_id, file_metadata)

    async def update_file_metadata(self, file_metadata: "AgentFileMetadata") -> None:
        """FileMetadataStorage接口: 更新文件元数据."""
        await self.update_file(file_metadata.conv_id, file_metadata)

    async def list_files(
        self, conv_id: str, file_type: Optional[Union[str, "FileType"]] = None
    ) -> List["AgentFileMetadata"]:
        """FileMetadataStorage接口: 列出会话的所有文件."""
        if file_type:
            return await self.get_files_by_type(conv_id, file_type)
        return await self.get_files(conv_id)

    async def delete_file(self, conv_id: str, file_key: str) -> bool:
        """FileMetadataStorage接口: 删除文件元数据.

        注意: 此方法删除元数据，但不删除实际文件。
        如需删除文件，请使用AgentFileSystem.delete_file().
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return False

        async with await self._get_conv_lock(conv_id):
            # 查找file_id
            file_id = cache.file_key_index.get(file_key)
            if file_id and file_id in cache.files:
                del cache.files[file_id]
                del cache.file_key_index[file_key]

        # 从持久化存储删除
        if self._file_metadata_db_storage:
            try:
                await self._file_metadata_db_storage.delete_file(conv_id, file_key)
                return True
            except Exception as e:
                logger.error(f"Failed to delete file metadata from DB storage: {e}")
                return False
        else:
            try:
                await blocking_func_to_async(
                    self._executor,
                    self._file_memory.delete_by_file_key,
                    conv_id,
                    file_key,
                )
                return True
            except Exception as e:
                logger.error(f"Failed to delete file metadata from storage: {e}")
                return False

    async def clear_conv_files(self, conv_id: str) -> None:
        """FileMetadataStorage接口: 清空会话的所有文件元数据."""
        cache = await self._get_cache(conv_id)
        if cache:
            async with await self._get_conv_lock(conv_id):
                cache.files.clear()
                cache.file_key_index.clear()
        if self._file_metadata_db_storage:
            await self._file_metadata_db_storage.clear_conv_files(conv_id)
        else:
            await blocking_func_to_async(
                self._executor, self._file_memory.delete_by_conv_id, conv_id
            )

    # =========================================================================
    # WorkLogStorage Interface Implementation
    # =========================================================================
    # GptsMemory 实现了 WorkLogStorage 接口，提供工作日志的统一存储能力

    async def append_work_entry(
        self,
        conv_id: str,
        entry: "WorkEntry",
        save_db: bool = True,
    ) -> None:
        """WorkLogStorage接口: 添加工作日志条目.

        Args:
            conv_id: 会话ID
            entry: 工作日志条目
            save_db: 是否持久化到数据库
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.work_logs.append(entry)

        if save_db:
            # 优先保存到数据库存储后端
            if self._work_log_db_storage:
                try:
                    await self._work_log_db_storage.append_async(
                        conv_id, conv_id, conv_id, entry
                    )
                    logger.debug(f"Persisted work entry to db storage: {conv_id}")
                except Exception as e:
                    logger.error(f"Failed to persist work log to db: {e}")
            else:
                # 回退到文件系统存储
                try:
                    work_log_data = [e.to_dict() for e in cache.work_logs]
                    await blocking_func_to_async(
                        self._executor,
                        self._file_memory.append,
                        AgentFileMetadata(
                            file_id=f"work_log_{conv_id}",
                            conv_id=conv_id,
                            conv_session_id=conv_id,
                            file_key=f"{conv_id}_work_log",
                            file_name="work_log.json",
                            file_type=FileType.WORK_LOG.value,
                            local_path="",
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed to persist work log: {e}")

        logger.debug(f"Appended work entry to {conv_id}: {entry.tool}")

    async def get_work_log(self, conv_id: str) -> List["WorkEntry"]:
        """WorkLogStorage接口: 获取会话的工作日志.

        Args:
            conv_id: 会话ID

        Returns:
            工作日志条目列表
        """
        cache = await self._get_or_create_cache(conv_id)
        return list(cache.work_logs)

    async def get_work_log_summaries(self, conv_id: str) -> List["WorkLogSummary"]:
        """WorkLogStorage接口: 获取工作日志摘要列表.

        Args:
            conv_id: 会话ID

        Returns:
            工作日志摘要列表
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return []
        return list(cache.work_log_summaries)

    async def append_work_log_summary(
        self,
        conv_id: str,
        summary: "WorkLogSummary",
        save_db: bool = True,
    ) -> None:
        """WorkLogStorage接口: 添加工作日志摘要.

        Args:
            conv_id: 会话ID
            summary: 工作日志摘要
            save_db: 是否持久化
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.work_log_summaries.append(summary)

        logger.debug(
            f"Appended work log summary to {conv_id}: "
            f"{summary.compressed_entries_count} entries compressed"
        )

    async def get_work_log_context(
        self,
        conv_id: str,
        max_entries: int = 50,
        max_tokens: int = 8000,
    ) -> str:
        """WorkLogStorage接口: 获取用于 prompt 的工作日志上下文.

        Args:
            conv_id: 会话ID
            max_entries: 最大条目数
            max_tokens: 最大 token 数

        Returns:
            格式化的上下文文本
        """
        cache = await self._get_cache(conv_id)
        if not cache or (not cache.work_logs and not cache.work_log_summaries):
            return "\n暂无工作日志记录。"

        lines = ["## 工作日志", ""]
        total_tokens = 0
        chars_per_token = 4

        # 添加历史摘要
        if cache.work_log_summaries:
            lines.append("### 历史摘要")
            for i, summary in enumerate(cache.work_log_summaries, 1):
                summary_text = f"#### 摘要 {i}\n{summary.summary_content}\n"
                lines.append(summary_text)
                total_tokens += len(summary_text) // chars_per_token
            lines.append("")

        # 添加活跃日志
        if cache.work_logs:
            lines.append("### 最近的工作")
            import time as time_module

            for entry in cache.work_logs[-max_entries:]:
                if entry.status == WorkLogStatus.ACTIVE.value:
                    time_str = time_module.strftime(
                        "%H:%M:%S", time_module.localtime(entry.timestamp)
                    )
                    entry_lines = [f"[{time_str}] {entry.tool}"]

                    if entry.args:
                        important_args = {
                            k: v
                            for k, v in entry.args.items()
                            if k
                            in [
                                "file_key",
                                "path",
                                "query",
                                "pattern",
                                "offset",
                                "limit",
                            ]
                        }
                        if important_args:
                            entry_lines.append(f"  参数: {important_args}")

                    if entry.result:
                        if entry.tool == "read_file":
                            entry_lines.append("  读取内容预览:")
                        result_lines = entry.result.split("\n")[:10]
                        preview = "\n".join(result_lines)
                        if len(preview) > 500:
                            preview = preview[:500] + "... (已截断)"
                        entry_lines.append(f"  {preview}")
                    elif entry.full_result_archive:
                        entry_lines.append(
                            f"  完整结果已归档: {entry.full_result_archive}"
                        )
                        entry_lines.append(
                            f'  💡 使用 read_file(file_key="{entry.full_result_archive}") 读取完整内容'
                        )

                    entry_text = "\n".join(entry_lines)
                    lines.append(entry_text)
                    total_tokens += len(entry_text) // chars_per_token

                    if total_tokens > max_tokens:
                        break

            lines.append("")

        return "\n".join(lines)

    async def clear_work_log(self, conv_id: str) -> None:
        """WorkLogStorage接口: 清空会话的工作日志.

        Args:
            conv_id: 会话ID
        """
        cache = await self._get_cache(conv_id)
        if cache:
            async with await self._get_conv_lock(conv_id):
                cache.work_logs.clear()
                cache.work_log_summaries.clear()
        logger.info(f"Cleared work log for {conv_id}")

    async def get_work_log_stats(self, conv_id: str) -> Dict[str, Any]:
        """WorkLogStorage接口: 获取工作日志统计信息.

        Args:
            conv_id: 会话ID

        Returns:
            统计信息字典
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return {
                "total_entries": 0,
                "active_entries": 0,
                "compressed_summaries": 0,
                "success_count": 0,
                "fail_count": 0,
                "current_tokens": 0,
            }

        entries = cache.work_logs
        summaries = cache.work_log_summaries

        total_tokens = sum(e.tokens for e in entries)

        return {
            "total_entries": len(entries)
            + sum(s.compressed_entries_count for s in summaries),
            "active_entries": len(entries),
            "compressed_summaries": len(summaries),
            "success_count": sum(1 for e in entries if e.success),
            "fail_count": sum(1 for e in entries if not e.success),
            "current_tokens": total_tokens,
        }

    # =========================================================================
    # KanbanStorage Interface Implementation
    # =========================================================================
    # GptsMemory 实现了 KanbanStorage 接口，提供看板的统一存储能力

    async def save_kanban(self, conv_id: str, kanban: "Kanban") -> None:
        """KanbanStorage接口: 保存看板.

        Args:
            conv_id: 会话ID
            kanban: 看板对象
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.kanban = kanban

        # 持久化到数据库
        if self._kanban_db_storage:
            try:
                kanban_data = {
                    "kanban_id": kanban.kanban_id,
                    "mission": kanban.mission,
                    "current_stage_index": kanban.current_stage_index,
                    "stages": [self._stage_to_dict(s) for s in kanban.stages],
                    "deliverables": dict(cache.deliverables),
                    "created_at": kanban.created_at,
                }
                await self._kanban_db_storage.save_kanban_async(
                    conv_id, conv_id, conv_id, kanban_data
                )
                logger.debug(f"Persisted kanban to db storage: {conv_id}")
            except Exception as e:
                logger.error(f"Failed to persist kanban to db: {e}")

        logger.debug(f"Saved kanban for {conv_id}: {kanban.kanban_id}")

    def _stage_to_dict(self, stage: "KanbanStage") -> Dict[str, Any]:
        """将 KanbanStage 转换为字典."""
        return {
            "stage_id": stage.stage_id,
            "description": stage.description,
            "status": stage.status,
            "deliverable_type": stage.deliverable_type,
            "deliverable_schema": stage.deliverable_schema,
            "deliverable_file": stage.deliverable_file,
            "work_log": [e.to_dict() for e in stage.work_log],
            "started_at": stage.started_at,
            "completed_at": stage.completed_at,
            "depends_on": stage.depends_on,
            "reflection": stage.reflection,
        }

    async def get_kanban(self, conv_id: str) -> Optional["Kanban"]:
        """KanbanStorage接口: 获取看板.

        优先从内存缓存获取，如果缓存不存在则从数据库加载。

        Args:
            conv_id: 会话ID

        Returns:
            看板对象，不存在返回 None
        """
        cache = await self._get_cache(conv_id)
        if cache and cache.kanban:
            return cache.kanban

        # 从数据库加载
        if self._kanban_db_storage:
            try:
                kanban_data = await self._kanban_db_storage.get_kanban_async(
                    conv_id, conv_id
                )
                if kanban_data:
                    kanban = self._dict_to_kanban(kanban_data)
                    cache = await self._get_or_create_cache(conv_id)
                    if cache:
                        cache.kanban = kanban
                        # 加载交付物
                        cache.deliverables = kanban_data.get("deliverables", {})
                    return kanban
            except Exception as e:
                logger.error(f"Failed to load kanban from db: {e}")

        return None

    def _dict_to_kanban(self, data: Dict[str, Any]) -> "Kanban":
        """从字典转换为 Kanban 对象."""
        stages = [self._dict_to_stage(s) for s in data.get("stages", [])]
        return Kanban(
            kanban_id=data.get("kanban_id", ""),
            mission=data.get("mission", ""),
            stages=stages,
            current_stage_index=data.get("current_stage_index", 0),
            created_at=data.get("created_at") or 0.0,
        )

    def _dict_to_stage(self, data: Dict[str, Any]) -> "KanbanStage":
        """从字典转换为 KanbanStage 对象."""
        work_log = [WorkEntry.from_dict(e) for e in data.get("work_log", [])]
        return KanbanStage(
            stage_id=data.get("stage_id", ""),
            description=data.get("description", ""),
            status=data.get("status", "working"),
            deliverable_type=data.get("deliverable_type", ""),
            deliverable_schema=data.get("deliverable_schema", {}),
            deliverable_file=data.get("deliverable_file", ""),
            work_log=work_log,
            started_at=data.get("started_at", 0.0),
            completed_at=data.get("completed_at", 0.0),
            depends_on=data.get("depends_on", []),
            reflection=data.get("reflection", ""),
        )

    async def delete_kanban(self, conv_id: str) -> bool:
        """KanbanStorage接口: 删除看板.

        Args:
            conv_id: 会话ID

        Returns:
            是否成功删除
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return False

        async with await self._get_conv_lock(conv_id):
            if cache.kanban:
                cache.kanban = None
                cache.pre_kanban_logs.clear()
                cache.deliverables.clear()

        # 从数据库删除
        if self._kanban_db_storage:
            try:
                await self._kanban_db_storage.delete_kanban_async(conv_id, conv_id)
                logger.debug(f"Deleted kanban from db storage: {conv_id}")
            except Exception as e:
                logger.error(f"Failed to delete kanban from db: {e}")

        return True

    async def save_deliverable(
        self,
        conv_id: str,
        stage_id: str,
        deliverable: Dict[str, Any],
        deliverable_type: str = "",
    ) -> str:
        """KanbanStorage接口: 保存交付物.

        Args:
            conv_id: 会话ID
            stage_id: 阶段ID
            deliverable: 交付物数据
            deliverable_type: 交付物类型

        Returns:
            交付物文件 key
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache:
            return ""

        key = f"{conv_id}_{stage_id}_deliverable"
        async with await self._get_conv_lock(conv_id):
            cache.deliverables[stage_id] = deliverable

            # 同时更新看板中阶段的交付物文件
            if cache.kanban:
                stage = cache.kanban.get_stage_by_id(stage_id)
                if stage:
                    stage.deliverable_file = key
                    stage.deliverable_type = deliverable_type

        logger.debug(f"Saved deliverable for {conv_id}/{stage_id}")
        return key

    async def get_deliverable(
        self, conv_id: str, stage_id: str
    ) -> Optional[Dict[str, Any]]:
        """KanbanStorage接口: 获取交付物.

        Args:
            conv_id: 会话ID
            stage_id: 阶段ID

        Returns:
            交付物数据，不存在返回 None
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return None
        return cache.deliverables.get(stage_id)

    async def get_all_deliverables(self, conv_id: str) -> Dict[str, Dict[str, Any]]:
        """KanbanStorage接口: 获取所有交付物.

        Args:
            conv_id: 会话ID

        Returns:
            {stage_id: deliverable} 字典
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return {}
        return dict(cache.deliverables)

    async def add_work_entry_to_stage(
        self,
        conv_id: str,
        stage_id: str,
        entry: "WorkEntry",
    ) -> bool:
        """KanbanStorage接口: 向指定阶段添加工作日志条目.

        Args:
            conv_id: 会话ID
            stage_id: 阶段ID
            entry: 工作日志条目

        Returns:
            是否成功添加
        """
        cache = await self._get_cache(conv_id)
        if not cache or not cache.kanban:
            return False

        async with await self._get_conv_lock(conv_id):
            stage = cache.kanban.get_stage_by_id(stage_id)
            if not stage:
                return False
            stage.work_log.append(entry)

        logger.debug(f"Added work entry to {conv_id}/{stage_id}")
        return True

    async def get_pre_kanban_logs(self, conv_id: str) -> List["WorkEntry"]:
        """KanbanStorage接口: 获取看板创建前的预研日志.

        Args:
            conv_id: 会话ID

        Returns:
            预研日志列表
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return []
        return list(cache.pre_kanban_logs)

    async def add_pre_kanban_log(
        self,
        conv_id: str,
        entry: "WorkEntry",
    ) -> None:
        """KanbanStorage接口: 添加预研日志条目.

        Args:
            conv_id: 会话ID
            entry: 工作日志条目
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.pre_kanban_logs.append(entry)

        logger.debug(f"Added pre-kanban log entry for {conv_id}")

    async def clear_pre_kanban_logs(self, conv_id: str) -> None:
        """KanbanStorage接口: 清空预研日志.

        Args:
            conv_id: 会话ID
        """
        cache = await self._get_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.pre_kanban_logs.clear()

        logger.debug(f"Cleared pre-kanban logs for {conv_id}")

    # =========================================================================
    # TodoStorage Interface Implementation
    # =========================================================================
    # GptsMemory 实现了 TodoStorage 接口，提供任务列表的统一存储能力
    # 参考 opencode 的 todowrite/todoread 设计，保持简洁

    async def write_todos(self, conv_id: str, todos: List["TodoItem"]) -> None:
        """TodoStorage接口: 写入任务列表.

        Args:
            conv_id: 会话ID
            todos: 任务列表
        """
        cache = await self._get_or_create_cache(conv_id)
        if not cache:
            return

        async with await self._get_conv_lock(conv_id):
            cache.todos = todos

        # 持久化到数据库存储后端
        if self._todo_db_storage:
            try:
                await self._todo_db_storage.write_todos(conv_id, todos)
                logger.debug(f"Persisted todos to db storage: {conv_id}")
            except Exception as e:
                logger.error(f"Failed to persist todos to db: {e}")

        logger.debug(f"Wrote {len(todos)} todos for {conv_id}")

    async def read_todos(self, conv_id: str) -> List["TodoItem"]:
        """TodoStorage接口: 读取任务列表.

        优先从内存缓存获取，如果缓存不存在则从数据库加载。

        Args:
            conv_id: 会话ID

        Returns:
            任务列表
        """
        cache = await self._get_cache(conv_id)
        if cache and cache.todos:
            return cache.todos

        # 从数据库加载
        if self._todo_db_storage:
            try:
                todos = await self._todo_db_storage.read_todos(conv_id)
                if todos:
                    cache = await self._get_or_create_cache(conv_id)
                    if cache:
                        cache.todos = todos
                    return todos
            except Exception as e:
                logger.error(f"Failed to load todos from db: {e}")

        return []

    async def clear_todos(self, conv_id: str) -> None:
        """TodoStorage接口: 清空任务列表.

        Args:
            conv_id: 会话ID
        """
        cache = await self._get_cache(conv_id)
        if cache:
            async with await self._get_conv_lock(conv_id):
                cache.todos.clear()

        # 从数据库删除
        if self._todo_db_storage:
            try:
                await self._todo_db_storage.clear_todos(conv_id)
                logger.debug(f"Cleared todos from db storage: {conv_id}")
            except Exception as e:
                logger.error(f"Failed to clear todos from db: {e}")
