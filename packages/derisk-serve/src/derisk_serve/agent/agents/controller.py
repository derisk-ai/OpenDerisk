import asyncio
import json
import logging
import uuid
from abc import ABC
from copy import deepcopy
from typing import Any, Dict, List, Optional, Type, AsyncGenerator, Callable, Tuple, Union

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from derisk._private.config import Config
from derisk.agent import (
    AgentContext,
    AgentMemory,
    ConversableAgent,
    EnhancedShortTermMemory,
    HybridMemory,
    LLMConfig,
    ResourceType,
    UserProxyAgent,
    AWELTeamContext,
    get_agent_manager, Memory, AgentResource, GptsMemory,
)
from derisk.agent.core.plan.react.team_react_plan import AutoTeamContext
from derisk.agent.core.base_team import ManagerAgent
from derisk.agent.core.memory.gpts import GptsMessage
from derisk.agent.core.schema import Status
from derisk.agent.resource.base import FILE_RESOURCES
from derisk.agent.resource import get_resource_manager, ResourceManager
from derisk.agent.util.llm.llm import LLMStrategyType
from derisk.component import BaseComponent, ComponentType, SystemApp
from derisk.core.awel.flow.flow_factory import FlowCategory
from derisk.core.interface.message import StorageConversation, HumanMessage
from derisk.model.cluster import WorkerManagerFactory
from derisk.model.cluster.client import DefaultLLMClient
from derisk.util.data_util import first
from derisk.util.date_utils import current_ms
from derisk.util.executor_utils import ExecutorFactory
from derisk.util.json_utils import serialize
from derisk.util.log_util import CHAT_LOGGER
from derisk.util.logger import digest
from derisk.util.tracer.tracer_impl import root_tracer
from derisk.vis import VisProtocolConverter
from derisk.vis.vis_manage import get_vis_manager
from derisk_app.derisk_server import system_app
from derisk_ext.agent.agents.awel.awel_runner_agent import AwelRunnerAgent
from derisk_serve.conversation.serve import Serve as ConversationServe
from derisk_serve.core import blocking_func_to_async
from derisk_serve.building.app.service.service import Service as AppService
from .chat.agent_chat_async import AsyncAgentChat
from .chat.agent_chat_background import BackGroundAgentChat
from .chat.agent_chat_quick import QuickAgentChat
from .chat.agent_chat_simple import SimpleAgentChat
from .derisks_memory import MetaDerisksMessageMemory, MetaDerisksPlansMemory
from ..db import GptsMessagesDao
from ..db.gpts_conversations_db import GptsConversationsDao, GptsConversationsEntity
from ..team.base import TeamMode
from ...building.app.api.schema_app import GptsApp
from ...building.app.api.schema_app_detail import GptsAppDetail
from ...building.app.api.schemas import ServerResponse
from ...building.config.api.schemas import ChatInParamValue, AppParamType
from ...rag.retriever.knowledge_space import KnowledgeSpaceRetriever

CFG = Config()

router = APIRouter()
logger = logging.getLogger(__name__)


def get_app_service() -> AppService:
    return AppService.get_instance(CFG.SYSTEM_APP)


