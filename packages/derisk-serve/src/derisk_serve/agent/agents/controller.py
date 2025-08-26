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
    get_agent_manager, Memory, AgentResource,
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

def _build_conversation(
        conv_id: str,
        select_param: Union[str, Dict[str, Any]],
        model_name: str,
        summary: str,
        app_code: str,
        conv_serve: ConversationServe,
        user_name: Optional[str] = "",
        sys_code: Optional[str] = "",
) -> StorageConversation:
    return StorageConversation(
        conv_uid=conv_id,
        chat_mode="chat_agent",
        user_name=user_name,
        sys_code=sys_code,
        model_name=model_name,
        summary=summary,
        param_type="derisks",
        param_value=select_param,
        app_code=app_code,
        conv_storage=conv_serve.conv_storage,
        message_storage=conv_serve.message_storage,
    )


class MultiAgents(BaseComponent, ABC):
    name = ComponentType.MULTI_AGENTS

    def init_app(self, system_app: SystemApp):
        system_app.app.include_router(router, prefix="/api", tags=["Multi-Agents"])
        self.system_app = system_app

    def __init__(self, system_app: SystemApp):
        self.gpts_conversations = GptsConversationsDao()
        self.gpts_messages_dao = GptsMessagesDao()

        from derisk.agent.core.memory.gpts.disk_cache_gpts_memory import DiskGptsMemory
        # from derisk.agent.core.memory.gpts.gpts_memory import GptsMemory
        self.memory = DiskGptsMemory(
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

    def after_start(self):
        worker_manager = CFG.SYSTEM_APP.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        self.llm_provider = DefaultLLMClient(
            worker_manager, auto_convert_message=True
        )


    def get_or_build_agent_memory(self, conv_id: str, derisks_name: str) -> AgentMemory:
        from derisk.rag.embedding.embedding_factory import EmbeddingFactory
        from derisk_serve.rag.storage_manager import StorageManager

        executor = self.system_app.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()

        storage_manager = StorageManager.get_instance(self.system_app)
        vector_store = storage_manager.create_vector_store(index_name="_agent_memory_")
        embeddings = EmbeddingFactory.get_instance(self.system_app).create()
        short_term_memory = EnhancedShortTermMemory(
            embeddings, executor=executor, buffer_size=10
        )
        memory = HybridMemory.from_vstore(
            vector_store,
            embeddings=embeddings,
            executor=executor,
            short_term_memory=short_term_memory,
        )
        agent_memory = AgentMemory(memory, gpts_memory=self.memory)

        return agent_memory

    def get_or_build_derisk_memory(
            self,
            conv_id: str,
            agent_id: str,
            user_id: str,
            team_context: Optional[
                Union[
                    str, AutoTeamContext
                ]
            ] = None
    ) -> AgentMemory:
        """ Get or build a Derisk memory instance for the given conversation ID.

        Args:
            conv_id:(str) conversation ID
            agent_id:(str) app_code
        """
        from derisk_serve.rag.storage_manager import StorageManager
        from derisk_ext.agent.memory.session import SessionMemory
        from derisk_ext.agent.memory.preference import PreferenceMemory

        executor = self.system_app.get_component(
            ComponentType.EXECUTOR_DEFAULT, ExecutorFactory
        ).create()

        storage_manager = StorageManager.get_instance(self.system_app)
        # session_id = f"session_{conv_id}"
        index_name = f"session_{agent_id}"
        vector_store = storage_manager.create_vector_store(
            index_name=index_name
        )
        worker_manager = self.system_app.get_component(
            ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
        ).create()
        llm_client = DefaultLLMClient(worker_manager=worker_manager)
        session_memory = SessionMemory(
            session_id=conv_id,
            agent_id=agent_id,
            vector_store=vector_store,
            executor=executor,
            gpts_memory=self.memory,
            llm_client=llm_client,
        )
        # from derisk_ext.agent.memory.enhanced_agent import EnhancedAgentMemory
        # agent_memory = AgentMemory(
        #     session_memory=session_memory, gpts_memory=self.memory
        # )
        agent_memory = AgentMemory(
            memory=session_memory, gpts_memory=self.memory
        )

        # 配置部分Agent有user preference
        if team_context:
            resources = team_context.resources
            enable_user_memory = False
            if resources:
                for resource in resources:
                    if resource.type == 'memory':
                        json_val = json.loads(resource.value)
                        if 'enable_user_memory' in json_val and json_val['enable_user_memory']:
                            enable_user_memory = True

            if enable_user_memory:
                logger.info(f"get_or_build_derisk_memory enable_user_memory:{user_id}")
                index_name = f"user_{user_id}"
                user_store = storage_manager.create_vector_store(
                    index_name=index_name
                )
                metadata : Dict[str, Any] = {"user_id": user_id}
                preference_memory = PreferenceMemory(
                    agent_id=agent_id,
                    vector_store=user_store,
                    executor=executor,
                    metadata=metadata,
                )
                agent_memory.preference_memory = preference_memory
        return agent_memory

    async def stop_chat(self, conv_id: str):
        """停止对话.

        Args:
            conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
        """
        logger.info(f"stop_chat conv_uid:{conv_id}")
        await self.memory.stop(conv_id=conv_id)

    # async def retry_chat(self, conv_id: str):
    #     """重试对话, 对于运行中且最终消息超过5分钟的 可以基于已有对话记录继续运行
    #
    #     Args:
    #         conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
    #     """
    #     gpts_conversation: GptsConversationsEntity = self.gpts_conversations.get_by_conv_id(conv_id)
    #     #
    #     if gpts_conversation:
    #         logger.info(f"last conversation status:{gpts_conversation.state}")
    #         if gpts_conversation.state == Status.WAITING.value:
    #             is_retry_chat = True
    #             agent_conv_id = gpts_conversation.conv_id
    #
    #             gpts_messages: List[GptsMessage] = self.gpts_messages_dao.get_by_conv_id(agent_conv_id)
    #             history_messages = gpts_messages
    #             last_message = gpts_messages[-1]
    #             message_round = last_message.rounds + 1
    #             last_speaker_name = last_message.sender
    #             gpt_app: GptsApp = self.gpts_app.app_detail(last_message.app_code)
    #
    #             if not gpt_app:
    #                 raise ValueError(f"重试对话消息对应的应用[{last_message.app_code}]{last_message.app_name}已经无法找到!")
    #     else:
    #         raise ValueError(f"没有找到[{conv_id}]对应的对话记录！")

    async def query_chat(self, conv_id: str, vis_render: Optional[str] = None):
        """查询对话

        Args:
            conv_id: 对话id(当前对话的agent_conv_id 非conversation_session_id)
            vis_render: 可视化协议名称（决定返回数据的格式）
        """
        gpts_conversation: GptsConversationsEntity = self.gpts_conversations.get_by_conv_id(conv_id)

        current_vis_render = vis_render or gpts_conversation.vis_render or "nex_vis_window"

        app_config = self.system_app.config.configs.get("app_config")
        web_config = app_config.service.web
        vis_manager = get_vis_manager()

        vis_convert: VisProtocolConverter =vis_manager.get_by_name(current_vis_render)(derisk_url=web_config.web_url)

        ## 重新初始化对话memory数据
        self.memory.init(conv_id=conv_id, vis_converter=vis_convert)
        await self.memory.load_persistent_memory(conv_id)
        ## 构建Agent应用实例并挂载到memory，获取对应头像等信息
        context: AgentContext = AgentContext(
            conv_id=conv_id,
            conv_session_id=gpts_conversation.conv_session_id,
            trace_id=uuid.uuid4().hex,
            rpc_id="",
            gpts_app_code=gpts_conversation.gpts_name,
        )
        try:
            await self.build_agent_by_app_code(gpts_conversation.gpts_name, context)
        except Exception as e:
            logger.warning(f"查询会话时，恢复agent对象异常！{str(e)}")

        # 返回对应协议的最终消息内容
        return await self.memory.vis_final(conv_id), await self.memory.user_answer(conv_id), current_vis_render

    async def build_agent_conv_id(self, conv_session_id: str, **ext_info):
        gpts_conversations: List[GptsConversationsEntity] = (
            self.gpts_conversations.get_by_session_id_asc(conv_session_id)
        )

        logger.info(
            f"gpts_conversations count:{conv_session_id}, "
            f"{len(gpts_conversations) if gpts_conversations else 0}"
        )
        last_conversation = gpts_conversations[-1] if gpts_conversations else None
        if last_conversation and Status.WAITING.value == last_conversation.state:
            agent_conv_id = last_conversation.conv_id
            logger.info("收到用户动作授权, 恢复会话: " + agent_conv_id)
        else:
            gpt_chat_order = "1" if not gpts_conversations else str(len(gpts_conversations) + 1)
            agent_conv_id = conv_session_id + "_" + gpt_chat_order
        return agent_conv_id, gpts_conversations

    async def agent_chat(
            self,
            conv_id: str,
            agent_conv_id: str,
            gpts_name: str,
            user_query: Union[str, HumanMessage],
            user_code: str = None,
            sys_code: str = None,
            stream: Optional[bool] = True,
            gpts_conversations: Optional[List[GptsConversationsEntity]] = None,
            specify_config_code: Optional[str] = None,
            chat_in_params: Optional[List[ChatInParamValue]] = None,
            **ext_info,
    ):
        """具体agent(app)对话入口，构建对话记忆和对话目标等通用的Agent对话逻辑(需要外层基于会话封装一般不直接)

        Args:
            conv_id: 会话id
            agent_conv_id：当前对话id
            gpts_name：要对话的智能体(应用/agent/工作流等)
        """
        logger.info(
            f"agent_chat conv_id:{conv_id}, agent_conv_id:{agent_conv_id},gpts_name:{gpts_name},user_query:"
            f"{user_query}"
        )
        digest(CHAT_LOGGER, "CHAT_ENTRY", conv_id=conv_id, app_code=gpts_name, user_code=user_code)
        start_ts = current_ms()
        succeed = False
        first_chunk_time = None
        if isinstance(user_query, str):
            user_query: HumanMessage = HumanMessage.parse_chat_completion_message(user_query, ignore_unknown_media=True)

        root_tracer.set_context_conv_id(agent_conv_id)
        message_round = 0
        history_message_count = 0
        is_retry_chat = False
        last_speaker_name = None
        history_messages = None

        ########################################################
        app_config = self.system_app.config.configs.get("app_config")
        web_config = app_config.service.web

        app_service = get_app_service()
        gpt_app: GptsApp = await app_service.app_detail(gpts_name, specify_config_code, building_mode=False)
        if not gpt_app:
            raise ValueError(f"Not found app {gpts_name}!")

        # init gpts  memory
        vis_render = ext_info.get("vis_render", None)
        # 如果接口指定使用接口传递，没有指定使用当前应用的布局配置
        if not vis_render:
            if gpt_app.layout and gpt_app.layout.chat_layout:
                vis_render = gpt_app.layout.chat_layout.name
            else:
                vis_render = "gpt_vis_all"

        vis_converter_mng = get_vis_manager()
        vis_protocol = vis_converter_mng.get_by_name(vis_render)(derisk_url=web_config.web_url)
        ext_info["incremental"] = vis_protocol.incremental

        self.memory.init(
            agent_conv_id,
            history_messages=history_messages,
            start_round=history_message_count,
            vis_converter=vis_protocol,
        )
        #########################################################

        # 检查最后一个对话记录是否完成，如果是等待状态，则要继续进行当前对话
        if gpts_conversations and len(gpts_conversations) > 0:
            last_gpts_conversation: GptsConversationsEntity = gpts_conversations[-1]
            logger.info(f"last conversation status:{last_gpts_conversation.__dict__}")
            if last_gpts_conversation.state == Status.WAITING.value:
                is_retry_chat = True
                agent_conv_id = last_gpts_conversation.conv_id

                gpts_messages: List[GptsMessage] = (
                    self.gpts_messages_dao.get_by_conv_id(agent_conv_id)
                )

                last_message = gpts_messages[-1]
                message_round = last_message.rounds + 1
                last_speaker_name = last_message.sender_name


        historical_dialogues: List[GptsMessage] = []
        if not is_retry_chat:
            # Create a new gpts conversation record

            ## When creating a new gpts conversation record, determine whether to
            # include the history of previous topics according to the application
            # definition.
            ## TODO BEGIN
            # Temporarily use system configuration management, and subsequently use
            # application configuration management
            if CFG.MESSAGES_KEEP_START_ROUNDS and CFG.MESSAGES_KEEP_START_ROUNDS > 0:
                gpt_app.keep_start_rounds = CFG.MESSAGES_KEEP_START_ROUNDS
            if CFG.MESSAGES_KEEP_END_ROUNDS and CFG.MESSAGES_KEEP_END_ROUNDS > 0:
                gpt_app.keep_end_rounds = CFG.MESSAGES_KEEP_END_ROUNDS
            ## TODO END

            if gpt_app.keep_start_rounds > 0 or gpt_app.keep_end_rounds > 0:
                if gpts_conversations and len(gpts_conversations) > 0:
                    rely_conversations = []
                    if gpt_app.keep_start_rounds + gpt_app.keep_end_rounds < len(
                            gpts_conversations
                    ):
                        if gpt_app.keep_start_rounds > 0:
                            front = gpts_conversations[gpt_app.keep_start_rounds:]
                            rely_conversations.extend(front)
                        if gpt_app.keep_end_rounds > 0:
                            back = gpts_conversations[-gpt_app.keep_end_rounds:]
                            rely_conversations.extend(back)
                    else:
                        rely_conversations = gpts_conversations
                    for gpts_conversation in rely_conversations:
                        temps: List[GptsMessage] = await self.memory.get_messages(
                            gpts_conversation.conv_id
                        )
                        if temps and len(temps) > 1:
                            historical_dialogues.append(temps[0])
                            historical_dialogues.append(temps[-1])

            self.gpts_conversations.add(
                GptsConversationsEntity(
                    conv_id=agent_conv_id,
                    conv_session_id=conv_id,
                    user_goal=json.dumps(user_query.to_dict(), ensure_ascii=False),
                    gpts_name=gpts_name,
                    team_mode=gpt_app.team_mode,
                    state=Status.RUNNING.value,
                    max_auto_reply_round=0,
                    auto_reply_count=0,
                    user_code=user_code,
                    sys_code=sys_code,
                    vis_render=vis_render,
                )
            )

        if (
                TeamMode.AWEL_LAYOUT.value == gpt_app.team_mode
                and gpt_app.team_context.flow_category == FlowCategory.CHAT_FLOW
        ):
            team_context = gpt_app.team_context
            from derisk.core.awel import CommonLLMHttpRequestBody

            flow_req = CommonLLMHttpRequestBody(
                model=ext_info.get("model_name", None),
                messages=user_query,
                stream=True,
                # context=flow_ctx,
                # temperature=
                # max_new_tokens=
                # enable_vis=
                conv_uid=agent_conv_id,
                span_id=root_tracer.get_current_span_id(),
                chat_mode=ext_info.get("chat_mode", None),
                chat_param=team_context.uid,
                user_name=user_code,
                sys_code=sys_code,
                incremental=ext_info.get("incremental", True),
            )
            from derisk_app.openapi.api_v1.api_v1 import get_chat_flow

            flow_service = get_chat_flow()
            async for chunk in flow_service.chat_stream_flow_str(
                    team_context.uid, flow_req
            ):
                yield None, chunk, agent_conv_id
        else:
            # init agent memory
            # if gpt_app.team_context and gpt_app.team_context.teamleader == REASONING_AGENT_NAME:
            #     agent_memory = self.get_or_build_derisk_memory(
            #         conv_id, gpt_app.app_code
            #     )
            # else:
            #     agent_memory = self.get_or_build_agent_memory(conv_id, gpts_name)
            agent_memory = self.get_or_build_derisk_memory(
                conv_id, gpt_app.app_code, user_code, gpt_app.team_context
            )
            file_handle = None
            try:
                task = asyncio.create_task(
                    multi_agents.agent_team_chat_new(
                        user_query=user_query,
                        conv_session_id=conv_id,
                        conv_uid=agent_conv_id,
                        gpts_app=gpt_app,
                        agent_memory=agent_memory,
                        is_retry_chat=is_retry_chat,
                        last_speaker_name=last_speaker_name,
                        init_message_rounds=message_round,
                        historical_dialogues=historical_dialogues,
                        user_code=user_code,
                        sys_code=sys_code,
                        stream=stream,
                        chat_in_params=chat_in_params,
                        **ext_info,
                    )
                )
                ## TEST FILE WRITE
                WRITE_TO_FILE = True

                if WRITE_TO_FILE:
                    from derisk.configs.model_config import DATA_DIR
                    import os
                    chat_chunk_file_path = os.path.join(DATA_DIR, "chat_chunk_file")
                    os.makedirs(chat_chunk_file_path, exist_ok=True)
                    filename = os.path.join(chat_chunk_file_path, f"_chat_file_{agent_conv_id}.jsonl")
                    file_handle = open(filename, 'w', encoding='utf-8')

                async for chunk in multi_agents.chat_messages(agent_conv_id):
                    if chunk and len(chunk) > 0:
                        try:
                            content = json.dumps(
                                {"vis": chunk},
                                default=serialize,
                                ensure_ascii=False,
                            )
                            if WRITE_TO_FILE:
                                file_handle.write(content)
                                file_handle.write('\n')
                            resp = f"data:{content}\n"
                            first_chunk_time = first_chunk_time or current_ms()
                            yield task, resp, agent_conv_id
                        except Exception as e:
                            logger.exception(
                                f"get messages {gpts_name} Exception!" + str(e)
                            )
                            yield task, f"data: {str(e)}\n", agent_conv_id

                # 5. 最终处理
                if task.done() and task.exception():
                    # 如果任务有异常，返回错误
                    logger.exception(f"agent chat exception!{conv_id}")
                    raise task.exception()
                else:
                    # 正常结束
                    yield task, _format_vis_msg("[DONE]"), agent_conv_id
                succeed = True
            except asyncio.CancelledError:
                # 取消时不立即回调
                logger.info("Generator cancelled, delaying callback")
                raise
            except Exception as e:
                logger.exception(f"Agent chat have error!{str(e)}")
                raise e
                # yield task, str(e), agent_conv_id
            finally:
                digest(CHAT_LOGGER, "CHAT_DONE", conv_id=conv_id, app_code=gpts_name, user_code=user_code,
                       succeed=succeed, cost_ms=current_ms() - start_ts,
                       first_chunk_time=(first_chunk_time - start_ts) if first_chunk_time else -1)
                # 确保文件句柄关闭
                if file_handle:
                    file_handle.close()

    async def quick_app_chat(self, conv_session_id, user_query: Union[str, HumanMessage], model: Optional[str] = None,
                             model_tokens: int = 16000, temperature: float = 0.6,
                             chat_in_params: Optional[List[ChatInParamValue]] = None, user_code: Optional[str] = None,
                             sys_code: Optional[str] = None, **ext_info):

        quick_app_code = "quick_chat"
        quick_app_name = "快速对话"
        quick_app_describe = "快速对话"
        conv_serve = ConversationServe.get_instance(CFG.SYSTEM_APP)
        current_message: StorageConversation = _build_conversation(
            conv_id=conv_session_id,
            select_param="快速对话",
            summary="",
            model_name="",
            app_code="quick_chat",
            conv_serve=conv_serve,
            user_name=user_code,
        )
        current_message.save_to_storage()
        current_message.start_new_round()
        current_message.add_user_message(user_query if isinstance(user_query, str) else user_query.content)
        agent_task = None
        error_info = None
        agent_conv_id, gpts_conversations = await multi_agents.build_agent_conv_id(conv_session_id)
        try:

            async for task, chunk, agent_conv_id in multi_agents.quick_chat(
                    conv_session_id,
                    agent_conv_id,
                    gpts_conversations=gpts_conversations,
                    user_query=user_query,
                    user_code=user_code,
                    sys_code=sys_code,
                    chat_in_params=chat_in_params,
                    model_tokens=model_tokens,
                    temperature=temperature,
                    model=model,
                    **ext_info,
            ):
                agent_task = task
                yield chunk
        except asyncio.CancelledError:
            # Client disconnects
            logger.warning("Client disconnected")
            if agent_task:
                logger.info(f"Chat to App {quick_app_name}:{agent_conv_id} Cancel!")
                agent_task.cancel()
        except Exception as e:
            logger.exception(f"Chat to App {quick_app_name} Failed!agent_conv_id:{agent_conv_id}." + str(e))
            error_info = str(e)
            yield str(e)
        finally:
            logger.info(f"save agent chat info！{conv_session_id}")
            if not agent_task:
                logger.info("对话协程已释放！")
            await self.save_conversation(conv_session_id, agent_conv_id, current_message, err_msg=error_info,
                                         chat_call_back=None)

    async def quick_chat(self, conv_session_id, agent_conv_id, gpts_conversations: List[GptsConversationsEntity],
                         user_query, model: Optional[str] = None, model_tokens: int = 16000, temperature: float = 0.6,
                         chat_in_params: Optional[List[ChatInParamValue]] = None, user_code: Optional[str] = None,
                         sys_code: Optional[str] = None, **ext_info):
        logger.info(
            f"quick_chat conv_id:{conv_session_id},user_query:"
            f"{user_query}"
        )
        quick_app_code = "quick_chat"
        quick_app_name = "智能助手"
        quick_app_describe = "快速对话"

        async def _quick_agent(agent_cov_id: str, language: Optional[str] = "zh", init_message_rounds: int = 0, user_code: Optional[str] = None,
                         sys_code: Optional[str] = None):
            logger.info("_quick_agent")
            try:
                if isinstance(user_query.content, List):
                    from derisk_serve.file.serve import Serve as FileServe
                    from derisk.core.interface.media import MediaContent

                    file_serve = FileServe.get_instance(self.system_app)
                    new_content = MediaContent.replace_url(
                        user_query.content, file_serve.replace_uri
                    )
                    user_query.content = new_content

                self.agent_manage = get_agent_manager()

                from derisk.agent.core.agent import ENV_CONTEXT_KEY
                from derisk.agent.core.agent import LLM_CONTEXT_KEY

                ## 处理对话输入参数，进行分层，环境参数穿透当前会话不落表，llm参数作为消息的扩展参数随消息落表，agent控制是否向下传递
                llm_context, env_context = self.chat_in_params_to_context(chat_in_params)

                if ext_info.get(ENV_CONTEXT_KEY):
                    env_context.update(ext_info.get(ENV_CONTEXT_KEY))
                context: AgentContext = AgentContext(
                    user_id=user_code or "derisk",
                    conv_id=agent_cov_id,
                    conv_session_id=conv_session_id,
                    trace_id=first(
                        ext_info.get("trace_id", None),
                        root_tracer.get_context_trace_id(),
                        uuid.uuid4().hex,
                    ),
                    rpc_id=ext_info.get("rpc_id", "0.1"),
                    gpts_app_code=quick_app_code,
                    gpts_app_name=quick_app_name,
                    agent_app_code=quick_app_code,
                    language=language,
                    incremental=ext_info.get("incremental", False),
                    env_context=env_context,
                    stream=True,
                    extra=ext_info,
                    max_new_tokens=model_tokens
                )
                agent_memory = self.get_or_build_derisk_memory(
                    conv_session_id, quick_app_code,user_id=user_code or "derisk"
                )

                root_tracer.start_span(
                    operation_name=quick_app_name, parent_span_id=context.trace_id
                )

                ## 处理agent资源内容
                agent_context = deepcopy(context)
                agent_context.agent_app_code = quick_app_code
                model = None
                resources = None
                for item in chat_in_params:
                    if item.param_type == AppParamType.Resource.value:
                        if item.sub_type not in FILE_RESOURCES:
                            try:
                                resources = AgentResource.from_dict({
                                    "name": "对话目标资源",
                                    "type": item.sub_type,
                                    "value": json.loads(item.param_value),
                                })
                            except Exception as e:
                                logger.warning(f"选择资源无法转换！{chat_in_params}", e)
                    elif item.param_type == AppParamType.Model.value:
                        model = item.param_value
                    elif item.param_type == AppParamType.Temperature.value:
                        temperature = item.param_value
                        agent_context.temperature = temperature
                    elif item.param_type == AppParamType.MaxNewTokens.value:
                        max_tokens = item.param_value
                        agent_context.max_new_tokens = max_tokens

                ##  暂时先支持模型、工具、知识的快速对话
                llm_config = LLMConfig(
                    llm_client=self.llm_provider,
                    llm_strategy=LLMStrategyType.Priority,
                    strategy_context=[model]
                )
                if resources:

                    rm = get_resource_manager()
                    depend_resource = await blocking_func_to_async(
                        CFG.SYSTEM_APP, rm.build_resource, [resources]
                    )
                    if resources.type == ResourceType.Knowledge.value or resources.type == ResourceType.KnowledgePack.value:
                        from derisk.agent.expand.summary_assistant_agent import SummaryAssistantAgent
                        recipient = await SummaryAssistantAgent().bind(context).bind(agent_memory).bind(
                            llm_config).bind(depend_resource).build()
                    elif resources.type == ResourceType.Tool.value:
                        from derisk.agent.expand.tool_assistant_agent import ToolAssistantAgent
                        recipient = await ToolAssistantAgent().bind(context).bind(agent_memory).bind(
                            llm_config).bind(depend_resource).build()
                    elif resources.type == ResourceType.DB.value:
                        from derisk.agent.expand.tool_assistant_agent import ToolAssistantAgent
                        from derisk.agent.expand.data_scientist_agent import DataScientistAgent
                        recipient = await DataScientistAgent().bind(context).bind(agent_memory).bind(
                            llm_config).bind(depend_resource).build()
                    else:
                        raise ValueError(f"快速对话 暂时不支持资源「{resources}」")

                else:
                    from derisk.agent.expand.simple_assistant_agent import SimpleAssistantAgent
                    recipient = await SimpleAssistantAgent().bind(context).bind(agent_memory).bind(llm_config).build()

                ## 处理Agent实例的基本信息
                temp_profile = recipient.profile.copy()
                temp_profile.desc = quick_app_describe
                temp_profile.name = quick_app_name
                temp_profile.avatar = ""
                recipient.bind(temp_profile)
                # init llm provider
                ### init chat param
                ## 检查应用是否配置完整

                user_proxy: UserProxyAgent = (
                    await UserProxyAgent().bind(context).bind(agent_memory).build()
                )
                user_code = ext_info.get("user_code", None)
                if user_code:
                    app_config = self.system_app.config.configs.get("app_config")
                    web_config = app_config.service.web
                    user_proxy.profile.avatar = (
                        f"{web_config.web_url}/user/avatar?loginName={user_code}"
                    )
                await user_proxy.initiate_chat(
                    recipient=recipient,
                    message=user_query,
                    is_retry_chat=is_retry_chat,
                    last_speaker_name=last_speaker_name,
                    message_rounds=init_message_rounds,
                    historical_dialogues=user_proxy.convert_to_agent_message(
                        historical_dialogues
                    ),
                    **llm_context,
                )
            except Exception as e:
                logger.error(f"chat abnormal termination！{str(e)}", e)
                self.gpts_conversations.update(agent_cov_id, Status.FAILED.value)
                raise ValueError(f"The conversation is abnormal!{str(e)}")
            finally:
                await self.memory.complete(agent_cov_id)

        digest(CHAT_LOGGER, "QUICK_CHAT_ENTRY", conv_id=conv_session_id, user_query=user_query, user_code=user_code)
        start_ts = current_ms()
        succeed = False
        first_chunk_time = None
        if isinstance(user_query, str):
            user_query: HumanMessage = HumanMessage.parse_chat_completion_message(user_query, ignore_unknown_media=True)

        message_round = 0
        history_message_count = 0
        is_retry_chat = False
        last_speaker_name = None
        history_messages = None

        ########################################################
        app_config = self.system_app.config.configs.get("app_config")
        web_config = app_config.service.web

        root_tracer.set_context_conv_id(agent_conv_id)

        # init gpts  memory
        vis_render = ext_info.get("vis_render", "derisk_vis_incr")

        vis_manager = get_vis_manager()
        vis_protocol = vis_manager.get_by_name(vis_render)(derisk_url=web_config.web_url)
        ext_info["incremental"] = vis_protocol.incremental

        self.memory.init(
            agent_conv_id,
            history_messages=history_messages,
            start_round=history_message_count,
            vis_converter=vis_protocol,
        )
        #########################################################

        # 检查最后一个对话记录是否完成，如果是等待状态，则要继续进行当前对话
        if gpts_conversations and len(gpts_conversations) > 0:
            last_gpts_conversation: GptsConversationsEntity = gpts_conversations[-1]
            logger.info(f"last conversation status:{last_gpts_conversation.__dict__}")
            if last_gpts_conversation.state == Status.WAITING.value:
                is_retry_chat = True
                agent_conv_id = last_gpts_conversation.conv_id

                gpts_messages: List[GptsMessage] = (
                    self.gpts_messages_dao.get_by_conv_id(agent_conv_id)
                )

                last_message = gpts_messages[-1]
                message_round = last_message.rounds + 1
                last_speaker_name = last_message.sender

        historical_dialogues: List[GptsMessage] = []

        keep_start_rounds: int = 1
        keep_end_rounds: int = 2

        # Create a new gpts conversation record

        ## When creating a new gpts conversation record, determine whether to
        # include the history of previous topics according to the application
        # definition.

        if keep_start_rounds > 0 or keep_end_rounds > 0:
            if gpts_conversations and len(gpts_conversations) > 0:
                rely_conversations = []
                if keep_start_rounds + keep_end_rounds < len(
                        gpts_conversations
                ):
                    if keep_start_rounds > 0:
                        front = gpts_conversations[keep_start_rounds:]
                        rely_conversations.extend(front)
                    if keep_end_rounds > 0:
                        back = gpts_conversations[-keep_end_rounds:]
                        rely_conversations.extend(back)
                else:
                    rely_conversations = gpts_conversations
                for gpts_conversation in rely_conversations:
                    temps: List[GptsMessage] = await self.memory.get_messages(
                        gpts_conversation.conv_id
                    )
                    if temps and len(temps) > 1:
                        historical_dialogues.append(temps[0])
                        historical_dialogues.append(temps[-1])

        self.gpts_conversations.add(
            GptsConversationsEntity(
                conv_id=agent_conv_id,
                conv_session_id=conv_session_id,
                user_goal=json.dumps(user_query.to_dict(), ensure_ascii=False),
                gpts_name=quick_app_name,
                team_mode=TeamMode.NATIVE_APP.value,
                state=Status.RUNNING.value,
                max_auto_reply_round=0,
                auto_reply_count=0,
                user_code=user_code,
                sys_code=sys_code,
                vis_render=vis_render,
            )
        )

        try:
            task = asyncio.create_task(
                _quick_agent(agent_conv_id, language="zh", init_message_rounds=message_round, user_code=user_code, sys_code=sys_code)
            )
            async for chunk in multi_agents.chat_messages(agent_conv_id):
                if chunk and len(chunk) > 0:
                    try:
                        content = json.dumps(
                            {"vis": chunk},
                            default=serialize,
                            ensure_ascii=False,
                        )
                        resp = f"data: {content}\n\n"
                        first_chunk_time = first_chunk_time or current_ms()
                        yield task, resp, agent_conv_id
                    except Exception as e:
                        logger.exception(
                            f"get messages {quick_app_code} Exception!" + str(e)
                        )
                        yield task, f"data: {str(e)}\n\n", agent_conv_id

            # 5. 最终处理
            if task.done() and task.exception():
                # 如果任务有异常，返回错误
                logger.exception(f"agent chat exception!{conv_session_id}")
                raise task.exception()
            else:
                # 正常结束
                yield task, _format_vis_msg("[DONE]"), agent_conv_id
            succeed = True
        except asyncio.CancelledError:
            # 取消时不立即回调
            logger.info("Generator cancelled, delaying callback")
            raise
        except Exception as e:
            logger.exception(f"Agent chat have error!{str(e)}")
            raise e
            # yield task, str(e), agent_conv_id
        finally:
            digest(CHAT_LOGGER, "CHAT_DONE", conv_id=conv_session_id, app_code=quick_app_code, user_code=user_code,
                   succeed=succeed, cost_ms=current_ms() - start_ts,
                   first_chunk_time=(first_chunk_time - start_ts) if first_chunk_time else -1)

    async def save_conversation(
            self,
            conv_session_id: str,
            agent_conv_id: str,
            current_message: StorageConversation,
            final_message: Optional[str] = None,
            err_msg: Optional[str] = None,
            chat_call_back: Optional[Callable[..., Optional[Any]]] = None,
    ):
        """最终对话保存（按格式收集最终内容，回调，并销毁缓存空间）

        Args:
            conv_session_id:会话id
            agent_conv_id:对话id
        """
        logger.info(f"Agent chat end, save conversation {agent_conv_id}!")
        """统一保存对话结果的逻辑"""
        if not final_message:
            try:
                final_message = await self.stable_message(agent_conv_id)
            except Exception as e:
                logger.exception(f"获取{agent_conv_id}最终消息异常: {str(e)}")

        if callable(chat_call_back):
            final_report = None
            try:
                final_report = await self.memory.user_answer(agent_conv_id)
            except Exception as e:
                logger.exception(f"获取{conv_session_id}最终报告异常: {str(e)}")

            await chat_call_back(conv_session_id, agent_conv_id, final_message, final_report, err_msg)

        logger.info(f"获取{conv_session_id}最终消息: {final_message}, 异常信息:{err_msg}")
        self.memory.clear(agent_conv_id)
        if err_msg:
            if not final_message:
                final_message = ""
            current_message.add_view_message(final_message + "\n" + err_msg)
        else:
            current_message.add_view_message(final_message)
        current_message.end_current_round()
        current_message.save_to_storage()

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
            **ext_info,
    ):
        """智能体对话入口V1版本(构建会话。发起Agent对话,如果断开链接立即中断对话)

        Args:
            conv_uid:   会话id
            gpts_name:  要对话的智能体
            user_query: 用户消息，支持多模态
        """
        logger.info(f"app_chat:{gpts_name},{user_query},{conv_uid}")
        # Temporary compatible scenario messages
        conv_serve = ConversationServe.get_instance(CFG.SYSTEM_APP)
        current_message: StorageConversation = _build_conversation(
            conv_id=conv_uid,
            select_param=gpts_name,
            summary=user_query,
            model_name="",
            app_code=gpts_name,
            conv_serve=conv_serve,
            user_name=user_code,
        )
        current_message.save_to_storage()
        current_message.start_new_round()
        current_message.add_user_message(user_query)
        agent_conv_id, gpts_conversations = await multi_agents.build_agent_conv_id(conv_uid, **ext_info)
        agent_task = None
        error_info = None
        try:
            async for task, chunk, agent_conv_id in multi_agents.agent_chat(
                    conv_uid,
                    agent_conv_id,
                    gpts_name,
                    user_query,
                    user_code,
                    sys_code,
                    **ext_info,
                    specify_config_code=specify_config_code,
                    gpts_conversations=gpts_conversations,
                    stream=stream,
            ):
                agent_task = task
                yield chunk
        except asyncio.CancelledError:
            # Client disconnects
            logger.warning("Client disconnected")
            if agent_task:
                logger.info(f"Chat to App {gpts_name}:{agent_conv_id} Cancel!")
                agent_task.cancel()
        except Exception as e:
            logger.exception(f"Chat to App {gpts_name} Failed!agent_conv_id:{agent_conv_id}." + str(e))
            error_info = str(e)
            yield str(e)
        finally:
            logger.info(f"save agent chat info！{conv_uid}")
            if not agent_task:
                logger.info("对话协程已释放！")
            await self.save_conversation(conv_uid, agent_conv_id, current_message, err_msg=error_info,
                                         chat_call_back=chat_call_back)

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
    ) -> StreamingResponse:
        """智能体对话入口V2版本(构建会话。发起Agent对话,如果断开链接立即转为后台运行，成功后保存对话进行回调,推荐回调里要推送最终消息的才可以使用)

        Args:
            conv_uid:   会话id
            gpts_name:  要对话的智能体
            user_query: 用户消息，支持多模态
        """
        logger.info(f"app_chat_v2:{gpts_name},{user_query},{conv_uid}")
        # Temporary compatible scenario messages
        conv_serve = ConversationServe.get_instance(CFG.SYSTEM_APP)
        current_message: StorageConversation = _build_conversation(
            conv_id=conv_uid,
            select_param=gpts_name,
            summary="",
            model_name="",
            app_code=gpts_name,
            conv_serve=conv_serve,
            user_name=user_code,
        )
        current_message.save_to_storage()
        current_message.start_new_round()
        current_message.add_user_message(user_query if isinstance(user_query, str) else user_query.content)

        task_queue = asyncio.Queue()
        processing_complete = asyncio.Event()
        state = {"last_agent_conv_id": None,
                 "lock": asyncio.Lock(),
                 "error": None  # 新增的错误存储字段
                 }

        async def agent_processor():
            """独立运行的处理任务，不受客户端连接状态影响"""
            try:
                agent_conv_id, gpts_conversations = await multi_agents.build_agent_conv_id(conv_uid)
                async for task, chunk, agent_conv_id in multi_agents.agent_chat(
                        conv_uid,
                        agent_conv_id,
                        gpts_name,
                        user_query,
                        user_code,
                        sys_code,
                        specify_config_code=specify_config_code,
                        gpts_conversations=gpts_conversations,
                        stream=stream,
                        chat_in_params=chat_in_params,
                        **ext_info,
                ):
                    async with state["lock"]:
                        state["last_agent_conv_id"] = agent_conv_id
                    await task_queue.put((chunk, agent_conv_id))
            # 新增：捕获所有异常并存储在state中
            except Exception as e:
                logger.exception(f"app_chat_v2 处理异常: {e}")
                async with state["lock"]:
                    # 存储异常对象和字符串表示
                    state["error"] = str(e)

                await task_queue.put((_format_vis_msg(str(e)), state["last_agent_conv_id"]))

            finally:
                processing_complete.set()  # 标记任务完成

        # 创建受防护的任务
        processor_task = asyncio.create_task(agent_processor())

        async def stream_generator() -> AsyncGenerator[str, None]:
            """增强稳定性的流生成器"""
            client_disconnected = False
            try:
                # 持续生产数据直到任务完成且队列清空
                while not (processing_complete.is_set() and task_queue.empty()):
                    try:
                        # 动态超时：未完成时等待更久
                        timeout = 1.0 if not processing_complete.is_set() else 0.1
                        chunk, agent_conv_id = await asyncio.wait_for(task_queue.get(), timeout=timeout)
                        error_info = ""
                        async with state["lock"]:
                            state["last_agent_conv_id"] = agent_conv_id
                            if state["error"]:
                                error_info = state["error"]
                        yield chunk + "\n" + error_info, agent_conv_id
                        task_queue.task_done()
                    except asyncio.TimeoutError:
                        if processing_complete.is_set() and task_queue.empty():
                            break
                        continue  # 继续检查状态
            except asyncio.CancelledError:
                logger.info(f"客户端断开: {conv_uid}")
                client_disconnected = True
            finally:
                async def background_cleanup():
                    """后台清理核心逻辑"""
                    try:
                        # 关键防护层：防止处理器任务被取消
                        await asyncio.shield(processor_task)
                    except Exception as e:
                        logger.exception(f"处理器任务异常: {e}")
                    finally:
                        # 确保处理完所有数据
                        while not task_queue.empty():
                            chunk, agent_conv_id = task_queue.get_nowait()
                            async with state["lock"]:
                                state["last_agent_conv_id"] = agent_conv_id
                            task_queue.task_done()
                        # 提取错误信息
                        error_info = None
                        async with state["lock"]:
                            if state["error"]:
                                error_info = state["error"]
                        # 最终保存
                        await multi_agents.save_conversation(
                            conv_uid,
                            state["last_agent_conv_id"],
                            current_message,
                            err_msg=error_info,
                            chat_call_back=chat_call_back,
                        )
                        logger.debug(f"对话持久化完成: {conv_uid}")

                # 添加后台任务（无论是否断开）
                background_tasks.add_task(background_cleanup)
                # 主动让出控制权以确保任务启动
                await asyncio.sleep(0)

        async for chunk, agent_conv_id in stream_generator():
            yield chunk

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
            **ext_info,
    ) -> Tuple[Optional[str], Optional[str]]:
        """智能体对话入口V3版本(构建异步会话。发起Agent对话,立即返回，并后台运行，成功后保存对话进行回调)

        Args:
            conv_uid:   会话id
            gpts_name:  要对话的智能体
            user_query: 用户消息，支持多模态
        """
        logger.info(f"app_chat_v3:{conv_uid},{gpts_name},{user_query}")

        # 初始化对话记录
        conv_serve = ConversationServe.get_instance(CFG.SYSTEM_APP)
        current_message: StorageConversation = _build_conversation(
            conv_id=conv_uid,
            select_param=gpts_name,
            summary="",
            model_name="",
            app_code=gpts_name,
            conv_serve=conv_serve,
            user_name=user_code,
        )
        current_message.save_to_storage()
        current_message.start_new_round()
        current_message.add_user_message(user_query)

        # 用于同步第一个chunk的事件和变量
        first_chunk_event = asyncio.Event()
        first_chunk_data = None
        agent_conv_id, gpts_conversations = await multi_agents.build_agent_conv_id(conv_uid)

        async def agent_processor():
            logger.info("agent_processor start!")
            """后台处理所有生成逻辑的协程"""
            nonlocal first_chunk_data, agent_conv_id
            agent_exception = None
            try:
                # 强制立即释放事件循环控制权
                await asyncio.sleep(0)
                async for task, chunk, new_conv_id in multi_agents.agent_chat(
                        conv_uid,
                        agent_conv_id,
                        gpts_name,
                        user_query,
                        user_code,
                        sys_code,
                        **ext_info,
                        specify_config_code=specify_config_code,
                        gpts_conversations=gpts_conversations,
                        stream=stream,
                ):
                    agent_conv_id = new_conv_id or agent_conv_id

                    if not first_chunk_event.is_set():
                        first_chunk_data = chunk
                        first_chunk_event.set()

                    logger.debug(f"Async chat running![{agent_conv_id}],{chunk}")
            except Exception as e:
                logger.error(f"Agent processing failed: {str(e)}")
                agent_exception = str(e)
                if not first_chunk_event.is_set():
                    first_chunk_event.set()  # 异常情况下也要触发事件
            finally:
                await multi_agents.save_conversation(
                    conv_uid,
                    agent_conv_id,
                    current_message,
                    err_msg=agent_exception,  # 确保异常传递到后续处理
                    chat_call_back=chat_call_back,
                )

        # 创建独立任务并立即调度
        processor_task = asyncio.create_task(agent_processor())

        try:
            # 添加双重检测机制
            done, pending = await asyncio.wait(
                [first_chunk_event.wait(), processor_task],
                timeout=600.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if first_chunk_event.is_set():
                return first_chunk_data, agent_conv_id
            elif processor_task.done():
                if processor_task.exception():
                    raise processor_task.exception()
                raise TimeoutError("Agent processing completed without producing data")
            else:
                raise TimeoutError("Timeout waiting for initial response")

        except asyncio.CancelledError:
            processor_task.cancel()
            raise

    async def build_agent_by_app_code(self, app_code: str, context: AgentContext, agent_memory: AgentMemory = None,
                                      **kwargs) -> ConversableAgent:
        app_service = get_app_service()
        gpts_app: ServerResponse = await app_service.app_detail(app_code, building_mode=False)
        agent_memory = agent_memory or self.get_or_build_agent_memory(context.conv_id, gpts_app.app_name)
        resource_manager: ResourceManager = get_resource_manager()
        return await self._build_agent_by_gpts(context=context, agent_memory=agent_memory, rm=resource_manager,
                                               app=gpts_app, **kwargs)

    async def _build_agent_by_gpts(
            self,
            context: AgentContext,
            agent_memory: AgentMemory,
            rm: ResourceManager,
            app: GptsApp,
            **kwargs,
    ) -> ConversableAgent:
        """Build a dialogue target agent through gpts configuration"""
        from datetime import datetime
        logger.info(f"_build_agent_by_gpts:{app.app_code},{app.app_name}, start:{datetime.now()}")
        try:
            employees: List[ConversableAgent] = []
            if app.details is not None and len(app.details) > 0:
                employees: List[ConversableAgent] = await self._build_employees(
                    context, agent_memory, rm, [deepcopy(item) for item in app.details]
                )

            team_mode = TeamMode(app.team_mode)
            ## 模型服务
            if not self.llm_provider:
                worker_manager = CFG.SYSTEM_APP.get_component(
                    ComponentType.WORKER_MANAGER_FACTORY, WorkerManagerFactory
                ).create()
                self.llm_provider = DefaultLLMClient(
                    worker_manager, auto_convert_message=True
                )

            if team_mode == TeamMode.SINGLE_AGENT:
                if employees is not None and len(employees) == 1:
                    recipient = employees[0]
                else:
                    cls: Type[ConversableAgent] = self.agent_manage.get_by_name(app.agent)
                    llm_config = LLMConfig(
                        llm_client=self.llm_provider,
                        llm_strategy=LLMStrategyType(app.llm_config.llm_strategy),
                        strategy_context=app.llm_config.llm_strategy_value
                    )
                    ## 处理agent资源内容
                    depend_resource = await blocking_func_to_async(
                        CFG.SYSTEM_APP, rm.build_resource, app.all_resources
                    )

                    agent_context = deepcopy(context)
                    agent_context.agent_app_code = app.app_code

                    recipient = (
                        await cls()
                        .bind(agent_context)
                        .bind(agent_memory)
                        .bind(llm_config)
                        .bind(depend_resource)
                        # .bind(prompt_template)
                        .build()
                    )

                ## 处理Agent实例的基本信息
                temp_profile = recipient.profile.copy()
                temp_profile.desc = app.app_describe
                temp_profile.name = app.app_name
                temp_profile.avatar = app.icon
                if app.system_prompt_template is not None:
                    temp_profile.system_prompt_template = app.system_prompt_template
                if app.user_prompt_template:
                    temp_profile.user_prompt_template = app.user_prompt_template
                recipient.bind(temp_profile)
                return recipient
            elif TeamMode.AUTO_PLAN == team_mode:

                agent_manager = get_agent_manager()
                auto_team_ctx = app.team_context

                manager_cls: Type[ConversableAgent] = agent_manager.get_by_name(
                    auto_team_ctx.teamleader
                )
                manager = manager_cls()

                llm_config = LLMConfig(
                    llm_client=self.llm_provider,
                    llm_strategy=LLMStrategyType(app.llm_config.llm_strategy),
                    strategy_context=app.llm_config.llm_strategy_value
                )

                if app.all_resources:
                    depend_resource = await blocking_func_to_async(
                        CFG.SYSTEM_APP, rm.build_resource, app.all_resources
                    )
                    manager.bind(depend_resource)

                agent_context = deepcopy(context)
                agent_context.agent_app_code = app.app_code

                manager = await manager.bind(agent_context).bind(llm_config).bind(agent_memory).build()

                ## 处理Agent实例的基本信息
                temp_profile = manager.profile.copy()
                temp_profile.desc = app.app_describe
                temp_profile.name = app.app_name
                temp_profile.avatar = app.icon
                if app.system_prompt_template is not None:
                    temp_profile.system_prompt_template = app.system_prompt_template
                if app.user_prompt_template:
                    temp_profile.user_prompt_template = app.user_prompt_template
                manager.bind(temp_profile)

                if isinstance(manager, ManagerAgent) and len(employees) > 0:
                    manager.hire(employees)
                logger.info(
                    f"_build_agent_by_gpts return:{manager.profile.name},{manager.profile.desc},{id(manager)}"
                )
                return manager
            elif TeamMode.AWEL_LAYOUT == team_mode:
                team_context: AWELTeamContext = app.team_context
                from derisk_app.openapi.api_v1.api_v1 import get_chat_flow
                agent: ConversableAgent = AwelRunnerAgent(team_context=team_context,
                                                          flow_service=get_chat_flow())  # todo: 通过team_context配置动态加载agent

                agent_context = deepcopy(context)
                agent_context.agent_app_code = app.app_code

                agent = await agent.bind(agent_context).bind(agent_memory).build()

                temp_profile = agent.profile.copy()
                temp_profile.desc = app.app_describe
                temp_profile.name = app.app_name
                temp_profile.avatar = app.icon
                agent.bind(temp_profile)

                return agent
            elif TeamMode.NATIVE_APP == team_mode:
                raise ValueError("Native APP chat not supported!")
            else:
                raise ValueError(f"Unknown Agent Team Mode!{team_mode}")
        finally:
            logger.info(f"_build_agent_by_gpts:{app.app_code},{app.app_name}, end:{datetime.now()}")

    async def _build_employees(
            self,
            context: AgentContext,
            agent_memory: AgentMemory,
            rm: ResourceManager,
            app_details: List[GptsAppDetail],
    ) -> List[ConversableAgent]:
        """Constructing dialogue members through gpts-related Agent or gpts app information."""
        from datetime import datetime
        logger.info(
            f"_build_employees:{[item.agent_role + ',' + item.agent_name for item in app_details] if app_details else ''},start:{datetime.now()}"
        )
        app_service = get_app_service()

        async def _build_employee_agent(record: GptsAppDetail):
            logger.info(f"_build_employees循环:{record.agent_role},{record.agent_name}, start:{datetime.now()}")
            if record.type == "app":
                gpt_app: GptsApp = deepcopy(await app_service.app_detail(record.agent_role, building_mode=False))
                if not gpt_app:
                    raise ValueError(f"Not found app {record.agent_role}!")
                employee_agent = await self._build_agent_by_gpts(
                    context, agent_memory, rm, gpt_app
                )
                logger.info(
                    f"append employee_agent:{employee_agent.profile.name},{employee_agent.profile.desc},{id(employee_agent)}"
                )
                return employee_agent
            else:
                # cls: Type[ConversableAgent] = self.agent_manage.get_by_name(
                #     record.agent_role
                # )
                # llm_config = LLMConfig(
                #     llm_client=self.llm_provider,
                #     llm_strategy=LLMStrategyType(record.llm_strategy),
                #     strategy_context=record.llm_strategy_value,
                # )
                # prompt_template = None
                # if record.prompt_template:
                #     prompt_template: PromptTemplate = prompt_service.get_template(
                #         prompt_code=record.prompt_template
                #     )
                # depend_resource = await blocking_func_to_async(
                #     CFG.SYSTEM_APP, rm.build_resource, record.resources
                # )
                # agent = (
                #     await cls()
                #     .bind(context)
                #     .bind(agent_memory)
                #     .bind(llm_config)
                #     .bind(depend_resource)
                #     .bind(prompt_template)
                #     .build()
                # )
                # if record.agent_describe:
                #     temp_profile = agent.profile.copy()
                #     temp_profile.desc = record.agent_describe
                #     temp_profile.name = record.agent_name
                #     agent.bind(temp_profile)
                raise ValueError("当前应用数据已经无法支持，请重新编辑构建！")
            logger.info(f"_build_employees循环:{record.agent_role},{record.agent_name}, end:{datetime.now()}")
            return agent

        api_tasks = []
        for record in app_details:
            api_tasks.append(_build_employee_agent(record))

        from derisk.util.chat_util import run_async_tasks
        employees = await run_async_tasks(tasks=api_tasks, concurrency_limit=10)
        logger.info(
            f"_build_employees return:{[item.profile.name if item.profile.name else '' + ',' + str(id(item)) for item in employees]},end:{datetime.now()}"
        )
        return employees

    def chat_in_params_to_context(self, chat_in_params: Optional[List[ChatInParamValue]]) -> Tuple[
        Dict[str, Any], Dict[str, Any]]:
        """处理对话输出参数"""
        context = {}
        ## 输入层参数转Agent上下文参数
        ### 1.资源类型统一变成对话上下文参数
        ### 2.其他类型统一变成环境上下文参数
        llm_context = {}
        env_context = {}
        if chat_in_params:
            for param in chat_in_params:
                if AppParamType.Resource.value == param.param_type:

                    if param.sub_type not in FILE_RESOURCES:
                        if isinstance(param.param_value, str):
                            value_obj = json.loads(param.param_value)
                            if isinstance(value_obj, list):
                                r_value = value_obj[0]
                            else:
                                r_value = value_obj
                        else:
                            r_value = param.param_value
                        chat_in_resource = AgentResource.from_dict({
                            "type": param.sub_type,
                            "name": "用户选择资源",
                            "value": r_value
                        })

                        llm_context[param.sub_type] = chat_in_resource
                    else:
                        llm_context[param.sub_type] = param.param_value
                else:
                    llm_context[param.param_type] = param.param_value
        return llm_context, env_context

    async def agent_team_chat_new(
            self,
            user_code: str,
            user_query: HumanMessage,
            conv_session_id: str,
            conv_uid: str,
            gpts_app: GptsApp,
            agent_memory: AgentMemory,
            is_retry_chat: bool = False,
            last_speaker_name: str = None,
            init_message_rounds: int = 0,
            link_sender: ConversableAgent = None,
            app_link_start: bool = False,
            historical_dialogues: Optional[List[GptsMessage]] = None,
            rely_messages: Optional[List[GptsMessage]] = None,
            stream: Optional[bool] = True,
            chat_in_params: Optional[List[ChatInParamValue]] = None,
            **ext_info,
    ):
        gpts_status = Status.COMPLETE.value
        try:

            if isinstance(user_query.content, List):
                from derisk_serve.file.serve import Serve as FileServe
                from derisk.core.interface.media import MediaContent

                file_serve = FileServe.get_instance(self.system_app)
                new_content = MediaContent.replace_url(
                    user_query.content, file_serve.replace_uri
                )
                user_query.content = new_content

            self.agent_manage = get_agent_manager()

            from derisk.agent.core.agent import ENV_CONTEXT_KEY
            from derisk.agent.core.agent import LLM_CONTEXT_KEY

            ## 处理对话输入参数，进行分层，环境参数穿透当前会话不落表，llm参数作为消息的扩展参数随消息落表，agent控制是否向下传递
            llm_context, env_context = self.chat_in_params_to_context(chat_in_params)

            if ext_info.get(ENV_CONTEXT_KEY):
                env_context.update(ext_info.get(ENV_CONTEXT_KEY))
            context: AgentContext = AgentContext(
                user_id=user_code,
                conv_id=conv_uid,
                conv_session_id=conv_session_id,
                trace_id=first(
                    ext_info.get("trace_id", None),
                    root_tracer.get_context_trace_id(),
                    uuid.uuid4().hex,
                ),
                rpc_id=ext_info.get("rpc_id", "0.1"),
                gpts_app_code=gpts_app.app_code,
                gpts_app_name=gpts_app.app_name,
                language=gpts_app.language,
                app_link_start=app_link_start,
                incremental=ext_info.get("incremental", False),
                env_context=env_context,
                stream=stream,
                extra=ext_info,
            )

            root_tracer.start_span(
                operation_name="agent_chat", parent_span_id=context.trace_id
            )

            rm = get_resource_manager()

            # init llm provider
            ### init chat param
            ## 检查应用是否配置完整
            if not gpts_app.agent:
                raise ValueError("当前应用还没配置Agent模版无法开启对话!")
            if not gpts_app.llm_config:
                raise ValueError("当前应用还没配置模型无法开始对话!")

            recipient = await self._build_agent_by_gpts(
                context,
                agent_memory,
                rm,
                gpts_app,
                **ext_info,
            )

            if is_retry_chat:
                # retry chat
                self.gpts_conversations.update(conv_uid, Status.RUNNING.value)

            user_proxy = None
            if link_sender:
                await link_sender.initiate_chat(
                    recipient=recipient,
                    message=user_query,
                    is_retry_chat=is_retry_chat,
                    last_speaker_name=last_speaker_name,
                    message_rounds=init_message_rounds,
                )
            else:
                user_proxy: UserProxyAgent = (
                    await UserProxyAgent().bind(context).bind(agent_memory).build()
                )
                user_code = ext_info.get("user_code", None)
                if user_code:
                    app_config = self.system_app.config.configs.get("app_config")
                    web_config = app_config.service.web
                    user_proxy.profile.avatar = (
                        f"{web_config.web_url}/user/avatar?loginName={user_code}"
                    )
                await user_proxy.initiate_chat(
                    recipient=recipient,
                    message=user_query,
                    is_retry_chat=is_retry_chat,
                    last_speaker_name=last_speaker_name,
                    message_rounds=init_message_rounds,
                    historical_dialogues=user_proxy.convert_to_agent_message(
                        historical_dialogues
                    ),
                    rely_messages=rely_messages,
                    approval_message_id=ext_info.get("approval_message_id"),
                    **llm_context,
                )

            if user_proxy:
                # Check if the user has received a question.
                if user_proxy.have_ask_user():
                    gpts_status = Status.WAITING.value
            if not app_link_start:
                self.gpts_conversations.update(conv_uid, gpts_status)
        except Exception as e:
            logger.error(f"chat abnormal termination！{str(e)}", e)
            self.gpts_conversations.update(conv_uid, Status.FAILED.value)
            raise ValueError(f"The conversation is abnormal!{str(e)}")
        finally:
            if not app_link_start:
                await self.memory.complete(conv_uid)

        return conv_uid

    async def chat_messages(
            self,
            conv_id: str,
            user_code: str = None,
            system_app: str = None,
    ):
        while True:
            queue = self.memory.queue(conv_id)
            if not queue:
                break
            item = await queue.get()
            if item == "[DONE]":
                queue.task_done()
                break
            else:
                yield item
                await asyncio.sleep(0.005)

    async def stable_message(
            self, conv_id: str, user_code: str = None, system_app: str = None
    ):
        return await self.memory.vis_final(conv_id)

    def gpts_conv_list(self, user_code: str = None, system_app: str = None):
        return self.gpts_conversations.get_convs(user_code, system_app)

    async def topic_terminate(
            self,
            conv_id: str,
    ):
        gpts_conversations: List[GptsConversationsEntity] = (
            self.gpts_conversations.get_by_session_id_asc(conv_id)
        )
        # 检查最后一个对话记录是否完成，如果是等待状态，则要继续进行当前对话
        if gpts_conversations and len(gpts_conversations) > 0:
            last_gpts_conversation: GptsConversationsEntity = gpts_conversations[-1]
            if last_gpts_conversation.state == Status.WAITING.value:
                self.gpts_conversations.update(
                    last_gpts_conversation.conv_id, Status.COMPLETE.value
                )

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


def _format_vis_msg(msg: str):
    content = json.dumps({"vis": msg}, default=serialize, ensure_ascii=False)
    return f"data:{content} \n"


multi_agents = MultiAgents(system_app)
