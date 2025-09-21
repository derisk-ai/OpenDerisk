import asyncio
import logging
from typing import Union, Optional, Any, List, AsyncGenerator, Tuple
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks

from derisk.core import HumanMessage, StorageConversation
from derisk_serve.agent.agents.chat.agent_chat import AgentChat, _format_vis_msg
from derisk_serve.building.config.api.schemas import ChatInParamValue

logger = logging.getLogger(__name__)


class ChatState:
    """聊天状态管理类"""

    def __init__(self):
        self.agent_conv_id: Optional[str] = None
        self.error: Optional[str] = None
        self._lock = asyncio.Lock()

    async def update(self, conv_id: Optional[str] = None, error: Optional[str] = None) -> None:
        """原子化更新状态"""
        async with self._lock:
            if conv_id is not None:
                self.agent_conv_id = conv_id
            if error is not None:
                self.error = error

    async def get_state(self) -> Tuple[Optional[str], Optional[str]]:
        """获取当前状态"""
        async with self._lock:
            return self.agent_conv_id, self.error


class BackGroundAgentChat(AgentChat):
    @asynccontextmanager
    async def _manage_chat_session(self, conv_uid: str, user_query: Union[str, HumanMessage],
                                   gpts_name: str, **ext_info) -> AsyncGenerator[
        Tuple[ChatState, asyncio.Queue, StorageConversation], None]:
        """管理聊天会话的上下文"""
        state = ChatState()
        task_queue: asyncio.Queue = asyncio.Queue()

        # 初始化会话
        current_message = await self._initialize_conversation(
            conv_session_id=conv_uid,
            app_code=gpts_name,
            user_query=user_query,
            user_code=ext_info.get('user_code')
        )

        try:
            yield state, task_queue, current_message
        finally:
            # 确保队列中的所有消息都被处理
            while not task_queue.empty():
                try:
                    task_queue.get_nowait()
                    task_queue.task_done()
                except asyncio.QueueEmpty:
                    break

    async def _process_agent_chat(self,
                                  state: ChatState,
                                  task_queue: asyncio.Queue,
                                  conv_uid: str, gpts_name: str,
                                  user_query: Union[str, HumanMessage],
                                  chat_call_back: Optional[Any] = None,
                                  chat_in_params: Optional[List[ChatInParamValue]] = None,
                                  **kwargs) -> None:
        """处理智能体对话的核心逻辑"""
        try:
            agent_conv_id, gpts_conversations = await self._initialize_agent_conversation(
                conv_session_id=conv_uid, **kwargs
            )

            async for task, chunk, agent_conv_id in self.aggregation_chat(
                conv_id=conv_uid,
                agent_conv_id=agent_conv_id,
                gpts_name=gpts_name,
                user_query=user_query,
                gpts_conversations=gpts_conversations,
                chat_call_back=chat_call_back,
                chat_in_params=chat_in_params,
                **kwargs
            ):
                await state.update(conv_id=agent_conv_id)
                await task_queue.put((chunk, agent_conv_id))

        except Exception as e:
            logger.exception(f"Agent chat error: {e}")
            await state.update(error=str(e))
            current_agent_conv_id = (await state.get_state())[0]
            await task_queue.put((_format_vis_msg(str(e)), current_agent_conv_id))
            # 发生异常时抛出以中断处理
            raise

    async def _stream_response(self, state: ChatState, task_queue: asyncio.Queue,
                               processing_complete: asyncio.Event,
                               processor_task: asyncio.Task) -> AsyncGenerator[str, None]:
        """生成响应流"""
        while not (processing_complete.is_set() and task_queue.empty()):
            # 首先检查处理任务是否有异常
            if processor_task.done():
                exc = processor_task.exception()
                if exc:
                    raise exc

            try:
                timeout = 1.0 if not processing_complete.is_set() else 0.1
                chunk, agent_conv_id = await asyncio.wait_for(
                    task_queue.get(), timeout=timeout
                )

                agent_conv_id, error = await state.get_state()
                yield chunk + ("\n" + error if error else ""), agent_conv_id
                task_queue.task_done()

            except asyncio.TimeoutError:
                if processing_complete.is_set() and task_queue.empty():
                    break
                continue

    async def _cleanup_conversation(self, processor_task: asyncio.Task,
                                    state: ChatState, conv_uid: str,
                                    current_message: StorageConversation,
                                    chat_call_back: Optional[Any]) -> None:
        """清理会话资源"""
        try:
            await asyncio.shield(processor_task)
        except Exception as e:
            logger.exception(f"Processor task cleanup error: {e}")
        finally:
            agent_conv_id, error = await state.get_state()
            await self.save_conversation(
                conv_uid,
                agent_conv_id,
                current_message,
                err_msg=error,
                chat_call_back=chat_call_back,
            )
            logger.debug(f"Conversation persisted: {conv_uid}")

    async def chat(
        self,
        conv_uid: str,
        gpts_name: str,
        user_query: Union[str, HumanMessage],
        background_tasks: Optional[BackgroundTasks] = None,
        specify_config_code: Optional[str] = None,
        user_code: Optional[str] = None,
        sys_code: Optional[str] = None,
        stream: bool = True,
        chat_call_back: Optional[Any] = None,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info
    ) -> AsyncGenerator[str, None]:
        """处理聊天请求的主入口"""
        logger.info(f"Simple app chat: {gpts_name}, {user_query}, {conv_uid}")

        async with self._manage_chat_session(conv_uid, user_query, gpts_name, **ext_info) as (
            state, task_queue, current_message):
            processing_complete = asyncio.Event()

            # 创建并启动处理任务
            processor_task = asyncio.create_task(
                self._process_agent_chat(
                    state, task_queue, conv_uid, gpts_name, user_query,
                    user_code=user_code,
                    sys_code=sys_code,
                    specify_config_code=specify_config_code,
                    stream=stream,
                    chat_in_params=chat_in_params,
                    chat_call_back=chat_call_back,
                    **ext_info
                )
            )

            try:
                async for chunk, agent_conv_id in self._stream_response(state, task_queue, processing_complete, processor_task):  # 传入 processor_task
                    yield chunk, agent_conv_id
            except asyncio.CancelledError:
                logger.info(f"Client disconnected: {conv_uid}")
                processor_task.cancel()  # 确保取消处理任务
            except Exception as e:
                processor_task.cancel()
                logger.exception(f"Chat [{conv_uid}] exception！")
                raise
            finally:
                processing_complete.set()
                # 添加清理任务
                background_tasks.add_task(
                    self._cleanup_conversation,
                    processor_task, state, conv_uid,
                    current_message, chat_call_back
                )