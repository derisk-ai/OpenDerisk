import logging
from abc import ABC
from typing import Any, List, Optional, Tuple, Union

from fastapi import APIRouter, BackgroundTasks
from derisk._private.config import Config
from derisk.agent import (
    ResourceType,
)
from derisk.component import BaseComponent, ComponentType, SystemApp
from derisk.core.interface.message import HumanMessage
from derisk.model.cluster import WorkerManagerFactory
from derisk.model.cluster.client import DefaultLLMClient
from derisk_serve.building.app.service.service import Service as AppService
from .chat.agent_chat_async import AsyncAgentChat
from .chat.agent_chat_background import BackGroundAgentChat
from .chat.agent_chat_quick import QuickAgentChat
from .chat.agent_chat_simple import SimpleAgentChat

from ...building.app.api.schema_app import GptsApp
from ...building.config.api.schemas import ChatInParamValue
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

        self.simpale_chat = SimpleAgentChat(self.system_app, llm_provider=self.llm_provider)
        self.quick_chat = QuickAgentChat(self.system_app, llm_provider=self.llm_provider)
        self.background_chat = BackGroundAgentChat(self.system_app, llm_provider=self.llm_provider)
        self.async_chat = AsyncAgentChat(self.system_app, llm_provider=self.llm_provider)

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

    async def knowledge_app_chat(
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
        """知识理解与生成对话入口V1版本(构建会话。发起Agent对话,如果断开链接立即中断对话)

        Args:
            conv_uid:   会话id
            gpts_name:  要对话的智能体
            user_query: 用户消息，支持多模态
        """
        async for chunk, agent_conv_id in self.knowledge_chat.chat(
                conv_uid=conv_uid, gpts_name=gpts_name,
                user_query=user_query, user_code=user_code,
                specify_config_code=specify_config_code,
                sys_code=sys_code, stream=stream,
                chat_call_back=chat_call_back,
                chat_in_params=chat_in_params,
                **ext_info
        ):
            yield chunk, agent_conv_id

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
            conv_session_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
        """
        logger.info(f"stop_chat conv_session_id:{conv_session_id}")
        await self.simpale_chat.stop_chat(conv_session_id=conv_session_id, user_id=user_id)

    async def query_chat(self, conv_id: str, vis_render: Optional[str] = None, user_id: Optional[str] = None):
        """停止对话.

        Args:
            conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
        """
        logger.info(f"query_chat conv_id:{conv_id},{user_id}")
        return await self.simpale_chat.query_chat(conv_id=conv_id, vis_render=vis_render)


multi_agents = MultiAgents(CFG.SYSTEM_APP)