class MultiAgents(BaseComponent, ABC):
    name = ComponentType.MULTI_AGENTS

    def init_app(self, system_app: SystemApp):
        self.system_app = system_app

    def __init__(self, system_app: SystemApp):

        from derisk.agent.core.memory.gpts.disk_cache_gpts_memory import DiskGptsMemory
        # from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
        self.memory: GptsMemory = DiskGptsMemory(
            plans_memory=MetaDerisksPlansMemory(),
            message_memory=MetaDerisksMessageMemory(),
        )
        self.agent_memory_map = {}
        super().__init__(system_app)
        self.system_app = system_app

    def on_init(self):
        """Called when init the application.

        Import your own module here to ensure the module is loaded before the
        application starts
        """
        from ..db.gpts_app import (  # noqa: F401
            GptsAppDetailEntity,
            GptsAppEntity,
            UserRecentAppsEntity,
        )

    async def async_after_start(self):
        worker_manager = CFG.SYSTEM_APP.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        self.llm_provider = DefaultLLMClient(
            worker_manager, auto_convert_message=True
        )

        self.simpale_chat = SimpleAgentChat(self.system_app, self.memory, self.llm_provider)
        self.quick_chat = QuickAgentChat(self.system_app, self.memory, self.llm_provider)
        self.background_chat = BackGroundAgentChat(self.system_app, self.memory, self.llm_provider)
        self.async_chat = AsyncAgentChat(self.system_app, self.memory, self.llm_provider)

    async def quick_app_chat(self, conv_session_id,
                             user_query: Union[str, HumanMessage],
                             app_code: Optional[str] = "chat_normal",
                             chat_in_params: Optional[List[ChatInParamValue]] = None,
                             user_code: Optional[str] = None,
                             sys_code: Optional[str] = None,
                             **ext_info) -> Tuple[Optional[str], Optional[str]]:
        async for chunk, agent_conv_id in self.quick_chat.chat(conv_uid=conv_session_id, gpts_name=app_code,
                                                               user_query=user_query,
                                                               user_code=user_code,
                                                               specify_config_code=None,
                                                               sys_code=sys_code,
                                                               stream=True,
                                                               app_code=app_code,
                                                               chat_call_back=None,
                                                               chat_in_params=chat_in_params,
                                                               **ext_info):
            yield chunk, agent_conv_id

    async def app_chat(
        self,
        conv_uid: str,
        gpts_name: str,
        user_query: Union[str, HumanMessage],
        specify_config_code: Optional[str] = None,
        user_code: str = None,
        sys_code: str = None,
        stream: Optional[bool] = True,
        chat_call_back: Optional[Any] = None,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info,
    ) -> Tuple[Optional[str], Optional[str]]:
        """智能体对话入口V1版本(构建会话。发起Agent对话,如果断开链接立即中断对话)

        Args:
            conv_uid:   会话id
            gpts_name:  要对话的智能体
            user_query: 用户消息，支持多模态
        """
        async for chunk, agent_conv_id in self.simpale_chat.chat(conv_uid=conv_uid, gpts_name=gpts_name,
                                                                 user_query=user_query, user_code=user_code,
                                                                 specify_config_code=specify_config_code,
                                                                 sys_code=sys_code, stream=stream,
                                                                 chat_call_back=chat_call_back,
                                                                 chat_in_params=chat_in_params,
                                                                 **ext_info):
            yield chunk, agent_conv_id

    async def app_chat_v2(
        self,
        conv_uid: str,
        gpts_name: str,
        user_query: Union[str, HumanMessage],
        background_tasks: BackgroundTasks,
        specify_config_code: Optional[str] = None,
        user_code: Optional[str] = None,
        sys_code: Optional[str] = None,
        stream: Optional[bool] = True,
        chat_call_back: Optional[Any] = None,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info,
    ) -> Tuple[Optional[str], Optional[str]]:
        """智能体对话入口V2版本(构建会话。发起Agent对话,如果断开链接立即转为后台运行，成功后保存对话进行回调,推荐回调里要推送最终消息的才可以使用)

        Args:
            conv_uid:   会话id
            gpts_name:  要对话的智能体
            user_query: 用户消息，支持多模态
        """
        logger.info(f"app_chat_v2:{gpts_name},{user_query},{conv_uid}")
        async for chunk, agent_conv_id in self.background_chat.chat(conv_uid=conv_uid, gpts_name=gpts_name,
                                                                    user_query=user_query, user_code=user_code,
                                                                    specify_config_code=specify_config_code,
                                                                    sys_code=sys_code, stream=stream,
                                                                    background_tasks=background_tasks,
                                                                    chat_call_back=chat_call_back,
                                                                    chat_in_params=chat_in_params,
                                                                    **ext_info):
            yield chunk, agent_conv_id

    async def app_chat_v3(
        self,
        conv_uid: str,
        gpts_name: str,
        user_query: Union[str, HumanMessage],
        background_tasks: BackgroundTasks,
        specify_config_code: Optional[str] = None,
        user_code: str = None,
        sys_code: str = None,
        stream: Optional[bool] = True,
        chat_call_back: Optional[Any] = None,
        chat_in_params: Optional[List[ChatInParamValue]] = None,
        **ext_info,
    ) -> Tuple[Optional[str], Optional[str]]:
        """智能体对话入口V3版本(构建异步会话。发起Agent对话,立即返回，并后台运行，成功后保存对话进行回调)

        Args:
            conv_uid:   会话id
            gpts_name:  要对话的智能体
            user_query: 用户消息，支持多模态
        """
        logger.info(f"app_chat_v3:{conv_uid},{gpts_name},{user_query}")

        return await self.async_chat.chat(conv_uid=conv_uid, gpts_name=gpts_name,
                                          user_query=user_query, user_code=user_code,
                                          specify_config_code=specify_config_code,
                                          sys_code=sys_code, stream=stream,
                                          background_tasks=background_tasks,
                                          chat_call_back=chat_call_back, chat_in_params=chat_in_params,
                                          **ext_info)

    async def get_knowledge_resources(self, app_code: str, question: str):
        """Get the knowledge resources."""
        context = []

        app_service = get_app_service()
        app: GptsApp = await app_service.app_detail(app_code, building_mode=False)
        if app and app.details and len(app.details) > 0:
            for detail in app.details:
                if detail and detail.resources and len(detail.resources) > 0:
                    for resource in detail.resources:
                        if resource.type == ResourceType.Knowledge:
                            retriever = KnowledgeSpaceRetriever(
                                space_id=str(resource.value),
                                top_k=CFG.KNOWLEDGE_SEARCH_TOP_SIZE,
                            )
                            chunks = await retriever.aretrieve_with_scores(
                                question, score_threshold=0.3
                            )
                            context.extend([chunk.content for chunk in chunks])
                        else:
                            continue
        return context

    async def stop_chat(self, conv_session_id: str, user_id: Optional[str] = None):
        """停止对话.

        Args:
            conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
        """
        logger.info(f"stop_chat conv_session_id:{conv_session_id}")
        await self.simpale_chat.stop_chat(conv_session_id=conv_session_id, user_id=user_id)


multi_agents = MultiAgents(CFG.SYSTEM_APP)
