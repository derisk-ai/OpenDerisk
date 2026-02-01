import asyncio
import logging
from typing import Union, Optional, Any, List, Tuple

from fastapi import BackgroundTasks

from derisk.core import HumanMessage
from derisk.util.date_utils import current_ms
from derisk.util.tracer import root_tracer
from derisk_serve.agent.agents.chat.agent_chat import AgentChat
from derisk_serve.building.config.api.schemas import ChatInParamValue

logger = logging.getLogger(__name__)


class AsyncAgentChat(AgentChat):
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
    ) -> Tuple[Optional[str], Optional[str]]:
        # logger.info(f"Async app chat: gpts_name={gpts_name}, query={user_query}, conv_uid={conv_uid}")
        start_ms = root_tracer.get_context_entrance_ms() or current_ms()
        ttft = None
        span = root_tracer.start_span(
            "agent_chat",
            metadata={
                "chat_type": "async",
                "app_code": gpts_name,
                "ttft": None,
                "succeed": False,
            }
        )

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
        span.metadata["conv_id"] = agent_conv_id

        # 创建后台处理任务
        async def process_agent_response():
            nonlocal agent_conv_id
            first_chunk_ms = None

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

                    # 记录第一个chunk到达时间（仅用于内部记录）
                    if first_chunk_ms is None:
                        first_chunk_ms = current_ms()
                        logger.debug(f"First chunk received at {first_chunk_ms}")
                        ttft = current_ms() - start_ms
                        span.metadata["ttft"] = ttft
                        root_tracer.start_span("agent.ttft", metadata={"ttft": ttft}).end()
            except Exception as e:
                logger.error(f"Agent processing failed: {str(e)}", exc_info=True)
                agent_exception = str(e)
            finally:
                # 确保保存对话结果（无论是否出错）
                await self.save_conversation(
                    conv_uid,
                    agent_conv_id,
                    current_message,
                    err_msg=agent_exception,
                    chat_call_back=chat_call_back,
                    first_chunk_ms=first_chunk_ms,  # 可能为None
                )
                span.metadata["succeed"] = True
                span.end()

        try:
            # 启动后台任务
            processor_task = asyncio.create_task(process_agent_response())
            if background_tasks:
                background_tasks.add_task(lambda: processor_task)

            # 直接返回对话ID（不等待任何chunk）
            logger.info(f"async chat [{agent_conv_id}] return!")
            return None, agent_conv_id  # 第一个返回值设为None
        except Exception as e:
            raise
        finally:
            pass
