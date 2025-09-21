import asyncio
import logging
from typing import Union, Optional, Any, List, AsyncGenerator, Tuple, Coroutine

from fastapi import BackgroundTasks

from derisk.core import HumanMessage
from derisk_serve.agent.agents.chat.agent_chat import AgentChat, _format_vis_msg
from derisk_serve.building.config.api.schemas import ChatInParamValue

logger = logging.getLogger(__name__)


class SimpleAgentChat(AgentChat):
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
        **ext_info: Any
    ) -> Union[AsyncGenerator[str, None], Tuple[str,str]]:
        """简单对话入口(构建会话、发起Agent对话、处理连接中断、保存对话历史)

        Args:
            conv_uid: 会话ID
            gpts_name: 要对话的智能体名称
            user_query: 用户消息，支持多模态
            background_tasks: FastAPI后台任务
            specify_config_code: 指定配置代码
            user_code: 用户代码
            sys_code: 系统代码
            stream: 是否使用流式响应
            chat_call_back: 对话回调函数
            chat_in_params: 对话输入参数
            **ext_info: 扩展信息

        Yields:
            str: 对话响应内容

        Raises:
            asyncio.CancelledError: 客户端断开连接
            Exception: 其他异常
        """
        logger.info(f"Simple agent chat initiated - GPT: {gpts_name}, Query: {user_query}, Session: {conv_uid}")

        current_message = None
        agent_conv_id = None
        agent_task: Optional[Coroutine] = None
        error_info: Optional[str] = None

        try:
            # 初始化对话
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

            # 处理对话流
            async for task, chunk, conv_id in self.aggregation_chat(
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
                agent_task = task
                yield chunk, agent_conv_id

        except asyncio.CancelledError:
            logger.warning("Client connection terminated")
            if agent_task:
                logger.info(f"Cancelling chat with {gpts_name} (Conversation ID: {agent_conv_id})")
                agent_task.cancel()
            yield _format_vis_msg("Client connection terminated!"), agent_conv_id

        except Exception as e:
            error_msg = f"Chat with {gpts_name} failed (Conversation ID: {agent_conv_id}) - {str(e)}"
            logger.exception(error_msg)
            error_info = str(e)
            if agent_task:
                logger.info(f"Exception chat with {gpts_name} (Conversation ID: {agent_conv_id})")
                agent_task.cancel()
            yield _format_vis_msg(error_info), agent_conv_id

        finally:
            logger.info(f"Saving conversation history for session {conv_uid}")
            try:
                await self.save_conversation(
                    conv_session_id=conv_uid,
                    agent_conv_id=agent_conv_id,
                    current_message=current_message,
                    err_msg=error_info,
                    chat_call_back=chat_call_back
                )
            except Exception as e:
                logger.error(f"Failed to save conversation: {e}")
                yield f"Failed to save conversation: {e}", agent_conv_id
