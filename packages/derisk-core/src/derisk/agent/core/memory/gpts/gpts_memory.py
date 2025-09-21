"""GPTs Memory Module (Optimized Version)"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from asyncio import Queue
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional, Union, Any, Generator
from cachetools import TTLCache

from derisk.util.executor_utils import blocking_func_to_async
from .base import GptsMessage, GptsMessageMemory, GptsPlansMemory, GptsPlan
from .default_gpts_memory import DefaultGptsMessageMemory, DefaultGptsPlansMemory
from ...action.base import ActionOutput
from .....util.id_generator import IdGenerator
from .....vis.vis_converter import VisProtocolConverter, DefaultVisConverter

logger = logging.getLogger(__name__)


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
        *,
        ttl: int = 3600,
        maxsize: int = 1000
    ):
        self.conv_id = conv_id

        # 核心缓存（自动过期）
        self.messages = TTLCache(maxsize=maxsize, ttl=ttl)  # {message_id: GptsMessage}
        self.plans = TTLCache(maxsize=maxsize, ttl=ttl)  # 计划缓存

        # agent引用缓存
        self.senders = TTLCache(maxsize=maxsize, ttl=ttl)  # {agent_name: Agent}

        # 辅助数据结构
        self.message_ids: List[str] = []  # 消息ID顺序
        self.channel = Queue()  # 消息队列
        self.round_generator = IdGenerator(start_round + 1)  # 轮次生成器
        self.vis_converter = vis_converter  # 可视化处理器
        self.start_round = start_round  # 起始轮次
        self.stop_flag = False

    def touch(self):
        """更新缓存访问时间（续期TTL）"""
        self.messages.expire()
        self.plans.expire()

    def is_expired(self, current_time: float) -> bool:
        """判断会话是否过期（示例逻辑）"""
        return False

    def update_vis_converter(self, converter: VisProtocolConverter):
        logger.info(f"update_vis_converter：{self.conv_id},{converter}")
        self.vis_converter = converter

    def clear(self):
        """清理所有资源"""
        # 清理内存缓存
        self.messages.clear()
        self.plans.clear()
        self.senders.clear()

        # 无需调用 close()，直接重新初始化队列
        self.channel = Queue()  # 替换为新的队列实例

        # 清理顺序列表
        self.message_ids.clear()

    def get_messages_ordered(self) -> List[GptsMessage]:
        """获取有序消息列表"""
        # return [self.messages[msg_id] for msg_id in self.message_ids if msg_id in self.messages]
        return [message for msg_id in self.message_ids if (message := self.messages.get(msg_id, None))]

    def get_plans_list(self) -> List[GptsPlan]:
        """获取计划列表"""
        return list(self.plans.values())


# --------------------------
# 2. 全局内存管理
# --------------------------
class GptsMemory:
    """会话全局消息记忆管理"""

    def __init__(
        self,
        plans_memory: GptsPlansMemory = DefaultGptsPlansMemory(),
        message_memory: GptsMessageMemory = DefaultGptsMessageMemory(),
        executor: Executor = ThreadPoolExecutor(max_workers=2),
        default_vis_converter: VisProtocolConverter = DefaultVisConverter(),
        *,
        cache_ttl: int = 3600,
        cache_maxsize: int = 1000
    ):
        # 持久化存储
        self._plans_memory = plans_memory
        self._message_memory = message_memory
        self._executor = executor

        # 可视化默认转换器
        self._default_vis_converter = default_vis_converter

        # 会话缓存管理 {conv_id: ConversationCache}
        # 使用 TTLCache 替代 WeakValueDictionary
        self._conversations = TTLCache(
            maxsize=100,
            ttl=cache_ttl,
            timer=time.time  # 使用系统时间计时
        )

        self._cache_ttl = cache_ttl
        self._cache_maxsize = cache_maxsize

        # 后台清理线程
        self._cleanup_running = True
        # self._cleanup_thread = threading.Thread(
        #     target=self._auto_cleanup,
        #     daemon=True
        # )
        # self._cleanup_thread.start()

    @property
    def plans_memory(self) -> GptsPlansMemory:
        return self._plans_memory

    @property
    def message_memory(self) -> GptsMessageMemory:
        return self._message_memory

    # --------------------------
    # 内部结构功能区
    # --------------------------
    def _auto_cleanup(self):
        """后台自动清理过期会话"""
        while self._cleanup_running:
            time.sleep(300)  # 每5分钟检查一次
            current_time = time.time()
            stale_conv_ids = [
                conv_id for conv_id, cache in self._conversations.items()
                if cache.is_expired(current_time)
            ]
            for conv_id in stale_conv_ids:
                self.clear(conv_id)
            self._conversations.expire()

    def clear(self, conv_id: str):
        """清理会话资源（兼容原版功能）"""
        logger.info(f"memory clear {conv_id}")
        if cache := self._conversations.pop(conv_id, None):
            # 清理缓存
            cache.clear()
            logger.info(f"Cleared conversation cache: {conv_id}")

    def __del__(self):
        """析构时停止清理线程"""
        logger.info(f"memory对象被释放！")
        self._cleanup_running = False
        # if self._cleanup_thread.is_alive():
        #     self._cleanup_thread.join()

    # --------------------------
    # 内部缓存操作方法
    # --------------------------
    def _get_cache(self, conv_id: str) -> Optional[ConversationCache]:
        """获取已存在的缓存"""
        if cache := self._conversations.get(conv_id):
            cache.touch()
            return cache
        return None
        # raise KeyError(f"Conversation {conv_id} not initialized")

    def _get_or_create_cache(
        self,
        conv_id: str,
        start_round: int = 0,
        vis_converter: Optional[VisProtocolConverter] = None,
    ) -> ConversationCache:
        """获取或创建会话缓存"""
        if conv_id not in self._conversations:
            logger.info(
                f"对话{conv_id}不在缓存中，构建新缓存！可视化组件:{vis_converter.render_name if vis_converter else ''}")
            self._conversations[conv_id] = ConversationCache(
                conv_id=conv_id,
                vis_converter=vis_converter or self._default_vis_converter,
                start_round=start_round,
                ttl=self._cache_ttl,
                maxsize=self._cache_maxsize
            )
        return self._conversations[conv_id]

    def _cache_messages(self, conv_id: str, messages: List[GptsMessage]):
        """缓存消息"""
        cache = self._get_cache(conv_id)
        for msg in messages:
            cache.messages[msg.message_id] = msg
            if msg.message_id not in cache.message_ids:
                cache.message_ids.append(msg.message_id)

    async def load_persistent_memory(self, conv_id: str):
        """加载持久化数据"""
        cache = self._get_cache(conv_id)
        ## 加载持久化的消息数据
        if not cache.message_ids:
            messages = await blocking_func_to_async(
                self._executor, self._message_memory.get_by_conv_id, conv_id
            )
            self._cache_messages(conv_id, messages)

        ## 加载持久化的规划信息
        if not cache.plans.currsize:
            plans = await blocking_func_to_async(
                self._executor, self._plans_memory.get_by_conv_id, conv_id
            )
            cache.plans.update({p.task_uid: p for p in plans})

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

    def queue(self, conv_id: str) -> Optional[Queue]:
        """获取会话消息队列"""
        return self._get_cache(conv_id).channel if conv_id in self._conversations else None

    # --------------------------
    # 外部核心方法区
    # --------------------------
    def init(self, conv_id: str, history_messages: List[GptsMessage] = None,
             vis_converter: VisProtocolConverter = None, start_round: int = 0):
        """初始化会话"""
        cache = self._get_or_create_cache(
            conv_id,
            start_round,
            vis_converter or self._default_vis_converter,
        )
        if history_messages:
            self._cache_messages(conv_id, history_messages)

    def init_message_senders(self, conv_id: str, senders: List["ConversableAgent"]):
        """初始化消息发送者"""
        cache = self._get_cache(conv_id)
        for agent in senders:
            cache.senders[agent.name] = agent

    def vis_converter(self, agent_conv_id: str):
        """Return the vis converter"""
        cache = self._get_cache(agent_conv_id)
        if cache:
            return cache.vis_converter
        else:
            logger.error(f"{agent_conv_id} cache is cleaned!")
            return None

    async def next_message_rounds(self, conv_id: str, new_init_round: Optional[int] = None) -> int:
        """获取下一个消息轮次"""
        cache = self._get_cache(conv_id)
        return await cache.round_generator.next(new_init_round)

    async def vis_final(self, conv_id: str) -> Any:
        """生成最终可视化视图"""

        messages = await self.get_messages(conv_id)

        cache = self._get_cache(conv_id)
        messages = messages[cache.start_round:]  # 应用起始轮次偏移

        # 合并消息 (原版逻辑)
        messages = self._merge_messages(messages)
        plans = {p.task_uid: p for p in cache.get_plans_list()}
        vis_convert = cache.vis_converter
        if not vis_convert:
            logger.warning(f"{conv_id} vis_convert is None!临时构建默认渲染器！")
            vis_convert = DefaultVisConverter()
        final_view = await vis_convert.final_view(
            messages=messages,
            plans_map=plans,
            senders_map=dict(cache.senders)
        )
        if cache.stop_flag:
            final_view = final_view
        return final_view

    async def user_answer(self, conv_id: str) -> str:
        messages = await self.get_messages(conv_id)
        cache = self._get_cache(conv_id)
        messages = messages[cache.start_round:]  # 应用起始轮次偏移
        reversed_messages = messages.copy()
        reversed_messages.reverse()
        from ...user_proxy_agent import HUMAN_ROLE
        final_content = None
        for message in reversed_messages:
            action_report_str = message.action_report
            content_view = message.content
            if action_report_str and len(action_report_str) > 0:
                action_out = ActionOutput.from_dict(json.loads(action_report_str))
                if action_out is not None:  # noqa
                    content_view = action_out.content
            if final_content == None:
                final_content = content_view
            if message.receiver == HUMAN_ROLE:
                return content_view
        return final_content

    async def vis_messages(
        self,
        conv_id: str,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[GptsPlan]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        senders_map: Optional[Dict[str, "ConversableAgent"]] = None
    ) -> Any:
        """生成消息可视化视图"""
        cache = self._get_cache(conv_id)
        messages = await self.get_messages(conv_id)
        messages = messages[cache.start_round:]  # 应用起始轮次偏移

        # 合并消息 (原版逻辑)
        messages = self._merge_messages(messages)
        all_plans = {p.task_uid: p for p in cache.get_plans_list()}

        return await cache.vis_converter.visualization(
            messages=messages,
            plans_map=all_plans,
            gpt_msg=gpt_msg,
            stream_msg=stream_msg,
            new_plans=new_plans,
            is_first_chunk=is_first_chunk,
            incremental=incremental,
            senders_map=senders_map or cache.senders
        )

    async def chat_messages(
        self,
        conv_id: str,
    ) -> Generator[Any, None, None]:
        """获取对话消息流"""
        cache = self._get_cache(conv_id)
        while True:
            item = await cache.channel.get()
            if item == "[DONE]":
                cache.channel.task_done()
                break
            else:
                yield item
                await asyncio.sleep(0.005)

    async def complete(self, conv_id: str):
        """标记对话完成"""
        logger.info(f"完成会话[{conv_id}]")
        cache = self._get_cache(conv_id)
        await cache.channel.put("[DONE]")

    async def stop(self, conv_id: str):

        cache = self._get_cache(conv_id)
        cache.stop_flag = True

    async def have_memory_cache(self, conv_id: str):
        cache = self._get_cache(conv_id)
        if cache:
            return True
        else:
            return False

    async def append_message(
        self,
        conv_id: str,
        message: GptsMessage,
        incremental: bool = False,
        save_db: bool = True,
        sender: Optional["ConversableAgent"] = None
    ):
        """追加消息"""
        cache = self._get_cache(conv_id)

        message.updated_at = datetime.now()
        # 缓存消息
        if cache:
            cache.messages[message.message_id] = message
            if message.message_id not in cache.message_ids:
                cache.message_ids.append(message.message_id)

        # 持久化存储
        if save_db:
            await blocking_func_to_async(
                self._executor, self._message_memory.update, message
            )

        # 推送显示消息
        await self.push_message(
            conv_id, gpt_msg=message, incremental=incremental, sender=sender
        )

    async def get_agent_messages(self, conv_id: str, agent: str) -> List[GptsMessage]:
        """获取指定代理的消息"""
        messages = await self.get_messages(conv_id)
        return [
            msg for msg in messages
            if msg.sender == agent or msg.receiver == agent
        ]

    async def get_agent_history_memory(
        self, conv_id: str, agent_role: str
    ) -> List[ActionOutput]:
        """获取代理历史记忆"""
        agent_messages = await blocking_func_to_async(
            self._executor, self._message_memory.get_by_agent, conv_id, agent_role
        )
        new_list = []
        for i in range(0, len(agent_messages), 2):
            if i + 1 >= len(agent_messages):
                break
            action_report = None
            if agent_messages[i + 1].action_report:
                try:
                    action_report = ActionOutput.from_dict(
                        json.loads(agent_messages[i + 1].action_report)
                    )
                except json.JSONDecodeError:
                    logger.error(f"Invalid action_report format: {agent_messages[i + 1].action_report}")
            new_list.append({
                "question": agent_messages[i].content,
                "ai_message": agent_messages[i + 1].content,
                "action_output": action_report,
                "check_pass": agent_messages[i + 1].is_success,
            })
        return [m["action_output"] for m in new_list if m["action_output"]]

    async def append_plans(
        self,
        conv_id: str,
        plans: List[GptsPlan],
        incremental: bool = False,
        sender: Optional["ConversableAgent"] = None,
        need_storage: bool = True
    ):
        """追加计划"""
        cache = self._get_cache(conv_id)
        if cache:
            # 更新缓存
            for plan in plans:
                plan.created_at = datetime.now()
                cache.plans[plan.task_uid] = plan
        # 推送显示
        await self.push_message(
            conv_id, new_plans=plans, incremental=incremental, sender=sender
        )
        if need_storage:
            # 持久化存储
            await blocking_func_to_async(
                self._executor, self._plans_memory.batch_save, plans
            )

    async def update_plan(
        self,
        conv_id: str,
        plan: GptsPlan,
        incremental: bool = False
    ):
        """更新计划"""
        logger.info(f"update_plan:{conv_id},{plan}")

        plan.updated_at = datetime.now()
        # 持久化更新
        await blocking_func_to_async(
            self._executor, self._plans_memory.update_by_uid,
            conv_id, plan.task_uid, plan.state, plan.retry_times,
            model=plan.agent_model, result=plan.result
        )

        # 更新缓存
        cache = self._get_cache(conv_id)
        if plan.task_uid in cache.plans:
            existing = cache.plans[plan.task_uid]
            existing.state = plan.state
            existing.retry_times = plan.retry_times
            existing.agent_model = plan.agent_model
            existing.result = plan.result

        # 推送显示
        await self.push_message(
            conv_id, new_plans=[plan], incremental=incremental
        )

        logger.info(f"update_plan {conv_id}:{plan.task_uid} success！")

    async def get_plans(self, conv_id: str) -> List[GptsPlan]:
        """获取所有计划"""
        cache = self._get_cache(conv_id)
        return list(cache.plans.values())

    async def get_plan(self, conv_id: str, task_uid: str) -> Optional[GptsPlan]:
        """获取所有计划"""
        cache = self._get_cache(conv_id)
        for item in list(cache.plans.values()):
            if item.task_uid == task_uid:
                return item
        return None

    async def get_planner_plans(self, conv_id: str, planner: str) -> List[GptsPlan]:
        """获取所有计划"""
        cache = self._get_cache(conv_id)
        planner_plans: List = []
        for item in list(cache.plans.values()):
            if item.planning_agent == planner:
                planner_plans.append(item)
        return planner_plans

    async def get_by_planner_and_round(self, conv_id: str, planner: str, round_id: str) -> List[GptsPlan]:
        cache = self._get_cache(conv_id)
        planner_plans: List = []
        for item in list(cache.plans.values()):
            if item.planning_agent == planner and item.conv_round_id == round_id:
                planner_plans.append(item)
        return planner_plans

    async def push_message(
        self,
        conv_id: str,
        gpt_msg: Optional[GptsMessage] = None,
        stream_msg: Optional[Union[Dict, str]] = None,
        new_plans: Optional[List[GptsPlan]] = None,
        is_first_chunk: bool = False,
        incremental: bool = False,
        sender: Optional["ConversableAgent"] = None
    ):
        """推送消息（兼容原版逻辑）"""
        cache = self._get_cache(conv_id)
        if not cache:
            return

        if cache.stop_flag:
            raise ValueError("当前会话已经停止！")

        # 更新发送者缓存
        if sender:
            cache.senders[sender.name] = sender

        # 原版HUMAN_ROLE过滤逻辑
        from derisk.agent.core.user_proxy_agent import HUMAN_ROLE
        if gpt_msg and gpt_msg.sender == HUMAN_ROLE:
            return

        # 处理视图生成
        final_view = await self.vis_messages(
            conv_id,
            gpt_msg=gpt_msg,
            stream_msg=stream_msg,
            new_plans=new_plans,
            is_first_chunk=is_first_chunk,
            incremental=incremental,
            senders_map=cache.senders
        )
        if final_view:
            # 推送至队列
            await cache.channel.put(final_view)

    async def get_messages(self, conv_id: str) -> List[GptsMessage]:
        """获取有序消息（兼容原版功能）"""
        cache = self._get_or_create_cache(conv_id)

        await self.load_persistent_memory(conv_id)

        messages = cache.get_messages_ordered()
        # 按轮次排序
        messages.sort(key=lambda x: x.rounds)
        return messages
