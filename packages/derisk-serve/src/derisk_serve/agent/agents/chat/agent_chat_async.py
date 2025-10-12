import asyncio
import logging
from typing import Union, Optional, Any, List, Tuple

from fastapi import BackgroundTasks

from derisk.core import HumanMessage
from derisk_serve.agent.agents.chat.agent_chat import AgentChat
from derisk_serve.building.config.api.schemas import ChatInParamValue

logger = logging.getLogger(__name__)


class AsyncAgentChat(AgentChat):
    async def chat(
        self,
        conv_uid: str,
        gpts_name: str,
        user_query: Union[str, HumanMessage],
        background_tasks: Optional[BackgroundTasks] = None,  # FastAPI的后台任务
        specify_config_code: Optional[str] = None,
        user_code: Optional[str] = None,
        sys_code: Optional[str] = None,
        stream: bool = True,
        chat_call_back: Optional[Any] = None,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info
    ) -> Tuple[Optional[str], Optional[str]]:
        """异步智能体对话

        Args:
            conv_uid: 会话id
            gpts_name: 智能体名称
            user_query: 用户输入(支持多模态)
            background_tasks: 后台任务
            specify_config_code: 指定配置代码
            user_code: 用户代码
            sys_code: 系统代码
            stream: 是否流式响应
            chat_call_back: 对话回调函数
            chat_in_params: 聊天输入参数
            ext_info: 扩展信息

        Returns:
            Tuple[Optional[str], Optional[str]]: (首个响应chunk, agent会话ID)

        Raises:
            TimeoutError: 响应超时
            asyncio.CancelledError: 任务被取消
            Exception: 其他异常
        """
        logger.info(f"Async app chat: gpts_name={gpts_name}, query={user_query}, conv_uid={conv_uid}")

        # 初始化会话
        current_message = await self._initialize_conversation(
            conv_session_id=conv_uid,
            app_code=gpts_name,
            user_query=user_query,
            user_code=user_code
        )

        agent_conv_id, gpts_conversations = await self._initialize_agent_conversation(
            conv_session_id=conv_uid,
            **ext_info
        )

        first_chunk_event = asyncio.Event()
        first_chunk_data = None
        processor_task = None

        async def process_agent_response():
            nonlocal first_chunk_data, agent_conv_id
            agent_exception = None
            try:
                async for task, chunk, new_conv_id in self.aggregation_chat(
                    conv_id=conv_uid,
                    agent_conv_id=agent_conv_id,
                    gpts_name=gpts_name,
                    user_query=user_query,
                    user_code=user_code,
                    sys_code=sys_code,
                    chat_in_params=chat_in_params,
                    specify_config_code=specify_config_code,
                    gpts_conversations=gpts_conversations,
                    stream=stream,
                    **ext_info
                ):
                    if new_conv_id:
                        agent_conv_id = new_conv_id

                    if not first_chunk_event.is_set():
                        first_chunk_data = chunk
                        first_chunk_event.set()

                    logger.debug(f"Processing chunk with agent_conv_id: {agent_conv_id}")

            except Exception as e:
                logger.error(f"Agent processing failed: {str(e)}", exc_info=True)
                agent_exception = str(e)
                if not first_chunk_event.is_set():
                    first_chunk_event.set()
            finally:
                await self.save_conversation(
                    conv_uid,
                    agent_conv_id,
                    current_message,
                    err_msg=agent_exception,
                    chat_call_back=chat_call_back,
                )

        try:
            # 创建处理任务
            processor_task = asyncio.create_task(process_agent_response())

            # 将处理任务添加到background_tasks以确保其持续运行
            if background_tasks:
                background_tasks.add_task(lambda: processor_task)

            # 等待第一个chunk（设置超时时间）
            await asyncio.wait_for(first_chunk_event.wait(), timeout=60.0)

            return first_chunk_data, agent_conv_id

        except asyncio.TimeoutError:
            # 超时时不取消处理任务，让它继续在后台运行
            raise TimeoutError("Response timeout")
        except Exception as e:
            # 只有在非取消错误时才取消处理任务
            if not isinstance(e, asyncio.CancelledError) and processor_task and not processor_task.done():
                processor_task.cancel()
            raise
