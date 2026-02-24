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
class GptsMemory(FileMetadataStorage):
    """会话全局消息记忆管理（包含文件元数据管理）.

    同时实现了FileMetadataStorage接口，可作为AgentFileSystem的存储后端。
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
    async def append_file(self, conv_id: str, file_metadata: AgentFileMetadata, save_db: bool = True):
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
            try:
                await blocking_func_to_async(
                    self._executor, self._file_memory.append, file_metadata
                )
                logger.debug(f"Saved file metadata to DB: {file_metadata.file_id}")
            except Exception as e:
                logger.error(f"Failed to save file metadata to DB: {e}")

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
            # 从持久化存储加载
            files = await blocking_func_to_async(
                self._executor, self._file_memory.get_by_conv_id, conv_id
            )
            async with await self._get_conv_lock(conv_id):
                for f in files:
                    cache.files[f.file_id] = f
                    cache.file_key_index[f.file_key] = f.file_id
            return files
        return list(cache.files.values())

    async def get_file_by_id(self, conv_id: str, file_id: str) -> Optional[AgentFileMetadata]:
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

    async def get_file_by_key(self, conv_id: str, file_key: str) -> Optional[AgentFileMetadata]:
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
        return None

    async def get_files_by_type(self, conv_id: str, file_type: Union[str, FileType]) -> List[AgentFileMetadata]:
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
            return [
                f for f in cache.files.values()
                if f.file_type == target_type
            ]

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

        # 将catalog映射保存到file_memory
        try:
            for file_key, file_id in cache.file_key_index.items():
                await blocking_func_to_async(
                    self._executor, self._file_memory.save_catalog, conv_id, file_key, file_id
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
        self,
        conv_id: str,
        file_type: Optional[Union[str, "FileType"]] = None
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
        try:
            await blocking_func_to_async(
                self._executor, self._file_memory.delete_by_file_key, conv_id, file_key
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
        await blocking_func_to_async(
            self._executor, self._file_memory.delete_by_conv_id, conv_id
        )
