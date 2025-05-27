import json
import logging
import uuid
from abc import ABC
from typing import List, Optional

from fastapi import APIRouter

from derisk._private.config import Config
from derisk.agent import (
    AgentContext,
    AgentMemory,
    LLMConfig,
    UserProxyAgent,
    get_agent_manager,
)
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.memory.gpts import GptsMessage

from derisk.agent.core.schema import Status
from derisk.agent.resource import get_resource_manager
from derisk.agent.util.llm.llm import LLMStrategyType
from derisk.component import ComponentType
from derisk.core import LLMClient

from derisk.model.cluster import WorkerManagerFactory
from derisk.model.cluster.client import DefaultLLMClient

from derisk.util.tracer.tracer_impl import root_tracer
from ..db import GptsConversationsDao

from ..db.gpts_app import GptsApp

CFG = Config()

router = APIRouter()
logger = logging.getLogger(__name__)


class AISREController(ABC):

    async def ai_sre_chat(self,
                          user_query: str,
                          conv_session_id: str,
                          conv_uid: str,
                          agent_memory: AgentMemory,
                          gpts_conversations: GptsConversationsDao,
                          is_retry_chat: bool = False,
                          last_speaker_name: str = None,
                          init_message_rounds: int = 0,
                          app_link_start: bool = False,
                          historical_dialogues: Optional[List[GptsMessage]] = None,
                          rely_messages: Optional[List[GptsMessage]] = None,
                          stream: Optional[bool] = True,
                          **ext_info,
                          ):
        gpts_status = Status.COMPLETE.value
        try:
            self.agent_manage = get_agent_manager()

            context: AgentContext = AgentContext(
                conv_id=conv_uid,
                conv_session_id=conv_session_id,
                trace_id=ext_info.get("trace_id", uuid.uuid4().hex),
                rpc_id=ext_info.get("rpc_id", "0.1"),
                gpts_app_code="ai_sre",
                gpts_app_name="AI-SRE",
                language="zh",
                app_link_start=app_link_start,
                incremental=ext_info.get("incremental", False),
                stream=stream,
            )
            root_tracer.start_span(
                operation_name="agent_chat", parent_span_id=context.trace_id
            )
            rm = get_resource_manager()
            # init llm provider
            ### init chat param
            worker_manager = CFG.SYSTEM_APP.get_component(
                ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
            ).create()
            llm_provider = DefaultLLMClient(
                worker_manager, auto_convert_message=True
            )

            employees = []
            thinking_llm_config = LLMConfig(
                llm_client=llm_provider,
                llm_strategy=LLMStrategyType.Priority,
                strategy_context=json.dumps(["deepseek-r1", "deepseek-v3"]),
            )
            ## 构建AISRE Agent
            from derisk_ext.ai_sre.sre_agent import SreManager
            ai_sre: ManagerAgent = (await SreManager()
                                    .bind(context)
                                    .bind(agent_memory)
                                    .bind(thinking_llm_config)
                                    .build())

            ## 构建规划Agent 可多个

            from derisk_ext.ai_sre.sre_planning_agent import SrePlanningAgent
            planner = (await SrePlanningAgent()
                       .bind(context)
                       .bind(agent_memory)
                       .bind(thinking_llm_config)
                       .build()
                       )
            employees.append(planner)
            ## 工具报告Agent 可多个

            from derisk_ext.ai_sre.diag_reporter_agent import DiagRportAssistantAgent
            diag_reporter = (await DiagRportAssistantAgent()
                             .bind(context)
                             .bind(agent_memory)
                             .bind(thinking_llm_config)
                             .build()
                             )
            employees.append(diag_reporter)
            ## 构建Ipaython代码Agent
            code_llm_config = LLMConfig(
                llm_client=llm_provider,
                llm_strategy=LLMStrategyType.Priority,
                strategy_context=json.dumps(["deepseek-v3","deepseek-r1",  ]),
            )
            from derisk_ext.ai_sre.ipython_agent import IpythonAssistantAgent
            coder = (await IpythonAssistantAgent()
                     .bind(context)
                     .bind(agent_memory)
                     .bind(code_llm_config)
                     .build()
                     )
            employees.append(coder)
            ## 构建知识Agent
            ### 动态绑定所有维护的知识

            ## 构建Tool工具Agent

            ## 构建数据分析Agent

            ai_sre.hire(employees)

            user_proxy: UserProxyAgent = (
                await UserProxyAgent().bind(context).bind(agent_memory).build()
            )

            await user_proxy.initiate_chat(
                recipient=ai_sre,
                message=user_query,
                is_retry_chat=is_retry_chat,
                last_speaker_name=last_speaker_name,
                message_rounds=init_message_rounds,
                historical_dialogues=user_proxy.convert_to_agent_message(
                    historical_dialogues
                ),
                rely_messages=rely_messages,
                **ext_info,
            )

            if user_proxy:
                # Check if the user has received a question.
                if user_proxy.have_ask_user():
                    gpts_status = Status.WAITING.value
            if not app_link_start:
                gpts_conversations.update(conv_uid, gpts_status)
        except Exception as e:
            logger.error(f"chat abnormal termination！{str(e)}", e)
            gpts_conversations.update(conv_uid, Status.FAILED.value)
            raise ValueError(f"The conversation is abnormal!{str(e)}")
        finally:
            if not app_link_start:
                await agent_memory.gpts_memory.complete(conv_uid)

        return conv_uid


ai_sre_controller = AISREController()
