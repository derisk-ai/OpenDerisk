import asyncio
import logging
from typing import Union, Optional, Any, List

from fastapi import BackgroundTasks

from derisk.core import HumanMessage
from derisk.util.date_utils import current_ms
from derisk.util.tracer import root_tracer
from derisk_serve.agent.agents.chat.agent_chat import AgentChat
from derisk_serve.building.config.api.schemas import ChatInParamValue

logger = logging.getLogger(__name__)
class QuickAgentChat(AgentChat):
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
    ):
        logger.info(f"quick app chat:{gpts_name},{user_query},{conv_uid}")
        start_ms = root_tracer.get_context_entrance_ms() or current_ms()
        ttft = None
        span = root_tracer.start_span(
            "agent_chat",
            metadata={
                "chat_type": "quick",
                "app_code": gpts_name,
                "ttft": None,
                "succeed": False,
            }
        )

        current_message = await self._initialize_conversation(conv_session_id=conv_uid, app_code=gpts_name, user_query=user_query, user_code=user_code)
        agent_conv_id, gpts_conversations = await self._initialize_agent_conversation(conv_session_id=conv_uid, **ext_info)
        span.metadata["conv_id"] = agent_conv_id

        agent_task = None
        error_info = None
        first_chunk_ms = None
        try:
            ## TODO 是否需要额外的快速对话入口？ 指定Agent模版和资源开始对话？
            async for task, chunk, agent_conv_id in self.aggregation_chat(
                conv_uid,
                agent_conv_id,
                gpts_name,
                user_query,
                user_code,
                sys_code,
                chat_in_params=chat_in_params,
                specify_config_code=specify_config_code,
                gpts_conversations=gpts_conversations,
                stream=stream,
                **ext_info,
            ):
                agent_task = task
                first_chunk_ms = first_chunk_ms if first_chunk_ms is not None else current_ms()
                if ttft is None:
                    ttft = current_ms() - start_ms
                    span.metadata["ttft"] = ttft
                    root_tracer.start_span("agent.ttft", metadata={"ttft": ttft}).end()
                yield chunk, agent_conv_id
            span.metadata["succeed"] = True
        except asyncio.CancelledError:
                # Client disconnects
                logger.warning("Client disconnected")
                if agent_task:
                    logger.info(f"Chat to App {gpts_name}:{agent_conv_id} Cancel!")
                    agent_task.cancel()
        except Exception as e:
            logger.exception(f"Chat to App {gpts_name} Failed!agent_conv_id:{agent_conv_id}." + str(e))
            error_info = str(e)
            yield str(e), agent_conv_id
        finally:
            logger.info(f"save agent chat info！{conv_uid}")
            if not agent_task:
                logger.info("对话协程已释放！")
            await self.save_conversation(conv_session_id=conv_uid, agent_conv_id=agent_conv_id,
                                         current_message=current_message, err_msg=error_info,
                                         chat_call_back=chat_call_back,first_chunk_ms=first_chunk_ms)
            span.end()
